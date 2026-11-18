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
MIN_MINUTE, MAX_MINUTE = 76, 88
MAX_MATCHES = 2
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
    hs, az, fid = _integer(g.get("home")), _integer(g.get("away")), _integer(f.get("id"))
    if (st.get("short") not in LIVE_STATUSES or minute is None
            or not MIN_MINUTE <= minute <= MAX_MINUTE
            or hs is None or az is None or fid is None
            or not h.get("id") or not a.get("id")
            or not h.get("name") or not a.get("name")):
        return None
    return {"fixture_id": fid, "minute": minute, "home_id": h["id"], "away_id": a["id"],
            "home": str(h["name"]), "away": str(a["name"]), "hg": hs, "ag": az}


def match_metrics(stats, fx):
    """Do not treat missing live team statistics as zero."""
    m = {}
    mapping = {"Shots on Goal": "sot", "Total Shots": "shots",
               "Corner Kicks": "corners", "Red Cards": "reds"}
    for row in stats:
        tid = (row.get("team") or {}).get("id")
        if str(tid) not in {str(fx["home_id"]), str(fx["away_id"])}:
            continue
        side = "h" if str(tid) == str(fx["home_id"]) else "a"
        vals = {x.get("type"): x.get("value") for x in (row.get("statistics") or []) if isinstance(x, dict)}
        for source, target in mapping.items():
            m[side + "_" + target] = _integer(vals.get(source))
    if any(m.get(side + "_" + metric) is None
           for side in ("h", "a") for metric in ("sot", "shots", "corners", "reds")):
        return None
    if m["h_reds"] or m["a_reds"]:
        return None
    sot = m["h_sot"] + m["a_sot"]
    shots = m["h_shots"] + m["a_shots"]
    corners = m["h_corners"] + m["a_corners"]
    # Conservative observable pressure gate, NOT a learned goal probability.
    if sot < 8 or shots < 19 or corners < 6 or abs(fx["hg"] - fx["ag"]) > 1:
        return None
    if m["h_sot"] > m["h_shots"] or m["a_sot"] > m["a_shots"]:
        return None
    return {"sot": sot, "shots": shots, "corners": corners}


def _utc_time(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        x = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return x if x.tzinfo else x.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def quote_for_next_goal(payload, fx, now=None):
    """Exact current total + 0.5: one *additional* goal, no Asian push."""
    now = now or dt.datetime.now(dt.timezone.utc)
    line = fx["hg"] + fx["ag"] + 0.5
    found = []
    for row in payload:
        if str((row.get("fixture") or {}).get("id")) != str(fx["fixture_id"]):
            continue
        status = row.get("status") or {}
        if any(status.get(k) is not False for k in ("blocked", "stopped", "finished")):
            continue
        updated = _utc_time(row.get("update"))
        if updated is None or abs((now - updated).total_seconds()) > ODDS_MAX_AGE_SECONDS:
            continue
        for bet in row.get("odds") or []:
            title = str(bet.get("name") or "").casefold()
            if not any(s in title for s in ("over/under", "goals over", "total goals")):
                continue
            for item in bet.get("values") or []:
                if item.get("suspended") is not False or item.get("main") is False:
                    continue
                value = str(item.get("value") or "").strip()
                if not re.fullmatch(r"Over(?:\s+\d+(?:\.\d+)?)?", value, re.I):
                    continue
                match = re.search(r"(\d+(?:\.\d+)?)", value)
                handicap = item.get("handicap")
                try:
                    actual_line = float(handicap) if handicap not in (None, "") else float(match.group(1)) if match else -1
                    odd = float(item.get("odd"))
                except (ValueError, TypeError):
                    continue
                if actual_line != line or not 1.6 <= odd <= 6.0:
                    continue
                found.append(round(odd, 3))
    # Refuse ambiguous or conflicting live prices within a fixture snapshot.
    return found[0] if len(found) == 1 else None


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
    key = f'{fx["fixture_id"]}:over:{line:.1f}'
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


def send(fx, metrics, odds):
    token = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_GROUP_LATE_GOALS")
    if not token or not chat:
        raise RuntimeError("Telegram Goal Hunter configuration missing")
    line = fx["hg"] + fx["ag"] + 0.5
    msg = (f"⚽ NETRATTLER · LAST MINUTE GOAL\n\n"
           f"🏟 {fx['home']} – {fx['away']}\n"
           f"⏱ {fx['minute']}'  |  {fx['hg']}:{fx['ag']}\n"
           f"🎯 Noch 1 Tor: OVER {line:.1f} @ {odds:.2f}\n"
           f"📊 Schüsse {metrics['shots']} · aufs Tor {metrics['sot']} · Ecken {metrics['corners']}\n"
           f"🏁 Auswertung: ⏳ offen")
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": msg, "disable_web_page_preview": True},
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
    matches.sort(key=lambda x: (abs(x["minute"] - 82), x["fixture_id"]))
    out = {"live_eligible": len(matches), "checked": 0, "signals": 0, "sent": 0,
           "mode": "live" if send_enabled else "dry-run"}
    for fx in matches[:max(0, min(2, int(os.getenv("LMG_MAX_MATCHES", str(MAX_MATCHES)))))]:
        out["checked"] += 1
        metrics = match_metrics(_api("/fixtures/statistics", {"fixture": fx["fixture_id"]}), fx)
        if not metrics:
            continue
        odds = quote_for_next_goal(_api("/odds/live", {"fixture": fx["fixture_id"]}), fx)
        if odds is None:
            continue
        out["signals"] += 1
        print(json.dumps({"fixture": fx["fixture_id"], "minute": fx["minute"],
                          "line": fx["hg"] + fx["ag"] + 0.5, "observed_odds": odds,
                          "stats": metrics, "send_enabled": send_enabled}))
        if send_enabled:
            key = reserve(fx, odds)
            if key:
                message_id = send(fx, metrics, odds)
                delivered(key, message_id)
                out["sent"] += 1
    return out


if __name__ == "__main__":
    try:
        print("LMG_SUMMARY " + json.dumps(run()))
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        print("LMG_FAIL_CLOSED " + str(exc).split("\n", 1)[0], file=sys.stderr)
        sys.exit(1)
