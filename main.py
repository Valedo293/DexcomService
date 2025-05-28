from flask import Flask, jsonify
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
import os
import requests
from threading import Timer
from datetime import datetime
from pymongo import MongoClient

# --- Carica variabili ambiente ---
load_dotenv()
USERNAME = os.getenv("DEXCOM_USERNAME")
PASSWORD = os.getenv("DEXCOM_PASSWORD")
MONGO_URI = os.getenv("MONGO_URI")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_IDS = os.getenv("TELEGRAM_CHAT_IDS", "").split(",")

# --- Flask App ---
app = Flask(__name__)
CORS(app)

# --- Connessione MongoDB ---
mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client["nightscout"]
entries_collection = mongo_db.entries

# --- Invio messaggi Telegram ---
def send_telegram_message(title, message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_IDS:
        print("[⚠️] Telegram: Token o Chat ID mancanti.")
        return

    for chat_id in TELEGRAM_CHAT_IDS:
        chat_id = chat_id.strip()
        if not chat_id:
            continue
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": chat_id, "text": f"{title}\n{message}"}
            res = requests.post(url, json=payload)
            print(f"[TELEGRAM] → {chat_id}: {res.status_code} - {res.text}")
        except Exception as e:
            print(f"[❌] Errore Telegram per {chat_id}: {e}")

# --- Scrittura Mongo ---
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
        print(f"[❌] Errore scrittura Mongo: {e}")

# --- Lettura e invio ---
def invia_a_mongo():
    try:
        print("[INFO] Avvio lettura da Dexcom...")
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if not reading:
            print("[⚠️] Nessuna lettura disponibile.")
            return

        valore = float(reading.value)
        timestamp = reading.time
        trend = reading.trend_arrow or "Flat"

        print(f"[DEXCOM] Valore: {valore}, Trend: {trend}, Timestamp: {timestamp}")
        scrivi_glicemia_su_mongo(valore, timestamp, trend)
        send_telegram_message("📊 Nuovo valore glicemico", f"{valore} mg/dL\nTrend: {trend}")

    except Exception as e:
        print(f"[❌] Errore Dexcom: {e}")
    finally:
        Timer(300, invia_a_mongo).start()

# --- Endpoint Dexcom diretto ---
@app.route("/glicemia", methods=["GET"])
def ottieni_glicemia():
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if reading:
            return jsonify({
                "glicemia": float(reading.value),
                "trend": reading.trend_description
            }), 200
        else:
            return jsonify({"errore": "Nessuna lettura disponibile"}), 404
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

@app.after_request
def after_request(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return response

# --- Avvio del sistema ---
send_telegram_message("🟢 Server avviato", "Monitoraggio glicemia attivo.")
invia_a_mongo()
app.run(host="0.0.0.0", port=5001)