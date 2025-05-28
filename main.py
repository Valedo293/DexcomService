from flask import Flask, jsonify, request
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
from threading import Timer
from datetime import datetime, timedelta
from pymongo import MongoClient
import os
import requests

# --- Carica variabili ambiente ---
load_dotenv()
USERNAME         = os.getenv("DEXCOM_USERNAME")
PASSWORD         = os.getenv("DEXCOM_PASSWORD")
SUPABASE_URL     = os.getenv("SUPABASE_URL")
SUPABASE_KEY     = os.getenv("SUPABASE_KEY")
MONGO_URI        = os.getenv("MONGO_URI")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- Flask App ---
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- Headers Supabase ---
headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# --- MongoDB ---
mongo_client       = MongoClient(MONGO_URI)
mongo_db           = mongo_client["nightscout"]
entries_collection = mongo_db.entries

# --- Alert ---
alert_attivo        = None
alert_cronologia    = []
intervallo_notifica = None

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
    global alert_attivo, alert_cronologia, intervallo_notifica

    alert_cronologia.append({"valore": valore, "trend": trend, "timestamp": timestamp})
    if len(alert_cronologia) > 5:
        alert_cronologia.pop(0)

    if alert_attivo:
        return

    # --- SOGLIE ---
    if valore < 75:
        alert_attivo = {"tipo": "Ipoglicemia grave", "azione": "Assumi zuccheri semplici subito"}
    elif valore <= 82 and len([x for x in alert_cronologia if x["valore"] < 86]) >= 3:
        alert_attivo = {"tipo": "Ipoglicemia lieve", "azione": "Mezzo succo o 1 biscotto se in discesa"}
    elif len(alert_cronologia) >= 2 and alert_cronologia[-2]["valore"] >= 90 and trend == "↓↓" and valore <= 85:
        alert_attivo = {"tipo": "Discesa rapida", "azione": "Monitoraggio stretto: prepararsi a correggere"}

    if alert_attivo:
        send_push(alert_attivo["tipo"], alert_attivo["azione"])
        if intervallo_notifica:
            intervallo_notifica.cancel()
        intervallo_notifica = Timer(2 * 60, lambda: send_push(alert_attivo["tipo"], alert_attivo["azione"]))
        intervallo_notifica.start()

def invia_a_mongo():
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if not reading:
            print("⚠️ Nessuna lettura disponibile")
            return

        valore    = float(reading.value)
        timestamp = reading.time
        trend     = reading.trend_arrow or "Flat"

        scrivi_glicemia_su_mongo(valore, timestamp, trend)
        valuta_glicemia(valore, trend, timestamp)

    except Exception as e:
        print(f"❌ Errore: {e}")
    finally:
        Timer(300, invia_a_mongo).start()

@app.route("/glicemia", methods=["GET"])
def ottieni_glicemia():
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
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

@app.after_request
def after_request(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return response

# --- AVVIO ---
if __name__ == "__main__":
    print("🚀 DexcomService attivo")
    invia_a_mongo()
    app.run(host="0.0.0.0", port=5001)