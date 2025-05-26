import os
import time
import threading
import requests
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
    try:
        for chat_id in TELEGRAM_CHAT_IDS:
            chat_id = chat_id.strip()
            if chat_id:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": f"{titolo.upper()}\n{messaggio}"
                }
                r = requests.post(url, json=payload)
                print(f"✅ Telegram [{chat_id}]: {r.status_code}")
    except Exception as e:
        print(f"❌ Errore Telegram: {e}")

def genera_alert(tipo, azione, codice):
    global alert_attivo, intervallo_notifica

    if alert_attivo and alert_attivo["codice"] == codice:
        return None

    alert_attivo = {"tipo": tipo, "azione": azione, "codice": codice}
    invia_notifica(tipo, azione)

    if intervallo_notifica:
        intervallo_notifica.cancel()

    def notifica_periodica():
        invia_notifica(tipo, azione)
        if alert_attivo:
            start_periodica()

    def start_periodica():
        global intervallo_notifica
        intervallo_notifica = threading.Timer(120, notifica_periodica)
        intervallo_notifica.start()

    start_periodica()
    return alert_attivo

def valuta_glicemia(valore, trend, timestamp):
    cronologia.append({"valore": valore, "trend": trend, "timestamp": timestamp})
    if len(cronologia) > 5:
        cronologia.pop(0)

    trend = trend_to_arrow(trend)

    if valore < 75:
        return genera_alert("Ipoglicemia grave", "Correggi con zuccheri semplici", "urgente")

    if 75 <= valore < 80:
        if trend in ["↓", "↓↓", "↓↓↓"]:
            return genera_alert("Sotto 80 in discesa", "Correggi con 15g zuccheri semplici", "critico_75_80")
        if len(cronologia) >= 2 and all(x["valore"] < 80 for x in cronologia[-2:]):
            return genera_alert("Sotto 80 stabile", "Zuccheri + snack se IOB attivo", "stabile_75_80")

    if 80 <= valore < 85:
        if trend == "↓↓↓":
            return genera_alert("Discesa doppia ripida", "Correzione IMMEDIATA + biscotto", "dr_80_85")
        if trend == "↓↓":
            return genera_alert("Discesa rapida", "Correzione con 10g zuccheri", "rapida_80_85")
        if len([x for x in cronologia if x["valore"] < 86]) >= 3:
            return genera_alert("3 valori <86", "Avvia monitoraggio attivo", "monitoraggio_85")

    if 85 <= valore < 90:
        if trend == "↓↓↓":
            return genera_alert("Allarme rapido 85", "Correggi con zuccheri subito", "flash_85")
        if trend == "↓↓" and cronologia[-2]["valore"] >= 90:
            return genera_alert("Da 90 in ↓↓", "Zuccheri + attenzione", "scivolo_90")

    return None

def conferma_utente():
    global alert_attivo, intervallo_notifica
    if intervallo_notifica:
        intervallo_notifica.cancel()
    alert_attivo = None
    intervallo_notifica = None
    print("✅ Alert disattivato")

def get_alert_attivo():
    return alert_attivo

def ottieni_chat_id():
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        r = requests.get(url)
        data = r.json()
        print("Risposta Telegram:", data)
    except Exception as e:
        print(f"Errore recupero chat ID: {e}")

# Solo per test locale
if __name__ == "__main__":
    ottieni_chat_id()