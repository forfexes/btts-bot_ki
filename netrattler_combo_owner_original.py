"""NETRATTLER COMBO 3–10 legs derived from the actual 7/9 PNG originals.

Always preserve the owner's crown, header and original footer; unused row
space is physically removed, and no synthetic generic design is ever used.
Unconfirmed combo prices are explicitly marked as calculated from leg quotes.
No Telegram or network calls.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import math

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT=Path(__file__).resolve().parent/"assets"/"original_templates"
W,H=1122,1402
NAVY="#071523"
CYAN="#25DFFF"
GOLD="#FFD74D"
WHITE="#F7FBFF"
GREEN="#3FF095"


def _font(size):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:return ImageFont.truetype(path,size)
        except OSError:pass
    return ImageFont.load_default()


def _label(draw, value, x,y,max_width, size=28,color=WHITE):
    name=str(value or "").strip()
    if not name:
        raise ValueError("COMBO original missing verified field")
    while size>=14 and draw.textlength(name,font=_font(size))>max_width:
        size-=1
    if size<14:
        raise ValueError("Original COMBO text exceeds verified card width")
    draw.text((x,y),name,font=_font(size),fill=color,anchor="mm",
              stroke_width=1,stroke_fill="#01040B")


def _photo_crest(data):
    if not isinstance(data,(bytes,bytearray)) or len(data)<100:
        raise ValueError("Echtes Vereins-Wappen fehlt: keine Platzhalter erlaubt")
    try:
        with Image.open(BytesIO(data)) as source:
            source.load()
            if min(source.size)<40:
                raise ValueError("Low-resolution club crest")
            return source.convert("RGBA").copy()
    except OSError as exc:
        raise ValueError("Unreadable club crest") from exc


def _num(value,what,minimum,maximum):
    try:num=float(value)
    except (ValueError,TypeError):raise ValueError("Verified "+what+" missing") from None
    if not math.isfinite(num) or not minimum<=num<=maximum:
        raise ValueError("Verified "+what+" outside allowed range")
    return num


def _owner_canvas(n):
    """Load a verified 7/9 source and crop unused rows, never generate a fallback.

    The header and footer are pixel copies from the real owner reference.
    The middle section is repainted with exactly n selection rows.
    """
    if not 3 <= n <= 10:
        raise ValueError("Original COMBO requires 3–10 legs")
    source_legs = 7 if n <= 7 else 9
    path = ROOT / f"NETRATTLER_COMBO_{source_legs}_originalkarte.png"
    if not path.is_file():
        raise FileNotFoundError(f"Actual COMBO-{source_legs} source is missing")
    with Image.open(path) as original:
        original.load()
        if original.format != "PNG" or min(original.size) < 600:
            raise ValueError("Owner original COMBO source invalid")
        source = original.convert("RGBA").resize((W,H),Image.Resampling.LANCZOS)
    # 10 rows fit within the original nine-row field using a smaller row step.
    if n in (7,9,10):
        return source.copy(), 0
    top, end, footer_start = 304, 1097, 1108
    master_legs = 7 if n < 7 else 9
    desired_height = round((end-top) * n/master_legs)
    shift = desired_height - (end-top)
    canvas = Image.new("RGBA",(W,H+shift),"#04111D")
    canvas.paste(source.crop((0,0,W,280)),(0,0))
    canvas.paste(source.crop((0,footer_start,W,H)),(0,footer_start+shift))
    return canvas, shift


def render_original_combo(legs,*,combined_odds,probability,ev,confidence,
                          stake,combined_odds_observed,combined_quote_id,
                          bookmaker,crest_provider,status="OFFEN"):
    legs=list(legs)
    n=len(legs)
    if not 3 <= n <= 10:
        raise ValueError("Original COMBO requires 3–10 legs")
    verified = (combined_odds_observed is True and
                bool(str(combined_quote_id or "").strip()) and
                bool(str(bookmaker or "").strip()))
    # Without a confirmed ticket price, calculate from the observed legs below.
    quote = (_num(combined_odds, "combined bookmaker quote", 1.01, 100000.0)
             if verified else None)
    prob=_num(probability,"model probability",0.0,100.0)
    ev_num=_num(ev,"expected value",-100.0,100000.0) if verified else None
    wager=_num(stake,"stake",0.001,5.0)
    if not callable(crest_provider):
        raise ValueError("Verified crest provider missing")
    badges={}
    checked=[]
    for i,leg in enumerate(legs,1):
        if not isinstance(leg,dict):
            raise ValueError("Invalid COMBO leg structure")
        home=str(leg.get("home") or "").strip()
        away=str(leg.get("away") or "").strip()
        market=str(leg.get("market") or "").strip()
        if not (home and away and home.casefold()!=away.casefold() and market):
            raise ValueError(f"Leg {i} missing exact fixture/market")
        price=_num(leg.get("odds"),f"Einzelquote Leg {i}",1.01,10000)
        for team in (home,away):
            if team not in badges:
                badges[team]=_photo_crest(crest_provider(team))
        checked.append((home,away,market,price))
    if quote is None:
        quote = math.prod(item[3] for item in checked)
        quote = _num(quote, "calculated combination quote", 1.01, 100000.0)
    im, shift = _owner_canvas(n)
    draw=ImageDraw.Draw(im)
    # Keep the owner's crown, metallic logo, yellow COMBO title and original
    # TIPPS ribbon completely untouched. Hide all baked example fixtures.
    # The owner's uploaded examples begin directly below the TIPPS ribbon.
    # Clear that FIRST sample row too; previously Barcelona/Over-2.5 or
    # Liverpool from the reference was still visible behind the new first leg.
    top=304
    end=1097+shift
    row_step=(end-top)/n
    draw.rounded_rectangle((31,280,1090,end+6),radius=18,
                           fill="#04111D",outline=CYAN,width=4)
    for i,(home,away,market,price) in enumerate(checked):
        y0=top+round(i*row_step)+3
        y1=top+round((i+1)*row_step)-3
        cy=(y0+y1)//2
        draw.rounded_rectangle((39,y0,1083,y1),radius=9,
                               fill=NAVY,outline=CYAN,width=2)
        draw.ellipse((50,cy-19,88,cy+19),
                     fill="#070C17",outline=GOLD,width=2)
        _label(draw,str(i+1),69,cy,36,22,GOLD)
        for j,team in enumerate((home,away)):
            icon=ImageOps.contain(badges[team],(57,57),
                                  method=Image.Resampling.LANCZOS)
            px=108 if j==0 else 193
            im.alpha_composite(icon,(px+(57-icon.width)//2,
                                     cy-icon.height//2))
        _label(draw,home+" VS "+away,479,cy-13,395,26,WHITE)
        _label(draw,market,815,cy+15,303,23,GOLD)
        draw.rounded_rectangle((957,cy-29,1072,cy+29),
                               radius=8,fill="#311D07",
                               outline=GOLD,width=3)
        _label(draw,f"{price:.2f}",1014,cy,105,25,GOLD)
    # Replace EVERY sample figure in the original footer while retaining the
    # original glow outside each data box and the exact @prophunter banner.
    draw.rounded_rectangle((35,1112+shift,1085,1303+shift),radius=16,
                           fill="#03111D",outline=CYAN,width=4)
    columns=(
        (210,"GESAMTQUOTE" if verified else "BERECHNET",f"{quote:.2f}"),
        (561,"MODELL",f"{prob:.1f}%"),
        (909,"EINSATZ",f"{wager:g}u"),
    )
    for cx,title,value in columns:
        draw.rounded_rectangle((cx-159,1121+shift,cx+159,1201+shift),
                               radius=11,fill="#091523",outline=GOLD,width=2)
        _label(draw,title,cx,1143+shift,296,22,WHITE)
        _label(draw,value,cx,1181+shift,296,37,GOLD)
    _label(draw,("EV "+f"{ev_num:+.1f}%") if verified else "QUOTE UNBESTÄTIGT",
           258,1249+shift,345,22 if not verified else 27,
           GREEN if verified and ev_num>=0 else "#FF7777" if verified else WHITE)
    _label(draw,"CONF "+str(confidence).strip().upper(),621,1249+shift,310,24,GOLD)
    state=str(status or "OFFEN").strip().upper()
    if state not in ("OFFEN","GEWONNEN","VERLOREN","VOID","PUSH"):
        raise ValueError("Unverified COMBO settlement state")
    _label(draw,state,968,1249+shift,198,25,GREEN if state=="GEWONNEN" else WHITE)
    buffer=BytesIO()
    im.convert("RGB").save(buffer,"PNG",optimize=True)
    return buffer.getvalue()
