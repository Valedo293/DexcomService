from flask import Flask, jsonify, request
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
import os
import requests
from datetime import datetime

# Carica variabili ambiente
load_dotenv()
USERNAME = os.getenv("DEXCOM_USERNAME")
PASSWORD = os.getenv("DEXCOM_PASSWORD")

app = Flask(__name__)
CORS(app)

def invia_ping(distanza_minuti):
    try:
        print(f"⏱️ Esecuzione ping t+{distanza_minuti} min")

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
            print(f"✅ Ping t+{distanza_minuti} salvato.")
        else:
            print(f"❌ Errore Google Sheet t+{distanza_minuti}: {res.text}")

    except Exception as e:
        print(f"❌ Errore ping t+{distanza_minuti}:", str(e))

@app.route("/ping", methods=["GET"])
def ping_cron():
    try:
        distanza_minuti = int(request.args.get("t", 0))

        if distanza_minuti not in [60, 90, 180]:
            raise ValueError("Parametro 't' non valido. Usa t=60, 90 o 180.")

        invia_ping(distanza_minuti)
        return jsonify({"messaggio": f"✅ Ping t+{distanza_minuti} eseguito."})

    except Exception as e:
        return jsonify({"errore": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)