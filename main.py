from flask import Flask, jsonify, request
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
import os
import requests
from threading import Timer
from datetime import datetime, timedelta
from pymongo import MongoClient
import subprocess  # <-- import subprocess per avviare il monitor

# --- Carica variabili ambiente ---
load_dotenv()
USERNAME         = os.getenv("DEXCOM_USERNAME")
PASSWORD         = os.getenv("DEXCOM_PASSWORD")
SUPABASE_URL     = os.getenv("SUPABASE_URL")
SUPABASE_KEY     = os.getenv("SUPABASE_KEY")
MONGO_URI        = os.getenv("MONGO_URI")

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

# Avvia il monitor glicemia in parallelo
try:
    subprocess.Popen(["python3", "MonitorGlicemia.py"])
    print("[STARTUP] MonitorGlicemia.py avviato correttamente.")
except Exception as e:
    print(f"[ERROR] Non sono riuscito ad avviare MonitorGlicemia.py: {e}")

invia_a_mongo()
app.run(host="0.0.0.0", port=5001)