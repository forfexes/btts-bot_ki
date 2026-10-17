"""Read-only sweep of every candidate data source for player odds / player stats.

Plain HTTPS GET with one honest User-Agent. No impersonation, no proxies, no captcha handling,
no retries against blocks. Records http status, size and a content signal per source into
netrattler_card_diag (probe=source_sweep). Licensed APIs use our own keys from secrets.
"""
import json, os, time
import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) NETRATTLER-research/1.0", "Accept": "application/json,text/html;q=0.9,*/*;q=0.8"}
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
RES = {}


def keys(name):
    return [k.strip() for k in (os.getenv(name) or "").split(",") if k.strip()]


def hit(name, url, signal=None, headers=None, params=None, method="GET", data=None):
    t = time.time()
    try:
        r = requests.request(method, url, headers={**UA, **(headers or {})}, params=params, data=data, timeout=20)
        body = r.text or ""
        sig = None
        if signal:
            try:
                sig = signal(r)
            except Exception as e:
                sig = f"sig_err:{str(e)[:60]}"
        RES[name] = {"http": r.status_code, "bytes": len(body), "ms": int((time.time() - t) * 1000), "signal": sig}
        return r
    except Exception as e:
        RES[name] = {"http": None, "err": str(e)[:100]}
        return None


def words(*ws):
    def f(r):
        low = r.text.lower()
        return {w: low.count(w) for w in ws}
    return f


PLAYERISH = words("shots", "foul", "tackle", "booked", "card", "player", "captcha", "cloudflare", "access denied")

# ---------- Exchanges / odds APIs ----------
hit("smarkets_events", "https://api.smarkets.com/v3/events/", params={"type": "football_match", "state": "upcoming", "limit": 20},
    signal=lambda r: {"events": len(r.json().get("events", []))})
try:
    ev = (requests.get("https://api.smarkets.com/v3/events/", params={"type": "football_match", "state": "upcoming", "limit": 5}, headers=UA, timeout=20).json().get("events") or [])
    if ev:
        hit("smarkets_markets", f"https://api.smarkets.com/v3/events/{ev[0]['id']}/markets/",
            signal=lambda r: sorted({m.get("market_type", {}).get("name") if isinstance(m.get("market_type"), dict) else str(m.get("market_type")) for m in r.json().get("markets", [])})[:40])
except Exception as e:
    RES["smarkets_markets"] = {"err": str(e)[:80]}

hit("matchbook_events", "https://api.matchbook.com/edge/rest/events", params={"sport-ids": 15, "per-page": 20, "include-prices": "false"},
    signal=lambda r: {"events": len(r.json().get("events", [])), "market_names": sorted({m.get("name") for e in r.json().get("events", []) for m in e.get("markets", [])})[:40]})

hit("pinnacle_guest_soccer", "https://guest.api.arcadia.pinnacle.com/0.1/sports/29/matchups",
    headers={"x-api-key": os.getenv("PINNACLE_GUEST_KEY", "")},
    signal=lambda r: {"matchups": len(r.json()), "specials": sum(1 for m in r.json() if m.get("type") == "special"),
                      "special_names": sorted({str(m.get("special", {}).get("category")) for m in r.json() if m.get("type") == "special"})[:20]})

bk, bs = keys("BETFAIR_APP_KEY"), keys("BETFAIR_SESSION_TOKEN")
if bk and bs:
    hit("betfair_market_types", "https://api.betfair.com/exchange/betting/rest/v1.0/listMarketTypes/",
        method="POST", headers={"X-Application": bk[0], "X-Authentication": bs[0], "Content-Type": "application/json"},
        data=json.dumps({"filter": {"eventTypeIds": ["1"]}}),
        signal=lambda r: sorted(x.get("marketType") for x in r.json())[:120] if isinstance(r.json(), list) else r.json())
else:
    RES["betfair_market_types"] = {"skip": "BETFAIR_APP_KEY/SESSION_TOKEN missing"}

# The Odds API: find a key with quota, then list markets of one EPL event
oa = None
for k in keys("ODDS_API_KEYS"):
    try:
        r = requests.get("https://api.the-odds-api.com/v4/sports", params={"apiKey": k}, timeout=15)
        if r.status_code == 200 and int(r.headers.get("x-requests-remaining", "0") or 0) > 5:
            oa = k; RES["odds_api_quota"] = {"keys": len(keys("ODDS_API_KEYS")), "remaining": r.headers.get("x-requests-remaining")}
            break
    except Exception:
        pass
if oa:
    try:
        evs = requests.get("https://api.the-odds-api.com/v4/sports/soccer_epl/events", params={"apiKey": oa}, timeout=15).json()
        if evs:
            hit("odds_api_epl_markets", f"https://api.the-odds-api.com/v4/sports/soccer_epl/events/{evs[0]['id']}/markets",
                params={"apiKey": oa, "regions": "uk,eu,us"},
                signal=lambda r: sorted({m.get("key") for b in r.json().get("bookmakers", []) for m in b.get("markets", [])})[:80])
            hit("odds_api_epl_player_shots", f"https://api.the-odds-api.com/v4/sports/soccer_epl/events/{evs[0]['id']}/odds",
                params={"apiKey": oa, "regions": "uk,eu,us", "markets": "player_shots_on_target,player_shots,player_goal_scorer_anytime"},
                signal=lambda r: {"bookmakers": len(r.json().get("bookmakers", [])) if isinstance(r.json(), dict) else r.json()})
    except Exception as e:
        RES["odds_api_epl_markets"] = {"err": str(e)[:80]}
else:
    RES["odds_api_quota"] = {"keys": len(keys("ODDS_API_KEYS")), "usable": 0}

ak = keys("API_FOOTBALL_KEYS")
if ak:
    hit("api_football_status", "https://v3.football.api-sports.io/status", headers={"x-apisports-key": ak[0]},
        signal=lambda r: r.json().get("response"))

# ---------- Bookmakers (status only, honest single request) ----------
for name, url in {
    "bet365": "https://www.bet365.com/", "williamhill": "https://sports.williamhill.com/betting/en-gb/football",
    "paddypower": "https://www.paddypower.com/football", "skybet": "https://m.skybet.com/football",
    "betfred": "https://www.betfred.com/sport/football", "betway": "https://betway.com/en/sports/cat/soccer",
    "unibet_kambi": "https://www.unibet.com/betting/sports/filter/football", "oddschecker": "https://www.oddschecker.com/football",
    "betvictor": "https://www.betvictor.com/en-gb/sports/football", "coral": "https://sports.coral.co.uk/sport/football",
    "ladbrokes": "https://sports.ladbrokes.com/sport/football", "boylesports": "https://www.boylesports.com/sports/football",
}.items():
    hit(f"book_{name}", url, signal=PLAYERISH)

# ---------- Stats sources ----------
hit("fpl_bootstrap", "https://fantasy.premierleague.com/api/bootstrap-static/",
    signal=lambda r: {"players": len(r.json().get("elements", [])), "fields_sample": sorted(r.json()["elements"][0].keys())[:60]})
hit("fpl_fixtures", "https://fantasy.premierleague.com/api/fixtures/", signal=lambda r: {"fixtures": len(r.json())})
hit("understat_epl", "https://understat.com/league/EPL", signal=words("playersdata", "shotsdata", "datesdata"))
hit("fbref_epl", "https://fbref.com/en/comps/9/Premier-League-Stats", signal=PLAYERISH)
hit("fotmob_matches", "https://www.fotmob.com/api/data/matches", params={"date": time.strftime("%Y%m%d")},
    signal=lambda r: {"leagues": len(r.json().get("leagues", []))})
hit("sofascore_events", "https://api.sofascore.com/api/v1/sport/football/scheduled-events/" + time.strftime("%Y-%m-%d"),
    signal=lambda r: {"events": len(r.json().get("events", []))})
hit("whoscored", "https://www.whoscored.com/", signal=PLAYERISH)
hit("transfermarkt", "https://www.transfermarkt.com/", signal=PLAYERISH)
hit("espn_scoreboard", "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard", signal=lambda r: {"events": len(r.json().get("events", []))})
hit("bundesliga_site", "https://www.bundesliga.com/en/bundesliga/stats/players", signal=PLAYERISH)
hit("uefa_api", "https://match.uefa.com/v5/matches", params={"competitionId": 1, "seasonYear": 2027, "limit": 5}, signal=lambda r: {"items": len(r.json()) if isinstance(r.json(), list) else 0})
hit("footballdata_couk", "https://www.football-data.co.uk/mmz4281/2627/E0.csv", signal=lambda r: {"rows": r.text.count("\n"), "has_corners": "HC," in r.text})
hit("thesportsdb", "https://www.thesportsdb.com/api/v1/json/3/eventsday.php", params={"d": time.strftime("%Y-%m-%d"), "s": "Soccer"},
    signal=lambda r: {"events": len((r.json() or {}).get("events") or [])})

out = {"probe": "source_sweep", "results": RES}
print(json.dumps(out, indent=1)[:12000])
if SB and SK:
    requests.post(f"{SB}/rest/v1/netrattler_card_diag", timeout=20,
                  headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"}, json={"info": out})
