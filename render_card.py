#!/usr/bin/env python3
"""
render_card.py  —  builds the daily "Marquee Games" social image for The Bannerman.

Reuses the game feeds from generate_sports_tv.py, picks the day's marquee games
(national / major-network games first), renders a 1080x1080 branded card with
Playwright, and writes:
    social-card.png   the image (committed to the repo so ContentStudio can fetch it)
    caption.txt       the post caption

Run from the repo root:  python render_card.py
"""
import os
import sys
import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_sports_tv import LEAGUES, load_games, fmt_time, PT, ET  # noqa: E402

PAGE_URL = "https://thebannerman.ca/pages/sports-on-tv-today"
LOGO_URL = "https://thebannerman.ca/cdn/shop/files/Logo_Watermark.png?width=300"

# networks that make a game "marquee" (national US windows + major Canadian nets)
_US_MAJOR = ["espn", "fox", "fs1", "tbs", "tnt", " abc", "nbc", "cbs", "mlb network",
             "nfl network", "nba tv", "prime video", "amazon", "apple tv", "peacock",
             "netflix", "max", "tru tv", "trutv"]
_CA_MAJOR = ["sportsnet", "tsn", "tva", "cbc", "sn now", "rds"]

# "SportsNet" is a Canadian brand (Rogers), but several US regional networks are
# also named "SportsNet <city>" (Pittsburgh, LA, New York/SNY). Those are US, not
# Canadian, so exclude them from the CA match below.
_US_SPORTSNET = ["sportsnet pittsburgh", "sportsnet la", "sportsnet l.a.",
                 "sportsnet new york", "sportsnet ny", "attsn", "at&t sportsnet"]


def _is_ca(name):
    """True only for genuine Canadian networks (guards against US SportsNet RSNs)."""
    n = (name or "").lower()
    if any(us in n for us in _US_SPORTSNET):
        return False
    return any(k in n for k in _CA_MAJOR)


def _has(nets, keys):
    j = " ".join(nets or []).lower()
    return any(k in j for k in keys)


def _score(g):
    s = 0
    if _has(g.get("us"), _US_MAJOR):
        s += 3           # national US window
    if any(_is_ca(n) for n in (g.get("ca") or [])):
        s += 2           # notable Canadian carrier
    return s


def _natl_net(g):
    """Pick the best single network label + market tag + style for the chip.
    National US window first, then a notable Canadian carrier, then any US/CA."""
    for n in (g.get("us") or []):
        if any(k in n.lower() for k in _US_MAJOR):
            return ("natl", "US", n + " · National")
    for n in (g.get("ca") or []):
        if _is_ca(n):
            return ("ca", "CA", n)
    # any US listing (including US "SportsNet <city>" regionals) shows as US
    for n in (g.get("us") or []):
        return ("us", "US", n)
    # last resort: something only in the CA list. If it's actually a US regional
    # (e.g. "SportsNet Pittsburgh"), tag it US; otherwise CA.
    for n in (g.get("ca") or []):
        us_rsn = any(x in n.lower() for x in _US_SPORTSNET)
        return ("us", "US", n) if us_rsn else ("ca", "CA", n)
    return ("us", "", "Check listings")


# Shorten "Los Angeles Dodgers" -> "Dodgers", "Toronto Blue Jays" -> "Blue Jays".
_TWO_WORD = {"sox", "jays", "leafs", "jackets", "knights", "blazers", "wings"}


def nick(full):
    parts = (full or "").split()
    if not parts:
        return full or ""
    if len(parts) >= 2 and parts[-1].lower() in _TWO_WORD:
        return " ".join(parts[-2:])
    return parts[-1]


def pick_marquee(date_iso, want=5):
    allg = []
    for lg in LEAGUES:
        try:
            for g in load_games(lg, date_iso):
                g["league"] = lg["name"]
                allg.append(g)
        except Exception as e:
            print(f"  ! {lg['name']} failed: {e}", flush=True)
    # highest-scored (national/major) first, then earliest start
    allg.sort(key=lambda g: (-_score(g),
              g["dt"] or datetime.datetime.max.replace(tzinfo=datetime.timezone.utc)))
    return allg[:want]


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def build_html(games, pretty):
    rows = []
    for g in games:
        style, tag, net = _natl_net(g)
        chip = (f"<div class='chip {style}'>"
                + (f"<span class='cc'>{tag}</span>" if tag else "")
                + f"{esc(net)}</div>")
        rows.append(
            "<div class='g'>"
            f"<div class='m'><div class='teams'>{esc(nick(g['away']))} "
            f"<span class='at'>@</span> {esc(nick(g['home']))}</div>"
            f"<div class='time'>{esc(fmt_time(g['dt']))}</div></div>"
            f"{chip}</div>")
    return CARD_TEMPLATE.replace("{{DATE}}", esc(pretty)).replace("{{ROWS}}", "".join(rows))


def caption(games, pretty):
    picks = []
    for g in games[:3]:
        _, _, net = _natl_net(g)
        picks.append(f"• {g['away']} vs {g['home']} — {net}")
    body = "\n".join(picks)
    return (f"⚾ On TV today ({pretty}) — the games worth watching, US & Canada:\n"
            f"{body}\n\n"
            f"Full listings + where to watch every game \U0001F449 {PAGE_URL}\n"
            f"#SportsOnTV #MLB #NHL #NBA #NFL")


CARD_TEMPLATE = """<!doctype html><html><head><meta charset='utf-8'>
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Oswald:wght@500;600;700&family=Barlow:wght@600;700;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
#card{width:1080px;height:1080px;position:relative;overflow:hidden;color:#f4f6f8;font-family:'Barlow',sans-serif;
 background:radial-gradient(1200px 600px at 50% -10%, #1a222b 0%, rgba(26,34,43,0) 60%), linear-gradient(180deg,#0e1318 0%, #0b0e12 100%)}
#card::before{content:"";position:absolute;inset:0;background-image:repeating-linear-gradient(135deg, rgba(255,255,255,.014) 0 2px, transparent 2px 9px)}
.wrap{position:absolute;inset:0;padding:60px 60px 54px;display:flex;flex-direction:column}
.top{display:flex;align-items:flex-start;justify-content:space-between}
.logobox{background:#fff;border-radius:14px;padding:14px 20px;display:inline-flex;align-items:center;box-shadow:0 6px 20px rgba(0,0,0,.35)}
.logobox img{height:72px;width:auto;display:block}
.flag{font-family:'Oswald';font-weight:600;letter-spacing:1.5px;text-transform:uppercase;font-size:16px;color:#9aa6b2;text-align:right;line-height:1.3;margin-top:8px}
.kick{display:flex;align-items:center;gap:12px;color:#e0be6b;font-family:'Oswald';font-weight:700;letter-spacing:4px;text-transform:uppercase;font-size:22px;margin-top:28px}
.dot{width:14px;height:14px;border-radius:50%;background:#c0392b;box-shadow:0 0 0 5px rgba(192,57,43,.22)}
h1{font-family:'Anton';font-size:108px;line-height:.92;letter-spacing:.5px;text-transform:uppercase;margin-top:8px}
h1 .em{color:#c9a24b}
.date{margin-top:10px;font-family:'Oswald';font-weight:600;letter-spacing:2px;text-transform:uppercase;font-size:26px;color:#cdd6df}
.games{margin-top:24px;flex:1;display:flex;flex-direction:column}
.g{display:flex;align-items:center;gap:18px;padding:16px 4px;border-top:1px solid #242c35}
.g:last-child{border-bottom:1px solid #242c35}
.m{flex:1;min-width:0}
.teams{font-family:'Oswald';font-weight:700;text-transform:uppercase;font-size:38px;line-height:1.05;letter-spacing:.4px;color:#fff;white-space:nowrap}
.teams .at{color:#9aa6b2;font-weight:500;margin:0 6px}
.time{font-family:'Barlow';font-weight:600;font-size:19px;color:#9aa6b2;margin-top:5px}
.chip{font-family:'Barlow';font-weight:800;font-size:18px;padding:8px 14px;border-radius:8px;white-space:nowrap;display:flex;align-items:center;gap:8px;flex:0 0 auto}
.chip .cc{font-size:13px;font-weight:800;padding:2px 6px;border-radius:5px}
.chip.us{background:#1f2732;color:#fff;border:1px solid #2f3a46}
.chip.us .cc{background:#3b4756;color:#dfe6ee}
.chip.natl{background:#c0392b;color:#fff}
.chip.natl .cc{background:rgba(255,255,255,.22);color:#fff}
.chip.ca{background:#173a2a;color:#eafff4;border:1px solid #245b41}
.chip.ca .cc{background:#e8112d;color:#fff}
.cta{margin-top:22px;display:flex;align-items:center;justify-content:space-between;gap:20px}
.pill{background:#c9a24b;color:#161a12;font-family:'Barlow';font-weight:800;font-size:25px;padding:15px 24px;border-radius:12px}
.url{text-align:right;font-family:'Oswald';font-weight:600;letter-spacing:1px;text-transform:uppercase}
.url .s{display:block;color:#9aa6b2;font-size:15px}.url .b{display:block;color:#fff;font-size:23px}
</style></head><body>
<div id='card'><div class='wrap'>
  <div class='top'>
    <div class='logobox'><img src='""" + LOGO_URL + """' alt='The Bannerman'></div>
    <div class='flag'>Where to watch<br>US &amp; Canada</div>
  </div>
  <div class='kick'><span class='dot'></span> On TV Today</div>
  <h1>Marquee <span class='em'>Games</span></h1>
  <div class='date'>{{DATE}}</div>
  <div class='games'>{{ROWS}}</div>
  <div class='cta'><div class='pill'>See every game + channel &rarr;</div>
    <div class='url'><span class='s'>Full US &amp; Canada listings</span><span class='b'>thebannerman.ca</span></div></div>
</div></div></body></html>"""


def main():
    today = datetime.datetime.now(PT).date()
    date_iso = today.strftime("%Y-%m-%d")
    pretty = today.strftime("%A, %B %-d")
    print(f"Building marquee card for {pretty}", flush=True)

    games = pick_marquee(date_iso, want=5)
    print(f"  picked {len(games)} games", flush=True)
    if not games:
        # nothing on today (rare) — still render a graceful card
        games = []

    html = build_html(games, pretty)
    with open("caption.txt", "w", encoding="utf-8") as f:
        f.write(caption(games, pretty) if games else
                f"\U0001F4FA On TV today ({pretty}) — see what's on and where to watch, "
                f"US & Canada \U0001F449 {PAGE_URL}")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1080}, device_scale_factor=2)
        pg.set_content(html, wait_until="networkidle")
        try:
            pg.evaluate("document.fonts.ready")
        except Exception:
            pass
        pg.wait_for_timeout(500)
        pg.screenshot(path="social-card.png", clip={"x": 0, "y": 0, "width": 1080, "height": 1080})
        b.close()
    print("  wrote social-card.png + caption.txt", flush=True)


if __name__ == "__main__":
    main()
