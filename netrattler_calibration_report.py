"""Kalibrierungs-Bericht: Modell-Wahrscheinlichkeit vs. Markt (1/Quote) vs. Realitaet je Markt.
Nur Lesen; Ergebnis als Diagnose-Zeile (probe=calibration) in netrattler_card_diag."""
import os, json, requests

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
DAYS = int(os.getenv("CAL_DAYS", "45"))
MARKETS = ("over25", "btts", "1x2", "over15_ht", "btts_ht", "combo", "corners")
WIN, LOSS = {"win", "won"}, {"loss", "lost"}


def points(rows):
    out = []
    for r in rows:
        try:
            p = float(r["probability"]) / 100.0
            o = float(r["odds"])
        except (TypeError, ValueError, KeyError):
            continue
        st = str(r.get("status") or "").lower()
        if o <= 1 or not (0 < p < 1) or st not in WIN | LOSS:
            continue
        out.append((p, 1.0 / o, 1.0 if st in WIN else 0.0, o))
    return out


def summarize(pts):
    n = len(pts)
    if n == 0:
        return {"n": 0}
    brier = lambda f: sum((f(x) - x[2]) ** 2 for x in pts) / n
    best_w, best_b = 0.0, 9.0
    for i in range(11):
        w = i / 10
        b = brier(lambda x, w=w: w * x[0] + (1 - w) * x[1])
        if b < best_b:
            best_w, best_b = w, b
    roi = sum((x[3] - 1) if x[2] else -1 for x in pts) / n
    return {"n": n, "model": round(100 * sum(x[0] for x in pts) / n, 1),
            "market": round(100 * sum(x[1] for x in pts) / n, 1),
            "real": round(100 * sum(x[2] for x in pts) / n, 1),
            "brier_model": round(brier(lambda x: x[0]), 4), "brier_market": round(brier(lambda x: x[1]), 4),
            "best_model_weight": best_w, "roi_pct": round(100 * roi, 1)}


def main():
    H = {"apikey": SK, "Authorization": f"Bearer {SK}"}
    out = {"probe": "calibration", "days": DAYS, "markets": {}}
    for m in MARKETS:
        rows, off = [], 0
        while True:
            r = requests.get(f"{SB}/rest/v1/tips", headers=H, timeout=30, params={
                "select": "probability,odds,status", "market": f"eq.{m}",
                "date": f"gte.{__import__('datetime').date.today() - __import__('datetime').timedelta(days=DAYS)}",
                "limit": "1000", "offset": str(off)})
            batch = r.json() if r.ok else []
            rows += batch
            if len(batch) < 1000:
                break
            off += 1000
        out["markets"][m] = summarize(points(rows))
    print(json.dumps(out)[:3000])
    try:
        requests.post(f"{SB}/rest/v1/netrattler_card_diag", timeout=20, json={"info": out},
                      headers={**H, "Content-Type": "application/json"})
    except Exception:
        pass


if __name__ == "__main__":
    main()
