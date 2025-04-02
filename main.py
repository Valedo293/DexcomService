from flask import Flask, jsonify, request
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
import os
import requests
from datetime import datetime
import threading
import time

# Carica variabili ambiente
load_dotenv()
USERNAME = os.getenv("DEXCOM_USERNAME")
PASSWORD = os.getenv("DEXCOM_PASSWORD")

app = Flask(__name__)
CORS(app)

def invia_ping(distanza_minuti, warmup=False):
    try:
        tipo_ping = "WARMUP" if warmup else "PING REALE"
        print(f"⏱️ Esecuzione {tipo_ping} t+{distanza_minuti} min")

        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()

        if warmup:
            print(f"✅ Warmup t+{distanza_minuti}: {reading.value} mg/dl - {reading.trend_description}")
            return

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
            print(f"✅ Ping t+{distanza_minuti} salvato.")
        else:
            print(f"❌ Errore Google Sheet t+{distanza_minuti}: {res.text}")

    except Exception as e:
        print(f"❌ Errore {tipo_ping} t+{distanza_minuti}:", str(e))

def programma_ping(distanza_minuti):
    # Ping warmup 5 minuti prima
    warmup_time = max(distanza_minuti - 5, 0)
    threading.Timer(warmup_time * 60, invia_ping, args=(distanza_minuti, True)).start()

    # Ping vero
    threading.Timer(distanza_minuti * 60, invia_ping, args=(distanza_minuti, False)).start()

@app.route("/programma-ping", methods=["GET"])
def programma_ping_endpoint():
    try:
        minuti = [10, 20, 45]
        for m in minuti:
            programma_ping(m)

        return jsonify({"messaggio": "✅ Ping programmati: 10, 20, 45 minuti con warmup 5 minuti prima."})
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)