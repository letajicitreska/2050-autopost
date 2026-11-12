#!/usr/bin/env python3
"""Autopost reels na Instagram (@2050_podcast) a YouTube Shorts (kanál 2050).

Čte plan/schedule.json, publikuje položky se status "approved", jejichž publish_at už nastalo.
Stav (ig_media_id, yt_video_id, status) zapisuje zpět do plan/schedule.json, takže se nic
nepublikuje dvakrát ani při částečném selhání.

Env: IG_ACCESS_TOKEN, YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
Volitelně: DRY_RUN=1 (nic neodesílá), ONLY_ID=<id položky>.
"""
import datetime as dt
import json
import os
import pathlib
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLAN = ROOT / "plan" / "schedule.json"
IG = "https://graph.instagram.com/v21.0"
DRY = os.environ.get("DRY_RUN") == "1"


def log(*a):
    print(*a, flush=True)


# ---------- Instagram ----------
def ig_publish(path, caption, token, cover_url=None, collaborators=None):
    """Instagram Login API bere video z veřejné URL (video_url). Pokud není PUBLIC_BASE, zkusí resumable upload."""
    base = os.environ.get("PUBLIC_BASE", "").rstrip("/")
    payload = {
        "media_type": "REELS",
        "caption": caption,
        "share_to_feed": "true",
        "access_token": token,
    }
    if base:
        payload["video_url"] = f"{base}/queue/{path.name}"
    else:
        payload["upload_type"] = "resumable"
    if cover_url:
        payload["cover_url"] = cover_url
    if collaborators:
        # max 3 účty; collab pozvánka čeká na přijetí druhou stranou
        payload["collaborators"] = json.dumps([c.lstrip("@") for c in collaborators][:3])
    r = requests.post(f"{IG}/me/media", data=payload, timeout=60)
    if not r.ok and collaborators:
        # špatný/neveřejný účet nesmí shodit publikaci: zkusit bez collabu
        first_err = f"{r.status_code} {r.text[:300]}"
        log(f"IG container s collaborators selhal ({first_err}), zkouším bez nich")
        payload.pop("collaborators", None)
        r = requests.post(f"{IG}/me/media", data=payload, timeout=60)
        if r.ok:
            ig_publish.collab_error = first_err
    if not r.ok:
        raise RuntimeError(f"IG container: {r.status_code} {r.text}")
    j = r.json()
    cid = j["id"]
    if not base:
        size = path.stat().st_size
        with open(path, "rb") as f:
            u = requests.post(
                j["uri"],
                headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)},
                data=f,
                timeout=1800,
            )
        if not u.ok:
            raise RuntimeError(f"IG upload: {u.status_code} {u.text}")
    for _ in range(90):
        s = requests.get(
            f"{IG}/{cid}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=60,
        ).json()
        code = s.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"IG zpracování: {s}")
        time.sleep(10)
    else:
        raise RuntimeError("IG zpracování trvá příliš dlouho")
    p = requests.post(
        f"{IG}/me/media_publish",
        data={"creation_id": cid, "access_token": token},
        timeout=120,
    )
    if not p.ok:
        raise RuntimeError(f"IG publish: {p.status_code} {p.text}")
    return p.json()["id"]


def ntfy(title, msg, click=None, tags="warning"):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic or DRY:
        return
    ntfy_send(topic, title, msg, click=click, tags=tags)


def ntfy_send(topic, title, msg, click=None, tags="warning"):
    """Odeslání přes JSON: diakritika v titulku nesmí do HTTP hlavičky
    (requests ji neumí zakódovat a požadavek vůbec neodejde)."""
    body = {"topic": topic, "title": title, "message": msg, "priority": 4, "tags": [tags]}
    if click:
        body["click"] = click
    try:
        r = requests.post("https://ntfy.sh/", json=body, timeout=30)
        if not r.ok:
            log(f"ntfy selhalo: HTTP {r.status_code}")
    except Exception as e:
        log(f"ntfy selhalo: {e}")


def notify_story(item, media_id, token):
    """Push na mobil (ntfy) hned po publikaci reelu: připomínka ručního sdílení do story."""
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return
    link = "https://www.instagram.com/2050_podcast/"
    try:
        j = requests.get(f"{IG}/{media_id}", params={"fields": "permalink", "access_token": token}, timeout=30).json()
        link = j.get("permalink") or link
    except Exception:
        pass
    title = item.get("title_yt", item["id"]).split(" | ")[0]
    ntfy_send(topic, "Reel je na IG", f"Je venku: {title}. Sdílej ho do story.", click=link, tags="movie_camera")


# ---------- YouTube ----------
def yt_access_token():
    r = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": os.environ["YT_CLIENT_ID"],
            "client_secret": os.environ["YT_CLIENT_SECRET"],
            "refresh_token": os.environ["YT_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        },
        timeout=60,
    )
    if not r.ok:
        raise RuntimeError(f"YT token: {r.status_code} {r.text}")
    return r.json()["access_token"]


def yt_status(publish_at=None, public=False):
    """publish_at (datetime UTC) = soukromé video, YouTube ho samo zveřejní v ten čas."""
    if public:
        return {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    st = {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
    if publish_at:
        st["publishAt"] = publish_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return st


def yt_upload(path, title, description, tags, publish_at=None):
    token = yt_access_token()
    size = path.stat().st_size
    meta = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags,
            "categoryId": "27",
        },
        "status": yt_status(publish_at) if publish_at else yt_status(public=True),
    }
    init = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(size),
            "X-Upload-Content-Type": "video/mp4",
        },
        data=json.dumps(meta),
        timeout=60,
    )
    if not init.ok:
        raise RuntimeError(f"YT init: {init.status_code} {init.text}")
    loc = init.headers["Location"]
    with open(path, "rb") as f:
        put = requests.put(loc, headers={"Content-Type": "video/mp4"}, data=f, timeout=1800)
    if not put.ok:
        raise RuntimeError(f"YT upload: {put.status_code} {put.text}")
    return put.json()["id"]


def yt_thumbnail(video_id, cover_path):
    """Miniatura (JPEG/PNG do 2 MB). Selhání není kritické."""
    token = yt_access_token()
    ctype = "image/png" if cover_path.suffix.lower() == ".png" else "image/jpeg"
    with open(cover_path, "rb") as f:
        r = requests.post(
            f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={video_id}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": ctype},
            data=f,
            timeout=120,
        )
    if not r.ok:
        raise RuntimeError(f"YT thumbnail: {r.status_code} {r.text[:200]}")


def yt_update_status(video_id, status):
    token = yt_access_token()
    r = requests.put(
        "https://www.googleapis.com/youtube/v3/videos?part=status",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
        data=json.dumps({"id": video_id, "status": status}),
        timeout=60,
    )
    if not r.ok:
        raise RuntimeError(f"YT update: {r.status_code} {r.text[:300]}")


# ---------- YouTube dopředu (naplánované zveřejnění) ----------
# GitHub cron chodí o hodiny později, YouTube ale umí zveřejnit video samo v daný čas.
# Short se proto nahraje dopředu jako soukromý s publishAt (pole yt_prestaged=true,
# yt_publish_at = čas, na který je u YouTube nastavený). Když se čas položky změní nebo
# položka přestane být approved, čas u YouTube se srovná (parked = soukromé bez času).
YT_AHEAD = dt.timedelta(hours=36)
YT_MIN_LEAD = dt.timedelta(minutes=20)


def pub_time(item):
    t = dt.datetime.fromisoformat(item["publish_at"])
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def yt_desc(it):
    d = it.get("desc_yt", "") + ("\n\n" + " ".join(it.get("hashtags", [])) if it.get("hashtags") else "")
    return d if "#Shorts" in d else d + " #Shorts"


def yt_prestage(plan, now):
    """Vrátí True, pokud se něco změnilo (pak je potřeba stav hned uložit a pushnout)."""
    changed = False
    for it in plan["items"]:
        if it.get("status") == "posted":
            continue
        try:
            t = pub_time(it)
            if it.get("yt_prestaged") and it.get("yt_video_id"):
                if it.get("status") != "approved":
                    if it.get("yt_publish_at"):
                        if DRY:
                            log(f"[{it['id']}] DRY YT: zrušit naplánování")
                            continue
                        yt_update_status(it["yt_video_id"], yt_status())
                        it["yt_publish_at"] = None
                        changed = True
                        log(f"[{it['id']}] YT: naplánování zrušeno (status {it.get('status')})")
                elif it.get("yt_publish_at") != it["publish_at"]:
                    public_now = t <= now + dt.timedelta(minutes=2)
                    if DRY:
                        log(f"[{it['id']}] DRY YT: přeplánovat na {it['publish_at']}")
                        continue
                    yt_update_status(it["yt_video_id"], yt_status(None if public_now else t, public=public_now))
                    it["yt_publish_at"] = it["publish_at"]
                    changed = True
                    log(f"[{it['id']}] YT: " + ("zveřejněno hned" if public_now else f"přeplánováno na {it['publish_at']}"))
                continue
            if it.get("status") != "approved" or it.get("yt_video_id"):
                continue
            if not (now + YT_MIN_LEAD < t <= now + YT_AHEAD):
                continue
            path = ROOT / "queue" / it["file"]
            if not path.exists():
                continue  # chybějící soubor ohlásí hlavní smyčka v čase publikace
            if DRY:
                log(f"[{it['id']}] DRY YT dopředu na {it['publish_at']}: {it['title_yt']}")
                continue
            it["yt_video_id"] = yt_upload(path, it["title_yt"], yt_desc(it), it.get("tags_yt", []), publish_at=t)
            it["yt_prestaged"] = True
            it["yt_publish_at"] = it["publish_at"]
            changed = True
            log(f"[{it['id']}] YT naplánováno na {it['publish_at']}: {it['yt_video_id']}")
            cover = ROOT / "queue" / it["cover_file"] if it.get("cover_file") else None
            if cover and cover.exists():
                try:
                    yt_thumbnail(it["yt_video_id"], cover)
                except Exception as e:
                    log(f"[{it['id']}] YT miniatura selhala: {e}")
        except Exception as e:  # nevadí: hlavní smyčka v čase publikace nahraje Short veřejně
            log(f"[{it['id']}] YT dopředu selhalo: {e}")
    return changed


def save_and_push(plan, msg):
    """Uloží frontu a hned ji pushne (aby se po případném pádu během čekání nic nenahrálo dvakrát)."""
    import subprocess
    PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    g = ["git", "-c", "user.name=2050-autopost", "-c", "user.email=autopost@users.noreply.github.com"]
    subprocess.run(g + ["add", "plan"], cwd=ROOT, check=True)
    subprocess.run(g + ["commit", "-q", "-m", msg], cwd=ROOT, check=False)
    for _ in range(3):
        subprocess.run(g + ["pull", "-q", "--rebase", "origin", "main"], cwd=ROOT, check=False)
        if subprocess.run(g + ["push", "-q"], cwd=ROOT).returncode == 0:
            return True
        time.sleep(5)
    return False


# ---------- hlavní smyčka ----------
def due(item, now):
    if item.get("status") != "approved":
        return False
    t = dt.datetime.fromisoformat(item["publish_at"])
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t <= now


def main():
    plan = json.loads(PLAN.read_text())
    now = dt.datetime.now(dt.timezone.utc)
    # GitHub cron chodí se zpožděním 30 min až hodiny (plánované běhy reálně jen každé
    # 3–8 h). Běh, který naběhne do LOOKAHEAD_MIN (300 = 5 h) před časem publikace,
    # počká a zveřejní IG přesně. YouTube je naplánované dopředu (yt_prestage).
    only = os.environ.get("ONLY_ID")
    saved = True
    if not only and yt_prestage(plan, now):
        saved = save_and_push(plan, "autopost: YouTube naplánováno")
        if not saved:
            log("Push stavu selhal, dnes nečekám (stav uloží závěrečný krok workflow)")
    look = int(os.environ.get("LOOKAHEAD_MIN") or 0)
    if look and not DRY and saved:
        upcoming = []
        for i in plan["items"]:
            if i.get("status") != "approved":
                continue
            t = dt.datetime.fromisoformat(i["publish_at"])
            t = t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
            if now < t <= now + dt.timedelta(minutes=look):
                upcoming.append(t)
        if upcoming:
            wait = (min(upcoming) - now).total_seconds() + 5
            log(f"Čekám {int(wait)} s do času publikace {min(upcoming).isoformat()}")
            time.sleep(wait)
            # během čekání se fronta mohla změnit: načíst aktuální stav z main
            import subprocess
            subprocess.run(["git", "pull", "-q", "--rebase", "origin", "main"], cwd=ROOT, check=False)
            plan = json.loads(PLAN.read_text())
            now = dt.datetime.now(dt.timezone.utc)
    todo = [i for i in plan["items"] if due(i, now) and (not only or i["id"] == only)]
    log(f"K publikování: {len(todo)}")
    for it in todo:
        path = ROOT / "queue" / it["file"]
        if not path.exists():
            log(f"[{it['id']}] chybí soubor {path.name}, přeskakuji")
            it["error"] = "missing file"
            ntfy("Reel nevyšel", f"{it['id']}: chybí video ve frontě")
            continue
        caption = it["caption_ig"] + ("\n\n" + " ".join(it.get("hashtags", [])) if it.get("hashtags") else "")
        ytdesc = yt_desc(it)
        try:
            if not it.get("ig_media_id"):
                if DRY:
                    log(f"[{it['id']}] DRY IG: {path.name} collab={it.get('collaborators', os.environ.get('IG_DEFAULT_COLLABORATORS', ''))}\n{caption}")
                else:
                    cover_url = it.get("cover_url") or (f"{os.environ['PUBLIC_BASE'].rstrip('/')}/queue/{it['cover_file']}" if os.environ.get("PUBLIC_BASE") and it.get("cover_file") else None)
                    # hosté z položky + výchozí účty (např. Fakta o klimatu), bez duplicit, max 3
                    collabs = []
                    for c in list(it.get("collaborators", [])) + (os.environ.get("IG_DEFAULT_COLLABORATORS") or "faktaoklimatu").split(","):
                        c = c.strip().lstrip("@")
                        if c and c not in collabs:
                            collabs.append(c)
                    collabs = collabs[:3]
                    ig_publish.collab_error = None
                    it["ig_media_id"] = ig_publish(path, caption, os.environ["IG_ACCESS_TOKEN"], cover_url, collabs)
                    if collabs and not ig_publish.collab_error:
                        it["ig_collaborators"] = collabs
                    elif ig_publish.collab_error:
                        it["collab_error"] = f"publikováno bez collabu: {ig_publish.collab_error}"
                        ntfy("Reel vyšel bez collabu", f"{it['id']}: Instagram odmítl collab ({', '.join(collabs)})", tags="information_source")
                    log(f"[{it['id']}] IG OK {it['ig_media_id']}")
                    notify_story(it, it["ig_media_id"], os.environ["IG_ACCESS_TOKEN"])
            if not it.get("yt_video_id"):
                if DRY:
                    log(f"[{it['id']}] DRY YT: {it['title_yt']}")
                else:
                    it["yt_video_id"] = yt_upload(path, it["title_yt"], ytdesc, it.get("tags_yt", []))
                    log(f"[{it['id']}] YT OK {it['yt_video_id']}")
                    cover = ROOT / "queue" / it["cover_file"] if it.get("cover_file") else None
                    if cover and cover.exists():
                        try:
                            yt_thumbnail(it["yt_video_id"], cover)
                            log(f"[{it['id']}] YT miniatura OK")
                        except Exception as e:
                            log(f"[{it['id']}] YT miniatura selhala: {e}")
            if not DRY and it.get("yt_prestaged") and it.get("yt_publish_at") != it["publish_at"]:
                # Short je u YouTube naplánovaný na jiný (zrušený nebo starý) čas: zveřejnit hned
                yt_update_status(it["yt_video_id"], yt_status(public=True))
                it["yt_publish_at"] = it["publish_at"]
                log(f"[{it['id']}] YT zveřejněno hned")
            if not DRY and it.get("ig_media_id") and it.get("yt_video_id"):
                it["status"] = "posted"
                it["posted_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
                it.pop("error", None)
                path.unlink()
                if it.get("cover_file") and (ROOT / "queue" / it["cover_file"]).exists():
                    (ROOT / "queue" / it["cover_file"]).unlink()
        except Exception as e:  # nezastaví ostatní položky
            it["error"] = str(e)[:500]
            log(f"[{it['id']}] CHYBA: {e}")
            ntfy("Reel nevyšel", f"{it['id']}: {str(e)[:180]}")
        if not DRY:
            PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
