"""fplci_player_match (ESPN + FPL-Core-Insights) -> player_game_log (Quelle der Builder-Spielerwahrscheinlichkeiten).
Eine Zeile pro Spieler und Spieltag (Schluessel player_key + 'datum:player_key'). FPL liefert Kurznamen ('Haaland'),
ESPN volle Namen ('Erling Haaland'): FPL-Zeilen werden dem ESPN-Namen zugeordnet und mit ihm zu einer Zeile verschmolzen
(FPL liefert Tackles/Minuten/xG, ESPN den Rest). Alte Zeilen im frueheren Format (event_id ohne ':') werden nach
erfolgreichem Schreiben entfernt (abgeleitete Tabelle, jederzeit aus fplci_player_match neu aufbaubar)."""
import os, re, sys, unicodedata, requests
from collections import defaultdict

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H = {"apikey": SK, "Authorization": f"Bearer {SK}"}
SELECT = ("match_id,player_id,player_name,team,league,match_date,minutes,shots,shots_on,goals,assists,"
          "fouls_committed,fouls_drawn,tackles,yellow,red,saves,xg,source")


def norm_name(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]", " ", s).split()


def key_of(name):
    return " ".join(norm_name(name))


def team_sim(a, b):
    ta, tb = set(norm_name(a)) - {"fc", "afc", "cf"}, set(norm_name(b)) - {"fc", "afc", "cf"}
    if not ta or not tb:
        return False
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return all(any(l.startswith(t[:3]) for l in long_) for t in short)


def to_log_row(r):
    """Einzelne Zeile (ohne Zusammenfuehrung) im Zielformat; None wenn kein Einsatz belegt."""
    name = str(r.get("player_name") or "").strip()
    if not name or not r.get("match_date") or not r.get("match_id"):
        return None
    if r.get("source") != "espn":  # ESPN liefert nur eingesetzte Spieler, aber keine Minuten
        try:
            if float(r.get("minutes") or 0) <= 0:
                return None
        except (TypeError, ValueError):
            return None
    return {
        "player_key": key_of(name), "event_id": f"{r['match_date']}:{key_of(name)}", "source": r.get("source") or "fplci",
        "player_id": str(r.get("player_id") or ""), "player_name": name, "team": r.get("team"),
        "league": r.get("league"), "match_date": r["match_date"], "minutes": r.get("minutes"),
        "shots": r.get("shots"), "sot": r.get("shots_on"), "goals": r.get("goals"), "assists": r.get("assists"),
        "fouls_committed": r.get("fouls_committed"), "fouls_won": r.get("fouls_drawn"), "tackles": r.get("tackles"),
        "yellow_cards": r.get("yellow"), "red_cards": r.get("red"), "saves": r.get("saves"), "xg": r.get("xg"),
    }


def build_canonical(rows):
    """rows: Rohzeilen aus fplci_player_match -> Liste verschmolzener Log-Zeilen."""
    espn_by_day = defaultdict(list)
    for r in rows:
        if r.get("source") == "espn" and r.get("player_name"):
            espn_by_day[r["match_date"]].append(r)
    # FPL-Spieler-ID -> ESPN-Vollname (aus allen Tagen mit eindeutigem Treffer)
    name_of = {}
    for r in rows:
        if r.get("source") == "espn" or not r.get("player_name"):
            continue
        toks = norm_name(r["player_name"])
        if not toks:
            continue
        cands = []
        for e in espn_by_day.get(r["match_date"], []):
            et = norm_name(e["player_name"])
            if et and et[-1] == toks[-1] and set(toks) <= set(et) and team_sim(r.get("team"), e.get("team")):
                cands.append(e)
        if len(cands) == 1:
            name_of.setdefault(("fpl", str(r.get("player_id"))), cands[0]["player_name"])
    merged = {}
    for r in rows:
        rr = dict(r)
        if r.get("source") != "espn":
            canon = name_of.get(("fpl", str(r.get("player_id"))))
            if canon:
                rr["player_name"] = canon
        row = to_log_row(rr)
        if not row:
            continue
        k = (row["player_key"], row["match_date"])
        old = merged.get(k)
        if old is None:
            merged[k] = row
        else:
            # Verschmelzen: FPL-Werte fuer minutes/tackles/xg bevorzugen, sonst erste nichtleere
            fpl_first = row if row["source"] != "espn" else old
            other = old if fpl_first is row else row
            out = dict(other)
            for f, v in fpl_first.items():
                if v is not None and (f in ("minutes", "tackles", "xg") or out.get(f) is None):
                    out[f] = v
            out["source"] = "fpl+espn"
            merged[k] = out
    return list(merged.values())


def fetch_all():
    rows, off = [], 0
    while True:
        r = requests.get(f"{SB}/rest/v1/fplci_player_match", headers=H, timeout=60, params={
            "select": SELECT, "order": "match_id.asc,player_id.asc", "limit": "1000", "offset": str(off)})
        if not r.ok:
            raise RuntimeError(f"lesen fehlgeschlagen {r.status_code}")
        part = r.json()
        if not part:
            return rows
        rows.extend(part)
        off += 1000


def main():
    if not SB or not SK:
        print("SUPABASE fehlt"); return 1
    rows = fetch_all()
    out = build_canonical(rows)
    ok = 0
    for i in range(0, len(out), 800):
        part = out[i:i + 800]
        w = requests.post(f"{SB}/rest/v1/player_game_log?on_conflict=player_key,event_id", timeout=60, json=part,
                          headers={**H, "Content-Type": "application/json",
                                   "Prefer": "resolution=merge-duplicates,return=minimal"})
        if w.ok:
            ok += len(part)
        else:
            print("schreiben fehlgeschlagen", w.status_code, w.text[:200])
    print(f"player_game_log: {ok}/{len(out)} Zeilen geschrieben")
    if ok == len(out) and os.getenv("GAME_LOG_PRUNE_OLD", "1") == "1":
        d = requests.delete(f"{SB}/rest/v1/player_game_log?event_id=not.like.*:*", headers={**H, "Prefer": "return=minimal"}, timeout=120)
        print("alte Zeilen (Altformat) entfernt:", d.status_code)
    return 0


if __name__ == "__main__":
    sys.exit(main())
