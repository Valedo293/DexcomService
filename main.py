
from flask import Flask, jsonify, request
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
import os
import requests
from threading import Timer
from datetime import datetime, timedelta
from pymongo import MongoClient
import time

# --- Carica variabili ambiente ---
load_dotenv()
USERNAME = os.getenv("DEXCOM_USERNAME")
PASSWORD = os.getenv("DEXCOM_PASSWORD")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
MONGO_URI = os.getenv("MONGO_URI")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_IDS = [cid.strip() for cid in os.getenv("TELEGRAM_CHAT_IDS", "").split(",") if cid.strip()]

# --- Flask App ---
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- Headers per Supabase ---
headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# --- Connessione a MongoDB ---
mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client["nightscout"]
entries_collection = mongo_db.entries

def scrivi_glicemia_su_mongo(valore, timestamp, direction="Flat"):
    try:
        entry = {
            "type": "sgv",
            "sgv": valore,
            "dateString": timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            "date": int(timestamp.timestamp() * 1000),
            "direction": direction,
            "device": "dexcom-server"
        }
        result = entries_collection.insert_one(entry)
        print(f"[MONGO] Scritta glicemia {valore} - ID: {result.inserted_id}")
    except Exception as e:
        print(f"❌ Errore scrittura Mongo: {e}")

def aggiorna_valore_tempo(id_pasto, campo, valore):
    try:
        url = f"{SUPABASE_URL}/rest/v1/analisi_dati?id=eq.{id_pasto}"
        payload = {campo: valore}
        res = requests.patch(url, headers=headers, json=payload)
        print(f"[SUPABASE] {campo}: {valore} -> {res.status_code}")
    except Exception as e:
        print(f"Errore PATCH Supabase: {e}")

def invia_ping(id_pasto, campo):
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if reading:
            valore = float(reading.value)
            aggiorna_valore_tempo(id_pasto, campo, valore)
    except Exception as e:
        print(f"Errore ping {campo}: {e}")

@app.route("/pianifica-ping", methods=["POST"])
def pianifica_ping():
    try:
        dati = request.get_json()
        id_pasto = dati.get("id")
        if not id_pasto:
            return jsonify({"errore": "ID del pasto mancante"}), 400

        Timer(60 * 60, invia_ping, args=[id_pasto, "t1"]).start()
        Timer(90 * 60, invia_ping, args=[id_pasto, "t2"]).start()
        Timer(180 * 60, invia_ping, args=[id_pasto, "t3"]).start()

        return jsonify({"messaggio": "Ping pianificati (via Timer)"})
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

@app.route("/glicemia", methods=["GET"])
def ottieni_glicemia():
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if reading:
            return jsonify({
                "glicemia": float(reading.value),
                "trend": reading.trend_description,
            })
        else:
            return jsonify({"errore": "Nessuna lettura disponibile"}), 404
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

@app.route("/glicemie-oggi", methods=["GET"])
def glicemie_oggi():
    try:
        data_param = request.args.get("data")
        giorno = datetime.strptime(data_param, "%Y-%m-%d").date() if data_param else datetime.utcnow().date()
        inizio = datetime.combine(giorno, datetime.min.time()) - timedelta(hours=2)
        fine = datetime.combine(giorno, datetime.max.time()) - timedelta(hours=2)

        timestamp_inizio = int(inizio.timestamp() * 1000)
        timestamp_fine = int(fine.timestamp() * 1000)

        risultati = list(entries_collection.find({
            "date": {
                "$gte": timestamp_inizio,
                "$lte": timestamp_fine
            }
        }).sort("date", 1))

        for r in risultati:
            r["_id"] = str(r["_id"])

        return jsonify(risultati)
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

def manda_telegram(messaggio):
    for chat_id in CHAT_IDS:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            data = {"chat_id": chat_id.strip(), "text": messaggio}
            requests.post(url, json=data)
        except Exception as e:
            print(f"[ERRORE TELEGRAM] {e}")

eventi_attivi = {}
notifiche_inviate = {}

def reset_evento(codice):
    if codice in eventi_attivi:
        print(f"✅ Evento {codice} risolto")
        eventi_attivi.pop(codice)
        notifiche_inviate.pop(codice, None)

def manda_notifica(codice, titolo, messaggio):
    adesso = time.time()
    numero, ultimo = notifiche_inviate.get(codice, (0, 0))

    if numero >= 2 and (adesso - ultimo) < 1800:
        print(f"[SKIP] {codice} già inviato {numero} volte. Aspetto prima dei 30 minuti.")
        return

def manda_notifica(codice, titolo, messaggio):
    adesso = time.time()
    numero, ultimo = notifiche_inviate.get(codice, (0, 0))

    if numero >= 2 and (adesso - ultimo) < 1800:
        print(f"[SKIP] {codice} già inviato {numero} volte. Aspetto prima dei 30 minuti.")
        return

    print(f"[ALERT] {titolo} - {messaggio}")
    manda_telegram(f"🚨 {titolo}\n{messaggio}")
    notifiche_inviate[codice] = (numero + 1, adesso)
    eventi_attivi[codice] = True
    eventi_attivi[codice] = True


evento_stabile = {}

def gestisci_discesa_stabile(cronologia, evento_stabile):
    try:
        ora = datetime.utcnow()
        valore = cronologia[-1]["valore"]
        trend = cronologia[-1]["trend"]
        timestamp = cronologia[-1]["timestamp"]

        if evento_stabile.get("pausa_fino") and ora < evento_stabile["pausa_fino"]:
            print("🔕 Pausa attiva, nessun alert inviato")
            return evento_stabile

        if evento_stabile.get("ultimo_timestamp") == timestamp:
            print("🔁 Glicemia già analizzata, skip")
            return evento_stabile

        evento_stabile["ultimo_timestamp"] = timestamp

        if valore >= 83 and trend in ["→", "↗", "↑", "↑↑"]:
            if evento_stabile.get("attivo"):
                print("✅ Evento stabile chiuso per risalita")
            return {
                "attivo": False,
                "stato": None,
                "ultimo_timestamp": timestamp,
                "pausa_fino": None
            }

        if not evento_stabile.get("attivo"):
            ultimi_3 = cronologia[-3:]
            if all(x["valore"] < 85 for x in ultimi_3) and \
               ultimi_3[0]["valore"] > ultimi_3[1]["valore"] > ultimi_3[2]["valore"] and \
               all(x["trend"] == "→" for x in ultimi_3):
                manda_telegram("📉 Discesa glicemica stabile confermata\nMonitora con attenzione.")
                return {
                    "attivo": True,
                    "stato": "monitoraggio",
                    "ultimo_timestamp": timestamp,
                    "pausa_fino": None
                }
            return evento_stabile

        if evento_stabile["attivo"]:
            stato = evento_stabile.get("stato")

            if valore <= 80 and stato == "monitoraggio":
                manda_telegram("⚠️ Sei al limite (80 mg/dL)\nValuta se correggere.")
                evento_stabile["stato"] = "limite_80"

            elif valore <= 75 and stato != "correzione":
                manda_telegram("🚨 Glicemia a 75\nCorreggi subito con un succo o zuccheri.")
                evento_stabile["stato"] = "correzione"
                evento_stabile["pausa_fino"] = ora + timedelta(minutes=20)

        return evento_stabile

    except Exception as e:
        print(f"❌ Errore in gestisci_discesa_stabile: {e}")
        return evento_stabile


def monitor_loop():
    global evento_stabile
    try:
        docs = list(entries_collection.find().sort("date", -1).limit(5))
        if len(docs) < 3:
            print("⚠️ Dati insufficienti")
            return

        cronologia = [{
            "valore": d["sgv"],
            "trend": d.get("direction", "→"),
            "timestamp": d["date"]
        } for d in reversed(docs)]

        ultimo = cronologia[-1]
        valore = ultimo["valore"]
        trend = ultimo["trend"]

        print(f"📈 Ultima glicemia: {valore} - Trend: {trend}")

        if valore >= 85 and trend in ["→", "↑", "↗", "↑↑"]:
            for codice in list(eventi_attivi):
                reset_evento(codice)

        if valore < 90 and trend in ["↓", "↓↓"]:
            manda_notifica("rapida", "Discesa rapida",
                "Correggi subito con un succo o 3 bustine di zucchero o 3 caramelle zuccherate.")

        if all(x["trend"] == "→" for x in cronologia[-3:]) and 70 < cronologia[-1]["valore"] <= 86:
            manda_notifica("stabile_86", "Glicemia stabile ma in calo",
                "Monitora attentamente.\nSe continua a scendere, interverremo.")

        if valore == 70 and trend == "→":
            manda_notifica("stabile_70", "Glicemia a 70",
                "Se non hai corretto, fallo ora.\nPrendi mezzo succo o 2 bustine di zucchero.")

        if valore < 70 and trend == "→":
            manda_notifica("stabile_sotto70", "Glicemia ancora in discesa",
                "Prendi subito un succo intero.\nSe hai già corretto, attendi e monitora.")

        if trend == "↘" and cronologia[-1]["valore"] <= 86 and cronologia[-2]["valore"] >= 90:
            manda_notifica("lenta_salto", "Discesa glicemica lenta",
                "Correggi subito con un succo intero o 3 bustine di zucchero.")

        if all(x["trend"] == "↘" for x in cronologia[-3:]) and all(x["valore"] < 90 for x in cronologia[-3:]):
            manda_notifica("lenta_graduale", "Discesa lenta confermata",
                "Correggi con un succo intero o 3 bustine di zucchero.")
    except Exception as e:
        print(f"❌ Errore loop monitor: {e}")

def invia_a_mongo():
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if not reading:
            print("⚠️ Nessuna lettura disponibile da Dexcom")
            return

        valore = float(reading.value)
        timestamp = reading.time
        trend = reading.trend_arrow or "Flat"

        scrivi_glicemia_su_mongo(valore, timestamp, trend)
        monitor_loop()

    except Exception as e:
        print(f"❌ Errore lettura/scrittura Dexcom: {e}")
    finally:
        Timer(300, invia_a_mongo).start()

@app.after_request
def after_request(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return response

# --- Avvio ---
invia_a_mongo()
app.run(host="0.0.0.0", port=5001)
