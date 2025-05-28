import pymongo
import os
import time
from datetime import datetime
from collections import deque
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
client = pymongo.MongoClient(MONGO_URI)
db = client["nightscout"]
collection = db["entries"]

TREND_MAP = {
    "Flat": "stabile",
    "SingleUp": "salita",
    "DoubleUp": "salita",
    "FortyFiveUp": "salita",
    "SingleDown": "discesa",
    "DoubleDown": "discesa",
    "FortyFiveDown": "discesa"
}

ultimo_id = None
storico = deque(maxlen=5)

allarmi_attivi = {
    "2_stabili": False,
    "stabile_salita": False,
    "discesa_ripida": False,
    "3_stabili_discesa": False
}

def reset_allarmi():
    for k in allarmi_attivi:
        allarmi_attivi[k] = False

def valuta_eventi(storico):
    if len(storico) < 3:
        return

    valori = [s["valore"] for s in storico]
    trend = [s["trend"] for s in storico]
    now = datetime.now().strftime("%H:%M:%S")

    # 1. Due stabili consecutivi tra 70 e 140
    if not allarmi_attivi["2_stabili"]:
        if (trend[-1] == "stabile" and trend[-2] == "stabile" and
            70 <= valori[-1] <= 140 and 70 <= valori[-2] <= 140):
            print(f"⚠️ [ALLARME 1 - {now}] Due valori stabili consecutivi tra 70 e 140")
            allarmi_attivi["2_stabili"] = True

    # 2. Stabile + salita tra 70 e 200
    if not allarmi_attivi["stabile_salita"]:
        if (trend[-2] == "stabile" and trend[-1] == "salita" and
            70 <= valori[-2] <= 200 and 70 <= valori[-1] <= 200):
            print(f"⚠️ [ALLARME 2 - {now}] Un valore stabile e uno in salita tra 70 e 200")
            allarmi_attivi["stabile_salita"] = True

    # 3. Discesa ripida tra 100 e 80
    if not allarmi_attivi["discesa_ripida"]:
        if trend[-1] == "discesa" and 80 <= valori[-1] <= 100:
            print(f"⚠️ [ALLARME 3 - {now}] Discesa ripida tra 100 e 80")
            allarmi_attivi["discesa_ripida"] = True

    # 4. Tre stabili in discesa tra 80 e 160
    if not allarmi_attivi["3_stabili_discesa"]:
        if (trend[-1] == trend[-2] == trend[-3] == "stabile" and
            80 <= valori[-3] <= 160 and
            valori[-3] > valori[-2] > valori[-1]):
            print(f"⚠️ [ALLARME 4 - {now}] Tre valori stabili in discesa tra 80 e 160")
            allarmi_attivi["3_stabili_discesa"] = True

def analizza_valore(valore):
    trend = TREND_MAP.get(valore.get("direction", "Flat"), "stabile")
    valore_glicemia = valore.get("sgv")
    timestamp = datetime.fromtimestamp(valore["date"] / 1000)

    print(f"🩸 Nuovo valore: {valore_glicemia} mg/dl | Trend: {trend} | {timestamp}")
    storico.append({
        "valore": valore_glicemia,
        "trend": trend,
        "timestamp": timestamp
    })
    valuta_eventi(storico)

print("✅ Monitor glicemia avviato")
while True:
    try:
        ultimo_valore = collection.find_one(sort=[("date", pymongo.DESCENDING)])
        if ultimo_valore and ultimo_valore["_id"] != ultimo_id:
            ultimo_id = ultimo_valore["_id"]
            analizza_valore(ultimo_valore)
        else:
            print("⏳ Nessun nuovo valore...")

        time.sleep(30)

        if storico and not any([
            70 <= storico[-1]["valore"] <= 140,
            80 <= storico[-1]["valore"] <= 160,
            100 >= storico[-1]["valore"] >= 80
        ]):
            reset_allarmi()

    except Exception as e:
        print(f"❌ Errore monitor: {e}")
        time.sleep(30)