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
MONGO_URI       = os.getenv("MONGO_URI")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- Flask App ---
app = Flask(__name__)
CORS(app)

# --- Connessione a MongoDB ---
mongo_client       = MongoClient(MONGO_URI)
mongo_db           = mongo_client["nightscout"]
entries_collection = mongo_db.entries

# --- Telegram ---
def send_telegram(title, message):
    try:
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": f"{title.upper()}\n{message}"}
            r = requests.post(url, json=payload)
            print(f"[Telegram] Status: {r.status_code}")
    except Exception as e:
        print(f"[Telegram ERROR] {e}")

# --- Scrittura su MongoDB ---
def write_glucose(value, timestamp, direction):
    try:
        entry = {
            "type": "sgv",
            "sgv": value,
            "dateString": timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            "date": int(timestamp.timestamp() * 1000),
            "direction": direction,
            "device": "dexcom-server"
        }
        result = entries_collection.insert_one(entry)
        print(f"[Mongo] Scritta glicemia {value} - ID: {result.inserted_id}")
    except Exception as e:
        print(f"[Mongo ERROR] {e}")

# --- Logica valutazione glicemia ---
cronologia = []
alert_attivo = None

def valuta_glicemia(valore, trend, timestamp):
    global cronologia, alert_attivo

    cronologia.append({"valore": valore, "trend": trend, "timestamp": timestamp})
    if len(cronologia) > 10:
        cronologia.pop(0)

    if alert_attivo and valore >= 78 and trend in ["→", "↑", "↗", "↑↑"]:
        alert_attivo = None
        print("✅ Alert disattivato")

    # Prova 1: 2 valori stabili tra 150 e 80
    if len(cronologia) >= 2:
        ultimi = cronologia[-2:]
        if all(80 <= x["valore"] <= 150 and x["trend"] == "→" for x in ultimi):
            if alert_attivo != "prova1":
                send_telegram("TEST PROVA 1", f"Glicemie stabili: {ultimi[0]['valore']} → {ultimi[1]['valore']}")
                alert_attivo = "prova1"

    # Prova 2: 3 valori stabili ma in discesa
    if len(cronologia) >= 3:
        ultimi = cronologia[-3:]
        if all(x["trend"] == "→" for x in ultimi) and ultimi[0]["valore"] > ultimi[1]["valore"] > ultimi[2]["valore"]:
            if alert_attivo != "prova2":
                send_telegram("TEST PROVA 2", f"Discesa stabile: {ultimi[0]['valore']} → {ultimi[2]['valore']}")
                alert_attivo = "prova2"

    # Prova 3: 100-70 con trend ↓
    if 70 <= valore <= 100 and trend == "↓":
        if alert_attivo != "prova3":
            send_telegram("TEST PROVA 3", f"Glicemia {valore} in discesa ↓")
            alert_attivo = "prova3"

    # Prova 4: 70-100 con trend ↑
    if 70 <= valore <= 100 and trend == "↑":
        if alert_attivo != "prova4":
            send_telegram("TEST PROVA 4", f"Glicemia {valore} in salita ↑")
            alert_attivo = "prova4"

@app.route("/glicemie-oggi", methods=["GET"])
def glicemie_oggi():
    try:
        oggi = datetime.utcnow().date()
        inizio = datetime.combine(oggi, datetime.min.time())
        fine   = datetime.combine(oggi, datetime.max.time())
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

        write_glucose(valore, timestamp, trend)
        valuta_glicemia(valore, trend, timestamp)

    except Exception as e:
        print(f"[Dexcom ERROR] {e}")
    finally:
        Timer(300, invia_a_mongo).start()

# --- Avvio automatico ---
invia_a_mongo()

# --- Avvio server ---
app.run(host="0.0.0.0", port=5001)