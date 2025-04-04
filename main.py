from flask import Flask, jsonify, request
from pydexcom import Dexcom
from dotenv import load_dotenv
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
import os
import requests
from datetime import datetime, timedelta
import pytz  # Import per gestire i fusi orari

# Carica variabili ambiente
load_dotenv()
USERNAME = os.getenv("DEXCOM_USERNAME")
PASSWORD = os.getenv("DEXCOM_PASSWORD")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

app = Flask(__name__)
CORS(app)

# Configura lo scheduler per il fuso orario locale
scheduler = BackgroundScheduler(timezone="Europe/Rome")
scheduler.start()

# Headers per comunicare con Supabase
headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

def aggiorna_valore_tempo(id_pasto, campo, valore):
    try:
        print(f"🚀 Aggiornamento valore per {campo}, id_pasto={id_pasto}, valore={valore}")
        url = f"{SUPABASE_URL}/rest/v1/analisi_dati?id=eq.{id_pasto}"
        payload = {campo: valore}
        res = requests.patch(url, headers=headers, json=payload)

        print(f"🔄 Risposta Supabase: Status Code {res.status_code}, Testo: {res.text}")

        if res.status_code in [200, 204]:
            print(f"✅ {campo} aggiornato con valore {valore}")
        else:
            print(f"❌ Errore aggiornamento {campo}: {res.text}")
    except Exception as e:
        print(f"❌ Errore PATCH Supabase per {campo}: {str(e)}")

def invia_ping(id_pasto, distanza_minuti, campo):
    print(f"🔍 Debug: Esecuzione invia_ping per {campo}, id_pasto={id_pasto}")  # Log di debug dettagliato
    try:
        print(f"⏱️ Esecuzione ping t+{distanza_minuti} min per {campo}, id_pasto={id_pasto}")
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()

        if reading is None:
            print(f"⚠ Nessuna lettura disponibile da Dexcom per {campo}")
            return

        # Estrarre solo il valore glicemia
        valore = float(reading.value)  # Usa solo il valore numerico della glicemia
        print(f"📈 Aggiornamento glicemia: {valore}")
        aggiorna_valore_tempo(id_pasto, campo, valore)
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Errore di rete durante il ping: {str(e)}")
    except Exception as e:
        print(f"❌ Errore durante il ping t+{distanza_minuti} ({campo}), id_pasto={id_pasto}: {str(e)}")

# Event listener per monitorare l'esecuzione dei job
def job_listener(event):
    if event.exception:
        print(f"❌ Il job {event.job_id} ha fallito: {event.exception}")
    else:
        print(f"✅ Il job {event.job_id} è stato eseguito correttamente!")

scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

@app.route("/pianifica-ping", methods=["POST"])
def pianifica_ping():
    try:
        dati = request.get_json()
        id_pasto = dati.get("id")
        if not id_pasto:
            print("❌ ID del pasto mancante!")
            return jsonify({"errore": "ID del pasto mancante"}), 400

        print(f"📅 Pianificazione ping per il pasto {id_pasto}")
        now = datetime.now(pytz.timezone("Europe/Rome"))  # Orario locale Europe/Rome
        ping_schedule = [
            (10, "t1"),
            (20, "t2"),
            (30, "t3"),
        ]

        for minuti, campo in ping_schedule:
            run_time = now + timedelta(minutes=minuti)  # Calcolo del run_time locale
            print(f"🕒 Scheduling ping per {campo} alle {run_time}")

            try:
                job = scheduler.add_job(
                    invia_ping,
                    "date",
                    run_date=run_time,
                    args=[id_pasto, minuti, campo],
                    id=f"ping_{id_pasto}_{campo}",
                    replace_existing=True
                )
                print(f"✅ Job aggiunto per {campo}: {job.id} alle {run_time}")
            except Exception as e:
                print(f"❌ Errore nell'aggiungere il job per {campo}: {str(e)}")

        print(f"✅ Ping programmati per il pasto {id_pasto}")
        return jsonify({"messaggio": "✅ Ping programmati per t1, t2, t3"})
    except Exception as e:
        print(f"❌ Errore nella pianificazione dei job: {str(e)}")
        return jsonify({"errore": str(e)}), 500

@app.route("/glicemia", methods=["GET"])
def glicemia():
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        print(f"📡 Risposta glicemia: {reading.value}, trend={reading.trend_description}, timestamp={reading.time}")  # Log aggiuntivo

        if reading is None:
            print("❌ Nessuna lettura disponibile da Dexcom")
            return jsonify({"errore": "Nessuna lettura disponibile da Dexcom"}), 404
        return jsonify({
            "glicemia": reading.value,
            "trend": reading.trend_description,
            "timestamp": reading.time.strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        print(f"❌ Errore nella glicemia: {str(e)}")
        return jsonify({"errore": str(e)}), 500

@app.route("/jobs", methods=["GET"])
def lista_job_schedulati():
    try:
        jobs = scheduler.get_jobs()
        elenco = []
        for job in jobs:
            print(f"🔄 Job schedulato: {job.id} alle {job.next_run_time}")  # Log dei job programmati
            elenco.append({
                "id": job.id,
                "name": job.name,
                "run_time": job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.next_run_time else None
            })
        return jsonify(elenco)
    except Exception as e:
        print(f"❌ Errore nel recupero dei job schedulati: {str(e)}")
        return jsonify({"errore": str(e)}), 500

if __name__ == "__main__":
    print("🚀 Server avviato!")
    app.run(host="0.0.0.0", port=5001)