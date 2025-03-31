from flask import Flask, jsonify
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
import os

# Carica le variabili d'ambiente dal file .env
load_dotenv()

# Recupera le credenziali dal file .env
USERNAME = os.getenv("DEXCOM_USERNAME")
PASSWORD = os.getenv("DEXCOM_PASSWORD")

# Stampa di debug per verificare che siano caricate correttamente
print("DEBUG - USERNAME:", USERNAME)
print("DEBUG - PASSWORD:", PASSWORD)

# Crea l'app Flask
app = Flask(__name__)
CORS(app)

@app.route("/glicemia")
def glicemia():
    try:
        if not USERNAME or not PASSWORD:
            raise ValueError("Username o password mancanti nelle variabili d'ambiente")

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
        print("ERRORE:", str(e))
        return jsonify({"errore": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)