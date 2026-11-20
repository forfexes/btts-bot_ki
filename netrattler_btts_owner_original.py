"""BTTS card on the actual owner-supplied NETRATTLER PNG reference.

The original crown, metallic wordmark, gold BTTS title, outer neon card frame
and @prophunter footer remain on the original photographic source. Every
sample player, club, quote or statistic in the inner panel is concealed before
rendering verified values. This module NEVER sends Telegram messages.
"""
from __future__ import annotations

import io
import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REFERENCE = (Path(__file__).resolve().parent / "assets" / "original_templates"
             / "NETRATTLER_BTTS_originalkarte.png")
W, H = 1122, 1402
WHITE, CYAN, GOLD, GREEN = "#F6FCFF", "#25DFFF", "#FFD847", "#3CF68E"
NAVY = "#061421"


@lru_cache(maxsize=12)
def _font(size: int) -> ImageFont.ImageFont:
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _text(draw: ImageDraw.ImageDraw, text, x, y, width, size=35, color=WHITE):
    value = str(text or "").strip()
    if not value:
        raise ValueError("Unverified blank value on BTTS card")
    n = size
    while n >= 15 and draw.textlength(value, font=_font(n)) > width:
        n -= 1
    if n < 15:
        raise ValueError("Verified BTTS label too long: " + value[:60])
    draw.text((x,y), value, anchor="mm", font=_font(n), fill=color,
              stroke_width=1, stroke_fill="#031017")


def _panel(draw, rect, edge=CYAN, radius=18, width=4):
    draw.rounded_rectangle(rect, radius=radius, fill=NAVY,
                           outline=edge, width=width)


def _percent(value, *, strict=False):
    if value is None or value == "":
        if strict:
            raise ValueError("Verified BTTS model probability missing")
        return "—"
    try:
        p = float(str(value).strip().replace("%", ""))
    except (TypeError, ValueError):
        raise ValueError("Invalid BTTS probability") from None
    if not math.isfinite(p) or p < 0 or p > 100:
        raise ValueError("Invalid BTTS probability")
    return f"{p:.1f}%"


def _optional(tip, *keys):
    for key in keys:
        value = tip.get(key)
        if value is not None and str(value).strip():
            return value
    return None


def _crest(im, img: Image.Image, cx: int):
    if not isinstance(img, Image.Image):
        raise ValueError("Genuine BTTS team crest missing")
    crest = img.convert("RGBA")
    crest.thumbnail((155,155),Image.Resampling.LANCZOS)
    if not crest.width or not crest.height:
        raise ValueError("Empty BTTS team crest")
    im.alpha_composite(crest,(cx-crest.width//2,350+(155-crest.height)//2))


def _result_label(result):
    if not isinstance(result,dict):
        return "OFFEN"
    marks=result.get("marks") or {}
    mark=marks.get("0") if isinstance(marks,dict) else None
    value={"win":"GEWONNEN","won":"GEWONNEN","loss":"VERLOREN",
           "lost":"VERLOREN","void":"VOID"}.get(str(mark or "").lower())
    return value or "OFFEN"


def render(tip: dict, home: str, away: str, home_img: Image.Image,
           away_img: Image.Image, odds: float, result=None) -> bytes:
    if not (REFERENCE.is_file() and home and away and home != away):
        raise ValueError("Authentic BTTS original or verified clubs missing")
    if not isinstance(tip,dict) or not (1.01 <= float(odds) <= 100.0):
        raise ValueError("Verified bookmaker odds missing")
    probability = _optional(tip,"probability","model_probability")
    model = _percent(probability,strict=True)
    with Image.open(REFERENCE) as reference:
        reference.load()
        if reference.format != "PNG" or min(reference.size) < 600:
            raise ValueError("Unapproved BTTS original image")
        im=reference.convert("RGBA").resize((W,H),Image.Resampling.LANCZOS)
    draw=ImageDraw.Draw(im)
    # Clean the ENTIRE sample-data interior (two example crests, competition,
    # names, L10s, tip, prices, model values and settlement) without altering
    # original logo, title, stadium spotlights, cyan exterior or footer.
    draw.rounded_rectangle((63,301,1059,1268),radius=25,fill="#04111F")
    _panel(draw,(81,323,1041,625),width=5)
    _crest(im,home_img,281)
    _crest(im,away_img,842)
    _text(draw,home.upper(),281,551,360,35)
    _text(draw,away.upper(),842,551,360,35)
    _text(draw,"VS",562,482,110,50,GOLD)
    league=str(tip.get("league") or "").strip()
    if league:
        _text(draw,league,562,368,265,23,CYAN)
    kick=str(tip.get("time_local") or tip.get("time") or "").strip()
    if kick:
        _text(draw,kick,562,581,250,24,WHITE)
    _panel(draw,(81,645,1041,865),width=4)
    labels=(
        ("BTTS L10", _optional(tip,"btts_l10","h2h_btts","BTTS_L10")),
        ("HEIM", _optional(tip,"btts_home","btts_home_prob","home_btts")),
        ("AUSW", _optional(tip,"btts_away","btts_away_prob","away_btts")),
    )
    for i,(title,value) in enumerate(labels):
        cx=242+i*322
        _text(draw,title,cx,699,290,30,CYAN)
        if value is None:
            display="—"
        elif "/" in str(value):
            display=str(value).strip()[:18]
        else:
            display=_percent(value)
        _text(draw,display,cx,789,290,43,GOLD)
        if i:
            draw.line((cx-161,671,cx-161,845),fill=CYAN,width=2)
    _panel(draw,(81,890,1041,1047),edge=GOLD,width=5)
    _text(draw,"TIPP: BTTS — JA",414,969,650,45,GOLD)
    _text(draw,f"@{float(odds):.2f}",892,969,235,48,GOLD)
    _panel(draw,(81,1061,1041,1150),width=3)
    _text(draw,"MODELL",227,1106,240,30,CYAN)
    _text(draw,model,485,1106,230,38,GREEN)
    estimated_edge=(float(str(probability).replace("%",""))/100*float(odds)-1)*100
    _text(draw,"EV",704,1106,100,29,CYAN)
    _text(draw,f"{estimated_edge:+.1f}%",911,1106,202,37,
          GREEN if estimated_edge>=0 else "#FF7777")
    _panel(draw,(81,1164,1041,1242),edge=GOLD,width=3)
    _text(draw,"AUSWERTUNG:",326,1202,415,30,WHITE)
    _text(draw,_result_label(result),785,1202,379,38,GOLD)
    out=io.BytesIO()
    im.convert("RGB").save(out,format="PNG",optimize=True)
    return out.getvalue()
