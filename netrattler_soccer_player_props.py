#!/usr/bin/env python3
"""Quota-bounded soccer player-props collector for The Odds API v4."""
import os
import requests
from netrattler_odds_harvester import _keys, _row, _dedupe

BASE="https://api.the-odds-api.com/v4"
MARKETS=("player_goal_scorer_anytime","player_first_goal_scorer","player_last_goal_scorer","player_to_receive_card","player_to_receive_red_card","player_shots_on_target")
LEAGUES=("soccer_epl","soccer_spain_la_liga","soccer_germany_bundesliga","soccer_italy_serie_a","soccer_france_ligue_one","soccer_usa_mls")

def normalize(event, sport):
    rows=[]
    for book in event.get("bookmakers") or []:
        for market in book.get("markets") or []:
            mk=market.get("key")
            if mk not in MARKETS: continue
            for outcome in market.get("outcomes") or []:
                player=str(outcome.get("description") or "").strip()
                name=str(outcome.get("name") or "").strip()
                if not player and mk!="player_shots_on_target" and name.lower() not in ("yes","no"):
                    player=name
                    name="Yes"
                if not player: continue
                selection=f"{player} | {name}"
                row=_row(source="the_odds_api_player_props",bookmaker=book.get("key") or book.get("title") or "unknown",event_id=event.get("id"),league=sport,home=event.get("home_team"),away=event.get("away_team"),commence_time=event.get("commence_time"),market=mk,selection=selection,odds=outcome.get("price"),line=outcome.get("point"),raw={"player":player,"outcome":name,"sport_key":sport,"market_last_update":market.get("last_update")})
                if row: rows.append(row)
    return rows

def collect(max_events=1, max_leagues=1, session=requests):
    keys=_keys()
    if not keys: return [],{"error":"no_keys"}
    max_events=max(0,min(int(max_events),3))
    max_leagues=max(0,min(int(max_leagues),3))
    diag={"events_checked":0,"events_with_props":0,"http_status":[],"remaining":None}
    rows=[]
    for league in LEAGUES[:max_leagues]:
        try:
            resp=session.get(f"{BASE}/sports/{league}/events/",params={"apiKey":keys[0]},timeout=15)
            diag["http_status"].append(resp.status_code)
            if not resp.ok: continue
            events=resp.json()
            if not isinstance(events,list): continue
            for event in events[:max_events]:
                eid=event.get("id")
                if not eid: continue
                diag["events_checked"]+=1
                # Soccer player props are primarily US-region markets.
                params={"apiKey":keys[0],"regions":"us","markets":",".join(MARKETS),"oddsFormat":"decimal"}
                result=session.get(f"{BASE}/sports/{league}/events/{eid}/odds/",params=params,timeout=15)
                diag["http_status"].append(result.status_code)
                diag["remaining"]=result.headers.get("x-requests-remaining")
                if not result.ok: continue
                data=result.json()
                if isinstance(data,dict):
                    new=normalize(data,league)
                    rows.extend(new)
                    if new: diag["events_with_props"]+=1
        except (requests.RequestException,ValueError,TypeError,KeyError) as exc:
            diag["error_type"]=type(exc).__name__
    return _dedupe(rows),diag

if __name__=="__main__":
    import json
    rows,diag=collect(int(os.getenv("PROPS_MAX_EVENTS","1")),int(os.getenv("PROPS_MAX_LEAGUES","1")))
    print("Player-props diagnostic:",json.dumps(diag,sort_keys=True))
    print("Normalized player-prop rows:",len(rows))
    print("Markets found:",sorted(set(x["market"] for x in rows)))
    # Deliberately no DB writes or Telegram sends in this diagnostic.
