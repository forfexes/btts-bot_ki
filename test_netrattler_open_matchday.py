import netrattler_open_matchday as source

def test_free_feed_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_OPEN_MATCHDAY", raising=False)
    assert source.collect() == []

def test_free_feed_csv_parser():
    rows = source.parse_csv("date,home_team,away_team,home_goals\n2026-10-25,A,B,2\n")
    assert rows == [{"date":"2026-10-25","home_team":"A","away_team":"B","home_goals":"2"}]

def test_free_feed_collect_opt_in(monkeypatch):
    monkeypatch.setenv("ENABLE_OPEN_MATCHDAY","true")
    class Response:
        content=b"date,home_team\n2026-10-25,A\n"
        text=content.decode()
        def raise_for_status(self): pass
    monkeypatch.setattr(source.requests,"get",lambda *a,**k: Response())
    assert source.collect()[0]["home_team"] == "A"
