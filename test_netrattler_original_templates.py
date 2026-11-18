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
        for n,height in ((2,994),(4,1194),(6,1402)):
            pick=_fixture(n)
            raw=builder.render_builder_card(pick)
            im=Image.open(io.BytesIO(raw)).convert("RGB")
            assert im.size==(1122,height)
            original=_base(str(BUILDER_IMAGE))
            assert ImageChops.difference(im.crop((0,0,1122,170)),
                                          original.crop((0,0,1122,170))).getbbox() is None
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
         "probability":26,"fairOdds":3.85,"goals_per_game":.3,"_source":"test_only"}
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
