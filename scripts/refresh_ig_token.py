#!/usr/bin/env python3
"""Měsíčně prodlouží platnost IG tokenu o dalších 60 dní (graph.instagram.com/refresh_access_token).
Pokud Instagram vrátí JINÝ token než je v secretu, běh záměrně selže (GitHub pošle e-mail) a je třeba secret ručně aktualizovat."""
import os, sys, requests

tok = os.environ["IG_ACCESS_TOKEN"]
r = requests.get(
    "https://graph.instagram.com/refresh_access_token",
    params={"grant_type": "ig_refresh_token", "access_token": tok},
    timeout=60,
)
if not r.ok:
    print("Obnova tokenu selhala:", r.status_code, r.text)
    sys.exit(1)
j = r.json()
days = int(j.get("expires_in", 0)) // 86400
print(f"Token prodloužen, platí ještě ~{days} dní.")
if j.get("access_token") != tok:
    print("POZOR: Instagram vrátil nový token. Aktualizuj secret IG_ACCESS_TOKEN (nový token je v dashboardu Meta).")
    sys.exit(1)
