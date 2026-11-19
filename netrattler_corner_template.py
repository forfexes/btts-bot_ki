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
    badge = ImageOps.contain(img, s, method=Image.Resampling.LANCZOS)
    xx, yy = (x0+(s[0]-badge.width)//2, y0+(s[1]-badge.height)//2)
    im.paste(badge, (xx,yy), badge)


def _gold_bar(im, area):
    draw = ImageDraw.Draw(im)
    x0,y0,x1,y1 = area
    for y in range(y0,y1):
        v = (y-y0)/max(1,y1-y0)
        col = (255, int(223 + 26*(1-abs(2*v-1))), int(48+70*(1-abs(2*v-1))))
        draw.line((x0+7,y,x1-7,y),fill=col,width=1)
    draw.rounded_rectangle(area, radius=26,outline=GOLD,width=4)


def render_corner_template(tip, target_date, result=None):
    """Corner Sniper on the premium SVG master with verified live data only."""
    import netrattler_stats_match_cards as cards
    from netrattler_corner_cards import kickoff_label
    from netrattler_premium_extra import render_corner
    day, clock = kickoff_label(tip, target_date)
    if clock == 'Zeit nicht bestätigt' or not clock:
        raise ValueError('corner_unconfirmed_kickoff')
    return render_corner(tip, cards._badge_bytes, kickoff=f'{day} · {clock} Uhr', result=result)


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
    return sorted(set(reasons))



def review_corner_png(payload):
    """Pixel check of the premium Corner card against its blank SVG master."""
    from PIL import ImageChops
    try:
        import cairosvg
        from netrattler_premium_compact import ASSETS
        with Image.open(io.BytesIO(payload)) as data:
            if data.format != 'PNG' or data.size != (W, H):
                return ['wrong_corner_png_geometry']
            rendered = data.convert('RGB')
        master = Image.open(io.BytesIO(cairosvg.svg2png(
            url=str(ASSETS / 'premium_corner_blank.svg'), output_width=W, output_height=H))).convert('RGB')
        regions = {'home_crest': (164, 242, 396, 360), 'away_crest': (726, 242, 958, 360),
                   'selection_row': (60, 395, 1060, 460), 'corner_panels': (42, 650, 1080, 800),
                   'corner_quote': (150, 1200, 330, 1270)}
        return ['unchanged_placeholder_' + k for k, box in regions.items()
                if ImageChops.difference(rendered.crop(box), master.crop(box)).getbbox() is None]
    except (OSError, ValueError, TypeError, ImportError):
        return ['corner_png_unreadable']
