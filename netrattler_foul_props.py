"""Foul-/Tackle-Props (begangene / gezogene Fouls) aus der Spielerhistorie, ohne Buchmacherquote.

Die Quote ist die faire Modellquote (1/p) und wird als solche markiert
(source="model_line_fouls", odds=0 -> die Quote muss beim Buchmacher geprueft werden).
Tackles gibt es nur fuer Spieler mit FPL-/API-Football-Daten (Premier League u.a.); fehlende Werte werden ignoriert.
"""
import os
from datetime import date
import requests

MIN_GAMES = 8
MIN_AVG_MINUTES = 55.0
STATS = {"fouls_committed": "fouls", "fouls_won": "fouls_won", "tackles": "tackles_committed", "shots": "shots", "sot": "sot"}
LINES = {"fouls_committed": (1, 2, 3), "fouls_won": (1, 2, 3), "tackles": (2, 3, 4), "shots": (2, 3, 4), "sot": (1, 2)}  # 1+ ist zu banal
LABEL = {"fouls_committed": "Fouls", "fouls_won": "Fouls gezogen", "tackles": "Tackles", "shots": "Schüsse", "sot": "Schüsse aufs Tor"}
MIN_HIT = float(os.getenv("NETRATTLER_FOUL_MIN_HIT", "0.70"))
MAX_PER_TEAM = int(os.getenv("NETRATTLER_FOUL_MAX_PER_TEAM", "8"))


def _sig(name):
    """Kurzer Suchbegriff fuer ilike (laengstes Wort des Teamnamens)."""
    words = [w for w in str(name or "").replace(".", " ").split() if len(w) > 2]
    return max(words, key=len) if words else str(name or "")


_STOP = {"fc", "sc", "cf", "afc", "fk", "sk", "ac", "as", "cd", "ca", "club"}


def same_team(a, b):
    ta = {t for t in str(a or "").lower().replace(".", " ").split() if t not in _STOP}
    tb = {t for t in str(b or "").lower().replace(".", " ").split() if t not in _STOP}
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if small <= big:
        return len(small) >= 2 or max(len(t) for t in small) >= 7
    return False


def player_rows(rows, team_norm, norm, team_raw=None):
    """rows: player_game_log-Zeilen (neueste zuerst) -> {player: [rows]} nur fuer dieses Team."""
    by = {}
    today = date.today().isoformat()
    for r in rows or []:
        if str(r.get("match_date") or "")[:10] > today:
            continue
        if norm(r.get("team")) != team_norm and not same_team(r.get("team"), team_raw):
            continue
        by.setdefault(r.get("player_name") or r.get("player_key"), []).append(r)
    return by


def _played(g):
    if str(g.get("match_date") or "")[:10] > date.today().isoformat():
        return False
    # ESPN-Zeilen haben oft keine Minuten (None) -> nicht ausschliessen; nur echte 0 Minuten zaehlen nicht.
    if g.get("minutes") is not None:
        return g["minutes"] > 0
    # ohne Minutenangabe: nur Zeilen mit irgendeiner Aktion gelten als gespielt (Bank/Nichteinsatz ausschliessen)
    return any((g.get(k) or 0) > 0 for k in ("shots", "sot", "fouls_committed", "fouls_won", "tackles", "passes"))


def foul_profiles(by_player, team, match, league, kickoff, n=10):
    """Je Spieler die Reihen der letzten Spiele (Fouls begangen/gezogen, Schuesse, Schuesse aufs Tor, Gelbe) fuer Leitern/Karten."""
    out = []
    keys = {"fouls": "fouls_committed", "fouls_won": "fouls_won", "tackles": "tackles", "shots": "shots", "sot": "sot", "yellow": "yellow_cards"}
    for name, games in by_player.items():
        games = [g for g in games if _played(g)][:n]
        if len(games) < MIN_GAMES:
            continue
        known = [g["minutes"] for g in games if g.get("minutes") is not None]
        if known and sum(known) / len(known) < MIN_AVG_MINUTES:
            continue
        prof = {"source": "foul_profile", "player": name, "team": team, "match": match, "league": league, "kickoff": kickoff}
        for k, col in keys.items():
            vals = [g.get(col) for g in games]
            if all(v is not None for v in vals):
                prof[k] = [int(v) for v in vals]
        if "fouls" in prof or "shots" in prof or "yellow" in prof:
            out.append(prof)
    return out


def legs_for_player(name, games, n=10):
    """Gibt Liste von (stat, line, hit_rate, games, series) fuer starke Linien zurueck."""
    games = [g for g in games if _played(g)][:n]
    if len(games) < MIN_GAMES:
        return []
    known = [g["minutes"] for g in games if g.get("minutes") is not None]
    if known and sum(known) / len(known) < MIN_AVG_MINUTES:
        return []
    out = []
    for stat, lines in LINES.items():
        vals = [g.get(stat) for g in games if g.get(stat) is not None]
        if len(vals) < MIN_GAMES:
            continue
        for line in lines:
            hits = sum(1 for v in vals if v >= line)
            rate = hits / len(vals)
            need = 0.90 if line == 1 and stat in ("fouls_committed", "fouls_won") else MIN_HIT  # 1+ nur bei sehr hoher Quote
            if rate >= need:
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
        params={"team": f"ilike.*{_sig(team)}*", "match_date": f"lte.{date.today().isoformat()}",
                "order": "match_date.desc", "limit": "1000",
                "select": "player_name,player_key,team,match_date,minutes,fouls_committed,fouls_won,tackles,shots,sot,passes,yellow_cards"},
        timeout=25,
    )
    return r.json() if r.ok and isinstance(r.json(), list) else []


STATS_LAST = {}


def rows_for_matches(matches, url, key, norm):
    """matches: [{'match': 'A vs B', 'league':..., 'kickoff':...}] -> Pool-Zeilen."""
    if os.getenv("NETRATTLER_FOUL_PROPS", "on").lower() == "off":
        return []
    out = []
    STATS_LAST.clear()
    STATS_LAST.update({"matches": len(matches), "teams": 0, "teams_with_rows": 0, "teams_with_players": 0, "legs": 0, "unmatched": []})
    for m in matches:
        parts = str(m.get("match", "")).split(" vs ")
        if len(parts) != 2:
            continue
        for team in parts:
            STATS_LAST["teams"] += 1
            rows = fetch_team_rows(url, key, team.strip())
            STATS_LAST["teams_with_rows"] += 1 if rows else 0
            by = player_rows(rows, norm(team), norm, team)
            STATS_LAST["teams_with_players"] += 1 if by else 0
            if rows and not by and len(STATS_LAST["unmatched"]) < 6:
                STATS_LAST["unmatched"].append([team.strip(), str(rows[0].get("team"))])
            out += build_rows(by, team.strip(), m["match"], m.get("league", ""), m.get("kickoff", ""))
            out += foul_profiles(by, team.strip(), m["match"], m.get("league", ""), m.get("kickoff", ""))
    STATS_LAST["legs"] = sum(1 for r in out if r.get("source") == "model_line_fouls")
    STATS_LAST["profiles"] = sum(1 for r in out if r.get("source") == "foul_profile")
    return out
