import os
import netrattler_table_router as r


def _env(**kw):
    for k in ("SUPABASE_URL", "V2_SUPABASE_URL", "V2_SUPABASE_SERVICE_KEY", "NETRATTLER_ROUTE_TABLES"):
        os.environ.pop(k, None)
    os.environ.update(kw)


def test_routes_only_listed_tables():
    _env(SUPABASE_URL="https://main.supabase.co", V2_SUPABASE_URL="https://arch.supabase.co",
         V2_SUPABASE_SERVICE_KEY="k2", NETRATTLER_ROUTE_TABLES="player_game_log,player_match_stats")
    u, h = r.rewrite("https://main.supabase.co/rest/v1/player_game_log?select=*", {"apikey": "k1", "Authorization": "Bearer k1"})
    assert u == "https://arch.supabase.co/rest/v1/player_game_log?select=*"
    assert h["apikey"] == "k2" and h["Authorization"] == "Bearer k2"
    u, h = r.rewrite("https://main.supabase.co/rest/v1/rpc/prune_player_game_log", {})
    assert u.startswith("https://arch.supabase.co/rest/v1/rpc/")
    u, h = r.rewrite("https://main.supabase.co/rest/v1/tips?select=*", {"apikey": "k1"})
    assert u.startswith("https://main.") and h == {"apikey": "k1"}
    u, _ = r.rewrite("https://main.supabase.co/rest/v1/player_game_log_old", {})
    assert u.startswith("https://main.")


def test_disabled_without_env():
    _env(SUPABASE_URL="https://main.supabase.co")
    u, h = r.rewrite("https://main.supabase.co/rest/v1/player_game_log", {"apikey": "k1"})
    assert u.startswith("https://main.") and h == {"apikey": "k1"}


def test_install_patches_session():
    import requests
    _env(SUPABASE_URL="https://main.supabase.co", V2_SUPABASE_URL="https://arch.supabase.co",
         V2_SUPABASE_SERVICE_KEY="k2", NETRATTLER_ROUTE_TABLES="player_game_log")
    seen = {}
    orig = requests.sessions.Session.request
    def fake(self, method, url, *a, **kw):
        seen["url"] = url; seen["h"] = kw.get("headers"); return None
    requests.sessions.Session.request = fake
    try:
        r._INSTALLED = False
        r.install()
        requests.get("https://main.supabase.co/rest/v1/player_game_log", headers={"apikey": "k1"})
        assert seen["url"].startswith("https://arch.") and seen["h"]["apikey"] == "k2"
        requests.get("https://main.supabase.co/rest/v1/tips", headers={"apikey": "k1"})
        assert seen["url"].startswith("https://main.") and seen["h"]["apikey"] == "k1"
    finally:
        requests.sessions.Session.request = orig
        r._INSTALLED = False
