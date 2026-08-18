#!/usr/bin/env python3
"""
cleanup_posts.py  —  removes already-published "Marquee Games" cards from
ContentStudio, leaving the OTDIS video posts untouched.

Why: once the daily TV-listings card has published, the ContentStudio record is
dead weight; the live post on Facebook/Instagram is the copy that matters. The
OTDIS library, on the other hand, is scheduled years ahead and must never be
touched.

Safety design
-------------
1. DRY_RUN defaults to "true". Nothing is deleted until it is explicitly set to
   "false", so the first workflow run only reports.

2. A post must match ALL FIVE of these to be considered a marquee card. The two
   content types were checked against 47 live posts and separate cleanly on every
   one of them, so any single signal would do; requiring all five means a change
   to the card format causes the cleanup to stop (safe) rather than to widen
   (unsafe):
       - status == "published"
       - "On TV today" appears in the text   (13/13 marquee, 0/34 OTDIS)
       - has at least one image
       - has no video                        (OTDIS is always video)
       - has no campaign and no labels        (OTDIS is campaign "OTDIS" + a Yr label)

3. Only posts whose publish time is at least DELETE_AFTER_HOURS old are removed,
   so a post still mid-publish across platforms is never deleted underneath itself.

!! ContentStudio API gotcha !!
    Passing only date_to (or only date_from) to /posts SILENTLY IGNORES the
    filter and returns the entire workspace. Both bounds must always be sent
    together. A delete loop built on a single bound would walk the whole library.
    Every request below sends both, and every candidate's date is re-checked
    locally before it is deleted.
"""
import os
import sys
import json
import datetime
import urllib.request
import urllib.error

API = "https://api.contentstudio.io/api/v1"
KEY = os.environ.get("CONTENTSTUDIO_API_KEY", "").strip()
DRY_RUN = os.environ.get("DRY_RUN", "true").strip().lower() != "false"
DELETE_AFTER_HOURS = int(os.environ.get("DELETE_AFTER_HOURS", "24"))
# How far back to look. Anything older than this was handled by an earlier run.
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "30"))

MARQUEE_MARKER = "On TV today"


def api(method, path, body=None):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "X-API-Key": KEY, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read().decode() or "{}"
            return r.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def find_list(obj, keys=("data", "workspaces", "accounts", "result", "items")):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys:
            if isinstance(obj.get(k), list):
                return obj[k]
        for k in keys:
            if isinstance(obj.get(k), dict):
                inner = find_list(obj[k], keys)
                if inner:
                    return inner
    return []


def gid(o):
    for k in ("id", "_id"):
        if o.get(k):
            return o[k]
    return None


def parse_ts(s):
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)


def is_marquee(post):
    """All five signals must hold. See the safety notes at the top."""
    if (post.get("status") or "").lower() != "published":
        return False

    content = ((post.get("common") or {}).get("content") or {})
    text = content.get("text") or ""
    if MARQUEE_MARKER not in text:
        return False

    media = content.get("media") or {}
    images = media.get("images") or []
    video = media.get("video")
    has_video = isinstance(video, dict) and bool(video.get("url"))
    if not images or has_video:
        return False

    campaign = post.get("campaign")
    if isinstance(campaign, dict) and campaign.get("id"):
        return False
    if post.get("labels"):
        return False

    return True


def main():
    if not KEY:
        sys.exit("CONTENTSTUDIO_API_KEY not set")

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(hours=DELETE_AFTER_HOURS)

    st, ws = api("GET", "/workspaces")
    wl = find_list(ws)
    if not wl:
        sys.exit(f"Could not read workspaces (HTTP {st}).")
    wid = gid(wl[0])
    print(f"workspace: {wid} ({wl[0].get('name')})", flush=True)
    print(f"mode: {'DRY RUN - nothing will be deleted' if DRY_RUN else 'LIVE - posts will be deleted'}")
    print(f"deleting published marquee cards older than {DELETE_AFTER_HOURS}h "
          f"(before {cutoff:%Y-%m-%d %H:%M} UTC)\n", flush=True)

    # BOTH bounds, always -- see the gotcha note at the top of this file.
    date_from = (now - datetime.timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    date_to = now.strftime("%Y-%m-%d")

    candidates, page = [], 1
    while True:
        st, res = api("GET", f"/workspaces/{wid}/posts"
                             f"?date_from={date_from}&date_to={date_to}"
                             f"&per_page=50&page={page}")
        if st != 200:
            sys.exit(f"Could not list posts (HTTP {st}): {json.dumps(res)[:300]}")
        batch = res.get("data") or []
        if not batch:
            break
        for p in batch:
            if not is_marquee(p):
                continue
            when = parse_ts(((p.get("scheduling") or {}).get("execute_time")))
            # Re-check the date locally; never trust the server-side filter alone.
            if when is None or when > cutoff:
                continue
            candidates.append((gid(p), when, (p["common"]["content"]["text"].splitlines() or [""])[0]))
        if page >= (res.get("last_page") or 1):
            break
        page += 1

    if not candidates:
        print("Nothing to clean up.")
        return

    print(f"{len(candidates)} marquee card(s) eligible:\n")
    deleted = failed = 0
    for pid, when, first_line in sorted(candidates, key=lambda c: c[1]):
        stamp = f"{when:%Y-%m-%d %H:%M}"
        if DRY_RUN:
            print(f"  would delete  {stamp}  {pid}  {first_line[:60]}")
            continue
        st, res = api("DELETE", f"/workspaces/{wid}/posts/{pid}")
        if st in (200, 201, 204):
            deleted += 1
            print(f"  deleted       {stamp}  {pid}")
        else:
            failed += 1
            print(f"  FAILED ({st}) {stamp}  {pid}  {json.dumps(res)[:160]}")

    print()
    if DRY_RUN:
        print(f"DRY RUN complete - {len(candidates)} would have been deleted. "
              f"Set DRY_RUN=false to act.")
    else:
        print(f"deleted {deleted}, failed {failed}")
        if failed:
            sys.exit(1)


if __name__ == "__main__":
    main()
