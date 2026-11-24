"""No-network approval-gated Telegram album and photo-settlement plan tests."""
import json
from io import BytesIO
from PIL import Image
import pytest
from netrattler_premium_mobile_telegram_plan import (
    plan_new_ticket,bind_message_ids,plan_same_photo_settlement,
)
from test_netrattler_premium_mobile_pages import ticket


def test_single_photo_plan_no_caption_overlay():
    plan=plan_new_ticket(ticket('single',1),'CHAT',preview_only=True)
    assert plan.method=='sendPhoto' and len(plan.files)==1
    assert plan.data['chat_id']=='CHAT'
    assert not plan.data.get('caption')
    with Image.open(BytesIO(plan.files['photo'][1])) as im:
        assert im.width==1080 and im.height>1400


def test_ten_leg_album_four_pages_and_one_ticket():
    plan=plan_new_ticket(ticket('builder',10),'CHAT',preview_only=True)
    assert plan.method=='sendMediaGroup'
    assert len(plan.files)==4 and len(plan.page_ranges)==4
    media=json.loads(plan.data['media'])
    assert len(media)==4
    assert sum('caption' in x for x in media)==1
    assert all(x['type']=='photo' for x in media)
    assert all(x['media'].startswith('attach://card_') for x in media)
    for name,(_,png,mime) in plan.files.items():
        assert mime=='image/png' and len(png)>10000


def test_result_is_exactly_four_in_place_edits_not_four_new_tips():
    original=ticket('builder',10)
    upload=plan_new_ticket(original,'CHAT',preview_only=True)
    state=bind_message_ids(upload,[111,112,113,114],'QATICKET-1')
    settled=dict(original,status='GEWONNEN')
    edits=plan_same_photo_settlement(settled,state,preview_only=True)
    assert [x.method for x in edits]==['editMessageMedia']*4
    assert [x.data['message_id'] for x in edits]==['111','112','113','114']
    assert [x.page_ranges for x in edits]==[((1,3),),((4,6),),((7,8),),((9,10),)]


def test_cannot_bind_missing_or_duplicate_ids():
    plan=plan_new_ticket(ticket('builder',6),'CHAT',preview_only=True)
    with pytest.raises(ValueError):bind_message_ids(plan,[123],'ID')
    with pytest.raises(ValueError):bind_message_ids(plan,[123,123],'ID')
    with pytest.raises(ValueError):bind_message_ids(plan,[123,False],'ID')


def test_cannot_edit_if_partition_changed():
    plan=plan_new_ticket(ticket('builder',8),'CHAT',preview_only=True)
    state=bind_message_ids(plan,[41,42,43],'T1')
    with pytest.raises(ValueError):
        plan_same_photo_settlement(ticket('builder',9),state,preview_only=True)


def test_cannot_transmit_unapproved_artwork():
    with pytest.raises(ValueError,match='club crests'):
        plan_new_ticket(ticket('builder',10),'CHAT',preview_only=False)


def test_transport_is_offline_only():
    from pathlib import Path
    src=Path(__file__).with_name('netrattler_premium_mobile_telegram_plan.py').read_text()
    assert 'requests.post' not in src and 'urlopen(' not in src