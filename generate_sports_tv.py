#!/usr/bin/env python3
"""
Sports on TV Today  —  daily page generator for The Bannerman (thebannerman.ca)
------------------------------------------------------------------------------
Dual-market (US + Canada) "what's on / where to watch" for:
    MLB, NHL, NBA, NFL, NCAA Men's Basketball, College Football (FBS)

Builds one clean, SEO-optimized HTML block and UPSERTS it into a single Shopify
page (handle: sports-on-tv-today) via the Admin API.

Data sources (all free, no key):
  * MLB  -> statsapi.mlb.com   (official; lists US AND Canadian networks, e.g. Sportsnet)
  * NHL  -> api-web.nhle.com   (official; tags each broadcast US vs CA -> Sportsnet/TSN/CBC)
  * NBA / NFL / College -> site.api.espn.com (US networks per game) + a Canadian
    carrier note per league (best-effort, since no free feed lists CA channels for
    these; refine the CA_* strings below any time).

Runs headless on GitHub Actions every morning at 4:35 AM Pacific.

Required env (GitHub repo secrets):
    SHOPIFY_ADMIN_TOKEN   custom-app Admin API token (shpat_...)
    SHOPIFY_SHOP          e.g. 6c1e0f-fc.myshopify.com   (optional; default below)
"""

import os
import json
import datetime
import re
import urllib.request
import urllib.error
import urllib.parse
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------- config ----
PT = ZoneInfo("America/Los_Angeles")
ET = ZoneInfo("America/New_York")

SHOP    = os.environ.get("SHOPIFY_SHOP", "6c1e0f-fc.myshopify.com").strip()
TOKEN   = os.environ.get("SHOPIFY_ADMIN_TOKEN", "").strip()
API_VER = os.environ.get("SHOPIFY_API_VERSION", "2026-07").strip()

PAGE_HANDLE = "sports-on-tv-today"
PAGE_TITLE  = "Sports on TV Today"
COLLECTIONS_URL = "https://thebannerman.ca/collections/all"

# Linkages (the "chip away" bits). {q} is filled per game.
#   Team names -> your store search for that team (internal link + a path to a sale).
#   Empty "where to watch" cells -> a live listings lookup so it's never a dead end.
# Swap STORE_SEARCH_URL to a collection pattern once you map team -> collection handles,
# e.g. "https://thebannerman.ca/collections/{q}"; swap the listings URLs to tvtv.ca /
# TSN / Sportsnet schedules any time.
STORE_SEARCH_URL = "https://thebannerman.ca/search?q={q}"
LISTINGS_US_URL  = "https://www.google.com/search?q={q}%20game%20today%20on%20tv"
LISTINGS_CA_URL  = "https://www.google.com/search?q={q}%20game%20today%20on%20tv%20canada"

# Leagues in display order.
#   src "mlb"/"nhl" -> official feed with real US + Canada channels per game.
#   src "espn"      -> ESPN for US channels + the ca_note string for Canada.
# Priority order for in-season leagues (Damon's watch order). Whatever has games
# today shows in THIS order at the top; off-season leagues drop to one line at the bottom.
LEAGUES = [
    {"name": "College Football (FBS)",     "src": "espn", "path": "football/college-football",
        "emoji": "\U0001F3C8", "groups": "80", "ca_note": "TSN / RDS / ESPN+ (select games)"},
    {"name": "NFL Football",               "src": "espn", "path": "football/nfl",
        "emoji": "\U0001F3C8", "ca_note": "DAZN (every game) · CTV / TSN (select games)"},
    {"name": "NHL Hockey",                 "src": "nhl", "emoji": "\U0001F3D2"},
    {"name": "MLB Baseball",               "src": "mlb", "emoji": "⚾"},
    {"name": "College Basketball (NCAAM)", "src": "espn", "path": "basketball/mens-college-basketball",
        "emoji": "\U0001F3C0", "groups": "50", "ca_note": "TSN / ESPN+ (select games)"},
    {"name": "NBA Basketball",             "src": "espn", "path": "basketball/nba",
        "emoji": "\U0001F3C0", "ca_note": "Sportsnet / TSN (national windows); NBA League Pass out-of-market"},
    {"name": "MLS Soccer",                 "src": "espn", "path": "soccer/usa.1",
        "emoji": "⚽", "ca_note": "Apple TV — MLS Season Pass (US &amp; Canada)"},
    {"name": "CFL Football",               "src": "espn", "path": "football/cfl",
        "emoji": "\U0001F3C8", "ca_note": "TSN / RDS (Canada)"},
]

# Recognize Canadian networks by name (MLB/NHL feeds have no country flag on some).
_CA_KEYS = ("sportsnet", "tsn", " rds", "rds", "tva sports", "cbc", "citytv", "dazn", "sn now")


def is_canadian(name):
    n = (name or "").lower().strip()
    if n in ("sn", "sn1", "sn360", "sn590"):
        return True
    return any(k in n for k in _CA_KEYS)


# --------------------------------------------------------------- helpers ----
def log(m):
    print(m, flush=True)


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "TheBannerman-SportsOnTV/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.load(r)
    except Exception as e:
        log(f"  ! fetch failed {url.split('?')[0]}: {e}")
        return None


def parse_dt(raw):
    if not raw:
        return None
    try:
        return datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def fmt_time(dt):
    if not dt:
        return "Time TBD"
    return f"{dt.astimezone(ET).strftime('%-I:%M %p')} ET / {dt.astimezone(PT).strftime('%-I:%M %p')} PT"


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def dedupe(seq):
    seen = set()
    return [x for x in seq if x and not (x in seq and (x in seen or seen.add(x)))]


# --------------------------------------------------------- source: MLB -----
def games_mlb(date_iso):
    url = ("https://statsapi.mlb.com/api/v1/schedule?sportId=1"
           f"&date={date_iso}&hydrate=broadcasts(all),team")
    data = get_json(url)
    out = []
    for d in (data or {}).get("dates", []):
        for g in d.get("games", []):
            away = g["teams"]["away"]["team"].get("name", "TBD")
            home = g["teams"]["home"]["team"].get("name", "TBD")
            state = {"Preview": "pre", "Live": "in", "Final": "post"}.get(
                g.get("status", {}).get("abstractGameState"), "pre")
            us, ca = [], []
            for b in g.get("broadcasts", []):
                if b.get("type") != "TV":
                    continue
                nm = b.get("name", "")
                (ca if is_canadian(nm) else us).append(nm)
            out.append({"away": away, "home": home, "dt": parse_dt(g.get("gameDate")),
                        "us": dedupe(us), "ca": dedupe(ca), "state": state,
                        "detail": g.get("status", {}).get("detailedState", "")})
    return out


# --------------------------------------------------------- source: NHL -----
def _nhl_team(t):
    n = t.get("name")
    if isinstance(n, dict) and n.get("default"):
        return n["default"]
    place = (t.get("placeName") or {}).get("default", "")
    common = (t.get("commonName") or {}).get("default", "") or t.get("teamName", "")
    return (f"{place} {common}").strip() or t.get("abbrev", "TBD")


def games_nhl(date_iso):
    data = get_json(f"https://api-web.nhle.com/v1/schedule/{date_iso}")
    out = []
    for wk in (data or {}).get("gameWeek", []):
        if wk.get("date") != date_iso:
            continue
        for g in wk.get("games", []):
            us, ca = [], []
            for tb in g.get("tvBroadcasts", []):
                net = tb.get("network")
                if not net:
                    continue
                cc = tb.get("countryCode")
                if cc == "CA" or (cc not in ("US",) and is_canadian(net)):
                    ca.append(net)
                else:
                    us.append(net)
            state = {"FUT": "pre", "PRE": "pre", "LIVE": "in", "CRIT": "in",
                     "FINAL": "post", "OFF": "post"}.get(g.get("gameState"), "pre")
            out.append({"away": _nhl_team(g.get("awayTeam", {})),
                        "home": _nhl_team(g.get("homeTeam", {})),
                        "dt": parse_dt(g.get("startTimeUTC")),
                        "us": dedupe(us), "ca": dedupe(ca), "state": state, "detail": ""})
    return out


# -------------------------------------------------------- source: ESPN -----
def games_espn(path, date_iso, groups=None):
    yyyymmdd = date_iso.replace("-", "")
    url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={yyyymmdd}&limit=400"
    if groups:
        url += f"&groups={groups}"
    data = get_json(url)
    out = []
    for ev in (data or {}).get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        away = home = None
        for c in comp.get("competitors", []):
            nm = c.get("team", {}).get("displayName") or c.get("team", {}).get("name")
            if c.get("homeAway") == "home":
                home = nm
            else:
                away = nm
        nets = []
        for b in comp.get("broadcasts", []):
            nets += b.get("names", []) or []
        for gb in comp.get("geoBroadcasts", []):
            sn = (gb.get("media") or {}).get("shortName")
            if sn:
                nets.append(sn)
        st = (comp.get("status") or {}).get("type", {}) or {}
        out.append({"away": away or "TBD", "home": home or "TBD",
                    "dt": parse_dt(ev.get("date")),
                    "us": dedupe([n for n in nets if not is_canadian(n)]),
                    "ca": [], "state": st.get("state"), "detail": st.get("shortDetail", "")})
    return out


def load_games(lg, date_iso):
    if lg["src"] == "mlb":
        games = games_mlb(date_iso)
    elif lg["src"] == "nhl":
        games = games_nhl(date_iso)
    else:
        games = games_espn(lg["path"], date_iso, lg.get("groups"))
    games.sort(key=lambda g: (g["dt"] is None,
               g["dt"] or datetime.datetime.max.replace(tzinfo=datetime.timezone.utc)))
    return games


# ------------------------------------------------------------ html build ----
def _status_badge(g):
    if g["state"] == "in":
        return " <span class='bnr-tv-live'>LIVE</span>"
    if g["state"] == "post":
        return f" <span class='bnr-tv-final'>{esc(g['detail'] or 'Final')}</span>"
    return ""


def qurl(tmpl, text):
    return tmpl.replace("{q}", urllib.parse.quote(text))


COLLECTION_INDEX = {}   # slug -> collection handle; filled at runtime from your store


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def load_collections():
    """Pull your store's collections so a team can link to its REAL collection page
    (better landing page + more SEO weight than a search). Falls back to search for any
    team without a collection, and self-updates as you add collections."""
    idx = {}
    for kind in ("custom_collections", "smart_collections"):
        # published_status=published asks Shopify for live collections only; we also
        # double-check published_at so a draft (e.g. an unfinished team page) is never linked.
        st, res = shopify("GET", f"{kind}.json?limit=250&published_status=published")
        if st != 200:
            log(f"  ! could not read {kind} ({st}) — team links will use search")
            continue
        for c in res.get(kind, []):
            h = c.get("handle")
            if not h or not c.get("published_at"):
                continue                      # skip drafts / unpublished collections
            idx.setdefault(slug(h), h)
            idx.setdefault(slug(c.get("title", "")), h)
    return idx


def team_url(name):
    """Best available link for a team: its collection if we have one, else a store search."""
    toks = name.split()
    cands = [slug(name)]
    if toks:
        cands.append(slug(toks[-1]))                # nickname, e.g. "jays"
    if len(toks) >= 2:
        cands.append(slug(" ".join(toks[-2:])))     # 2-word nickname, e.g. "blue-jays"
    for c in cands:
        if c and c in COLLECTION_INDEX:
            return f"https://thebannerman.ca/collections/{COLLECTION_INDEX[c]}"
    return qurl(STORE_SEARCH_URL, name)


def team_link(name):
    if not name or name == "TBD":
        return esc(name or "TBD")
    return f"<a class='bnr-tv-team' href='{team_url(name)}'>{esc(name)}</a>"


def net_cell(nets, listings_url):
    """Networks if we have them; otherwise a live 'check listings' link (never a dead end)."""
    if nets:
        return ", ".join(esc(n) for n in nets)
    return (f"<a class='bnr-tv-check' href='{listings_url}' target='_blank' "
            "rel='noopener nofollow'>Check listings &rarr;</a>")


def build_html(today_pt):
    pretty = today_pt.strftime("%A, %B %-d, %Y")
    date_iso = today_pt.strftime("%Y-%m-%d")
    updated = datetime.datetime.now(PT).strftime("%-I:%M %p PT")

    blocks, schema_items, total = [], [], 0

    # Load every league, then float the ones WITH games today to the top and
    # collapse off-season / off-day leagues into a single line at the bottom.
    active, inactive = [], []
    for lg in LEAGUES:
        games = load_games(lg, date_iso)
        total += len(games)
        log(f"  {lg['name']}: {len(games)} game(s)")
        (active if games else inactive).append((lg, games))

    def render(lg, games):
        anchor = lg["path"].split("/")[-1] if "path" in lg else lg["src"]
        head = f"<h2 id='{anchor}'>{lg['emoji']} {esc(lg['name'])} on TV Today</h2>"
        rows = []
        for g in games:
            q = f"{g['away']} vs {g['home']}"
            match = (f"{team_link(g['away'])} <span class='bnr-tv-at'>@</span> "
                     f"{team_link(g['home'])}{_status_badge(g)}")
            rows.append(
                "<div class='bnr-tv-row'>"
                f"<div class='bnr-tv-c bnr-tv-match'>{match}</div>"
                f"<div class='bnr-tv-c bnr-tv-time'><span class='bnr-tv-lbl'>Start</span>{esc(fmt_time(g['dt']))}</div>"
                f"<div class='bnr-tv-c bnr-tv-net'><span class='bnr-tv-lbl'>\U0001F1FA\U0001F1F8 US</span>{net_cell(g['us'], qurl(LISTINGS_US_URL, q))}</div>"
                f"<div class='bnr-tv-c bnr-tv-net bnr-tv-ca'><span class='bnr-tv-lbl'>\U0001F1E8\U0001F1E6 Canada</span>{net_cell(g['ca'], qurl(LISTINGS_CA_URL, q))}</div>"
                "</div>")
            if g["dt"] and g["state"] != "post":
                schema_items.append({"@type": "SportsEvent",
                                     "name": f"{g['away']} at {g['home']}",
                                     "startDate": g["dt"].astimezone(ET).isoformat(),
                                     "eventStatus": "https://schema.org/EventScheduled"})
        table = ("<div class='bnr-tv-grid'><div class='bnr-tv-hrow'>"
                 "<div>Matchup</div><div>Start</div><div>\U0001F1FA\U0001F1F8 US</div><div>\U0001F1E8\U0001F1E6 Canada</div>"
                 "</div>" + "".join(rows) + "</div>")
        note = ""
        if lg["src"] == "espn" and lg.get("ca_note"):
            note = f"<p class='bnr-tv-canote'>\U0001F1E8\U0001F1E6 <strong>In Canada:</strong> {esc(lg['ca_note'])}.</p>"
        return f"<section class='bnr-tv-league'>{head}{note}{table}</section>"

    for lg, games in active:
        blocks.append(render(lg, games))

    if inactive:
        names = " &middot; ".join(f"{lg['emoji']} {esc(lg['name'])}" for lg, _ in inactive)
        blocks.append("<section class='bnr-tv-league bnr-tv-noton'>"
                      "<p class='bnr-tv-off'><strong>Not on today</strong> "
                      f"(off-season or no games): {names}.</p></section>")

    schema = {"@context": "https://schema.org", "@type": "ItemList",
              "name": f"Sports on TV — {pretty}", "numberOfItems": len(schema_items),
              "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": it}
                                  for i, it in enumerate(schema_items)]}

    css = """
<style>
.bnr-tv-wrap{max-width:940px;margin:0 auto;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#f4f4f4;background:#111418;padding:28px 22px 40px;border-radius:14px;line-height:1.5}
.bnr-tv-wrap h1{font-size:1.9rem;margin:0 0 4px;color:#fff}
.bnr-tv-date{color:#c9a24b;font-weight:700;margin:0 0 14px;text-transform:uppercase;letter-spacing:1px;font-size:.9rem}
.bnr-tv-intro{color:#c8ccd2;margin:0 0 22px}
.bnr-tv-league{margin:0 0 26px}
.bnr-tv-league h2{font-size:1.2rem;margin:0 0 8px;padding-bottom:6px;border-bottom:2px solid #2a2f36;color:#fff}
.bnr-tv-canote{color:#9aa4b2;font-size:.85rem;margin:0 0 10px}
.bnr-tv-grid{width:100%;font-size:.95rem}
.bnr-tv-hrow,.bnr-tv-row{display:grid !important;grid-template-columns:minmax(0,1.3fr) 168px minmax(0,1fr) minmax(0,1fr);gap:12px;align-items:start;margin:0}
.bnr-tv-hrow{color:#8b93a1;font-weight:600;font-size:.72rem;text-transform:uppercase;letter-spacing:.5px;padding:0 0 7px;border-bottom:1px solid #2a2f36}
.bnr-tv-row{padding:10px 0;border-bottom:1px solid #1c2127}
.bnr-tv-c{min-width:0;overflow-wrap:anywhere}
.bnr-tv-lbl{display:none}
.bnr-tv-match{font-weight:600;color:#fff}
.bnr-tv-at{color:#c9a24b;font-weight:400;padding:0 2px}
.bnr-tv-time{color:#c8ccd2;white-space:nowrap}
.bnr-tv-net{color:#7fd1a6}
.bnr-tv-ca{color:#e0574a}
.bnr-tv-none{color:#8b93a1;font-style:italic}
.bnr-tv-team{color:#fff;text-decoration:none;border-bottom:1px dotted #c9a24b}
.bnr-tv-team:hover{color:#c9a24b}
.bnr-tv-check{color:#8b93a1;font-style:italic;text-decoration:none}
.bnr-tv-check:hover{color:#c9a24b}
.bnr-tv-live{background:#c0392b;color:#fff;font-size:.66rem;padding:1px 6px;border-radius:4px;font-weight:700}
.bnr-tv-final{color:#8b93a1;font-size:.78rem}
.bnr-tv-off{color:#8b93a1;font-style:italic;margin:2px 0 0}
.bnr-tv-cta{margin:26px 0 6px;padding:18px 20px;background:#1a1f26;border-radius:10px;border:1px solid #2a2f36}
.bnr-tv-cta a{display:inline-block;margin-top:10px;background:#c9a24b;color:#111;font-weight:700;text-decoration:none;padding:9px 16px;border-radius:8px;white-space:nowrap;font-size:.92rem}
.bnr-tv-foot{color:#6b7280;font-size:.8rem;margin-top:18px}
@media(max-width:600px){
.bnr-tv-hrow{display:none !important}
.bnr-tv-row{grid-template-columns:1fr !important;gap:4px;padding:14px 0}
.bnr-tv-lbl{display:inline-block;color:#8b93a1;font-size:.66rem;text-transform:uppercase;letter-spacing:.5px;margin-right:8px;min-width:64px}
.bnr-tv-match{font-size:1.05rem;margin-bottom:3px}
}
</style>
"""

    html = f"""{css}
<div class="bnr-tv-wrap">
  <p class="bnr-tv-date">{esc(pretty)}</p>

  {''.join(blocks)}

  <div class="bnr-tv-cta">
    <strong>Love Thy Team.</strong><br>
    <a href="{COLLECTIONS_URL}">Shop the collection &rarr;</a>
  </div>

  <p class="bnr-tv-foot">Times shown Eastern / Pacific. US &amp; Canadian listings sourced from
  official league schedules (MLB, NHL) and public sports data; Canadian channels for NBA, NFL
  and college are typical national carriers &mdash; check local listings to confirm. Last
  refreshed {esc(updated)}. Not affiliated with or endorsed by any league or broadcaster.</p>
</div>
<script type="application/ld+json">{json.dumps(schema)}</script>
"""

    meta_title = f"Sports on TV Today (US &amp; Canada) — {pretty}"
    meta_desc = (f"Every NFL, college football, NHL, MLB, NBA, MLS & CFL game on TV today, {pretty} "
                 "— US & Canadian channels (Sportsnet, TSN, ESPN, FOX, DAZN & more) with start times. "
                 "Updated every morning by The Bannerman.")
    return html, meta_title, meta_desc, total


# ---------------------------------------------------------- shopify i/o ----
def shopify(method, path, body=None):
    url = f"https://{SHOP}/admin/api/{API_VER}/{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:500]}


def upsert_page(html, meta_title, meta_desc):
    # NOTE: Shopify's REST pages.json IGNORES a ?handle= filter — it returns
    # whatever pages exist. So we must pull the list and match the handle in
    # code, or we'd blindly overwrite some other page (About, Contact, ...).
    status, res = shopify("GET", "pages.json?limit=250&fields=id,handle,title")
    if status != 200:
        raise SystemExit(f"Shopify GET pages failed ({status}): {res}")
    pages = [p for p in res.get("pages", []) if p.get("handle") == PAGE_HANDLE]
    payload = {"page": {"title": PAGE_TITLE, "handle": PAGE_HANDLE,
                        "body_html": html, "published": True}}
    if pages:
        pid = pages[0]["id"]
        status, res = shopify("PUT", f"pages/{pid}.json", payload); action = "updated"
    else:
        status, res = shopify("POST", "pages.json", payload); action = "created"
        pid = (res.get("page") or {}).get("id")
    if status not in (200, 201):
        raise SystemExit(f"Shopify {action} page failed ({status}): {res}")
    log(f"  page {action}: /pages/{PAGE_HANDLE} (id {pid})")
    for key, val in (("title_tag", meta_title), ("description_tag", meta_desc)):
        st, r = shopify("POST", f"pages/{pid}/metafields.json",
                        {"metafield": {"namespace": "global", "key": key,
                                       "type": "single_line_text_field", "value": val}})
        if st not in (200, 201):
            log(f"  ! could not set {key} ({st}) — page still fine")
    return pid


# ----------------------------------------------------------------- main ----
def main():
    global COLLECTION_INDEX
    if not TOKEN:
        raise SystemExit("SHOPIFY_ADMIN_TOKEN is not set (add it as a GitHub secret).")
    today_pt = datetime.datetime.now(PT).date()
    log(f"Building 'Sports on TV Today' for {today_pt} (Pacific)")
    COLLECTION_INDEX = load_collections()
    log(f"  loaded {len(COLLECTION_INDEX)} collection keys for team links")
    html, mt, md, total = build_html(today_pt)
    log(f"Total games today: {total}")
    upsert_page(html, mt, md)
    log("Done ✅")


if __name__ == "__main__":
    main()
