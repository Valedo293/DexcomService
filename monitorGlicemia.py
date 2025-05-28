import pymongo
import time
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

def main():
    try:
        client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # Forza la connessione per verificare subito se funziona
        client.server_info()
        db = client["nightscout"]
        collection = db["entries"]

        print("✅ Connessione a MongoDB stabilita")

        ultimo_id = None

        while True:
            try:
                ultimo_valore = collection.find_one(sort=[("date", pymongo.DESCENDING)])

                if ultimo_valore:
                    if ultimo_valore["_id"] != ultimo_id:
                        ultimo_id = ultimo_valore["_id"]
                        print(f"📊 Nuova glicemia: {ultimo_valore.get('sgv')} | Trend: {ultimo_valore.get('direction')} | Timestamp: {ultimo_valore.get('date')}")
                    else:
                        print("⏳ Nessun nuovo valore")
                else:
                    print("⚠️ Nessun dato trovato nella collezione 'entries'")

            except Exception as e:
                print(f"❌ Errore durante la lettura dal DB: {e}")

            time.sleep(30)

    except Exception:
        print("❌ Non sono riuscito a collegarmi a MongoDB. Controlla URI e connessione.")

if __name__ == "__main__":
    main()