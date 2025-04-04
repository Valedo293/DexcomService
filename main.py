from flask import Flask, jsonify, request
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
import os
import requests
from datetime import datetime, timedelta
import pytz

# Carica variabili ambiente
load_dotenv()
USERNAME = os.getenv("DEXCOM_USERNAME")
PASSWORD = os.getenv("DEXCOM_PASSWORD")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

app = Flask(__name__)
CORS(app)

# Configura lo scheduler
scheduler = BackgroundScheduler(timezone="Europe/Rome")
scheduler.start()

# Headers Supabase
headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# PATCH su Supabase con log completo
def aggiorna_valore_tempo(id_pasto, campo, valore):
    try:
        url = f"{SUPABASE_URL}/rest/v1/analisi_dati?id=eq.{id_pasto}"
        payload = {campo: valore}
        print("🚀 [PATCH Supabase] INIZIO")
        print(f"🔗 URL: {url}")
        print(f"📦 Payload: {payload}")
        print(f"🧾 Headers: {headers}")

        res = requests.patch(url, headers=headers, json=payload)

        print(f"📬 Status Code: {res.status_code}")
        print(f"📬 Risposta: {res.text}")

        if res.status_code in [200, 204]:
            print(f"✅ Supabase aggiornato con successo per {campo}")
        else:
            print(f"❌ Errore aggiornamento {campo}: {res.text}")
    except Exception as e:
        print(f"❌ Errore PATCH Supabase per {campo}: {str(e)}")

def invia_ping(id_pasto, distanza_minuti, campo):
    print(f"🔍 Esecuzione invia_ping per {campo}, id_pasto={id_pasto}")
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()

        if reading is None:
            print(f"⚠ Nessuna lettura disponibile da Dexcom per {campo}")
            return

        valore = float(reading.value)
        print(f"📈 Glicemia letta: {valore}")
        aggiorna_valore_tempo(id_pasto, campo, valore)

    except requests.exceptions.RequestException as e:
        print(f"❌ Errore rete durante il ping: {str(e)}")
    except Exception as e:
        print(f"❌ Errore generale ping {campo}: {str(e)}")

# Listener dei job
def job_listener(event):
    if event.exception:
        print(f"❌ Job {event.job_id} fallito: {event.exception}")
    else:
        print(f"✅ Job {event.job_id} eseguito correttamente!")

scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

# Endpoint pianificazione ping
@app.route("/pianifica-ping", methods=["POST"])
def pianifica_ping():
    try:
        dati = request.get_json()
        id_pasto = dati.get("id")
        if not id_pasto:
            return jsonify({"errore": "ID del pasto mancante"}), 400

        print(f"📅 Inizio pianificazione ping per pasto: {id_pasto}")
        now = datetime.now(pytz.timezone("Europe/Rome"))

        ping_schedule = [
            (1, "t1"),
            (3, "t2"),
            (5, "t3"),
        ]

        for minuti, campo in ping_schedule:
            run_time = now + timedelta(minutes=minuti)
            print(f"⏰ Scheduling job {campo} alle {run_time}")
            try:
                job = scheduler.add_job(
                    invia_ping,
                    "date",
                    run_date=run_time,
                    args=[id_pasto, minuti, campo],
                    id=f"ping_{id_pasto}_{campo}",
                    replace_existing=True
                )
                print(f"✅ Job {campo} schedulato: {job.id} | Run: {run_time}")
            except Exception as e:
                print(f"❌ Errore creazione job {campo}: {str(e)}")

        return jsonify({"messaggio": "✅ Ping programmati per t1, t2, t3"})
    except Exception as e:
        print(f"❌ Errore endpoint /pianifica-ping: {str(e)}")
        return jsonify({"errore": str(e)}), 500

@app.route("/glicemia", methods=["GET"])
def glicemia():
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()

        if reading is None:
            return jsonify({"errore": "Nessuna lettura disponibile da Dexcom"}), 404

        print(f"📡 Glicemia: {reading.value}, trend={reading.trend_description}, timestamp={reading.time}")
        return jsonify({
            "glicemia": reading.value,
            "trend": reading.trend_description,
            "timestamp": reading.time.strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        print(f"❌ Errore /glicemia: {str(e)}")
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
            print(f"🔄 Job schedulato: {job.id} | Next run: {job.next_run_time}")
        return jsonify(elenco)
    except Exception as e:
        print(f"❌ Errore /jobs: {str(e)}")
        return jsonify({"errore": str(e)}), 500

if __name__ == "__main__":
    print("🚀 Server Flask avviato")
    app.run(host="0.0.0.0", port=5001)