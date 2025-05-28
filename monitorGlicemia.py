import pymongo
import time
from datetime import datetime
from collections import deque

# Connessione al database MongoDB
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["glicemia"]
collection = db["valori"]

# Tracciamento dell'ultimo valore letto
ultimo_id = None

# Coda per memorizzare gli ultimi valori
storico = deque(maxlen=5)

# Stato degli allarmi per evitare notifiche ripetute
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

    # 1. Due valori stabili consecutivi tra 70 e 140
    if not allarmi_attivi["2_stabili"]:
        if (storico[-1]["trend"] == "stabile" and storico[-2]["trend"] == "stabile" and
            70 <= valori[-1] <= 140 and 70 <= valori[-2] <= 140):
            print(f"⚠️ [ALLARME 1 - {now}] Due valori stabili consecutivi tra 70 e 140")
            allarmi_attivi["2_stabili"] = True

    # 2. Un valore stabile e uno in salita tra 70 e 200
    if not allarmi_attivi["stabile_salita"]:
        if (storico[-2]["trend"] == "stabile" and storico[-1]["trend"] == "salita" and
            70 <= valori[-2] <= 200 and 70 <= valori[-1] <= 200):
            print(f"⚠️ [ALLARME 2 - {now}] Un valore stabile e uno in salita tra 70 e 200")
            allarmi_attivi["stabile_salita"] = True

    # 3. Un solo valore con discesa ripida tra 100 e 80
    if not allarmi_attivi["discesa_ripida"]:
        if (storico[-1]["trend"] == "discesa" and 80 <= valori[-1] <= 100):
            print(f"⚠️ [ALLARME 3 - {now}] Discesa ripida tra 100 e 80")
            allarmi_attivi["discesa_ripida"] = True

    # 4. Tre valori stabili in discesa tra 80 e 160
    if not allarmi_attivi["3_stabili_discesa"]:
        if (len(storico) >= 3 and all(s["trend"] == "stabile" for s in storico[-3:]) and
            80 <= valori[-1] <= 160 and
            valori[-3] > valori[-2] > valori[-1]):
            print(f"⚠️ [ALLARME 4 - {now}] Tre valori stabili in discesa tra 80 e 160")
            allarmi_attivi["3_stabili_discesa"] = True

def analizza_valore(valore):
    print(f"🩸 Nuovo valore: {valore['valore']} mg/dl | Trend: {valore['trend']} | {valore['timestamp']}")
    storico.append(valore)
    valuta_eventi(storico)

# Ciclo principale
while True:
    try:
        ultimo_valore = collection.find_one(sort=[("_id", pymongo.DESCENDING)])

        if ultimo_valore and ultimo_valore["_id"] != ultimo_id:
            ultimo_id = ultimo_valore["_id"]
            analizza_valore(ultimo_valore)
        else:
            print("⏳ Nessun nuovo valore.")

        time.sleep(30)  # attesa prima di rileggere

        # Reset degli allarmi se la glicemia esce dai range
        if storico and not any([
            70 <= storico[-1]["valore"] <= 140,
            80 <= storico[-1]["valore"] <= 160,
            100 >= storico[-1]["valore"] >= 80
        ]):
            reset_allarmi()

    except Exception as e:
        print(f"❌ Errore: {e}")
        time.sleep(30)