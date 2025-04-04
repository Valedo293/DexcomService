from flask import Flask, jsonify, request
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from datetime import datetime, timedelta
import pytz
import os
import requests

# Carica variabili ambiente
load_dotenv()
USERNAME = os.getenv("DEXCOM_USERNAME")
PASSWORD = os.getenv("DEXCOM_PASSWORD")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

app = Flask(__name__)
CORS(app)

# Scheduler con fuso orario italiano
scheduler = BackgroundScheduler(timezone="Europe/Rome")
scheduler.start()

# Header per Supabase
headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# Log dei job
def job_listener(event):
    if event.exception:
        print(f"❌ Il job {event.job_id} ha fallito: {event.exception}")
    else:
        print(f"✅ Il job {event.job_id} è stato eseguito correttamente!")

scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

# PATCH a Supabase
def aggiorna_valore_tempo(id_pasto, campo, valore):
    try:
        print(f"🚀 Aggiornamento valore per {campo}, id_pasto={id_pasto}, valore={valore}")
        url = f"{SUPABASE_URL}/rest/v1/analisi_dati?id=eq.{id_pasto}"
        payload = {campo: valore}
        res = requests.patch(url, headers=headers, json=payload)
        print(f"🔄 Risposta Supabase: {res.status_code} - {res.text}")
        if res.status_code in [200, 204]:
            print(f"✅ {campo} aggiornato con valore {valore}")
        else:
            print(f"❌ Errore aggiornamento {campo}: {res.text}")
    except Exception as e:
        print(f"❌ Errore PATCH Supabase per {campo}: {str(e)}")

# Richiesta a Dexcom
def invia_ping(id_pasto, distanza_minuti, campo):
    print(f"🔍 Esecuzione invia_ping per {campo}, id_pasto={id_pasto}")
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()

        if reading is None:
            print(f"⚠ Nessuna lettura disponibile da Dexcom per {campo}")
            return

        valore = float(reading.value)
        print(f"📈 Glicemia ricevuta: {valore}")
        aggiorna_valore_tempo(id_pasto, campo, valore)

    except requests.exceptions.RequestException as e:
        print(f"❌ Errore di rete durante il ping: {str(e)}")
    except Exception as e:
        print(f"❌ Errore durante il ping t+{distanza_minuti} ({campo}): {str(e)}")

# Pianificazione ping
@app.route("/pianifica-ping", methods=["POST"])
def pianifica_ping():
    try:
        dati = request.get_json()
        id_pasto = dati.get("id")
        if not id_pasto:
            print("❌ ID del pasto mancante!")
            return jsonify({"errore": "ID del pasto mancante"}), 400

        print(f"📅 Inizio pianificazione ping per pasto: {id_pasto}")
        now = datetime.now(pytz.timezone("Europe/Rome"))

        ping_schedule = [
            (3, "t1"),
            (6, "t2"),
            (9, "t3"),
        ]

        for minuti, campo in ping_schedule:
            run_time = now + timedelta(minutes=minuti)
            print(f"⏰ Scheduling job {campo} alle {run_time}")
            try:
                scheduler.add_job(
                    invia_ping,
                    "date",
                    run_date=run_time,
                    args=[id_pasto, minuti, campo],
                    id=f"ping_{id_pasto}_{campo}",
                    replace_existing=True
                )
                print(f"✅ Job {campo} schedulato per {run_time}")
            except Exception as e:
                print(f"❌ Errore nell’aggiungere il job per {campo}: {str(e)}")

        return jsonify({"messaggio": "✅ Ping programmati per t1, t2, t3"})
    except Exception as e:
        print(f"❌ Errore nella pianificazione dei job: {str(e)}")
        return jsonify({"errore": str(e)}), 500

# Endpoint glicemia singola
@app.route("/glicemia", methods=["GET"])
def glicemia():
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if reading is None:
            return jsonify({"errore": "Nessuna lettura disponibile"}), 404
        return jsonify({
            "glicemia": reading.value,
            "trend": reading.trend_description,
            "timestamp": reading.time.strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        print(f"❌ Errore nella glicemia: {str(e)}")
        return jsonify({"errore": str(e)}), 500

# Endpoint lista job
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

# Avvio
if __name__ == "__main__":
    print("🚀 Server Flask avviato!")
    app.run(host="0.0.0.0", port=5001)