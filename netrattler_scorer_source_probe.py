#!/usr/bin/env python3
"""Probe free, keyless bookmaker feeds from the Actions runner.
For each source: reachable? how many football events? do event offers contain
anytime-goalscorer quotes? Read-only; writes counts to netrattler_card_diag."""
import json, os, re, requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Accept": "application/json", "Accept-Language": "en"}
SCORER = re.compile(r"goal\s*-?\s*scorer|anytime|to score", re.I)
KAMBI_BRANDS = ["ub", "ubse", "ubnl", "ubbe", "ubdk", "ubuk", "paf", "pafse", "svenskaspel", "atg",
                "rsicouk", "rsiuspa", "bingoal", "napoleongames", "betcitynl", "leovegas", "888",
                "expekt", "nordicbet", "casumoes", "mrgreen", "unibetes"]
KAMBI_HOSTS = ["https://eu-offering-api.kambicdn.com", "https://e0-api.kambi.com"]


def get(url, **params):
    try:
        r = requests.get(url, params=params, headers=UA, timeout=15)
        try:
            return r.status_code, r.json(), r.text
        except Exception:
            return r.status_code, None, r.text or ""
    except Exception as exc:
        return 0, None, type(exc).__name__


def kambi(brand):
    for host in KAMBI_HOSTS:
        st, js, _ = get(f"{host}/offering/v2018/{brand}/listView/football/all/all/all/matches.json", lang="en_GB", market="GB")
        if st != 200 or not isinstance(js, dict):
            continue
        evs = [e for e in js.get("events") or [] if (e.get("event") or {}).get("state") == "NOT_STARTED"]
        res = {"http": 200, "events": len(evs), "scorer_events": 0, "scorer_quotes": 0}
        for e in evs[:4]:
            eid = (e.get("event") or {}).get("id")
            st2, js2, _ = get(f"{host}/offering/v2018/{brand}/betoffer/event/{eid}.json", lang="en_GB", market="GB")
            if st2 != 200 or not isinstance(js2, dict):
                continue
            n = sum(len(b.get("outcomes") or []) for b in js2.get("betOffers") or []
                    if SCORER.search(str((b.get("criterion") or {}).get("label") or "")))
            res["scorer_quotes"] += n
            res["scorer_events"] += 1 if n else 0
        return res
    return {"http": st}


def generic(name, url, **params):
    st, js, txt = get(url, **params)
    return {"http": st, "bytes": len(txt or ""), "scorer_kw": bool(SCORER.search(txt or "")),
            "blocked": bool(re.search(r"captcha|cloudflare|access denied|just a moment", (txt or "")[:4000], re.I))}


def main():
    out = {"probe": "scorer_sources_v2"}
    for b in KAMBI_BRANDS:
        out[f"kambi_{b}"] = kambi(b)
    out["pinnacle_guest"] = generic("pin", "https://guest.api.arcadia.pinnacle.com/0.1/sports/29/matchups", withSpecials="true")
    out["1xbet"] = generic("1x", "https://1xbet.com/LineFeed/Get1x2_VZip", sports=1, count=50, lng="en", mode=4, country=1)
    out["melbet"] = generic("mel", "https://melbet.com/LineFeed/Get1x2_VZip", sports=1, count=50, lng="en", mode=4, country=1)
    out["betwinner"] = generic("bw", "https://betwinner.com/LineFeed/Get1x2_VZip", sports=1, count=50, lng="en", mode=4, country=1)
    out["22bet"] = generic("22", "https://22bet.com/LineFeed/Get1x2_VZip", sports=1, count=50, lng="en", mode=4, country=1)
    out["bwin_cds"] = generic("bwin", "https://sports.bwin.com/cds-api/bettingoffer/fixtures",
                              **{"x-bwin-accessid": "NTZiMjk3OGMtNjU5Mi00NjA5LWI2MWItZmU4MDRhN2QxZmEz", "lang": "en",
                                 "country": "GB", "userCountry": "GB", "fixtureTypes": "Standard", "state": "Latest",
                                 "offerMapping": "Filtered", "sportIds": "4", "skip": "0", "take": "20"})
    out["betsson_obg"] = generic("obg", "https://www.betsson.com/api/sb/v1/widgets/events-table/v2",
                                 categoryIds="1", pageNumber="1", eventPhase="Prematch")
    out["marathonbet"] = generic("mara", "https://www.marathonbet.com/en/betting/Football/")
    out["sportybet"] = generic("sporty", "https://www.sportybet.com/api/ng/factsCenter/pcUpcomingEvents",
                               sportId="sr:sport:1", pageSize="20", pageNum="1")
    out["betway"] = generic("betway", "https://sports.betway.com/api/Events/v2/GetGroup")
    out["stake"] = generic("stake", "https://stake.com/sports/soccer")
    out["polymarket"] = generic("poly", "https://gamma-api.polymarket.com/events", tag_slug="soccer", closed="false", limit="20")
    print(json.dumps(out, indent=1))
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if url and key:
        requests.post(f"{url}/rest/v1/netrattler_card_diag", timeout=15, json={"info": out},
                      headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"})


if __name__ == "__main__":
    main()
