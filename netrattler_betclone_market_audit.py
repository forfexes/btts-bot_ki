#!/usr/bin/env python3
"""NETRATTLER market availability audit from already-used PUBLIC sportsbook feeds.

This only reads the same unauthenticated endpoints as netrattler_keyless_odds.py.
No login, cookies, account tokens, private APIs, or protection bypasses.
Observing a market is not evidence of a supported production mapping.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
import re

import requests

UA = {
    "User-Agent": "NETRATTLER-PublicOddsAudit/1.0 (+https://github.com/forfexes/btts-bot_ki)",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-GB,en;q=0.8",
}

def public_json(url, params, headers=None, timeout=16):
    try:
        r = requests.get(url, params=params, headers={**UA, **(headers or {})},
                         timeout=(5, timeout), allow_redirects=True)
        ct = r.headers.get("content-type", "").lower()
        result = {"http": r.status_code, "json": None, "error": None}
        if r.status_code != 200:
            result["error"] = "HTTP_" + str(r.status_code)
        elif "json" not in ct:
            result["error"] = "not_json"
        elif len(r.content) > 12_000_000:
            result["error"] = "payload_too_large"
        else:
            result["json"] = r.json()
        return result
    except requests.RequestException as e:
        return {"http": 0, "json": None, "error": type(e).__name__}
    except ValueError:
        return {"http": 200, "json": None, "error": "invalid_json"}


def sample_x1_events(payload):
    games = payload.get("Value", []) if isinstance(payload, dict) else []
    events = []
    for game in games[:120]:
        if not isinstance(game, dict):
            continue
        home, away = str(game.get("O1") or ""), str(game.get("O2") or "")
        if not home or not away:
            continue
        selections = list(game.get("E") or [])
        for group in game.get("AE") or []:
            if isinstance(group, dict):
                selections.extend(v for v in (group.get("ME") or []) if isinstance(v, dict))
        events.append((game, selections))
    return events


def summarize_x1(payload):
    games = sample_x1_events(payload)
    codes = Counter()
    with_price = Counter()
    with_param = Counter()
    group_codes = Counter()
    optional_fields = Counter()
    example_labels = {}
    all_nonzero_prices = 0
    for game, sels in games:
        for group in game.get("AE") or []:
            if isinstance(group, dict) and "G" in group:
                group_codes[str(group["G"])] += 1
        for entry in sels:
            if not isinstance(entry, dict):
                continue
            code = str(entry.get("T", "none"))
            codes[code] += 1
            for field in entry:
                optional_fields[str(field)] += 1
            if entry.get("P") is not None:
                with_param[code] += 1
            try:
                value = float(entry.get("C"))
                if 1.01 <= value <= 1000:
                    with_price[code] += 1
                    all_nonzero_prices += 1
            except (ValueError, TypeError):
                pass
            if code not in example_labels:
                # Only short raw descriptions, no session IDs or auth tokens.
                labels = [str(entry.get(k) or "")[:80] for k in ("N", "SN", "Name", "V")]
                example_labels[code] = [v for v in labels if v]
    return {
        "fixture_count": len(games),
        "raw_selections": sum(codes.values()),
        "valid_price_selections": all_nonzero_prices,
        "market_type_codes": [
            {"type_code": code, "observations": count, "valid_prices": with_price[code],
             "line_parameter_count": with_param[code],
             "raw_labels": example_labels.get(code, [])}
            for code, count in codes.most_common(70)
        ],
        "other_market_type_codes_count": max(0, len(codes) - 70),
        "group_codes": dict(group_codes.most_common(25)),
        "selection_fields": dict(optional_fields.most_common(30)),
        "market_label_limitation": "An internal numeric code is not a mapped soccer market without independently validated semantics",
    }


def bwin_text(item):
    if isinstance(item, dict):
        return str(item.get("value") or item.get("short") or item.get("text") or "")
    return str(item or "")


def summarize_bwin(payload):
    fx = payload.get("fixtures", []) if isinstance(payload, dict) else []
    names = Counter()
    with_options = Counter()
    prices = Counter()
    available_samples = []
    for f in fx[:100]:
        if not isinstance(f, dict):
            continue
        games = list(f.get("optionMarkets") or []) + list(f.get("games") or [])
        for mk in games:
            if not isinstance(mk, dict):
                continue
            label = bwin_text(mk.get("name")).strip()
            if not label:
                continue
            names[label] += 1
            opts = mk.get("options") or mk.get("results") or []
            if opts:
                with_options[label] += 1
            for o in opts:
                if not isinstance(o, dict):
                    continue
                p = o.get("price")
                val = p.get("odds") if isinstance(p, dict) else o.get("odds")
                try:
                    if 1.01 <= float(val) <= 1000:
                        prices[label] += 1
                except (ValueError, TypeError):
                    pass
            if len(available_samples) < 16 and prices[label]:
                available_samples.append(label)
    return {
        "fixture_count": len(fx),
        "distinct_market_names": len(names),
        "markets": [
            {"name": name, "fixtures": n, "with_options": with_options[name],
             "valid_price_selections": prices[name]} for name, n in names.most_common(100)
        ],
        "not_shown_market_names": max(0, len(names) - 100),
        "examples_with_prices": available_samples,
        "market_label_limitation": "Only the markets actually present in the public fixture listing were examined",
    }


def market_family(label):
    s = re.sub(r"\s+", " ", (label or "").lower())
    if re.search(r"both teams to score|btts|both teams score", s):
        return "btts_ht" if re.search(r"1st half|first half|half time|halftime", s) else "btts"
    if re.search(r"anytime goal.?scorer|first goal.?scorer|last goal.?scorer|to score at any time", s):
        return "goalscorer"
    if re.search(r"shots? on target", s):
        return "shots_on_target"
    if re.search(r"total shots?|shots? by", s):
        return "shots"
    if re.search(r"\bcorners?\b", s):
        return "corners"
    if re.search(r"1st half|first half", s):
        return "first_half_other"
    if re.search(r"total goals|over.?under", s):
        return "totals"
    return "other"


def summarize_market_families(bwin_result):
    totals = Counter()
    priced = Counter()
    for entry in bwin_result.get("markets", []):
        name = entry.get("name", "")
        family = market_family(name)
        totals[family] += entry.get("fixtures", 0)
        priced[family] += entry.get("valid_price_selections", 0)
    return {k: {"market_instances": totals[k], "priced_outcomes": priced[k]}
            for k in sorted(totals)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="netrattler_betclone_market_audit.json")
    p.add_argument("--timeout", type=int, default=16)
    args = p.parse_args()

    x1 = public_json("https://22bet.com/service-api/LineFeed/Get1x2_VZip",
        {"sports": "1", "count": "100", "lng": "en", "mode": "4", "country": "1",
         "getEmpty": "true"}, timeout=args.timeout)
    bwin_params = {
        "x-bwin-accessid": os.getenv("BWIN_ACCESS_ID", "NTZiMjk3OGMtNjU5Mi00NjA5LWI2MWItZmU4MDRhN2QxZmEz"),
        "lang": "en", "country": "GB", "userCountry": "GB",
        "fixtureTypes": "Standard", "state": "Latest", "offerMapping": "Filtered",
        "sportIds": "4", "skip": "0", "take": "45",
    }
    bwin = public_json("https://sports.bwin.com/cds-api/bettingoffer/fixtures",
        bwin_params, timeout=args.timeout)

    report = {
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Public anonymous 1xBet-family and bwin listing responses, observation only",
        "x1": {"http": x1["http"], "error": x1["error"],
               "data": summarize_x1(x1["json"]) if x1["json"] else None},
        "bwin": {"http": bwin["http"], "error": bwin["error"],
                 "data": summarize_bwin(bwin["json"]) if bwin["json"] else None},
    }
    if report["bwin"]["data"]:
        report["bwin"]["market_families"] = summarize_market_families(report["bwin"]["data"])
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("X1", json.dumps({k: v for k, v in report["x1"].items() if k != "data"}),
          "fixtures", (report["x1"]["data"] or {}).get("fixture_count", 0), flush=True)
    for code in (report["x1"]["data"] or {}).get("market_type_codes", [])[:30]:
        print("X1_CODE", code["type_code"], code["observations"], "valid", code["valid_prices"],
              "labels", code["raw_labels"], flush=True)
    print("BWIN", json.dumps({k: v for k, v in report["bwin"].items() if k not in ("data", "market_families")}),
          "fixtures", (report["bwin"]["data"] or {}).get("fixture_count", 0), flush=True)
    for family, info in report["bwin"].get("market_families", {}).items():
        print("BWIN_FAMILY", family, info["market_instances"], "outcomes", info["priced_outcomes"], flush=True)
    for m in (report["bwin"]["data"] or {}).get("markets", [])[:50]:
        if m["valid_price_selections"]:
            print("BWIN_MARKET", json.dumps(m, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
