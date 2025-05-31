import os
import requests
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_ids = os.getenv("TELEGRAM_CHAT_IDS", "").split(",")

def manda_telegram(chat_id, messaggio):
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id.strip(), "text": messaggio}
        r = requests.post(url, json=payload)
        print(f"[TEST TELEGRAM] Chat {chat_id.strip()} → {r.status_code} - {r.text}")
    except Exception as e:
        print(f"[ERRORE] Chat {chat_id.strip()} → {e}")

print("== AVVIO TEST NOTIFICHE TELEGRAM ==")
print(f"TOKEN presente: {'SI' if token else 'NO'}")
print(f"Chat IDs trovati: {chat_ids}")

for cid in chat_ids:
    if cid.strip():
        manda_telegram(cid, "🔔 TEST da Render attivo! Se leggi questo, la connessione funziona.")