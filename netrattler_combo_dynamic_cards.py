"""Dynamic NETRATTLER COMBO card (3–10 legs) with verified team crest bytes.

Standalone renderer: it never substitutes generic shields for missing crests.
Caller supplies real crests from its trusted club-identity/image pipeline.
"""
from __future__ import annotations
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageOps

CYAN = "#27E6FF"
GOLD = "#FFE14A"
WHITE = "#FAFCFF"
BG = "#06111C"

def _font(size):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()

def _fit(draw, value, max_width, size=27):
    value = str(value or "").strip()
    if not value:
        raise ValueError("Leerer Combo-Kartentext")
    while size >= 14:
        f = _font(size)
        if draw.textbbox((0, 0), value, font=f)[2] <= max_width:
            return f
        size -= 1
    raise ValueError("Combo-Text zu lang: " + value[:40])

def _crest(raw):
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        raise ValueError("Echtes Vereinswappen fehlt: keine Platzhalter erlaubt")
    with Image.open(BytesIO(raw)) as source:
        source.load()
        if min(source.size) < 24:
            raise ValueError("Vereinswappen hat zu geringe Auflösung")
        return source.convert("RGBA").copy()

def _text(draw, x, y, value, width, size=27, color=WHITE):
    f = _fit(draw, value, width, size)
    draw.text((x, y), str(value), font=f, fill=color)

def render_combo(legs, *, combined_odds, probability, ev, confidence, status="OFFEN",
                 crest_provider=None):
    """Each leg: home, away, market, odds; crest_provider(team)->image bytes.

    Explicit inputs avoid invented odds, fixtures and probabilities.
    Returns PNG bytes. Does not send Telegram messages.
    """
    legs = list(legs)
    if not 3 <= len(legs) <= 10:
        raise ValueError("COMBO erfordert 3 bis 10 Tipps")
    if not callable(crest_provider):
        raise ValueError("Verifizierte Vereinswappen-Quelle fehlt")
    for v in (combined_odds, probability, ev):
        if not isinstance(v, (float, int)) or isinstance(v, bool):
            raise ValueError("Bestätigte Quote/Wahrscheinlichkeit/EV fehlt")
    if combined_odds <= 1 or not 0 <= probability <= 100:
        raise ValueError("Ungültige Quote oder Wahrscheinlichkeit")
    for leg in legs:
        if not all(str(leg.get(k) or "").strip() for k in ("home", "away", "market")):
            raise ValueError("Unvollständiger COMBO-Tipp")
        if not isinstance(leg.get("odds"), (int, float)) or leg["odds"] <= 1:
            raise ValueError("Echte Einzelquote fehlt")
    # Validate and cache all badges BEFORE painting; never output partial cards.
    crests = {}
    for leg in legs:
        for team in (leg["home"], leg["away"]):
            if team not in crests:
                crests[team] = _crest(crest_provider(team))
    width, top, row_h, footer = 1100, 290, 114, 315
    height = top + len(legs) * row_h + footer
    im = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((24, 20, width-24, height-22), radius=35,
                        outline=CYAN, width=5)
    _text(d, 165, 38, "NETRATTLER", 790, 78)
    d.rounded_rectangle((280, 140, 820, 212), radius=18, outline=GOLD, width=5)
    _text(d, 405, 155, "COMBO", 400, 48, GOLD)
    _text(d, 420, 235, f"{len(legs)} TIPPS", 310, 34, GOLD)
    for i, leg in enumerate(legs):
        y = top + i * row_h
        d.rounded_rectangle((42, y, width-42, y+row_h-13), radius=18,
                            outline=CYAN, width=4, fill="#071B28")
        _text(d, 60, y+29, str(i+1), 50, 32, GOLD)
        for team, x in ((leg["home"], 115), (leg["away"], 573)):
            badge = ImageOps.contain(crests[team], (64, 64))
            im.paste(badge, (x, y+13), badge)
            _text(d, x+74, y+12, team.upper(), 270, 25)
        _text(d, 510, y+16, "VS", 60, 25, GOLD)
        _text(d, 195, y+63, leg["market"], 610, 23, GOLD)
        _text(d, 897, y+42, f'{leg["odds"]:.2f}', 120, 30, GOLD)
    y = top + len(legs) * row_h + 20
    for x, label, val, color in (
        (50, "QUOTE", f"{combined_odds:.2f}", GOLD),
        (395, "WAHRSCHEINLICHKEIT", f"{probability:.1f}%", WHITE),
        (770, "EV", f"{ev:+.1f}%", GOLD),
    ):
        d.rounded_rectangle((x, y, x+285, y+130), radius=18, outline=CYAN, width=4)
        _text(d, x+18, y+14, label, 252, 25)
        _text(d, x+22, y+58, val, 250, 42, color)
    _text(d, 62, y+165, f"KONFIDENZ: {str(confidence).upper()}", 500, 26, GOLD)
    _text(d, 62, y+220, f"AUSWERTUNG: {str(status).upper()}", 580, 25)
    _text(d, 795, y+220, "@prophunter", 260, 27, GOLD)
    output = BytesIO()
    im.save(output, format="PNG")
    return output.getvalue()
