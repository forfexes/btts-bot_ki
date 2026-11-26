#!/usr/bin/env python3
"""NETRATTLER Last Minute Goal: observed live data + real in-play prices only.

Runs once; suitable for a bounded scheduled GitHub Action. No synthetic odds,
unverified probabilities, stale prices, or silent Telegram duplicates.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

import requests

BASE = "https://v3.football.api-sports.io"
LIVE_STATUSES = {"2H"}
MIN_MINUTE, MAX_MINUTE = 55, 88
MAX_MATCHES = 1
ODDS_MAX_AGE_SECONDS = 150


def _key():
    return next((x.strip() for x in (os.getenv("API_FOOTBALL_KEYS") or os.getenv("API_FOOTBALL_KEY") or "")
                 .replace("\n", ",").split(",") if x.strip()), "")


def _api(path, params):
    k = _key()
    if not k:
        raise RuntimeError("API_FOOTBALL_KEYS missing")
    r = requests.get(BASE + path, params=params, headers={"x-apisports-key": k},
                     timeout=25)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict) or data.get("errors"):
        raise RuntimeError("API-Football returned an error")
    # The free plan is shared with NETRATTLER: stop before exhausting its quota.
    remain = r.headers.get("x-ratelimit-requests-remaining")
    if remain is not None and int(remain) < 12:
        raise RuntimeError("API-Football quota reserve reached")
    return data.get("response") or []


def _integer(value):
    if isinstance(value, bool):
        return None
    try:
        if value is None or str(value).strip() in ("", "-"):
            return None
        n = float(value)
        return int(n) if n.is_integer() and 0 <= n <= 999 else None
    except (ValueError, TypeError, OverflowError):
        return None


def fixture_info(row):
    f, t, g = row.get("fixture") or {}, row.get("teams") or {}, row.get("goals") or {}
    st = f.get("status") or {}
    minute = _integer(st.get("elapsed"))
    h, a = t.get("home") or {}, t.get("away") or {}
    hs, az = _integer(g.get("home")), _integer(g.get("away"))
    # Fixture IDs are identifiers, not bounded sporting statistics. Modern
    # API-Football fixtures routinely exceed 999; do not discard the entire feed.
    raw_id = f.get("id")
    fid = int(raw_id) if (not isinstance(raw_id, bool) and
                         re.fullmatch(r"[1-9][0-9]{0,17}", str(raw_id or ""))) else None
    if (st.get("short") not in LIVE_STATUSES or minute is None
            or not MIN_MINUTE <= minute <= MAX_MINUTE
            or hs is None or az is None or fid is None
            or not h.get("id") or not a.get("id")
            or not h.get("name") or not a.get("name")):
        return None
    if hs + az > 5:
        return None
    league = row.get("league") or {}
    return {"fixture_id": fid, "minute": minute, "home_id": h["id"], "away_id": a["id"],
            "home": str(h["name"]), "away": str(a["name"]), "hg": hs, "ag": az,
            "league": str(league.get("name") or "")}


def match_metrics(stats, fx):
    """Cumulative real live stats; no fabricated xG, radar, or last-5 shots."""
    metrics = {}
    mapping = {"Shots on Goal": "sot", "Total Shots": "shots",
               "Corner Kicks": "corners", "Red Cards": "reds"}
    for row in stats:
        tid = (row.get("team") or {}).get("id")
        if str(tid) not in {str(fx["home_id"]), str(fx["away_id"])}:
            continue
        side = "h" if str(tid) == str(fx["home_id"]) else "a"
        vals = {x.get("type"): x.get("value") for x in (row.get("statistics") or []) if isinstance(x, dict)}
        for source, target in mapping.items():
            metrics[side + "_" + target] = _integer(vals.get(source))
    if any(metrics.get(side + "_" + metric) is None
           for side in ("h", "a") for metric in ("sot", "shots")):
        return None
    # Red cards are explicit vetoes when known, not falsely interpreted as absent.
    if any(metrics.get(side + "_reds") is not None and metrics[side + "_reds"] > 0
           for side in ("h", "a")):
        return None
    sot = metrics["h_sot"] + metrics["a_sot"]
    shots = metrics["h_shots"] + metrics["a_shots"]
    corners = (metrics["h_corners"] + metrics["a_corners"]
               if metrics.get("h_corners") is not None and metrics.get("a_corners") is not None
               else None)
    if metrics["h_sot"] > metrics["h_shots"] or metrics["a_sot"] > metrics["a_shots"]:
        return None
    if sot < 5 or shots < 10:
        return None
    if fx["minute"] > 80 and sot < 8:
        return None
    if fx["hg"] == fx["ag"] == 0 and fx["minute"] > 75:
        return None
    if abs(fx["hg"] - fx["ag"]) > 3:
        return None
    tier = "PREMIUM" if sot >= 8 and shots >= 16 and fx["minute"] <= 76 else "STANDARD"
    return {"sot": sot, "shots": shots, "corners": corners, "tier": tier}


def market_targets(fx):
    """Return total-match half-goal lines; second target always takes TWO goals."""
    goals = fx["hg"] + fx["ag"]
    return goals + 0.5, goals + 1.5


def _utc_time(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        x = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return x if x.tzinfo is not None and x.utcoffset() is not None else None
    except ValueError:
        return None


def live_quotes(payload, fx, now=None):
    """Select genuinely observed fresh *full-match* goal overs, never implied odds.

    Only explicit exact-line over bets, non-suspended and fixture-matched.
    If multiple identical lines are supplied, prefer the single main=true value;
    otherwise refuse ambiguity instead of selecting a convenient price.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    primary, secondary = market_targets(fx)
    buckets = {primary: [], secondary: []}
    for row in payload:
        if str((row.get("fixture") or {}).get("id")) != str(fx["fixture_id"]):
            continue
        status = row.get("status") or {}
        if any(status.get(k) is not False for k in ("blocked", "stopped", "finished")):
            continue
        updated = _utc_time(row.get("update"))
        if updated is None or not 0 <= (now - updated).total_seconds() <= ODDS_MAX_AGE_SECONDS:
            continue
        for bet in row.get("odds") or []:
            title = str(bet.get("name") or "").casefold().strip()
            # Explicitly exclude first-half, second-half, team and Asian markets.
            if title not in {"over/under line", "over/under", "total goals", "goals over/under"}:
                continue
            for item in bet.get("values") or []:
                if item.get("suspended") is not False:
                    continue
                val = str(item.get("value") or "").strip()
                if not re.fullmatch(r"Over(?:\s+\d+(?:\.\d+)?)?", val, re.I):
                    continue
                part = re.search(r"(\d+(?:\.\d+)?)", val)
                try:
                    handicap = item.get("handicap")
                    line = float(handicap) if handicap not in (None, "") else (
                        float(part.group(1)) if part else -1)
                    odd = float(item.get("odd"))
                except (ValueError, TypeError):
                    continue
                if line not in buckets or not 1.30 <= odd <= 30.0:
                    continue
                buckets[line].append((bool(item.get("main")), round(odd, 3)))
    result = {}
    for line, values in buckets.items():
        if len(values) == 1:
            result[line] = values[0][1] if values[0][0] else None
        else:
            mains = [v for main, v in values if main]
            result[line] = mains[0] if len(mains) == 1 else None
    return result


def _db():
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    token = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not token:
        raise RuntimeError("Supabase service-role missing: delivery disabled")
    return url + "/rest/v1/netrattler_lmg_alerts", {
        "apikey": token, "Authorization": "Bearer " + token,
        "Content-Type": "application/json"}


def reserve(fx, odds):
    url, headers = _db()
    line = fx["hg"] + fx["ag"] + 0.5
    key = str(fx["fixture_id"])  # one original Telegram card per fixture
    r = requests.post(url, params={"on_conflict": "alert_key"},
                      headers={**headers, "Prefer": "resolution=ignore-duplicates,return=representation"},
                      json={"alert_key": key, "fixture_id": fx["fixture_id"], "home": fx["home"],
                            "away": fx["away"], "minute": fx["minute"],
                            "score": f'{fx["hg"]}:{fx["ag"]}', "selection": f"Over {line:.1f}",
                            "observed_odds": odds}, timeout=15)
    r.raise_for_status()
    rows = r.json()
    return key if isinstance(rows, list) and len(rows) == 1 else None


def delivered(key, message_id):
    url, headers = _db()
    r = requests.patch(url, params={"alert_key": "eq." + key},
                       headers=headers, json={"status": "sent",
                                              "telegram_message_id": message_id,
                                              "sent_at": dt.datetime.now(dt.timezone.utc).isoformat()},
                       timeout=15)
    r.raise_for_status()


def format_tip(fx, metrics, quotes):
    primary, secondary = market_targets(fx)
    odd = quotes[primary]
    if odd is None:
        raise ValueError("primary odds unavailable")
    base = ("OVER 0.5 VALUE" if fx["hg"] + fx["ag"] == 0 else
            "MONEYBAG + 3 GOALS" if fx["hg"] + fx["ag"] >= 3 else "MONEYBAG")
    corners = str(metrics["corners"]) if metrics["corners"] is not None else "k.A."
    msg = (f"⚽ NETRATTLER · LAST MINUTE GOAL\n"
           f"💥 {base} · {metrics['tier']}-TIER\n\n"
           f"🏆 {fx['league'] or 'Liga k.A.'}\n"
           f"🏟 {fx['home']} – {fx['away']}\n"
           f"⏱ {fx['minute']}'  |  {fx['hg']}:{fx['ag']}\n"
           f"🎯 Ziel 1: ÜBER {primary:.1f} @ {odd:.2f} (1 Tor)\n")
    if quotes[secondary] is not None:
        msg += f"🎯 Ziel 2: ÜBER {secondary:.1f} @ {quotes[secondary]:.2f} (2 Tore; nur Info)\n"
    msg += (f"📊 Torschüsse {metrics['sot']}, Schüsse {metrics['shots']}, Ecken {corners}\n"
            f"📍 Verifizierte Live-Quote, keine ungeprüfte Prozent-Prognose\n"
            f"🏁 Auswertung: ⏳ offen")
    return msg


def send(fx, metrics, quotes):
    token = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_GROUP_LATE_GOALS")
    if not token or not chat:
        raise RuntimeError("Telegram Goal Hunter configuration missing")
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": format_tip(fx, metrics, quotes),
                            "disable_web_page_preview": True},
                      timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok") or not (data.get("result") or {}).get("message_id"):
        raise RuntimeError("Telegram message not confirmed")
    return data["result"]["message_id"]


def run():
    send_enabled = os.getenv("LMG_SEND", "false").lower() in ("1", "yes", "true")
    rows = _api("/fixtures", {"live": "all"})
    matches = [x for row in rows if (x := fixture_info(row))]
    matches.sort(key=lambda x: (abs(x["minute"] - 63), x["fixture_id"]))
    out = {"live_eligible": len(matches), "checked": 0, "signals": 0, "sent": 0,
           "mode": "live" if send_enabled else "dry-run"}
    for fx in matches[:max(0, min(1, int(os.getenv("LMG_MAX_MATCHES", str(MAX_MATCHES)))))]:
        out["checked"] += 1
        metrics = match_metrics(_api("/fixtures/statistics", {"fixture": fx["fixture_id"]}), fx)
        if not metrics:
            continue
        quotes = live_quotes(_api("/odds/live", {"fixture": fx["fixture_id"]}), fx)
        primary, _ = market_targets(fx)
        if quotes.get(primary) is None:
            continue
        out["signals"] += 1
        print(json.dumps({"fixture": fx["fixture_id"], "minute": fx["minute"],
                          "primary_line": primary, "observed_odds": quotes[primary],
                          "tier": metrics["tier"], "stats": metrics, "send_enabled": send_enabled}))
        if send_enabled:
            key = reserve(fx, quotes[primary])
            if key:
                message_id = send(fx, metrics, quotes)
                delivered(key, message_id)
                out["sent"] += 1
    return out


if __name__ == "__main__":
    try:
        print("LMG_SUMMARY " + json.dumps(run()))
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        print("LMG_FAIL_CLOSED " + str(exc).split("\n", 1)[0], file=sys.stderr)
        sys.exit(1)
