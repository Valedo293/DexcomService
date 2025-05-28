import os
import time
import threading
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_IDS = os.getenv("TELEGRAM_CHAT_IDS", "").split(",")

cronologia = []
alert_attivo = None
intervallo_notifica = None

def trend_to_arrow(trend_raw):
    trend_map = {
        "DoubleUp": "↑↑",
        "SingleUp": "↑",
        "FortyFiveUp": "↗",
        "Flat": "→",
        "FortyFiveDown": "↘",
        "SingleDown": "↓",
        "DoubleDown": "↓↓",
        "NotComputable": "→",
        "RateOutOfRange": "→"
    }
    return trend_map.get(trend_raw, "→")

def invia_notifica(titolo, messaggio):
    print(f"[DEBUG] Invio notifica Telegram: {titolo} - {messaggio}")
    print(f"[DEBUG] TOKEN: {TELEGRAM_TOKEN}")
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

def valuta_glicemia(valore, trend_raw, timestamp):
    global cronologia, alert_attivo
    trend = trend_to_arrow(trend_raw)

    cronologia.append({"valore": valore, "trend": trend, "timestamp": timestamp})
    if len(cronologia) > 10:
        cronologia.pop(0)

    print(f"[DEBUG] Glicemia attuale: {valore} | Trend: {trend} | Timestamp: {timestamp}")
    print(f"[DEBUG] Cronologia: {cronologia}")
    print(f"[DEBUG] Alert attivo: {alert_attivo}")

    # RESET se glicemia torna stabile o in salita ≥ 78
    if alert_attivo and valore >= 78 and trend in ["→", "↑", "↗", "↑↑"]:
        print("[DEBUG] Glicemia risalita, reset alert.")
        reset_alert()

    # PROVA 1 - 3 glicemie tra 140-100 stabili
    if len(cronologia) >= 3:
        ultime = cronologia[-3:]
        if all(100 <= x["valore"] <= 140 and x["trend"] == "→" for x in ultime):
            return genera_alert(
                "TEST PROVA 1",
                "Tre valori stabili tra 100 e 140",
                "test_3_stabili"
            )

    # PROVA 2 - due stabili tra 140-100 seguite da una discesa
    if len(cronologia) >= 3:
        c1, c2, c3 = cronologia[-3:]
        if all(100 <= x["valore"] <= 140 for x in [c1, c2, c3]):
            if c1["trend"] == "→" and c2["trend"] == "→" and c3["trend"] in ["↘", "↓"]:
                return genera_alert(
                    "TEST PROVA 2",
                    "Due glicemie stabili tra 140-100 seguite da discesa",
                    "test_2_stabili_1_discesa"
                )

    # PROVA 3 - 140 in salita
    if valore == 140 and trend in ["↗", "↑", "↑↑"]:
        return genera_alert(
            "TEST PROVA 3",
            "Valore 140 in salita → occhio alla glicemia",
            "test_140_salita"
        )

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
    print("Modulo monitorGlicemia TEST attivo. Usa `valuta_glicemia(valore, trend, timestamp)` per simulare.")