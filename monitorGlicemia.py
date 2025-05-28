import os
import threading
import requests
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Configurazione
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_IDS = os.getenv("TELEGRAM_CHAT_IDS", "").split(",")
MONGO_URI = os.getenv("MONGODB_URI")

# Connessione a MongoDB
client = MongoClient(MONGO_URI)
db = client.get_database()
collezione_glicemie = db.get_collection("glicemie")

alert_attivo = None
intervallo_notifica = None

def trend_to_arrow(trend_raw):
    trend_map = {
        "DoubleUp": "↑↑", "SingleUp": "↑", "FortyFiveUp": "↗",
        "Flat": "→", "FortyFiveDown": "↘", "SingleDown": "↓",
        "DoubleDown": "↓↓", "NotComputable": "→", "RateOutOfRange": "→"
    }
    arrow = trend_map.get(trend_raw, "→")
    print(f"[DEBUG] trend_raw: {trend_raw} → trend_arrow: {arrow}")
    return arrow

def invia_notifica(titolo, messaggio):
    print(f"[DEBUG] Invio notifica Telegram: {titolo} - {messaggio}")
    for chat_id in TELEGRAM_CHAT_IDS:
        chat_id = chat_id.strip()
        if not chat_id:
            print("[DEBUG] Chat ID vuoto, salto.")
            continue
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": chat_id, "text": f"{titolo.upper()}\n{messaggio}"}
            r = requests.post(url, json=payload)
            print(f"✅ Telegram [{chat_id}]: {r.status_code} - {r.text}")
        except Exception as e:
            print(f"❌ Errore Telegram: {e}")

def reset_alert():
    global alert_attivo, intervallo_notifica
    print("[DEBUG] Eseguo reset_alert")
    if intervallo_notifica:
        intervallo_notifica.cancel()
    alert_attivo = None
    intervallo_notifica = None
    print("[DEBUG] ✅ Alert disattivato (automatico)")

def genera_alert(titolo, messaggio, codice, ripetizioni=2):
    global alert_attivo, intervallo_notifica
    if alert_attivo and alert_attivo["codice"] == codice:
        print(f"[DEBUG] Alert {codice} già attivo, non invio doppio.")
        return None
    print(f"[DEBUG] Genera alert: {titolo} | {messaggio} | codice: {codice}")
    alert_attivo = {"tipo": titolo, "azione": messaggio, "codice": codice, "ripetizioni": ripetizioni}
    invia_notifica(titolo, messaggio)

    def notifica_periodica():
        if alert_attivo and alert_attivo["ripetizioni"] > 0:
            print("[DEBUG] Invio notifica periodica")
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

    return alert_attivo

def recupera_ultime_glicemie(n=3):
    try:
        print(f"[DEBUG] Recupero ultime {n} glicemie da Mongo...")
        dati = list(collezione_glicemie.find().sort("timestamp", -1).limit(n))
        dati_ordinati = sorted(dati, key=lambda x: x["timestamp"])
        for g in dati_ordinati:
            print(f"[DEBUG] Da Mongo: {g['valore']} mg/dL, trend: {g['trend']}, ts: {g['timestamp']}")
        return dati_ordinati
    except Exception as e:
        print(f"[ERRORE] Recupero glicemie da Mongo fallito: {e}")
        return []

def valuta_glicemia(valore, trend_raw, timestamp):
    global alert_attivo
    print(f"[DEBUG] ➤ Chiamata valuta_glicemia con valore={valore}, trend_raw={trend_raw}, timestamp={timestamp}")

    trend = trend_to_arrow(trend_raw)

    # RESET se glicemia torna stabile o in salita ≥ 78
    if alert_attivo and valore >= 78 and trend in ["→", "↑", "↗", "↑↑"]:
        print("[DEBUG] Glicemia risalita, reset alert.")
        reset_alert()

    ultime = recupera_ultime_glicemie(3)
    if len(ultime) < 3:
        print("[DEBUG] Meno di 3 valori in Mongo. Nessuna valutazione.")
        return None

    # PROVA 1
    if all(100 <= x["valore"] <= 140 and x["trend"] == "→" for x in ultime):
        return genera_alert("TEST PROVA 1", "Tre valori stabili tra 100 e 140", "test_3_stabili")

    # PROVA 2
    if all(100 <= x["valore"] <= 140 for x in ultime):
        if ultime[0]["trend"] == "→" and ultime[1]["trend"] == "→" and ultime[2]["trend"] in ["↘", "↓"]:
            return genera_alert("TEST PROVA 2", "Due stabili seguite da discesa tra 100-140", "test_2_stabili_1_discesa")

    # PROVA 3
    if valore == 140 and trend in ["↗", "↑", "↑↑"]:
        return genera_alert("TEST PROVA 3", "Valore 140 in salita → occhio alla glicemia", "test_140_salita")

    # PROVA 4
    if 70 <= valore <= 100 and trend in ["→", "↘", "↓"]:
        return genera_alert("TEST PROVA 4", "Valore tra 100 e 70 con trend stabile o in discesa", "test_tra_100_70")

    # PROVA 5
    if all(70 <= x["valore"] <= 100 and x["trend"] in ["↘", "↓"] for x in ultime):
        return genera_alert("TEST PROVA 5", "Tre valori in discesa tra 100 e 70", "test_3_discese_100_70")

    # PROVA 6
    if all(70 <= x["valore"] <= 100 for x in ultime[-2:]):
        c1, c2 = ultime[-2:]
        if (c1["trend"] in ["↘", "↓"] and c2["trend"] == "→") or (c1["trend"] == "→" and c2["trend"] in ["↘", "↓"]):
            return genera_alert("TEST PROVA 6", "Una discesa + una stabile tra 100 e 70", "test_discesa_stabile_100_70")

    print("[DEBUG] Nessuna condizione di alert soddisfatta.")
    return None

def get_alert_attivo():
    return alert_attivo

def ottieni_chat_id():
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        r = requests.get(url)
        data = r.json()
        print("[DEBUG] Risposta Telegram:", data)
    except Exception as e:
        print(f"[DEBUG] Errore recupero chat ID: {e}")

if __name__ == "__main__":
    print("[DEBUG] Modulo monitorGlicemia con Mongo ATTIVO.")
    print("Usa `valuta_glicemia(valore, trend_raw, timestamp)` per testarlo.")