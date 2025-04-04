from flask import Flask, jsonify, request
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import os
import requests
from datetime import datetime, timedelta

# Carica variabili ambiente
load_dotenv()
USERNAME = os.getenv("DEXCOM_USERNAME")
PASSWORD = os.getenv("DEXCOM_PASSWORD")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

app = Flask(__name__)
CORS(app)

scheduler = BackgroundScheduler()
scheduler.start()

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

def aggiorna_valore_tempo(id_pasto, campo, valore):
    try:
        url = f"{SUPABASE_URL}/rest/v1/analisi_dati?id=eq.{id_pasto}"
        payload = {campo: valore}
        res = requests.patch(url, headers=headers, json=payload)

        if res.status_code in [200, 204]:
            print(f"✅ {campo} aggiornato con successo.")
        else:
            print(f"❌ Errore aggiornamento {campo}: {res.text}")
    except Exception as e:
        print(f"❌ Errore durante la chiamata PATCH per {campo}:", str(e))

def invia_ping(id_pasto, distanza_minuti, campo):
    try:
        print(f"⏱️ Esecuzione ping t+{distanza_minuti} min per {campo}")
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if reading is not None:
            aggiorna_valore_tempo(id_pasto, campo, reading.value)
        else:
            print(f"⚠ Nessuna lettura disponibile per il ping {campo}")
    except Exception as e:
        print(f"❌ Errore ping t+{distanza_minuti} ({campo}):", str(e))

@app.route("/pianifica-ping", methods=["POST"])
def pianifica_ping():
    try:
        dati = request.get_json()
        id_pasto = dati.get("id")
        if not id_pasto:
            return jsonify({"errore": "ID del pasto mancante"}), 400

        now = datetime.now()
        ping_schedule = [
            (60, "t1"),
            (120, "t2"),
            (180, "t3"),
        ]

        for minuti, campo in ping_schedule:
            run_time = now + timedelta(minutes=minuti)
            scheduler.add_job(
                invia_ping,
                "date",
                run_date=run_time,
                args=[id_pasto, minuti, campo],
                id=f"ping_{id_pasto}_{campo}",
                replace_existing=True
            )

        return jsonify({"messaggio": "✅ Ping programmati per t1, t2, t3"})
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

@app.route("/glicemia", methods=["GET"])
def glicemia():
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if reading is None:
            return jsonify({"errore": "Nessuna lettura disponibile da Dexcom"}), 404
        return jsonify({
            "glicemia": reading.value,
            "trend": reading.trend_description,
            "timestamp": reading.time.strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        print("❌ Errore nella glicemia:", str(e))
        return jsonify({"errore": str(e)}), 500

@app.route("/jobs", methods=["GET"])
def lista_job_schedulati():
    try:
        jobs = scheduler.get_jobs()
        elenco = []
        for job in jobs:
            elenco.append({
                "id": job.id,
                "name": job.name,
                "run_time": job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.next_run_time else None
            })
        return jsonify(elenco)
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)