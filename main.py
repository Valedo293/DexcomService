from flask import Flask, jsonify, request
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime, timedelta
from threading import Timer
import os

# ================
# Config & helpers
# ================
load_dotenv()

USERNAME   = os.getenv("DEXCOM_USERNAME")
PASSWORD   = os.getenv("DEXCOM_PASSWORD")
MONGO_URI  = os.getenv("MONGO_URI")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client["nightscout"]
entries_collection = mongo_db.entries

# Dexcom → codice numerico "trend" (Nightscout style)
ARROW_TO_TREND = {
    "DoubleDown": 1,    # ↓↓
    "SingleDown": 2,    # ↓
    "FortyFiveDown": 3, # ↘
    "Flat": 4,          # →
    "FortyFiveUp": 5,   # ↗
    "SingleUp": 6,      # ↑
    "DoubleUp": 7       # ↑↑
}

def scrivi_glicemia_su_mongo(valore, timestamp, trend_code: int | None):
    try:
        entry = {
            "device": "dexcom",
            "type": "sgv",
            "sgv": float(valore),
            # 👇 qui rimane come lo avevi: locale, non forzato a UTC
            "dateString": timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            "date": int(timestamp.timestamp() * 1000),
        }
        if trend_code is not None:
            entry["trend"] = int(trend_code)

        result = entries_collection.insert_one(entry)
        print(f"[MONGO] scritto: sgv={valore}, trend={trend_code}, id={result.inserted_id}")
    except Exception as e:
        print(f"❌ Errore scrittura Mongo: {e}")

def leggi_da_dexcom_e_salva():
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()

        if not reading:
            print("⚠️ Nessuna lettura disponibile da Dexcom")
        else:
            valore = float(reading.value)
            ts = reading.time
            trend_name = getattr(reading, "trend_arrow", None) or getattr(reading, "trend", None)
            trend_code = ARROW_TO_TREND.get(trend_name, None)

            scrivi_glicemia_su_mongo(valore, ts, trend_code)

    except Exception as e:
        print(f"❌ Errore lettura Dexcom: {e}")
    finally:
        Timer(300, leggi_da_dexcom_e_salva).start()  # ogni 5 minuti

@app.after_request
def after_request(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return response

@app.route("/glicemia", methods=["GET"])
def ottieni_glicemia():
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if not reading:
            return jsonify({"errore": "Nessuna lettura disponibile"}), 404

        trend_name = getattr(reading, "trend_arrow", None) or getattr(reading, "trend", None)
        trend_code = ARROW_TO_TREND.get(trend_name, None)

        return jsonify({
            "glicemia": float(reading.value),
            "trendName": trend_name,
            "trend": trend_code,
            "timestamp": reading.time.strftime("%Y-%m-%dT%H:%M:%S")
        })
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

@app.route("/glicemie-oggi", methods=["GET"])
def glicemie_oggi():
    try:
        data_param = request.args.get("data")
        giorno = datetime.strptime(data_param, "%Y-%m-%d").date() if data_param else datetime.now().date()

        inizio = datetime.combine(giorno, datetime.min.time())
        fine = datetime.combine(giorno, datetime.max.time())

        ts_start = int(inizio.timestamp() * 1000)
        ts_end   = int(fine.timestamp() * 1000)

        docs = list(
            entries_collection.find({
                "date": {"$gte": ts_start, "$lte": ts_end},
                "type": "sgv"
            }).sort("date", 1)
        )

        risultati = []
        for d in docs:
            risultati.append({
                "_id": str(d.get("_id")),
                "device": d.get("device", "dexcom"),
                "type": d.get("type", "sgv"),
                "sgv": d.get("sgv"),
                "date": d.get("date"),
                "dateString": d.get("dateString"),
                "trend": d.get("trend")
            })

        return jsonify(risultati)
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

if __name__ == "__main__":
    leggi_da_dexcom_e_salva()
    app.run(host="0.0.0.0", port=5001)
