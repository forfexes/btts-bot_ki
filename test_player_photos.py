import netrattler_player_photos as pp


def test_pick_photo_matches_surname_and_initial():
    players = [{"strPlayer": "Danny Welbeck", "strSport": "Soccer", "strCutout": "http://x/c.png"},
               {"strPlayer": "Other", "strSport": "Soccer", "strCutout": "http://x/o.png"}]
    assert pp.pick_photo(players, "D. Welbeck") == "http://x/c.png"
    assert pp.pick_photo(players, "Jack Welbeck") is None
    assert pp.pick_photo([{"strPlayer": "Danny Welbeck", "strSport": "Basketball", "strThumb": "u"}], "Danny Welbeck") is None


def test_apply_preview_only_with_marker():
    p = pp.apply_preview({"text": 'x<a href="http://x/a.png">​</a>y', "disable_web_page_preview": True})
    assert p["link_preview_options"]["url"] == "http://x/a.png" and "disable_web_page_preview" not in p
    q = pp.apply_preview({"text": "plain", "disable_web_page_preview": True})
    assert q["disable_web_page_preview"] is True


def test_anchor_empty_without_photo(monkeypatch):
    monkeypatch.setattr(pp, "photo_url", lambda n: None)
    assert pp.anchor("Nobody") == ""


def test_pick_fpl_espn_wiki():
    boot = {"elements": [{"first_name": "Mohamed", "second_name": "Salah", "web_name": "M.Salah", "photo": "118748.jpg"}]}
    assert pp.pick_fpl(boot, "Mohamed Salah").endswith("p118748.png")
    assert pp.pick_fpl(boot, "Ali Salah") is None
    esp = {"items": [{"type": "player", "displayName": "Erling Haaland", "uid": "s:600~a:123456"}]}
    assert pp.pick_espn(esp, "E. Haaland").endswith("/123456.png")
    wiki = {"query": {"pages": {"1": {"title": "Bukayo Saka", "thumbnail": {"source": "http://w/s.jpg"}}}}}
    assert pp.pick_wiki(wiki, "Bukayo Saka") == "http://w/s.jpg"


def test_chain_falls_through(monkeypatch):
    pp._MEM.clear()
    monkeypatch.setattr(pp, "_save", lambda: None)
    monkeypatch.setattr(pp, "_load", lambda: None)
    def boom(n): raise RuntimeError("x")
    monkeypatch.setattr(pp, "SOURCES", [boom, lambda n: None, lambda n: "http://ok/p.png"])
    assert pp.photo_url("Test Player") == "http://ok/p.png"
