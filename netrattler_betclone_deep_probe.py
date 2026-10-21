#!/usr/bin/env python3
"""BetClone deep probe v2: which PUBLIC data endpoints does each operator's own
sports page load, and do they carry football prices?

Why v2: the 2026-10-16/18 audit found "no feed" for 7 families, but it only
waited ~2 s on the HOMEPAGE, inspected JSON bodies only from the operator's own
host (sportsbooks are usually served from a platform host or an iframe), skipped
every body > 220 KB (odds lists are big) and ignored WebSocket feeds.

v2 visits the operator's public sports/football page like a normal visitor,
waits for the sportsbook to render, and records — per endpoint *template*
(host + path with ids replaced, never the query string) — how many responses
carry decimal-price structures, the top-level key names and one small,
truncated sample object, so an adapter can be designed (the same way the
Altenar adapter was built). WebSocket frames are summarised the same way.

Rules (unchanged): plain headless Chromium, no stealth/fingerprint evasion,
no login, cookies or tokens stored, no proxy/VPN/captcha handling. A 401/403/
429/451 or challenge page ends that brand immediately. An observed endpoint is
evidence for review, never an automatically enabled odds source.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from netrattler_betclone_hardprobe import CANDIDATES as HARD_CANDIDATES

DENIAL_TEXT = ("captcha", "access denied", "just a moment", "verify you are human",
               "attention required", "geo-block", "geo restricted", "not available in your country")
SPORT_PATHS = ("/sports", "/sport", "/en/sports", "/sportsbook", "/betting", "/en/sport")
FOOTBALL_TEXT = re.compile(r"^\s*(football|soccer|fu(ss|ß)ball)\s*$", re.I)
PRICE_KEYS = {"odds", "price", "coef", "coefficient", "k", "c", "decimal", "decimalodds",
              "oddsvalue", "rate", "value", "odd", "cf", "kf"}
CONTEXT_KEYS = {"id", "name", "n", "type", "typeid", "t", "label", "title", "outcome", "selection",
                "market", "marketid", "eventid", "matchid", "competitor", "team", "line", "p", "sv",
                "handicap", "outcomeid", "selectionid", "oddid", "betid"}
SECRET_KEY = re.compile(r"token|session|auth|passw|cookie|email|phone|user|account|balance|wallet|jwt|sign", re.I)
MAX_BODY = 4_000_000
MAX_ENDPOINTS = 10


def norm_key(k: Any) -> str:
    return "".join(ch for ch in str(k).lower() if ch.isalnum())


def path_template(url: str) -> Tuple[str, str]:
    """(host, path) with numbers / long hex / uuids replaced; query and fragment dropped."""
    u = urlparse(url)
    host = (u.hostname or "").lower()
    parts = []
    for seg in (u.path or "/").split("/"):
        if re.fullmatch(r"\d+", seg):
            seg = "{n}"
        elif re.fullmatch(r"[0-9a-f]{12,}", seg, re.I) or re.fullmatch(r"[0-9a-f-]{32,36}", seg, re.I):
            seg = "{h}"
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", seg):
            seg = "{d}"
        parts.append(seg)
    return host, "/".join(parts)[:160] or "/"


def _is_price(v: Any) -> bool:
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        return False
    try:
        x = float(v)
    except (TypeError, ValueError):
        return False
    return 1.01 <= x <= 60.0 and not (isinstance(v, int) and x in (2, 3))  # bare ints 2/3 are usually enums


def price_signals(payload: Any, budget: int = 40000) -> Dict[str, Any]:
    """Count dicts that look like a priced selection: a price-like key with a decimal value
    plus at least one identifying/context key. Returns counts and one truncated sample."""
    priced, seen = 0, 0
    sample: Optional[Dict[str, Any]] = None
    stack = [payload]
    while stack and seen < budget:
        node = stack.pop()
        seen += 1
        if isinstance(node, list):
            stack.extend(node[:400])
        elif isinstance(node, dict):
            keys = {norm_key(k): k for k in list(node)[:80]}
            price_hits = [k for nk, k in keys.items() if nk in PRICE_KEYS and _is_price(node.get(k))]
            if price_hits and (set(keys) & CONTEXT_KEYS):
                priced += 1
                if sample is None:
                    sample = safe_sample(node)
            stack.extend(v for v in list(node.values())[:80] if isinstance(v, (dict, list)))
    return {"priced": priced, "sample": sample}


def safe_sample(obj: Dict[str, Any], max_keys: int = 14) -> Dict[str, Any]:
    out = {}
    for k, v in list(obj.items())[:max_keys]:
        if SECRET_KEY.search(str(k)):
            continue
        if isinstance(v, (dict, list)):
            out[str(k)[:30]] = f"<{type(v).__name__}:{len(v)}>"
        else:
            out[str(k)[:30]] = str(v)[:40]
    return out


def top_keys(payload: Any) -> List[str]:
    if isinstance(payload, dict):
        return [str(k)[:30] for k in list(payload)[:15] if not SECRET_KEY.search(str(k))]
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return ["[]"] + [str(k)[:30] for k in list(payload[0])[:14] if not SECRET_KEY.search(str(k))]
    return []


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def decimal_key_paths(payload: Any, budget: int = 60000) -> Dict[str, int]:
    """Key paths (list indices -> []) whose values look like decimal odds: non-integer 1.01..60.
    Finds price fields whatever they are called ("Cotizacion", "k", "coef" ...)."""
    out: Dict[str, int] = {}
    stack = [(payload, "")]
    seen = 0
    while stack and seen < budget:
        node, path = stack.pop()
        seen += 1
        if isinstance(node, list):
            stack.extend((x, path + "[]") for x in node[:300])
        elif isinstance(node, dict):
            for k, v in list(node.items())[:120]:
                if SECRET_KEY.search(str(k)):
                    continue
                kp = f"{path}.{str(k)[:30]}"
                if isinstance(v, (dict, list)):
                    stack.append((v, kp))
                else:
                    x = _num(v)
                    if x is not None and 1.01 <= x <= 60 and abs(x - round(x)) > 1e-9:
                        if re.search(r"\d{2,}", str(k)) and len(out) > 40:
                            continue
                        out[kp] = out.get(kp, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1])[:12])


def skeleton(node: Any, depth: int = 0, max_depth: int = 6) -> Any:
    """Structure with keys and one example per list; values truncated; no secret keys."""
    if depth >= max_depth:
        return "..."
    if isinstance(node, dict):
        return {str(k)[:30]: skeleton(v, depth + 1, max_depth)
                for k, v in list(node.items())[:14] if not SECRET_KEY.search(str(k))}
    if isinstance(node, list):
        return [skeleton(node[0], depth + 1, max_depth), f"<{len(node)}>"] if node else []
    return str(node)[:30]


def is_denied(status: int, text: str) -> bool:
    low = (text or "").lower()[:5000]
    return status in (401, 403, 407, 429, 451) or any(t in low for t in DENIAL_TEXT)


class Collector:
    def __init__(self) -> None:
        self.endpoints: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        self.json_responses = 0
        self.ws_hosts: Dict[str, Dict[str, Any]] = {}

    def add_json(self, url: str, payload: Any, size: int, kind: str = "http") -> None:
        host, path = path_template(url)
        key = (kind, host, path)
        sig = price_signals(payload)
        e = self.endpoints.setdefault(key, {"kind": kind, "host": host, "path": path, "n": 0, "bytes": 0,
                                            "max_priced": 0, "top_keys": top_keys(payload), "sample": None,
                                            "decimal_paths": {}, "skeleton": None, "_best_dec": 0})
        e["n"] += 1
        e["bytes"] += size
        if size >= 5000 and not re.search(r"config|translation|countr|currenc|banner|casino|promo|seo|i18n|geoloc", path, re.I):
            dp = decimal_key_paths(payload)
            tot = sum(dp.values())
            if tot > e["_best_dec"]:
                e["_best_dec"] = tot
                e["decimal_paths"] = dp
                e["skeleton"] = skeleton(payload)
        if sig["priced"] > e["max_priced"]:
            e["max_priced"] = sig["priced"]
            e["sample"] = sig["sample"]
            e["top_keys"] = top_keys(payload)

    def summary(self) -> List[Dict[str, Any]]:
        rows = sorted(self.endpoints.values(), key=lambda e: (-e["max_priced"], -e["_best_dec"], -e["bytes"]))
        out = []
        for i, e in enumerate(rows[:MAX_ENDPOINTS]):
            e = dict(e)
            e["decimal_values"] = e.pop("_best_dec")
            if i >= 4 or not e["decimal_values"]:
                e["skeleton"] = None  # keep the diagnostic row small
            out.append(e)
        return out


def probe_brand(browser, family: str, brand: str, url: str, settle_s: float = 8.0) -> Dict[str, Any]:
    res: Dict[str, Any] = {"family": family, "brand": brand, "status": "not_checked"}
    col = Collector()
    ctx = browser.new_context(accept_downloads=False, service_workers="block", locale="en-GB",
                              viewport={"width": 1366, "height": 900})
    page = ctx.new_page()

    def on_response(r):
        try:
            if r.status != 200:
                return
            ctype = str(r.headers.get("content-type") or "").lower()
            if "json" not in ctype:
                return
            clen = r.headers.get("content-length")
            if clen and int(clen) > MAX_BODY:
                return
            col.json_responses += 1
            body = r.body()
            if len(body) > MAX_BODY:
                return
            col.add_json(r.url, json.loads(body.decode("utf-8", "replace")), len(body))
        except Exception:
            return

    def on_ws(ws):
        host, path = path_template(ws.url)
        info = col.ws_hosts.setdefault(host, {"path": path, "frames": 0, "json_frames": 0})

        def frame(payload):
            info["frames"] += 1
            if info["json_frames"] >= 25 or not isinstance(payload, str) or len(payload) > MAX_BODY:
                return
            txt = payload.strip()
            # some feeds prefix frames (e.g. "42[...]" socket.io)
            m = re.match(r"^\d*([\[{].*)$", txt, re.S)
            if not m:
                return
            try:
                data = json.loads(m.group(1))
            except Exception:
                return
            info["json_frames"] += 1
            col.add_json(ws.url, data, len(txt), kind="ws")
        ws.on("framereceived", frame)

    page.on("response", on_response)
    page.on("websocket", on_ws)
    t0 = time.time()
    try:
        nav = page.goto(url, wait_until="domcontentloaded", timeout=20000)
        if nav is None:
            res["status"] = "no_navigation"; return res
        page.wait_for_timeout(2500)
        if is_denied(nav.status, page.title() + " " + page.locator("body").inner_text(timeout=4000)[:5000]):
            res["status"] = "access_denied_or_challenge"; return res
        base = page.url
        # 1) an advertised sports link on the operator's own site, else common public paths
        hrefs = page.locator("a[href]").evaluate_all("(a) => a.slice(0, 300).map(x => x.getAttribute('href'))")
        target = None
        bh = (urlparse(base).hostname or "").removeprefix("www.")
        for h in hrefs or []:
            if not isinstance(h, str):
                continue
            t = urljoin(base, h)
            p = urlparse(t)
            th = (p.hostname or "").removeprefix("www.")
            if p.scheme == "https" and (th == bh or th.endswith("." + bh)) and re.search(r"sport|betting", p.path, re.I) \
                    and not re.search(r"terms|rules|promo|bonus|casino|virtual|esport|live", p.path, re.I):
                target = p._replace(query="", fragment="").geturl()
                break
        tried = [target] if target else [urljoin(base, x) for x in SPORT_PATHS]
        reached = None
        for t in tried[:6]:
            try:
                n2 = page.goto(t, wait_until="domcontentloaded", timeout=20000)
            except Exception:
                continue
            if n2 is None or n2.status >= 400:
                continue
            page.wait_for_timeout(1500)
            if is_denied(n2.status, page.locator("body").inner_text(timeout=4000)[:5000]):
                res["status"] = "sports_page_denied_or_challenge"; return res
            reached = urlparse(page.url).path[:80]
            break
        res["sports_path"] = reached
        page.wait_for_timeout(int(settle_s * 1000))
        # 2) open the football section if a plain link/button says so
        try:
            loc = page.get_by_text(FOOTBALL_TEXT).first
            if loc and loc.is_visible(timeout=1500):
                loc.click(timeout=3000)
                res["football_clicked"] = True
                page.wait_for_timeout(int(settle_s * 1000))
        except Exception:
            pass
        try:
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(3000)
        except Exception:
            pass
        res["status"] = "rendered"
        return res
    except Exception as exc:
        res["status"] = "browser_error"
        res["error"] = type(exc).__name__
        return res
    finally:
        res["seconds"] = round(time.time() - t0, 1)
        res["json_responses"] = col.json_responses
        res["endpoints"] = col.summary()
        res["websockets"] = [{"host": h, **v} for h, v in list(col.ws_hosts.items())[:6]]
        res["best_priced"] = max([e["max_priced"] for e in res["endpoints"]] or [0])
        res["best_decimal_values"] = max([e["decimal_values"] for e in res["endpoints"]] or [0])
        try:
            ctx.close()
        except Exception:
            pass


def targets(family: str = "", brands: str = "") -> List[Tuple[str, str, str]]:
    want = {b.strip().lower() for b in brands.split(",") if b.strip()}
    out = []
    for fam, brands in HARD_CANDIDATES.items():
        if fam == "1xbet":
            continue  # already integrated through its public LineFeed
        if family and fam != family:
            continue
        out.extend((fam, b, u) for b, u in brands if not want or b.lower() in want)
    return out


def post_diag(row: Dict[str, Any]) -> None:
    sb = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if not sb or not key:
        return
    import requests
    try:
        requests.post(f"{sb}/rest/v1/netrattler_card_diag", timeout=20,
                      headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      json={"info": {"probe": "betclone_deep_probe", **row}})
    except Exception as exc:
        print("diag write failed", exc)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="")
    ap.add_argument("--settle", type=float, default=8.0)
    ap.add_argument("--brands", default="")
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            for fam, brand, url in targets(args.family, args.brands):
                row = probe_brand(browser, fam, brand, url, settle_s=args.settle)
                row["checked_utc"] = datetime.now(timezone.utc).isoformat()
                print("BETCLONE_DEEP", json.dumps(row, ensure_ascii=False)[:3000], flush=True)
                post_diag(row)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
