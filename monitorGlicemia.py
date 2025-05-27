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
    for chat_id in TELEGRAM_CHAT_IDS:
        chat_id = chat_id.strip()
        if not chat_id:
            continue
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": chat_id, "text": f"{titolo.upper()}\n{messaggio}"}
            r = requests.post(url, json=payload)
            print(f"✅ Telegram [{chat_id}]: {r.status_code}")
        except Exception as e:
            print(f"❌ Errore Telegram: {e}")

def reset_alert():
    global alert_attivo, intervallo_notifica
    if intervallo_notifica:
        intervallo_notifica.cancel()
    alert_attivo = None
    intervallo_notifica = None
    print("✅ Alert disattivato (automatico)")

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

    return alert_attivo

def valuta_glicemia(valore, trend_raw, timestamp):
    global cronologia, alert_attivo
    trend = trend_to_arrow(trend_raw)

    cronologia.append({"valore": valore, "trend": trend, "timestamp": timestamp})
    if len(cronologia) > 10:
        cronologia.pop(0)

    # RESET se glicemia torna stabile o in salita ≥ 78
    if alert_attivo and valore >= 78 and trend in ["→", "↑", "↗", "↑↑"]:
        reset_alert()

    # 1. Ipoglicemia grave <75
    if valore < 75:
        return genera_alert(
            "Ipoglicemia",
            "Correggi con: un succo, 3 bustine di zucchero o 3 caramelle zuccherate. Se IOB attivo anche uno snack",
            "ipo_grave"
        )

    # 2. 86 in discesa lenta (↘ o ↓)
    if valore == 86 and trend in ["↘", "↓"]:
        return genera_alert(
            "Ipoglicemia in arrivo",
            "Correggi con mezzo succo.\nSe sei lontano dal pasto o hai insulina attiva, mangia anche uno snack: un Tuc, un grissino o una caramella zuccherata.",
            "lenta_86"
        )

    # 3. 3 valori consecutivi stabili ma in discesa (tra 86 e 79)
    if len(cronologia) >= 3:
        ultime = cronologia[-3:]
        if all(x["trend"] == "→" for x in ultime) and ultime[0]["valore"] > ultime[1]["valore"] > ultime[2]["valore"] >= 79:
            return genera_alert(
                "Glicemia al limite",
                "Mangia un Tuc, un grissino o una caramella.",
                "limite_stabile"
            )

    # 4. Glicemia = 78 o 79 stabile → alert
    if valore in [78, 79] and trend == "→":
        return genera_alert(
            "Glicemia al limite",
            "Mangia un Tuc, un grissino o una caramella.",
            "limite_78_stabile"
        )

    # 5. Da 90 a 70 in discesa rapida o doppia
    if 70 <= valore <= 90 and trend in ["↓", "↓↓"]:
        return genera_alert(
            "Discesa glicemica rapida",
            "Correggi subito con zuccheri semplici. Aggiungi uno snack se hai fatto insulina da meno di 2 ore.",
            f"rapida_{valore}"
        )

    # 6. Due glicemie consecutive <90 con discesa lenta
    if len(cronologia) >= 2:
        c1 = cronologia[-1]
        c2 = cronologia[-2]
        if c1["valore"] < 90 and c2["valore"] < 90 and c1["trend"] in ["↘", "↓"] and c2["trend"] in ["↘", "↓"]:
            return genera_alert(
                "Discesa confermata",
                "Glicemia in calo costante. Correggi con mezzo succo.",
                "doppia_discesa_90"
            )

    return None

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

if __name__ == "__main__":
    print("Modulo monitorGlicemia attivo. Usa `valuta_glicemia(valore, trend, timestamp)` per test.")