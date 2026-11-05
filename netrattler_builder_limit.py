"""Begrenzt Builder pro Spiel ueber alle Engines und Laeufe (Tabelle netrattler_builder_picks).

Default aligns with the engine daily per-match cap (6). Exact duplicates and
leg-set overlaps are independently checked by the sender.
"""
import json, os
import requests

PER_MATCH = int(os.getenv("NETRATTLER_BUILDER_PER_MATCH_TOTAL", "6"))


def matches_of(legs):
    out = []
    for leg in legs or []:
        m = leg.get("match") if isinstance(leg, dict) else getattr(leg, "match", None)
        if m and m not in out:
            out.append(m)
    return out


def at_limit(url, key, match_date, legs, limit=None):
    """True, wenn fuer eines der Spiele bereits `limit` Builder (nicht void) existieren. Bei DB-Fehler sperren, damit die Tagesgrenze erhalten bleibt."""
    limit = PER_MATCH if limit is None else limit
    if limit <= 0:
        return False
    if not url or not key:
        return True
    hdr = {"apikey": key, "Authorization": f"Bearer {key}"}
    for match in matches_of(legs):
        try:
            r = requests.get(f"{url.rstrip('/')}/rest/v1/netrattler_builder_picks", headers=hdr, timeout=15, params=[
                ("select", "builder_id"), ("match_date", f"eq.{str(match_date)[:10]}"),
                ("status", "neq.void"), ("legs", "cs." + json.dumps([{"match": match}])), ("limit", str(limit))])
            if not r.ok:
                return True
            rows = r.json()
            if not isinstance(rows, list) or len(rows) >= limit:
                return True
        except Exception:
            return True
    return False

# Production verification trigger: post-merge builder ladder deployment (2026-11-05).
