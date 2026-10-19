#!/usr/bin/env python3
"""
FINISHING RADAR - xG-Regression Torschuetzen-Radar fuer NETRATTLER / Prop Hunter

Idee: Der Markt (und die Oeffentlichkeit) schaut auf TORE der letzten Spiele.
Tore sind aber stark von Glueck getrieben, xG ist stabiler. Das Skript misst pro
Spieler die Abweichung  Tore - xG  (letzte 8 Einsaetze) und rechnet daraus eine
regressions-bereinigte Torwahrscheinlichkeit:

    rate = ALPHA * rate_Tore + (1 - ALPHA) * rate_xG      (beide Bayes-geschrumpft)
    P(Tor) = 1 - exp(-rate * erwartete_Minuten / 90)

Backtest auf player_game_log (13'780 Einsaetze, walk-forward, Spieler mit xG):
    Brier Baseline (Liga-Schnitt) 0.17310
    Brier nur Tore                0.16693
    Brier nur xG                  0.16523
    Brier Mix ALPHA=0.25          0.16506   <- Standard
Spieler stark ueber xG (>= +1.5 Tore) treffen real nur 29.8% statt der 34.6%,
die ein reines Tore-Modell erwartet; Spieler stark unter xG treffen 28.9% statt 15.8%.

Nutzung:
    export SUPABASE_URL=https://<ref>.supabase.co
    export SUPABASE_KEY=<service_role key>      # player_game_log hat RLS aktiv
    python finishing_radar.py                   # Radar: Top-Kandidaten + Regressions-Warnungen
    python finishing_radar.py --backtest        # Backtest + Alpha-Grid + Divergenz-Buckets
    python finishing_radar.py --csv radar.csv   # zusaetzlich CSV schreiben
    python finishing_radar.py --telegram        # zusaetzlich an Telegram senden
                                                # (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    python finishing_radar.py --selftest        # Test ohne Datenbank

Abhaengigkeit: requests
"""
import os
import sys
import csv
import math
import argparse
import datetime as dt
from collections import defaultdict

WINDOW = 8          # letzte N Einsaetze (mit xG) als Formfenster
K = 6.0             # Bayes-Schrumpfung in "Voll-Spielen" Richtung Liga-Schnitt
ALPHA = 0.25        # Gewicht der Tore-Rate (Rest: xG-Rate) - im Backtest optimal bei ~0.25
MIN_PRIOR = 5       # mindestens so viele Einsaetze im Fenster
MIN_MINUTES = 45    # Backtest: nur Einsaetze ab 45 Min (Startelf-Proxy)
STARTER_AVG_MIN = 60.0   # Radar: Durchschnittsminuten im Fenster
FRESH_DAYS = 21     # Radar: letzter Einsatz hoechstens so alt
DIV_STRONG = 1.5    # Tore - xG Schwelle fuer Regressions-/Value-Label

COLS = "player_key,player_name,team,league,home_team,away_team,event_id,match_date,minutes,goals,xg"


# --------------------------------------------------------------------------- Daten
def fetch_rows(url, key):
    import requests
    base_headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    params = {
        "select": COLS,
        "xg": "not.is.null",
        "minutes": "not.is.null",
        "goals": "not.is.null",
        "match_date": "not.is.null",
        "order": "match_date.asc,event_id.asc,player_key.asc",
    }
    rows, start, page = [], 0, 1000
    while True:
        headers = dict(base_headers, **{"Range-Unit": "items", "Range": f"{start}-{start + page - 1}"})
        r = requests.get(f"{url.rstrip('/')}/rest/v1/player_game_log", params=params, headers=headers, timeout=90)
        r.raise_for_status()
        batch = r.json()
        rows.extend(batch)
        if len(batch) < page:
            break
        start += page
    return rows


def by_player(rows):
    d = defaultdict(list)
    for r in rows:
        try:
            r["minutes"] = float(r["minutes"])
            r["goals"] = float(r["goals"])
            r["xg"] = float(r["xg"])
        except (TypeError, ValueError):
            continue
        d[r["player_key"]].append(r)
    for lst in d.values():
        lst.sort(key=lambda r: (str(r["match_date"]), str(r["event_id"])))
    return d


# --------------------------------------------------------------------------- Modell
def window_stats(prev):
    m = sum(r["minutes"] for r in prev)
    return {
        "g": sum(r["goals"] for r in prev),
        "x": sum(r["xg"] for r in prev),
        "m": m,
        "n": len(prev),
        "avgm": m / len(prev) if prev else 0.0,
    }


def calibrate(outcome_rows):
    """Globale Konstanten aus der Stichprobe: Tore/90, xG/90, Tore pro xG."""
    sg = sum(r["goals"] for r in outcome_rows)
    sx = sum(r["xg"] for r in outcome_rows)
    sm = sum(r["minutes"] for r in outcome_rows)
    if sm <= 0 or sx <= 0:
        raise ValueError("Keine verwertbare Stichprobe fuer die Kalibrierung")
    return {"lam_g": sg / sm * 90.0, "lam_x": sx / sm * 90.0, "ratio": sg / sx}


def predict(ws, cal, alpha=ALPHA):
    matches = ws["m"] / 90.0
    rg = (ws["g"] + K * cal["lam_g"]) / (matches + K)
    rx = (ws["x"] + K * cal["lam_x"]) / (matches + K) * cal["ratio"]
    rate = alpha * rg + (1.0 - alpha) * rx
    f = min(ws["avgm"], 90.0) / 90.0
    return 1.0 - math.exp(-rate * f)


# --------------------------------------------------------------------------- Backtest
def backtest(players):
    samples = []
    for lst in players.values():
        for i, cur in enumerate(lst):
            prev = lst[max(0, i - WINDOW):i]
            if len(prev) < MIN_PRIOR or cur["minutes"] < MIN_MINUTES:
                continue
            ws = window_stats(prev)
            if ws["m"] <= 0:
                continue
            samples.append((ws, 1 if cur["goals"] > 0 else 0, cur))
    if not samples:
        print("Zu wenige Daten fuer den Backtest.")
        return
    cal = calibrate([s[2] for s in samples])
    n = len(samples)
    base_rate = sum(s[1] for s in samples) / n

    def brier(fn):
        return sum((fn(s) - s[1]) ** 2 for s in samples) / n

    print(f"Backtest: {n} Einsaetze | Trefferquote (>=1 Tor) {base_rate:.4f} | "
          f"Tore/90 {cal['lam_g']:.4f} | Tore pro xG {cal['ratio']:.3f}\n")
    print(f"{'Modell':<28}{'Brier':>9}")
    print(f"{'Baseline (Liga-Schnitt)':<28}"
          f"{brier(lambda s: 1 - math.exp(-cal['lam_g'] * min(s[0]['avgm'], 90) / 90)):>9.5f}")
    for a in (1.0, 0.5, 0.35, 0.25, 0.15, 0.0):
        tag = {1.0: "nur Tore", 0.0: "nur xG"}.get(a, f"Mix ALPHA={a}")
        print(f"{tag:<28}{brier(lambda s, a=a: predict(s[0], cal, a)):>9.5f}")

    print("\nDivergenz-Buckets (Tore - xG im Fenster):")
    print(f"{'Bucket':<28}{'n':>6}{'real':>9}{'Modell':>9}{'nur Tore':>10}{'nur xG':>9}")
    edges = [(-1e9, -DIV_STRONG, "stark UNTER xG"), (-DIV_STRONG, -0.5, "unter xG"),
             (-0.5, 0.5, "im Soll"), (0.5, DIV_STRONG, "ueber xG"), (DIV_STRONG, 1e9, "stark UEBER xG")]
    for lo, hi, name in edges:
        grp = [s for s in samples if lo <= s[0]["g"] - s[0]["x"] < hi]
        if not grp:
            continue
        k = len(grp)
        print(f"{name:<28}{k:>6}{sum(s[1] for s in grp) / k:>9.4f}"
              f"{sum(predict(s[0], cal) for s in grp) / k:>9.4f}"
              f"{sum(predict(s[0], cal, 1.0) for s in grp) / k:>10.4f}"
              f"{sum(predict(s[0], cal, 0.0) for s in grp) / k:>9.4f}")


# --------------------------------------------------------------------------- Radar
def build_radar(players, today=None):
    today = today or dt.date.today()
    outcome = [r for lst in players.values() for r in lst if r["minutes"] >= MIN_MINUTES]
    cal = calibrate(outcome)
    out = []
    for lst in players.values():
        window = lst[-WINDOW:]
        if len(window) < MIN_PRIOR:
            continue
        last = window[-1]
        try:
            age = (today - dt.date.fromisoformat(str(last["match_date"])[:10])).days
        except ValueError:
            continue
        if age > FRESH_DAYS:
            continue
        ws = window_stats(window)
        if ws["m"] <= 0 or ws["avgm"] < STARTER_AVG_MIN:
            continue
        p = predict(ws, cal)
        p_goals = predict(ws, cal, 1.0)      # was die Tore-Sicht (Markt/Oeffentlichkeit) erwartet
        div = ws["g"] - ws["x"]
        if div >= DIV_STRONG:
            label = "REGRESSION-RISIKO"
        elif div <= -DIV_STRONG:
            label = "UNTERBEWERTET"
        else:
            label = ""
        out.append({
            "spieler": last.get("player_name") or last["player_key"],
            "team": last.get("team") or "",
            "liga": last.get("league") or "",
            "einsaetze": ws["n"],
            "tore": int(ws["g"]),
            "xg": round(ws["x"], 2),
            "divergenz": round(div, 2),
            "p_tor": round(p, 4),
            "fair_quote": round(1.0 / p, 2) if p > 0 else None,
            "p_tore_sicht": round(p_goals, 4),
            "korrektur": round(p - p_goals, 4),
            "label": label,
            "letztes_spiel": str(last["match_date"])[:10],
        })
    return out, cal


def fmt_table(items, title):
    lines = [title, f"{'Spieler':<24}{'Team':<18}{'Tore':>5}{'xG':>6}{'P(Tor)':>8}{'Fair':>7}{'vs Tore-Sicht':>15}"]
    for r in items:
        lines.append(f"{r['spieler'][:23]:<24}{r['team'][:17]:<18}{r['tore']:>5}{r['xg']:>6.1f}"
                     f"{r['p_tor'] * 100:>7.1f}%{r['fair_quote']:>7.2f}{r['korrektur'] * 100:>+14.1f}%")
    return "\n".join(lines)


def report(radar, cal, top):
    top_p = sorted(radar, key=lambda r: -r["p_tor"])[:top]
    under = sorted([r for r in radar if r["label"] == "UNTERBEWERTET"], key=lambda r: -r["korrektur"])[:top]
    over = sorted([r for r in radar if r["label"] == "REGRESSION-RISIKO"], key=lambda r: r["korrektur"])[:top]
    txt = [f"FINISHING RADAR | {len(radar)} Spieler im Fenster | Tore pro xG global {cal['ratio']:.3f}", "",
           fmt_table(top_p, "Hoechste Torwahrscheinlichkeit"), "",
           fmt_table(under, "UNTERBEWERTET - Tore < xG (Tore-Sicht unterschaetzt)"), "",
           fmt_table(over, "REGRESSION-RISIKO - Tore > xG (Tore-Sicht ueberschaetzt)")]
    return "\n".join(txt)


def send_telegram(text):
    import requests
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("Telegram: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID fehlen.", file=sys.stderr)
        return
    for i in range(0, len(text), 3800):
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": "<pre>" + text[i:i + 3800].replace("<", "&lt;") + "</pre>",
                            "parse_mode": "HTML"}, timeout=30)


# --------------------------------------------------------------------------- Selftest
def selftest():
    import random
    random.seed(7)
    rows, today = [], dt.date.today()
    for p in range(60):
        skill = random.uniform(0.1, 0.5)
        for i in range(14):
            xg = max(0.0, random.gauss(skill, 0.15))
            goals = 1.0 if random.random() < 1 - math.exp(-xg) else 0.0
            rows.append({"player_key": f"p{p}", "player_name": f"Spieler {p}", "team": f"Team {p % 6}",
                         "league": "Test", "event_id": f"e{p}_{i}",
                         "match_date": (today - dt.timedelta(days=(14 - i) * 3)).isoformat(),
                         "minutes": 90.0, "goals": goals, "xg": xg})
    players = by_player(rows)
    backtest(players)
    radar, cal = build_radar(players)
    assert radar and all(0 < r["p_tor"] < 1 for r in radar)
    print("\n" + report(radar, cal, 3))
    print("\nSelftest OK")


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Finishing Radar - xG-Regression Torschuetzen-Radar")
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--csv", help="Radar als CSV speichern")
    ap.add_argument("--telegram", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL und SUPABASE_KEY (service_role) muessen gesetzt sein.")
    players = by_player(fetch_rows(url, key))
    if args.backtest:
        backtest(players)
        return
    radar, cal = build_radar(players)
    text = report(radar, cal, args.top)
    print(text)
    if args.csv and radar:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(radar[0].keys()))
            w.writeheader()
            w.writerows(sorted(radar, key=lambda r: -r["p_tor"]))
    if args.telegram:
        send_telegram(text)


if __name__ == "__main__":
    main()