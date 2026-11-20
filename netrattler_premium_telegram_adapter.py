"""Production adapter for verified NETRATTLER premium match masters.

No Telegram, Supabase or web calls here. The caller supplies verified team
crest image bytes; missing crests fail closed instead of using fake shields.
"""
from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw, ImageFont
from netrattler_premium_verified_cards import render_verified_png

MARKETS = {
    "btts": ("btts", "BTTS YES"),
    "over25": ("over", "OVER 2.5 YES"),
    "btts_ht": ("btts_halftime", "BTTS 1. HZ"),
    "over15_ht": ("over_halftime", "OVER 1.5 1. HZ"),
    "1x2": ("match_result", "1X2"),
    "combo": ("cross_mix", "BTTS + OVER 2.5"),
}


def _price(tip):
    for key in ("oddsYes", "odds", "odd", "price"):
        try:
            num = float(tip.get(key))
        except (TypeError, ValueError):
            continue
        if math.isfinite(num) and 1.01 <= num <= 100:
            return num
    raise ValueError("Verified original bookmaker odds missing")


def _font(size=28):
    for name in ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _crest(raw):
    if not isinstance(raw, (bytes, bytearray)) or len(raw) < 150:
        raise ValueError("Real team crest missing: no placeholders allowed")
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
        if min(im.size) < 40:
            raise ValueError("Team crest has insufficient resolution")
        return im.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise ValueError("Invalid genuine team crest") from exc


def _fit(draw, text, maxwidth, size=26):
    text = str(text or "").strip()
    for n in range(size, 15, -1):
        f = _font(n)
        if draw.textbbox((0,0),text,font=f)[2] <= maxwidth:
            return f
    raise ValueError("Team text would overflow approved premium layout")


def render(entries, target_date, *, crest_provider, result=None):
    if len(entries) != 1:
        raise ValueError("Premium single-market card needs one real selection")
    market, tip = entries[0]
    if market not in MARKETS:
        raise ValueError("Premium market not mapped: " + str(market))
    if not isinstance(tip, dict) or tip.get("_no_real_odds") or tip.get("synthetic") or tip.get("estimated_odds"):
        raise ValueError("Unverified odds or tip cannot be rendered")
    name = str(tip.get("match") or "")
    if " vs " in name:
        home, away = [p.strip() for p in name.split(" vs ",1)]
    elif " - " in name:
        home, away = [p.strip() for p in name.split(" - ",1)]
    else:
        raise ValueError("Two verified club names required")
    if not home or not away or home == away:
        raise ValueError("Invalid verified club pairing")
    # Real bookmaker/source evidence must exist in the original guarded tip.
    provenance = (tip.get("bookmaker") or tip.get("odds_source")
                  or tip.get("_source") or tip.get("source"))
    if not str(provenance or "").strip():
        raise ValueError("Real bookmaker source missing")
    category, selection = MARKETS[market]
    # Never publish "YES" when a qualified source pick actually says NO.
    # The absence of a separate selection field is valid for markets whose
    # canonical type already implies YES, but explicit contradictory values
    # must fail closed instead of silently reversing the betting direction.
    if market in ("btts", "over25", "btts_ht", "over15_ht", "combo"):
        declared = str(tip.get("selection") or tip.get("tip") or "").strip().upper()
        if declared in ("NO", "NEIN", "FALSE", "0", "UNDER", "UNTER"):
            raise ValueError("Market selection contradicts premium YES artwork")
    if market == "1x2":
        selection = str(tip.get("selection") or tip.get("tip") or "").strip()
        if selection not in ("1", "X", "2", "HOME", "DRAW", "AWAY"):
            raise ValueError("1X2 selection not verified")
    image_bytes = render_verified_png(category, [{
        "match": name, "market": selection,
        "bookmaker_odds": _price(tip), "bookmaker": str(provenance),
    }])
    first = _crest(crest_provider(home))
    second = _crest(crest_provider(away))
    with Image.open(io.BytesIO(image_bytes)) as source:
        im = source.convert("RGBA")
    draw = ImageDraw.Draw(im)
    for crest, team, cx in ((first,home,280),(second,away,842)):
        crest.thumbnail((116,116),Image.Resampling.LANCZOS)
        im.alpha_composite(crest, (int(cx-crest.width/2),242))
        draw.text((cx,361),team,font=_fit(draw,team,430),fill="#FAFCFF",anchor="mm")
    league = str(tip.get("league") or "").strip()
    if league:
        draw.text((561,530),league[:55],font=_fit(draw,league[:55],950,26),
                  fill="#27E6FF",anchor="mm")
    t = str(tip.get("time_local") or tip.get("time") or "").strip()
    if t:
        draw.text((561,585),t[:25],font=_font(27),fill="#FAFCFF",anchor="mm")
    probability = tip.get("probability")
    try:
        n = float(probability)
        if math.isfinite(n) and 0 <= n <= 100:
            draw.text((561,1235),f"MODELL  {n:.1f}%",font=_font(31),
                      fill="#FFE16A",anchor="mm")
    except (ValueError,TypeError):
        pass
    if isinstance(result,dict):
        marks=result.get("marks") or {}
        ft=str(result.get("ft") or "").strip()
        mark=marks.get("0") if isinstance(marks,dict) else None
        status={"win":"GEWONNEN","won":"GEWONNEN","loss":"VERLOREN",
                "lost":"VERLOREN","void":"VOID"}.get(str(mark).lower(),"")
        if ft or status:
            draw.text((561,1280),("FT "+ft+"  "+status).strip()[:46],
                      font=_font(26),fill="#3AFD75" if status=="GEWONNEN" else "#FAFCFF",
                      anchor="mm")
    buf=io.BytesIO()
    im.convert("RGB").save(buf,format="PNG")
    return buf.getvalue()
