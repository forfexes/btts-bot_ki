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
DENIAL_TEXT = ("captcha", "access denied", "just a moment",
               "verify you are human", "geo-block", "geo restricted")


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


def audit_page(browser, family: str, brand: str, url: str) -> dict:
    """One bounded browser visit, collecting aggregate evidence only."""
    result = {"platform": family, "brand": brand, "status": "not_checked",
              "json_responses": 0, "first_party_json": 0,
              "public_structured_price_candidates": 0, "verified_production_feed": False}
    context = browser.new_context(accept_downloads=False, service_workers="block")
    page = context.new_page()
    seen_responses = set()
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
        try:
            obj = response.json()
            mapped = audit_odds_json(obj)
            result["public_structured_price_candidates"] += min(
                500, int(mapped.get("verified_prices", 0)))
        except (ValueError, TypeError, RuntimeError):
            pass
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
                            if result["public_structured_price_candidates"]
                            else "rendered_without_verified_public_odds")
        return result
    except Exception as exc:
        result["status"] = "browser_error"
        result["error_type"] = type(exc).__name__
        return result
    finally:
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
          "validated_feeds=0", flush=True)


if __name__ == "__main__":
    main()
