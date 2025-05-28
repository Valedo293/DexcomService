import os
import threading
import requests
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

# Caricamento variabili ambiente
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_IDS = os.getenv("TELEGRAM_CHAT_IDS", "").split(",")
MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI)
db = client["nightscout"]
collezione = db.entries

alert_attivo = None
intervallo_notifica = None

def trend_to_arrow(trend_raw):
    mappa = {
        "DoubleUp": "↑↑", "SingleUp": "↑", "FortyFiveUp": "↗",
        "Flat": "→", "FortyFiveDown": "↘", "SingleDown": "↓",
        "DoubleDown": "↓↓", "NotComputable": "→", "RateOutOfRange": "→"
    }
    return mappa.get(trend_raw, "→")

def invia_notifica(titolo, messaggio):
    for chat_id in TELEGRAM_CHAT_IDS:
        if chat_id.strip():
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                payload = {"chat_id": chat_id.strip(), "text": f"{titolo.upper()}\n{messaggio}"}
                requests.post(url, json=payload)
            except Exception as e:
                print(f"[Telegram] Errore: {e}")

def reset_alert():
    global alert_attivo, intervallo_notifica
    if intervallo_notifica:
        intervallo_notifica.cancel()
    alert_attivo = None
    intervallo_notifica = None

def genera_alert(titolo, messaggio, codice, ripetizioni=2):
    global alert_attivo, intervallo_notifica
    if alert_attivo and alert_attivo["codice"] == codice:
        return None
    alert_attivo = {"tipo": titolo, "azione": messaggio, "codice": codice, "ripetizioni": ripetizioni}
    invia_notifica(titolo, messaggio)

    def notifica_periodica():
        if alert_attivo and alert_attivo["ripetizioni"] > 0:
            invia_notifica(titolo, messaggio)
            alert_attivo["ripetizioni"] -= 1
            start_periodica()
        else:
            reset_alert()

    def start_periodica():
        global intervallo_notifica
        intervallo_notifica = threading.Timer(120, notifica_periodica)
        intervallo_notifica.start()

    if ripetizioni > 0:
        start_periodica()

def recupera_ultime_glicemie(n=3):
    try:
        docs = list(collezione.find().sort("date", -1).limit(n))
        docs_ordinati = sorted(docs, key=lambda x: x["date"])
        return [{
            "valore": x["sgv"],
            "trend": trend_to_arrow(x.get("direction", "Flat")),
            "timestamp": datetime.fromtimestamp(x["date"] / 1000)
        } for x in docs_ordinati]
    except Exception as e:
        print(f"[MongoDB] Errore lettura: {e}")
        return []

def valuta_glicemia_mongo():
    ultime = recupera_ultime_glicemie(3)
    if len(ultime) < 3:
        print("[DEBUG] Meno di 3 valori disponibili.")
        return

    print(f"[DEBUG] Ultime glicemie: {ultime}")
    c1, c2, c3 = ultime

    if all(70 <= x["valore"] <= 140 and x["trend"] == "→" for x in [c2, c3]):
        return genera_alert("ALLARME 1", "Due valori stabili consecutivi tra 70-140", "alert_1")

    if (70 <= c2["valore"] <= 200 and c2["trend"] == "→" and
        70 <= c3["valore"] <= 200 and c3["trend"] in ["↗", "↑", "↑↑"]):
        return genera_alert("ALLARME 2", "Stabile seguito da salita tra 70-200", "alert_2")

    if 80 <= c3["valore"] <= 100 and c3["trend"] in ["↘", "↓", "↓↓"]:
        return genera_alert("ALLARME 3", "Discesa ripida singola tra 80-100", "alert_3")

    if all(80 <= x["valore"] <= 160 and x["trend"] == "→" for x in [c1, c2, c3]) and c1["valore"] > c2["valore"] > c3["valore"]:
        return genera_alert("ALLARME 4", "Tre valori stabili ma in discesa tra 80-160", "alert_4")

    print("[DEBUG] Nessuna condizione soddisfatta.")
    reset_alert()

def ciclo_monitoraggio():
    valuta_glicemia_mongo()
    threading.Timer(300, ciclo_monitoraggio).start()

# Avvio
ciclo_monitoraggio()