#!/usr/bin/env python3
import argparse
import json
import math
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from supabase_client import SupabaseRest

def n(raw: Dict[str, Any], *names: str) -> float:
    for name in names:
        v = raw.get(name)
        if v is None or v == "":
            continue
        try:
            return float(str(v).replace(",", ""))
        except Exception:
            pass
    return 0.0

def per90(value: float, minutes: float) -> float:
    if not minutes or minutes <= 0:
        return 0.0
    return round(value / max(minutes / 90.0, 1), 3)

def implied_hit_rate(avg: float, line: float) -> float:
    # Simple Poisson Näherung: P(X > line)
    threshold = math.floor(line + 0.00001)
    lam = max(avg, 0.01)
    cdf = sum(math.exp(-lam) * (lam ** k) / math.factorial(k) for k in range(threshold + 1))
    return round(max(0.0, min(1.0, 1 - cdf)) * 100, 1)

def build_player_props(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not rows:
        return None

    by_table = {r["table_name"]: r.get("raw") or {} for r in rows}
    base = rows[0]
    minutes = max([float(r.get("minutes") or 0) for r in rows] + [0])

    standard = by_table.get("standard", {})
    shooting = by_table.get("shooting", {})
    passing = by_table.get("passing", {})
    pass_types = by_table.get("pass_types", {})
    defense = by_table.get("defense", {})
    possession = by_table.get("possession", {})
    misc = by_table.get("misc", {})

    stats = {
        "shots": per90(n(shooting, "Sh", "Standard_Sh"), minutes),
        "shots_on_target": per90(n(shooting, "SoT", "Standard_SoT"), minutes),
        "xg": per90(n(shooting, "xG", "Expected_xG"), minutes),
        "goals": per90(n(standard, "Gls", "Performance_Gls"), minutes),
        "assists": per90(n(standard, "Ast", "Performance_Ast"), minutes),
        "key_passes": per90(n(passing, "KP"), minutes),
        "crosses": per90(n(pass_types, "Crs", "Pass_Types_Crs"), minutes),
        "tackles": per90(n(defense, "Tkl", "Tackles_Tkl"), minutes),
        "interceptions": per90(n(defense, "Int"), minutes),
        "blocks": per90(n(defense, "Blocks", "Blocks_Blocks"), minutes),
        "dribbles_success": per90(n(possession, "Succ", "Take-Ons_Succ"), minutes),
        "fouls_committed": per90(n(misc, "Fls", "Performance_Fls"), minutes),
        "fouls_drawn": per90(n(misc, "Fld", "Performance_Fld"), minutes),
        "yellow_cards": per90(n(misc, "CrdY", "Performance_CrdY"), minutes),
        "offsides": per90(n(misc, "Off", "Performance_Off"), minutes),
    }

    markets = {}
    for key, avg in stats.items():
        common_line = 0.5
        if key in ["shots", "tackles", "crosses"]:
            common_line = 1.5
        if key in ["xg", "goals", "yellow_cards", "offsides"]:
            common_line = 0.5
        markets[key] = {
            "avg_per90": avg,
            "line": common_line,
            "estimated_over_hit_pct": implied_hit_rate(avg, common_line),
        }

    return {
        "player": base["player"],
        "squad": base["squad"],
        "league_name": base["league_name"],
        "minutes": minutes,
        "markets": markets,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--team", required=True)
    parser.add_argument("--league", default="")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()

    supa = SupabaseRest()
    params = {
        "squad": f"eq.{args.team}",
        "select": "player,squad,league_name,table_name,minutes,raw",
        "limit": "10000",
    }
    if args.league:
        params["league_name"] = f"eq.{args.league}"

    rows = supa.select("fbref_player_stats", params)
    grouped = {}
    for r in rows:
        key = (r["player"], r["squad"], r["league_name"])
        grouped.setdefault(key, []).append(r)

    outputs = []
    for _, group in grouped.items():
        props = build_player_props(group)
        if props:
            outputs.append(props)

    print(json.dumps(outputs, ensure_ascii=False, indent=2))

    if args.save and outputs:
        save_rows = [{
            "player": p["player"],
            "squad": p["squad"],
            "league_name": p["league_name"],
            "props": p,
        } for p in outputs]
        supa.upsert("generated_player_props", save_rows, on_conflict="player,squad,league_name")

if __name__ == "__main__":
    main()
