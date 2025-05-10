from flask import Flask, jsonify, request
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
import os
import requests
from threading import Timer
from datetime import datetime
import json

# Carica variabili ambiente
load_dotenv()
USERNAME = os.getenv("DEXCOM_USERNAME")
PASSWORD = os.getenv("DEXCOM_PASSWORD")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
NIGHTSCOUT_URL = os.getenv("NIGHTSCOUT_URL")
NIGHTSCOUT_API_SECRET = os.getenv("NIGHTSCOUT_API_SECRET")

app = Flask(__name__)
CORS(app)

# Headers per Supabase
headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

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

# NIGHTSCOUT - invio ogni 5 minuti
def invia_a_nightscout():
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if not reading:
            return

        valore = float(reading.value)
        timestamp_iso = reading.time.strftime("%Y-%m-%dT%H:%M:%S")
        trend = reading.trend_arrow or "Flat"

        payload = [{
            "type": "sgv",
            "sgv": valore,
            "dateString": timestamp_iso,
            "direction": trend,
            "device": "dexcom-server"
        }]

        headers_nightscout = {
            "API-SECRET": NIGHTSCOUT_API_SECRET,
            "Content-Type": "application/json"
        }

        res = requests.post(f"{NIGHTSCOUT_URL}/api/v1/entries", headers=headers_nightscout, data=json.dumps(payload))
        print(f"[NS] {timestamp_iso} - {valore} mg/dL - Status: {res.status_code}")

    except Exception as e:
        print(f"Errore invio Nightscout: {e}")
    finally:
        Timer(300, invia_a_nightscout).start()  # Ripeti ogni 5 minuti

# Avvio server
if __name__ == "__main__":
    invia_a_nightscout()
    app.run(host="0.0.0.0", port=5001)