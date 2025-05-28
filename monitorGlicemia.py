import pymongo
import time
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

def main():
    try:
        client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        db = client["nightscout"]
        collection = db["entries"]

        print("✅ Connessione a MongoDB stabilita")

        ultimo_id = None

        while True:
            try:
                # Prendo gli ultimi 5 documenti ordinati per data desc
                ultimi_documenti = list(collection.find().sort("date", pymongo.DESCENDING).limit(5))
                
                if not ultimi_documenti:
                    print("⚠️ Nessun dato trovato nella collezione 'entries'")
                else:
                    # Stampiamo i dati per capire cosa c’è
                    print(f"📊 Ultimi {len(ultimi_documenti)} valori:")
                    for doc in reversed(ultimi_documenti):  # dal più vecchio al più recente
                        print(f"   id: {doc.get('_id')} | glicemia: {doc.get('sgv')} | trend: {doc.get('direction')} | timestamp: {doc.get('date')}")

                    # Controllo se l’ultimo valore è nuovo rispetto a quello già letto
                    ultimo_doc = ultimi_documenti[0]  # primo elemento è il più recente per sort desc
                    if ultimo_doc.get('_id') != ultimo_id:
                        print(f"✨ Nuovo valore rilevato: {ultimo_doc.get('sgv')} (id: {ultimo_doc.get('_id')})")
                        ultimo_id = ultimo_doc.get('_id')
                    else:
                        print("⏳ Nessun nuovo valore")

            except Exception as e:
                print(f"❌ Errore durante la lettura dal DB: {e}")

            time.sleep(30)

    except Exception:
        print("❌ Non sono riuscito a collegarmi a MongoDB. Controlla URI e connessione.")

if __name__ == "__main__":
    main()