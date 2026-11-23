"""Hermetic image QA; no network, Telegram, Supabase, or new live tips."""
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import os

import pytest
from PIL import Image, ImageDraw

from netrattler_clean_card_renderer import render_qa_card, render_cross_mix_qa, _logo
from netrattler_clean_master_builder import W, H, SOURCE_MAP, render_clean_master

NOW = datetime(2026, 11, 23, 13, 0, tzinfo=timezone.utc)


def _asset():
    # Synthetic shape used ONLY in watermarked sandbox tests.
    icon = Image.new("RGBA", (120, 140), (0, 0, 0, 0))
    ImageDraw.Draw(icon).polygon(((60, 7), (104, 107), (60, 125), (12, 107)),
                                 fill=(224, 28, 32, 255))
    return icon


def _metadata():
    return {"category": "over", "classification": "owner-derived_clean_QA_NOT_user_original",
            "production_approved": False, "logo_backplates": False,
            "floating_crest_slots": [
                {"center_x": 250, "center_y": 456, "max_width": 194, "max_height": 195},
                {"center_x": 872, "center_y": 456, "max_width": 194, "max_height": 195}],
            "blank_slots": {
                f"stat_{j}": {"x": 555, "y": 638 + (j-1)*142 + 24,
                                "width": 388, "height": 66}
                for j in (1, 2, 3)}}


def _record():
    return {"home": "QA Home", "away": "QA Away", "home_id": "aa", "away_id": "bb",
            "home_crest": _asset(), "away_crest": _asset(),
            "fixture_id": "SANDBOX-987",
            "kickoff": NOW + timedelta(hours=1), "bookmaker": "QA only",
            "quote_id": "QA-receipt-987", "quote_observed_at": NOW-timedelta(minutes=1),
            "bookmaker_odds": 1.87, "price_estimated": False,
            "selection": "OVER 2.5", "stats": {}}


SELECTIONS = {
    "over": "OVER 2.5", "btts_halftime": "BTTS YES HT",
    "over_halftime": "OVER 1.5 HT", "match_result": "HOME WIN",
    "player_props": "PLAYER SHOTS OVER 2.5",
    "fouls_cards": "CARDS OVER 3.5", "var": "VAR YES",
    "late_goals": "OVER 0.5 RESTSPIELZEIT",
    "live_halftime": "OVER 0.5 HT", "cross_mix": "CROSS BUILDER",
}


def _for_category(category):
    record = _record()
    record["selection"] = SELECTIONS[category]
    if category == "player_props":
        record.update(player_id="p10", player_name="QA Player",
                      confirmed_starter=True, player_team_id="aa",
                      player_photo_source="OFFLINE-FAKE-IMAGE-QA",
                      player_photo=_asset())
    if category == "cross_mix":
        record.update(combined_odds_observed=True, combined_quote_id="book-ticket-123",
                      legs=[{"id": "leg1"}, {"id": "leg2"}])
    if category in ("late_goals", "live_halftime"):
        minute = 75 if category == "late_goals" else 35
        record.update(kickoff=NOW-timedelta(minutes=minute),
                      quote_observed_at=NOW-timedelta(seconds=20),
                      match_minute=minute, live_event_id="evt-100",
                      live_source="verified-provider", current_score="1:1")
    return record


def _cross_ticket(count=2):
    base = _record()
    base.update(quote_observed=True, market="BTTS", selection="YES")
    legs = []
    for i in range(count):
        leg = dict(base)
        leg.update(
            fixture_id=f"QA-CROSS-{i}", home=f"QA HOME {i}",
            away=f"QA AWAY {i}", home_id=f"H{i}", away_id=f"A{i}",
            quote_id=f"QA-LEG-{i}",
        )
        legs.append(leg)
    return {
        "bookmaker": base["bookmaker"],
        "combined_quote_id": "QA-REAL-COMBINED-TICKET",
        "combined_odds": 3.94,
        "combined_odds_observed": True,
        "price_estimated": False,
        "quote_observed_at": base["quote_observed_at"],
        "kickoff": base["kickoff"],
        "legs": legs,
    }


def _plate():
    out = BytesIO()
    Image.new("RGB", (W, H), (5, 18, 34)).save(out, "PNG")
    return out.getvalue()


def test_all_ten_categories_render_sandbox_without_legacy_stickers():
    for family in sorted(SOURCE_MAP):
        meta = _metadata()
        meta["category"] = family
        if family == "cross_mix":
            with pytest.raises(ValueError, match="Cross/Mix"):
                render_qa_card(_plate(), meta, _for_category(family), now=NOW)
            png = render_cross_mix_qa(_cross_ticket(), now=NOW)
        else:
            png = render_qa_card(_plate(), meta, _for_category(family), now=NOW)
        with Image.open(BytesIO(png)) as im:
            assert im.format == "PNG" and im.size == (W, H)
            if family == "cross_mix":
                continue
            assert im.getpixel((155, 356)) == (5, 18, 34)
            assert im.getpixel((767, 356)) == (5, 18, 34)
            assert im.getpixel((250, 456))[0] > 100
            assert im.getpixel((872, 456))[0] > 100
            assert any(im.getpixel((x, y)) != (5, 18, 34)
                       for x in range(730, 768) for y in range(678, 716))


@pytest.mark.parametrize("family", sorted(SOURCE_MAP))
def test_actual_owner_derived_plate_in_sandbox_only(family):
    # Unlike the synthetic fixture above this uses the real repo's
    # original artwork, but the preview ALWAYS has a sandbox watermark.
    plate, meta = render_clean_master(family)
    if family == "cross_mix":
        png = render_cross_mix_qa(_cross_ticket(), now=NOW)
    else:
        png = render_qa_card(plate, meta, _for_category(family), now=NOW)
    with Image.open(BytesIO(png)) as im:
        assert im.format == "PNG"
        assert im.size == (W, H)
        im.verify()
    preview_dir = os.getenv("NETRATTLER_CARD_QA_PREVIEW_DIR")
    if preview_dir:
        outdir = Path(preview_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / (family + "_SANDBOX_NOT_APPROVED.png")).write_bytes(png)


def test_market_mismatch_never_reaches_any_visual_card():
    for family in SELECTIONS:
        if family in ("over", "over_halftime"):
            continue
        meta = _metadata()
        meta["category"] = family
        record = _for_category(family)
        record["selection"] = "OVER 2.5"
        with pytest.raises(ValueError, match="Cross/Mix" if family=="cross_mix" else "Selection"):
            render_qa_card(_plate(), meta, record, now=NOW)


def test_missing_or_fake_assets_fail_closed():
    record = _record()
    for key, bad in (("home_crest", None),
                     ("away_crest", Image.new("RGB", (80, 80), "red")),
                     ("price_estimated", True),
                     ("quote_id", ""),
                     ("home_id", "bb"),
                     ("quote_observed_at", NOW-timedelta(minutes=16)),
                     ("kickoff", NOW-timedelta(seconds=1)),
                     ("bookmaker_odds", float("nan"))):
        edited = dict(record, **{key: bad})
        with pytest.raises(ValueError):
            render_qa_card(_plate(), _metadata(), edited, now=NOW)


def test_no_runtime_approval_or_unsupported_master():
    for edit in ({"production_approved": True},
                 {"classification": "original_approved"},
                 {"category": "builder"},
                 {"logo_backplates": True}):
        with pytest.raises(ValueError):
            render_qa_card(_plate(), dict(_metadata(), **edit), _record(), now=NOW)


def test_lookahead_stats_and_anonymous_statistics_rejected():
    record = _record()
    record["stats"] = {"stat_1": {"value": "3", "source": "provider",
                                   "event_id": "match-id", "observed_at": NOW+timedelta(minutes=1)}}
    with pytest.raises(ValueError, match="Look-ahead"):
        render_qa_card(_plate(), _metadata(), record, now=NOW)
    record["stats"]["stat_1"].pop("source")
    with pytest.raises(ValueError, match="provider"):
        render_qa_card(_plate(), _metadata(), record, now=NOW)


def test_too_small_logo_is_not_scaled_into_an_artificial_badge():
    with pytest.raises(ValueError):
        _logo(Image.new("RGBA", (10, 10), (240, 10, 20, 255)), 194, 195)


@pytest.mark.parametrize("count", range(2, 11))
def test_cross_mix_all_rows_kept_and_actual_ticket_required(count):
    from netrattler_five_owner_dynamic_qa import ROW_H, BODY_END, BODY_TOP
    png=render_cross_mix_qa(_cross_ticket(count),now=NOW)
    extra=max(0,count*ROW_H+36-(BODY_END-BODY_TOP))
    with Image.open(BytesIO(png)) as im:
        assert im.size==(W,H+extra)
        im.verify()


def test_cross_mix_never_hides_rows_or_uses_synthetic_ticket_price():
    with pytest.raises(ValueError):
        render_cross_mix_qa(_cross_ticket(11),now=NOW)
    for field,bad in (("combined_quote_id",""),
                      ("combined_odds_observed",False),
                      ("combined_odds",float("nan"))):
        ticket=_cross_ticket()
        ticket[field]=bad
        with pytest.raises(ValueError):
            render_cross_mix_qa(ticket,now=NOW)
    ticket=_cross_ticket()
    ticket["legs"][1]["quote_observed"]=False
    with pytest.raises(ValueError):
        render_cross_mix_qa(ticket,now=NOW)



def test_player_prop_fails_without_verified_alpha_photo_and_team_identity():
    good = _for_category("player_props")
    for field, bad in (
        ("player_photo", None),
        ("player_photo", Image.new("RGB", (80, 100), "pink")),
        ("player_photo_source", ""),
        ("player_team_id", "wrong-team"),
        ("player_id", ""),
        ("confirmed_starter", False),
    ):
        record={**good,field:bad}
        with pytest.raises(ValueError):
            render_qa_card(_plate(), {**_metadata(),"category":"player_props"},record,now=NOW)


def test_statistics_must_belong_to_the_same_fixture():
    good=_record()
    good["stats"]={
        "stat_1":{
            "value": "7/10", "source": "observed-provider",
            "event_id": "ANOTHER_MATCH",
            "observed_at": NOW-timedelta(minutes=4),
        }}
    with pytest.raises(ValueError,match="different fixture"):
        render_qa_card(_plate(),_metadata(),good,now=NOW)
