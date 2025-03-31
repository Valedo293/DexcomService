from flask import Flask, jsonify
from pydexcom import Dexcom
from datetime import datetime
from flask_cors import CORS  # Importa CORS
from dotenv import load_dotenv
import os

# Carica le variabili d'ambiente dal file .env
load_dotenv()

app = Flask(__name__)

# Abilita CORS su tutte le route
CORS(app)

# Recupera le credenziali dell'account Dexcom dalle variabili d'ambiente
USERNAME = os.getenv("DEXCOM_USERNAME")
PASSWORD = os.getenv("DEXCOM_PASSWORD")

@app.route("/glicemia")
def glicemia():
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()

        print("DEBUG - Glicemia:", reading.value)
        print("DEBUG - Trend:", reading.trend_description)
        print("DEBUG - Timestamp:", reading.time)

        return jsonify({
            "glicemia": reading.value,
            "trend": reading.trend_description,
            "timestamp": reading.time.strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001)