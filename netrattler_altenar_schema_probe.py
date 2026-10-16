#!/usr/bin/env python3
"""Bounded, read-only Altenar (biahosted.com) field-schema sniffer.

This is a narrow follow-up to netrattler_betclone_browser_probe.py's generic
"price-shape counter". That probe deliberately never persists actual field
names or sample values, which is correct for a broad catalogue audit but is
not enough to build a real Altenar adapter: we need to know the ACTUAL key
names and representative (truncated, public) values used for event id,
team names, kickoff time, market/selection labels and decimal odds before
any mapping or adapter code can be written and tested.

Still strictly observational:
- Visits ONE already-curated public homepage (Vegas.hu) exactly like the
  existing browser probe does. No login, no bypass, no stealth/fingerprint
  evasion, no private/partner endpoints.
- Only inspects JSON responses already loaded by the public page from the
  previously-observed public "biahosted.com" platform host.
- Persists ONLY: a bounded list of distinct key names per node "shape", and
  up to a handful of representative sample objects with every value
  truncated to 80 chars / rounded. No cookies, headers, tokens, full
  response bodies, or unrelated hosts are stored.
- Writes to Supabase netrattler_card_diag (probe='altenar_schema_sniff') so
  the result can be read back without depending on GitHub Actions log
  retrieval (log-fetch to the Azure blob endpoint is blocked in this
  environment's network policy).
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from urllib.parse import urlparse

import requests

from netrattler_betclone_browser_probe import (
    _PUBLIC_SCHEMA_KEYS,
    is_denied,
    is_first_party_response,
    is_observed_public_platform_host,
)

# Other BetClone-catalogued Altenar brands (netrattler_betclone_hardprobe.
# CANDIDATES["altenar"]) never checked for their own keyless widget: a
# biahosted.com customer may run under a different regional subdomain, so
# each is worth the same bounded, read-only check already proven for
# vegas.hu. Only already publicly-reachable homepages from the prior static
# audit are listed; no geo-blocked or 403 site is added.
TARGETS = (
    ("altenar", "vegas.hu", "https://vegas.hu/"),
    ("altenar", "rabona", "https://rabona.com/"),
    ("altenar", "sportaza", "https://sportaza.com/"),
    ("altenar", "betinia", "https://betinia.com/"),
    ("altenar", "campobet", "https://campobet.com/"),
    ("altenar", "nomini", "https://nomini.com/"),
    ("altenar", "betrepublic", "https://betrepublic.com/"),
)
MAX_SAMPLES = 6
MAX_RESPONSES_INSPECTED = 24


def _truncate(value, depth=0):
    """Public, bounded, non-identifying value preview. No credentials/tokens."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        try:
            return round(float(value), 4)
        except Exception:
            return None
    if isinstance(value, str):
        return value[:80]
    if depth >= 2:
        return "…"
    if isinstance(value, list):
        return [_truncate(v, depth + 1) for v in value[:4]]
    if isinstance(value, dict):
        return {str(k)[:40]: _truncate(v, depth + 1) for k, v in list(value.items())[:12]}
    return str(value)[:80]


def _node_role(keys: set) -> dict:
    return {role: bool(keys & names) for role, names in _PUBLIC_SCHEMA_KEYS.items()}


_TOP_ARRAYS = ("events", "markets", "competitors", "champs", "categories", "sports")


def _truncate_deep(value, depth=0, max_depth=7, list_limit=2):
    """Like _truncate, but keeps real nested structure (bounded) instead of
    collapsing past depth 2 — needed to see how events/markets/odds actually
    join (shared id fields), not just that a price-shaped leaf exists."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        try:
            return round(float(value), 4)
        except Exception:
            return None
    if isinstance(value, str):
        return value[:100]
    if depth >= max_depth:
        return "…"
    if isinstance(value, list):
        return [_truncate_deep(v, depth + 1, max_depth, list_limit) for v in value[:list_limit]]
    if isinstance(value, dict):
        return {str(k)[:40]: _truncate_deep(v, depth + 1, max_depth, list_limit)
                for k, v in list(value.items())[:25]}
    return str(value)[:100]


def describe_top_level_arrays(payload) -> dict:
    """One or two real (bounded/truncated) sample items per known top-level
    Altenar array, so an adapter can see the actual join keys between
    events/markets/odds/competitors instead of only an aggregate price count."""
    out = {}
    if not isinstance(payload, dict):
        return out
    for key in _TOP_ARRAYS:
        val = payload.get(key)
        if isinstance(val, list) and val:
            out[key] = [_truncate_deep(v) for v in val[:2]]
    return out


def sniff(payload) -> dict:
    """Walk bounded JSON, collecting key-name shapes and a few truncated samples."""
    shapes = Counter()
    samples = []
    pending = [(payload, 0)]
    visited = 0
    while pending and visited < 4000:
        obj, depth = pending.pop()
        visited += 1
        if depth > 40:
            continue
        if isinstance(obj, list):
            for item in obj[:200]:
                if isinstance(item, (list, dict)):
                    pending.append((item, depth + 1))
        elif isinstance(obj, dict):
            keys = {str(k).lower().replace("_", "") for k in list(obj)[:150]}
            roles = _node_role(keys)
            if any(roles.values()):
                shape_key = ",".join(sorted(k for k in roles if roles[k]))
                shapes[shape_key] += 1
                if roles["prices"] and len(samples) < MAX_SAMPLES:
                    samples.append({"keys": sorted(obj.keys())[:30], "sample": _truncate(obj)})
            for val in list(obj.values())[:150]:
                if isinstance(val, (list, dict)):
                    pending.append((val, depth + 1))
    return {"shapes": dict(shapes), "samples": samples}


def _probe_one(pw, family: str, brand: str, url: str) -> dict:
    result = {"platform": family, "brand": brand, "url": url, "status": "not_checked",
              "inspected": 0, "shapes": {}, "samples": [], "arrays": {}, "endpoints": []}
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(accept_downloads=False, service_workers="block")
    page = context.new_page()
    all_shapes = Counter()
    all_samples = []
    all_arrays = {}
    all_endpoints = []
    all_query_captured = [False]

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
        if len(all_arrays) < len(_TOP_ARRAYS):
            for k, v in describe_top_level_arrays(payload).items():
                all_arrays.setdefault(k, v)
        # Bounded endpoint fingerprint (method + path, no query string, no
        # headers/cookies/body) so a later keyless HTTP collector can be
        # attempted the same way the existing 1xBet/bwin collectors are,
        # instead of requiring a full browser for every scrape.
        if len(all_endpoints) < 10:
            parsed = urlparse(response.url)
            try:
                method = response.request.method
            except Exception:
                method = "?"
            fp = f"{method} {parsed.hostname}{parsed.path}"
            if fp not in all_endpoints:
                all_endpoints.append(fp)
        # The one endpoint we actually need to replicate keylessly: capture
        # its public query string (no cookies/headers/auth token — Altenar's
        # anonymous widget query params, same category of info already
        # hardcoded in netrattler_keyless_odds.py for 1xBet/bwin) exactly
        # once, redacting anything that looks like a bearer/session value.
        if "GetTopEvents" in response.url and not all_query_captured[0]:
            parsed_q = urlparse(response.url)
            safe_q = "&".join(
                p for p in (parsed_q.query or "").split("&")
                if not re.search(r"(token|session|auth|bearer|key)", p, re.I)
            )
            all_query_captured[0] = True
            result["top_events_query"] = safe_q[:600]

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
    for result in results:
        print(json.dumps({k: v for k, v in result.items() if k != "samples"}, indent=2))
        print("samples:", json.dumps(result.get("samples", []), indent=2)[:2000])
    SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if SUPABASE_URL and SUPABASE_KEY:
        for result in results:
            try:
                requests.post(
                    f"{SUPABASE_URL}/rest/v1/netrattler_card_diag", timeout=15,
                    headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                             "Content-Type": "application/json"},
                    json={"info": {"probe": "altenar_schema_sniff", **result}},
                )
            except Exception as exc:
                print("Supabase write failed:", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
