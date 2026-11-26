"""Nine-family production rendering and transport contract.

Only the explicit owner-authorized, pinned source-derived layouts are allowed.
Callers must supply actual original source receipts and an atomic durable
reservation/confirmation interface. No synthetic data, legacy artwork, new
tables or Telegram text fallback. This adapter does not generate predictions.
"""
from datetime import datetime, timezone
from pathlib import Path
from hashlib import sha256
from io import BytesIO
from collections.abc import Mapping
import json
import re

from PIL import Image
from netrattler_lmg_owner_release import git_blob
from netrattler_clean_card_renderer import _stamp, _logo
from netrattler_premium_live_bridge import _book_price
from netrattler_builder_engine import is_bookmaker_source
from netrattler_crest_identity import same_club
from netrattler_candidate_settlement import grades

ROOT=Path(__file__).resolve().parent
AUTH=ROOT/".github/netrattler-all-family-owner-authorization.json"
FAMILIES=frozenset(("goal","corner","builder","combo","player_props",
                   "fouls_cards","late_goals","live_halftime","cross_mix"))
MULTI=frozenset(("builder","combo","cross_mix"))
LIVE=frozenset(("late_goals","live_halftime"))
FIVE=frozenset(("goal","corner","builder","combo"))
PINNED_GENERATORS={
    "netrattler_clean_master_builder.py":"5dc713ebc074aea67d6210bc151d192549fbb158",
    "netrattler_five_owner_reference_qa.py":"b7a1426499d08615675c0ddb4421c1a5a356325f",
}
VERSION="owner-derived-nine-v1"

def require_release(family):
    from netrattler_clean_master_builder import SOURCE_MAP
    from netrattler_five_owner_reference_qa import SPECS
    if family not in FAMILIES:
        raise ValueError("Unsupported owner-derived production family")
    data=json.loads(AUTH.read_text(encoding="utf-8"))
    row=(data.get("families") or {}).get(family) or {}
    expected=(SPECS[family][0] if family in FIVE else SOURCE_MAP[family])
    if (data.get("owner_release_requested") is not True
        or data.get("scope")!="all-16-netrattler-card-families"
        or row.get("owner_release_authorized") is not True
        or row.get("source_kind")!="source_reference_for_derived_master"
        or ROOT/str(row.get("source_path") or "")!=expected
        or git_blob(expected)!=row.get("source_git_blob")):
        raise ValueError("Pinned owner-derived master release required")
    for path,digest in PINNED_GENERATORS.items():
        if git_blob(ROOT/path)!=digest:
            raise ValueError("Owner-derived master generator changed")
    return row["source_git_blob"]

def _asset_signature(image):
    icon=_logo(image,96,96)
    return sha256(icon.tobytes()+str(icon.size).encode()).hexdigest()

def validate_release_and_data(family,record,*,now=None,settlement=None):
    require_release(family)
    if not isinstance(record,Mapping):
        raise ValueError("Original source record required")
    if any(record.get(k) for k in ("synthetic","_synthetic","estimated","estimated_odds","model_only","preview_only")):
        raise ValueError("Synthetic/preview record forbidden in production")
    rows=record.get("legs") if family in MULTI else [record]
    if not isinstance(rows,list) or not (2<=len(rows)<=10 if family in MULTI else len(rows)==1):
        raise ValueError("Wrong production selection count")
    if family in MULTI and record.get("formula_only") is not True:
        raise ValueError("Owner rule: combination prices are calculated from observed legs")
    if not str(record.get("ticket_id") or "").strip():
        raise ValueError("Stable original ticket identity required")
    seen=set()
    fixtures={}
    for row in rows:
        if not isinstance(row,Mapping):
            raise ValueError("Original selection mapping required")
        for k in ("fixture_id","quote_id","home_id","away_id","home","away","selection","bookmaker"):
            if not str(row.get(k) or "").strip():
                raise ValueError("Missing original provider evidence: "+k)
        key=tuple(str(row[k]) for k in ("fixture_id","quote_id"))
        if key in seen:
            raise ValueError("Repeated source quote receipt")
        seen.add(key)
        identity=tuple(str(row[k]) for k in ("home_id","away_id","home","away"))+(_stamp(row.get("kickoff")),)
        if fixtures.setdefault(key[0],identity)!=identity:
            raise ValueError("Conflicting original fixture")
        if (same_club(row["home"],row["away"]) or str(row["home_id"])==str(row["away_id"])):
            raise ValueError("Contradictory club identity")
        if (row.get("quote_observed") is not True or row.get("price_estimated") is not False
                or not is_bookmaker_source(row["bookmaker"])
                or any(row.get(k) for k in ("synthetic","_synthetic","estimated","model_only","preview_only"))):
            raise ValueError("Explicit original observed bookmaker evidence required")
        _book_price(row)
        if _asset_signature(row.get("home_crest"))==_asset_signature(row.get("away_crest")):
            raise ValueError("Duplicate opponent crest pixels")
        if family in LIVE:
            if (str(row.get("live_event_id"))!=str(row["fixture_id"])
                    or not row.get("live_source")
                    or not re.fullmatch(r"[0-9]{1,2}:[0-9]{1,2}",str(row.get("current_score") or ""))):
                raise ValueError("Exact live fixture score and identity required")
        if family in ("player_props","goal") or row.get("player_name"):
            if (not row.get("player_id") or not row.get("player_name")
                or row.get("confirmed_starter") is not True
                or str(row.get("player_team_id")) not in (str(row["home_id"]),str(row["away_id"]))
                or not row.get("player_photo_source")):
                raise ValueError("Verified player identity, photo provenance and starting XI required")
            _asset_signature(row.get("player_photo"))
    if family=="builder" and len(fixtures)!=1:
        raise ValueError("Single-match builder must use one fixture")
    if family=="cross_mix" and len(fixtures)<2:
        raise ValueError("Cross/Mix requires separate fixtures")
    grades(record,settlement)

def render(family,record,*,now=None,settlement=None):
    now=_stamp(now or datetime.now(timezone.utc))
    from netrattler_five_owner_dynamic_qa import render_owner_reference_qa
    from netrattler_clean_card_renderer import render_qa_card,render_cross_mix_qa
    from netrattler_clean_master_builder import render_clean_master
    if family in FIVE:
        return render_owner_reference_qa(family,record,now=now,settlement=settlement,production=True)
    if family=="cross_mix":
        return render_cross_mix_qa(record,now=now,settlement=settlement,production=True)
    plate,meta=render_clean_master(family)
    return render_qa_card(plate,meta,record,now=now,settlement=settlement,production=True)

def _snapshot(row):
    if isinstance(row,Image.Image):
        return {"asset_digest":_asset_signature(row)}
    if isinstance(row,datetime):
        return _stamp(row).isoformat()
    if isinstance(row,Mapping):
        return {str(k):_snapshot(v) for k,v in row.items()}
    if isinstance(row,(list,tuple)):
        return [_snapshot(x) for x in row]
    if row is None or type(row) in (str,int,float,bool):
        return row
    raise ValueError("Unserializable original source snapshot")

def snapshot(family,record,rendered_at,chat):
    return {"version":VERSION,"family":family,"ticket_id":record["ticket_id"],
            "chat_id":str(chat),"source_blob":require_release(family),
            "rendered_at":_stamp(rendered_at).isoformat(),
            "original":_snapshot(record)}

def send(cards,token,chat,family,record,*,reserve,confirm,log=print,now=None):
    """Production photo send only after a caller's durable atomic reservation.

    reserve(state) must return True only for a new durable unique ticket.
    confirm(state) stores the exact positive Telegram receipt in that same
    reservation. A failure after send must retain the reservation, not retry.
    """
    if not token or not chat:
        raise ValueError("Missing Telegram destination")
    clock=_stamp(now or datetime.now(timezone.utc))
    payload=render(family,record,now=clock)
    state=snapshot(family,record,clock,chat)
    if reserve(state) is not True:
        log("CANDIDATE_SEND_DEFERRED: duplicate or unavailable durable reservation")
        return None
    mid=cards._send_photo(token,chat,"",payload,log)
    if type(mid) is not int or mid<=0:
        log("CANDIDATE_SEND_UNCONFIRMED: reservation retained for reconciliation")
        return None
    receipt=dict(state,message_id=mid)
    if confirm(receipt) is not True:
        log("CANDIDATE_RECEIPT_PERSIST_FAILED: never re-send reserved ticket")
    return mid

def edit(cards,token,state,record,settlement,*,log=print):
    """Re-render original immutable inputs using the original render timestamp.

    Caller must load state from the durable reservation and supply independently
    verified grades; photos must still resolve to the exact saved pixel hashes.
    """
    if (not isinstance(state,Mapping) or state.get("version")!=VERSION
            or type(state.get("message_id")) is not int or state["message_id"]<=0
            or not str(state.get("chat_id") or "") or not token
            or settlement is None):
        raise ValueError("Confirmed original Telegram receipt and final grades required")
    family=state.get("family")
    clock=_stamp(state.get("rendered_at"))
    expected=snapshot(family,record,clock,state["chat_id"])
    if any(state.get(k)!=v for k,v in expected.items()):
        raise ValueError("Original source/asset snapshot differs; settlement deferred")
    payload=render(family,record,now=clock,settlement=settlement)
    return cards._edit_photo(token,state["chat_id"],state["message_id"],payload,log)
