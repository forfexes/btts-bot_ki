"""Offline regression suite for mobile-safe NETRATTLER premium ticket pages."""
import hashlib
import pytest
from PIL import Image
from netrattler_premium_mobile_pages import (
    MASTER_PATH, MASTER_SHA256, CATEGORIES, MULTI, MAX_LEGS_PER_IMAGE,
    group_lengths, render_mobile_pages,
)


def leg(i):
    return {"match":f"QA TEST TEAM {i} VS QA TEST TEAM B", "market":"BTTS - BOTH TEAMS TO SCORE",
            "bookmaker_odds":1.85,"bookmaker":"QA-OFFLINE", "form":"L10 7/10 · L15 10/15"}


def ticket(category, total):
    d={"category":category,"legs":[leg(i) for i in range(1,total+1)],
       "stake_units":1,"status":"OFFEN","ticket_id":"QA-ONE-TICKET"}
    if category in MULTI:
        d.update(combined_odds=4.25,combined_odds_observed=True,
                 combined_ticket_id="QA-TICKET-NO-BOOK")
    return d


@pytest.mark.parametrize("count",range(1,11))
def test_all_lengths_retain_exact_master_and_global_ranges(count):
    data=ticket("single" if count==1 else "builder",count)
    pages=render_mobile_pages(MASTER_PATH,data,preview_only=True)
    ranges=[list(range(p.first_leg,p.last_leg+1)) for p in pages]
    assert [leg for rng in ranges for leg in rng]==list(range(1,count+1))
    assert [p.page for p in pages]==list(range(1,len(pages)+1))
    assert len(pages)==len(group_lengths(count))
    assert all(p.pages==len(pages) for p in pages)
    with Image.open(MASTER_PATH) as im:
        expected=im.convert("RGB").tobytes()
    for p in pages:
        assert p.image.width==1080 and 1080<p.image.height<2300
        assert p.last_leg-p.first_leg+1<=MAX_LEGS_PER_IMAGE
        assert p.image.crop((0,0,1080,608)).tobytes()==expected


@pytest.mark.parametrize("category",sorted(CATEGORIES))
def test_every_category_mobile_qa(category):
    count=10 if category in MULTI else 1
    pages=render_mobile_pages(MASTER_PATH,ticket(category,count),preview_only=True)
    assert 1 <= len(pages) <= 4
    assert pages[0].first_leg==1
    assert pages[-1].last_leg==count


def test_master_digest_is_pinned():
    assert hashlib.sha256(MASTER_PATH.read_bytes()).hexdigest()==MASTER_SHA256


def test_qa_cannot_serve_as_production_card():
    with pytest.raises(ValueError,match="club crests"):
        render_mobile_pages(MASTER_PATH,ticket("builder",10),preview_only=False)


def test_no_calculated_combined_prices_as_genuine_bookmaker():
    data=ticket("builder",10)
    data["combined_odds_observed"]=False
    with pytest.raises(ValueError,match="bookmaker ticket|book price|ticket ID"):
        render_mobile_pages(MASTER_PATH,data,preview_only=True)


def test_no_fake_player_or_team_assets():
    data=ticket("single",1)
    data["legs"][0].update(home_logo="missing.png",away_logo="missing2.png")
    with pytest.raises((ValueError,FileNotFoundError)):
        render_mobile_pages(MASTER_PATH,data,preview_only=False)


def test_overflow_rejected_instead_of_miniaturizing():
    data=ticket("single",1)
    data["legs"][0]["market"]="A VERY LONG MARKET "*140
    with pytest.raises(ValueError,match="overflow"):
        render_mobile_pages(MASTER_PATH,data,preview_only=True)


def test_ten_selections_get_four_mobile_images():
    assert group_lengths(10)==[3,3,2,2]
    assert group_lengths(9)==[3,3,3]
    assert group_lengths(8)==[3,3,2]
    assert group_lengths(6)==[3,3]


def test_no_telegram_or_supabase_code():
    from pathlib import Path
    source=Path(__file__).with_name('netrattler_premium_mobile_pages.py').read_text()
    assert 'requests.post(' not in source and 'urllib.request.urlopen' not in source
    assert 'supabase.create_client(' not in source

def test_alternative_background_allowed_only_in_offline_qa(tmp_path):
    img=Image.new("RGB",(1080,608),(2,3,4))
    another=tmp_path/"replacement.png"
    img.save(another)
    render_mobile_pages(another,ticket("single",1),preview_only=True)
    real=ticket("single",1)
    real["legs"][0].update(home_logo="must-be-real.png",away_logo="must-be-real-too.png")
    # Real delivery cannot silently substitute a different master, even
    # when complete input image data would later become available.
    with pytest.raises(ValueError):
        render_mobile_pages(another,real,preview_only=False)
