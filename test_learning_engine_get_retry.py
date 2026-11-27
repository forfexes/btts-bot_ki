import requests
import netrattler_learning_engine as le


class R:
    def __init__(self, rows, code=200):
        self._r, self.status_code, self.ok, self.text = rows, code, code < 400, ""

    def json(self):
        return self._r


def test_get_retries_timeout_and_shrinks(monkeypatch):
    calls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append(params["limit"])
        if len(calls) == 1:
            raise requests.exceptions.ReadTimeout("x")
        return R([{"a": i} for i in range(min(params["limit"], 3))])

    monkeypatch.setattr(le.requests, "get", fake_get)
    monkeypatch.setattr(le.time, "sleep", lambda s: None)
    rows = le.SupabaseRest("http://x", "k").get("t", limit_total=1000, page_size=1000)
    assert calls[0] == 1000 and calls[1] == 500
    assert len(rows) == 3


def test_get_gives_up_without_raising(monkeypatch):
    def boom(*a, **k):
        raise requests.exceptions.ReadTimeout("x")

    monkeypatch.setattr(le.requests, "get", boom)
    monkeypatch.setattr(le.time, "sleep", lambda s: None)
    assert le.SupabaseRest("http://x", "k").get("t") == []
