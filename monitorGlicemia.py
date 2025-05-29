import pymongo
import time
import os
from dotenv import load_dotenv
import requests
from datetime import datetime

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_IDS = os.getenv("TELEGRAM_CHAT_IDS").split(",")

alert_attivo = None
cronologia = []

def trend_to_arrow(trend_raw):
    trend_map = {
        "DoubleUp": "↑↑", "SingleUp": "↑", "FortyFiveUp": "↗",
        "Flat": "→", "FortyFiveDown": "↘", "SingleDown": "↓",
        "DoubleDown": "↓↓", "NotComputable": "→", "RateOutOfRange": "→"
    }
    return trend_map.get(trend_raw, "→")

def send_telegram(title, message):
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": chat_id.strip(), "text": f"{title}\n{message}"}
            requests.post(url, json=payload)
        except Exception as e:
            print(f"[❌] Errore Telegram: {e}")

def reset_alert():
    global alert_attivo
    alert_attivo = None

def genera_alert(titolo, messaggio, codice):
    global alert_attivo
    if alert_attivo and alert_attivo["codice"] == codice:
        return
    alert_attivo = {"codice": codice, "timestamp": datetime.now().isoformat()}
    send_telegram(titolo, messaggio)

def valuta_glicemia(valore, trend):
    global cronologia, alert_attivo

    freccia = trend_to_arrow(trend)
    cronologia.append({"valore": valore, "trend": freccia})
    if len(cronologia) > 10:
        cronologia.pop(0)

    # RESET se glicemia torna stabile o in salita ≥ 78
    if alert_attivo and valore >= 78 and freccia in ["→", "↑", "↗", "↑↑"]:
        reset_alert()

    # 1. Ipoglicemia grave <75
    if valore < 75:
        return genera_alert(
            "Ipoglicemia",
            "Correggi con: un succo, 3 bustine di zucchero o 3 caramelle zuccherate. Se IOB attivo anche uno snack",
            "ipo_grave"
        )

    # 2. 86 in discesa lenta (↘ o ↓)
    if valore == 86 and freccia in ["↘", "↓"]:
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
    if valore in [78, 79] and freccia == "→":
        return genera_alert(
            "Glicemia al limite",
            "Mangia un Tuc, un grissino o una caramella.",
            "limite_78_stabile"
        )

    # 5. Da 90 a 70 in discesa rapida o doppia
    if 70 <= valore <= 90 and freccia in ["↓", "↓↓"]:
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

def main():
    try:
        client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client["nightscout"]
        collection = db["entries"]

        ultimo_id = None

        while True:
            try:
                ultimi = list(collection.find().sort("date", pymongo.DESCENDING).limit(5))
                if not ultimi:
                    time.sleep(40)
                    continue

                ultimo_doc = ultimi[0]
                if ultimo_doc.get("_id") != ultimo_id:
                    ultimo_id = ultimo_doc.get("_id")
                    valore = float(ultimo_doc.get("sgv"))
                    trend = ultimo_doc.get("direction", "Flat")
                    valuta_glicemia(valore, trend)

            except Exception as e:
                print(f"❌ Errore lettura Mongo: {e}")

            time.sleep(40)

    except Exception:
        print("❌ Impossibile collegarsi a MongoDB")

if _name_ == "_main_":
    main()
