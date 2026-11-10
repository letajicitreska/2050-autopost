"""Připomínky na mobil (ntfy) k ručním krokům po zveřejnění, např. odkaz do prvního komentáře
LinkedIn postu. Položky v plan/reminders.json: id, at (ISO, UTC), title, message, click (volitelně),
sent (nastaví skript). Posílá se přes tentýž ntfy kanál (secret NTFY_TOPIC) jako u reels."""
import json, os, sys, datetime as dt
import requests

PATH = "plan/reminders.json"
topic = os.environ.get("NTFY_TOPIC")
now = dt.datetime.now(dt.timezone.utc)
data = json.load(open(PATH, encoding="utf-8"))
changed = False
for it in data.get("items", []):
    if it.get("sent"):
        continue
    at = dt.datetime.fromisoformat(it["at"].replace("Z", "+00:00"))
    if at > now:
        continue
    if not topic:
        print("NTFY_TOPIC chybí"); sys.exit(1)
    h = {"Title": it["title"], "Priority": "high", "Tags": "speech_balloon"}
    if it.get("click"):
        h["Click"] = it["click"]
    r = requests.post(f"https://ntfy.sh/{topic}", data=it["message"].encode("utf-8"), headers=h, timeout=30)
    if r.ok:
        it["sent"] = now.isoformat(timespec="seconds")
        changed = True
        print("odesláno:", it["id"])
    else:
        print("ntfy selhalo:", it["id"], r.status_code)
if changed:
    json.dump(data, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(PATH, "a").write("\n")
