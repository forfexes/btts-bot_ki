"""Probe: welche Odds-/Stats-Seiten sind vom GitHub-Runner ohne API-Key erreichbar?"""
import re, sys, requests
try:
    import netrattler_health as H
except Exception:
    H = None
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept-Language": "en"}
URLS = [
 "https://eu-offering-api.kambicdn.com/offering/v2018/ub/listView/football/all/all/all/matches.json?lang=en_GB&market=GB",
 "https://eu-offering-api.kambicdn.com/offering/v2018/888/listView/football/all/all/all/matches.json?lang=en_GB&market=GB",
 "https://eu-offering-api.kambicdn.com/offering/v2018/paddypower/listView/football/all/all/all/matches.json?lang=en_GB&market=GB",
 "https://eu-offering-api.kambicdn.com/offering/v2018/betsson/listView/football/all/all/all/matches.json?lang=en_GB&market=SE",
 "https://eu-offering-api.kambicdn.com/offering/v2018/leovegas/listView/football/all/all/all/matches.json?lang=en_GB&market=SE",
 "https://eu-offering-api.kambicdn.com/offering/v2018/svenskaspel/listView/football/all/all/all/matches.json?lang=sv_SE&market=SE",
 "https://eu-offering-api.kambicdn.com/offering/v2018/ubnl/listView/football/all/all/all/matches.json?lang=en_GB&market=NL",
 "https://eu-offering-api.kambicdn.com/offering/v2018/ubfr/listView/football/all/all/all/matches.json?lang=en_GB&market=FR",
 "https://www.football-data.co.uk/fixtures.csv",
 "https://www.football-data.co.uk/matches.php",
 "https://www.betexplorer.com/next/soccer/?year=2026&month=10&day=05",
 "https://www.betexplorer.com/football/england/premier-league/",
 "https://www.betexplorer.com/football/england/premier-league/fixtures/",
 "https://www.livescore.com/en/",
 "https://prod-public-api.livescore.com/v1/api/app/date/soccer/20261005/0?locale=en",
 "https://www.espn.com/soccer/scoreboard",
 "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard",
 "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard?dates=20261010",
 "https://sports.api.decathlon.com/",
 "https://api.football-data.org/v4/matches",
 "https://www.scoresandodds.com/soccer",
 "https://www.sportsbet.com.au/betting/soccer",
 "https://api.bet9ja.com/",
 "https://sportsbook.draftkings.com/leagues/soccer/epl",
 "https://sportsbook-nash.draftkings.com/sites/US-SB/api/v5/eventgroups/40253?format=json",
 "https://www.fanduel.com/sports/soccer",
 "https://api.nsoft.com/",
 "https://www.tipico.de/",
 "https://sports.coral.co.uk/",
 "https://www.oddspedia.com/football",
 "https://oddspedia.com/api/v1/getMatchList?geoCode=CH&wettsteuer=0&startDate=2026-10-05T00:00:00Z&endDate=2026-10-05T23:59:59Z&sport=football&status=all&language=en",
 "https://www.sportytrader.com/en/odds/football-1/",
 "https://www.betbrain.com/football/",
]
for u in URLS:
    try:
        r = requests.get(u, headers=UA, timeout=20)
        t = r.text or ""
        odd = len(re.findall(r'"(?:odds|price|decimal)"', t))
        print(f"{r.status_code} len={len(t):>8} oddsWords={odd:>4} {u}", flush=True)
        if H: H.record("source_probe2", u[:90], len(t), odd, note=f"http {r.status_code} oddsWords={odd}", ok=(r.status_code==200 and len(t)>2000))
    except Exception as e:
        print(f"ERR {type(e).__name__} {u}", flush=True)
        if H: H.record("source_probe2", u[:90], 0, 0, note=f"ERR {type(e).__name__} {str(e)[:120]}", ok=False)
