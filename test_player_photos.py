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
