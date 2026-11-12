"""Připomínky na mobil (ntfy) k ručním krokům po zveřejnění, např. odkaz do prvního komentáře
LinkedIn postu. Položky v plan/reminders.json: id, at (ISO, UTC), title, message, click (volitelně),
sent (nastaví skript). Posílá se přes tentýž ntfy kanál (secret NTFY_TOPIC) jako u reels.

Přesný čas hlídá ntfy, ne GitHub: GitHub cron chodí i o hodiny později, proto se připomínka
předá ntfy dopředu s polem "delay" (Unix čas) a ntfy ji doručí přesně v `at`. ntfy.sh drží
naplánované zprávy nejvýš 3 dny dopředu, vzdálenější připomínky se předají při pozdějším běhu.
Push změny plan/reminders.json spouští běh hned, takže nová připomínka se předá okamžitě.
Jednou předanou připomínku nejde přeplánovat: při změně času založ novou položku s novým id."""
import json, sys, datetime as dt
import os
import requests

PATH = "plan/reminders.json"
HANDOFF = dt.timedelta(hours=70)   # rezerva pod limitem ntfy.sh (3 dny)
topic = os.environ.get("NTFY_TOPIC")
now = dt.datetime.now(dt.timezone.utc)
data = json.load(open(PATH, encoding="utf-8"))
changed = False
failed = False
for it in data.get("items", []):
    if it.get("sent"):
        continue
    at = dt.datetime.fromisoformat(it["at"].replace("Z", "+00:00"))
    if at > now + HANDOFF:
        continue
    if not topic:
        print("NTFY_TOPIC chybí"); sys.exit(1)
    body = {"topic": topic, "title": it["title"], "message": it["message"],
            "priority": 4, "tags": ["speech_balloon"]}
    if it.get("click"):
        body["click"] = it["click"]
    scheduled = at > now + dt.timedelta(seconds=30)
    if scheduled:
        body["delay"] = str(int(at.timestamp()))
    r = requests.post("https://ntfy.sh/", json=body, timeout=30)  # odpověď obsahuje téma, nevypisovat
    if r.ok:
        it["sent"] = now.isoformat(timespec="seconds")
        if scheduled:
            it["delivery"] = "naplánováno v ntfy na " + at.isoformat(timespec="minutes")
        changed = True
        print("předáno:" if scheduled else "odesláno:", it["id"])
    else:
        failed = True
        print("ntfy selhalo:", it["id"], r.status_code)
if changed:
    json.dump(data, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(PATH, "a").write("\n")
if failed:
    sys.exit(1)  # běh zčervená a GitHub pošle e-mail; stav úspěšně předaných se uloží (if: always)
