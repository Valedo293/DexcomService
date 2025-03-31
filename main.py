from pydexcom import Dexcom

username = "emamaceri"
password = "Emanuele.08"

dexcom = Dexcom(username, password, ous=True)

glucose_value = dexcom.get_current_glucose_reading()

print(f"Glicemia attuale: {glucose_value.value} mg/dL")
print(f"Trend: {glucose_value.trend_description}")
print(f"Ora lettura: {glucose_value.system_time}")