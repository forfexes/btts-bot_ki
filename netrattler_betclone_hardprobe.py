#!/usr/bin/env python3
"""Read-only BetClone catalogue and public bookmaker homepage audit.

Inventory lists BetClone's bookmakers by sportsbook platform. BetClone bookmaker
links are affiliate redirects, NOT bookmaker URLs. Only explicitly curated
candidate homepage URLs are requested. A homepage HTTP 200 is never called
a working odds feed. Never bypass access controls, authentication or CAPTCHA.
"""
import argparse
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

PAGES = {
    "1xbet": "1xbet.shtml",
    "altenar": "altenar.shtml",
    "betby": "betby.shtml",
    "betconstruct": "betconstruct.shtml",
    "delasport": "delasport.shtml",
    "digitain": "digitain.shtml",
    "igate": "igate.shtml",
    "inplaynet": "inplaynet.shtml",
    "first": "first.shtml",
    "softswiss": "softswiss.shtml",
}

# Candidate operator homepages, not affiliate URLs or presumed APIs.
# Recognition as a bookmaker is not a claim that odds can be collected.
# A country-specific block is NOT evaded with mirrors or proxies.
CANDIDATES = {
    "1xbet": [
        ("1xbet", "https://1xbet.com/"), ("22bet", "https://22bet.com/"),
        ("betwinner", "https://betwinner.com/"), ("melbet", "https://melbet.com/"),
        ("spinbetter", "https://spinbetter.com/"), ("1xbit", "https://1xbit.com/"),
    ],
    "altenar": [
        ("rabona", "https://rabona.com/"), ("sportaza", "https://sportaza.com/"),
        ("betinia", "https://betinia.com/"), ("vegas.hu", "https://vegas.hu/"),
        ("betrepublic", "https://betrepublic.com/"),
    ],
    "betby": [
        ("betfury", "https://betfury.com/"), ("20bet", "https://20bet.com/"),
        ("tonybet", "https://tonybet.com/"), ("vave", "https://vave.com/"),
        ("mama.bet", "https://mama.bet/"), ("noxino", "https://noxino.com/"),
    ],
    "betconstruct": [
        ("vbet", "https://www.vbet.com/"), ("efbet", "https://efbet.com/"),
        ("olybet", "https://olybet.com/"), ("fastbet", "https://fastbet.com/"),
    ],
    "delasport": [
        ("grandwin", "https://grandwin.bet/"), ("felicebet", "https://felicebet.com/"),
        ("silverplay", "https://silverplay.com/"), ("monoplay", "https://monoplay.com/"),
        ("spinimax", "https://spinimax.com/"),
    ],
    "digitain": [
        ("slottica", "https://slottica.com/"), ("magic365", "https://magic365.com/"),
        ("viks", "https://viks.com/"), ("spinamba", "https://spinamba.com/"),
    ],
    "igate": [
        ("pandido", "https://pandido.com/"), ("spinbara", "https://spinbara.com/"),
        ("reybets", "https://reybets.com/"), ("spinlynx", "https://spinlynx.com/"),
    ],
    "inplaynet": [
        ("mystake", "https://mystake.com/"), ("goldenbet", "https://goldenbet.com/"),
        ("rolletto", "https://rolletto.com/"), ("velobet", "https://velobet.com/"),
        ("cosmobet", "https://cosmobet.com/"),
    ],
    "first": [
        ("sportsbet.io", "https://sportsbet.io/"), ("bk8", "https://www.bk8sports.com/en"),
        ("dicepalace", "https://dicepalace.com/"), ("wildies", "https://wildies.com/"),
    ],
    "softswiss": [
        ("n1bet", "https://n1bet.com/"), ("wild.io", "https://wild.io/"),
        ("metaspins", "https://metaspins.com/"),
        ("platincasino", "https://platincasino.com/"),
        ("roosterbet", "https://roosterbet.com/"),
    ],
}
HEADERS = {
    "User-Agent": "NETRATTLER-PublicSourceAudit/2.0 (+https://github.com/forfexes/btts-bot_ki)",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.5",
    "Accept-Language": "en,en-US;q=0.8",
}
BLOCKED = re.compile(r"captcha|access denied|just a moment|attention required|verify you are human|geo.?blocked", re.I)
MAX_BYTES = 600_000


def fetch_public(url, timeout=9):
    """Single unauthed GET; bounded response; no retries or bypass techniques."""
    with requests.get(url, headers=HEADERS, timeout=(4, timeout), stream=True, allow_redirects=True) as response:
        chunks = []
        total = 0
        for part in response.iter_content(chunk_size=32768):
            if not part:
                continue
            if total + len(part) > MAX_BYTES:
                chunks.append(part[: MAX_BYTES - total])
                total = MAX_BYTES
                break
            chunks.append(part)
            total += len(part)
            if total >= MAX_BYTES:
                break
        body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
        return response.status_code, response.url, response.headers.get("Content-Type", ""), body, total


def parse_catalogue_html(html):
    """Read ALL bookmaker table sections; ignore navigation, ads and referral URLs."""
    soup = BeautifulSoup(html, "html.parser")
    found = []
    seen = set()
    for table in soup.find_all("table"):
        links = table.select("a[href]")
        has_bookmaker_header = "bookmaker" in table.get_text(" ", strip=True)[:200].lower()
        has_bookmaker_referrals = any(
            "finmart.pro" in (a.get("href") or "").lower() for a in links
        )
        if not has_bookmaker_header and not has_bookmaker_referrals:
            continue
        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            cell = cells[0]
            brand = re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).strip()
            if not brand or len(brand) > 90 or brand.lower() in {"bookmaker", "bonus"}:
                continue
            # Continuing tables may have no column headings, but always have an
            # operator affiliate link. We extract only the TEXT, never follow it.
            if not cell.find("a") and not has_bookmaker_header:
                continue
            key = brand.casefold()
            if key not in seen:
                seen.add(key)
                found.append(brand)
    return found


def parse_extended_bookmakers(html):
    """Unlinked Betconstruct appendix: explicitly mark as historical/unverified."""
    soup = BeautifulSoup(html, "html.parser")
    extra = []
    seen = set()
    for p in soup.find_all(["p", "div"]):
        if p.find(["p", "div"]):
            continue
        t = p.get_text(" ", strip=True)
        if len(t) < 200 or t.count(",") < 15 or "Betx101" not in t:
            continue
        for name in re.split(r",\s*", t):
            name = re.sub(r"\s+sportsbook$", "", name.strip(), flags=re.I)
            if 2 <= len(name) <= 80 and len(name.split()) <= 5:
                key = name.casefold()
                if key not in seen:
                    extra.append(name)
                    seen.add(key)
    return extra

def inventory_one(family, page):
    url = "https://betclone.com/" + page
    try:
        code, final, ct, body, n = fetch_public(url, timeout=11)
        names = parse_catalogue_html(body) if code == 200 else []
        extra = parse_extended_bookmakers(body) if code == 200 else []
        return {"url": url, "http": code, "count": len(names),
                "status": "listed" if names else "catalogue_unavailable_or_unparsed",
                "bookmakers": names, "historical_extra_bookmakers": extra,
                "historical_extra_count": len(extra)}
    except requests.RequestException as exc:
        return {"url": url, "http": 0, "count": 0,
                "status": "network_error", "error_type": type(exc).__name__,
                "bookmakers": [], "historical_extra_bookmakers": [], "historical_extra_count": 0}


def valid_decimal(value):
    if isinstance(value, bool):
        return False
    try:
        return 1.01 <= float(value) <= 1000
    except (TypeError, ValueError):
        return False


def audit_odds_json(payload):
    """Conservative: selection + numerical price + enclosing event AND market."""
    counts = Counter()
    price_fields = {"odds", "decimalodds", "decimalprice", "price"}
    label_fields = {"name", "label", "selection", "outcome"}
    event_fields = {"eventid", "fixtureid", "matchid", "eventname", "home", "hometeam", "participants"}
    market_fields = {"market", "marketid", "marketname", "bettype", "markets"}
    def walk(obj, event=False, market=False, depth=0):
        if depth > 15:
            return
        if isinstance(obj, list):
            for item in obj[:400]:
                walk(item, event, market, depth + 1)
        elif isinstance(obj, dict):
            keys = {str(k).lower().replace("_", "") for k in obj}
            e = event or bool(keys & event_fields)
            m = market or bool(keys & market_fields)
            prices = [v for k, v in obj.items() if str(k).lower().replace("_", "") in price_fields]
            if e and m and keys & label_fields and any(valid_decimal(v) for v in prices):
                counts["verified_prices"] += 1
                category_text = " ".join(str(v)[:100] for k, v in obj.items()
                                         if str(k).lower().replace("_", "") in label_fields).lower()
                for marker, pat in (
                    ("btts", r"both teams to score|\bbtts\b"),
                    ("goalscorer", r"goal.?scorer|to score"),
                    ("shots", r"shots? on target|total shots?"),
                    ("corners", r"corners?"),
                    ("half", r"1st half|first half|half.time"),
                ):
                    if re.search(pat, category_text):
                        counts[marker] += 1
            for val in obj.values():
                if isinstance(val, (list, dict)):
                    walk(val, e, m, depth + 1)
    walk(payload)
    return dict(counts)


def probe_homepage(family, brand, url, timeout=9):
    out = {"platform": family, "brand": brand, "url": url,
           "http": 0, "bytes": 0, "state": "not_tested",
           "verified_odds": 0, "markets": {}, "final_host": None}
    try:
        code, final, content_type, body, n = fetch_public(url, timeout)
        out.update({"http": code, "bytes": n, "final_host": urlparse(final).hostname})
        mime = content_type.split(";")[0].lower()
        if code in (401, 403, 407, 429, 451) or (code != 200 and BLOCKED.search(body[:2000])):
            out["state"] = "blocked"
        elif code != 200:
            out["state"] = "http_error"
        elif BLOCKED.search(body[:2000]):
            out["state"] = "challenge_page"
        else:
            data = []
            if "json" in mime:
                try:
                    data.append(json.loads(body))
                except ValueError:
                    pass
            elif "html" in mime:
                soup = BeautifulSoup(body, "html.parser")
                for tag in soup.find_all("script", type=re.compile("json", re.I))[:12]:
                    raw = tag.string or tag.get_text()
                    if raw and len(raw) < 350000:
                        try:
                            data.append(json.loads(raw))
                        except ValueError:
                            pass
            for item in data:
                c = audit_odds_json(item)
                out["verified_odds"] += c.get("verified_prices", 0)
                for k, v in c.items():
                    if k != "verified_prices":
                        out["markets"][k] = out["markets"].get(k, 0) + v
            if out["verified_odds"]:
                out["state"] = "public_structured_odds_candidate"
            elif "html" in mime:
                out["state"] = "html_no_verified_odds"
            else:
                out["state"] = "no_verified_odds"
        # A cross-site redirect might be benign but is never certified as a source.
        src_host = (urlparse(url).hostname or "").removeprefix("www.")
        dst_host = (out["final_host"] or "").removeprefix("www.")
        if src_host and dst_host and not (dst_host == src_host or dst_host.endswith("." + src_host)):
            out["off_domain_redirect"] = True
            if out["state"] == "public_structured_odds_candidate":
                out["state"] = "odds_on_different_domain_needs_review"
    except requests.RequestException as exc:
        out["state"] = "network_error"
        out["error_type"] = type(exc).__name__
    return out


def run_scan(timeout=9, workers=7, scan_sites=True):
    catalogue = {}
    sites = []
    jobs = {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 10))) as pool:
        for family, path in PAGES.items():
            jobs[pool.submit(inventory_one, family, path)] = ("catalogue", family)
        if scan_sites:
            for family, entries in CANDIDATES.items():
                for brand, url in entries:
                    jobs[pool.submit(probe_homepage, family, brand, url, timeout)] = ("site", family)
        for future in as_completed(jobs):
            kind, family = jobs[future]
            try:
                val = future.result()
            except Exception as exc:
                val = {"platform": family, "state": "unexpected_error", "error_type": type(exc).__name__}
            if kind == "catalogue":
                catalogue[family] = val
            else:
                sites.append(val)
    seen = {family: {name.casefold() for name in item.get("bookmakers", [])}
            for family, item in catalogue.items()}
    for site in sites:
        site["brand_in_betclone_table"] = site["brand"].casefold() in seen.get(site["platform"], set())
    states = Counter(s["state"] for s in sites)
    return {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "one_unauthed_public_homepage_GET_per_curated_domain",
        "not_a_feed_integration": True,
        "catalogue": catalogue,
        "catalogue_total_listed_entries": sum(i["count"] for i in catalogue.values()),
        "catalogue_families_retrieved": sum(i["count"] > 0 for i in catalogue.values()),
        "historical_extra_entries": sum(i.get("historical_extra_count", 0) for i in catalogue.values()),
        "sites_checked": len(sites),
        "site_states": dict(states),
        "sites": sorted(sites, key=lambda x: (x["platform"], x["brand"])),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--timeout", type=int, default=9)
    p.add_argument("--workers", type=int, default=7)
    p.add_argument("--inventory-only", action="store_true")
    p.add_argument("--output", default="netrattler_betclone_hardprobe.json")
    args = p.parse_args()
    result = run_scan(timeout=args.timeout, workers=args.workers, scan_sites=not args.inventory_only)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print("CATALOGUE", result["catalogue_families_retrieved"], "/", len(PAGES),
          "groups; primary brands", result["catalogue_total_listed_entries"],
          "extra historical names", result["historical_extra_entries"], flush=True)
    for family, r in sorted(result["catalogue"].items()):
        print("CATALOGUE_GROUP", family, r["count"], r["status"], flush=True)
    print("HOMEPAGES", result["sites_checked"], "STATUS", json.dumps(result["site_states"]), flush=True)
    for row in result["sites"]:
        print("SITE", row["platform"], row["brand"], row["http"], row["state"],
              "odds", row["verified_odds"], "host", row["final_host"], flush=True)


if __name__ == "__main__":
    main()
