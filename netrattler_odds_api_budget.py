"""Tages-Budget fuer the-odds-api.com (Gratisplan: 500 Credits/Monat).

Wird ueber sitecustomize in jeden Python-Lauf geladen. Zaehlt nur kostenpflichtige Aufrufe (/odds, /scores,
/historical), liest den echten Verbrauch aus dem Header x-requests-last und blockiert weitere Aufrufe, sobald
das Tageslimit (NETRATTLER_ODDS_API_DAILY_CAP, Standard 15) erreicht oder das Restkontingent unter
NETRATTLER_ODDS_API_RESERVE (Standard 25) gefallen ist. Blockierte Aufrufe liefern eine lokale 429-Antwort
(keine Credits verbraucht). Tagesstand liegt in netrattler_card_diag (probe=odds_api_budget).
Abschalten: NETRATTLER_ODDS_API_BUDGET=off."""
from __future__ import annotations

import atexit
import os
from datetime import datetime, timezone

_INSTALLED = False
_STATE = {"date": None, "used": 0, "loaded": False, "remaining": None, "dirty": False}
HOST = "api.the-odds-api.com"
PAID_MARKERS = ("/odds", "/scores", "/historical")


def _cap() -> int:
    try:
        return int(os.getenv("NETRATTLER_ODDS_API_DAILY_CAP", "15"))
    except ValueError:
        return 15


def _reserve() -> int:
    try:
        return int(os.getenv("NETRATTLER_ODDS_API_RESERVE", "25"))
    except ValueError:
        return 25


def is_paid(url: str) -> bool:
    if not isinstance(url, str) or HOST not in url:
        return False
    path = url.split(HOST, 1)[1].split("?", 1)[0]
    return any(m in path for m in PAID_MARKERS)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _sb():
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    return url, key


def _load(session_request):
    if _STATE["loaded"]:
        return
    _STATE["loaded"] = True
    _STATE["date"] = _today()
    url, key = _sb()
    if not (url and key):
        return
    try:
        r = session_request("GET", f"{url}/rest/v1/netrattler_card_diag", params={
            "select": "info,ts", "info->>probe": "eq.odds_api_budget", "info->>date": f"eq.{_STATE['date']}",
            "order": "ts.desc", "limit": "1"},
            headers={"apikey": key, "Authorization": f"Bearer {key}"}, timeout=10)
        rows = r.json() if r.ok else []
        if rows:
            info = rows[0].get("info") or {}
            _STATE["used"] = int(info.get("used") or 0)
            _STATE["remaining"] = info.get("remaining")
    except Exception:
        pass


def _save():
    if not _STATE["dirty"]:
        return
    url, key = _sb()
    if not (url and key):
        return
    try:
        import requests
        requests.post(f"{url}/rest/v1/netrattler_card_diag", timeout=15,
                      headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      json={"info": {"probe": "odds_api_budget", "date": _STATE["date"], "used": _STATE["used"],
                                     "cap": _cap(), "remaining": _STATE["remaining"]}})
    except Exception:
        pass


def blocked() -> str:
    """Grund, warum ein kostenpflichtiger Aufruf jetzt nicht erlaubt ist (leer = erlaubt)."""
    if _STATE["used"] >= _cap():
        return f"Tageslimit {_cap()} erreicht"
    rem = _STATE["remaining"]
    if rem is not None and int(rem) <= _reserve():
        return f"Restkontingent {rem} <= Reserve {_reserve()}"
    return ""


def record(headers) -> None:
    try:
        last = int((headers or {}).get("x-requests-last", 1) or 1)
    except (TypeError, ValueError):
        last = 1
    _STATE["used"] += max(0, last)
    try:
        rem = (headers or {}).get("x-requests-remaining")
        if rem is not None:
            _STATE["remaining"] = int(float(rem))
    except (TypeError, ValueError):
        pass
    _STATE["dirty"] = True


def install() -> bool:
    global _INSTALLED
    if _INSTALLED or os.getenv("NETRATTLER_ODDS_API_BUDGET", "on").lower() in {"off", "0", "false"}:
        return _INSTALLED
    import requests
    import requests.sessions as rs
    orig = rs.Session.request

    def request(self, method, url, *args, **kwargs):
        if not is_paid(url):
            return orig(self, method, url, *args, **kwargs)
        _load(lambda m, u, **kw: orig(self, m, u, **kw))
        why = blocked()
        if why:
            resp = requests.models.Response()
            resp.status_code = 429
            resp._content = ('{"message":"netrattler budget: %s"}' % why).encode()
            resp.url = str(url)
            resp.headers["x-netrattler-budget"] = "blocked"
            return resp
        resp = orig(self, method, url, *args, **kwargs)
        record(resp.headers)
        return resp

    rs.Session.request = request
    atexit.register(_save)
    _INSTALLED = True
    return True
