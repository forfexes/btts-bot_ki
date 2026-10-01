import os
import netrattler_quote_consensus as qc
import netrattler_sockodds as so

def test_consensus_two_sources():
    rows=[{"match":"A vs B","market":"btts","selection":"yes","odds":1.90,"source":"oddspapi"},
          {"match":"A vs B","market":"btts","selection":"yes","odds":1.95,"source":"5dollar"}]
    assert qc.consensus(rows)["ok"] is True

def test_consensus_rejects_weak_single():
    r=qc.consensus([{"match":"A vs B","market":"btts","selection":"yes","odds":1.9,"source":"random_scrape"}])
    assert r["ok"] is False

def test_sockodds_only_real_player_entities():
    e={"eventID":"x","odds":{"a":{"oddID":"x","marketName":"Shots","statEntityID":"all","byBookmaker":{"b":{"decimal":1.9}}},
                             "b":{"oddID":"y","marketName":"Shots","statEntityID":"PLAYER_1","byBookmaker":{"b":{"decimal":2.1,"available":True}}}}}
    rows=so.player_prop_rows(e)
    assert len(rows)==1 and rows[0]["player_id"]=="PLAYER_1"


def test_team_markets_never_look_like_sockodds_player_props():
    e={"eventID":"x","odds":{
      "btts":{"marketName":"BTTS","statEntityID":"all","byBookmaker":{"book":{"decimal":1.8}}},
      "goal":{"marketName":"Team Goals","statEntityID":"home","byBookmaker":{"book":{"decimal":1.7}}}
    }}
    assert so.player_prop_rows(e)==[]

def test_consensus_rejects_line_mismatch():
    rows=[{"match":"A vs B","market":"corners","selection":"over","line":9.5,"odds":1.9,"source":"oddspapi"},
          {"match":"A vs B","market":"corners","selection":"over","line":10.5,"odds":1.9,"source":"5dollar"}]
    assert qc.consensus(rows)["ok"] is False
