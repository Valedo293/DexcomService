from datetime import datetime, timedelta
from threading import Timer
from flask import Flask, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Config
MONGO_URI        = os.getenv("MONGO_URI")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# MongoDB
mongo_client       = MongoClient(MONGO_URI)
mongo_db           = mongo_client["nightscout"]
entries_collection = mongo_db.entries

# Flask App
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

alert_attivo = None

def trend_to_arrow(trend_raw):
    trend_map = {
        "DoubleUp": "↑↑", "SingleUp": "↑", "FortyFiveUp": "↗",
        "Flat": "→",
        "FortyFiveDown": "↘", "SingleDown": "↓", "DoubleDown": "↓↓",
        "NotComputable": "→", "RateOutOfRange": "→"
    }
    return trend_map.get(trend_raw, "→")

def send_telegram_alert(title, message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Dati Telegram mancanti")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": f"{title.upper()}\n{message}"}
        response = requests.post(url, json=payload)
        print(f"[TELEGRAM] {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")

def valuta_ultimi_valori():
    global alert_attivo

    now = datetime.utcnow()
    ts_start = int((now - timedelta(minutes=20)).timestamp() * 1000)
    records = list(entries_collection.find({"date": {"$gte": ts_start}}).sort("date", 1))

    if len(records) < 3:
        print("⚠️ Dati insufficienti per valutazione")
        return

    valori = [{"valore": r["sgv"], "trend": trend_to_arrow(r.get("direction", "Flat"))} for r in records[-5:]]
    print("[DEBUG] Ultimi valori:", valori)

    # Prova 1: 2 valori stabili tra 150 e 80
    if len(valori) >= 2 and all(v["trend"] == "→" and 80 <= v["valore"] <= 150 for v in valori[-2:]):
        if alert_attivo != "prova1":
            send_telegram_alert("Prova 1", "Due glicemie stabili tra 150 e 80.")
            alert_attivo = "prova1"
        return

    # Prova 2: 3 valori stabili ma in diminuzione
    if len(valori) >= 3:
        ultimi = valori[-3:]
        if all(v["trend"] == "→" for v in ultimi) and ultimi[0]["valore"] > ultimi[1]["valore"] > ultimi[2]["valore"]:
            if alert_attivo != "prova2":
                send_telegram_alert("Prova 2", "Tre glicemie stabili ma in diminuzione.")
                alert_attivo = "prova2"
            return

    # Prova 3: glicemia 70-100 in discesa singola
    if valori[-1]["valore"] >= 70 and valori[-1]["valore"] <= 100 and valori[-1]["trend"] == "↓":
        if alert_attivo != "prova3":
            send_telegram_alert("Prova 3", "Glicemia in discesa tra 70 e 100.")
            alert_attivo = "prova3"
        return

    # Prova 4: glicemia 70-100 in salita singola
    if valori[-1]["valore"] >= 70 and valori[-1]["valore"] <= 100 and valori[-1]["trend"] == "↑":
        if alert_attivo != "prova4":
            send_telegram_alert("Prova 4", "Glicemia in salita tra 70 e 100.")
            alert_attivo = "prova4"
        return

    alert_attivo = None

def avvia_monitoraggio():
    try:
        valuta_ultimi_valori()
    except Exception as e:
        print(f"[ERRORE MONITORAGGIO] {e}")
    finally:
        Timer(300, avvia_monitoraggio).start()

@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "ok", "ultima_valutazione": datetime.utcnow().isoformat()}), 200

@app.after_request
def after_request(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return response

if __name__ == "__main__":
    avvia_monitoraggio()
    app.run(host="0.0.0.0", port=5001)