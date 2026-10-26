"""fplci_player_match (ESPN + FPL-Core-Insights) -> player_game_log (Quelle der Builder-Spielerwahrscheinlichkeiten).
Nur Spieler mit Einsatz (minutes>0). Idempotenter Upsert (player_key,event_id)."""
import os, sys, requests

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H = {"apikey": SK, "Authorization": f"Bearer {SK}"}


def to_log_row(r):
    name = str(r.get("player_name") or "").strip()
    if not name or not r.get("match_date") or not r.get("match_id"):
        return None
    try:
        if float(r.get("minutes") or 0) <= 0:
            return None
    except (TypeError, ValueError):
        return None
    return {
        "player_key": name.lower(), "event_id": str(r["match_id"]), "source": r.get("source") or "fplci",
        "player_id": str(r.get("player_id") or ""), "player_name": name, "team": r.get("team"),
        "league": r.get("league"), "match_date": r["match_date"], "minutes": r.get("minutes"),
        "shots": r.get("shots"), "sot": r.get("shots_on"), "goals": r.get("goals"), "assists": r.get("assists"),
        "fouls_committed": r.get("fouls_committed"), "fouls_won": r.get("fouls_drawn"), "tackles": r.get("tackles"),
        "yellow_cards": r.get("yellow"), "red_cards": r.get("red"), "saves": r.get("saves"), "xg": r.get("xg"),
    }


def main():
    if not SB or not SK:
        print("SUPABASE fehlt"); return 1
    done, off = 0, 0
    while True:
        r = requests.get(f"{SB}/rest/v1/fplci_player_match", headers=H, timeout=60, params={
            "select": "match_id,player_id,player_name,team,league,match_date,minutes,shots,shots_on,goals,assists,"
                      "fouls_committed,fouls_drawn,tackles,yellow,red,saves,xg,source",
            "minutes": "gt.0", "order": "match_id.asc,player_id.asc", "limit": "1000", "offset": str(off)})
        if not r.ok:
            print("lesen fehlgeschlagen", r.status_code); return 1
        rows = r.json()
        if not rows:
            break
        out = [x for x in (to_log_row(y) for y in rows) if x]
        if out:
            w = requests.post(f"{SB}/rest/v1/player_game_log?on_conflict=player_key,event_id", timeout=60, json=out,
                              headers={**H, "Content-Type": "application/json",
                                       "Prefer": "resolution=merge-duplicates,return=minimal"})
            if not w.ok:
                print("schreiben fehlgeschlagen", w.status_code, w.text[:200]); return 1
            done += len(out)
        off += 1000
    print(f"player_game_log synchronisiert: {done} Zeilen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
