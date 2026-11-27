"""NETRATTLER cards on the owner's master background (assets/netrattler_master_background.png).

The master contains only the stadium, the crown and the NETRATTLER AI logo.
All panels are drawn on top of it in the established neon style. Everything on a
card is real input: no sample values, no placeholders, no estimated odds.
Missing crest / photo / odds / probability => ValueError (fail closed, nothing is sent).
This module never talks to Telegram.  `@prophunter` is NOT drawn into the image
(owner rule: it belongs to the Telegram text under the tip).
"""
from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

MASTER = Path(__file__).resolve().parent / "assets" / "netrattler_master_background.png"
W, H = 1122, 1402
CYAN, GOLD, GREEN = (37, 223, 255), (255, 216, 71), (60, 246, 142)
RED, WHITE, NAVY = (255, 105, 105), (246, 252, 255), (4, 13, 24)
_FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-BoldOblique.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


@lru_cache(maxsize=64)
def _font(size: int):
    for path in _FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    raise ValueError("No bold font available")


# ---------------------------------------------------------------- primitives
def _master() -> Image.Image:
    if not MASTER.is_file():
        raise ValueError("NETRATTLER master background missing")
    with Image.open(MASTER) as src:
        if src.size != (W, H):
            raise ValueError("Master background has wrong size")
        return src.convert("RGBA")


def _need(value, name):
    if value is None or str(value).strip() == "":
        raise ValueError(f"Verified value missing: {name}")
    return value


def _odds(value, name="odds"):
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Verified bookmaker {name} missing") from None
    if not 1.01 <= v <= 1000.0:
        raise ValueError(f"Bookmaker {name} out of range")
    return v


def _pct(value, name="probability"):
    try:
        v = float(str(value).replace("%", ""))
    except (TypeError, ValueError):
        raise ValueError(f"Verified {name} missing") from None
    if v <= 1.0:
        v *= 100.0
    if not 0.0 < v <= 100.0:
        raise ValueError(f"{name} out of range")
    return v


def _text(d, xy, value, width, size=34, fill=WHITE, anchor="mm", min_size=13):
    value = str(value).strip()
    if not value:
        raise ValueError("Empty text on card")
    n = size
    while n >= min_size and d.textlength(value, font=_font(n)) > width:
        n -= 1
    if n < min_size:
        raise ValueError("Text too long for slot: " + value[:50])
    d.text(xy, value, font=_font(n), fill=fill, anchor=anchor, stroke_width=1, stroke_fill=(2, 8, 12))


def _glow(im, box, edge=CYAN, radius=26, alpha=214, width=4, glow=13):
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=radius, outline=edge + (255,), width=9)
    im.alpha_composite(layer.filter(ImageFilter.GaussianBlur(glow)))
    body = Image.new("RGBA", im.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(body)
    bd.rounded_rectangle(box, radius=radius, fill=NAVY + (alpha,))
    im.alpha_composite(body)
    ImageDraw.Draw(im).rounded_rectangle(box, radius=radius, outline=edge, width=width)


def _slant_pts(box, skew):
    x0, y0, x1, y1 = box
    return [(x0 + skew, y0), (x1, y0), (x1 - skew, y1), (x0, y1)]


def _gold(im, box, radius=22, skew=0):
    x0, y0, x1, y1 = box
    grad = Image.new("RGBA", (x1 - x0, y1 - y0))
    gd = ImageDraw.Draw(grad)
    for y in range(y1 - y0):
        t = y / max(1, y1 - y0 - 1)
        gd.line((0, y, x1 - x0, y), fill=(255, int(232 - 78 * t), int(96 - 70 * t), 255))
    mask = Image.new("L", grad.size, 0)
    halo = Image.new("RGBA", im.size, (0, 0, 0, 0))
    if skew:
        ImageDraw.Draw(mask).polygon(_slant_pts((0, 0, grad.width - 1, grad.height - 1), skew), fill=255)
        ImageDraw.Draw(halo).polygon(_slant_pts(box, skew), outline=GOLD + (255,), width=9)
    else:
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, grad.width - 1, grad.height - 1), radius=radius, fill=255)
        ImageDraw.Draw(halo).rounded_rectangle(box, radius=radius, outline=GOLD + (255,), width=9)
    im.alpha_composite(halo.filter(ImageFilter.GaussianBlur(10)))
    im.paste(grad, (x0, y0), mask)
    if skew:
        ImageDraw.Draw(im).polygon(_slant_pts(box, skew), outline=(255, 244, 170), width=2)
    else:
        ImageDraw.Draw(im).rounded_rectangle(box, radius=radius, outline=(255, 244, 170), width=2)


def _image(value, name):
    if isinstance(value, (bytes, bytearray)):
        with Image.open(io.BytesIO(value)) as src:
            return src.convert("RGBA")
    if isinstance(value, Image.Image):
        return value.convert("RGBA")
    raise ValueError(f"Real {name} missing: no placeholders allowed")


def _crest(im, img, center, size):
    crest = _image(img, "team crest")
    box = crest.getchannel("A").point(lambda a: 255 if a >= 24 else 0).getbbox()
    if box is None:
        raise ValueError("Team crest contains no visible artwork")
    crest = crest.crop(box)
    if min(crest.size) < 24:
        raise ValueError("Team crest too small")
    f = min(size / crest.width, size / crest.height)
    if f > 4:
        raise ValueError("Team crest resolution too low")
    crest = crest.resize((max(1, round(crest.width * f)), max(1, round(crest.height * f))), Image.Resampling.LANCZOS)
    im.alpha_composite(crest, (round(center[0] - crest.width / 2), round(center[1] - crest.height / 2)))


def _photo(im, img, center, diameter, ring=GOLD):
    photo = _image(img, "player photo")
    if min(photo.size) < 80:
        raise ValueError("Player photo too small")
    s = min(photo.size)
    photo = photo.crop(((photo.width - s) // 2, 0, (photo.width - s) // 2 + s, s)).resize((diameter, diameter), Image.Resampling.LANCZOS)
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter - 1, diameter - 1), fill=255)
    cx, cy = center
    halo = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse((cx - diameter // 2 - 4, cy - diameter // 2 - 4, cx + diameter // 2 + 4, cy + diameter // 2 + 4), outline=ring + (255,), width=10)
    im.alpha_composite(halo.filter(ImageFilter.GaussianBlur(9)))
    im.paste(photo, (cx - diameter // 2, cy - diameter // 2), mask)
    ImageDraw.Draw(im).ellipse((cx - diameter // 2 - 3, cy - diameter // 2 - 3, cx + diameter // 2 + 3, cy + diameter // 2 + 3), outline=ring, width=4)


# ---------------------------------------------------------------- shared blocks
def _head(im, title, subtitle=None):
    d = ImageDraw.Draw(im)
    _gold(im, (221, 262, 901, 338), 26, skew=40)
    _text(d, (561, 300), title.upper(), 560, 46, (14, 10, 0))
    if subtitle:
        _text(d, (561, 366), subtitle.upper(), 700, 26, WHITE)


def _ribbon(im, yc, left=(110, 10, 20), right=(10, 40, 120)):
    box = (45, yc - 52, 1077, yc + 52)
    for part, col, edge in ((0, left, (255, 80, 80)), (1, right, (70, 140, 255))):
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        mid = 561
        pts = ([(box[0] + 40, box[1]), (mid + 20, box[1]), (mid - 20, box[3]), (box[0], box[3])] if part == 0
               else [(mid + 20, box[1]), (box[2], box[1]), (box[2] - 40, box[3]), (mid - 20, box[3])])
        ld.polygon(pts, fill=col + (205,))
        im.alpha_composite(layer)
        glow = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(glow).polygon(pts, outline=edge + (255,), width=7)
        im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(9)))
        ImageDraw.Draw(im).polygon(pts, outline=edge, width=3)


def _versus(im, home, away, home_img, away_img, yc=450, league=None, kickoff=None, crest=124):
    """Team ribbon (red | blue) with crests on both ends, names, VS pill, info strip."""
    _ribbon(im, yc)
    d = ImageDraw.Draw(im)
    _crest(im, home_img, (118, yc), crest)
    _crest(im, away_img, (1004, yc), crest)
    _text(d, (355, yc), home.upper(), 300, 34)
    _text(d, (767, yc), away.upper(), 300, 34)
    _glow(im, (508, yc - 30, 614, yc + 30), GOLD, 18, 235, 3)
    _text(d, (561, yc), "VS", 80, 34, GOLD)
    info = "   |   ".join(x for x in (league, kickoff) if x)
    if info:
        _glow(im, (170, yc + 66, 952, yc + 114), CYAN, 22, 220, 3)
        _text(d, (561, yc + 90), info, 740, 26)


def _cells(im, y, cells, h=132):
    cells = [(str(_need(a, "label")), str(_need(b, "value"))) for a, b in cells]
    if not 1 <= len(cells) <= 4:
        raise ValueError("1-4 stat cells supported")
    _glow(im, (45, y, 1077, y + h), CYAN, 24)
    d = ImageDraw.Draw(im)
    step = 1032 / len(cells)
    for i, (label, value) in enumerate(cells):
        cx = int(45 + step * (i + .5))
        _text(d, (cx, y + 36), label, int(step) - 26, 24, CYAN)
        _text(d, (cx, y + 88), value, int(step) - 26, 46, GOLD)
        if i:
            d.line((int(45 + step * i), y + 18, int(45 + step * i), y + h - 18), fill=CYAN, width=2)


def _tip(im, y, tip, h=104):
    """TIPP label + slanted gold pill with the pick (like the Corner Sniper original)."""
    d = ImageDraw.Draw(im)
    _glow(im, (45, y, 330, y + h), CYAN, 28)
    _text(d, (188, y + h // 2), "TIPP", 200, 50)
    _gold(im, (292, y, 1077, y + h), 26, skew=44)
    _text(d, (700, y + h // 2), _need(tip, "tip"), 700, 48, (14, 10, 0))


def _trio(im, y, odds, prob, h=118):
    o, p = _odds(odds), _pct(prob)
    ev = (p / 100 * o - 1) * 100
    d = ImageDraw.Draw(im)
    boxes = ((45, 372), (388, 730), (746, 1077))
    items = (("QUOTE", f"{o:.2f}", GOLD), ("WAHRSCHEINLICHKEIT", f"{p:.0f}%", GREEN),
             ("EV", f"{ev:+.1f}%", GREEN if ev >= 0 else RED))
    for (x0, x1), (label, value, col) in zip(boxes, items):
        _glow(im, (x0, y, x1, y + h), CYAN if label != "QUOTE" else GOLD, 26)
        cx = (x0 + x1) // 2
        _text(d, (cx, y + round(h * .27)), label, x1 - x0 - 24, 22, CYAN)
        _text(d, (cx, y + round(h * .68)), value, x1 - x0 - 30, 50 if h >= 110 else 42, col)


def _foot(im, y, conf=None, result="OFFEN"):
    d = ImageDraw.Draw(im)
    _glow(im, (45, y, 560, y + 76), GOLD, 22, width=3)
    if conf is None:
        _text(d, (302, y + 38), "KONFIDENZ  —", 420, 28)
    else:
        c = int(conf)
        if not 1 <= c <= 5:
            raise ValueError("confidence 1-5")
        _text(d, (175, y + 38), "KONFIDENZ", 200, 26)
        for i in range(5):
            x = 330 + i * 46
            d.rounded_rectangle((x, y + 24, x + 38, y + 52), radius=8, fill=GOLD if i < c else (80, 84, 92))
    _glow(im, (580, y, 1077, y + 76), GOLD, 22, width=3)
    col = {"GEWONNEN": GREEN, "VERLOREN": RED}.get(result, GOLD)
    _text(d, (828, y + 38), f"AUSWERTUNG  {result}", 450, 28, col)
    _text(d, (561, y + 108), "NETRATTLER AI", 400, 26, CYAN)


def _png(im):
    out = io.BytesIO()
    im.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()


# ---------------------------------------------------------------- card families
def _flow(top, bottom, heights):
    """Distribute blocks evenly between top and bottom; returns the y of each block."""
    gap = (bottom - top - sum(heights)) / (len(heights) + 1)
    if gap < 8:
        raise ValueError("Card content does not fit the master")
    ys, y = [], top + gap
    for h in heights:
        ys.append(round(y))
        y += h + gap
    return ys


def render_match(spec, home, away, home_img, away_img):
    """btts, over, btts_halftime, over_halftime, match_result, late_goals, corner, var."""
    im = _master()
    _head(im, spec["title"], spec.get("subtitle"))
    _versus(im, home, away, home_img, away_img, 462, spec.get("league"), spec.get("kickoff"))
    heights = [150] + ([130] if spec.get("stats2") else []) + [104, 118]
    ys = _flow(598, 1170, heights)
    _cells(im, ys[0], spec["stats"], 150)
    k = 1
    if spec.get("stats2"):
        _cells(im, ys[1], spec["stats2"], 130)
        k = 2
    _tip(im, ys[k], spec["tip"])
    _trio(im, ys[k + 1], spec["odds"], spec["prob"])
    _foot(im, 1196, spec.get("conf"), spec.get("result", "OFFEN"))
    return _png(im)


def render_player(spec, player, club_img, photo):
    """goal (anytime scorer), player_props, fouls_cards."""
    im = _master()
    _head(im, spec["title"], spec.get("subtitle"))
    _photo(im, photo, (561, 548), 290)
    _crest(im, club_img, (850, 650), 110)
    d = ImageDraw.Draw(im)
    _gold(im, (221, 712, 901, 784), 26)
    _text(d, (561, 748), _need(player, "player").upper(), 620, 40, (14, 10, 0))
    if spec.get("match"):
        _text(d, (561, 812), spec["match"], 700, 26)
    _cells(im, 836, spec["stats"], 112)
    _tip(im, 966, spec["tip"], 92)
    _trio(im, 1072, spec["odds"], spec["prob"], 104)
    _foot(im, 1196, spec.get("conf"), spec.get("result", "OFFEN"))
    return _png(im)


def render_live(spec, home, away, home_img, away_img):
    """last_minute_goal / live_halftime."""
    im = _master()
    _head(im, spec["title"], spec.get("subtitle"))
    d = ImageDraw.Draw(im)
    _glow(im, (45, 396, 1077, 600), CYAN, 30)
    _crest(im, home_img, (215, 480), 130)
    _crest(im, away_img, (907, 480), 130)
    _glow(im, (410, 410, 712, 588), GOLD, 28)
    _text(d, (561, 440), "LIVE", 140, 28, RED)
    _text(d, (561, 505), f"{int(spec['home_goals'])} : {int(spec['away_goals'])}", 260, 80, WHITE)
    _text(d, (561, 566), f"{_need(spec['minute'], 'minute')}'", 120, 28, GOLD)
    _text(d, (215, 562), home.upper(), 300, 26)
    _text(d, (907, 562), away.upper(), 300, 26)
    rows = spec["live_stats"]
    if not 1 <= len(rows) <= 5:
        raise ValueError("1-5 live stat rows")
    _glow(im, (45, 624, 1077, 624 + 58 * len(rows) + 20), CYAN, 24)
    for i, (label, a, b) in enumerate(rows):
        yy = 653 + i * 58
        _text(d, (130, yy), str(_need(a, label)), 160, 32, GOLD)
        _text(d, (561, yy), label, 420, 26, WHITE)
        _text(d, (992, yy), str(_need(b, label)), 160, 32, GOLD)
    y = 624 + 58 * len(rows) + 52
    _gold(im, (45, y, 1077, y + 92), 26, skew=44)
    _text(d, (561, y + 46), _need(spec["tip"], "tip"), 940, 40, (14, 10, 0))
    _trio(im, y + 112, spec["odds"], spec["prob"], 104)
    _foot(im, 1196, spec.get("conf"), spec.get("result", "OFFEN"))
    return _png(im)


def _hits(d, x, y, series, step=26):
    if not series:
        return
    for i, (label, hit, total) in enumerate(series):
        _text(d, (x, y + i * step), f"{label}: {hit}/{total} ({round(100 * hit / total)}%)", 230, 20, GREEN, "lm", 14)


def render_builder(legs, home, away, home_img, away_img, kickoff=None, league=None, result=None):
    """2-6 player legs of one match. Quote = product of REAL single quotes."""
    if not 2 <= len(legs) <= 6:
        raise ValueError("Builder needs 2-6 legs")
    im = _master()
    _head(im, f"{len(legs)}-LEG BUILDER")
    _versus(im, home, away, home_img, away_img, 478, league, kickoff, 96)
    d = ImageDraw.Draw(im)
    total = 1.0
    top, rh = 604, min(118, 486 // len(legs))
    for i, leg in enumerate(legs):
        y = top + i * rh
        odds = _odds(leg["odds"], "single quote")
        total *= odds
        _glow(im, (45, y, 1077, y + rh - 8), CYAN, 22, width=3)
        _photo(im, leg["photo"], (118, y + (rh - 8) // 2), min(88, rh - 22), GOLD)
        _crest(im, leg["crest"], (212, y + (rh - 8) // 2), min(60, rh - 30))
        _text(d, (270, y + (rh - 8) // 2 - 16), _need(leg["player"], "player").upper(), 420, 28, WHITE, "lm")
        _text(d, (270, y + (rh - 8) // 2 + 18), _need(leg["market"], "market").upper(), 420, 22, GOLD, "lm")
        _hits(d, 720, y + (rh - 8) // 2 - (26 if rh >= 100 else 22), leg.get("hits"), 26 if rh >= 100 else 22)
        _gold(im, (952, y + 16, 1062, y + rh - 24), 16)
        _text(d, (1007, y + (rh - 8) // 2), f"{odds:.2f}", 96, 30, (14, 10, 0))
    yb = top + len(legs) * rh + 6
    _glow(im, (45, yb, 1077, yb + 84), GOLD, 26)
    _text(d, (330, yb + 42), f"EINZELQUOTEN ×  {total:.2f}", 520, 36, GOLD)
    if legs[0].get("combined_prob"):
        _text(d, (850, yb + 42), f"MODELL {_pct(legs[0]['combined_prob']):.0f}%", 380, 34, GREEN)
    _foot(im, 1200, None, result or "OFFEN")
    return _png(im)


def render_combo(legs, category="combo", result=None):
    """combo 3-10 / cross_mix 2-6: one row per tip, both crests, real quotes."""
    lo, hi = (3, 10) if category == "combo" else (2, 6)
    if not lo <= len(legs) <= hi:
        raise ValueError(f"{category} needs {lo}-{hi} tips")
    im = _master()
    _head(im, "COMBO" if category == "combo" else "CROSS / MIX", f"{len(legs)} TIPPS")
    d = ImageDraw.Draw(im)
    top = 392
    rh = min(112, 700 // len(legs))
    total = 1.0
    for i, leg in enumerate(legs):
        y = top + i * rh
        odds = _odds(leg["odds"], "single quote")
        total *= odds
        mid = y + (rh - 8) // 2
        _glow(im, (45, y, 1077, y + rh - 8), CYAN, 20, width=3)
        cs = min(64, rh - 22)
        _crest(im, leg["home_img"], (112, mid), cs)
        _crest(im, leg["away_img"], (200, mid), cs)
        _text(d, (262, mid - 14 if rh > 60 else mid), _need(leg["match"], "match").upper(), 470, 24 if rh > 60 else 20, WHITE, "lm")
        if rh > 60:
            _text(d, (262, mid + 18), _need(leg["market"], "market").upper(), 470, 22, GOLD, "lm")
        else:
            _text(d, (760, mid), leg["market"].upper(), 200, 18, GOLD, "lm")
        mark = {"won": "✔", "lost": "✖", "void": "VOID"}.get(str(leg.get("result") or ""), "")
        if mark:
            _text(d, (835, mid), mark, 80, 28, {"✔": GREEN, "✖": RED}.get(mark, GOLD))
        _gold(im, (930, y + 12, 1062, y + rh - 20), 16)
        _text(d, (996, mid), f"{odds:.2f}", 110, 28 if rh > 60 else 24, (14, 10, 0))
    yb = top + len(legs) * rh + 6
    _glow(im, (45, yb, 1077, yb + 84), GOLD, 26)
    _text(d, (561, yb + 42), f"GESAMTQUOTE  {total:.2f}", 800, 40, GOLD)
    _foot(im, 1200, None, result or "OFFEN")
    return _png(im)
