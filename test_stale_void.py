from datetime import date
import netrattler_settlement_v16_final as s


def test_stale_no_result_voids():
    assert s.stale_no_result("pending", {}, "2026-10-17", date(2026, 10, 24))
    assert s.stale_no_result("pending", None, "2026-10-20", date(2026, 10, 24))


def test_recent_or_with_result_untouched():
    assert not s.stale_no_result("pending", {}, "2026-10-23", date(2026, 10, 24))
    assert not s.stale_no_result("pending", {"home_score": 1}, "2026-10-10", date(2026, 10, 24))
    assert not s.stale_no_result("win", {}, "2026-10-10", date(2026, 10, 24))


def test_reason_counts_as_genuine_void():
    assert s._genuine_void_reason("void: kein Ergebnis nach 3 Tagen verfuegbar (Liga ohne Datenquelle)")


def test_stale_void_is_written_to_source_but_legacy_void_is_not():
    assert s._writes_to_source({"status": "win"})
    assert s._writes_to_source({"status": "void", "reason": "void: kein Ergebnis nach 3 Tagen verfuegbar (Liga ohne Datenquelle)"})
    assert not s._writes_to_source({"status": "void", "reason": "Score fehlt"})
    assert not s._writes_to_source({"status": "pending", "reason": "x"})


def test_stale_unresolvable():
    import datetime as dt
    import netrattler_settlement_v16_final as s
    today = dt.date(2026, 10, 24)
    assert s.stale_unresolvable("pending", "2026-10-17", today)
    assert not s.stale_unresolvable("pending", "2026-10-20", today)
    assert not s.stale_unresolvable("win", "2026-10-01", today)


def test_corner_tip_prefers_source_with_corners():
    import netrattler_settlement_v16_final as s
    tip = {"_table": "tips", "tip_id": "t1", "market": "corners", "date": "2026-10-18", "league": "Premier League",
           "match": "AFC Bournemouth vs Sunderland AFC", "tip": "Over 7.5 Ecken", "odds": 1.8}
    base = {"home": "AFC Bournemouth", "away": "Sunderland", "home_team": "AFC Bournemouth", "away_team": "Sunderland",
            "match_date": "2026-10-18", "home_score": 2, "away_score": 0}
    espn = dict(base, source="espn", raw={})
    fm = dict(base, source="fotmob", raw={"home_corners": 5, "away_corners": 3})
    out = s.settle_tip(tip, [espn, fm], [])
    assert out["status"] == "win", out["reason"]


def test_load_results_dedupe_keeps_corners(monkeypatch):
    import netrattler_settlement_v16_final as s
    base = {"home": "AFC Bournemouth", "away": "Sunderland", "home_team": "AFC Bournemouth", "away_team": "Sunderland",
            "match_date": "2026-10-18", "home_score": 2, "away_score": 0}
    rows = {"espn": dict(base, raw={}), "fotmob": dict(base, raw={"home_corners": 5, "away_corners": 3})}
    monkeypatch.setattr(s, "RESULT_TABLES", {"espn": ["match_date"], "fotmob": ["match_date"]})
    monkeypatch.setattr(s, "sb_get_paged", lambda t, p, **k: [dict(rows[t])])
    out = s.load_results(["2026-10-18"])
    assert len(out) == 1 and s._has_corners(out[0])
