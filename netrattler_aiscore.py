#!/usr/bin/env python3
"""NETRATTLER AiScore public collector (keyless, conservative).

AiScore is used for public H2H/form/lineup context and, only when explicitly
labelled in captured public JSON/XHR, observed bookmaker odds. Unknown numbers,
model/fair odds and guessed/default prices are never accepted as bookmaker odds.

Discovery is intentionally redundant: public AiScore football links first, then
Pinnacle's public guest soccer matchups as fixture seeds. Pinnacle is only used
for the team names in that fallback; the AiScore data still comes from AiScore.
No CAPTCHA/Cloudflare bypass and no login automation are performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import requests

BASE = (os.getenv("NETRATTLER_AISCORE_BASE") or "https://m.aiscore.com").rstrip("/")
UA = os.getenv(
    "NTR_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124 Safari/537.36",
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = float(os.getenv("NETRATTLER_AISCORE_TIMEOUT", "15"))
BROWSER_WAIT_MS = int(os.getenv("NETRATTLER_AISCORE_BROWSER_WAIT_MS", "1800"))
SNAPSHOT = Path(os.getenv("NETRATTLER_AISCORE_SNAPSHOT", "netrattler_aiscore_snapshot.json"))
SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""

PINNACLE_BASE = os.getenv("PINNACLE_BASE", "https://guest.api.arcadia.pinnacle.com/0.1")
PINNACLE_GUEST_KEY = os.getenv("PINNACLE_GUEST_KEY", "")
PINNACLE_HEADERS = {
    "x-api-key": PINNACLE_GUEST_KEY,
    "Content-Type": "application/json",
    "User-Agent": UA,
    "Referer": "https://www.pinnacle.com/",
    "Origin": "https://www.pinnacle.com",
    "Accept": "application/json",
}


def log(message: str, level: str = "INFO") -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] [AiScore:{level}] {message}", flush=True)


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower().strip())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _slug(value: Any) -> str:
    return _norm(value).replace(" ", "-")


def _stable(*parts: Any) -> str:
    return hashlib.sha256("||".join(str(x or "") for x in parts).encode("utf-8")).hexdigest()[:48]


def _decimal(value: Any) -> Optional[float]:
    try:
        x = float(str(value).replace(",", "."))
    except Exception:
        return None
    return round(x, 4) if 1.01 <= x <= 100.0 else None


def _page_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        return re.sub(r"\s+", " ", BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)).strip()
    except Exception:
        text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", html or "", flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()


def extract_h2h_features_from_text(text: str, home: str = "", away: str = "") -> Dict[str, Any]:
    """Parse only explicit AiScore H2H/form summary text."""
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    low = raw.lower()
    out: Dict[str, Any] = {
        "has_h2h": "head to head" in low or "h2h" in low,
        "has_lineups": "lineup" in low,
        "has_odds_words": "odds" in low or "asian handicap" in low or "o/u" in low,
    }
    pattern = re.compile(
        r"Last\s*5\s*,\s*(?P<team>.*?)\s+Win\s+(?P<win>\d+)\s*,\s*Draw\s+(?P<draw>\d+)\s*,\s*Lose\s+(?P<lose>\d+)"
        r".*?Score\s+Win\s+Prob:\s*(?P<winprob>\d+(?:\.\d+)?)%"
        r".*?Asian\s+Handicap\s+Win%:\s*(?P<ah>\d+(?:\.\d+)?)%"
        r".*?Total\s+Goals\s+Over%:\s*(?P<over>\d+(?:\.\d+)?)%",
        flags=re.I,
    )
    blocks = []
    for match in pattern.finditer(raw):
        blocks.append({
            "team": match.group("team").strip(" ,"),
            "wins": int(match.group("win")),
            "draws": int(match.group("draw")),
            "losses": int(match.group("lose")),
            "win_prob_pct": float(match.group("winprob")),
            "asian_handicap_win_pct": float(match.group("ah")),
            "over_pct": float(match.group("over")),
        })
    if blocks:
        out["last5"] = blocks
        for side, team in (("home", home), ("away", away)):
            nt = _norm(team)
            if not nt:
                continue
            best = next((b for b in blocks if nt in _norm(b["team"]) or _norm(b["team"]) in nt), None)
            if best:
                out[f"{side}_last5_win_prob_pct"] = best["win_prob_pct"]
                out[f"{side}_last5_over_pct"] = best["over_pct"]
                out[f"{side}_last5_ah_win_pct"] = best["asian_handicap_win_pct"]
    m = re.search(r"In\s+the\s+last\s+(\d+)\s+matches", raw, flags=re.I)
    if m:
        out["h2h_n"] = int(m.group(1))
    return out


def _first(mapping: Mapping[str, Any], names: Sequence[str]) -> Any:
    lowered = {str(k).lower(): v for k, v in mapping.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _line_from_text(text: Any) -> Optional[float]:
    m = re.search(r"(?<!\d)(\d{1,2}(?:[\.,]\d+)?)", str(text or ""))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except Exception:
        return None


def _same_team(selection: str, team: str) -> bool:
    s, t = _norm(selection), _norm(team)
    return bool(s and t and (s == t or s in t or t in s))


def _classify_market(
    market_text: str,
    selection_text: str,
    line: Optional[float],
    home: str = "",
    away: str = "",
) -> Optional[Tuple[str, str, Optional[float]]]:
    m = _norm(market_text)
    s = _norm(selection_text)
    if not m or not s:
        return None

    if any(token in m for token in ("1x2", "match result", "full time result", "match winner", "three way")):
        if s in {"1", "home", "home win"} or _same_team(selection_text, home):
            return "1x2", "home", None
        if s in {"x", "draw", "tie"}:
            return "1x2", "draw", None
        if s in {"2", "away", "away win"} or _same_team(selection_text, away):
            return "1x2", "away", None

    is_btts = "btts" in m or ("both teams" in m and "score" in m)
    combo_context = is_btts and any(t in m for t in ("over 2 5", "total goals", "and over", "plus over", "btts over"))
    combo_selection = any(t in s for t in ("yes over 2 5", "yes and over", "yes over", "btts over"))
    if combo_context and combo_selection:
        observed_line = line if line is not None else (_line_from_text(selection_text) or _line_from_text(market_text))
        if observed_line is not None and abs(observed_line - 2.5) <= 0.01:
            return "btts_over25_combo", "yes", 2.5

    if is_btts:
        if s not in {"yes", "y", "no", "n"}:
            return None
        market = "btts_ht" if any(t in m for t in ("first half", "1st half", "half time", "halftime", "1h")) else "btts"
        return market, "yes" if s in {"yes", "y"} else "no", None

    # Corners must precede generic totals because many feeds say "Total Corners".
    if "corner" in m:
        observed_line = line if line is not None else _line_from_text(market_text)
        side = "over" if s.startswith("over") or s == "o" else "under" if s.startswith("under") or s == "u" else None
        if observed_line is None or not side:
            return None
        tag = str(observed_line).replace(".", "_")
        return f"corners_{tag}", f"{side}_{tag}", observed_line

    if any(token in m for token in ("over under", "total goals", "goals total", "total")):
        observed_line = line if line is not None else _line_from_text(market_text)
        if observed_line is None:
            return None
        side = "over" if s.startswith("over") or s == "o" else "under" if s.startswith("under") or s == "u" else None
        if not side:
            return None
        first_half = any(t in m for t in ("first half", "1st half", "half time", "halftime", "1h"))
        if first_half and abs(observed_line - 1.5) <= 0.01:
            return "totals_ht_1_5", f"{side}_1_5", 1.5
        tag = str(observed_line).replace(".", "_")
        return f"totals_{tag}", f"{side}_{tag}", observed_line

    player_tokens = ("player", "shots", "shot on target", "tackle", "foul", "card", "assist", "goalscorer", "to score")
    if any(t in m for t in player_tokens):
        observed_line = line if line is not None else _line_from_text(selection_text)
        return f"player_prop:{m[:80]}", s[:120], observed_line
    return None


def extract_observed_odds_from_json(payload: Any, home: str, away: str, source_url: str = "") -> List[Dict[str, Any]]:
    """Recursively parse only explicit labelled bookmaker prices from captured JSON."""
    rows: List[Dict[str, Any]] = []
    seen = set()
    market_keys = ("market", "marketname", "market_name", "bettype", "bet_type", "criterion", "groupname", "group_name")
    book_keys = ("bookmaker", "bookmakername", "bookmaker_name", "provider", "company", "sportsbook")
    selection_keys = ("selection", "outcome", "label", "name", "designation", "option", "choice", "title")
    price_keys = ("decimalodds", "decimal_odds", "decimalvalue", "decimal_value", "odds", "price", "odd")
    line_keys = ("line", "point", "points", "handicap", "total")

    def walk(obj: Any, context: Dict[str, Any]) -> None:
        if isinstance(obj, list):
            for item in obj:
                walk(item, dict(context))
            return
        if not isinstance(obj, dict):
            return
        ctx = dict(context)
        own_market = _first(obj, market_keys)
        if isinstance(own_market, dict):
            own_market = _first(own_market, ("name", "label", "title", "englishLabel"))
        if isinstance(own_market, (str, int, float)) and str(own_market).strip():
            ctx["market"] = str(own_market)
        own_book = _first(obj, book_keys)
        if isinstance(own_book, dict):
            own_book = _first(own_book, ("name", "label", "title"))
        if isinstance(own_book, (str, int, float)) and str(own_book).strip():
            ctx["bookmaker"] = str(own_book)

        price = _decimal(_first(obj, price_keys))
        selection = _first(obj, selection_keys)
        if isinstance(selection, dict):
            selection = _first(selection, ("name", "label", "title"))
        line_raw = _first(obj, line_keys)
        try:
            line = float(line_raw) if line_raw not in (None, "") else None
        except Exception:
            line = _line_from_text(line_raw)

        market_text = str(ctx.get("market") or "")
        selection_text = str(selection or "")
        if price is not None and market_text and selection_text:
            classified = _classify_market(market_text, selection_text, line, home, away)
            if classified:
                market, normalized_selection, normalized_line = classified
                bookmaker = str(ctx.get("bookmaker") or "aiscore_displayed")
                key = (market, normalized_selection, normalized_line, round(price, 4), _norm(bookmaker))
                if key not in seen:
                    seen.add(key)
                    rows.append({
                        "source": "aiscore", "bookmaker": bookmaker,
                        "home_team": home, "away_team": away,
                        "market": market, "selection": normalized_selection,
                        "line": normalized_line, "odds": price,
                        "observed": True, "source_url": source_url,
                    })
        for value in obj.values():
            if isinstance(value, (dict, list)):
                walk(value, ctx)

    walk(payload, {})
    return rows


def _json_scripts(html: str) -> List[Any]:
    out: List[Any] = []
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html or "", "html.parser")
        for script in soup.find_all("script"):
            typ, sid = str(script.get("type") or "").lower(), str(script.get("id") or "")
            if "json" not in typ and sid not in {"__NEXT_DATA__", "__NUXT_DATA__"}:
                continue
            try:
                out.append(json.loads(script.string or script.get_text() or ""))
            except Exception:
                pass
    except Exception:
        pass
    return out


def _requests_html(url: str) -> Tuple[str, Optional[int]]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        return (r.text if r.ok else ""), r.status_code
    except Exception:
        return "", None


def _browser_page(url: str) -> Tuple[str, List[Any], Optional[int]]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return "", [], None
    payloads: List[Any] = []
    status = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=UA, locale="en-US")

            def on_response(response):
                try:
                    ctype = str(response.headers.get("content-type") or "").lower()
                    u = response.url.lower()
                    if "aiscore" not in u:
                        return
                    if "json" not in ctype and not any(t in u for t in ("api", "odds", "match", "lineup", "h2h")):
                        return
                    data = response.json()
                    if isinstance(data, (dict, list)):
                        payloads.append(data)
                except Exception:
                    pass

            page.on("response", on_response)
            response = page.goto(url, wait_until="domcontentloaded", timeout=int(TIMEOUT * 1000))
            status = response.status if response else None
            page.wait_for_timeout(BROWSER_WAIT_MS)
            html = page.content()
            browser.close()
            return html, payloads, status
    except Exception:
        return "", payloads, status


def candidate_urls(home: str, away: str) -> List[str]:
    h, a = _slug(home), _slug(away)
    # AiScore H2H slugs are sometimes exposed in either ordering; both are public
    # URLs and are tried conservatively. Live pages use the normal match ordering.
    return list(dict.fromkeys([
        f"{BASE}/head-to-head/soccer-{h}-vs-{a}",
        f"{BASE}/head-to-head/soccer-{a}-vs-{h}",
        f"{BASE}/live/football-{h}-vs-{a}",
    ]))


def collect_match(home: str, away: str, use_browser: bool = True) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "home": home, "away": away, "source": "aiscore",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "pages": [], "features": {}, "odds": [],
    }
    all_odds: List[Dict[str, Any]] = []
    feature_texts: List[str] = []
    for url in candidate_urls(home, away):
        html, status = _requests_html(url)
        mode = "requests" if html else "failed"
        payloads = _json_scripts(html) if html else []
        if use_browser:
            browser_html, browser_payloads, browser_status = _browser_page(url)
            if browser_html and (not html or len(browser_html) > len(html)):
                html, mode, status = browser_html, "playwright", browser_status or status
            payloads.extend(browser_payloads)
        text = _page_text(html) if html else ""
        if text:
            feature_texts.append(text)
        for payload in payloads:
            all_odds.extend(extract_observed_odds_from_json(payload, home, away, url))
        result["pages"].append({
            "url": url, "mode": mode, "status": status,
            "bytes": len((html or "").encode("utf-8", errors="ignore")),
            "json_payloads": len(payloads),
        })
    result["features"] = extract_h2h_features_from_text(" ".join(feature_texts), home, away)
    best: Dict[Tuple[str, str, Any, str], Dict[str, Any]] = {}
    for row in all_odds:
        key = (row["market"], row["selection"], row.get("line"), _norm(row.get("bookmaker")))
        if key not in best or float(row["odds"]) > float(best[key]["odds"]):
            best[key] = row
    result["odds"] = list(best.values())
    return result


def _pair_from_href(href: str, label: str = "") -> Optional[Tuple[str, str]]:
    text = str(label or "").strip()
    if " - " in text:
        home, away = [x.strip() for x in text.split(" - ", 1)]
        if home and away:
            return home, away
    path = str(href or "")
    m = re.search(r"/(?:live/football-|head-to-head/soccer-)(.+?)-vs-(.+?)(?:[/?#]|$)", path, flags=re.I)
    if m:
        clean = lambda s: " ".join(x.capitalize() for x in s.replace("-", " ").split())
        return clean(m.group(1)), clean(m.group(2))
    return None


def discover_aiscore_links(limit: int = 60, use_browser: bool = True) -> List[Tuple[str, str]]:
    urls = [f"{BASE}/football", BASE + "/"]
    pairs: List[Tuple[str, str]] = []
    seen = set()
    for url in urls:
        html, _ = _requests_html(url)
        if use_browser:
            bhtml, _, _ = _browser_page(url)
            if bhtml and len(bhtml) > len(html):
                html = bhtml
        if not html:
            continue
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for anchor in soup.find_all("a", href=True):
                href = str(anchor.get("href") or "")
                label = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True))
                eligible_href = "/live/football-" in href or "/head-to-head/soccer-" in href
                if not eligible_href and " vs " not in label and " - " not in label:
                    continue
                pair = _pair_from_href(href, label)
                if not pair:
                    continue
                key = (_norm(pair[0]), _norm(pair[1]))
                if not all(key) or key in seen:
                    continue
                seen.add(key); pairs.append(pair)
                if len(pairs) >= limit:
                    return pairs
        except Exception:
            pass
    return pairs


def discover_pinnacle_seeds(limit: int = 60, target_date: Optional[str] = None) -> List[Tuple[str, str]]:
    """Use public Pinnacle soccer matchups only as team-name seeds for AiScore."""
    try:
        r = requests.get(
            f"{PINNACLE_BASE}/sports/29/matchups",
            headers=PINNACLE_HEADERS,
            params={"withSpecials": "false", "brandId": "0"},
            timeout=TIMEOUT,
        )
        if not r.ok:
            return []
        payload = r.json() or []
    except Exception:
        return []
    wanted = None
    if target_date:
        try:
            d = datetime.fromisoformat(str(target_date)[:10]).date()
            wanted = {d, d + timedelta(days=1)}
        except Exception:
            wanted = None
    rows: List[Tuple[str, str]] = []
    seen = set()
    for item in payload if isinstance(payload, list) else []:
        if item.get("type") != "matchup":
            continue
        start = str(item.get("startTime") or "")
        if wanted and start:
            try:
                d = datetime.fromisoformat(start.replace("Z", "+00:00")).date()
                if d not in wanted:
                    continue
            except Exception:
                pass
        participants = item.get("participants") or []
        home = next((str(p.get("name") or "").strip() for p in participants if p.get("alignment") == "home"), "")
        away = next((str(p.get("name") or "").strip() for p in participants if p.get("alignment") == "away"), "")
        key = (_norm(home), _norm(away))
        if not home or not away or key in seen:
            continue
        seen.add(key); rows.append((home, away))
        if len(rows) >= limit:
            break
    return rows


def discover_matches(limit: int = 60, use_browser: bool = True, target_date: Optional[str] = None) -> List[Tuple[str, str]]:
    """Union AiScore's own public links with public Pinnacle fixture seeds."""
    out: List[Tuple[str, str]] = []
    seen = set()
    for source_rows in (
        discover_aiscore_links(limit, use_browser=use_browser),
        discover_pinnacle_seeds(limit, target_date=target_date),
    ):
        for pair in source_rows:
            key = (_norm(pair[0]), _norm(pair[1]))
            if not all(key) or key in seen:
                continue
            seen.add(key); out.append(pair)
            if len(out) >= limit:
                return out
    return out


def odds_history_rows(matches: Sequence[Mapping[str, Any]], match_date: Optional[str] = None) -> List[Dict[str, Any]]:
    day = str(match_date or date.today().isoformat())[:10]
    now = datetime.now(timezone.utc).isoformat()
    rows: List[Dict[str, Any]] = []
    for match in matches:
        home, away = str(match.get("home") or "").strip(), str(match.get("away") or "").strip()
        if not home or not away:
            continue
        event_id = _stable(day, home, away)
        for odd in match.get("odds") or []:
            price = _decimal(odd.get("odds"))
            if price is None:
                continue
            rows.append({
                "source": "aiscore", "match_id": event_id,
                "home_team": home, "away_team": away,
                "match_date": day, "captured_date": now[:10],
                "market": str(odd.get("market") or ""),
                "bookmaker": str(odd.get("bookmaker") or "aiscore_displayed"),
                "selection": str(odd.get("selection") or ""), "odds": price,
                "raw": {"line": odd.get("line"), "captured_at": now,
                        "source_url": odd.get("source_url"), "observed": True},
            })
    return rows


def persist(matches: Sequence[Mapping[str, Any]], match_date: Optional[str] = None) -> Dict[str, int]:
    day = str(match_date or date.today().isoformat())[:10]
    odds_rows = odds_history_rows(matches, day)
    payload = {
        "version": "AISCORE_V2", "captured_at": datetime.now(timezone.utc).isoformat(),
        "match_date": day, "matches": list(matches), "odds_rows": odds_rows,
    }
    SNAPSHOT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    saved = 0
    if SUPABASE_URL and SUPABASE_KEY and odds_rows:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                   "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=minimal"}
        conflict = "source,match_id,market,bookmaker,captured_date,selection"
        for i in range(0, len(odds_rows), 200):
            batch = odds_rows[i:i + 200]
            try:
                r = requests.post(f"{SUPABASE_URL}/rest/v1/odds_history", headers=headers,
                                  params={"on_conflict": conflict}, json=batch, timeout=max(20.0, TIMEOUT))
                if r.ok:
                    saved += len(batch)
                else:
                    log(f"odds_history HTTP {r.status_code}: {r.text[:160]}", "WARN")
            except Exception as exc:
                log(f"odds_history write failed: {str(exc)[:140]}", "WARN")
    return {"matches": len(matches), "odds": len(odds_rows), "saved": saved}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=int(os.getenv("NETRATTLER_AISCORE_MAX_MATCHES", "40")))
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--match", action="append", default=[], help="Exact fixture as HOME|AWAY; repeatable")
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()
    use_browser = not args.no_browser
    pairs: List[Tuple[str, str]] = []
    for raw in args.match:
        if "|" in raw:
            home, away = [x.strip() for x in raw.split("|", 1)]
            if home and away:
                pairs.append((home, away))
    if not pairs:
        pairs = discover_matches(args.limit, use_browser=use_browser, target_date=args.date)
    pairs = pairs[:max(0, args.limit)]
    log(f"discovered fixtures={len(pairs)} browser={use_browser}")

    matches = []
    for idx, (home, away) in enumerate(pairs, 1):
        try:
            row = collect_match(home, away, use_browser=use_browser)
            matches.append(row)
            pages = row.get("pages") or []
            reachable = sum(1 for p in pages if p.get("bytes", 0) > 1000)
            log(f"{idx}/{len(pairs)} {home} vs {away}: pages={reachable}/{len(pages)} odds={len(row.get('odds') or [])} h2h={bool((row.get('features') or {}).get('has_h2h'))}")
        except Exception as exc:
            log(f"{home} vs {away}: {str(exc)[:140]}", "WARN")
        time.sleep(float(os.getenv("NETRATTLER_AISCORE_MATCH_SLEEP", "0.25")))
    result = persist(matches, args.date)
    log(f"finished {result}")
    try:
        from netrattler_health import record
        pages_ok = sum(1 for m in matches for p in (m.get("pages") or []) if p.get("bytes", 0) > 1000)
        pages_all = sum(len(m.get("pages") or []) for m in matches)
        from collections import Counter
        st = Counter(str(p.get("status")) for m in matches for p in (m.get("pages") or []))
        md = Counter(str(p.get("mode")) for m in matches for p in (m.get("pages") or []))
        js = sum(int(p.get("json_payloads") or 0) for m in matches for p in (m.get("pages") or []))
        odds_words = sum(1 for m in matches if (m.get("features") or {}).get("has_odds_words"))
        h2h = sum(1 for m in matches if (m.get("features") or {}).get("has_h2h"))
        record("aiscore", "aiscore_odds", result.get("odds", 0), result.get("saved", 0),
               note=(f"fixtures={len(pairs)} pages={pages_ok}/{pages_all} http={dict(st)} mode={dict(md)} "
                     f"json_payloads={js} seiten_mit_odds_wort={odds_words} h2h={h2h}"))
        record("aiscore", "aiscore_h2h", h2h, note="Spiele mit H2H-Features")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
