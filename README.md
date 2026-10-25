# 2050-autopost

Automatické publikování reels z Podcastu 2050 na Instagram (@2050_podcast) a YouTube Shorts.

- `plan/schedule.json` – fronta. Každá položka: `id`, `file` (název v `queue/`), `publish_at` (ISO, UTC nebo s časovou zónou), `caption_ig`, `title_yt`, `desc_yt`, `tags_yt`, `hashtags`, `status` (`draft` → `approved` → `posted`).
- `queue/` – videa čekající na publikaci (po publikaci se smažou).
- `scripts/post.py` – publikuje schválené a splatné položky (spouští hodinově `post.yml`).
- `scripts/metrics.py` – denní snapshot výkonu do `metrics/metrics.json` (`metrics.yml`).

Secrets (Settings → Secrets and variables → Actions): `IG_ACCESS_TOKEN`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.

Test bez odeslání: Actions → post-reels → Run workflow → `dry_run = 1`.
