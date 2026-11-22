"""Integration QA: API-Football lineup -> real L15 profile -> research-only board."""
from datetime import datetime, timedelta, timezone
import netrattler_lineup_builders as lineup


def test_lineup_scan_collects_fouls_research_without_telegram(monkeypatch, capsys):
    now = datetime.now(timezone.utc)
    f = {
        "id": 80001, "league_id": 39, "league": "Premier League",
        "home": "Newcastle United", "away": "Arsenal",
        "home_team_id": 10, "away_team_id": 20,
        "ko": (now + timedelta(minutes=55)).isoformat(),
    }
    home = ["Joe Willock", "William Osula", "Bruno Guimaraes",
            "Newcastle A", "Newcastle B", "Newcastle C", "Newcastle D",
            "Newcastle E", "Newcastle F", "Newcastle G", "Newcastle H"]
    away = [f"Arsenal {i}" for i in
            ("One","Two","Three","Four","Five","Six","Seven",
             "Eight","Nine","Ten","Eleven")]
    provider = [
        {"team": {"id":10}, "startXI":[
            {"player":{"id":100+i,"name":x}} for i,x in enumerate(home)]},
        {"team": {"id":20}, "startXI":[
            {"player":{"id":200+i,"name":x}} for i,x in enumerate(away)]},
    ]
    source = [
        {"source":"foul_profile","player":"Joe Willock",
         "team":"Newcastle United","match":"Newcastle United vs Arsenal",
         "history_order":"latest_first","fouls":[2]*15,
         "fouls_won":[3]*15,"minutes_series":[90]*15},
        {"source":"foul_profile","player":"Bruno Guimaraes",
         "team":"Newcastle United","match":"Newcastle United vs Arsenal",
         "history_order":"latest_first","fouls":[3]*15,
         "fouls_won":[2]*15,"minutes_series":[90]*15},
    ]
    monkeypatch.setattr(lineup,"KEYS",["qa"])
    monkeypatch.setattr(lineup,"SB","https://qa.invalid")
    monkeypatch.setattr(lineup,"SK","qa")
    monkeypatch.setattr(lineup,"_diag_rows",lambda probe,day:[])
    reports=[]
    monkeypatch.setattr(lineup,"_diag",reports.append)
    monkeypatch.setattr(lineup,"load_fixtures",lambda day,now:([f],1))
    monkeypatch.setattr(lineup,"_api",lambda path,params:object())
    monkeypatch.setattr(lineup,"checked_response",lambda response:provider)
    monkeypatch.setattr(lineup.fp,"rows_for_matches",lambda *args:source)
    monkeypatch.setattr(lineup.mb,"run",lambda rows,*args: 0)
    original=lineup.premium_fouls.scout_foul_candidates
    seen=[]
    def scout(*args,**kwargs):
        result=original(*args,**kwargs)
        seen.append(result)
        return result
    monkeypatch.setattr(lineup.premium_fouls,"scout_foul_candidates",scout)
    assert lineup.run()==0
    assert len(seen)==1 and len(seen[0]["candidates"])>=4
    assert seen[0]["publication_allowed"] is False
    assert seen[0]["bookmaker_total_odds"] is None
    assert "PREMIUM_FOUL_SCOUT_RESEARCH_ONLY" in capsys.readouterr().out
    assert any(x["probe"]=="lineup_run" and x["sent"]==0 for x in reports)


def test_team_specific_xi_rejects_opponents_and_foreign_player():
    fixture={"home":"Newcastle United","away":"Arsenal",
             "home_team_id":10,"away_team_id":20}
    original={
        "home":{"team_id":10,"starters":["Joe Willock","William Osula"]},
        "away":{"team_id":20,"starters":["Arsenal One","Arsenal Two"]},
    }
    verified={"Newcastle United vs Arsenal":(fixture,original)}
    rows=[
        {"match":"Newcastle United vs Arsenal","player":"Joe Willock",
         "team":"Newcastle United","source":"foul_profile"},
        {"match":"Newcastle United vs Arsenal","player":"Joe Willock",
         "team":"Arsenal","source":"foul_profile"},
        {"match":"Newcastle United vs Arsenal","player":"Ezri Konsa",
         "team":"Aston Villa","source":"foul_profile"},
        {"match":"Newcastle United vs Arsenal","player":"Arsenal One",
         "team":"Arsenal","source":"foul_profile"},
        {"match":"Liverpool vs Arsenal","player":"Arsenal One",
         "team":"Arsenal","source":"foul_profile"},
    ]
    filtered=lineup.filter_verified_team_starters(rows,verified)
    assert filtered==[rows[0],rows[3]]
    assert lineup.filter_verified_team_starters(rows,{})==[]
    # An invalid source team-ID must never silently reuse the same names.
    suspicious={"Newcastle United vs Arsenal":(
        fixture,{**original,"home":{**original["home"],"team_id":999}})}
    assert lineup.filter_verified_team_starters(rows[:1],suspicious)==[]
