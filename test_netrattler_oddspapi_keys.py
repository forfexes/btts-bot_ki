#!/usr/bin/env python3
from __future__ import annotations

import os

import netrattler_oddspapi as op


class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


class _Requests:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None, headers=None):
        self.calls.append({"url": url, "params": dict(params or {})})
        if not self.responses:
            raise AssertionError("unexpected extra request")
        return self.responses.pop(0)


def _reset():
    op._KEY_STATE["index"] = 0
    op._KEY_STATE["rotations"] = 0
    op._RATE_LIMITED_FLAG["hit"] = False


def test_key_parsing_and_dedup():
    old_multi = os.environ.get("ODDSPAPI_KEYS")
    old_single = os.environ.get("ODDSPAPI_KEY")
    try:
        os.environ["ODDSPAPI_KEYS"] = " key-a,key-b\nkey-c;key-a "
        os.environ["ODDSPAPI_KEY"] = "key-d"
        assert op._keys() == ["key-a", "key-b", "key-c", "key-d"]
    finally:
        if old_multi is None:
            os.environ.pop("ODDSPAPI_KEYS", None)
        else:
            os.environ["ODDSPAPI_KEYS"] = old_multi
        if old_single is None:
            os.environ.pop("ODDSPAPI_KEY", None)
        else:
            os.environ["ODDSPAPI_KEY"] = old_single


def test_auth_failure_rotates_to_next_key():
    old_multi = os.environ.get("ODDSPAPI_KEYS")
    old_single = os.environ.pop("ODDSPAPI_KEY", None)
    old_requests = op.requests
    try:
        os.environ["ODDSPAPI_KEYS"] = "key-a,key-b"
        _reset()
        fake = _Requests([
            _Resp(401, {}),
            _Resp(200, [{"fixtureId": "ok"}]),
        ])
        op.requests = fake
        data = op._get("fixtures", {"sportId": 10})
        assert data == [{"fixtureId": "ok"}]
        assert len(fake.calls) == 2
        assert fake.calls[0]["params"]["apiKey"] == "key-a"
        assert fake.calls[1]["params"]["apiKey"] == "key-b"
        assert op._KEY_STATE["rotations"] == 1
    finally:
        op.requests = old_requests
        if old_multi is None:
            os.environ.pop("ODDSPAPI_KEYS", None)
        else:
            os.environ["ODDSPAPI_KEYS"] = old_multi
        if old_single is not None:
            os.environ["ODDSPAPI_KEY"] = old_single


def test_rate_limit_does_not_hop_accounts():
    old_multi = os.environ.get("ODDSPAPI_KEYS")
    old_single = os.environ.pop("ODDSPAPI_KEY", None)
    old_requests = op.requests
    try:
        os.environ["ODDSPAPI_KEYS"] = "key-a,key-b,key-c"
        _reset()
        fake = _Requests([_Resp(429, {})])
        op.requests = fake
        data = op._get("fixtures", {"sportId": 10})
        assert data == {"_rate_limited": True}
        assert len(fake.calls) == 1
        assert op._RATE_LIMITED_FLAG["hit"] is True
        assert op._KEY_STATE["rotations"] == 0
    finally:
        op.requests = old_requests
        if old_multi is None:
            os.environ.pop("ODDSPAPI_KEYS", None)
        else:
            os.environ["ODDSPAPI_KEYS"] = old_multi
        if old_single is not None:
            os.environ["ODDSPAPI_KEY"] = old_single


def main():
    test_key_parsing_and_dedup()
    test_auth_failure_rotates_to_next_key()
    test_rate_limit_does_not_hop_accounts()
    print("OK: OddsPapi multi-key parsing/failover regression passed")


if __name__ == "__main__":
    main()
