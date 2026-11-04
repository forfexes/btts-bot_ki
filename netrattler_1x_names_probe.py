#!/usr/bin/env python3
"""Liest die Markt-/Gruppennamen direkt aus dem oeffentlichen 22bet-LineFeed: je Unterspiel (Titel TG/PN)
die Gruppen-IDs (G), Typ-IDs (T), Linien (P) und Spielernamen-Felder. Nur lesend, begrenzte Anzahl Anfragen.
Schreibt probe='x1_names' in netrattler_card_diag; Mapping Titel -> G/T fuer Ecken, Torschuetzen u. a."""
from __future__ import annotations
import json, os
from collections import Counter, defaultdict
import requests

HOST = "https://22bet.com"
HEADERS = {"User-Agent": "NETRATTLER-PublicSourceAudit/2.0 (+https://github.com/forfexes/btts-bot_ki)", "Accept": "application/json"}
TOP = ("england", "premier", "germany", "bundesliga", "spain", "laliga", "italy", "serie a", "france", "ligue 1", "champions", "europa")
MAX_SUB = int(os.getenv("X1_NAMES_MAX_SUB", "70"))


def _get(params, path="GetGameZip"):
    try:
        r = requests.get(f"{HOST}/service-api/LineFeed/{path}", params=params, headers=HEADERS, timeout=15)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def _events(val):
    evs = list(val.get("E") or [])
    for grp in val.get("GE") or []:
        for r in grp.get("E") or []:
            evs.extend(r if isinstance(r, list) else [r])
    return [e for e in evs if isinstance(e, dict)]


def _profile(val):
    evs = _events(val)
    groups = defaultdict(lambda: {"n": 0, "T": Counter(), "P": Counter(), "PN": set(), "ex": None})
    for e in evs:
        g = groups[e.get("G")]
        g["n"] += 1
        g["T"][e.get("T")] += 1
        if e.get("P") is not None:
            g["P"][e.get("P")] += 1
        if e.get("PL") or e.get("PN"):
            g["PN"].add(str(e.get("PL") or e.get("PN"))[:30])
        if g["ex"] is None:
            g["ex"] = {k: (v if isinstance(v, (int, float)) else str(v)[:40]) for k, v in e.items()}
    names = {}
    for grp in val.get("GE") or []:
        if grp.get("G") is not None:
            names[grp.get("G")] = str(grp.get("GS") or "")[:30]
    return [{"G": gid, "n": d["n"], "T": d["T"].most_common(4), "lines": [p for p, _ in d["P"].most_common(4)],
             "players": sorted(d["PN"])[:2], "gs": names.get(gid), "ex": d["ex"]} for gid, d in list(groups.items())[:30]]


def main():
    data = _get({"sports": 1, "count": 300, "lng": "en", "mode": 4, "country": 1}, "Get1x2_VZip")
    games = [g for g in (data or {}).get("Value") or [] if g.get("I") and g.get("O1") and g.get("O2")]
    games.sort(key=lambda g: (not any(t in str(g.get("L") or "").lower() for t in TOP), int(g.get("S") or 0)))
    out = []
    for g in games[:2]:
        full = _get({"id": g["I"], "lng": "en", "cfview": 0, "grMode": 4, "country": 1, "marketType": 1, "isSubGames": "true"})
        if not full or not full.get("Value"):
            continue
        fv = full["Value"]
        row = {"match": f"{g.get('O1')} vs {g.get('O2')}"[:70], "league": str(g.get("L"))[:40], "main": _profile(fv)[:25], "sub": []}
        for sg in (fv.get("SG") or [])[:MAX_SUB]:
            title = str(sg.get("TG") or sg.get("PN") or "")
            if not title:
                continue
            sub = _get({"id": sg.get("CI"), "lng": "en", "cfview": 0, "grMode": 4, "country": 1, "marketType": 1})
            if sub and sub.get("Value"):
                row["sub"].append({"title": title[:50], "groups": _profile(sub["Value"])[:6]})
        out.append(row)
    print(json.dumps(out, ensure_ascii=False)[:6000])
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if url and key:
        for i, row in enumerate(out):
            for part in range(0, len(row["sub"]), 12):
                requests.post(f"{url}/rest/v1/netrattler_card_diag", timeout=20,
                              headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                              json={"info": {"probe": "x1_names", "fixture": i, "match": row["match"], "league": row["league"],
                                             "main": row["main"] if part == 0 else None, "sub": row["sub"][part:part + 12]}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
