from cta import charger_etat, now, date
e = charger_etat(); a = e.get("attente", {})
rec = [k for k,v in a.items() if (now()-date(v["t"])).total_seconds() < 900]
print("ETAT attente", len(a), "| nouvelles questions (15 dernières min):", len(rec))
