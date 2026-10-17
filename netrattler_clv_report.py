"""CLV / market-benchmark report (read-only; writes one diag row).

For every tip in 1x2 / over25 compares the taken price with the LAST Pinnacle quote
before kickoff (closing proxy) and the no-vig Pinnacle probability with the tip's hit rate.
Answers: do we beat the market, or only the noise?
"""
import json, os, re, unicodedata
from collections import defaultdict
import requests

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H = {"apikey": SK, "Authorization": f"Bearer {SK}"}


def nrm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(fc|cf|sc|afc|ac|sk|fk|club|de|the)\b", " ", s)
    return re.sub(r"[^a-z0-9]", "", s)


def get(table, params):
    out, off = [], 0
    while True:
        r = requests.get(f"{SB}/rest/v1/{table}", headers={**H, "Range": f"{off}-{off+999}"}, params=params, timeout=40)
        r.raise_for_status()
        rows = r.json()
        out += rows
        if len(rows) < 1000 or off > 60000:
            return out
        off += 1000


def pin_index():
    idx = defaultdict(dict)  # (date,home,away) -> {(market,sel): (imported_at, odds)}
    for row in get("odds_history", {"select": "match_date,home_team,away_team,market,selection,odds,imported_at",
                                    "source": "eq.pinnacle", "market": "in.(1x2,totals_2_5)"}):
        k = (str(row["match_date"])[:10], nrm(row["home_team"]), nrm(row["away_team"]))
        mk = (row["market"], row["selection"])
        cur = idx[k].get(mk)
        t = row["imported_at"]
        if cur is None or t > cur[0]:
            idx[k][mk] = (t, float(row["odds"]))
    return idx


def main():
    idx = pin_index()
    tips = get("tips", {"select": "market,tip,match,odds,date,status,probability", "market": "in.(1x2,over25)",
                        "date": "gte." + os.getenv("CLV_SINCE", "2026-09-01"), "status": "in.(win,loss)"})
    stats = defaultdict(lambda: {"n": 0, "clv_sum": 0.0, "pos": 0, "nv_sum": 0.0, "model": 0.0, "hit": 0})
    unmatched = 0
    for t in tips:
        parts = re.split(r"\s+vs\.?\s+", str(t["match"]), maxsplit=1)
        if len(parts) != 2:
            continue
        k = (str(t["date"])[:10], nrm(parts[0]), nrm(parts[1]))
        book = idx.get(k)
        if not book:
            unmatched += 1
            continue
        try:
            taken = float(str(t["odds"]).replace(",", "."))
        except Exception:
            continue
        if t["market"] == "over25":
            sel, group = ("totals_2_5", "over_2_5"), [("totals_2_5", "over_2_5"), ("totals_2_5", "under_2_5")]
        else:
            tp = str(t["tip"]).lower()
            s = "home" if tp in ("1", "home") or "heim" in tp else "away" if tp in ("2", "away") or "gast" in tp else "draw" if tp in ("x", "draw") else None
            if not s:
                continue
            sel, group = ("1x2", s), [("1x2", "home"), ("1x2", "draw"), ("1x2", "away")]
        if sel not in book or any(g not in book for g in group):
            continue
        close = book[sel][1]
        inv = sum(1 / book[g][1] for g in group)
        nv = (1 / close) / inv  # no-vig closing probability
        a = stats[t["market"]]
        a["n"] += 1
        a["clv_sum"] += taken / close - 1
        a["pos"] += taken > close
        a["nv_sum"] += nv
        a["model"] += float(t["probability"] or 0) / 100
        a["hit"] += t["status"] == "win"
    out = {"probe": "clv_report", "unmatched": unmatched, "markets": {}}
    for m, a in stats.items():
        n = a["n"]
        out["markets"][m] = {"n": n, "avg_clv_pct": round(100 * a["clv_sum"] / n, 2), "beat_close_pct": round(100 * a["pos"] / n, 1),
                             "pinnacle_novig_p": round(100 * a["nv_sum"] / n, 1), "model_p": round(100 * a["model"] / n, 1),
                             "hit_pct": round(100 * a["hit"] / n, 1)}
    print(json.dumps(out))
    if SB and SK:
        requests.post(f"{SB}/rest/v1/netrattler_card_diag", timeout=20, headers={**H, "Content-Type": "application/json"}, json={"info": out})


if __name__ == "__main__":
    main()
