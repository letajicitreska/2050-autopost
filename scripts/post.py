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
def ig_publish(path, caption, token, cover_url=None):
    size = path.stat().st_size
    payload = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption,
        "share_to_feed": "true",
        "access_token": token,
    }
    if cover_url:
        payload["cover_url"] = cover_url
    r = requests.post(f"{IG}/me/media", data=payload, timeout=60)
    if not r.ok:
        raise RuntimeError(f"IG container: {r.status_code} {r.text}")
    j = r.json()
    cid, uri = j["id"], j["uri"]
    with open(path, "rb") as f:
        u = requests.post(
            uri,
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


def yt_upload(path, title, description, tags):
    token = yt_access_token()
    size = path.stat().st_size
    meta = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags,
            "categoryId": "27",
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
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
    only = os.environ.get("ONLY_ID")
    todo = [i for i in plan["items"] if due(i, now) and (not only or i["id"] == only)]
    log(f"K publikování: {len(todo)}")
    for it in todo:
        path = ROOT / "queue" / it["file"]
        if not path.exists():
            log(f"[{it['id']}] chybí soubor {path.name}, přeskakuji")
            it["error"] = "missing file"
            continue
        caption = it["caption_ig"] + ("\n\n" + " ".join(it.get("hashtags", [])) if it.get("hashtags") else "")
        ytdesc = it.get("desc_yt", "") + ("\n\n" + " ".join(it.get("hashtags", [])) if it.get("hashtags") else "")
        if "#Shorts" not in ytdesc:
            ytdesc += " #Shorts"
        try:
            if not it.get("ig_media_id"):
                if DRY:
                    log(f"[{it['id']}] DRY IG: {path.name}\n{caption}")
                else:
                    it["ig_media_id"] = ig_publish(path, caption, os.environ["IG_ACCESS_TOKEN"], it.get("cover_url"))
                    log(f"[{it['id']}] IG OK {it['ig_media_id']}")
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
        if not DRY:
            PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
