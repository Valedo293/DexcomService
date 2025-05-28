def valuta_glicemia(valore, trend_raw, timestamp):
    global cronologia, alert_attivo
    trend = trend_to_arrow(trend_raw)

    cronologia.append({"valore": valore, "trend": trend, "timestamp": timestamp})
    if len(cronologia) > 10:
        cronologia.pop(0)

    print(f"[DEBUG] Glicemia attuale: {valore} | Trend: {trend} | Timestamp: {timestamp}")
    print(f"[DEBUG] Cronologia: {cronologia}")
    print(f"[DEBUG] Alert attivo: {alert_attivo}")

    # RESET se glicemia torna stabile o in salita ≥ 78
    if alert_attivo and valore >= 78 and trend in ["→", "↑", "↗", "↑↑"]:
        print("[DEBUG] Glicemia risalita, reset alert.")
        reset_alert()

    # PROVA 1 - 3 valori stabili tra 100 e 140
    if len(cronologia) >= 3:
        ultime = cronologia[-3:]
        if all(100 <= x["valore"] <= 140 and x["trend"] == "→" for x in ultime):
            return genera_alert("TEST PROVA 1", "Tre valori stabili tra 100 e 140", "test_3_stabili")

    # PROVA 2 - 2 stabili seguite da discesa tra 140-100
    if len(cronologia) >= 3:
        c1, c2, c3 = cronologia[-3:]
        if all(100 <= x["valore"] <= 140 for x in [c1, c2, c3]):
            if c1["trend"] == "→" and c2["trend"] == "→" and c3["trend"] in ["↘", "↓"]:
                return genera_alert("TEST PROVA 2", "Due stabili seguite da discesa (100-140)", "test_2_stabili_1_discesa")

    # PROVA 3 - 140 in salita
    if valore == 140 and trend in ["↗", "↑", "↑↑"]:
        return genera_alert("TEST PROVA 3", "Valore 140 in salita → occhio alla glicemia", "test_140_salita")

    # PROVA 4 - Qualsiasi valore stabile o in discesa tra 100-70
    if 70 <= valore <= 100 and trend in ["→", "↘", "↓"]:
        return genera_alert("TEST PROVA 4", "Valore tra 100 e 70 con trend stabile o discesa", "test_tra_100_70")

    # PROVA 5 - Tre glicemie in discesa tra 100 e 70
    if len(cronologia) >= 3:
        ultime = cronologia[-3:]
        if all(70 <= x["valore"] <= 100 and x["trend"] in ["↘", "↓"] for x in ultime):
            return genera_alert("TEST PROVA 5", "Tre valori in discesa tra 100 e 70", "test_3_discese_100_70")

    # PROVA 6 - Una discesa + una stabile tra 100 e 70
    if len(cronologia) >= 2:
        c1, c2 = cronologia[-2:]
        if all(70 <= x["valore"] <= 100 for x in [c1, c2]):
            if (c1["trend"] in ["↓", "↘"] and c2["trend"] == "→") or (c1["trend"] == "→" and c2["trend"] in ["↓", "↘"]):
                return genera_alert("TEST PROVA 6", "Una discesa + una stabile tra 100 e 70", "test_discesa_stabile_100_70")

    return None