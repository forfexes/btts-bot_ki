"""Foul-/Tackle-Props (begangene / gezogene Fouls) aus der Spielerhistorie, ohne Buchmacherquote.

Die Quote ist die faire Modellquote (1/p) und wird als solche markiert
(source="model_line_fouls", odds=0 -> die Quote muss beim Buchmacher geprueft werden).
Tackles gibt es nur fuer Spieler mit FPL-/API-Football-Daten (Premier League u.a.); fehlende Werte werden ignoriert.
"""
import os
import requests

MIN_GAMES = 8
MIN_AVG_MINUTES = 55.0
STATS = {"fouls_committed": "fouls", "fouls_won": "fouls_won", "tackles": "tackles_committed", "shots": "shots", "sot": "sot"}
LINES = {"fouls_committed": (2, 3), "fouls_won": (2, 3), "tackles": (2, 3, 4), "shots": (2, 3, 4), "sot": (1, 2)}  # 1+ ist zu banal
LABEL = {"fouls_committed": "Fouls", "fouls_won": "Fouls gezogen", "tackles": "Tackles", "shots": "Schüsse", "sot": "Schüsse aufs Tor"}
MIN_HIT = float(os.getenv("NETRATTLER_FOUL_MIN_HIT", "0.70"))
MAX_PER_TEAM = int(os.getenv("NETRATTLER_FOUL_MAX_PER_TEAM", "8"))


def _sig(name):
    """Kurzer Suchbegriff fuer ilike (laengstes Wort des Teamnamens)."""
    words = [w for w in str(name or "").replace(".", " ").split() if len(w) > 2]
    return max(words, key=len) if words else str(name or "")


def player_rows(rows, team_norm, norm):
    """rows: player_game_log-Zeilen (neueste zuerst) -> {player: [rows]} nur fuer dieses Team."""
    by = {}
    for r in rows or []:
        if norm(r.get("team")) != team_norm:
            continue
        by.setdefault(r.get("player_name") or r.get("player_key"), []).append(r)
    return by


def legs_for_player(name, games, n=10):
    """Gibt Liste von (stat, line, hit_rate, games, series) fuer starke Linien zurueck."""
    games = [g for g in games if (g.get("minutes") or 0) > 0][:n]
    if len(games) < MIN_GAMES:
        return []
    if sum((g.get("minutes") or 0) for g in games) / len(games) < MIN_AVG_MINUTES:
        return []
    out = []
    for stat, lines in LINES.items():
        vals = [g.get(stat) for g in games if g.get(stat) is not None]
        if len(vals) < MIN_GAMES:
            continue
        for line in lines:
            hits = sum(1 for v in vals if v >= line)
            rate = hits / len(vals)
            if rate >= MIN_HIT:
                out.append((stat, line, rate, len(vals), [int(v) for v in vals]))
    # pro Statistik nur die hoechste Linie, die die Huerde noch schafft
    best = {}
    for item in out:
        if item[0] not in best or item[1] > best[item[0]][1]:
            best[item[0]] = item
    return list(best.values())


def build_rows(by_player, team, match, league, kickoff):
    cands = []
    for name, games in by_player.items():
        for stat, line, rate, ngames, series in legs_for_player(name, games):
            # leicht geglaettete Wahrscheinlichkeit (kleine Stichprobe)
            p = (rate * ngames + 0.5 * 2) / (ngames + 2)
            cands.append({
                "player": name, "team": team, "match": match, "league": league,
                "market": f"{name} {line}+ {LABEL[stat]}",
                "category": STATS[stat], "line": float(line), "odds": 0.0,
                "probability": round(p * 100, 1), "source": "model_line_fouls",
                "kickoff": kickoff, "games": ngames, "hit_rate": round(rate * 100, 1),
                "series": series,
            })
    cands.sort(key=lambda c: (-c["probability"], -c["line"]))
    return cands[:MAX_PER_TEAM]


def fetch_team_rows(url, key, team):
    r = requests.get(
        f"{url}/rest/v1/player_game_log",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        params={"team": f"ilike.*{_sig(team)}*", "order": "match_date.desc", "limit": "1000",
                "select": "player_name,player_key,team,match_date,minutes,fouls_committed,fouls_won,tackles,shots,sot"},
        timeout=25,
    )
    return r.json() if r.ok and isinstance(r.json(), list) else []


def rows_for_matches(matches, url, key, norm):
    """matches: [{'match': 'A vs B', 'league':..., 'kickoff':...}] -> Pool-Zeilen."""
    if os.getenv("NETRATTLER_FOUL_PROPS", "on").lower() == "off":
        return []
    out = []
    for m in matches:
        parts = str(m.get("match", "")).split(" vs ")
        if len(parts) != 2:
            continue
        for team in parts:
            rows = fetch_team_rows(url, key, team.strip())
            by = player_rows(rows, norm(team), norm)
            out += build_rows(by, team.strip(), m["match"], m.get("league", ""), m.get("kickoff", ""))
    return out
