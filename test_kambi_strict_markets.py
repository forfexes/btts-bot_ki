import netrattler_prop_sources as ps
import netrattler_kambi_team_odds as kt


def _bo(label, outcomes):
    return {"criterion": {"label": label, "englishLabel": label}, "outcomes": outcomes}


def _oc(label, odds, line=None, typ=None):
    d = {"label": label, "odds": int(odds * 1000)}
    if line is not None:
        d["line"] = int(line * 1000)
    if typ:
        d["type"] = typ
    return d


OFFER = {"events": [{"id": 1, "state": "NOT_STARTED"}], "betOffers": [
    _bo("Full Time", [_oc("1", 1.9), _oc("X", 3.6), _oc("2", 4.2)]),
    _bo("3-Way Handicap", [_oc("1", 7.5), _oc("X", 4.4), _oc("2", 1.3)]),
    _bo("Both Teams To Score", [_oc("Yes", 1.72), _oc("No", 2.05)]),
    _bo("Both Teams To Score in Both Halves", [_oc("Yes", 8.0), _oc("No", 1.05)]),
    _bo("Both Teams To Score - 2nd Half", [_oc("Yes", 3.9)]),
    _bo("Both Teams To Score - 1st Half", [_oc("Yes", 4.1)]),
    _bo("Total Goals", [_oc("Over", 1.95, 2.5), _oc("Under", 1.85, 2.5)]),
    _bo("Total Goals by Crystal Palace", [_oc("Over", 8.5, 2.5)]),
    _bo("Total Goals - 1st Half", [_oc("Over", 2.9, 1.5)]),
]}


def test_kind():
    assert ps._kambi_kind("Both Teams To Score") == "btts"
    assert ps._kambi_kind("Both Teams To Score in Both Halves") is None
    assert ps._kambi_kind("Both Teams To Score - 2nd Half") is None
    assert ps._kambi_kind("Total Goals by Brighton") is None
    assert ps._kambi_kind("3-Way Handicap") is None
    assert ps._kambi_kind("Full Time") == "result"
    assert ps._kambi_kind("Total Goals - 1st Half") == "total_ht"


def test_team_odds_strict():
    out = kt.parse_offer(OFFER)
    assert out["btts_yes"] == 1.72, out
    assert out["over_25"] == 1.95, out
    assert out["home_win"] == 1.9 and out["away_win"] == 4.2, out
    assert out["btts_yes_ht"] == 4.1, out
    assert out["over_15_ht"] == 2.9, out


def test_specials_strict():
    out = ps._extract_kambi_team_specials(OFFER)
    assert out.get("btts_yes") == 1.72, out
    assert out.get("btts_yes_ht") == 4.1, out


def test_live_event_ignored():
    live = dict(OFFER, events=[{"id": 1, "state": "STARTED"}])
    assert kt.parse_offer(live) == {}
