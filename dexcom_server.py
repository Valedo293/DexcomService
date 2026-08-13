from flask import Flask, jsonify, request
from dexcom_g7 import get_g7_reading
from dotenv import load_dotenv
from flask_cors import CORS
import requests
from datetime import datetime

# Carica le variabili dal file .env
load_dotenv()

app = Flask(__name__)
CORS(app)

# Endpoint per glicemia attuale
@app.route("/glicemia")
def glicemia():
    try:
        reading = get_g7_reading()
        if reading is None:
            return jsonify({"errore": "Nessuna lettura G7 disponibile"}), 404

        return jsonify({
            "glicemia": reading.value,
            "trend": reading.trend_description,
            "timestamp": reading.time.strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

# Funzione per inviare i ping al backend e al Google Sheet
def invia_ping(distanza_minuti):
    try:
        reading = get_g7_reading()
        if reading is None:
            return jsonify({"errore": "Nessuna lettura G7 disponibile"}), 404

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
            return jsonify({"messaggio": f"✅ Ping t+{distanza_minuti} min salvato."})
        else:
            return jsonify({"errore": f"Errore Google Sheet: {res.text}"}), 500

    except Exception as e:
        return jsonify({"errore": str(e)}), 500

# Endpoint per i ping programmati: 10, 20, 45 minuti
@app.route("/ping", methods=["GET"])
def ping():
    try:
        # Otteniamo il tempo da un parametro di query (in minuti)
        distanza_minuti = int(request.args.get("t", 0))

        if distanza_minuti not in [10, 20, 45]:
            raise ValueError("Parametro 't' non valido. Usa t=10, 20, 45.")

        # Risveglio prima del ping
        risveglio = distanza_minuti - 2
        invia_ping(risveglio)  # Ping di risveglio

        # Invio del ping programmato
        invia_ping(distanza_minuti)

        return jsonify({"messaggio": f"✅ Ping t+{distanza_minuti} min e risveglio t+{risveglio} min eseguiti."})

    except Exception as e:
        return jsonify({"errore": str(e)}), 500

# Avvio server
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
