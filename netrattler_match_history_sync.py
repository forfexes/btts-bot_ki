"""Sync the open match dataset (+ football-data.co.uk current seasons and extra leagues) (xgabora/Club-Football-Match-Data, MIT) into Supabase
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


FD_MAIN = os.getenv("FD_MAIN_DIVS", "E0,E1,E2,E3,EC,SC0,SC1,SC2,SC3,D1,D2,I1,I2,SP1,SP2,F1,F2,N1,B1,P1,T1,G1").split(",")
FD_EXTRA = os.getenv("FD_EXTRA_COUNTRIES", "ARG,AUT,BRA,CHN,DNK,FIN,IRL,JPN,MEX,NOR,POL,ROU,RUS,SWE,SWZ,USA").split(",")


# Same division codes as the open dataset so rows dedupe on the primary key.
_DIV_ALIAS = {"DNK": "DEN", "JPN": "JAP", "ROU": "ROM", "SWZ": "SUI"}


def _iso(d):
    d = (d or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            import datetime as _dt
            return _dt.datetime.strptime(d, fmt).date().isoformat()
        except Exception:
            continue
    return None


def football_data_rows():
    """Current + previous season of the main FD leagues and all FD 'extra' leagues
    (Argentina, Brazil, USA, Japan, ...). Keeps the history current beyond the open dataset."""
    import datetime as _dt
    import io
    out = []
    y = _dt.date.today().year
    start = y if _dt.date.today().month >= 7 else y - 1
    seasons = [f"{str(start - 1)[2:]}{str(start)[2:]}", f"{str(start)[2:]}{str(start + 1)[2:]}"]
    for season in seasons:
        for div in FD_MAIN:
            try:
                r = requests.get(f"https://www.football-data.co.uk/mmz4281/{season}/{div.strip()}.csv", timeout=30)
                if not r.ok:
                    continue
                for x in csv.DictReader(io.StringIO(r.content.decode("utf-8", "ignore"))):
                    d = _iso(x.get("Date"))
                    h, a = _i(x.get("FTHG")), _i(x.get("FTAG"))
                    if d and h is not None and a is not None and x.get("HomeTeam"):
                        out.append({"division": div.strip(), "match_date": d, "home_team": x["HomeTeam"].strip(),
                                    "away_team": x["AwayTeam"].strip(), "ft_home": h, "ft_away": a,
                                    "ht_home": _i(x.get("HTHG")), "ht_away": _i(x.get("HTAG"))})
            except Exception as exc:
                print(f"FD {season}/{div}: {type(exc).__name__}")
    for c in FD_EXTRA:
        try:
            r = requests.get(f"https://www.football-data.co.uk/new/{c.strip()}.csv", timeout=60)
            if not r.ok:
                continue
            for x in csv.DictReader(io.StringIO(r.content.decode("utf-8", "ignore"))):
                d = _iso(x.get("Date"))
                h, a = _i(x.get("HG")), _i(x.get("AG"))
                if d and d >= "2015-01-01" and h is not None and a is not None and x.get("Home"):
                    out.append({"division": _DIV_ALIAS.get(c.strip(), c.strip()), "match_date": d,
                                "home_team": x["Home"].strip(), "away_team": x["Away"].strip(), "ft_home": h,
                                "ft_away": a, "ht_home": None, "ht_away": None})
        except Exception as exc:
            print(f"FD new {c}: {type(exc).__name__}")
    print(f"football-data: {len(out)} Spiele (Saison {seasons}, {len(FD_EXTRA)} Zusatzländer)")
    return out


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
    for x in football_data_rows():
        key = (x["division"], x["match_date"], x["home_team"], x["away_team"])
        if key not in seen:
            seen.add(key)
            rows.append(x)
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
