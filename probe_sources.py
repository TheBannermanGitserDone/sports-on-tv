#!/usr/bin/env python3
"""Probe candidate sports data sources from inside a GitHub Actions runner.

ESPN's site.api host returns HTTP 403 to GitHub runner IPs even with full
browser headers, so the block is on the IP range rather than the User-Agent.
This tests alternative hosts and league-official feeds to find which are
reachable from CI. Read the log, then wire the survivors into the generator.
"""
import datetime
import urllib.request
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
today = datetime.datetime.now(PT).date()
slash = today.strftime("%Y/%m/%d")
dash = today.strftime("%Y-%m-%d")

HDRS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.espn.com/",
}

CANDIDATES = [
    ("ESPN site.api CFB (baseline)", "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"),
    ("ESPN cdn.espn CFB", "https://cdn.espn.com/core/college-football/scoreboard?xhr=1"),
    ("ESPN site.web.api CFB", "https://site.web.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"),
    ("ESPN cdn.espn NFL", "https://cdn.espn.com/core/nfl/scoreboard?xhr=1"),
    ("ESPN cdn.espn NBA", "https://cdn.espn.com/core/nba/scoreboard?xhr=1"),
    ("ESPN cdn.espn NCAAM", "https://cdn.espn.com/core/mens-college-basketball/scoreboard?xhr=1"),
    ("ESPN cdn.espn MLS", "https://cdn.espn.com/core/soccer/scoreboard?xhr=1&league=usa.1"),
    ("ESPN cdn.espn CFL", "https://cdn.espn.com/core/cfl/scoreboard?xhr=1"),
    ("NCAA official FBS", "https://data.ncaa.com/casablanca/scoreboard/football/fbs/" + slash + "/scoreboard.json"),
    ("NCAA official MBB", "https://data.ncaa.com/casablanca/scoreboard/basketball-men/d1/" + slash + "/scoreboard.json"),
    ("NBA official CDN", "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"),
    ("MLS official", "https://sportapi.mlssoccer.com/api/matches?culture=en-us&dateFrom=" + dash + "&dateTo=" + dash),
    ("TheSportsDB NFL", "https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d=" + dash + "&l=NFL"),
    ("TheSportsDB NCAA FB", "https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d=" + dash + "&l=NCAA%20Football"),
]


def main():
    print("Probing sources for " + str(today) + " (Pacific)")
    print("")
    ok = 0
    for name, url in CANDIDATES:
        try:
            req = urllib.request.Request(url, headers=HDRS)
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read()
                print("  OK    {:3d}  {:>9,}b  {}".format(r.status, len(body), name))
                ok += 1
        except Exception as e:
            print("  FAIL            -        {}  ->  {}".format(name, e))
    print("")
    print("{}/{} reachable from this runner.".format(ok, len(CANDIDATES)))


if __name__ == "__main__":
    main()
