from flask import Flask, jsonify, request
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
import os
import requests
from threading import Timer
from datetime import datetime

# Carica variabili ambiente
load_dotenv()
USERNAME = os.getenv("DEXCOM_USERNAME")
PASSWORD = os.getenv("DEXCOM_PASSWORD")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

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
        print(f"🚀 PATCH Supabase per {campo}, id_pasto={id_pasto}, valore={valore}")
        url = f"{SUPABASE_URL}/rest/v1/analisi_dati?id=eq.{id_pasto}"
        payload = {campo: valore}
        res = requests.patch(url, headers=headers, json=payload)
        print(f"🔄 Status: {res.status_code}, Response: {res.text}")
    except Exception as e:
        print(f"❌ PATCH error: {e}")

def invia_ping(id_pasto, campo):
    try:
        print(f"⏱️ Eseguo ping per {campo}, id_pasto={id_pasto}")
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if reading:
            valore = float(reading.value)
            print(f"📈 Glicemia letta: {valore}")
            aggiorna_valore_tempo(id_pasto, campo, valore)
        else:
            print("⚠️ Nessuna lettura disponibile da Dexcom")
    except Exception as e:
        print(f"❌ Errore durante ping {campo}: {e}")

@app.route("/pianifica-ping", methods=["POST"])
def pianifica_ping():
    try:
        dati = request.get_json()
        id_pasto = dati.get("id")
        if not id_pasto:
            return jsonify({"errore": "ID del pasto mancante"}), 400

        print(f"⏰ Programmazione ping per pasto {id_pasto}...")

        # Ping: t1 (60 min), t2 (90 min), t3 (180 min)
        Timer(60 * 60, invia_ping, args=[id_pasto, "t1"]).start()
        Timer(90 * 60, invia_ping, args=[id_pasto, "t2"]).start()
        Timer(180 * 60, invia_ping, args=[id_pasto, "t3"]).start()

        return jsonify({"messaggio": "Ping pianificati (via Timer)"})
    except Exception as e:
        print(f"❌ Errore in /pianifica-ping: {e}")
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
                "timestamp": reading.datetime.strftime("%Y-%m-%d %H:%M:%S")
            })
        else:
            return jsonify({"errore": "Nessuna lettura disponibile"}), 404
    except Exception as e:
        print(f"❌ Errore in /glicemia: {e}")
        return jsonify({"errore": str(e)}), 500