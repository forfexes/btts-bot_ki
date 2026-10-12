#!/usr/bin/env python3
"""NETRATTLER keyless source discovery v3 (read-only).

Tries many public bookmaker / exchange / stats endpoints from the Actions runner and
stores, per endpoint: HTTP status, size, JSON or not, top-level keys and blocking.
For sources that answer with JSON it also stores a small trimmed structure sample so
parsers can be written against the real schema. Writes to netrattler_card_diag.
"""
import datetime as dt
import json
import os
import re

import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept": "application/json, text/plain, */*", "Accept-Language": "en-GB,en;q=0.9"}
BLOCK = re.compile(r"captcha|cloudflare|access denied|just a moment|attention required|incapsula|akamai", re.I)
T = dt.date.today()
T2 = T + dt.timedelta(days=2)
BWIN = {"x-bwin-accessid": "NTZiMjk3OGMtNjU5Mi00NjA5LWI2MWItZmU4MDRhN2QxZmEz", "lang": "en", "country": "GB",
        "userCountry": "GB"}

GET = {
    # exchanges / prediction markets
    "smarkets_events": ("https://api.smarkets.com/v3/events/", {"type": "football_match", "state": "upcoming", "limit": "20"}),
    "matchbook_events": ("https://api.matchbook.com/edge/rest/events", {"sport-ids": "15", "per-page": "20", "include-prices": "true"}),
    "polymarket_events": ("https://gamma-api.polymarket.com/events", {"tag_slug": "soccer", "closed": "false", "limit": "5"}),
    "betdaq": ("https://www.betdaq.com/exchange/soccer", None),
    # bwin group
    "bwin_fixtures": ("https://sports.bwin.com/cds-api/bettingoffer/fixtures",
                      {**BWIN, "fixtureTypes": "Standard", "state": "Latest", "offerMapping": "Filtered",
                       "sportIds": "4", "skip": "0", "take": "3"}),
    # 1xbet family alternative paths
    "1xbet_service_api": ("https://1xbet.com/service-api/LineFeed/Get1x2_VZip",
                          {"sports": "1", "count": "20", "lng": "en", "mode": "4", "country": "1", "partner": "1", "getEmpty": "true"}),
    "melbet_service_api": ("https://melbet.com/service-api/LineFeed/Get1x2_VZip",
                           {"sports": "1", "count": "20", "lng": "en", "mode": "4", "country": "1", "getEmpty": "true"}),
    "22bet_service_api": ("https://22bet.com/service-api/LineFeed/Get1x2_VZip",
                          {"sports": "1", "count": "20", "lng": "en", "mode": "4", "country": "1", "getEmpty": "true"}),
    "betwinner_service_api": ("https://betwinner.com/service-api/LineFeed/Get1x2_VZip",
                              {"sports": "1", "count": "20", "lng": "en", "mode": "4", "country": "1", "getEmpty": "true"}),
    # Superbet (offer CDN)
    "superbet_pl": ("https://production-superbet-offer-pl.freetls.fastly.net/v2/en-BR/events/by-date",
                    {"currentStatus": "active", "offerState": "prematch", "startDate": f"{T} 00:00:00", "endDate": f"{T2} 00:00:00"}),
    "superbet_ro": ("https://production-superbet-offer-ro.freetls.fastly.net/v2/en-BR/events/by-date",
                    {"currentStatus": "active", "offerState": "prematch", "startDate": f"{T} 00:00:00", "endDate": f"{T2} 00:00:00"}),
    # African / LatAm books
    "sportybet_ng": ("https://www.sportybet.com/api/ng/factsCenter/pcUpcomingEvents",
                     {"sportId": "sr:sport:1", "marketId": "1,18,29", "pageSize": "20", "pageNum": "1", "option": "1"}),
    "betika": ("https://api.betika.com/v1/uo/matches", {"page": "1", "limit": "20", "sport_id": "14", "sort_id": "1"}),
    "bet9ja": ("https://sports.bet9ja.com/desktop/feapi/PalimpsestAjax/GetEventsInDailyBundleV3", {"v_cache_version": "1.0"}),
    # Central Europe (relevant for CH/SK)
    "tipsport_cz": ("https://www.tipsport.cz/rest/offer/v2/offer", {"limit": "20"}),
    "fortuna_sk": ("https://www.ifortuna.sk/stavkovanie/futbal", None),
    "nike_sk": ("https://api.nike.sk/api/nikeone/v1/boxes/prematch", {"sport": "futbal"}),
    "tipico_de": ("https://sports.tipico.de/json/program/selectedEvents/all/fussball", None),
    "interwetten": ("https://www.interwetten.com/en/sportsbook/o/10/football", None),
    "betathome": ("https://www.bet-at-home.com/en/sport/football", None),
    "admiral_at": ("https://www.admiral.at/de/sportwetten/fussball", None),
    # Western EU
    "betclic_fr": ("https://offer.cdn.betclic.fr/api/pub/v4/events", {"application": "2", "countrycode": "fr", "language": "fr", "limit": "20", "offset": "0", "sportIds": "1"}),
    "winamax": ("https://www.winamax.fr/paris-sportifs/sports/1", None),
    "sisal": ("https://betting.sisal.it/api/lettura-palinsesto-sport/palinsesto/prematch/schedaManifestazione/0/1", None),
    "snai": ("https://www.snai.it/sport/calcio", None),
    "ladbrokes": ("https://sports.ladbrokes.com/football", None),
    "coral": ("https://sports.coral.co.uk/football", None),
    "williamhill": ("https://sports.williamhill.com/betting/en-gb/football", None),
    "paddypower": ("https://www.paddypower.com/football", None),
    "betvictor": ("https://www.betvictor.com/en-gb/sports/240/meetings", None),
    "betway_page": ("https://sports.betway.com/en/sports/sct/soccer", None),
    "vbet": ("https://www.vbet.com/en/sports/pre-match/event-view/Soccer", None),
    "cashpoint": ("https://www.cashpoint.com/de/sportwetten", None),
    "marathonbet_api": ("https://www.marathonbet.com/en/react/sport/football", None),
    "betcity_ru": ("https://ad.betcity.ru/d/off/events", {"rev": "8", "ver": "1", "csn": "ooca9s", "ids_sp": "1"}),
    "stake_graphql": ("https://stake.com/_api/graphql", None),
    # stats / fixtures
    "livescore_date": ("https://prod-public-api.livescore.com/v1/api/app/date/soccer/" + T.strftime("%Y%m%d") + "/0", {"MD": "1"}),
    "espn_all": ("https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard", {"dates": T.strftime("%Y%m%d")}),
    "fd_new_index": ("https://www.football-data.co.uk/new/ARG.csv", None),
    "openfootball": ("https://raw.githubusercontent.com/openfootball/football.json/master/2025-26/en.1.json", None),
    "clubelo": ("http://api.clubelo.com/" + str(T), None),
    "fotmob_data": ("https://www.fotmob.com/api/data/matches", {"date": T.strftime("%Y%m%d")}),
    "sofascore_www": ("https://www.sofascore.com/api/v1/sport/football/scheduled-events/" + str(T), None),
    "flashscore": ("https://www.flashscore.com/football/", None),
    "soccerway": ("https://int.soccerway.com/matches/", None),
    "besoccer": ("https://www.besoccer.com/livescore", None),
    "kicker": ("https://www.kicker.de/fussball/spieltag", None),
    "transfermarkt_api": ("https://www.transfermarkt.com/ceapi/live-score/day/" + str(T), None),
}


def trim(obj, depth=0):
    """Small structural sample: keep keys, shorten lists/strings."""
    if depth > 4:
        return "…"
    if isinstance(obj, dict):
        return {k: trim(v, depth + 1) for k, v in list(obj.items())[:25]}
    if isinstance(obj, list):
        return [trim(x, depth + 1) for x in obj[:2]] + ([f"+{len(obj) - 2}"] if len(obj) > 2 else [])
    if isinstance(obj, str):
        return obj[:60]
    return obj


def probe(url, params):
    try:
        r = requests.get(url, params=params, headers=UA, timeout=15)
        txt = r.text or ""
        try:
            js = r.json()
        except Exception:
            js = None
        out = {"http": r.status_code, "kb": round(len(txt) / 1024), "json": js is not None,
               "blocked": bool(BLOCK.search(txt[:6000]))}
        if isinstance(js, dict):
            out["keys"] = list(js.keys())[:12]
        elif isinstance(js, list):
            out["keys"] = [f"list[{len(js)}]"]
        out["ok"] = r.status_code == 200 and not out["blocked"] and len(txt) > 500
        return out, js
    except Exception as exc:
        return {"http": 0, "err": type(exc).__name__, "ok": False}, None


def main():
    summary, samples = {"probe": "discovery_v3", "date": str(T)}, {"probe": "discovery_v3_samples"}
    for name, (url, params) in GET.items():
        res, js = probe(url, params)
        summary[name] = res
        print(name, json.dumps(res), flush=True)
        if res.get("ok") and js is not None:
            samples[name] = trim(js)
    # bwin: one full fixture-view to see market names (scorer, corners, cards)
    try:
        r = requests.get("https://sports.bwin.com/cds-api/bettingoffer/fixtures", headers=UA, timeout=15,
                         params={**BWIN, "fixtureTypes": "Standard", "state": "Latest", "offerMapping": "Filtered",
                                 "sportIds": "4", "skip": "0", "take": "10"})
        fx = (r.json() or {}).get("fixtures") or []
        if fx:
            fid = fx[0].get("id")
            r2 = requests.get("https://sports.bwin.com/cds-api/bettingoffer/fixture-view", headers=UA, timeout=20,
                              params={**BWIN, "offerMapping": "All", "fixtureIds": fid, "state": "Latest"})
            f = (r2.json() or {}).get("fixture") or {}
            games = f.get("games") or []
            opt = f.get("optionMarkets") or []
            names = sorted({str((g.get("name") or {}).get("value") or "") for g in games + opt})
            summary["bwin_fixture_view"] = {"http": r2.status_code, "games": len(games), "optionMarkets": len(opt),
                                            "market_names": names[:120]}
            samples["bwin_fixture_view"] = trim(f)
    except Exception as exc:
        summary["bwin_fixture_view"] = {"err": type(exc).__name__}
    summary["ok_list"] = sorted(k for k, v in summary.items() if isinstance(v, dict) and v.get("ok"))
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if url and key:
        h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        requests.post(f"{url}/rest/v1/netrattler_card_diag", timeout=20, json={"info": summary}, headers=h)
        requests.post(f"{url}/rest/v1/netrattler_card_diag", timeout=20, json={"info": json.loads(json.dumps(samples, default=str))}, headers=h)


if __name__ == "__main__":
    main()
