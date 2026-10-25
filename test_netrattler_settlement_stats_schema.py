"""Regression for legacy Supabase stats schema (missing priced column)."""
import json
from unittest.mock import patch
import netrattler_settlement_v16_final as settlement

class FakeResponse:
    def __init__(self, code, text=""):
        self.status_code = code
        self.text = text

def test_legacy_stats_retry_drops_only_priced():
    calls = []
    def post(url, **kwargs):
        calls.append(json.loads(kwargs["data"]))
        if len(calls) == 1:
            return FakeResponse(400, '{"code":"PGRST204","message":"Could not find the \'priced\' column of \'netrattler_group_stats\' in the schema cache"}')
        return FakeResponse(201)
    with patch.object(settlement.requests, "post", side_effect=post):
        with patch.object(settlement, "SUPABASE_URL", "https://example.supabase.co"):
            with patch.object(settlement, "SUPABASE_KEY", "test"):
                result = settlement.sb_upsert("netrattler_group_stats", [{"stat_id":"x","priced":3,"wins":2}], "stat_id")
    assert result == 1
    assert len(calls) == 2
    assert calls[0][0] == {"stat_id":"x","priced":3,"wins":2}
    assert calls[1][0] == {"stat_id":"x","wins":2}

def test_other_tables_never_strip_priced():
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs)
        return FakeResponse(400, '{"code":"PGRST204","message":"Could not find the \'priced\' column in schema cache"}')
    with patch.object(settlement.requests, "post", side_effect=post):
        with patch.object(settlement, "SUPABASE_URL", "https://example.supabase.co"):
            with patch.object(settlement, "SUPABASE_KEY", "test"):
                result = settlement.sb_upsert("netrattler_settlements", [{"stat_id":"x","priced":3}], "stat_id")
    assert result == 0
    assert len(calls) == 1

def test_successful_stats_upsert_does_not_retry():
    with patch.object(settlement.requests, "post", return_value=FakeResponse(201)) as post:
        with patch.object(settlement, "SUPABASE_URL", "https://example.supabase.co"):
            with patch.object(settlement, "SUPABASE_KEY", "test"):
                result = settlement.sb_upsert("netrattler_performance_stats", [{"stat_id":"x","priced":3}], "stat_id")
    assert result == 1
    assert post.call_count == 1
