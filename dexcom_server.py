from flask import Flask, jsonify
from pydexcom import Dexcom
from datetime import datetime

app = Flask(__name__)

# Inserisci qui le credenziali dell'account Dexcom principale (quello di Emanuele)
USERNAME = "emamaceri"
PASSWORD = "Emanuele.08"

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
    app.run(port=5001)