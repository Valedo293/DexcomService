from flask import Flask, jsonify, request
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
from pymongo import MongoClient
import os, requests
from threading import Timer
from datetime import datetime, timedelta

# --- Config ---
load_dotenv()
USERNAME = os.getenv("DEXCOM_USERNAME")
PASSWORD = os.getenv("DEXCOM_PASSWORD")
MONGO_URI = os.getenv("MONGO_URI")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_IDS = os.getenv("TELEGRAM_CHAT_IDS")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# --- Mongo ---
mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client["nightscout"]
entries_collection = mongo_db.entries

# --- Flask ---
app = Flask(__name__)
CORS(app)

# --- Alert state ---
alert_cronologia = []
alert_attivo = None
intervallo_notifica = None

def trend_to_arrow(trend_raw):
    trend_map = {
        "DoubleUp": "↑↑", "SingleUp": "↑", "FortyFiveUp": "↗",
        "Flat": "→", "FortyFiveDown": "↘", "SingleDown": "↓",
        "DoubleDown": "↓↓", "NotComputable": "→", "RateOutOfRange": "→"
    }
    return trend_map.get(trend_raw, "→")

def send_push(titolo, messaggio):
    try:
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": TELEGRAM_CHAT_IDS, "text": f"{titolo.upper()}\n{messaggio}"}
            res = requests.post(url, json=payload)
            print(f"[TELEGRAM] {res.status_code}")
    except Exception as e:
        print(f"❌ Telegram: {e}")

def valuta_glicemia(valore, trend_raw, timestamp):
    global alert_cronologia, alert_attivo, intervallo_notifica
    trend = trend_to_arrow(trend_raw)
    print(f"[DEBUG] Valore ricevuto: {valore} mg/dL, Trend: {trend}, Timestamp: {timestamp}")

    alert_cronologia.append({"valore": valore, "trend": trend, "timestamp": timestamp})
    if len(alert_cronologia) > 10:
        alert_cronologia.pop(0)
    print(f"[DEBUG] Cronologia aggiornata: {alert_cronologia}")

    if alert_attivo:
        print("[DEBUG] Alert già attivo, nessuna nuova azione.")
        return

    # PROVA 1: 2 valori stabili tra 150 e 80
    if len(alert_cronologia) >= 2:
        v1, v2 = alert_cronologia[-2], alert_cronologia[-1]
        if 80 <= v1["valore"] <= 150 and 80 <= v2["valore"] <= 150 and v1["trend"] == "→" and v2["trend"] == "→":
            alert_attivo = {"tipo": "Prova 1", "azione": "Due glicemie stabili tra 150-80"}
    
    # PROVA 2: 3 valori stabili ma in diminuzione
    if len(alert_cronologia) >= 3:
        ultimi = alert_cronologia[-3:]
        if all(x["trend"] == "→" for x in ultimi) and ultimi[0]["valore"] > ultimi[1]["valore"] > ultimi[2]["valore"]:
            alert_attivo = {"tipo": "Prova 2", "azione": "Tre glicemie stabili in discesa"}

    # PROVA 3: Qualsiasi valore tra 100–70 in discesa singola
    if 70 <= valore <= 100 and trend == "↓":
        alert_attivo = {"tipo": "Prova 3", "azione": "Valore in discesa tra 70 e 100"}

    # PROVA 4: Qualsiasi valore tra 70–100 in salita singola
    if 70 <= valore <= 100 and trend == "↑":
        alert_attivo = {"tipo": "Prova 4", "azione": "Valore in salita tra 70 e 100"}

    if alert_attivo:
        print(f"[DEBUG] ALARM TRIGGERED: {alert_attivo}")
        send_push(alert_attivo["tipo"], alert_attivo["azione"])
        if intervallo_notifica:
            intervallo_notifica.cancel()
        intervallo_notifica = Timer(300, lambda: send_push(alert_attivo["tipo"], alert_attivo["azione"]))
        intervallo_notifica.start()

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
        print(f"❌ Mongo Write Error: {e}")

@app.route("/glicemia", methods=["GET"])
def ottieni_glicemia():
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if reading:
            valore = float(reading.value)
            trend = reading.trend_description
            timestamp = reading.time
            scrivi_glicemia_su_mongo(valore, timestamp, trend)
            return jsonify({"glicemia": valore, "trend": trend}), 200
        return jsonify({"errore": "Nessuna lettura"}), 404
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

@app.route("/glicemie-oggi", methods=["GET"])
def glicemie_oggi():
    try:
        giorno = datetime.utcnow().date()
        inizio = datetime.combine(giorno, datetime.min.time()) - timedelta(hours=2)
        fine = datetime.combine(giorno, datetime.max.time()) - timedelta(hours=2)
        ts_in, ts_fn = int(inizio.timestamp() * 1000), int(fine.timestamp() * 1000)

        risultati = list(entries_collection.find({"date": {"$gte": ts_in, "$lte": ts_fn}}).sort("date", 1))
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

# Lettura da Mongo ogni 5 minuti
def leggi_e_valuta():
    try:
        ultimo = entries_collection.find_one(sort=[("date", -1)])
        if not ultimo:
            print("[DEBUG] Nessun valore trovato in Mongo")
        else:
            valore = float(ultimo["sgv"])
            trend = ultimo.get("direction", "Flat")
            timestamp = datetime.now().isoformat()
            valuta_glicemia(valore, trend, timestamp)
    except Exception as e:
        print(f"❌ Errore lettura Mongo: {e}")
    finally:
        Timer(300, leggi_e_valuta).start()

leggi_e_valuta()

@app.after_request
def after_request(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response

# --- Start ---
app.run(host="0.0.0.0", port=5001)