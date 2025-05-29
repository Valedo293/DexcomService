# ---- main.py COMPLETO ----
from flask import Flask, jsonify, request
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
import os
import requests
from threading import Timer
from datetime import datetime, timedelta
from pymongo import MongoClient

# --- Carica variabili ambiente ---
load_dotenv()
USERNAME = os.getenv("DEXCOM_USERNAME")
PASSWORD = os.getenv("DEXCOM_PASSWORD")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
MONGO_URI = os.getenv("MONGO_URI")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_IDS = os.getenv("TELEGRAM_CHAT_IDS", "").split(",")

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

        if data_param:
            giorno = datetime.strptime(data_param, "%Y-%m-%d").date()
        else:
            giorno = datetime.utcnow().date()

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

# ---- MonitorGlicemia aggiornato ----
eventi_attivi = {}
notifiche_inviate = {}
silenzio_attivo = {}

def reset_evento(codice):
    eventi_attivi.pop(codice, None)
    notifiche_inviate.pop(codice, None)
    silenzio_attivo.pop(codice, None)

def manda_notifica(codice, titolo, messaggio):
    if notifiche_inviate.get(codice, 0) < 2:
        manda_telegram(f"🚨 {titolo}\n{messaggio}")
        notifiche_inviate[codice] = notifiche_inviate.get(codice, 0) + 1
        eventi_attivi[codice] = True
        print(f"[NOTIFICA] {codice}: {titolo}")
    else:
        print(f"[SKIP] Max notifiche per {codice}")

def monitor_loop():
    try:
        docs = list(entries_collection.find().sort("date", -1).limit(5))
        if len(docs) < 3:
            return

        cronologia = [{"valore": d["sgv"], "trend": d.get("direction", "→")} for d in reversed(docs)]
        v1, v2, v3 = cronologia[-3:]

        # RESET se glicemie ≥ 90 x 2 e trend positivo
        if v2["valore"] >= 90 and v3["valore"] >= 90 and v2["trend"] in ["→", "↑", "↗", "↑↑"] and v3["trend"] in ["→", "↑", "↗", "↑↑"]:
            for codice in list(eventi_attivi):
                reset_evento(codice)

        # 1. Discesa rapida 80–90 con trend ↓
        if 80 <= v3["valore"] < 90 and v3["trend"] == "↓":
            manda_notifica("discesa_rapida", "Discesa glicemica rapida", "Glicemia in calo. Valore < 90 con trend ↓.")
        
        elif "discesa_rapida" in eventi_attivi and v3["valore"] < 90 and v3["trend"] == "↓":
            manda_notifica("discesa_rapida", "Discesa glicemica continua", "Ancora sotto 90 con ↓.")

        # 2. Doppia discesa ↘
        if v2["valore"] <= 90 and v3["valore"] <= 90 and v2["trend"] == "↘" and v3["trend"] == "↘":
            manda_notifica("doppia_discesa", "Doppia discesa confermata", "Due glicemie consecutive ≤ 90 con trend ↘.")

        # 3. Discesa lenta → tra 78–90, max 2 notifiche, silenzio 5 min
        if v2["valore"] <= 86 and v3["valore"] <= 86 and v2["trend"] == "→" and v3["trend"] == "→":
            codice = "lenta_stabile"
            if codice not in silenzio_attivo:
                manda_notifica(codice, "Discesa lenta stabile", "Due valori stabili ≤ 86: attenzione.")
                if notifiche_inviate[codice] == 2:
                    silenzio_attivo[codice] = datetime.utcnow() + timedelta(minutes=5)
        # Silenzio attivo scaduto
        for codice in list(silenzio_attivo):
            if datetime.utcnow() > silenzio_attivo[codice]:
                reset_evento(codice)

    except Exception as e:
        print(f"❌ Errore monitor: {e}")
    finally:
        Timer(60, monitor_loop).start()

def invia_a_mongo():
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if not reading:
            return

        valore = float(reading.value)
        timestamp = reading.time
        trend = reading.trend_arrow or "Flat"

        scrivi_glicemia_su_mongo(valore, timestamp, trend)

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
monitor_loop()
app.run(host="0.0.0.0", port=5001)