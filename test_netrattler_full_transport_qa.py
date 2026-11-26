"""Test actual owner/clean-candidate artwork through the real photo HTTP adapter.

No live Telegram, no database, no predictions. Candidate art remains SANDBOX.
"""
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import os

import pytest
from PIL import Image
import netrattler_stats_match_cards as cards
import netrattler_premium_telegram_adapter as adapter
from netrattler_premium_verified_cards import CATEGORIES
from netrattler_strict_delivery import verified_regular_payload
from netrattler_telegram_safe_zone import append_safe_margin, assert_safe_margin
from netrattler_five_owner_dynamic_qa import render_owner_reference_qa
from netrattler_clean_card_renderer import render_qa_card, render_cross_mix_qa
from netrattler_clean_master_builder import render_clean_master
from test_netrattler_stadium_portrait import _sample, _crest_bytes
from test_netrattler_five_owner_dynamic_qa import one, ticket, NOW as FIVE_NOW
from test_netrattler_clean_card_renderer import _for_category, _cross_ticket, NOW as TEN_NOW
from last_minute_owner_20261122.live_data_bridge import make_live, make_settled
from last_minute_owner_20261122.test_live_data_bridge import FIXTURE, METRICS, authentic_qa_image

REGULAR = {"btts":"btts","over":"over25","btts_halftime":"btts_ht",
           "over_halftime":"over15_ht","match_result":"1x2","var":"var"}

def formula(record):
    row=dict(record)
    for name in ("combined_quote_id","combined_odds","bookmaker"):
        row.pop(name,None)
    row.update(formula_only=True,combined_odds_observed=False)
    return row

def render_family(family):
    if family in REGULAR:
        market=REGULAR[family]
        row={**_sample(),"selection":"1" if market=="1x2" else "YES",
             "tip_eligible":True,"settlement_rule_verified":True}
        args=([(market,row)],"2026-11-25")
        raw=adapter.render(*args,crest_provider=_crest_bytes)
        done=adapter.render(*args,crest_provider=_crest_bytes,
                            result={"marks":{"0":"won"},"ft":"2-1"})
        assert verified_regular_payload(raw) and verified_regular_payload(done)
        return raw,done,"pinned_owner_stadium"
    if family=="last_minute_goal":
        raw=make_live(FIXTURE,METRICS,crest_provider=authentic_qa_image,preview_only=True)
        done=make_settled(FIXTURE,final_score="2:1",won=True,
                          crest_provider=authentic_qa_image,preview_only=True)
        return raw,done,"clean_last_minute_candidate"
    if family in ("builder","combo"):
        raw=render_owner_reference_qa(family,formula(ticket(family,3)),now=FIVE_NOW)
    elif family in ("goal","corner"):
        row=one()
        row.update(market="GOALS OVER 2.5" if family=="goal" else "CORNERS OVER 9.5",
                   selection="OVER 2.5" if family=="goal" else "OVER 9.5")
        raw=render_owner_reference_qa(family,row,now=FIVE_NOW)
    elif family=="cross_mix":
        raw=render_cross_mix_qa(formula(_cross_ticket(3)),now=TEN_NOW)
    else:
        plate,meta=render_clean_master(family)
        raw=render_qa_card(plate,meta,_for_category(family),now=TEN_NOW)
    return raw,None,"owner_derived_candidate"

def test_all_sixteen_actual_pngs_reach_mocked_transport(monkeypatch):
    monkeypatch.setenv("NETRATTLER_ORIGINAL_ONLY","1")
    monkeypatch.setenv("NETRATTLER_BLOCK_OVERPAINTED_MASTERS","1")
    monkeypatch.setenv("STATS_MATCH_CARDS_RETRIES","1")
    out=Path(os.getenv("NETRATTLER_FULL_TRANSPORT_QA","output/full-transport-qa"))
    out.mkdir(parents=True,exist_ok=True)
    report={}
    def network_forbidden(*args,**kwargs):
        pytest.fail("Unexpected real HTTP request")
    monkeypatch.setattr(cards.requests.sessions.Session,"request",network_forbidden)
    for i,family in enumerate(CATEGORIES,1):
        raw,done,source=render_family(family)
        with Image.open(BytesIO(raw)) as im:
            assert im.format=="PNG"
            im.verify()
        mid=1000+i
        calls=[]
        def endpoint(url,**kw):
            calls.append((url,kw))
            assert url.startswith("https://api.telegram.org/botOFFLINE_ONLY/")
            assert kw["data"]["chat_id"]=="OFFLINE_ONLY"
            return SimpleNamespace(ok=True,status_code=200,
                json=lambda:{"ok":True,"result":{"message_id":mid,
                     "chat":{"id":"OFFLINE_ONLY"}}})
        with patch.object(cards.requests,"post",side_effect=endpoint):
            assert cards._send_photo("OFFLINE_ONLY","OFFLINE_ONLY",
                       "SANDBOX - KEIN TIPP",raw,print)==mid
            sent=calls[0][1]["files"]["photo"][1]
            assert calls[0][0].endswith("/sendPhoto")
            assert sent==append_safe_margin(raw)
            assert_safe_margin(raw,sent)
            (out/(family+"_SANDBOX.png")).write_bytes(sent)
            if done is not None:
                assert cards._edit_photo("OFFLINE_ONLY","OFFLINE_ONLY",mid,done,print,
                           caption="SANDBOX - KEIN TIPP")
                assert calls[1][0].endswith("/editMessageMedia")
                assert calls[1][1]["data"]["message_id"]==mid
                assert_safe_margin(done,calls[1][1]["files"]["card"][1])
                (out/(family+"_SETTLED_SANDBOX.png")).write_bytes(calls[1][1]["files"]["card"][1])
            assert len(calls)==(2 if done is not None else 1)
        report[family]={"source":source,"send_photo_mock":"PASS",
                        "edit_original_mock":"PASS" if done is not None else "NOT_IMPLEMENTED",
                        "production_eligible":family in REGULAR,
                        "real_telegram_sent":False}
    assert len(report)==16
    (out/"transport_report.json").write_text(json.dumps(report,indent=2)+"\n")
    print("ALL_16_ACTUAL_PNG_TRANSPORT_QA_PASS",len(report))
