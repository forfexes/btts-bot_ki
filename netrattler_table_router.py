"""Route Supabase REST calls for selected tables from the main project to the archive project (V2).

Activated only when NETRATTLER_ROUTE_TABLES is set and V2_SUPABASE_URL / V2_SUPABASE_SERVICE_KEY exist.
Patches requests.Session.request once; every other URL is untouched. Keys are never logged.
"""
from __future__ import annotations

import os

_INSTALLED = False


def _cfg():
    main = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    dst = (os.getenv("V2_SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("V2_SUPABASE_SERVICE_KEY") or ""
    tables = [t.strip() for t in (os.getenv("NETRATTLER_ROUTE_TABLES") or "").split(",") if t.strip()]
    if not (main and dst.startswith("https://") and key and tables) or dst == main:
        return None
    prefixes = []
    for t in tables:
        prefixes.append(f"{main}/rest/v1/{t}")
        if t == "player_game_log":
            prefixes.append(f"{main}/rest/v1/rpc/prune_player_game_log")
    return main, dst, key, tuple(prefixes)


def rewrite(url: str, headers: dict | None, cfg=None):
    cfg = cfg or _cfg()
    if not cfg or not isinstance(url, str):
        return url, headers
    main, dst, key, prefixes = cfg
    for p in prefixes:
        if url == p or url.startswith(p + "?") or url.startswith(p + "/"):
            h = dict(headers or {})
            for k in list(h):
                if k.lower() in ("apikey", "authorization"):
                    h.pop(k)
            h["apikey"] = key
            h["Authorization"] = f"Bearer {key}"
            return dst + url[len(main):], h
    return url, headers


def install() -> bool:
    global _INSTALLED
    if _INSTALLED or _cfg() is None:
        return _INSTALLED
    import requests.sessions as rs
    orig = rs.Session.request

    def request(self, method, url, *args, **kwargs):
        cfg = _cfg()
        if cfg:
            new_url, new_headers = rewrite(url, kwargs.get("headers"), cfg)
            if new_url is not url:
                url = new_url
                kwargs["headers"] = new_headers
                # session-level auth headers must not leak the main key to the archive project
                if self.headers.get("apikey") or self.headers.get("Authorization"):
                    merged = dict(self.headers); merged.update(new_headers)
                    kwargs["headers"] = merged
        return orig(self, method, url, *args, **kwargs)

    rs.Session.request = request
    _INSTALLED = True
    return True
