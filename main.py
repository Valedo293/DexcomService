from flask import Flask, jsonify, request
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
import os
import requests
from threading import Timer
from datetime import datetime, timedelta
from pymongo import MongoClient

# Carica variabili ambiente
load_dotenv()
USERNAME        = os.getenv("DEXCOM_USERNAME")
PASSWORD        = os.getenv("DEXCOM_PASSWORD")
MONGO_URI       = os.getenv("MONGO_URI")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Flask App
app = Flask(__name__)
CORS(app)

# Connessione a MongoDB
mongo_client       = MongoClient(MONGO_URI)
mongo_db           = mongo_client["nightscout"]
entries_collection = mongo_db.entries

# Logica Alert
alert_attivo = None
cronologia = []

def trend_to_arrow(trend_raw):
    trend_map = {
        "DoubleUp": "↑↑", "SingleUp": "↑", "FortyFiveUp": "↗",
        "Flat": "→", "FortyFiveDown": "↘", "SingleDown": "↓", "DoubleDown": "↓↓"
    }
    return trend_map.get(trend_raw, "→")

def invia_notifica(titolo, messaggio):
    try:
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": f"{titolo.upper()}\n{messaggio}"}
            res = requests.post(url, json=payload)
            print(f"[TELEGRAM] {res.status_code} - {titolo}")
    except Exception as e:
        print(f"Errore Telegram: {e}")

def valuta(valori):
    global alert_attivo
    if len(valori) < 3:
        return

    v1, v2, v3 = valori[-3:]
    print(f"[DEBUG] Ultimi valori: {v1['valore']} {v2['valore']} {v3['valore']}")

    # Prova 1: 2 valori stabili tra 150 e 80
    if all(150 >= v["valore"] >= 80 and v["trend"] == "→" for v in [v2, v3]):
        invia_notifica("Prova 1", "Due glicemie stabili tra 150 e 80")

    # Prova 2: 3 valori stabili ma in diminuzione
    if all(v["trend"] == "→" for v in [v1, v2, v3]) and v1["valore"] > v2["valore"] > v3["valore"]:
        invia_notifica("Prova 2", "Tre glicemie stabili ma in calo")

    # Prova 3: valore tra 100 e 70 in discesa
    if 100 >= v3["valore"] >= 70 and v3["trend"] in ["↘", "↓"]:
        invia_notifica("Prova 3", f"Glicemia {v3['valore']} in discesa singola")

    # Prova 4: valore tra 70 e 100 in salita
    if 100 >= v3["valore"] >= 70 and v3["trend"] in ["↗", "↑"]:
        invia_notifica("Prova 4", f"Glicemia {v3['valore']} in salita singola")

@app.route("/glicemia", methods=["GET"])
def ottieni_glicemia():
    try:
        dexcom  = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if reading:
            valore = float(reading.value)
            timestamp = reading.time
            trend = reading.trend_description or "Flat"
            arrow = trend_to_arrow(reading.trend)
            cronologia.append({"valore": valore, "trend": arrow, "timestamp": timestamp})
            if len(cronologia) > 10:
                cronologia.pop(0)
            valuta(cronologia)
            return jsonify({"glicemia": valore, "trend": trend}), 200
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

@app.after_request
def after_request(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)