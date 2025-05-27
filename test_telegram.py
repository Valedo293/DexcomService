import os
import requests
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_ids = os.getenv("TELEGRAM_CHAT_IDS", "").split(",")

for chat_id in chat_ids:
    chat_id = chat_id.strip()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": "Test notifica Telegram"}
    r = requests.post(url, json=payload)
    print(f"Chat {chat_id} → {r.status_code}")