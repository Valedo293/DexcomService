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
print("🚀 Caricamento variabili ambiente...")
load_dotenv()
USERNAME = os.getenv("DEXCOM_USERNAME")
PASSWORD = os.getenv("DEXCOM_PASSWORD")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

print(f"🔐 USERNAME: {USERNAME}")
print(f"🔐 PASSWORD: {'*' * len(PASSWORD) if PASSWORD else None}")
print(f"🔗 SUPABASE_URL: {SUPABASE_URL}")
print(f"🔑 SUPABASE_KEY: {'*' * len(SUPABASE_KEY) if SUPABASE_KEY else None}")

app = Flask(__name__)
CORS(app)

scheduler = BackgroundScheduler(timezone="Europe/Rome")
scheduler.start()
print("🕓 Scheduler avviato con timezone Europe/Rome")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

def aggiorna_valore_tempo(id_pasto, campo, valore):
    try:
        print(f"🚀 [PATCH] Aggiorno Supabase -> Campo: {campo}, ID pasto: {id_pasto}, Valore: {valore}")
        url = f"{SUPABASE_URL}/rest/v1/analisi_dati?id=eq.{id_pasto}"
        payload = {campo: valore}
        print(f"🔗 URL: {url}")
        print(f"📦 Payload: {payload}")
        print(f"📬 Headers: {headers}")
        res = requests.patch(url, headers=headers, json=payload)
        print(f"📨 Risposta: Status {res.status_code} - Body: {res.text}")

        if res.status_code in [200, 204]:
            print(f"✅ Supabase aggiornato correttamente per {campo}")
        else:
            print(f"❌ Errore aggiornamento Supabase: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"❌ Eccezione durante PATCH Supabase: {str(e)}")

def invia_ping(id_pasto, distanza_minuti, campo):
    print(f"🔍 [PING] Invio ping per campo {campo}, ID pasto: {id_pasto}")
    try:
        print(f"🔑 Login a Dexcom con {USERNAME}")
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()

        if reading is None:
            print(f"⚠️ Nessuna lettura disponibile da Dexcom")
            return

        valore = float(reading.value)
        trend = reading.trend_description
        timestamp = reading.time.strftime("%Y-%m-%d %H:%M:%S")

        print(f"📈 Dato ottenuto: {valore} mg/dl | Trend: {trend} | Time: {timestamp}")
        aggiorna_valore_tempo(id_pasto, campo, valore)

    except requests.exceptions.RequestException as e:
        print(f"❌ Errore di rete durante invio ping: {str(e)}")
    except Exception as e:
        print(f"❌ Errore generico nel ping t+{distanza_minuti} min ({campo}) - ID pasto: {id_pasto} | Errore: {str(e)}")

def job_listener(event):
    if event.exception:
        print(f"❌ JOB FALLITO: {event.job_id} | Errore: {event.exception}")
    else:
        print(f"✅ JOB ESEGUITO: {event.job_id}")

scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

@app.route("/pianifica-ping", methods=["POST"])
def pianifica_ping():
    try:
        dati = request.get_json()
        print(f"📩 Ricevuto JSON: {dati}")

        id_pasto = dati.get("id")
        if not id_pasto:
            print("❌ Nessun ID pasto ricevuto")
            return jsonify({"errore": "ID del pasto mancante"}), 400

        print(f"📅 Inizio pianificazione ping per pasto: {id_pasto}")
        now = datetime.now(pytz.timezone("Europe/Rome"))
        ping_schedule = [(10, "t1"), (20, "t2"), (30, "t3")]

        for minuti, campo in ping_schedule:
            run_time = now + timedelta(minutes=minuti)
            print(f"🕒 Scheduling job {campo} alle {run_time}")
            try:
                job = scheduler.add_job(
                    invia_ping,
                    "date",
                    run_date=run_time,
                    args=[id_pasto, minuti, campo],
                    id=f"ping_{id_pasto}_{campo}",
                    replace_existing=True
                )
                print(f"✅ Job {campo} schedulato: {job.id} alle {run_time}")
            except Exception as e:
                print(f"❌ Errore durante la creazione del job {campo}: {str(e)}")

        return jsonify({"messaggio": "✅ Ping programmati per t1, t2, t3"})

    except Exception as e:
        print(f"❌ Errore durante /pianifica-ping: {str(e)}")
        return jsonify({"errore": str(e)}), 500

@app.route("/glicemia", methods=["GET"])
def glicemia():
    try:
        print("📡 Richiesta lettura glicemia attuale da Dexcom")
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()

        if reading is None:
            print("❌ Nessuna lettura disponibile")
            return jsonify({"errore": "Nessuna lettura disponibile da Dexcom"}), 404

        valore = reading.value
        trend = reading.trend_description
        timestamp = reading.time.strftime("%Y-%m-%d %H:%M:%S")

        print(f"📈 Glicemia attuale: {valore}, Trend: {trend}, Timestamp: {timestamp}")
        return jsonify({
            "glicemia": valore,
            "trend": trend,
            "timestamp": timestamp
        })

    except Exception as e:
        print(f"❌ Errore /glicemia: {str(e)}")
        return jsonify({"errore": str(e)}), 500

@app.route("/jobs", methods=["GET"])
def lista_job_schedulati():
    try:
        jobs = scheduler.get_jobs()
        elenco = []
        print(f"📋 Recupero jobs schedulati...")
        for job in jobs:
            print(f"🔄 Job: {job.id} | Next run: {job.next_run_time}")
            elenco.append({
                "id": job.id,
                "name": job.name,
                "run_time": job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.next_run_time else None
            })
        return jsonify(elenco)
    except Exception as e:
        print(f"❌ Errore /jobs: {str(e)}")
        return jsonify({"errore": str(e)}), 500

if __name__ == "__main__":
    print("🚀 Avvio server Flask in modalità standalone...")
    app.run(host="0.0.0.0", port=5001)