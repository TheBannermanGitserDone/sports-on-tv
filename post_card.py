#!/usr/bin/env python3
"""
post_card.py  —  posts the daily marquee card to ContentStudio via its API.

Reads caption.txt (from render_card.py) and IMAGE_URL (env), discovers the
workspace + connected accounts automatically, drops Twitter/X, and creates the
post. PUBLISH_TYPE env controls draft vs live ("draft" while we verify, then
"published" once it looks right). Prints raw API responses so the first run
tells us the exact JSON shapes.
"""
import os
import sys
import json
import urllib.request
import urllib.error

API = "https://api.contentstudio.io/api/v1"
KEY = os.environ.get("CONTENTSTUDIO_API_KEY", "").strip()
IMAGE_URL = os.environ.get("IMAGE_URL", "").strip()
PUBLISH_TYPE = os.environ.get("PUBLISH_TYPE", "draft").strip()
EXCLUDE = ("twitter", "x")   # never post to these platforms


def api(method, path, body=None):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "X-API-Key": KEY, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def find_list(obj, keys=("data", "workspaces", "accounts", "result", "items", "channels")):
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
    for k in ("id", "_id", "account_id", "uuid", "channel_id"):
        if o.get(k):
            return o[k]
    return None


def platform(o):
    for k in ("platform", "type", "channel_type", "account_type", "provider", "network", "platform_type"):
        v = o.get(k)
        if isinstance(v, str):
            return v.lower()
    return ""


def label(o):
    for k in ("name", "platform_name", "username", "title", "display_name"):
        if o.get(k):
            return str(o[k])
    return gid(o) or "?"


def main():
    if not KEY:
        sys.exit("CONTENTSTUDIO_API_KEY not set")
    if not IMAGE_URL:
        sys.exit("IMAGE_URL not set")
    try:
        with open("caption.txt", encoding="utf-8") as f:
            text = f.read().strip()
    except FileNotFoundError:
        sys.exit("caption.txt missing (run render_card.py first)")

    # 1) workspace
    st, ws = api("GET", "/workspaces")
    print("GET /workspaces ->", st, json.dumps(ws)[:800], flush=True)
    wl = find_list(ws)
    if not wl:
        sys.exit("Could not read workspaces from response above.")
    wid = gid(wl[0])
    print("using workspace:", wid, label(wl[0]), flush=True)

    # 2) accounts (drop Twitter/X)
    st, acc = api("GET", f"/workspaces/{wid}/accounts")
    print(f"GET /workspaces/{wid}/accounts ->", st, json.dumps(acc)[:1200], flush=True)
    al = find_list(acc)
    ids = []
    for a in al:
        plat = platform(a)
        aid = gid(a)
        if not aid:
            continue
        if any(x in plat for x in EXCLUDE):
            print("  skip (excluded):", label(a), plat, flush=True)
            continue
        print("  will post to:", label(a), plat, flush=True)
        ids.append(aid)
    if not ids:
        sys.exit("No eligible accounts found (check the accounts response above).")

    # 3) create the post
    payload = {
        "content": {"text": text, "media": {"images": [IMAGE_URL]}},
        "accounts": ids,
        "scheduling": {"publish_type": PUBLISH_TYPE},
    }
    st, res = api("POST", f"/workspaces/{wid}/posts", payload)
    print("POST /posts ->", st, json.dumps(res)[:1200], flush=True)
    if st not in (200, 201):
        sys.exit(f"ContentStudio rejected the post ({st}). See response above.")
    print(f"OK — post created ({PUBLISH_TYPE}).", flush=True)


if __name__ == "__main__":
    main()
