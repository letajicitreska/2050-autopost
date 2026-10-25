#!/usr/bin/env python3
"""Denní snapshot výkonu publikovaných reels (IG insights + YouTube statistiky) do metrics/metrics.json."""
import datetime as dt
import json
import os
import pathlib
import sys

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLAN = ROOT / "plan" / "schedule.json"
OUT = ROOT / "metrics" / "metrics.json"
IG = "https://graph.instagram.com/v21.0"
IG_METRICS = "reach,views,likes,comments,shares,saved,total_interactions,ig_reels_avg_watch_time,ig_reels_video_view_total_time"


def ig_stats(mid, token):
    out = {}
    r = requests.get(f"{IG}/{mid}", params={"fields": "like_count,comments_count,permalink,timestamp", "access_token": token}, timeout=60)
    if r.ok:
        out.update(r.json())
    i = requests.get(f"{IG}/{mid}/insights", params={"metric": IG_METRICS, "access_token": token}, timeout=60)
    if i.ok:
        for m in i.json().get("data", []):
            out[m["name"]] = m["values"][0]["value"]
    else:
        out["insights_error"] = i.text[:200]
    return out


def yt_token():
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
    r.raise_for_status()
    return r.json()["access_token"]


def yt_stats(ids, token):
    out = {}
    for k in range(0, len(ids), 50):
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "statistics", "id": ",".join(ids[k : k + 50])},
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        r.raise_for_status()
        for v in r.json().get("items", []):
            out[v["id"]] = v["statistics"]
    return out


def main():
    plan = json.loads(PLAN.read_text())
    posted = [i for i in plan["items"] if i.get("status") == "posted"]
    if not posted:
        print("Nic publikovaného.")
        return 0
    snap = {"at": dt.datetime.now(dt.timezone.utc).isoformat(), "items": {}}
    ig_token = os.environ.get("IG_ACCESS_TOKEN")
    yt_ids = [i["yt_video_id"] for i in posted if i.get("yt_video_id")]
    yts = {}
    if yt_ids and os.environ.get("YT_REFRESH_TOKEN"):
        yts = yt_stats(yt_ids, yt_token())
    for it in posted:
        e = {}
        if it.get("ig_media_id") and ig_token:
            e["ig"] = ig_stats(it["ig_media_id"], ig_token)
        if it.get("yt_video_id") in yts:
            e["yt"] = yts[it["yt_video_id"]]
        snap["items"][it["id"]] = e
    data = json.loads(OUT.read_text()) if OUT.exists() else {"snapshots": []}
    data["snapshots"].append(snap)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"Snapshot: {len(snap['items'])} položek")
    return 0


if __name__ == "__main__":
    sys.exit(main())
