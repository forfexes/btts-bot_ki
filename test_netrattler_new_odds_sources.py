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


def test_odds_api_io_opt_in_and_exact_1x2(monkeypatch):
    import netrattler_odds_harvester as h
    monkeypatch.delenv("ODDS_API_IO_KEY", raising=False)
    assert h.collect_odds_api_io("2026-10-25") == []
    monkeypatch.setenv("ODDS_API_IO_KEY", "test-only")
    monkeypatch.setenv("ODDS_API_IO_MAX_EVENTS", "1")
    class Response:
        status_code = 200
        def __init__(self, value): self.value = value
        def raise_for_status(self): pass
        def json(self): return self.value
    calls = []
    def get(url, params, timeout):
        calls.append(url)
        if url.endswith("/events"):
            return Response([{"id": 42, "home": "A", "away": "B", "date": "2026-10-25T17:00:00Z"}])
        return Response({"bookmakers": {"Book": [
            {"name": "ML", "odds": {"home": "2.10", "draw": "3.30", "away": "3.40"}},
            {"name": "Player Shots", "odds": {"home": "99", "draw": "99", "away": "99"}}]}})
    monkeypatch.setattr(h.requests, "get", get)
    rows = h.collect_odds_api_io("2026-10-25")
    assert len(calls) == 2
    assert len(rows) == 3
    assert {x["selection"] for x in rows} == {"home", "draw", "away"}
    assert all(x["source"] == "odds_api_io" and x["market"] == "1x2" for x in rows)


def test_scraper_dedupe_keeps_distinct_lines_and_freshest_price():
    import netrattler_odds_harvester as h
    def quote(price, stamp, line):
        return {"home_team": "A", "away_team": "B", "market": "totals", "selection": "over",
                "source": "bwin", "bookmaker": "bwin", "match_date": "2026-10-25",
                "odds": price, "raw": {"line": line, "captured_at": stamp}}
    rows = h._dedupe([quote(4.5, "2026-10-25T10:00:00Z", 2.5),
                      quote(1.9, "2026-10-25T10:05:00Z", 2.5),
                      quote(2.3, "2026-10-25T10:04:00Z", 3.5)])
    assert len(rows) == 2
    assert {r["raw"]["line"]: r["odds"] for r in rows} == {2.5: 1.9, 3.5: 2.3}
