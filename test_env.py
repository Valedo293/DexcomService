from dotenv import load_dotenv
import os

# Carica le variabili d'ambiente dal file .env
load_dotenv()

USERNAME = os.getenv("DEXCOM_USERNAME")
PASSWORD = os.getenv("DEXCOM_PASSWORD")

print(f"USERNAME: {USERNAME}")
print(f"PASSWORD: {PASSWORD}")