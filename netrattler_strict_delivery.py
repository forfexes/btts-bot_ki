"""Fail-closed production card transport. No legacy text fallback."""
from io import BytesIO
from PIL import Image, ImageChops
from netrattler_premium_live_bridge import _split_match, _book_price
from netrattler_visual_gate import club_same
from netrattler_scorer_qualification import qualifies
from netrattler_stadium_portrait import REGULAR, VERSION, DIMENSIONS, load_master, _verified_time

def scorer_eligible(tip):
    try:
        home,away=_split_match(tip.get("match"))
        team=tip.get("team")
        if sum(club_same(team,t) for t in (home,away))!=1:
            return False,"unverified_player_team"
        if not str(tip.get("player") or "").strip():
            return False,"missing_player"
        return qualifies(tip.get("odds"),tip.get("probability"),
                         tip.get("_source") or tip.get("bookmaker") or tip.get("odds_source"))
    except (ValueError,TypeError,AttributeError):
        return False,"invalid_scorer"

def verified_regular_payload(payload):
    """Validate the actual outgoing PNG against the pinned owner master."""
    if not isinstance(payload, (bytes, bytearray)):
        return False
    try:
        master = load_master()
        with Image.open(BytesIO(payload)) as source:
            if source.format != "PNG" or source.size != DIMENSIONS:
                return False
            source.verify()
        with Image.open(BytesIO(payload)) as source:
            image = source.convert("RGB")
        # The masthead is reserved artwork, never a data overlay.
        region = (0, 0, DIMENSIONS[0], 265)
        if ImageChops.difference(master.crop(region), image.crop(region)).getbbox() is not None:
            return False
        # A blank owner master is not a rendered tip. Both the matchup area
        # and the selection/price area must contain actual data overlays.
        for box in ((75, 350, DIMENSIONS[0]-75, 740),
                    (75, 835, DIMENSIONS[0]-75, 970)):
            if ImageChops.difference(master.crop(box), image.crop(box)).getbbox() is None:
                return False
        return True
    except (OSError, ValueError, SyntaxError, TypeError):
        return False


def send_regular(cards,token,chat,market,tip,target_date,log=print):
    if not token or not chat or market not in REGULAR:
        log("ORIGINAL_CARD_DEFERRED: unsupported market or missing destination")
        return None
    try:
        row=dict(tip)
        _book_price(row)
        # Never reinterpret an unverified local clock as a real fixture.
        stamp=next((row[k] for k in ("commence_time","kickoff_utc","_kickoff","kickoff","starts","time_utc","time") if _verified_time({"commence_time":row.get(k)})),None)
        if not stamp:
            log("ORIGINAL_CARD_DEFERRED: unverified kickoff")
            return None
        row["commence_time"]=stamp
        row["card_template_version"]=VERSION
        entries=[(market,row)]
        payload=cards.render_card(entries,target_date)
        if not verified_regular_payload(payload):
            log("ORIGINAL_CARD_DEFERRED: invalid or altered original PNG")
            return None
        mid=cards._send_photo(token,chat,"",payload,log)
        if not isinstance(mid,int) or isinstance(mid,bool) or mid<=0:
            return None
        # Do not send the same tip again if secondary card history fails.
        try:
            cards.save_card(chat,mid,entries,target_date,log)
        except Exception as exc:
            log("ORIGINAL_CARD_HISTORY_FAILED: "+type(exc).__name__)
        return mid
    except Exception as exc:
        log("ORIGINAL_CARD_DEFERRED: "+type(exc).__name__+": "+str(exc)[:100])
        return None
