"""Render NETRATTLER cards using the current SVG technical masters.

These SVGs are programmatically generated placeholders, NOT the original user
reference pictures. Only verified player/team data may be rendered. Telegram
sending and settlement remain in existing modules.
"""
from __future__ import annotations

import io
import math
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, ImageOps

ASSETS = Path(__file__).resolve().parent / "assets"
BUILDER_IMAGE = ASSETS / "premium_builder_blank.svg"
GOAL_IMAGE = ASSETS / "premium_goal_blank.svg"
WHITE, GOLD, CYAN, GREEN, RED = "#FAFCFF", "#FFE14A", "#27E6FF", "#3AFD75", "#FF6C6C"


@lru_cache(maxsize=2)
def _base(path: str):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"NETRATTLER Originalvorlage nicht gefunden: {path.name}")
    if path.suffix.lower() == ".svg":
        try:
            import cairosvg
        except ImportError as exc:
            raise RuntimeError("cairosvg wird für die Premium-SVG-Master benötigt") from exc
        data = cairosvg.svg2png(url=str(path), output_width=1122, output_height=1402)
        source = io.BytesIO(data)
    else:
        source = path
    with Image.open(source) as image:
        if image.size != (1122, 1402):
            raise ValueError("Premium-Vorlage hat unerwartete Abmessungen")
        return image.convert("RGB").copy()


@lru_cache(maxsize=100)
def _font(size: int, italic: bool = True):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-BoldOblique.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    if not italic:
        paths = paths[1:] + paths[:1]
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _label(draw, text, cx, cy, width, *, size=27, min_size=14,
           fill=WHITE, shadow=True, italic=True):
    value = str(text or "").strip()
    if not value:
        raise ValueError("Nicht bestätigter Text auf NETRATTLER-Karte")
    while size > min_size and draw.textlength(value, _font(size, italic)) > width:
        size -= 1
    if draw.textlength(value, _font(size, italic)) > width:
        raise ValueError("Text überlang für Original-Vorlage: " + value[:55])
    f = _font(size, italic)
    length = draw.textlength(value, f)
    x = int(cx - length/2)
    if shadow:
        draw.text((x+2,cy+2),value,font=f,fill="#020609",stroke_width=2,stroke_fill="#030A14")
    draw.text((x,cy),value,font=f,fill=fill)


def _erase(draw, box, *, fill="#07141B", radius=8):
    draw.rounded_rectangle(tuple(map(int,box)), radius=radius, fill=fill)


def _picture(raw, min_size=60):
    if not isinstance(raw,(bytes,bytearray)) or not raw:
        raise ValueError("Echtes Spielerbild/Wappen fehlt")
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        if min(image.size)<min_size:
            raise ValueError("Bildauflösung zu gering")
        return image.convert("RGBA")


def _portrait(im, cards, player, team, rect, *, circle=False):
    raw=cards._player_photo(player,team)
    pic=_picture(raw)
    x0,y0,x1,y1=map(int,rect)
    w,h=x1-x0,y1-y0
    pic=ImageOps.fit(pic,(w,h),Image.Resampling.LANCZOS,centering=(.5,.18))
    mask=Image.new("L",(w,h),0)
    dr=ImageDraw.Draw(mask)
    if circle:
        dr.ellipse((0,0,w-1,h-1),fill=255)
    else:
        dr.rounded_rectangle((0,0,w-1,h-1),radius=12,fill=255)
        for yi in range(max(0,h-32),h):
            alpha=int(255*(h-yi)/32)
            dr.line((0,yi,w,yi),fill=alpha)
    im.paste(pic,(x0,y0),mask)


def _crest(im, cards, team, rect):
    raw=cards._badge_bytes(team)
    badge=_picture(raw,min_size=24)
    x0,y0,x1,y1=map(int,rect)
    badge.thumbnail((x1-x0,y1-y0),Image.Resampling.LANCZOS)
    p=(int((x0+x1-badge.width)/2),int((y0+y1-badge.height)/2))
    im.paste(badge,p,badge)


def _kickoff(value):
    stamp=str(value or "").strip()
    if not stamp:
        raise ValueError("Bestätigte Anstosszeit fehlt")
    try:
        dt=datetime.fromisoformat(stamp.replace("Z","+00:00"))
        if not dt.tzinfo:
            raise ValueError("Time zone missing")
        dt=dt.astimezone(ZoneInfo("Europe/Zurich"))
        return dt.strftime("%d.%m.%Y / %H:%M Uhr")
    except (TypeError,ValueError,OverflowError) as e:
        raise ValueError("Ungültige bestätigte Anstosszeit") from e


def _write(io_image):
    out=io.BytesIO()
    io_image.save(out,format="PNG",optimize=True)
    return out.getvalue()


def _builder_canvas(legs):
    # Exact original image, with unused visual rows removed for 2-/4-leg cards.
    n=len(legs)
    if not 2<=n<=6:
        raise ValueError("2–6 Legs nötig für Originalvorlage")
    original=_base(str(BUILDER_IMAGE))
    if n==6:
        # Cached reference is immutable; every tip needs its own pixel buffer.
        # Mutating it leaks the previous player's photo into the next tip.
        return original.copy(),0
    upper_y=405+100*n
    footer_y=1013
    im=Image.new("RGB",(1122,upper_y+1402-footer_y))
    im.paste(original.crop((0,0,1122,upper_y)),(0,0))
    im.paste(original.crop((0,footer_y,1122,1402)),(0,upper_y))
    return im,upper_y-footer_y


def render_builder(pick):
    import netrattler_stats_match_cards as cards
    import netrattler_neon_design as nd
    from netrattler_builder_cards import builder_leg_label
    legs=list(getattr(pick,"legs",None) or [])
    im,shift=_builder_canvas(legs)
    draw=ImageDraw.Draw(im)
    home,away=cards._teams(legs[0].match)
    if not home or not away or len({str(l.match) for l in legs})!=1:
        raise ValueError("Original-Builder-Vorlage erfordert ein eindeutiges Spiel")
    # Original metallic logo and gold ribbon are deliberately untouched.
    for name,rect,txt_rect,center in [
        (home,(132,182,237,296),(262,212,490,269),377),
        (away,(874,182,979,296),(632,212,864,269),748),
    ]:
        _erase(draw,rect,fill="#0B151F",radius=20)
        _crest(im,cards,name,(142 if name==home else 885,195,224 if name==home else 961,283))
        _erase(draw,txt_rect,fill="#07131B")
        _label(draw,name.upper(),center,211,222,size=36,min_size=17)
    _erase(draw,(304,279,851,308),fill="#061D28")
    _label(draw,_kickoff(legs[0].kickoff),562,278,450,size=23,min_size=17)
    _erase(draw,(220,325,636,385),fill="#08131D")
    _label(draw,f"{len(legs)}-LEG BUILDER",423,326,390,size=40,min_size=27)
    from netrattler_neon_design import _builder_quote_display,_stat_series,_form_label,_percent,_number
    title,value,book_quote=_builder_quote_display(pick,legs)
    if book_quote is None:
        raise ValueError("Keine bestätigte Buchmacher-Kombiquote")
    _erase(draw,(710,333,1000,376),fill="#F6C92E",radius=10)
    _label(draw,f"@ {book_quote:.2f}",857,333,260,size=35,min_size=22,fill="#11121B",shadow=False)
    for i,leg in enumerate(legs):
        y=409+100*i
        # Erase baked-in sample photo, club crest, label and statistics before
        # inserting *only* the actual corresponding player's verified data.
        _erase(draw,(94,y-14,258,y+107),fill="#0A1117",radius=17)
        _portrait(im,cards,leg.player,leg.team,(101,y-14,247,y+99))
        _erase(draw,(269,y+1,352,y+83),fill="#071720",radius=18)
        _crest(im,cards,leg.team,(276,y+8,343,y+77))
        _erase(draw,(365,y+1,745,y+96),fill="#07131B",radius=4)
        _label(draw,leg.player.upper(),545,y+3,350,size=30,min_size=17)
        _label(draw,builder_leg_label(leg).upper(),550,y+42,342,size=25,min_size=15,fill=GOLD)
        _erase(draw,(800,y+1,1057,y+94),fill="#07131A",radius=4)
        series=_stat_series(leg,__import__("netrattler_builder_engine"),getattr(pick,"match_date",""))
        if len(series)<15:
            raise ValueError("Für den Spieler fehlt echte L15-Spielhistorie")
        for period,yy in ((5,y+5),(10,y+34),(15,y+63)):
            _label(draw,f"L{period}: {_form_label(series,leg.line,period)}",931,yy,246,size=20,min_size=14,fill=GREEN,italic=False)
    f=shift
    # Footer source locations remain exact, shifted when fewer than six legs.
    y0=1034+f
    probability=_percent(getattr(pick,"joint_probability",None))
    if probability is None:
        probability=_percent(getattr(pick,"probability",None))
    if probability is None:
        raise ValueError("Bestätigte Modellwahrscheinlichkeit fehlt")
    ev=(probability/100*book_quote-1)*100
    conf=str(getattr(pick,"confidence","") or "").upper()
    if not conf or conf=="—":
        raise ValueError("Konfidenz fehlt")
    # Source template keeps neon borders and metric headings; replace values.
    for box,label,center,color in [
        ((167,y0+49,333,y0+121),f"{book_quote:.2f}",251,GOLD),
        ((495,y0+49,645,y0+121),f"{ev:+.1f}%",571,GREEN if ev>=0 else RED),
        ((881,y0+49,1046,y0+121),f"{probability:.1f}%",963,GOLD),
    ]:
        _erase(draw,box,fill="#03120C",radius=11)
        _label(draw,label,center,y0+63,box[2]-box[0]-14,size=45,min_size=26,fill=color)
    status,col=nd._result_text(getattr(pick,"status",None))
    _erase(draw,(362,1206+f,512,1269+f),fill="#FBD331",radius=15)
    _label(draw,conf,437,1220+f,135,size=29,min_size=19,fill="#161514",shadow=False)
    _erase(draw,(847,1198+f,1053,1267+f),fill="#071620",radius=10)
    _label(draw,status,950,1223+f,195,size=27,min_size=18,fill=col)
    return _write(im)


def render_goal(tip,target_date,result=None):
    import netrattler_stats_match_cards as cards
    import netrattler_neon_design as nd
    im=_base(str(GOAL_IMAGE)).copy()
    draw=ImageDraw.Draw(im)
    home,away=cards._teams(tip.get("match"))
    player=str(tip.get("player") or "").strip()
    club=str(tip.get("team") or "").strip()
    if not all((home,away,player,club)):
        raise ValueError("Goal Hunter hat nicht verifizierte Spieler-/Spieldaten")
    # Original artwork header, stadium, metallic logo and ribbon untouched.
    for name,logo_box,label_box,cx,crest_rect in [
        (home,(90,405,274,630),(87,662,347,725),215,(96,430,267,615)),
        (away,(820,405,1019,630),(778,662,1046,725),901,(830,430,1011,615)),
    ]:
        _erase(draw,logo_box,fill="#0A1B27",radius=30)
        _crest(im,cards,name,crest_rect)
        _erase(draw,label_box,fill="#07141B",radius=12)
        _label(draw,name.upper(),cx,668,label_box[2]-label_box[0]-24,size=33,min_size=13)
    _erase(draw,(340,315,770,727),fill="#061623",radius=200)
    _portrait(im,cards,player,club,(340,319,769,720),circle=True)
    # Reapply the golden halo from the master frame rather than replacing logo.
    draw.arc((316,309,780,738),0,360,fill="#FFDA45",width=8)
    _erase(draw,(204,761,901,837),fill="#06131B",radius=12)
    _label(draw,player.upper(),555,772,665,size=54,min_size=27)
    # Compact confirmed Swiss kickoff beneath the player's name. Preserve the
    # user's original stadium, crown, header, panels and player photo.
    kickoff_value = tip.get("_kickoff") or tip.get("kickoff")
    if kickoff_value:
        kickoff_label = "ANSTOSS " + _kickoff(kickoff_value).replace(" / ", " · ")
        draw.rounded_rectangle((335,828,789,860),radius=14,
                               fill="#061723",outline=CYAN,width=2)
        _label(draw,kickoff_label,562,832,440,size=21,min_size=16,
               fill=WHITE,italic=False)
    odds=cards._price(tip)
    probability=cards._pct(tip.get("probability"))
    fair=nd._number(tip.get("fairOdds") if tip.get("fairOdds") is not None else tip.get("fair_odds"))
    if fair is None and probability is not None and probability>0:
        fair=100/probability
    gpg=nd._number(tip.get("goals_per_game"))
    if odds is None or probability is None or fair is None or gpg is None:
        raise ValueError("Goal Hunter: erforderliche Statistik/Quote fehlt")
    fields=[(52,269,f"{odds:.2f}",GOLD),(326,539,f"{probability:.0f}%",GREEN),
            (590,793,f"{fair:.2f}",GOLD),(852,1068,f"{gpg:.2f}",GOLD)]
    for i,(x0,x1,text,color) in enumerate(fields):
        _erase(draw,(x0,953,x1,1023),fill="#03150D",radius=14)
        _label(draw,text,(x0+x1)//2,956,x1-x0-12,size=47,min_size=28,fill=color)
    status=(result.get("marks") or {}).get("0") if isinstance(result,dict) else None
    label,col=nd._result_text(status)
    _erase(draw,(456,1214,647,1283),fill="#07151D",radius=14)
    _label(draw,label,550,1220,182,size=39,min_size=25,fill=col)
    return _write(im)