"""Durable candidate card receipts in the existing NETRATTLER match-card table.

No schema migration, image blobs or extra tables. Reserve atomically by the
existing card_id primary key; an ambiguous Telegram response never resends.
"""
import hashlib
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import json
import requests
from netrattler_candidate_production import send,VERSION,require_release
from netrattler_clean_card_renderer import _stamp
from netrattler_premium_live_bridge import _split_match,_raw_asset,_book_price
from netrattler_crest_identity import same_club

def _card_id(state):
    key=json.dumps([state["family"],state["chat_id"],state["ticket_id"]],ensure_ascii=False)
    return "candidate-v1-"+hashlib.sha256(key.encode()).hexdigest()

class Ledger:
    def __init__(self,cards):
        self.url,self.headers=cards._sb()
        if not self.url or not self.headers:
            raise ValueError("Existing card-history database is unavailable")
    def reserve(self,state):
        card_id=_card_id(state)
        original=state["original"]
        rows=original.get("legs") or [original]
        first=rows[0]
        # Keep these records distinct from the legacy name-matched editor.
        day=_stamp(first["kickoff"]).astimezone(ZoneInfo("Europe/Zurich")).date().isoformat()
        payload={"card_id":card_id,"chat_id":state["chat_id"],"message_id":0,
                 "match":str(first["home"])+" vs "+str(first["away"]),
                 "match_key":card_id,"card_date":day,
                 "entries":[["candidate_v1",{"state":state}]]}
        try:
            response=requests.post(self.url,headers={**self.headers,
                 "Prefer":"resolution=ignore-duplicates,return=representation"},
                 params={"on_conflict":"card_id"},json=payload,timeout=15)
            items=response.json() if response.ok else []
            return (isinstance(items,list) and len(items)==1
                    and items[0].get("card_id")==card_id
                    and items[0].get("message_id")==0)
        except (requests.RequestException,ValueError,TypeError,AttributeError):
            return False
    def confirm(self,state):
        if type(state.get("message_id")) is not int or state["message_id"]<=0:
            return False
        card_id=_card_id(state)
        try:
            response=requests.patch(self.url,headers={**self.headers,"Prefer":"return=representation"},
                params={"card_id":"eq."+card_id,"message_id":"eq.0"},
                json={"message_id":state["message_id"],
                      "entries":[["candidate_v1",{"state":state}]]},timeout=15)
            items=response.json() if response.ok else []
            return (isinstance(items,list) and len(items)==1
                    and items[0].get("card_id")==card_id
                    and items[0].get("message_id")==state["message_id"])
        except (requests.RequestException,ValueError,TypeError,AttributeError):
            return False

class ExactTransport:
    """Do not retry a POST whose Telegram result is ambiguous."""
    def __init__(self,cards):
        self.cards=cards
    def _send_photo(self,token,chat,caption,payload,log):
        from netrattler_telegram_safe_zone import append_safe_margin,assert_safe_margin
        png=append_safe_margin(payload)
        assert_safe_margin(payload,png)
        try:
            reply=requests.post("https://api.telegram.org/bot"+token+"/sendPhoto",
                 data={"chat_id":chat,"caption":self.cards._telegram_card_caption(caption)},
                 files={"photo":("netrattler.png",png,"image/png")},timeout=25)
            data=reply.json() if reply.ok else {}
            result=data.get("result") if data.get("ok") is True else None
            if (not isinstance(result,dict) or type(result.get("message_id")) is not int
                or result["message_id"]<=0
                or str((result.get("chat") or {}).get("id"))!=str(chat)):
                return None
            return result["message_id"]
        except (requests.RequestException,ValueError,TypeError,AttributeError):
            log("CANDIDATE_SEND_UNCONFIRMED: no retry of ambiguous upload")
            return None

def dispatch(cards,token,chat,family,record,log=print,*,now=None):
    ledger=Ledger(cards)
    return send(ExactTransport(cards),token,chat,family,record,
                reserve=ledger.reserve,confirm=ledger.confirm,log=log,now=now)

def single_record(cards,tip,family,target_date,*,now=None):
    """Use the original source receipt; never invent a missing provider ID."""
    if family not in ("goal","corner","player_props","fouls_cards","late_goals","live_halftime"):
        raise ValueError("Not a single selection")
    require_release(family)
    row=dict(tip)
    home,away=_split_match(row.get("match") or (str(row.get("home") or "")+" vs "+str(row.get("away") or "")))
    row.update(home=home,away=away)
    price,book=_book_price(row)
    row.update(bookmaker=book,bookmaker_odds=price)
    if row.get("quote_observed") is not True or row.get("price_estimated") is not False:
        raise ValueError("Original source quote proof is missing")
    for key in ("fixture_id","home_id","away_id","quote_id","quote_observed_at"):
        if not str(row.get(key) or "").strip():
            raise ValueError("Original source evidence missing: "+key)
    start=_stamp(row.get("kickoff") or row.get("commence_time") or row.get("_kickoff"))
    clock=_stamp(now or datetime.now(timezone.utc))
    if start.astimezone(ZoneInfo("Europe/Zurich")).date().isoformat()!=str(target_date)[:10]:
        raise ValueError("Wrong Swiss fixture day")
    row["kickoff"]=start
    if family=="goal":
        from netrattler_strict_delivery import scorer_eligible
        ok,reason=scorer_eligible(tip)
        if not ok:
            raise ValueError("Scorer not qualified: "+reason)
        row["market"]="GOAL SCORER"
        row["selection"]="SPIELER TRIFFT"
        row["player_name"]=row.get("player_name") or row.get("player")
    else:
        row["selection"]=row.get("selection") or row.get("tip")
    if not row.get("selection"):
        raise ValueError("Actual selection is missing")
    # Stable selection identity is local deduplication, not a bookmaker receipt.
    stable=[family,str(row["fixture_id"]),str(row.get("player_id") or ""),str(row["selection"])]
    row["ticket_id"]=str(row.get("ticket_id") or hashlib.sha256(json.dumps(stable).encode()).hexdigest())
    row["home_crest"]=_raw_asset(cards._badge_bytes(home),"home",40)
    row["away_crest"]=_raw_asset(cards._badge_bytes(away),"away",40)
    if row.get("player_name"):
        team=row.get("player_team") or row.get("team")
        if sum(same_club(team,name) for name in (home,away))!=1:
            raise ValueError("Unverified player club")
        row["player_team"]=team
        row["player_photo"]=_raw_asset(cards._player_photo(row["player_name"],team),"player",80)
    # Only JSON-compatible metadata or real decoded assets may enter the snapshot.
    return row

def send_single(cards,token,chat,family,tip,target_date,log=print):
    try:
        record=single_record(cards,tip,family,target_date)
        return dispatch(cards,token,chat,family,record,log)
    except (ValueError,RuntimeError,OSError,TypeError,KeyError) as exc:
        log("CANDIDATE_CARD_DEFERRED "+family+": "+str(exc)[:150])
        return None


def candidate_state(cards,chat,message_id):
    """Find only the exact original ledger receipt. None means no candidate card.
    DB failure or ambiguity must not trigger a caption/legacy image fallback.
    """
    if not str(chat or "") or not str(message_id or "").isdigit() or int(message_id)<=0:
        return None
    ledger=Ledger(cards)
    response=requests.get(ledger.url,headers=ledger.headers,params={
        "card_id":"like.candidate-v1-*","chat_id":"eq."+str(chat),
        "message_id":"eq."+str(message_id),"select":"card_id,chat_id,message_id,entries,result",
        "limit":"2"},timeout=15)
    if not response.ok:
        raise RuntimeError("Candidate receipt lookup failed")
    rows=response.json()
    if not isinstance(rows,list) or len(rows)>1:
        raise ValueError("Ambiguous candidate receipt")
    if not rows:
        return None
    row=rows[0]
    entries=row.get("entries")
    if not isinstance(entries,list) or len(entries)!=1 or entries[0][0]!="candidate_v1":
        raise ValueError("Invalid original candidate receipt")
    state=entries[0][1]["state"]
    if (state.get("version")!=VERSION or row["card_id"]!=_card_id(state)
            or str(state.get("chat_id"))!=str(chat) or state.get("message_id")!=int(message_id)):
        raise ValueError("Contradictory candidate receipt")
    return row

def restore_record(cards,state):
    """Recover original metadata; never substitute different image pixels."""
    import copy
    from netrattler_candidate_production import _asset_signature
    record=copy.deepcopy(state["original"])
    for row in record.get("legs") or [record]:
        assets={"home_crest":lambda:cards._badge_bytes(row["home"]),
                "away_crest":lambda:cards._badge_bytes(row["away"])}
        if "player_photo" in row:
            assets["player_photo"]=lambda:cards._player_photo(row["player_name"],row["player_team"])
        for field,provider in assets.items():
            old=row.get(field)
            image=_raw_asset(provider(),field,80 if field=="player_photo" else 40)
            if not isinstance(old,dict) or old.get("asset_digest")!=_asset_signature(image):
                raise ValueError("Original asset cannot be recovered unchanged")
            row[field]=image
    return record

def settlement_evidence(state,settled):
    """Only exact original provider fixture/quote IDs and independently sourced final grades."""
    from netrattler_candidate_settlement import grades
    from collections.abc import Mapping
    original=state["original"]
    expected=original.get("legs") or [original]
    data=settled.get("tip_payload") or {}
    raw=settled.get("raw") or {}
    if raw.get("strict_match") is not True:
        raise ValueError("No strict settlement evidence")
    items=settled.get("legs_payload") if original.get("legs") else [
        {"leg":data,"status":settled.get("status"),"result_source":raw.get("result_source"),
         "result_fixture_id":raw.get("result_fixture_id")}]
    if not isinstance(items,list) or len(items)!=len(expected):
        raise ValueError("Incomplete original selection grades")
    result=[]
    status_map={"win":"won","loss":"lost","void":"void","push":"push"}
    for item in items:
        leg=item.get("leg") or {}
        fixture=str(leg.get("fixture_id") or "")
        quote=str(leg.get("quote_id") or "")
        # An independent result must match the exact original fixture, not
        # merely a date/team fuzzy match or another match in the ticket.
        if not fixture or str(item.get("result_fixture_id") or "")!=fixture:
            raise ValueError("Result does not carry exact original fixture identity")
        source=str(item.get("result_source") or "").strip()
        status=status_map.get(item.get("status"))
        if not quote or not source or not status:
            raise ValueError("Final grade/quote/source is incomplete")
        if status=="void" and not str(item.get("reason") or settled.get("reason") or "").startswith("void: Spieler ohne Einsatz"):
            raise ValueError("Unverified sporting void")
        result.append(dict(fixture_id=fixture,quote_id=quote,source=source,status=status))
    evidence={"verified":True,"legs":result}
    grades(original,evidence)
    return evidence

def try_edit_settlement(cards,token,chat,message_id,settled,log=print):
    """True/False for a known candidate; None only for a confirmed absent receipt."""
    from netrattler_candidate_production import edit
    try:
        row=candidate_state(cards,chat,message_id)
        if row is None:
            return None
        state=row["entries"][0][1]["state"]
        evidence=settlement_evidence(state,settled)
        if (row.get("result") or {}).get("candidate_grades")==evidence:
            return True
        record=restore_record(cards,state)
        if not edit(cards,token,state,record,evidence,log=log):
            return False
        ledger=Ledger(cards)
        response=requests.patch(ledger.url,headers={**ledger.headers,"Prefer":"return=representation"},
            params={"card_id":"eq."+row["card_id"],"message_id":"eq."+str(message_id)},
            json={"result":{"candidate_grades":evidence}},timeout=15)
        if not response.ok:
            log("CANDIDATE_EDIT_RECEIPT_FAILED: original image updated")
        return True
    except (ValueError,RuntimeError,KeyError,TypeError,AttributeError,OSError,requests.RequestException) as exc:
        log("CANDIDATE_EDIT_DEFERRED: "+str(exc)[:150])
        return False
