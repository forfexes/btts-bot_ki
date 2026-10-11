"""Sync the open match dataset (xgabora/Club-Football-Match-Data, MIT) into Supabase
table netrattler_match_history. Idempotent upsert; safe to re-run weekly."""
import csv
import os
import sys
import time

import requests

URL = os.getenv("CARD_MATCHES_CSV_URL",
                "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data-2000-2025/main/data/Matches.csv")
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
BATCH = 4000


def _i(v):
    try:
        return int(float(v))
    except Exception:
        return None


def main():
    if not SB or not KEY:
        print("SUPABASE_URL/KEY fehlen")
        return 1
    path = "/tmp/matches.csv"
    r = requests.get(URL, timeout=120, stream=True)
    r.raise_for_status()
    with open(path, "wb") as fh:
        for chunk in r.iter_content(1 << 20):
            fh.write(chunk)
    rows, seen = [], set()
    with open(path, encoding="utf-8", errors="ignore", newline="") as fh:
        for x in csv.DictReader(fh):
            ft_h, ft_a = _i(x.get("FTHome")), _i(x.get("FTAway"))
            if ft_h is None or ft_a is None or not x.get("MatchDate"):
                continue
            key = (x["Division"], x["MatchDate"], x["HomeTeam"], x["AwayTeam"])
            if key in seen:
                continue
            seen.add(key)
            rows.append({"division": key[0], "match_date": key[1], "home_team": key[2], "away_team": key[3],
                         "ft_home": ft_h, "ft_away": ft_a, "ht_home": _i(x.get("HTHome")), "ht_away": _i(x.get("HTAway"))})
    print(f"{len(rows)} Spiele gelesen")
    hdr = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json",
           "Prefer": "resolution=merge-duplicates,return=minimal"}
    ok = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        for attempt in range(3):
            resp = requests.post(f"{SB}/rest/v1/netrattler_match_history?on_conflict=division,match_date,home_team,away_team",
                                 headers=hdr, json=chunk, timeout=120)
            if resp.ok:
                ok += len(chunk)
                break
            print(f"Batch {i}: HTTP {resp.status_code} {resp.text[:150]}")
            time.sleep(3 * (attempt + 1))
        if (i // BATCH) % 10 == 0:
            print(f"{ok}/{len(rows)}")
    print(f"fertig: {ok}/{len(rows)} gespeichert")
    return 0 if ok == len(rows) else 2


if __name__ == "__main__":
    sys.exit(main())
