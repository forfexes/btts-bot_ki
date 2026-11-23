"""User-approved 18 Nov 2026 NETRATTLER AI Corner Sniper master template.

Background is the exact supplied artwork, not an approximate generated layout.
All sports statistics shown in production must come from the actual tip.
"""
from __future__ import annotations
import io
import math
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

MASTER = Path(__file__).resolve().parent / 'assets' / 'netrattler_template_corner_original.webp'
W, H = 1122, 1402
WHITE = '#F6F7FC'
CYAN = '#28E8FF'
GOLD = '#FFDB34'
GREEN = '#36F78A'
RED = '#FF6578'
NAVY = '#06121F'


def number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(str(value).replace(',', '.'))
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def first(tip, *names):
    for name in names:
        v = number(tip.get(name))
        if v is not None and v >= 0:
            return v
    return None


def fmt(v, decimals=1):
    return '—' if v is None else (f'{v:.{decimals}f}'.replace('.', ','))


def pct(value):
    n = number(value)
    if n is None:
        return None
    n = 100 * n if 0 <= n <= 1 else n
    return n if 0 <= n <= 100 else None


def _font(size, italic=False):
    for file in (['DejaVuSansCondensed-BoldOblique.ttf', 'DejaVuSansCondensed-Bold.ttf']
                 if italic else ['DejaVuSansCondensed-Bold.ttf', 'DejaVuSans-Bold.ttf']):
        try:
            return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/' + file, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _label(draw, txt, cx, y, width, size=30, color=WHITE, italic=True, minsize=16):
    txt = str(txt or '').strip()
    font = _font(size, italic)
    while size > minsize and draw.textlength(txt, font=font) > width:
        size -= 1
        font = _font(size, italic)
    if draw.textlength(txt, font=font) > width:
        while len(txt) > 2 and draw.textlength(txt + '…', font=font) > width:
            txt = txt[:-1]
        txt += '…'
    draw.text((int(cx - draw.textlength(txt, font=font) / 2), y), txt,
              font=font, fill=color, stroke_width=1, stroke_fill='#070D19')


def _erase(draw, area, color=NAVY, radius=8):
    draw.rounded_rectangle(area, radius=radius, fill=color)


def _badge(im, draw, cards, name, area):
    raw = cards._badge_bytes(name)
    if not raw:
        raise ValueError('missing_verified_crest:' + str(name))
    img = Image.open(io.BytesIO(raw)).convert('RGBA')
    if img.width < 45 or img.height < 45:
        raise ValueError('invalid_verified_crest:' + str(name))
    x0, y0, x1, y1 = area
    s = (x1-x0, y1-y0)
    visible=img.getchannel("A").point(
        lambda alpha:255 if alpha>=24 else 0).getbbox()
    if visible is None:
        raise ValueError('Real Corner Sniper crest has no visible pixels')
    img=img.crop(visible)
    if min(img.size)<12:
        raise ValueError('Corner Sniper emblem artwork is too small')
    scale=min(s[0]/img.width,s[1]/img.height)
    if scale>4:
        raise ValueError('Corner Sniper emblem resolution too low')
    badge=img.resize((max(1,round(img.width*scale)),
                      max(1,round(img.height*scale))),
                     Image.Resampling.LANCZOS)
    xx, yy = (x0+(s[0]-badge.width)//2, y0+(s[1]-badge.height)//2)
    im.paste(badge, (xx,yy), badge.getchannel("A"))


def _gold_bar(im, area):
    draw = ImageDraw.Draw(im)
    x0,y0,x1,y1 = area
    for y in range(y0,y1):
        v = (y-y0)/max(1,y1-y0)
        col = (255, int(223 + 26*(1-abs(2*v-1))), int(48+70*(1-abs(2*v-1))))
        draw.line((x0+7,y,x1-7,y),fill=col,width=1)
    draw.rounded_rectangle(area, radius=26,outline=GOLD,width=4)


def render_corner_template(tip, target_date, result=None):
    """Offline QA only until an independently clean Corner owner plate exists."""
    # The old Corner screenshot still has baked sample figures and badges.
    # Refuse ANY production image overlay; only explicitly isolated sandbox
    # previews may call this compositor. Never replace old Telegram cards
    # with a partially covered screenshot.
    if os.getenv("NETRATTLER_BLOCK_OVERPAINTED_MASTERS", "1") != "0":
        raise ValueError("corner_original_overpainted_compositor_blocked")
    import netrattler_stats_match_cards as cards
    from netrattler_corner_cards import kickoff_label
    if not MASTER.is_file():
        raise FileNotFoundError('corner_master_missing')
    im = Image.open(MASTER).convert('RGB')
    if im.size != (W,H):
        raise ValueError('corner_master_wrong_size')
    draw=ImageDraw.Draw(im)
    home,away = cards._teams(tip.get('match',''))
    if not home or not away:
        raise ValueError('corner_fixture_missing')
    # Keep the approved stadium artwork, crown, gold title and cyan panel borders.
    # Strip all placeholder team names/logos before placing verified identities.
    _erase(draw,(91,204,495,321), '#081019')
    _erase(draw,(637,204,1026,321), '#081019')
    _erase(draw,(138,190,213,204),'#081019')
    _erase(draw,(107,319,215,327),'#081019')
    _badge(im, draw, cards, home, (106,214,210,300))
    _erase(draw,(915,190,1009,204),'#081019')
    _erase(draw,(917,319,1009,327),'#081019')
    _badge(im, draw, cards, away, (911,214,1014,300))
    _label(draw,home.upper(),355,242,270,36)
    _label(draw,away.upper(),769,242,254,36)
    day,clock=kickoff_label(tip,target_date)
    if clock == 'Zeit nicht bestätigt' or not clock:
        raise ValueError('corner_unconfirmed_kickoff')
    _erase(draw,(150,329,394,390),'#07131C')
    _erase(draw,(489,329,741,386),'#07131C')
    _erase(draw,(823,329,1007,388),'#07131C')
    league=str(tip.get('league') or '').strip()
    if league:
        _label(draw,league,270,340,240,25)
    _label(draw,day,610,344,255,27)
    _label(draw,clock+' Uhr',921,344,173,27)
    # The three inset statistic panels retain the original glowing outlines.
    for box in ((63,431,380,624),(425,431,694,624),(728,431,1040,624)):
        _erase(draw,box,'#020B12',15)
    home_l10=first(tip,'home_corners_l10','home_l10_corners','home_avg_corners_l10','home_corners_l10_avg')
    home_l15=first(tip,'home_corners_l15','home_l15_corners','home_avg_corners_l15','home_corners_l15_avg')
    away_l10=first(tip,'away_corners_l10','away_l10_corners','away_avg_corners_l10','away_corners_l10_avg')
    away_l15=first(tip,'away_corners_l15','away_l15_corners','away_avg_corners_l15','away_corners_l15_avg')
    _label(draw,home.upper(),222,439,302,27)
    _label(draw,away.upper(),886,439,301,27)
    _label(draw,'ECKEN · Ø',222,477,300,24,GOLD)
    _label(draw,'ECKEN · Ø',886,477,300,24,GOLD)
    for cx,a,b in ((222,home_l10,home_l15),(886,away_l10,away_l15)):
        _label(draw,'L10: '+fmt(a),cx,529,265,29,GREEN)
        _label(draw,'L15: '+fmt(b),cx,582,265,29,GREEN)
    _label(draw,'H2H · ECKEN',560,439,261,26)
    n=first(tip,'h2h_matches')
    havg=first(tip,'h2h_avg_corners')
    _label(draw,('Spiele: '+fmt(n,0)) if n is not None else 'Spiele: —',560,510,245,26,WHITE)
    _label(draw,'Ø Ecken: '+fmt(havg),560,563,244,25,GOLD)
    # Central summary strip with real expectations and form only.
    for box in ((218,658,478,812),(490,658,769,812),(777,658,1059,812)):
        _erase(draw,box,'#05101A',9)
    expected=first(tip,'expected_corners')
    hv=first(tip,'home_avg_corners')
    av=first(tip,'away_avg_corners')
    _label(draw,'Ø GESAMT-ECKEN',345,683,241,24)
    _label(draw,fmt(expected),345,738,245,47,GOLD)
    _label(draw,'BEIDE TEAMS',624,683,259,24)
    _label(draw,'Ø '+fmt(hv)+' / '+fmt(av),624,737,267,35,GOLD)
    market=str(tip.get('tip') or tip.get('selection') or 'Ecken').strip()
    _label(draw,'TREFFERQUOTE',910,683,252,24)
    _label(draw,'L10: '+str(tip.get('corner_hits_l10') or '—'),912,724,250,24,GREEN)
    _label(draw,'L15: '+str(tip.get('corner_hits_l15') or '—'),912,763,250,24,GREEN)
    _gold_bar(im,(406,864,1043,944))
    draw=ImageDraw.Draw(im)
    _label(draw,market,727,884,592,45,'#080E13')
    # Quote, probability and EV must be internally consistent. Never infer a quote.
    quote=cards._price(tip)
    prob=pct(tip.get('probability'))
    ev=((quote*prob/100)-1)*100 if quote is not None and prob is not None else None
    for box in ((80,993,345,1154),(377,993,740,1154),(762,993,1058,1154)):
        _erase(draw,box,'#071520',12)
    _label(draw,'QUOTE',211,1013,246,24)
    _label(draw,fmt(quote,2),211,1060,231,60,GOLD)
    _label(draw,'WAHRSCHEINLICHKEIT',554,1013,332,21)
    _label(draw,fmt(prob,0)+'%' if prob is not None else '—',554,1064,314,58,GREEN)
    _label(draw,'EV',903,1013,270,24)
    _label(draw,(f'{ev:+.1f}%'.replace('.',',')) if ev is not None else '—',903,1064,277,51,GREEN if ev is not None and ev>=0 else RED)
    conf=str(tip.get('confidence') or '').strip().upper()
    if not conf:
        conf='—'
    _erase(draw,(119,1202,521,1280),'#09101B')
    _label(draw,'KONFIDENZ: '+conf,330,1222,355,29,GOLD)
    res=result if isinstance(result,dict) else {}
    status=str((res.get('marks') or {}).get('0') or res.get('status') or 'pending').lower()
    label,col={'win':('GEWONNEN',GREEN),'loss':('VERLOREN',RED),'void':('VOID',GOLD)}.get(status,('OFFEN',GOLD))
    _erase(draw,(633,1202,1056,1280),'#091321')
    _label(draw,'AUSWERTUNG: '+label,870,1222,349,30,col)
    # User-approved NETRATTLER AI branding in the lower unused turf area.
    _label(draw,'NETRATTLER AI',562,1321,625,33,WHITE)
    _label(draw,'@netrattler',562,1366,625,20,CYAN)
    out=io.BytesIO();im.save(out,'PNG',optimize=True);return out.getvalue()


def validate_corner(tip, target_date, cards):
    """Fail closed for missing identifiers, verified prices or corner inputs."""
    from netrattler_corner_cards import kickoff_label
    reasons=[]
    if not cards._valid(tip):
        reasons.append('missing_real_bookmaker_quote')
    home,away=cards._teams(tip.get('match',''))
    if not home or not away:
        reasons.append('invalid_fixture')
    day,clock=kickoff_label(tip,target_date)
    if clock == 'Zeit nicht bestätigt' or not clock:
        reasons.append('missing_confirmed_kickoff')
    if pct(tip.get('probability')) is None:
        reasons.append('missing_probability')
    if first(tip,'expected_corners') is None:
        reasons.append('missing_expected_corners')
    if first(tip,'home_corners_l10','home_l10_corners','home_avg_corners_l10','home_corners_l10_avg') is None:
        reasons.append('missing_home_l10')
    if first(tip,'away_corners_l10','away_l10_corners','away_avg_corners_l10','away_corners_l10_avg') is None:
        reasons.append('missing_away_l10')
    if first(tip,'home_corners_l15','home_l15_corners','home_avg_corners_l15','home_corners_l15_avg') is None:
        reasons.append('missing_home_l15')
    if first(tip,'away_corners_l15','away_l15_corners','away_avg_corners_l15','away_corners_l15_avg') is None:
        reasons.append('missing_away_l15')
    for field in ('corner_hits_l10','corner_hits_l15','confidence'):
        if not str(tip.get(field) or '').strip():
            reasons.append('missing_' + field)
    for field in ('home_avg_corners','away_avg_corners'):
        if first(tip,field) is None:
            reasons.append('missing_' + field)
    if not str(tip.get('tip') or tip.get('selection') or '').strip():
        reasons.append('missing_corner_selection')
    if first(tip,'h2h_matches') is None:
        reasons.append('missing_h2h_matches')
    if first(tip,'h2h_avg_corners') is None:
        reasons.append('missing_h2h_corner_avg')
    for team in (home,away):
        raw=cards._badge_bytes(team) if team else b''
        try:
            if not raw or Image.open(io.BytesIO(raw)).width < 45:
                reasons.append('missing_verified_crest')
        except (OSError,ValueError):
            reasons.append('invalid_verified_crest')
    if not MASTER.is_file():
        reasons.append('missing_original_corner_asset')
    return sorted(set(reasons))



def review_corner_png(payload):
    """Pixel-level check of actual image against original; no mere data-only test."""
    from PIL import ImageChops
    try:
        with Image.open(io.BytesIO(payload)) as data:
            if data.format != 'PNG' or data.size != (W,H):
                return ['wrong_corner_png_geometry']
            rendered=data.convert('RGB')
        original=Image.open(MASTER).convert('RGB')
        regions={'home_team':(222,238,477,295),
                 'away_team':(648,238,904,295),
                 'corner_history':(120,513,365,614),
                 'corner_h2h':(449,495,683,617),
                 'corner_quote':(116,1030,324,1137),
                 'corner_probability':(435,1030,686,1137),
                 'corner_settlement':(710,1218,1037,1276),
                 'netrattler_ai_brand':(395,1315,745,1360)}
        missing=[]
        for label,rect in regions.items():
            diff=ImageChops.difference(rendered.crop(rect),original.crop(rect))
            if diff.getbbox() is None:
                missing.append('unchanged_placeholder_'+label)
        return missing
    except (OSError,ValueError,TypeError):
        return ['invalid_corner_png']