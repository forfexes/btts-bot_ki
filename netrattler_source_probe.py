"""Probe: welche Odds-/Stats-Seiten sind vom GitHub-Runner ohne API-Key erreichbar?"""
import re, sys, requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept-Language": "en"}
URLS = [
 "https://www.oddsportal.com/matches/soccer/",
 "https://www.betexplorer.com/football/",
 "https://www.betexplorer.com/next/soccer/",
 "https://www.flashscore.com/football/",
 "https://www.soccerstats.com/matches.asp",
 "https://www.football-data.co.uk/fixtures.csv",
 "https://www.football-data.co.uk/new_fixtures.csv",
 "https://www.oddschecker.com/football",
 "https://www.sportinglife.com/football/fixtures",
 "https://sports.bwin.com/en/sports/football-4",
 "https://www.betfair.com/exchange/plus/football",
 "https://api.sofascore.com/api/v1/sport/football/scheduled-events/2026-10-05",
 "https://www.sofascore.com/api/v1/sport/football/scheduled-events/2026-10-05",
 "https://api.sofascore.app/api/v1/sport/football/scheduled-events/2026-10-05",
 "https://www.fotmob.com/api/matches?date=20261005",
 "https://www.22bet.com/line/football",
 "https://www.bet365.com/",
 "https://www.nordicbet.com/",
 "https://eu-offering-api.kambicdn.com/offering/v2018/ubse/listView/football.json?lang=en_GB&market=CH",
 "https://eu-offering-api.kambicdn.com/offering/v2018/unibet/listView/football.json?lang=en_GB&market=GB&useCombined=true",
 "https://sbapi.sbtech.com/",
 "https://www.scorebat.com/video-api/v3/",
 "https://api.the-odds-api.com/v4/sports/",
 "https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d=2026-10-05&s=Soccer",
 "https://www.aiscore.com/",
]
for u in URLS:
    try:
        r = requests.get(u, headers=UA, timeout=20)
        t = r.text or ""
        odd = len(re.findall(r'"(?:odds|price|decimal)"', t))
        print(f"{r.status_code} len={len(t):>8} oddsWords={odd:>4} {u}", flush=True)
    except Exception as e:
        print(f"ERR {type(e).__name__} {u}", flush=True)
