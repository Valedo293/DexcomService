from dotenv import load_dotenv
import os
import pymongo
import time
import requests

# --- Caricamento variabili ambiente ---
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_IDS = os.getenv("TELEGRAM_CHAT_IDS", "").split(",")

alert_attivo = False
ultimo_alert = None

def manda_telegram(messaggio):
    for chat_id in CHAT_IDS:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            data = {"chat_id": chat_id.strip(), "text": messaggio}
            r = requests.post(url, json=data)
            print(f"[TELEGRAM] Inviato a {chat_id.strip()} - Status: {r.status_code}")
        except Exception as e:
            print(f"[ERRORE TELEGRAM] {e}")

def reset_alert():
    global alert_attivo, ultimo_alert
    print("✅ Condizioni risolte, alert chiuso")
    alert_attivo = False
    ultimo_alert = None

def genera_alert(titolo, messaggio, codice):
    global alert_attivo, ultimo_alert
    if ultimo_alert != codice:
        print(f"[ALERT] {titolo} - {messaggio}")
        manda_telegram(f"🚨 {titolo}\n{messaggio}")
        alert_attivo = True
        ultimo_alert = codice
    else:
        print(f"[SKIP] Alert {codice} già attivo")

def monitor_loop():
    try:
        client = pymongo.MongoClient(MONGO_URI)
        db = client["nightscout"]
        collection = db["entries"]
        print("✅ Connesso a MongoDB")
        manda_telegram("🟢 MonitorGlicemia avviato correttamente")

        while True:
            try:
                docs = list(collection.find().sort("date", pymongo.DESCENDING).limit(5))
                if len(docs) < 3:
                    print("⚠ Dati insufficienti")
                    time.sleep(40)
                    continue

                cronologia = [{
                    "valore": d["sgv"],
                    "trend": d.get("direction", "→")
                } for d in reversed(docs)]

                valore = cronologia[-1]["valore"]
                trend = cronologia[-1]["trend"]

                print(f"📈 Ultima glicemia: {valore} - Trend: {trend}")

                if alert_attivo and valore >= 78 and trend in ["→", "↑", "↗", "↑↑"]:
                    reset_alert()

                if valore < 75:
                    genera_alert("Ipoglicemia",
                                 "Correggi con: un succo, 3 bustine di zucchero o 3 caramelle zuccherate. Se IOB attivo anche uno snack",
                                 "ipo_grave")

                if valore == 86 and trend in ["↘", "↓"]:
                    genera_alert("Ipoglicemia in arrivo",
                                 "Correggi con mezzo succo. Se sei lontano dal pasto o hai insulina attiva, mangia anche uno snack.",
                                 "lenta_86")

                if all(x["trend"] == "→" for x in cronologia[-3:]) and \
                        cronologia[-3]["valore"] > cronologia[-2]["valore"] > cronologia[-1]["valore"] >= 79:
                    genera_alert("Glicemia al limite",
                                 "Mangia un Tuc, un grissino o una caramella.",
                                 "limite_stabile")

                if valore in [78, 79] and trend == "→":
                    genera_alert("Glicemia al limite",
                                 "Mangia un Tuc, un grissino o una caramella.",
                                 "limite_78_stabile")

                if 70 <= valore <= 90 and trend in ["↓", "↓↓"]:
                    genera_alert("Discesa glicemica rapida",
                                 "Correggi subito con zuccheri semplici. Aggiungi uno snack se hai fatto insulina da meno di 2 ore.",
                                 f"rapida_{valore}")

                c1 = cronologia[-1]
                c2 = cronologia[-2]
                if c1["valore"] < 90 and c2["valore"] < 90 and \
                        c1["trend"] in ["↘", "↓"] and c2["trend"] in ["↘", "↓"]:
                    genera_alert("Discesa confermata",
                                 "Glicemia in calo costante. Correggi con mezzo succo.",
                                 "doppia_discesa_90")

            except Exception as e:
                print(f"❌ Errore loop monitor: {e}")

            time.sleep(40)

    except Exception as e:
        print(f"❌ Errore iniziale MongoDB: {e}")

if _name_ == "_main_":
    monitor_loop()
