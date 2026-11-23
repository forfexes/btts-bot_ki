"""Five NETRATTLER owner-reference families: strict OFFLINE dynamic card QA.

This module renders ONLY onto source-derived blank QA plates. It does not
approve artwork, send to Telegram, access the network, or create predictions.
All data must be supplied by a caller. Sandbox watermark is always visible.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
import math
from typing import Mapping

from PIL import Image, ImageDraw

from netrattler_clean_card_renderer import _crest, _logo, _stamp, _text
from netrattler_clean_master_builder import W, H
from netrattler_five_owner_reference_qa import SPECS, build

ROW_H = 110
BODY_TOP = 614
BODY_END = 1092


def _required(row, keys, prefix=""):
    if not isinstance(row, Mapping):
        raise ValueError(prefix + "verified record required")
    for key in keys:
        val = row.get(key)
        if val is None or isinstance(val, str) and not val.strip():
            raise ValueError(prefix + "missing " + key)


def _price(value):
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("Observed decimal bookmaker odds required") from None
    if not math.isfinite(number) or not (1.01 <= number <= 1000):
        raise ValueError("Invalid bookmaker decimal odds")
    return number


def _observed(row, now, prefix=""):
    _required(row, ("bookmaker", "quote_id", "quote_observed_at", "kickoff"), prefix)
    if row.get("quote_observed") is not True or row.get("price_estimated") is not False:
        raise ValueError(prefix + "bookmaker quote must be explicitly observed")
    seen, kickoff = _stamp(row["quote_observed_at"]), _stamp(row["kickoff"])
    if not seen <= now < kickoff or not timedelta(0) <= now-seen <= timedelta(minutes=15):
        raise ValueError(prefix + "quote must be fresh and strictly pre-match")
    return kickoff


def _fixture(row):
    _required(row, ("fixture_id", "home", "away", "home_id", "away_id"))
    if (str(row["home_id"]) == str(row["away_id"])
            or str(row["home"]).casefold() == str(row["away"]).casefold()):
        raise ValueError("Ambiguous or identical opponents")
    return str(row["fixture_id"])


def _open_source(category):
    if category not in SPECS:
        raise ValueError("Only five genuine owner reference families supported")
    plate, meta = build(category)
    if (meta.get("production_approved") is not False
            or meta.get("classification") != "owner-derived_clean_QA_NOT_user_original"
            or meta.get("logo_backplates") is not False):
        raise ValueError("Unapproved source provenance incorrectly represented")
    with Image.open(BytesIO(plate)) as check:
        if check.format != "PNG" or check.size != (W, H):
            raise ValueError("Invalid owner-source-derived QA plate")
        check.verify()
    with Image.open(BytesIO(plate)) as image:
        return image.convert("RGBA").copy(), meta


def _draw_match(canvas, meta, match):
    _fixture(match)
    for slot, crest in zip(meta["floating_crest_slots"],
                          (match.get("home_crest"), match.get("away_crest"))):
        _crest(canvas, crest, slot)
    d = ImageDraw.Draw(canvas)
    _text(d, "VS", (W//2, 419), max_width=155, max_height=64,
          start_size=47, color="#FFE56C")
    _text(d, match["home"], (250, 559), max_width=248, max_height=42,
          start_size=23)
    _text(d, match["away"], (872, 559), max_width=248, max_height=42,
          start_size=23)
    _text(d, match["fixture_id"], (W//2, 484), max_width=355,
          max_height=36, start_size=18)


def _stat(row, key, now, fixture_id):
    stats = row.get("stats") or {}
    if not isinstance(stats, Mapping):
        raise ValueError("Verified statistic mapping required")
    item = stats.get(key)
    if item is None:
        return "—"
    _required(item, ("value", "source", "event_id", "observed_at"), key+": ")
    if str(item["event_id"]) != fixture_id or _stamp(item["observed_at"]) > now:
        raise ValueError("Mismatched or future observed stat")
    return str(item["value"])


def _single(category, canvas, meta, record, now):
    fixture = _fixture(record)
    _observed(record, now)
    _required(record, ("selection", "market", "bookmaker_odds"))
    allowed = {
        "btts": ("BTTS", "BEIDE TEAMS"),
        "goal": ("TOR", "GOAL", "OVER", "UNDER"),
        "corner": ("ECKE", "CORNER"),
    }[category]
    if not any(word in str(record["market"]).upper() for word in allowed):
        raise ValueError("Wrong market on original family card")
    value = _price(record["bookmaker_odds"])
    _draw_match(canvas, meta, record)
    d = ImageDraw.Draw(canvas)
    for index in (1, 2, 3):
        name = f"stat_{index}"
        slot = meta["blank_slots"][name]
        _text(d, _stat(record, name, now, fixture),
              (int(slot["x"])+int(slot["width"])//2,
               int(slot["y"])+int(slot["height"])//2),
              max_width=int(slot["width"])-18,
              max_height=int(slot["height"])-9, start_size=27)
    _text(d, f'{record["selection"]} @{value:.2f}', (685, 1168),
          max_width=466, max_height=45, start_size=30, color="#FFE56C")
    return canvas, 0


def _mini_crest(canvas, logo, center):
    icon = _logo(logo, 48, 48)
    cx, cy = center
    x, y = round(cx-icon.width/2), round(cy-icon.height/2)
    if min(x, y) < 0 or x + icon.width > canvas.width or y + icon.height > canvas.height:
        raise ValueError("Authentic crest exceeds selected row")
    canvas.alpha_composite(icon, (x, y))


def _ticket(category, record, now):
    _required(record, ("bookmaker", "combined_quote_id", "combined_odds",
                       "kickoff", "quote_observed_at"))
    if record.get("combined_odds_observed") is not True or record.get("price_estimated") is not False:
        raise ValueError("Confirmed combined bookmaker ticket required")
    _observed(dict(record, quote_id=record["combined_quote_id"], quote_observed=True), now)
    total = _price(record["combined_odds"])
    legs = record.get("legs")
    max_legs = 7 if category == "builder" else 10
    if not isinstance(legs, (list, tuple)) or not 2 <= len(legs) <= max_legs:
        raise ValueError("2 through valid max individually verified legs required")
    for idx, leg in enumerate(legs, 1):
        _fixture(leg)
        _required(leg, ("market", "selection", "bookmaker_odds",
                        "home_crest", "away_crest"), prefix=f"leg {idx}: ")
        _observed(leg, now, prefix=f"leg {idx}: ")
        _price(leg["bookmaker_odds"])
        if str(leg["bookmaker"]).casefold() != str(record["bookmaker"]).casefold():
            raise ValueError("Ticket and legs need same real sportsbook")
        if not all(isinstance(leg[k], Image.Image) for k in ("home_crest", "away_crest")):
            raise ValueError("Each fixture needs real transparent club emblems")
        if (str(leg.get("player_name") or "").strip()
                and (not leg.get("player_id") or not isinstance(leg.get("player_photo"), Image.Image))):
            raise ValueError("Player builder leg requires authentic athlete photo and player ID")
    return legs, total


def _multi_canvas(base, count):
    # The five-asset clean builder/combo source has a BLANK lower body.
    # Insert new empty original-derived arena area, never old screenshot data.
    extra = max(0, count*ROW_H+36-(BODY_END-BODY_TOP))
    if not extra:
        return base, 0
    expanded = Image.new("RGBA", (W, H+extra), (3, 16, 29, 255))
    expanded.alpha_composite(base.crop((0, 0, W, BODY_END)), (0, 0))
    # Extend only the already-clean, data-free arena. Match the original
    # 70px background grid rhythm, preserving its ambient sides and cyan
    # vertical rails instead of inserting a solid dark rectangle/seam.
    band = base.crop((0, 882, W, 952))
    for offset in range(0, extra, 70):
        height = min(70, extra-offset)
        expanded.alpha_composite(band.crop((0, 0, W, height)),
                                 (0, BODY_END+offset))
    expanded.alpha_composite(base.crop((0, BODY_END, W, H)),
                             (0, BODY_END+extra))
    return expanded, extra


def _multi(category, base, record, now):
    legs, total = _ticket(category, record, now)
    canvas, extra = _multi_canvas(base, len(legs))
    draw = ImageDraw.Draw(canvas)
    fixture_count = len({str(leg["fixture_id"]) for leg in legs})
    match_caption = "MEHRERE SPIELE" if fixture_count > 1 else "EIN SPIEL"
    _text(draw, match_caption, (W//2, 428),
          max_width=346, max_height=45, start_size=26, color="#FFE56C")
    _text(draw, f"{len(legs)} AUSWAHLEN · ECHTE GESAMTQUOTE",
          (W//2, 487), max_width=355, max_height=32, start_size=16)
    for idx, leg in enumerate(legs, 1):
        y = BODY_TOP + 15 + (idx-1)*ROW_H
        draw.rounded_rectangle((125, y, W-125, y+ROW_H-8),
                               radius=12, fill="#081E30", outline="#1FBADD", width=2)
        _mini_crest(canvas, leg["home_crest"], (173,y+48))
        _mini_crest(canvas, leg["away_crest"], (244,y+48))
        _text(draw, f'{idx}. {leg["home"]} – {leg["away"]}',
              (550,y+27), max_width=440, max_height=32, start_size=18)
        _text(draw, f'{leg["market"]} · {leg["selection"]}',
              (540,y+56), max_width=430, max_height=28, start_size=17,
              color="#FFE56C")
        # Every leg carries its own verified fixture start, not one
        # invented shared time for a cross-game ticket.
        leg_time = _stamp(leg["kickoff"]).strftime("%d.%m.%Y %H:%M UTC")
        _text(draw, leg_time, (540,y+84), max_width=410,
              max_height=23, start_size=17, color="#AEC8D5")
        _text(draw, f'@{_price(leg["bookmaker_odds"]):.2f}',
              (938,y+49), max_width=96, max_height=37, start_size=20,
              color="#40F58A")
    _text(draw, f'{category.upper()} {len(legs)} · @{total:.2f}',
          (685, 1169+extra), max_width=470, max_height=45,
          start_size=27, color="#FFE56C")
    return canvas, extra


def render_owner_reference_qa(category, record, *, now=None):
    """Return a watermarked synthetic-data preview only, never an approved tip."""
    if not isinstance(record, Mapping):
        raise ValueError("Strict verified fixture or ticket mapping required")
    now = _stamp(now or datetime.now(timezone.utc))
    image, meta = _open_source(category)
    if category in ("builder", "combo"):
        image, extra = _multi(category, image, record, now)
    else:
        image, extra = _single(category, image, meta, record, now)
    d = ImageDraw.Draw(image)
    _text(d, "SANDBOX · KEIN TIPP", (W//2, 1268+extra),
          max_width=398, max_height=43, start_size=25, color="#FFFFFF")
    buffer = BytesIO()
    image.convert("RGB").save(buffer, "PNG", optimize=True)
    return buffer.getvalue()
