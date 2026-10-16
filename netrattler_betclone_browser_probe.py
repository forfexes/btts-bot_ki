#!/usr/bin/env python3
"""Read-only Playwright probe for curated PUBLIC BetClone-listed operator homepages.

The browser can render accessible JS content, but is not used to circumvent
authentication, CAPTCHAs, geo-restrictions, or access denials. A structured
price candidate is not a validated, production-ready odds feed.

No cookies, credentials, page HTML, tokens, request queries or JSON bodies are
persisted. This is an observational audit, never a live-tip source.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from collections import Counter
import json
from pathlib import Path
from urllib.parse import urljoin, urlparse

from netrattler_betclone_hardprobe import audit_odds_json

# Curated operator homepages previously returning HTTP 200 in the static audit.
# Blocked or restricted websites are excluded, without mirrors or proxies.
# Curated sites with a recent unauthenticated HTTP 200 in the BetClone
# homepage audit. Never add 403/429/challenge sites, guessed mirror domains or
# affiliate redirects. This is a public browser audit only, not an odds scraper.
CANDIDATES = (
    ("betby", "tonybet", "https://tonybet.com/"),
    ("betconstruct", "vbet", "https://www.vbet.com/"),
    ("first", "bk8", "https://www.bk8sports.com/en"),
    ("softswiss", "metaspins", "https://metaspins.com/"),
    ("altenar", "betinia", "https://betinia.com/"),
    ("betby", "gamdom", "https://gamdom.com/"),
    ("betconstruct", "olybet", "https://olybet.com/"),
    ("betconstruct", "fastbet", "https://fastbet.com/"),
    ("inplaynet", "rolletto", "https://rolletto.com/"),
    ("softswiss", "wild.io", "https://wild.io/"),
    # Already HTTP 200 in the public-site audit; more family coverage.
    # These are public homepages, NOT verified football odds feeds.
    ("igate", "spinlynx", "https://spinlynx.com/"),
    ("altenar", "vegas.hu", "https://vegas.hu/"),
    ("inplaynet", "cosmobet", "https://cosmobet.com/"),
    ("betby", "vave", "https://vave.com/"),
)
# Provider-related hosts were OBSERVED in a public Chromium network trace;
# these suffixes are not permission to call private/partner endpoints.
OBSERVED_HOSTED_PLATFORM_SUFFIXES = {
    "inplaynet": ("inplaynet.tech",),
    "altenar": ("biahosted.com",),
}
DENIAL_TEXT = ("captcha", "access denied", "just a moment",
               "verify you are human", "geo-block", "geo restricted")


def public_response_host_only(url: str) -> str | None:
    """Return only the hostname, never credentials, paths or query parameters."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or len(host) > 160:
        return None
    return host


def is_observed_public_platform_host(platform: str, response_url: str) -> bool:
    """Allow bounded analysis of public JSON actually loaded by the operator page."""
    hostname = public_response_host_only(response_url)
    return bool(hostname and any(
        hostname == suffix or hostname.endswith("." + suffix)
        for suffix in OBSERVED_HOSTED_PLATFORM_SUFFIXES.get(platform, ())
    ))


def is_first_party_response(page_url: str, response_url: str) -> bool:
    """Only inspect public JSON returned by the operator's own host family."""
    page_host = (urlparse(page_url).hostname or "").lower().removeprefix("www.")
    response_host = (urlparse(response_url).hostname or "").lower().removeprefix("www.")
    return bool(page_host and response_host and
                (response_host == page_host or response_host.endswith("." + page_host)))


def first_party_sports_link(homepage: str, hrefs: list[str]) -> str | None:
    """Find at most one explicitly published sportsbook link; no URL guessing."""
    for href in hrefs[:120]:
        if not isinstance(href, str) or not href:
            continue
        target = urljoin(homepage, href)
        parsed = urlparse(target)
        if (parsed.scheme == "https" and
                is_first_party_response(homepage, target) and
                "sport" in parsed.path.lower() and
                parsed.path.strip("/").lower() != "sportsbook-terms"):
            # Strip query and fragment, including transient signed parameters.
            return parsed._replace(query="", fragment="").geturl()
    return None


def is_denied(status: int, body: str) -> bool:
    return status in (401, 403, 407, 429, 451) or any(
        term in (body or "").lower()[:4000] for term in DENIAL_TEXT)


# Fixed allow-list: diagnostics record neither JSON values nor arbitrary keys.
# Normalize underscores/hyphens/case before counting schema roles.
_PUBLIC_SCHEMA_KEYS = {
    "events": {"event", "events", "eventid", "eventname", "fixture",
               "fixtures", "fixtureid", "match", "matches", "matchid",
               "hometeam", "awayteam", "participants"},
    "markets": {"market", "markets", "marketid", "marketname", "bettype",
                "betoffer", "betoffers", "optionmarkets", "markettype",
                "bettingmarkets", "marketgroup", "marketgroups"},
    "selections": {"selection", "selections", "outcome", "outcomes",
                   "options", "bets", "runners", "participants"},
    "prices": {"odds", "decimalodds", "decimalprice", "price",
               "coefficient", "fixedodds", "europeanodds"},
    "sports": {"sport", "sports", "sportid", "league", "leagues",
               "tournament", "tournaments", "competition"},
}


def sports_json_shape_signals(payload) -> dict[str, int]:
    """Bounded, value-free market anatomy: raw prices vs valid quote context.

    Count only fixed structural roles, never market names, prices, users, links,
    request headers, query strings, or arbitrary JSON keys.
    """
    hits: Counter = Counter()
    nodes = [(payload, False, False, False)]
    inspected = 0
    label_fields = {
        "name", "label", "title", "outcomename", "selectionname",
        "optionname", "runnername", "participantname", "competitorname",
    }
    def decimal_quote(value):
        # Only decimal odds, never probabilities, booleans, floats in
        # unrelated "price" structures, or any nested raw data.
        if isinstance(value, bool) or isinstance(value, (list, dict)):
            return False
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return False
        return 1.0001 < number <= 100.0

    while nodes and inspected < 1200:
        item, event_parent, market_parent, sport_parent = nodes.pop()
        inspected += 1
        if isinstance(item, list):
            nodes.extend((child, event_parent, market_parent, sport_parent)
                         for child in item[:100])
        elif isinstance(item, dict):
            keys = {
                "".join(c for c in str(k).lower() if c.isalnum())
                for k in list(item)[:100]
            }
            matched = {role: bool(keys & names)
                       for role, names in _PUBLIC_SCHEMA_KEYS.items()}
            for role, present in matched.items():
                if present:
                    hits[role] += 1
            event_ctx = event_parent or matched["events"]
            market_ctx = market_parent or matched["markets"]
            sport_ctx = sport_parent or matched["sports"]
            if matched["prices"]:
                price_values = [
                    value for key, value in list(item.items())[:100]
                    if "".join(c for c in str(key).lower() if c.isalnum())
                    in _PUBLIC_SCHEMA_KEYS["prices"]
                ]
                if any(decimal_quote(value) for value in price_values):
                    hits["plausible_decimal_price_fields"] += 1
                    if event_ctx and market_ctx and keys & label_fields:
                        hits["plausible_decimal_full_context"] += 1
                        # Whitelisted field names only; no values or arbitrary keys.
                        for label_key in sorted(label_fields & keys):
                            hits["full_context_label_" + label_key] += 1
                        for price_key in sorted(_PUBLIC_SCHEMA_KEYS["prices"] & keys):
                            hits["full_context_price_" + price_key] += 1
                if event_ctx:
                    hits["priced_with_event"] += 1
                if market_ctx:
                    hits["priced_with_market"] += 1
                if sport_ctx:
                    hits["priced_with_sports"] += 1
                if keys & label_fields:
                    hits["priced_with_label"] += 1
                    if event_ctx and market_ctx:
                        hits["priced_complete_context"] += 1
            nodes.extend((child, event_ctx, market_ctx, sport_ctx)
                         for child in list(item.values())[:100])
    names = [*_PUBLIC_SCHEMA_KEYS, "priced_with_event", "priced_with_market",
             "priced_with_sports", "priced_with_label",
             "priced_complete_context", "plausible_decimal_price_fields",
             "plausible_decimal_full_context"]
    names += ["full_context_label_" + key for key in sorted(label_fields)]
    names += ["full_context_price_" + key for key in sorted(_PUBLIC_SCHEMA_KEYS["prices"])]
    return {role: min(1200, hits[role]) for role in names}


def public_response_evidence(response) -> dict | None:
    """Extract only diagnostic counts from already-loaded, unauthenticated JSON."""
    try:
        payload = response.json()
        return {"prices": min(500, int(audit_odds_json(payload).get("verified_prices", 0))),
                "shape": sports_json_shape_signals(payload)}
    except Exception:
        return None


def public_response_price_count(response) -> int | None:
    """Read an already-observed public JSON reply without leaking missing-body errors.

    Navigation may evict Chrome's Network.getResponseBody; unavailable data is
    NOT a zero-odds source and is never silently treated as a valid feed.
    """
    evidence = public_response_evidence(response)
    return evidence["prices"] if evidence is not None else None


def audit_page(browser, family: str, brand: str, url: str) -> dict:
    """One bounded browser visit, collecting aggregate evidence only."""
    result = {"platform": family, "brand": brand, "status": "not_checked",
              "json_responses": 0, "first_party_json": 0,
              "public_structured_price_candidates": 0, "verified_production_feed": False,
              "external_json_hosts": [], "hosted_json_inspected": 0,
              "hosted_structured_price_candidates": 0,
              "unavailable_json_bodies": 0,
              "hosted_schema_signals": {
                  role: 0 for role in sports_json_shape_signals(None)
              }}
    context = browser.new_context(accept_downloads=False, service_workers="block")
    page = context.new_page()
    seen_responses = set()
    external_json_host_counts: dict[str, int] = {}
    def inspect_response(response):
        if len(seen_responses) >= 35 or response.status != 200:
            return
        if "json" not in str(response.headers.get("content-type") or "").lower():
            return
        result["json_responses"] += 1
        # A public homepage can redirect to its canonical operator domain.
        # Only the actual browser-rendered navigation origin, never an
        # arbitrary third-party JSON host, is allowed for payload inspection.
        origin = page.url if (urlparse(page.url).scheme == "https") else url
        if not is_first_party_response(origin, response.url):
            # Hosted sportsbook frontends may receive public JSON from a
            # different domain. Record ONLY a bounded hostname/count so the
            # provider can be reviewed without collecting private payloads.
            host = public_response_host_only(response.url)
            if host and (host in external_json_host_counts or len(external_json_host_counts) < 48):
                external_json_host_counts[host] = external_json_host_counts.get(host, 0) + 1
            # Only inspect the JSON of observed platform-host responses that
            # were already fetched by this anonymous public web page.
            # No direct API calls, request headers, cookies, or JSON bodies saved.
            if (is_observed_public_platform_host(family, response.url)
                    and result["hosted_json_inspected"] < 32):
                clen = response.headers.get("content-length")
                try:
                    if clen and int(clen) > 220_000:
                        return
                except (ValueError, TypeError):
                    return
                result["hosted_json_inspected"] += 1
                evidence = public_response_evidence(response)
                if evidence is None:
                    result["unavailable_json_bodies"] += 1
                else:
                    result["hosted_structured_price_candidates"] += evidence["prices"]
                    for role, count in evidence["shape"].items():
                        result["hosted_schema_signals"][role] += count
            return
        if len(seen_responses) >= 16:
            return
        clen = response.headers.get("content-length")
        if clen:
            try:
                if int(clen) > 220_000:
                    return
            except ValueError:
                return
        seen_responses.add(id(response))
        result["first_party_json"] += 1
        observed = public_response_price_count(response)
        if observed is None:
            result["unavailable_json_bodies"] += 1
        else:
            result["public_structured_price_candidates"] += observed
    page.on("response", inspect_response)
    try:
        navigation = page.goto(url, wait_until="domcontentloaded", timeout=12000)
        if navigation is None:
            result["status"] = "no_navigation"
            return result
        if navigation.status in (401, 403, 407, 429, 451):
            result["status"] = "access_denied"
            return result
        if navigation.status >= 400:
            result["status"] = "http_error"
            return result
        # A redirected page may be a different public brand host; report this
        # without storing its URL, assuming ownership, or validating odds.
        result["redirected_to_other_host"] = not is_first_party_response(url, page.url)
        # A JS shell may populate public odds after the initial page response.
        page.wait_for_timeout(2000)
        title = page.title()
        body = page.locator("body").inner_text(timeout=2500)[:4000]
        if is_denied(navigation.status, title + " " + body):
            result["status"] = "restricted_or_challenge"
            return result
        # Navigate ONE genuine on-site sports link, when advertised publicly.
        # Landing pages often expose only login and promotions, not betting odds.
        hrefs = page.locator("a[href]").evaluate_all(
            "(anchors) => anchors.slice(0, 120).map(a => a.getAttribute('href'))")
        sports_url = first_party_sports_link(page.url, hrefs)
        if sports_url:
            result["public_sports_link_found"] = True
            try:
                sports_navigation = page.goto(sports_url, wait_until="domcontentloaded", timeout=10000)
                if sports_navigation and sports_navigation.status in (401, 403, 407, 429, 451):
                    result["status"] = "sports_page_access_denied"
                    return result
                page.wait_for_timeout(1500)
                if is_denied(sports_navigation.status if sports_navigation else 0,
                             page.locator("body").inner_text(timeout=2000)[:3000]):
                    result["status"] = "sports_page_restricted_or_challenge"
                    return result
            except Exception:
                result["sports_page_error"] = True
        result["status"] = ("candidate_prices_require_independent_market_validation"
                            if (result["public_structured_price_candidates"]
                                or result["hosted_structured_price_candidates"])
                            else "rendered_without_verified_public_odds")
        return result
    except Exception as exc:
        result["status"] = "browser_error"
        result["error_type"] = type(exc).__name__
        return result
    finally:
        result["external_json_hosts"] = [
            {"host": h, "json_responses": n}
            for h, n in sorted(external_json_host_counts.items(),
                               key=lambda pair: (-pair[1], pair[0]))[:8]
        ]
        context.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="netrattler_betclone_browser_probe.json")
    parser.add_argument("--limit", type=int, default=len(CANDIDATES))
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright
    rows = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            for family, brand, url in CANDIDATES[:max(0, min(args.limit, len(CANDIDATES)))]:
                row = audit_page(browser, family, brand, url)
                rows.append(row)
                print("BETCLONE_BROWSER", json.dumps(row, ensure_ascii=False), flush=True)
        finally:
            browser.close()
    report = {"checked_utc": datetime.now(timezone.utc).isoformat(),
              "mode": "public_render_only_not_a_live_feed",
              "checked": len(rows), "results": rows,
              "validated_new_production_feeds": 0}
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("BETCLONE_BROWSER_SUMMARY checked=", len(rows),
          "price_candidates=", sum(row["public_structured_price_candidates"] for row in rows),
          "hosted_candidates=", sum(row["hosted_structured_price_candidates"] for row in rows),
          "validated_feeds=0", flush=True)


if __name__ == "__main__":
    main()
