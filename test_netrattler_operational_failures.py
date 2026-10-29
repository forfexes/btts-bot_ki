import json
import urllib.error
import urllib.request
from unittest.mock import Mock, patch
import pytest
import netrattler_post_run_check as monitor
from netrattler_apif_response import checked_response
import netrattler_pending_result_backfill as backfill


def test_provider_error_is_not_empty_success():
    response = Mock(ok=True)
    response.json.return_value = {"errors": {"access": "suspended"}, "response": []}
    with pytest.raises(RuntimeError, match="provider error"):
        checked_response(response)
    response.json.return_value = {"errors": [], "response": []}
    assert checked_response(response) == []


def test_signed_log_redirect_removes_only_cross_host_authorization():
    handler = monitor.LogRedirectHandler()
    req = urllib.request.Request("https://api.github.com/jobs/1/logs", headers={"Authorization": "Bearer fake"})
    redirect = handler.redirect_request(req, None, 302, "Found", {}, "https://logs.example/signed")
    assert redirect.get_header("Authorization") is None
    redirect = handler.redirect_request(req, None, 302, "Found", {}, "https://api.github.com/next")
    assert redirect.get_header("Authorization") == "Bearer fake"


@pytest.mark.parametrize("logs", ["Coverage: btts=no_candidates", None])
def test_monitor_fails_when_coverage_missing_or_unreadable(tmp_path, monkeypatch, logs):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"workflow_run": {"name": "NETRATTLER AI Tipp Bot", "status": "completed", "conclusion": "success"}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    with patch.object(monitor, "notify"), patch.object(monitor, "fetch_job_logs") as fetch:
        if logs is None:
            fetch.side_effect = urllib.error.HTTPError("https://example", 403, "Forbidden", {}, None)
        else:
            fetch.return_value = logs
        assert monitor.main() == 1


def test_backfill_uses_explicit_date_and_cross_match_builder_legs():
    tips = [{"tip_id": "builder_without_date", "match_date": "2026-10-24", "created_at": "2026-10-23", "legs": [
        {"match": "A vs B", "market": "shots"}, {"match": "C vs D", "date": "2026-10-25", "market": "over15_ht"}]}]
    plan = backfill.plan(tips)
    assert ("A", "B", False) in plan["2026-10-24"]
    assert ("C", "D", True) in plan["2026-10-25"]
