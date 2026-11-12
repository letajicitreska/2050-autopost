#!/usr/bin/env python3
"""Měsíčně prodlouží platnost IG tokenu o dalších 60 dní (graph.instagram.com/refresh_access_token).
Když Instagram vrátí JINÝ token než je v secretu, zapíše ho do souboru NEW_TOKEN_FILE
a další krok workflow ho uloží do secretu IG_ACCESS_TOKEN (přes GH_PAT).
Token se nikdy nevypisuje: v logu ho maskuje ::add-mask::."""
import os, sys, requests

tok = os.environ["IG_ACCESS_TOKEN"]
r = requests.get(
    "https://graph.instagram.com/refresh_access_token",
    params={"grant_type": "ig_refresh_token", "access_token": tok},
    timeout=60,
)
if not r.ok:
    print("Obnova tokenu selhala:", r.status_code, r.text[:300])
    sys.exit(1)
j = r.json()
new = j.get("access_token") or ""
days = int(j.get("expires_in", 0)) // 86400
if new:
    print(f"::add-mask::{new}")
print(f"Token prodloužen, platí ještě ~{days} dní.")
out = os.environ.get("NEW_TOKEN_FILE")
if new and new != tok:
    print("Instagram vrátil nový token, uloží se do secretu IG_ACCESS_TOKEN.")
    if not out:
        sys.exit(1)
    with open(out, "w") as f:
        f.write(new)
