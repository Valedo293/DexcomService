from flask import Flask, jsonify, request
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
import os
import requests
from datetime import datetime

# Carica le variabili dal file .env
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

# Endpoint per cron job: salva ping t+60, 90 o 180
@app.route("/ping", methods=["GET"])
def ping_cron():
    try:
        distanza_minuti = int(request.args.get("t", 0))

        if distanza_minuti not in [60, 90, 180]:
            raise ValueError("Parametro 't' non valido. Usa t=60, 90 o 180.")

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
            return jsonify({"messaggio": f"✅ Ping t+{distanza_minuti} min salvato."})
        else:
            return jsonify({"errore": f"Errore Google Sheet: {res.text}"}), 500

    except Exception as e:
        return jsonify({"errore": str(e)}), 500

# Endpoint warmup: sveglia Render ma non salva nulla
@app.route("/ping-warmup", methods=["GET"])
def ping_warmup():
    try:
        distanza_minuti = int(request.args.get("t", 0))

        if distanza_minuti not in [60, 90, 180]:
            raise ValueError("Parametro 't' non valido. Usa t=60, 90 o 180.")

        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()

        print(f"✅ Warmup t+{distanza_minuti}: {reading.value} mg/dl - {reading.trend_description}")
        return jsonify({"messaggio": f"✅ Warmup t+{distanza_minuti} eseguito."})

    except Exception as e:
        print(f"❌ Errore warmup t+{distanza_minuti}:", str(e))
        return jsonify({"errore": str(e)}), 500

# Avvio server
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)