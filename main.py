from flask import Flask, jsonify, request
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
import os
import threading
import time
import requests
from datetime import datetime

# Carica variabili dal file .env
load_dotenv()

USERNAME = os.getenv("DEXCOM_USERNAME")
PASSWORD = os.getenv("DEXCOM_PASSWORD")

app = Flask(__name__)
CORS(app)

# Endpoint per glicemia attuale
@app.route("/glicemia")
def glicemia():
    try:
        if not USERNAME or not PASSWORD:
            raise ValueError("Username o password mancanti")

        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()

        return jsonify({
            "glicemia": reading.value,
            "trend": reading.trend_description,
            "timestamp": reading.time.strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

# Funzione per eseguire il ping differito
def esegui_ping(distanza_minuti):
    time.sleep(10)
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()

        payload = {
            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "glicemia": reading.value,
            "trend": reading.trend_description,
            "timestampDexcom": reading.time.strftime("%Y-%m-%d %H:%M:%S"),
            "distanza": distanza_minuti,
            "tipo": "monitoraggio post-prandiale"
        }

        res = requests.post(
            "https://script.google.com/macros/s/AKfycbzO4lT2z4bZL2S9sKUdnak1OHEpeuyltsPcXK3CSNgZemw1Hx4LO-41xcwmYIQdhbtZ8A/exec",
            json=payload
        )

        if res.status_code == 200:
            print(f"✅ Ping t+{distanza_minuti} min salvato.")
        else:
            print(f"❌ Errore salvataggio t+{distanza_minuti}: {res.text}")

    except Exception as e:
        print(f"❌ Errore ping t+{distanza_minuti} min:", str(e))

# Endpoint per avviare i ping
@app.route("/ping-postprandiale", methods=["POST"])
def avvia_ping():
    try:
        for minuti in [60, 90, 180]:
            threading.Thread(target=esegui_ping, args=(minuti,)).start()

        return jsonify({"messaggio": "✅ Ping post-prandiali programmati."})
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

# Avvio server
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)