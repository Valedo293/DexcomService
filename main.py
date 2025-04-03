from flask import Flask, jsonify, request
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
from supabase import create_client, Client
import os
import requests
from datetime import datetime, timedelta

# Carica variabili ambiente
load_dotenv()
USERNAME = os.getenv("DEXCOM_USERNAME")
PASSWORD = os.getenv("DEXCOM_PASSWORD")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
CORS(app)

scheduler = BackgroundScheduler()
scheduler.start()

# Dizionario per tenere traccia degli ID pasto da aggiornare
task_mapping = {}

def invia_ping(id_pasto, distanza_minuti):
    try:
        print(f"⏱️ Esecuzione ping t+{distanza_minuti} min per ID: {id_pasto}")
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()

        campo = f"t{[60, 120, 180].index(distanza_minuti) + 1}"
        valore = reading.value

        result = supabase.table("analisi_dati").update({campo: valore}).eq("id", id_pasto).execute()

        if result.data:
            print(f"✅ Glicemia {campo} salvata su Supabase: {valore}")
        else:
            print(f"❌ Errore salvataggio Supabase {campo}: {result}")

    except Exception as e:
        print(f"❌ Errore ping t+{distanza_minuti}:", str(e))

@app.route("/pianifica-ping", methods=["POST"])
def pianifica_ping():
    try:
        body = request.get_json()
        id_pasto = body.get("id")

        if not id_pasto:
            return jsonify({"errore": "ID pasto mancante"}), 400

        now = datetime.now()
        for minuti in [60, 120, 180]:
            run_time = now.replace(second=0, microsecond=0) + timedelta(minutes=minuti)
            scheduler.add_job(
                invia_ping,
                'date',
                run_date=run_time,
                args=[id_pasto, minuti],
                id=f"ping_{id_pasto}_{minuti}",
                replace_existing=True
            )

        return jsonify({"messaggio": "✅ Ping programmati per t+60, 120, 180 minuti."})
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

@app.route("/glicemia", methods=["GET"])
def glicemia():
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        return jsonify({
            "glicemia": reading.value,
            "trend": reading.trend_description,
            "timestamp": reading.time.strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
