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
USERNAME        = os.getenv("DEXCOM_USERNAME")
PASSWORD        = os.getenv("DEXCOM_PASSWORD")
SUPABASE_URL    = os.getenv("SUPABASE_URL")
SUPABASE_KEY    = os.getenv("SUPABASE_KEY")
MONGO_URI       = os.getenv("MONGO_URI")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

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
mongo_client       = MongoClient(MONGO_URI)
mongo_db           = mongo_client["nightscout"]
entries_collection = mongo_db.entries

# --- Logica Alert ---
alert_cronologia      = []
alert_attivo          = None
intervallo_notifica   = None

def send_push(titolo, messaggio):
    try:
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": f"{titolo.upper()}\n{messaggio}"
            }
            res = requests.post(url, json=payload)
            print(f"[PUSH] Telegram: {res.status_code}")
    except Exception as e:
        print(f"❌ Errore Telegram: {e}")

def scrivi_glicemia_su_mongo(valore, timestamp, direction="Flat"):
    try:
        entry = {
            "type":       "sgv",
            "sgv":        valore,
            "dateString": timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            "date":       int(timestamp.timestamp() * 1000),
            "direction":  direction,
            "device":     "dexcom-server"
        }
        result = entries_collection.insert_one(entry)
        print(f"[MONGO] Scritta glicemia {valore} - ID: {result.inserted_id}")
    except Exception as e:
        print(f"❌ Errore scrittura Mongo: {e}")

def valuta_glicemia(valore, trend, timestamp):
    global alert_cronologia, alert_attivo, intervallo_notifica

    print("[DEBUG] ENTRATO IN valuta_glicemia")
    print(f"📥 INPUT ricevuto - valore: {valore}, trend: {trend}, timestamp: {timestamp}")

    alert_cronologia.append({"valore": valore, "trend": trend, "timestamp": timestamp})
    if len(alert_cronologia) > 5:
        alert_cronologia.pop(0)

    if alert_attivo:
        return None

    if valore < 75:
        alert_attivo = {"tipo": "ipoglicemia grave", "azione": "Assumi zuccheri semplici subito"}
    elif len([x for x in alert_cronologia if x["valore"] < 86]) >= 3 and valore <= 82:
        alert_attivo = {"tipo": "ipoglicemia lieve", "azione": "Mezzo succo o 1 biscotto se in discesa"}
    elif len(alert_cronologia) >= 2 and alert_cronologia[-2]["valore"] >= 90 and trend == "↓↓" and valore <= 85:
        alert_attivo = {"tipo": "discesa rapida", "azione": "Monitoraggio stretto: prepararsi a correggere"}

    if alert_attivo:
        send_push(alert_attivo["tipo"], alert_attivo["azione"])
        if intervallo_notifica:
            intervallo_notifica.cancel()
        intervallo_notifica = Timer(2 * 60, lambda: send_push(alert_attivo["tipo"], alert_attivo["azione"]))
        intervallo_notifica.start()

    return alert_attivo

@app.route("/alert", methods=["GET"])
def get_alert():
    return jsonify(alert_attivo or {}), 200

@app.route("/alert/clear", methods=["POST"])
def clear_alert():
    global alert_attivo, intervallo_notifica
    alert_attivo = None
    if intervallo_notifica:
        intervallo_notifica.cancel()
        intervallo_notifica = None
    return jsonify({"status": "ok"}), 200

def aggiorna_valore_tempo(id_pasto, campo, valore):
    try:
        url     = f"{SUPABASE_URL}/rest/v1/analisi_dati?id=eq.{id_pasto}"
        payload = {campo: valore}
        res     = requests.patch(url, headers=headers, json=payload)
        print(f"[SUPABASE] {campo}: {valore} -> {res.status_code}")
    except Exception as e:
        print(f"Errore PATCH Supabase: {e}")

def invia_ping(id_pasto, campo):
    try:
        dexcom  = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if reading:
            valore = float(reading.value)
            aggiorna_valore_tempo(id_pasto, campo, valore)
    except Exception as e:
        print(f"Errore ping {campo}: {e}")

@app.route("/pianifica-ping", methods=["POST"])
def pianifica_ping():
    try:
        dati     = request.get_json()
        id_pasto = dati.get("id")
        if not id_pasto:
            return jsonify({"errore": "ID del pasto mancante"}), 400

        Timer(60 * 60,  invia_ping, args=[id_pasto, "t1"]).start()
        Timer(90 * 60,  invia_ping, args=[id_pasto, "t2"]).start()
        Timer(180 * 60, invia_ping, args=[id_pasto, "t3"]).start()

        return jsonify({"messaggio": "Ping pianificati (via Timer)"}), 200
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

@app.route("/glicemia", methods=["GET"])
def ottieni_glicemia():
    try:
        dexcom  = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if reading:
            return jsonify({
                "glicemia": float(reading.value),
                "trend":    reading.trend_description,
            }), 200
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
        fine   = datetime.combine(giorno, datetime.max.time()) - timedelta(hours=2)
        ts_in  = int(inizio.timestamp() * 1000)
        ts_fn  = int(fine.timestamp() * 1000)

        risultati = list(entries_collection.find({
            "date": {"$gte": ts_in, "$lte": ts_fn}
        }).sort("date", 1))

        for r in risultati:
            r["_id"] = str(r["_id"])

        return jsonify(risultati), 200

    except Exception as e:
        return jsonify({"errore": str(e)}), 500

def invia_a_mongo():
    try:
        dexcom  = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if not reading:
            print("⚠️ Nessuna lettura disponibile da Dexcom")
            return

        valore    = float(reading.value)
        timestamp = reading.time
        trend     = reading.trend_arrow or "Flat"

        scrivi_glicemia_su_mongo(valore, timestamp, trend)
        print(f"[DEBUG] CHIAMO valuta_glicemia: {valore} | {trend} | {timestamp}")
        valuta_glicemia(valore, trend, timestamp)

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