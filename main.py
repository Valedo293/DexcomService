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

# Headers per Supabase
headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# Scheduler
scheduler = BackgroundScheduler(timezone="Europe/Rome")
scheduler.start()

def aggiorna_valore_tempo(id_pasto, campo, valore):
    try:
        print(f"🚀 PATCH Supabase per {campo}, id_pasto={id_pasto}, valore={valore}")
        url = f"{SUPABASE_URL}/rest/v1/analisi_dati?id=eq.{id_pasto}"
        payload = {campo: valore}
        res = requests.patch(url, headers=headers, json=payload)
        print(f"🔄 Status: {res.status_code}, Response: {res.text}")
    except Exception as e:
        print(f"❌ PATCH error: {e}")

def invia_ping(id_pasto, distanza_minuti, campo):
    try:
        print(f"⏱️ Ping eseguito per {campo}, id_pasto={id_pasto}")
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if reading:
            valore = float(reading.value)
            print(f"📈 Glicemia letta: {valore}")
            aggiorna_valore_tempo(id_pasto, campo, valore)
        else:
            print("⚠️ Nessuna lettura disponibile da Dexcom")
    except Exception as e:
        print(f"❌ Errore invio ping {campo}: {e}")

def job_listener(event):
    if event.exception:
        print(f"❌ Il job {event.job_id} ha fallito: {event.exception}")
    else:
        print(f"✅ Il job {event.job_id} è stato eseguito con successo!")

scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

@app.route("/pianifica-ping", methods=["POST"])
def pianifica_ping():
    try:
        dati = request.get_json()
        id_pasto = dati.get("id")
        if not id_pasto:
            return jsonify({"errore": "ID del pasto mancante"}), 400

        now = datetime.now(pytz.timezone("Europe/Rome"))
        intervalli = [(2, "t1"), (4, "t2"), (6, "t3")]

        for minuti, campo in intervalli:
            run_time = now + timedelta(minutes=minuti)
            print(f"⏰ Schedulo {campo} per le {run_time}")
            scheduler.add_job(
                invia_ping,
                "date",
                run_date=run_time,
                args=[id_pasto, minuti, campo],
                id=f"ping_{id_pasto}_{campo}",
                replace_existing=True
            )

        return jsonify({"messaggio": "Ping schedulati con successo"})
    except Exception as e:
        print(f"❌ Errore in /pianifica-ping: {e}")
        return jsonify({"errore": str(e)}), 500

@app.route("/jobs", methods=["GET"])
def lista_job_schedulati():
    try:
        jobs = scheduler.get_jobs()
        elenco = [{
            "id": job.id,
            "name": job.name,
            "run_time": job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.next_run_time else None
        } for job in jobs]
        return jsonify(elenco)
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

@app.route("/esegui-subito", methods=["POST"])
def esegui_ping_subito():
    try:
        dati = request.get_json()
        id_pasto = dati.get("id")
        campo = dati.get("campo", "t1")
        if not id_pasto:
            return jsonify({"errore": "ID del pasto mancante"}), 400
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if reading:
            valore = float(reading.value)
            aggiorna_valore_tempo(id_pasto, campo, valore)
            return jsonify({"messaggio": f"✅ Ping eseguito per {campo}", "glicemia": valore})
        else:
            return jsonify({"errore": "Nessuna lettura disponibile da Dexcom"}), 404
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

@app.route("/glicemia", methods=["GET"])
def ottieni_glicemia():
    try:
        dexcom = Dexcom(USERNAME, PASSWORD, ous=True)
        reading = dexcom.get_current_glucose_reading()
        if reading:
            return jsonify({
                "glicemia": float(reading.value),
                "trend": reading.trend_description,
                "timestamp": reading.datetime.strftime("%Y-%m-%d %H:%M:%S")
            })
        else:
            return jsonify({"errore": "Nessuna lettura disponibile"}), 404
    except Exception as e:
        return jsonify({"errore": str(e)}), 500

# TEST JOB per Render
def job_di_test():
    print("✅ JOB DI TEST ESEGUITO (Render sta mantenendo attivo lo scheduler)")

scheduler.add_job(
    job_di_test,
    "date",
    run_date=datetime.now(pytz.timezone("Europe/Rome")) + timedelta(minutes=2),
    id="job_test_scheduler"
)
print("🧪 Job di test schedulato per 2 minuti dopo l’avvio")