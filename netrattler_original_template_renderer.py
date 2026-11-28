"""Render NETRATTLER cards on the actual user-supplied reference artwork.

Original WebP sources remain immutable; verified match, player and price data
are overlaid for card rendering. This module never sends Telegram messages.
"""
from __future__ import annotations

import io
import math
import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ASSETS = Path(__file__).resolve().parent / "assets"
BUILDER_IMAGE = ASSETS / "original_templates" / "prop_builder_original.webp"
GOAL_IMAGE = ASSETS / "original_templates" / "goal_hunter_original.webp"
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
    """Insert a single genuine club crest into its existing owner-art slot.

    Strip the external file's transparent padding BEFORE fitting; otherwise
    tiny crests drift within the original circle and appear stuck on top.
    No decorative disk, overpainted old logo, or placeholder is generated.
    """
    raw=cards._badge_bytes(team)
    badge=_picture(raw,min_size=24)
    x0,y0,x1,y1=map(int,rect)
    w,h=x1-x0,y1-y0
    if w<=0 or h<=0 or im.mode not in ("RGB", "RGBA"):
        raise ValueError("Invalid original club crest slot")
    visible=badge.getchannel("A").point(
        lambda alpha: 255 if alpha>=24 else 0).getbbox()
    if visible is None:
        raise ValueError("Club crest has no visible pixels")
    badge=badge.crop(visible)
    if min(badge.size)<12:
        raise ValueError("Club crest artwork too small")
    # Fit the visible authentic crest to the original slot in both
    # directions. thumbnail() would leave small provider artwork tiny.
    scale=min(w/badge.width,h/badge.height)
    if scale>4:
        raise ValueError("Club crest artwork too low-resolution for premium slot")
    dims=(max(1,round(badge.width*scale)),
          max(1,round(badge.height*scale)))
    badge=badge.resize(dims,Image.Resampling.LANCZOS)
    p=(round((x0+x1-badge.width)/2),
       round((y0+y1-badge.height)/2))
    if im.mode == "RGBA":
        im.alpha_composite(badge,p)
    else:
        # The owner's original WEBP production artwork is RGB. Blend the
        # authentic transparent crest once; never force a new background.
        im.paste(badge,p,badge.getchannel("A"))


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
    """Derive 2–7 leg layouts only from the uploaded six-row owner WebP.

    For 7 legs, repeat the original sixth row's *artwork*, then overwrite its
    player, club and statistics with the seventh verified selection. The
    owner's crown, header and footer stay untouched and move by exactly 100px.
    """
    n = len(legs)
    if not 2 <= n <= 7:
        raise ValueError("Original Builder requires 2–7 Legs (verified)")
    source = _base(str(BUILDER_IMAGE))
    row_start, six_rows_end = 409, 1009
    shift = 100 * (n - 6)
    if n == 6:
        return source.copy(), shift
    canvas = Image.new("RGB", (1122, 1402 + shift))
    canvas.paste(source.crop((0, 0, 1122, row_start)), (0, 0))
    retained = min(n, 6)
    canvas.paste(source.crop((0, row_start, 1122,
                              row_start + retained * 100)), (0, row_start))
    if n == 7:
        canvas.paste(source.crop((0, six_rows_end - 100, 1122, six_rows_end)),
                     (0, six_rows_end))
    canvas.paste(source.crop((0, six_rows_end, 1122, 1402)),
                 (0, row_start + n * 100))
    return canvas, shift


def _render_builder_legacy(pick):
    if os.getenv("NETRATTLER_BLOCK_OVERPAINTED_MASTERS", "1") != "0":
        raise ValueError("Original Builder has no approved overlay-free clean source")
    import netrattler_stats_match_cards as cards
    import netrattler_neon_design as nd
    from netrattler_builder_cards import builder_leg_label
    legs=list(getattr(pick,"legs",None) or [])
    if not 2 <= len(legs) <= 7:
        raise ValueError("Original Builder requires 2–7 Legs (verified)")
    # Reject cross-fixture and missing fixtures before quote or image lookup.
    home,away=cards._teams(legs[0].match)
    if not home or not away or len({str(l.match) for l in legs})!=1:
        raise ValueError("Original-Builder-Vorlage erfordert ein eindeutiges Spiel")
    # Preflight bookmaker combined price BEFORE any image/network lookup. The
    # price may not be substituted by a product of single-leg odds.
    from netrattler_neon_design import _builder_quote_display,_stat_series,_form_label,_percent,_number
    title,value,book_quote=_builder_quote_display(pick,legs)
    if book_quote is None:
        raise ValueError("Keine bestätigte Buchmacher-Kombiquote; Formelprodukt darf nicht als Wettquote erscheinen")
    im,shift=_builder_canvas(legs)
    draw=ImageDraw.Draw(im)
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
    shown = f"@ {book_quote:.2f}"
    _erase(draw,(710,333,1000,376),fill="#F6C92E",radius=10)
    _label(draw,shown,857,333,275,size=35,
           min_size=15,fill="#11121B",shadow=False)
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
    # The REAL owner artwork already prints "GESAMTQUOTE", "EV",
    # "WAHRSCHEINLICHKEIT", "KONFIDENZ" and "AUSWERTUNG".
    # Populate their existing value boxes only. Never draw duplicate headings
    # over the lower status row (observed in the synthetic 2/4/6-leg QA PNGs).
    probability=_percent(getattr(pick,"joint_probability",None))
    if probability is None:
        probability=_percent(getattr(pick,"probability",None))
    if probability is None:
        raise ValueError("Bestätigte Modellwahrscheinlichkeit fehlt")
    # EV may only use the bookmaker-confirmed combined price.
    ev=(probability/100*book_quote-1)*100
    quote_text=f"{book_quote:.2f}"
    conf=str(getattr(pick,"confidence","") or "").upper()
    if not conf or conf=="—":
        raise ValueError("Konfidenz fehlt")
    status,col=nd._result_text(getattr(pick,"status",None))
    for cx,value,color in (
        (235,quote_text,GOLD),
        (561,f"{ev:+.1f}%" if ev is not None else "—",
         GREEN if ev is not None and ev>=0 else RED if ev is not None else WHITE),
        (885,f"{probability:.1f}%",GOLD),
    ):
        # Clear demo dash INSIDE the existing neon value cell; keep its frame.
        _erase(draw,(cx-124,1100+shift,cx+124,1164+shift),
               fill="#06131B",radius=10)
        _label(draw,value,cx,1107+shift,232,size=41,min_size=24,
               fill=color,italic=False)
    # The bottom footer is a separate row ~1200px below the original header.
    # Right-hand results must NOT collide with the three metric value boxes.
    _erase(draw,(385,1230+shift,503,1285+shift),fill="#07131B",radius=9)
    _label(draw,conf,445,1240+shift,113,size=25,min_size=16,
           fill=WHITE,italic=False)
    _erase(draw,(863,1230+shift,1055,1285+shift),fill="#07131B",radius=9)
    _label(draw,status,957,1240+shift,183,size=28,min_size=17,
           fill=col,italic=False)
    return _write(im)



def _goal_arena(im):
    """Reconstruct only the baked sample matchup band for offline review.

    The source is flattened, so the hidden stadium pixels cannot be recovered.
    Use actual unobstructed edge artwork, not the old face or golden halo.
    """
    top, bottom = 310, 755
    size = (im.width, bottom-top)
    left = im.crop((0,top,50,bottom)).resize(size,Image.Resampling.BICUBIC)
    right = im.crop((im.width-50,top,im.width,bottom)).resize(size,Image.Resampling.BICUBIC)
    arena = Image.blend(left,right,.5).filter(ImageFilter.GaussianBlur(8))
    arena = Image.blend(arena,Image.new("RGB",size,"#061623"),.40)
    im.paste(arena,(0,top))


def render_builder(pick):
    """Prop Builder on the master background. Real data only; fails closed."""
    import netrattler_stats_match_cards as cards
    import netrattler_neon_design as nd
    import netrattler_master_cards as M
    from netrattler_builder_cards import builder_leg_label
    from netrattler_neon_design import _stat_series, _number
    legs = list(getattr(pick, "legs", None) or [])
    if not 2 <= len(legs) <= 6:
        raise ValueError("Builder requires 2-6 verified legs")
    if len({str(l.match) for l in legs}) != 1:
        raise ValueError("Builder card needs exactly one fixture")
    home, away = cards._teams(legs[0].match)
    if not home or not away:
        raise ValueError("Two verified club names required")
    rows = []
    for leg in legs:
        series = _stat_series(leg, __import__("netrattler_builder_engine"), getattr(pick, "match_date", ""))
        if len(series) < 15:
            raise ValueError("Real L15 history missing for " + str(leg.player))
        need = math.ceil(_number(leg.line))
        hits = [(f"L{n}", sum(x >= need for x in series[:n]), n) for n in (5, 10, 15)]
        rows.append(dict(player=leg.player, market=builder_leg_label(leg), odds=leg.odds,
                         photo=cards._player_photo(leg.player, leg.team),
                         crest=cards._badge_bytes(leg.team), hits=hits))
    prob = nd._percent(getattr(pick, "joint_probability", None))
    if prob is not None:
        rows[0]["combined_prob"] = prob
    from netrattler_corner_cards import kickoff_label
    day, clock = kickoff_label({"_kickoff": legs[0].kickoff}, getattr(pick, "match_date", ""))
    status, _col = nd._result_text(getattr(pick, "status", None))
    return M.render_builder(rows, home, away, cards._badge_bytes(home), cards._badge_bytes(away),
                            kickoff=f"{day} · {clock}", league=getattr(legs[0], "league", None),
                            result=status if status in ("GEWONNEN", "VERLOREN", "VOID") else None)


def _floating_goal_photo(im, cards, player, team, rect):
    pic = _picture(cards._player_photo(player,team))
    alpha = pic.getchannel("A")
    if alpha.getextrema()[0] == 255:
        raise ValueError("Goal Hunter requires genuine transparent player cutout")
    bbox = alpha.point(lambda v: 255 if v >= 24 else 0).getbbox()
    if bbox is None:
        raise ValueError("Goal Hunter player photo has no visible artwork")
    pic = pic.crop(bbox)
    if min(pic.size)<60:
        raise ValueError("Goal Hunter cutout resolution too low")
    x0,y0,x1,y1 = rect
    scale = min((x1-x0)/pic.width,(y1-y0)/pic.height)
    if scale>4:
        raise ValueError("Goal Hunter cutout resolution too low")
    pic = pic.resize((round(pic.width*scale),round(pic.height*scale)),
                     Image.Resampling.LANCZOS)
    im.paste(pic,((x0+x1-pic.width)//2,y1-pic.height),pic.getchannel("A"))


def render_goal(tip,target_date,result=None):
    if os.getenv("NETRATTLER_BLOCK_OVERPAINTED_MASTERS", "1") != "0":
        raise ValueError("Original Goal Hunter has no approved overlay-free clean source")
    import netrattler_stats_match_cards as cards
    import netrattler_neon_design as nd
    im=_base(str(GOAL_IMAGE)).copy()
    draw=ImageDraw.Draw(im)
    home,away=cards._teams(tip.get("match"))
    player=str(tip.get("player") or "").strip()
    club=str(tip.get("team") or "").strip()
    if not all((home,away,player,club)):
        raise ValueError("Goal Hunter hat nicht verifizierte Spieler-/Spieldaten")
    # The header, category ribbon and lower stats are still the original.
    # Reconstruct the baked face/crest/halo band, then float real cutouts.
    _goal_arena(im)
    _floating_goal_photo(im,cards,player,club,(326,315,796,697))
    for name,label_box,cx,crest_rect in [
        (home,(48,655,348,725),198,(83,410,285,625)),
        (away,(774,655,1074,725),924,(837,410,1039,625)),
    ]:
        _crest(im,cards,name,crest_rect)
        draw.rounded_rectangle(label_box,radius=12,fill="#07141B",
                               outline=CYAN,width=3)
        _label(draw,name.upper(),cx,668,label_box[2]-label_box[0]-24,size=33,min_size=13)
    _label(draw,"VS",561,711,100,size=32,min_size=25,fill=GOLD)
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
        # Only cover the original value area INSIDE the neon outline.
        _erase(draw,(x0+15,985,x1-15,1037),fill="#03150D",radius=5)
        _label(draw,text,(x0+x1)//2,984,x1-x0-34,size=43,min_size=24,fill=color)
    status=(result.get("marks") or {}).get("0") if isinstance(result,dict) else None
    label,col=nd._result_text(status)
    # Keep both original frame strokes untouched. The result text sits
    # on the same baseline as AUSWERTUNG, not above the gold border.
    draw.rectangle((465,1239,640,1299),fill="#060A0C")
    _label(draw,label,548,1243,156,size=36,min_size=21,fill=col)
    # Preserve the original Telegram plane and cyan frame; change ONLY
    # the old handle text inside the right footer.
    draw.rectangle((827,1242,1081,1294),fill="#06131B")
    _label(draw,"@prophunter",954,1249,244,size=30,min_size=22,fill=WHITE)
    return _write(im)