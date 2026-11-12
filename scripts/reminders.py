"""Připomínky na mobil (ntfy) k ručním krokům po zveřejnění, např. odkaz do prvního komentáře
LinkedIn postu. Položky v plan/reminders.json: id, at (ISO, UTC), title, message, click (volitelně),
sent (nastaví skript). Posílá se přes tentýž ntfy kanál (secret NTFY_TOPIC) jako u reels.

GitHub cron chodí i o hodiny později (reálně běh jednou za 3–8 h), proto běh, který naběhne
do WINDOW před časem připomínky, počká a pošle ji přesně. Posílá se vždy hned (okamžitá zpráva):
ntfy zprávy s odkladem ("delay") se na iPhonu jako upozornění neukážou, jen v appce
(ověřeno 12. 11. 2026). Po každém odeslání se stav hned pushne, aby nic nešlo dvakrát."""
import json, os, subprocess, sys, time, datetime as dt
import requests

PATH = "plan/reminders.json"
WINDOW = dt.timedelta(minutes=int(os.environ.get("WAIT_MIN") or 0))  # 0 = nečekat (ruční/push běh)
START = dt.datetime.now(dt.timezone.utc)
topic = os.environ.get("NTFY_TOPIC")
GIT = ["git", "-c", "user.name=2050-autopost", "-c", "user.email=autopost@users.noreply.github.com"]


def at_of(it):
    return dt.datetime.fromisoformat(it["at"].replace("Z", "+00:00"))


def load():
    subprocess.run(GIT + ["pull", "-q", "--rebase", "origin", "main"], check=False)
    return json.load(open(PATH, encoding="utf-8"))


def save_push(data):
    json.dump(data, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(PATH, "a").write("\n")
    subprocess.run(GIT + ["add", PATH], check=True)
    subprocess.run(GIT + ["commit", "-q", "-m", "reminders: odesláno"], check=False)
    for _ in range(3):
        subprocess.run(GIT + ["pull", "-q", "--rebase", "origin", "main"], check=False)
        if subprocess.run(GIT + ["push", "-q"]).returncode == 0:
            return
        time.sleep(5)
    print("Push stavu selhal"); sys.exit(1)  # radši skončit, než riskovat dvojí odeslání


failed = False
data = json.load(open(PATH, encoding="utf-8"))
while True:
    now = dt.datetime.now(dt.timezone.utc)
    sent_any = False
    for it in data.get("items", []):
        if it.get("sent") or at_of(it) > now + dt.timedelta(seconds=20):
            continue
        if not topic:
            print("NTFY_TOPIC chybí"); sys.exit(1)
        body = {"topic": topic, "title": it["title"], "message": it["message"],
                "priority": 4, "tags": ["speech_balloon"]}
        if it.get("click"):
            body["click"] = it["click"]
        r = requests.post("https://ntfy.sh/", json=body, timeout=30)  # odpověď obsahuje téma, nevypisovat
        if r.ok:
            it["sent"] = now.isoformat(timespec="seconds")
            sent_any = True
            print("odesláno:", it["id"])
        else:
            failed = True
            print("ntfy selhalo:", it["id"], r.status_code)
    if sent_any:
        save_push(data)
    upcoming = [at_of(i) for i in data.get("items", []) if not i.get("sent") and at_of(i) > now]
    if not upcoming or min(upcoming) > START + WINDOW:
        break
    wait = (min(upcoming) - now).total_seconds()
    print(f"Čekám {int(wait)} s na další připomínku")
    time.sleep(max(0, wait))
    data = load()  # během čekání se seznam mohl změnit
if failed:
    sys.exit(1)
