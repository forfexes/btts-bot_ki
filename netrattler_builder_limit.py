"""Begrenzt Builder pro Spiel ueber alle Engines und Laeufe (Tabelle netrattler_builder_picks)."""
import json, os
import requests

PER_MATCH = int(os.getenv("NETRATTLER_BUILDER_PER_MATCH_TOTAL", "1"))


def matches_of(legs):
    out = []
    for leg in legs or []:
        m = leg.get("match") if isinstance(leg, dict) else getattr(leg, "match", None)
        if m and m not in out:
            out.append(m)
    return out


def at_limit(url, key, match_date, legs, limit=None):
    """True, wenn fuer eines der Spiele bereits `limit` Builder (nicht void) existieren. Fail-open bei DB-Fehler."""
    limit = PER_MATCH if limit is None else limit
    if not url or not key or limit <= 0:
        return False
    hdr = {"apikey": key, "Authorization": f"Bearer {key}"}
    for match in matches_of(legs):
        try:
            r = requests.get(f"{url.rstrip('/')}/rest/v1/netrattler_builder_picks", headers=hdr, timeout=15, params=[
                ("select", "builder_id"), ("match_date", f"eq.{str(match_date)[:10]}"),
                ("status", "neq.void"), ("legs", "cs." + json.dumps([{"match": match}])), ("limit", str(limit))])
            if r.ok and len(r.json()) >= limit:
                return True
        except Exception:
            pass
    return False
