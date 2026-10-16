#!/usr/bin/env python3
"""Bounded, read-only InPlayNet (sportservice.inplaynet.tech) field-schema sniffer.

Same rationale and same safety bounds as netrattler_altenar_schema_probe.py:
the generic BetClone browser probe already established that Rolletto and
Cosmobet generate many public JSON responses from an inplaynet.tech host,
but (by design) never persists field names or sample values -- only a
price-shape count. This narrow follow-up visits the same curated public
homepages and, for responses already observed from the allowlisted
inplaynet.tech host, records bounded key-name shapes, a handful of
value-truncated samples, and a bounded endpoint fingerprint (method+path,
then once the real query string for the first "events"-shaped hit) --
exactly like the Altenar probe, so a real market mapping can be attempted
without declaring anything an integrated feed first.

No login, no bypass, no stealth, no private/partner endpoints. No cookies,
headers, tokens or full response bodies are persisted.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from urllib.parse import urlparse

import requests

from netrattler_altenar_schema_probe import _truncate, describe_top_level_arrays, sniff
from netrattler_betclone_browser_probe import is_denied, is_first_party_response, is_observed_public_platform_host

TARGETS = (
    ("inplaynet", "rolletto", "https://rolletto.com/"),
    ("inplaynet", "cosmobet", "https://cosmobet.com/"),
)
MAX_SAMPLES = 6
MAX_RESPONSES_INSPECTED = 24


def _probe_one(pw, family: str, brand: str, url: str) -> dict:
    result = {"platform": family, "brand": brand, "url": url, "status": "not_checked",
              "inspected": 0, "shapes": {}, "samples": [], "arrays": {}, "endpoints": [],
              "top_events_query": None}
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(accept_downloads=False, service_workers="block")
    page = context.new_page()
    all_shapes = Counter()
    all_samples = []
    all_arrays = {}
    all_endpoints = []
    query_captured = [False]

    def inspect_response(response):
        if result["inspected"] >= MAX_RESPONSES_INSPECTED or response.status != 200:
            return
        if "json" not in str(response.headers.get("content-type") or "").lower():
            return
        if not is_observed_public_platform_host(family, response.url):
            return
        clen = response.headers.get("content-length")
        try:
            if clen and int(clen) > 400_000:
                return
        except (ValueError, TypeError):
            return
        try:
            payload = response.json()
        except Exception:
            return
        result["inspected"] += 1
        sniffed = sniff(payload)
        for shape, n in sniffed["shapes"].items():
            all_shapes[shape] += n
        for s in sniffed["samples"]:
            if len(all_samples) < MAX_SAMPLES:
                all_samples.append(s)
        if len(all_arrays) < 8:
            for k, v in describe_top_level_arrays(payload).items():
                all_arrays.setdefault(k, v)
        if len(all_endpoints) < 10:
            parsed = urlparse(response.url)
            try:
                method = response.request.method
            except Exception:
                method = "?"
            fp = f"{method} {parsed.hostname}{parsed.path}"
            if fp not in all_endpoints:
                all_endpoints.append(fp)
        if sniffed["shapes"] and not query_captured[0]:
            parsed_q = urlparse(response.url)
            safe_q = "&".join(
                p for p in (parsed_q.query or "").split("&")
                if not re.search(r"(token|session|auth|bearer|key)", p, re.I)
            )
            query_captured[0] = True
            result["top_events_query"] = {"path": parsed_q.path, "query": safe_q[:600]}

    page.on("response", inspect_response)
    try:
        navigation = page.goto(url, wait_until="domcontentloaded", timeout=15000)
        if navigation is None:
            result["status"] = "no_navigation"
            return result
        if navigation.status in (401, 403, 407, 429, 451):
            result["status"] = "access_denied"
            return result
        page.wait_for_timeout(3000)
        body = page.locator("body").inner_text(timeout=2500)[:4000]
        if is_denied(navigation.status, page.title() + " " + body):
            result["status"] = "restricted_or_challenge"
            return result
        hrefs = page.locator("a[href]").evaluate_all(
            "(anchors) => anchors.slice(0, 120).map(a => a.getAttribute('href'))")
        sports_url = None
        for href in hrefs or []:
            if href and any(tok in href.lower() for tok in ("sport", "football", "soccer")):
                if href.startswith("http") and is_first_party_response(url, href):
                    sports_url = href
                    break
        if sports_url:
            try:
                page.goto(sports_url, wait_until="domcontentloaded", timeout=12000)
                page.wait_for_timeout(2500)
            except Exception:
                pass
        result["status"] = "ok" if result["inspected"] else "no_hosted_json_observed"
    except Exception as exc:
        result["status"] = "browser_error"
        result["error_type"] = type(exc).__name__
    finally:
        result["shapes"] = dict(all_shapes)
        result["samples"] = all_samples
        result["arrays"] = all_arrays
        result["endpoints"] = all_endpoints
        context.close()
        browser.close()
    return result


def run() -> list:
    from playwright.sync_api import sync_playwright
    results = []
    with sync_playwright() as pw:
        for family, brand, url in TARGETS:
            results.append(_probe_one(pw, family, brand, url))
    return results


def main() -> int:
    results = run()
    for r in results:
        print(json.dumps({k: v for k, v in r.items() if k != "samples"}, indent=2))
    SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if SUPABASE_URL and SUPABASE_KEY:
        for r in results:
            try:
                requests.post(
                    f"{SUPABASE_URL}/rest/v1/netrattler_card_diag", timeout=15,
                    headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                             "Content-Type": "application/json"},
                    json={"info": {"probe": "inplaynet_schema_sniff", **r}},
                )
            except Exception as exc:
                print("Supabase write failed:", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
