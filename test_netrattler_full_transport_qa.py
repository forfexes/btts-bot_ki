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
        row=formula(ticket(family,3))
        render=lambda settlement=None:render_owner_reference_qa(family,row,now=FIVE_NOW,settlement=settlement)
    elif family in ("goal","corner"):
        row=one()
        row.update(market="GOALS OVER 2.5" if family=="goal" else "CORNERS OVER 9.5",
                   selection="OVER 2.5" if family=="goal" else "OVER 9.5")
        render=lambda settlement=None:render_owner_reference_qa(family,row,now=FIVE_NOW,settlement=settlement)
    elif family=="cross_mix":
        row=formula(_cross_ticket(3))
        render=lambda settlement=None:render_cross_mix_qa(row,now=TEN_NOW,settlement=settlement)
    else:
        row=_for_category(family)
        plate,meta=render_clean_master(family)
        render=lambda settlement=None:render_qa_card(plate,meta,row,now=TEN_NOW,settlement=settlement)
    raw=render()
    settlement={"verified":True,"legs":[{"fixture_id":leg["fixture_id"],"quote_id":leg["quote_id"],
          "source":"OFFLINE_QA_RESULT","status":"lost" if i%2 else "won"}
          for i,leg in enumerate(row.get("legs") or [row])]}
    done=render(settlement)
    assert done!=raw
    with pytest.raises(ValueError):
        render({**settlement,"verified":False})
    wrong={**settlement,"legs":[{**settlement["legs"][0],"quote_id":"WRONG"},
                                 *settlement["legs"][1:]]}
    with pytest.raises(ValueError):
        render(wrong)
    return raw,done,"owner_derived_candidate"


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
    assert all(r['edit_original_mock']=='PASS' for r in report.values())
    (out/"transport_report.json").write_text(json.dumps(report,indent=2)+"\n")
    print("ALL_16_ACTUAL_PNG_TRANSPORT_QA_PASS",len(report))


def test_candidate_settlement_never_infers_or_reuses_wrong_grade():
    from netrattler_candidate_settlement import grades,footer
    row=formula(ticket("combo",3))
    evidence={"verified":True,"legs":[dict(fixture_id=leg["fixture_id"],quote_id=leg["quote_id"],
        source="OFFLINE",status="void") for leg in row["legs"]]}
    assert grades(row,evidence)==["void","void","void"]
    assert "3 VOID" in footer(row,evidence)
    assert "GEWINN" not in footer(row,evidence)
    for bad in (
        {**evidence,"legs":evidence["legs"][:2]},
        {**evidence,"legs":[evidence["legs"][0]]*3},
        {**evidence,"legs":[{**evidence["legs"][0],"source":""},*evidence["legs"][1:]]},
        {**evidence,"legs":[{**evidence["legs"][0],"status":"pending"},*evidence["legs"][1:]]},
    ):
        with pytest.raises(ValueError):
            grades(row,bad)


def test_builder_normalization_retains_actual_provider_evidence():
    from netrattler_builder_engine import normalize_prop
    row={"player":"QA Player","team":"QA Home","match":"QA Home vs QA Away",
         "market":"Shots 2+","category":"shots","odds":1.8,"source":"Pinnacle",
         "probability":0.8,"ko":"2099-11-25T18:00:00Z",
         "fixture_id":"fixture-123","home_id":"home-2","away_id":"away-9",
         "player_id":"player-10","quote_id":"receipt-19",
         "quote_observed_at":"2099-11-25T17:59:00Z","odds_observed":True}
    leg=normalize_prop(row)
    assert leg is not None
    for key in ("fixture_id","home_id","away_id","player_id","quote_id",
                "quote_observed_at","odds_observed"):
        assert getattr(leg,key)==row[key]
    without={k:v for k,v in row.items() if k not in ("quote_id","quote_observed_at","odds_observed")}
    leg=normalize_prop(without)
    assert leg is not None and leg.quote_id=="" and leg.quote_observed_at=="" and leg.odds_observed is None
    for bad in ({"odds_observed":False},{"quote_observed":False},{"price_calculated":True},
                {"synthetic":True},{"price_type":"calculated_from_leg_odds"}):
        assert normalize_prop(dict(row,**bad)) is None


def test_actual_builder_source_receipts_reach_existing_candidate_renderer():
    from datetime import timedelta
    from types import SimpleNamespace as Pick
    from netrattler_premium_live_bridge import builder_candidate_record, render_builder_candidate_qa
    from netrattler_builder_engine import normalize_prop
    from test_netrattler_five_owner_dynamic_qa import NOW,crest
    def raw(i):
        return dict(player="QA Player "+str(i),team="QA HOME",match="QA HOME vs QA AWAY",
            market="Shots 2+",category="shots",line=2,odds=1.8,source="Pinnacle",
            probability=0.8,ko=(NOW+timedelta(minutes=30)).isoformat(),
            fixture_id="fixture-123",home_id="home-2",away_id="away-9",
            player_id="p"+str(i),quote_id="receipt-"+str(i),
            quote_observed_at=(NOW-timedelta(seconds=30)).isoformat(),odds_observed=True)
    def png(color):
        b=BytesIO();crest(color).save(b,"PNG");return b.getvalue()
    def badge(team):
        return png((255,30,50,255) if team=="QA HOME" else (10,160,240,255))
    def player(*args):
        return png((20,210,150,255))
    rows=[raw(1),raw(2)]
    pick=Pick(builder_id="QA-original",match_date=NOW.date().isoformat(),
              legs=[normalize_prop(row) for row in rows],total_odds=99)
    record=builder_candidate_record(pick,crest_provider=badge,player_provider=player,now=NOW)
    assert record["formula_only"] is True and "combined_odds" not in record
    assert [x["quote_id"] for x in record["legs"]]==["receipt-1","receipt-2"]
    assert record["category"]=="builder"
    image=render_builder_candidate_qa(pick,crest_provider=badge,player_provider=player,now=NOW)
    with Image.open(BytesIO(image)) as im:
        assert im.format=="PNG"
        im.verify()
    def unexpected(*args):
        pytest.fail("Invalid original source fetched an image")
    for edit in ({"quote_id":""},{"odds_observed":None},{"player_id":""},
                 {"quote_observed_at":(NOW-timedelta(minutes=16)).isoformat()},
                 {"fixture_id":"fixture-123","away_id":"wrong"},
                 {"quote_id":"receipt-1"}):
        bad=Pick(**{**vars(pick),"legs":[normalize_prop(rows[0]),normalize_prop(dict(rows[1],**edit))]})
        with pytest.raises(ValueError):
            builder_candidate_record(bad,crest_provider=unexpected,player_provider=unexpected,now=NOW)
    with pytest.raises(ValueError,match="Identical"):
        builder_candidate_record(pick,crest_provider=lambda _:badge("QA HOME"),player_provider=player,now=NOW)


def test_last_minute_accepts_real_fixture_ids_and_rejects_naive_quote_time():
    from netrattler_last_minute_goal import fixture_info,_utc_time
    row={"fixture":{"id":1934567,"status":{"short":"2H","elapsed":72}},
         "teams":{"home":{"id":100,"name":"QA Home"},"away":{"id":200,"name":"QA Away"}},
         "goals":{"home":1,"away":1},"league":{"name":"QA League"}}
    assert fixture_info(row)["fixture_id"]==1934567
    for bad in (0,True,-1,"1.5",""):
        assert fixture_info(dict(row,fixture={**row["fixture"],"id":bad})) is None
    assert _utc_time("2026-11-26T17:00:00") is None
    assert _utc_time("2026-11-26T17:00:00Z") is not None
