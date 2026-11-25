from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
import netrattler_api_corner_store as store


def test_capped_pages_and_cache(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://offline.invalid")
    monkeypatch.setenv("SUPABASE_KEY", "offline")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    rows = [dict(match_date="2026-01-01", home_team=f"H{i}", away_team="A",
                 home_corners=4, away_corners=5, home_goals=1, away_goals=2)
            for i in range(1201)]
    offsets = []

    def fetch(url, **kwargs):
        params = kwargs["params"]
        offset = int(params["offset"])
        offsets.append(offset)
        assert params["order"] == "match_date.desc,fixture_id.desc"
        assert params["match_date"] == "gte." + (date.today() - timedelta(days=540)).isoformat()
        # Simulate a server-side maximum below the requested page size.
        response = Mock()
        response.json.return_value = rows[offset:offset + 500]
        return response

    monkeypatch.setattr(store.requests, "get", fetch)
    bot = SimpleNamespace(_fd_co_uk_load_csv=lambda league: [{"Date": "csv"}],
                          API_FOOTBALL_LEAGUES={"L": 1}, log=Mock())
    store.install(bot)
    result = bot._ntr_corner_history("L")
    assert len(result) == 1202
    assert offsets == [0, 500, 1000, 1201]
    assert result[0]["HC"] == 4 and result[-1]["Date"] == "csv"
    assert bot._ntr_corner_history("L") == result
    assert len(offsets) == 4


def test_error_uses_csv_only(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://offline.invalid")
    monkeypatch.setenv("SUPABASE_KEY", "offline")
    fetch = Mock(side_effect=store.requests.RequestException("offline"))
    monkeypatch.setattr(store.requests, "get", fetch)
    bot = SimpleNamespace(_fd_co_uk_load_csv=lambda league: [{"Date": "csv"}],
                          API_FOOTBALL_LEAGUES={"L": 1}, log=Mock())
    store.install(bot)
    assert bot._ntr_corner_history("L") == [{"Date": "csv"}]
    bot.log.assert_called_once()
