"""Offline original-family dynamic cards: exact leg counts, photos/logos and quote guards.

All fixture/team/crest content is synthetic, marked SANDBOX and NEVER sent.
"""
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import os

import pytest
from PIL import Image, ImageDraw, ImageChops

from netrattler_clean_master_builder import W, H
from netrattler_five_owner_dynamic_qa import render_owner_reference_qa, ROW_H, BODY_END, BODY_TOP

NOW = datetime(2026, 11, 23, 16, 0, tzinfo=timezone.utc)


def crest(color=(255, 42, 58, 255)):
    im = Image.new("RGBA", (150, 150), (0, 0, 0, 0))
    ImageDraw.Draw(im).polygon([(75, 10), (138, 47), (108, 127),
                                 (44, 140), (14, 49)], fill=color)
    return im


def one(fixture_id="QA-001", suffix=1):
    return {
        "fixture_id": fixture_id, "home_id": f"H{suffix}",
        "away_id": f"A{suffix}", "home": f"TEST HOME {suffix}",
        "away": f"TEST AWAY {suffix}", "home_crest": crest(),
        "away_crest": crest((31, 202, 244, 255)),
        "market": "BTTS", "selection": "YES",
        "bookmaker": "OFFLINE-QA-BOOK", "bookmaker_odds": 1.81,
        "quote_id": f"QA-Q-{suffix}", "quote_observed": True,
        "price_estimated": False,
        "quote_observed_at": NOW - timedelta(seconds=25),
        "kickoff": NOW + timedelta(minutes=46),
        "stats": {"stat_1": {"value": "8/10", "source": "fixture-source",
                           "event_id": fixture_id,
                           "observed_at": NOW - timedelta(minutes=2)}}
    }


def ticket(family, n, same_game=False):
    legs = []
    for i in range(1, n+1):
        leg = one(f"QA-{i}" if not same_game else "QA-001",
                  i if not same_game else 1)
        leg["market"] = "OVER 2.5" if i % 2 else "BTTS"
        leg["selection"] = f"OVER {i}.5" if i % 2 else "YES"
        leg["bookmaker_odds"] = 1.77 + i/100
        legs.append(leg)
    return {
        "bookmaker": "OFFLINE-QA-BOOK", "combined_quote_id": f"OFFLINE-TKT-{n}",
        "combined_odds": 5.93, "combined_odds_observed": True,
        "price_estimated": False, "quote_observed_at": NOW - timedelta(seconds=30),
        "kickoff": NOW + timedelta(minutes=46), "legs": legs,
    }


@pytest.mark.parametrize("family,market,selection", [
    ("btts", "BTTS", "YES"), ("goal", "GOALS OVER 2.5", "OVER 2.5"),
    ("corner", "CORNERS OVER 9.5", "OVER 9.5"),
])
def test_three_single_owner_families(family,market,selection):
    row = one()
    row.update(market=market,selection=selection)
    png = render_owner_reference_qa(family,row,now=NOW)
    with Image.open(BytesIO(png)) as im:
        assert im.format == "PNG" and im.size == (W,H)
        im.verify()
    output_dir = os.environ.get("NETRATTLER_FIVE_DYNAMIC_QA")
    if output_dir:
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{family}_SANDBOX_DYNAMIC.png").write_bytes(png)


@pytest.mark.parametrize("family,count", [
    ("builder",2),("builder",4),("builder",7),
    ("combo",2),("combo",4),("combo",7),("combo",10),
])
def test_every_multi_leg_remains_visible_and_poster_extends(family,count):
    png = render_owner_reference_qa(family,ticket(family,count),now=NOW)
    extra = max(0,count*ROW_H+36-(BODY_END-BODY_TOP))
    with Image.open(BytesIO(png)) as im:
        assert im.format == "PNG" and im.size == (W,H+extra)
        assert im.convert("RGB").getbbox() is not None
        im.verify()
    output_dir = os.environ.get("NETRATTLER_FIVE_DYNAMIC_QA")
    if output_dir:
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{family}_{count}_SANDBOX_DYNAMIC.png").write_bytes(png)


def test_sg_builder_uses_one_match_not_fake_multi_match():
    result1=render_owner_reference_qa("builder",ticket("builder",3,True),now=NOW)
    result2=render_owner_reference_qa("builder",ticket("builder",3,False),now=NOW)
    with Image.open(BytesIO(result1)) as a, Image.open(BytesIO(result2)) as b:
        # Distinct fixture count changes the *visible* caption.
        assert ImageChops.difference(a.convert("RGB").crop((300,396,830,449)),
                                     b.convert("RGB").crop((300,396,830,449))).getbbox()


def test_no_unverified_single_market_or_odds():
    row=one()
    for edited in (
        {"market":"CORNER OVER"}, {"bookmaker_odds":float("nan")},
        {"price_estimated":True}, {"quote_id":""},
        {"quote_observed":False},
        {"quote_observed_at":NOW-timedelta(minutes=16)},
        {"kickoff":NOW-timedelta(minutes=1)},
        {"home_id":row["away_id"]},
        {"away_crest":None},
    ):
        with pytest.raises((ValueError,TypeError)):
            render_owner_reference_qa("btts",{**row,**edited},now=NOW)


def test_no_fake_combined_ticket_and_no_hidden_legs():
    original=ticket("builder",4)
    for change in (
        {"combined_odds_observed":False},
        {"combined_quote_id":""},
        {"price_estimated":True},
        {"combined_odds":float("inf")},
        {"legs":original["legs"]*3},
        {"quote_observed_at":NOW-timedelta(minutes=20)},
    ):
        with pytest.raises((ValueError,TypeError)):
            render_owner_reference_qa("builder",{**original,**change},now=NOW)
    bad_leg={**original["legs"][0],"quote_observed":False}
    with pytest.raises(ValueError):
        render_owner_reference_qa("builder",{**original,"legs":[bad_leg,*original["legs"][1:]]},now=NOW)


def test_combo_rejects_11_legs_instead_of_truncating_to_10():
    with pytest.raises(ValueError):
        render_owner_reference_qa("combo",ticket("combo",11),now=NOW)


def test_unapproved_categories_do_not_silently_reuse_owner_art():
    for category in ("var","cross_mix","last_minute_goal","fake"):
        with pytest.raises(ValueError,match="five"):
            render_owner_reference_qa(category,one(),now=NOW)
