import netrattler_html_odds_scraper as scraper


def test_html_scraper_requires_allowlist(monkeypatch):
    monkeypatch.delenv("NETRATTLER_HTML_ODDS_URLS", raising=False)
    assert scraper.collect_html_odds("2026-10-25") == []


def test_html_scraper_extracts_only_explicit_market_and_selection():
    import json
    payload = {"@type": "SportsEvent", "startDate": "2026-10-25T18:00:00Z",
               "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"},
               "offers": [
                   {"market": "1x2", "selection": "home", "seller": {"name": "Book"}, "price": "2.05"},
                   {"market": "shots", "selection": "home", "seller": "Book", "price": "50"}]}
    html = '<script type="application/ld+json">' + json.dumps(payload) + '</script>'
    rows = scraper.parse_html(html, "https://example.com/event", "2026-10-25")
    assert len(rows) == 1
    assert rows[0]["odds"] == 2.05
    assert rows[0]["source"] == "html_odds_shadow"
    assert scraper.parse_html(html, "https://example.com/event", "2026-10-26") == []


def test_html_scraper_allowlisted_page_without_redirect(monkeypatch):
    import json
    payload = {"@type": "SportsEvent", "startDate": "2026-10-25T18:00:00Z",
               "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"},
               "offers": [{"market": "btts", "selection": "yes", "seller": "Book", "price": 1.8}]}
    html = '<script type="application/ld+json">' + json.dumps(payload) + '</script>'
    monkeypatch.setenv("NETRATTLER_HTML_ODDS_URLS", "https://example.com/event")
    monkeypatch.setenv("NETRATTLER_HTML_ODDS_HOSTS", "example.com")
    class Response:
        status_code = 200
        content = html.encode()
        text = html
        def raise_for_status(self): pass
    def get(url, **kwargs):
        assert url == "https://example.com/event"
        assert kwargs["allow_redirects"] is False
        return Response()
    monkeypatch.setattr(scraper.requests, "get", get)
    rows = scraper.collect_html_odds("2026-10-25")
    assert len(rows) == 1 and rows[0]["selection"] == "yes"
