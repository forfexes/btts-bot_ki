"""Pixel-level test: real user templates + safe mocked Telegram transport."""
import io
from types import SimpleNamespace as S
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageChops

import netrattler_stats_match_cards as cards
import netrattler_builder_cards as builder
from netrattler_original_template_renderer import _base, BUILDER_IMAGE, GOAL_IMAGE
from netrattler_visual_review import review_png


def _test_photo():
    im=Image.new("RGB",(240,260),"#0F5872")
    d=ImageDraw.Draw(im)
    d.ellipse((70,25,185,155),fill="#BD885E")
    d.polygon(((8,260),(50,155),(194,155),(230,260)),fill="#9D2238")
    buf=io.BytesIO()
    im.save(buf,"PNG")
    return buf.getvalue()


def _fixture(n):
    legs=[S(player=f"Beispiel Spieler {i+1}",team="Demo United" if i%2==0 else "Test FC",
            match="Demo United vs Test FC",category="shots",line=1,market="Shots",
            odds=1.75,source="test_only",estimated=False,
            kickoff="2026-11-21T17:30:00+00:00",league="Demo League",
            series=[2]*15,quality=.82,probability=.68)
          for i in range(n)]
    return S(legs=legs,match_date="2026-11-21",status="pending",confidence="HOCH",
             combined_quote_verified=True,combined_bookmaker_quote=8.5,
             joint_probability=.3,style="BUILDER",variant="",tiers=[])


def test_builder_two_four_six_leg_masters_and_dry_run_send():
    photo=_test_photo()
    with patch.object(cards,"_player_photo",return_value=photo), \
         patch.object(cards,"_badge_bytes",return_value=photo):
        for n,height in ((2,1002),(4,1202),(6,1402)):
            pick=_fixture(n)
            raw=builder.render_builder_card(pick)
            im=Image.open(io.BytesIO(raw)).convert("RGB")
            assert im.size==(1122,height)
            # Compact SVG gradients depend on canvas height. Compare against
            # the SAME compact master, never the full-height 6-leg SVG.
            from netrattler_premium_compact import compact_master
            import cairosvg
            master=Image.open(io.BytesIO(cairosvg.svg2png(
                bytestring=compact_master("builder",n)))).convert("RGB")
            assert master.size==im.size
            assert ImageChops.difference(im.crop((0,0,1122,170)),
                                          master.crop((0,0,1122,170))).getbbox() is None
            quality=review_png(raw,"builder",legs=n)
            assert quality.passed,quality.describe()
            with patch("netrattler_visual_gate.validate_builder",return_value=(pick,[])), \
                 patch.object(cards,"_send_photo",return_value=3141) as send:
                assert builder.send_builder_card("FAKE_TOKEN","FAKE_CHAT",pick)==3141
                assert send.call_count == 1
                assert send.call_args.args[3].startswith(b"\x89PNG\r\n\x1a\n")


def test_goal_hunter_master_and_dry_run_send():
    photo=_test_photo()
    tip={"match":"Demo United vs Test FC","player":"Beispiel Stürmer",
         "team":"Demo United","league":"Demo League","odds":9.5,
         "probability":26,"fairOdds":3.85,"goals_per_game":.3,
         "_kickoff":"2026-11-21T17:30:00+00:00","_source":"test_only"}
    with patch.object(cards,"_player_photo",return_value=photo), \
         patch.object(cards,"_badge_bytes",return_value=photo):
        raw=cards.render_scorer_card(tip,"2026-11-21")
        im=Image.open(io.BytesIO(raw)).convert("RGB")
        assert im.size==(1122,1402)
        original=_base(str(GOAL_IMAGE))
        assert ImageChops.difference(im.crop((0,0,1122,170)),
            original.crop((0,0,1122,170))).getbbox() is None
        quality=review_png(raw,"scorer")
        assert quality.passed, quality.describe()
        won=cards.render_scorer_card(tip,"2026-11-21",{"marks":{"0":"win"}})
        assert review_png(won,"scorer").passed
        with patch("netrattler_visual_gate.enrich_scorer",return_value=tip), \
             patch("netrattler_visual_gate.validate_scorer",return_value=[]), \
             patch.object(cards,"save_card",return_value=True), \
             patch.object(cards,"_send_photo",return_value=3142) as send:
            assert cards.send_scorer_card("FAKE_TOKEN","FAKE_CHAT",tip,
                                          "2026-11-21",return_id=True)==3142
            assert send.call_args.args[3].startswith(b"\x89PNG\r\n\x1a\n")


def test_missing_original_template_fails_closed():
    from netrattler_original_template_renderer import _base
    import pytest
    with pytest.raises(FileNotFoundError):
        _base("/no-such-directory/netrattler_original_template.webp")


def test_six_leg_original_base_is_immutable_between_different_players():
    """Never copy a prior tip's portrait or details into the next Telegram PNG."""
    import hashlib
    original=_base(str(BUILDER_IMAGE))
    digest=hashlib.sha256(original.tobytes()).hexdigest()
    fake=_test_photo()
    with patch.object(cards,"_player_photo",return_value=fake), \
         patch.object(cards,"_badge_bytes",return_value=fake):
        first=_fixture(6)
        a=builder.render_builder_card(first)
        second=_fixture(6)
        second.legs[0].player="Zweiter Spieler"
        b=builder.render_builder_card(second)
    assert a!=b
    assert hashlib.sha256(_base(str(BUILDER_IMAGE)).tobytes()).hexdigest()==digest
    assert review_png(a,"builder",legs=6).passed
    assert review_png(b,"builder",legs=6).passed


def test_regular_match_card_sender_rejects_incomplete_goal_hunter():
    """Both Telegram paths must reject a missing photo, not only send_scorer_card."""
    entry=("scorer",{"match":"Demo United vs Test FC",
                     "player":"Unverified Scorer","team":"Demo United",
                     "odds":3.3,"probability":35,"_source":"test_only"})
    with patch.object(cards,"select_cards",return_value=[[entry]]), \
         patch.object(cards,"_existing_card_signatures",return_value=set()), \
         patch.object(cards,"_crest_cache_load",return_value=None), \
         patch.object(cards,"_crest_cache_save",return_value=None), \
         patch.object(cards,"_badge_bytes",return_value=b"fake"), \
         patch.object(cards,"_player_photo",return_value=b""), \
         patch.object(cards.time,"sleep",return_value=None), \
         patch.object(cards,"_send_photo",return_value=999) as send, \
         patch("netrattler_visual_gate.enrich_scorer",return_value=entry[1]):
        assert cards.send_cards({"scorer":[entry[1]]},"2026-11-21",
                                "FAKE_TOKEN","FAKE_CHAT") == 0
    send.assert_not_called()


def test_goal_hunter_kickoff_is_swiss_local_and_visible_in_original_artwork():
    from netrattler_original_template_renderer import _kickoff
    assert _kickoff("2026-11-21T17:30:00+00:00") == "21.11.2026 / 18:30 Uhr"
    assert _kickoff("2026-07-21T17:30:00+00:00") == "21.07.2026 / 19:30 Uhr"
    photo=_test_photo()
    tip={"match":"Demo United vs Test FC","player":"Beispiel Stürmer",
         "team":"Demo United","odds":9.50,"probability":26,"fairOdds":3.85,
         "goals_per_game":.30,"_kickoff":"2026-11-21T17:30:00+00:00"}
    with patch.object(cards,"_player_photo",return_value=photo), \
         patch.object(cards,"_badge_bytes",return_value=photo):
        with_time=cards.render_scorer_card(tip,"2026-11-21")
        without_time=cards.render_scorer_card({k:v for k,v in tip.items()
                                                if k!="_kickoff"},"2026-11-21")
    from netrattler_visual_review import review_png
    assert review_png(with_time,"scorer").passed
    report=review_png(without_time,"scorer")
    assert not report.passed and "scorer_kickoff_displayed" in report.problems
    with Image.open(io.BytesIO(with_time)) as first, Image.open(io.BytesIO(without_time)) as second:
        assert ImageChops.difference(first.crop((343,830,781,859)),
                                     second.crop((343,830,781,859))).getbbox()


def test_scorer_kickoff_enrichment_requires_verified_offset_and_accurate_fixture():
    from netrattler_visual_gate import enrich_scorer, validate_scorer
    record={"match":"Demo United vs Test FC","player":"Beispiel Stürmer",
            "team":"Demo United","goals_per_game":.3,
            "kickoff":"2026-11-21T17:30:00Z"}
    with patch("netrattler_visual_gate.kickoff_for_match") as lookup:
        out=enrich_scorer(record,"2026-11-21")
        lookup.assert_not_called()
    assert out["_kickoff"]=="2026-11-21T17:30:00+00:00"
    no_time={**record,"kickoff":"18:30"}
    with patch("netrattler_visual_gate.kickoff_for_match",return_value=""):
        unknown=enrich_scorer(no_time,"2026-11-21")
    assert "_kickoff" not in unknown
    with patch.object(cards,"_player_photo",return_value=_test_photo()), \
         patch.object(cards,"_badge_bytes",return_value=_test_photo()):
        assert "missing_confirmed_kickoff" in validate_scorer({
            **unknown,"odds":4.5,"probability":30},"2026-11-21")
    with patch("netrattler_visual_gate.kickoff_for_match",
               return_value="2026-11-21T17:30:00+00:00"):
        found=enrich_scorer(no_time,"2026-11-21")
    assert found["_kickoff"]=="2026-11-21T17:30:00+00:00"


def test_builder_shows_all_three_verified_form_windows():
    """L5, L10 and L15 must all appear; never infer missing form."""
    from netrattler_original_template_renderer import render_builder, _label
    photo=_test_photo()
    pick=_fixture(6)
    with patch.object(cards,"_player_photo",return_value=photo), \
         patch.object(cards,"_badge_bytes",return_value=photo), \
         patch("netrattler_original_template_renderer._label", wraps=_label) as label:
        raw=render_builder(pick)
    labels=[str(call.args[1]) for call in label.call_args_list if len(call.args)>1]
    for period in (5,10,15):
        assert any(text.startswith(f"L{period}:") for text in labels), f"L{period} absent"
    assert raw.startswith(bytes.fromhex("89504e470d0a1a0a"))
