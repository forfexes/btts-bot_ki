"""Offline-only, no-overpaint renderer for NETRATTLER's ten owner-derived QA plates.

This is NOT an approved owner-original Telegram renderer. Never import it from a
production sender: it always prints a conspicuous SANDBOX marker and provides
no Telegram, network, database or publication function.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from io import BytesIO
from math import isfinite
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFont

from netrattler_clean_master_builder import LABELS, W, H

FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def _font(size: int):
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _text(draw: ImageDraw.ImageDraw, text: str, center: tuple[int, int],
          *, max_width: int, max_height: int, start_size: int = 35,
          color: str = "#F9FCFF") -> None:
    value = " ".join(str(text or "").split())
    if not value or len(value) > 100 or any(ord(c) < 32 for c in value):
        raise ValueError("Missing or invalid verified card field")
    for size in range(start_size, 13, -1):
        font = _font(size)
        x0, y0, x1, y1 = draw.textbbox((0, 0), value, font=font, anchor="mm")
        if x1-x0 <= max_width and y1-y0 <= max_height:
            draw.text(center, value, fill=color, font=font, anchor="mm")
            return
    raise ValueError("Verified text does not fit the original-layout slot")


def _stamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except (ValueError, TypeError):
            raise ValueError("Timestamp must be ISO-8601 with timezone") from None
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("Timestamp must include its timezone")
    return dt.astimezone(timezone.utc)


def _logo(source: Image.Image, max_w: int, max_h: int) -> Image.Image:
    """Only real alpha art, no circular background, badge, ring or sticker."""
    if not isinstance(source, Image.Image):
        raise ValueError("Authentic team crest required")
    im = source.convert("RGBA")
    alpha = im.getchannel("A")
    if alpha.getextrema()[0] != 0:
        raise ValueError("Opaque square logo would look like a pasted-on sticker")
    bbox = alpha.point(lambda px: 255 if px >= 32 else 0).getbbox()
    if bbox is None:
        raise ValueError("Crest is fully transparent")
    im = im.crop(bbox)
    if min(im.size) < 24:
        raise ValueError("Insufficient visible crest resolution")
    factor = min(max_w / im.width, max_h / im.height)
    if factor > 3.0:
        raise ValueError("Tiny crest cannot be enlarged into premium artwork")
    im = im.resize((max(1, round(im.width * factor)),
                    max(1, round(im.height * factor))), Image.Resampling.LANCZOS)
    return im


def _crest(canvas: Image.Image, source: Image.Image, slot: Mapping[str, Any]) -> None:
    width, height = int(slot["max_width"]), int(slot["max_height"])
    cx, cy = int(slot["center_x"]), int(slot["center_y"])
    icon = _logo(source, width, height)
    x, y = round(cx-icon.width/2), round(cy-icon.height/2)
    if x < 95 or x+icon.width > W-95 or y < 348 or y+icon.height > 560:
        raise ValueError("Crest exceeds isolated, floating original slot")
    canvas.alpha_composite(icon, (x, y))


_MARKET_WORDS = {
    "over": ("OVER", "UNDER"),
    "btts_halftime": ("BTTS", "BEIDE TEAMS"),
    "over_halftime": ("OVER", "UNDER"),
    "match_result": ("HOME", "AWAY", "DRAW", "1X2", "HEIM", "AUSW", "UNENTSCHIEDEN"),
    "player_props": ("PLAYER", "SHOTS", "GOALS", "ASSISTS", "SCHUESSE", "SCHÜSSE", "TORE"),
    "fouls_cards": ("FOUL", "TACKLE", "CARD", "KARTE"),
    "var": ("VAR",),
    "late_goals": ("RESTSPIELZEIT", "NÄCHSTES TOR", "NEXT GOAL"),
    "live_halftime": ("HALBZEIT", "HT", "1. HÄLFTE"),
    "cross_mix": ("CROSS", "KOMBI", "BUILDER", "MIX"),
}


def _market_guard(category: str, record: Mapping[str, Any]) -> bool:
    selection = str(record.get("selection") or "").strip().upper()
    if not any(word in selection for word in _MARKET_WORDS[category]):
        raise ValueError("Selection does not belong to the verified card category")
    if category == "player_props":
        if (not record.get("player_id") or not record.get("player_name") or
                record.get("confirmed_starter") is not True or
                str(record.get("player_team_id")) not in
                (str(record.get("home_id")), str(record.get("away_id"))) or
                not str(record.get("player_photo_source") or "").strip() or
                not isinstance(record.get("player_photo"), Image.Image)):
            raise ValueError("Player card needs authenticated cutout photo, player and confirmed XI")
        _logo(record["player_photo"], 128, 158)
    if category == "cross_mix":
        if (record.get("combined_odds_observed") is not True or
                not record.get("combined_quote_id") or
                not isinstance(record.get("legs"), (list, tuple)) or
                len(record["legs"]) < 2):
            raise ValueError("Multi-leg card needs a real combined bookmaker ticket")
    live = category in ("late_goals", "live_halftime")
    if live:
        minute = record.get("match_minute")
        if not (isinstance(minute, int) and
                (65 <= minute <= 90 if category == "late_goals" else 1 <= minute <= 45) and
                record.get("live_event_id") and record.get("live_source") and
                record.get("current_score")):
            raise ValueError("Live card missing exact event, score or minute")
    return live


def render_qa_card(plate_png: bytes, metadata: Mapping[str, Any],
                   record: Mapping[str, Any], *, now: datetime | None = None, settlement=None) -> bytes:
    """Render one strictly labeled SANDBOX PNG; never produce a publishable tip.

    The record needs verified fixture/team IDs, observed bookmaker quote ID,
    decimal price, timestamp, kickoff and two transparent real team crests.
    Missing statistics are displayed as an em dash, never as a zero.
    """
    if not isinstance(metadata, Mapping) or not isinstance(record, Mapping):
        raise ValueError("Metadata and verified record are required")
    category = str(metadata.get("category") or "")
    # CROSS/MIX has multiple independently verified fixtures. Never publish
    # the former single-row preview that hides its individual selections.
    if category == "cross_mix":
        raise ValueError("Cross/Mix requires the full verified multi-leg renderer")
    if (category not in LABELS or
            metadata.get("classification") != "owner-derived_clean_QA_NOT_user_original" or
            metadata.get("production_approved") is not False or
            metadata.get("logo_backplates") is not False):
        raise ValueError("Not a valid, explicitly unapproved owner-derived QA master")
    slots = metadata.get("floating_crest_slots")
    stat_slots = metadata.get("blank_slots")
    if not (isinstance(slots, list) and len(slots) == 2
            and isinstance(stat_slots, dict) and len(stat_slots) == 3):
        raise ValueError("Original layout metadata incomplete")
    for key in ("home", "away", "home_id", "away_id", "fixture_id",
                "bookmaker", "quote_id", "selection"):
        if not str(record.get(key) or "").strip():
            raise ValueError("Verified match, teams, market, quote source and receipt required: " + key)
    if (str(record["home_id"]) == str(record["away_id"]) or
            str(record["home"]).casefold() == str(record["away"]).casefold()):
        raise ValueError("Fixture must have two distinct verified teams")
    try:
        price = float(record.get("bookmaker_odds"))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Real observed bookmaker price required") from None
    if not (isfinite(price) and 1.01 <= price <= 1000.0) or record.get("price_estimated") is not False:
        raise ValueError("Unverified or estimated bookmaker quote")
    live = _market_guard(category, record)
    now = _stamp(now or datetime.now(timezone.utc))
    kickoff, observed = _stamp(record.get("kickoff")), _stamp(record.get("quote_observed_at"))
    if live:
        fresh = (kickoff <= now <= kickoff + timedelta(hours=3) and
                 timedelta(0) <= now-observed <= timedelta(seconds=90))
    else:
        fresh = (observed <= now < kickoff and
                 timedelta(0) <= now-observed <= timedelta(minutes=15))
    if not fresh:
        raise ValueError("Outdated, future, or wrongly timed bookmaker quote")
    if not isinstance(plate_png, (bytes, bytearray)):
        raise ValueError("Expected a clean PNG plate")
    with Image.open(BytesIO(plate_png)) as original:
        if original.format != "PNG" or original.size != (W, H):
            raise ValueError("Original-derived master has incorrect type or dimensions")
        original.verify()
    with Image.open(BytesIO(plate_png)) as source:
        canvas = source.convert("RGBA").copy()
    for slot, source in zip(slots, (record.get("home_crest"), record.get("away_crest"))):
        _crest(canvas, source, slot)
    draw = ImageDraw.Draw(canvas)
    if category == "player_props":
        # A real alpha-cutout photo floats between the actual club crests
        # on the data-free original stadium. Never draw a circular avatar,
        # sticker, opaque portrait box, or substitute generic sports icon.
        photo = _logo(record["player_photo"], 128, 158)
        canvas.alpha_composite(photo, (
            W//2-photo.width//2, 433-photo.height//2))
        _text(draw, str(record["fixture_id"]), (W//2, 563),
              max_width=330, max_height=29, start_size=16)
        _text(draw, str(record["player_name"]), (W//2, 602),
              max_width=395, max_height=31, start_size=23, color="#FFE56C")
    else:
        _text(draw, "VS", (W//2, 420), max_width=165, max_height=72,
              start_size=48, color="#FFE56C")
        _text(draw, str(record["fixture_id"]), (W//2, 479),
              max_width=355, max_height=38, start_size=19)
    _text(draw, str(record["home"]), (250, 564),
          max_width=250, max_height=44, start_size=24)
    _text(draw, str(record["away"]), (872, 564),
          max_width=250, max_height=44, start_size=24)
    stats = record.get("stats") or {}
    if not isinstance(stats, Mapping):
        raise ValueError("Only source-verified statistics mappings accepted")
    for j in range(1, 4):
        key = "stat_" + str(j)
        loc = stat_slots[key]
        item = stats.get(key)
        if item is None:
            value = "—"
        elif (not isinstance(item, Mapping) or not item.get("source") or
              not item.get("event_id") or not item.get("observed_at") or
              str(item.get("value") or "").strip() == ""):
            raise ValueError("Statistics need independent provider/event/time evidence")
        else:
            stamp = _stamp(item["observed_at"])
            if stamp > now or (not live and stamp > kickoff):
                raise ValueError("Look-ahead statistic or mismatched timing")
            if str(item["event_id"]) != str(record["fixture_id"]):
                raise ValueError("Statistics belong to a different fixture")
            value = str(item["value"])
        _text(draw, value,
              (int(loc["x"]) + int(loc["width"])//2,
               int(loc["y"]) + int(loc["height"])//2),
              max_width=int(loc["width"])-15,
              max_height=int(loc["height"])-8, start_size=31)
    # New text goes only into blank fields. No opaque backing rectangles
    # or emblem circles are ever drawn over the source-derived QA plate.
    selection = f'{record["selection"]}  @{price:.2f}'
    _text(draw, selection, (682, 1169), max_width=465,
          max_height=50, start_size=33, color="#FFE56C")
    from netrattler_candidate_settlement import footer
    _text(draw, footer(record, settlement), (W//2, 1268), max_width=395,
          max_height=45, start_size=25, color="#FCFCFF")
    output = BytesIO()
    canvas.convert("RGB").save(output, "PNG", optimize=True)
    return output.getvalue()



def render_cross_mix_qa(record: Mapping[str, Any], *, now: datetime | None = None, settlement=None) -> bytes:
    """Render all 2-10 Cross/Mix legs onto its owner-derived clean reference.

    This is strictly watermarked OFFLINE QA, never a production Telegram
    renderer. It reuses the proven combo row geometry and independently
    validates bookmaker receipts, times, each fixture and authentic alpha
    team crests for every single selection.
    """
    from netrattler_clean_master_builder import render_clean_master
    from netrattler_five_owner_dynamic_qa import _multi
    if not isinstance(record, Mapping):
        raise ValueError("Verified Cross/Mix ticket mapping required")
    plate, metadata = render_clean_master("cross_mix")
    if (metadata.get("production_approved") is not False
            or metadata.get("classification") != "owner-derived_clean_QA_NOT_user_original"):
        raise ValueError("Cross/Mix cannot reuse an unapproved owner screenshot")
    with Image.open(BytesIO(plate)) as picture:
        if picture.format != "PNG" or picture.size != (W, H):
            raise ValueError("Missing clean Cross/Mix QA plate")
        canvas = picture.convert("RGBA")
    canvas, extra = _multi("cross_mix", canvas, record,
                           _stamp(now or datetime.now(timezone.utc)), settlement=settlement)
    draw = ImageDraw.Draw(canvas)
    from netrattler_candidate_settlement import footer
    _text(draw, footer(record, settlement), (W//2, 1268+extra),
          max_width=398, max_height=43, start_size=25, color="#FCFCFF")
    output = BytesIO()
    canvas.convert("RGB").save(output, "PNG", optimize=True)
    return output.getvalue()
