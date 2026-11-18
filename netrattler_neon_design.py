"""NETRATTLER screenshot-style Goal Hunter and Prop Builder cards.

Presentation only: source selectors, validated odds, duplicate protection and
settlement storage stay in their existing production modules.
Missing photos, histories, and prices are displayed as unknown, not guessed.
"""
from __future__ import annotations

import io
import math
import os
from datetime import datetime
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

GOLD = "#FFD348"
CYAN = "#29DFFF"
GREEN = "#40F58A"
WHITE = "#F8FAFF"
MUTED = "#B5D2EA"
NAVY = "#061525"


@lru_cache(maxsize=80)
def _font(size):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, int(size))
        except OSError:
            continue
    return ImageFont.load_default()


def _fit(draw, text, width, size=36, minimum=16):
    text = str(text or "")
    n = size
    while n > minimum and draw.textlength(text, font=_font(n)) > width:
        n -= 1
    while text and draw.textlength(text, font=_font(n)) > width:
        text = text[:-2].rstrip() + "…"
    return text, _font(n)


def _center(draw, text, x, y, size=34, color=WHITE, width=None):
    t, f = _fit(draw, text, width or 1100, size)
    draw.text((int(x - draw.textlength(t, font=f) / 2), int(y)), t, font=f, fill=color)


def _box(draw, rect, outline=CYAN, fill="#071A30", radius=19, thick=3):
    draw.rounded_rectangle(tuple(int(v) for v in rect), radius=radius,
                           fill=fill, outline=outline, width=thick)


def _background(w, h):
    """Gold-and-cyan night stadium rather than the former flat midnight grid."""
    import random
    im = Image.new("RGB", (w, h), "#030D1C")
    draw = ImageDraw.Draw(im)
    crowd_top = int(h * 0.34)
    pitch_top = int(h * 0.62)
    for y in range(h):
        t = y / max(h - 1, 1)
        if y < crowd_top:
            v = y / max(1, crowd_top)
            color = (2, int(11 + 8 * v), int(28 + 17 * v))
        elif y < pitch_top:
            v = (y - crowd_top) / max(1, pitch_top - crowd_top)
            color = (int(1 + 3 * v), int(20 + 12 * v), int(44 - 11 * v))
        else:
            v = (y - pitch_top) / max(1, h - pitch_top)
            color = (int(4 + 4 * v), int(43 - 22 * v), int(22 - 12 * v))
        draw.line((0, y, w, y), fill=color, width=1)
    # Stadium bowl and tiers; small spectator highlights suggest real stands.
    for i in range(7):
        y = int(h * (.32 + .043 * i))
        draw.arc((-w * .35, y - 75, w * 1.35, y + 165), 0, 180,
                 fill=(8 + i * 2, 58 + i * 2, 76 + i * 3), width=3)
        draw.line((0, y + i * 3, w, y + i * 3), fill="#082B3B", width=1)
    rng = random.Random(170118)
    for _ in range(5000):
        x = rng.randrange(w)
        y = rng.randrange(crowd_top, max(crowd_top + 1, pitch_top))
        if rng.randrange(5) > 1 and w * .19 < x < w * .81:
            continue
        lum = rng.randrange(24, 112)
        color = (lum // 2, int(lum * .80), lum)
        draw.ellipse((x, y, x + 2, y + 2), fill=color)
    # Ground perspective and white painted football lines.
    draw.polygon(((0, h), (0, int(h * .84)), (w // 2, int(h * .71)),
                  (w, int(h * .84)), (w, h)), fill="#082419")
    for y in range(int(h * .76), h, 68):
        draw.line((0, y, w, y), fill="#104632", width=2)
    draw.line((0, int(h * .84), w // 2, int(h * .71), w, int(h * .84)),
              fill="#227860", width=3)
    # Floodlight beams behind content: glow plus visible 5x4 lamp arrays.
    beam = Image.new("RGBA", im.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(beam)
    lamps = []
    for side in (0, 1):
        ox = 24 if side == 0 else w - 24
        for j in range(4):
            for k in range(5):
                sx = ox + ((k * 22) if side == 0 else -(k * 22))
                sy = 12 + j * 17 + int(k * 2)
                lamps.append((sx, sy))
        for bx in (.17, .41, .66, .88):
            dest = int(w * bx)
            bd.polygon(((ox, 29), (ox + (-18 if side else 18), 90),
                        (dest, int(h * .54))), fill=(10, 112, 205, 12))
    im = Image.alpha_composite(im.convert("RGBA"), beam).convert("RGB")
    bloom = Image.new("RGB", im.size, "black")
    glow = ImageDraw.Draw(bloom)
    for x, y in lamps:
        glow.ellipse((x - 10, y - 10, x + 10, y + 10), fill=(140, 230, 255))
    im = ImageChops.screen(im, bloom.filter(ImageFilter.GaussianBlur(21)))
    d = ImageDraw.Draw(im)
    for x, y in lamps:
        d.ellipse((x - 7, y - 7, x + 7, y + 7), fill="#EAFBFF", outline=CYAN, width=2)
    return im


def _finish(im, glow):
    layer = Image.new("RGB", im.size, "black")
    g = ImageDraw.Draw(layer)
    for rect, color in glow:
        g.rounded_rectangle(rect, radius=19, outline=color, width=8)
    halo = layer.filter(ImageFilter.GaussianBlur(14))
    im = ImageChops.screen(im, halo)
    g2 = ImageDraw.Draw(im)
    for rect, color in glow:
        g2.rounded_rectangle(rect, radius=19, outline=color, width=3)
    return im



def _headline(draw, w, label):
    """Metallic italic masthead and illuminated gold title ribbon."""
    try:
        logo_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-BoldOblique.ttf", 94)
        tag_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-BoldOblique.ttf", 51)
    except OSError:
        logo_font, tag_font = _font(94), _font(51)
    word = "NETRATTLER"
    text_width = draw.textlength(word, font=logo_font)
    x, y = int((w - text_width) / 2), 13
    # Black depth, silver face and gold underlining rather than duplicate dark text.
    draw.text((x + 4, y + 6), word, font=logo_font, fill="#0A0F15",
              stroke_width=6, stroke_fill="#070C13")
    draw.text((x, y), word, font=logo_font, fill="#F9FDFF",
              stroke_width=3, stroke_fill="#40505D")
    draw.line((x + 18, 110, x + text_width - 16, 110), fill="#EFC454", width=4)
    c = w // 2
    draw.polygon(((c - 32, 12), (c - 27, -1), (c - 9, 13),
                  (c + 4, -4), (c + 19, 11), (c + 33, -1),
                  (c + 30, 24), (c - 31, 24)),
                 fill="#FFE669", outline="#D3950A")
    # Gold trapezoid band: luminous centre and slanted wings.
    x0, x1, y0, y1 = int(w * .15), int(w * .85), 120, 188
    draw.polygon(((x0 + 26, y0 - 5), (x1 + 8, y0 - 5),
                  (x1 - 14, y1 + 4), (x0 - 5, y1 + 4)),
                 fill="#F1AB1C", outline="#9C5800")
    for yy in range(y0, y1):
        q = (yy - y0) / max(1, y1 - y0)
        top = q < .43
        draw.line((x0 + 28 - 18 * q, yy, x1 + 3 - 20 * q, yy),
                  fill=(255, int(226 + 25 * q if top else 251 - 36 * (q - .43)),
                        int(90 + 85 * q if top else 175 - 124 * (q - .43))), width=1)
    tag_w = draw.textlength(label, font=tag_font)
    draw.text(((w - tag_w) / 2, 124), label, font=tag_font, fill="#0D1015",
              stroke_width=1, stroke_fill="#231A05")


def _initials(name):
    parts = str(name or "").split()
    return "".join(p[:1].upper() for p in parts[:2]) or "?"


def _photo(im, draw, cards, name, team, rect, ring=GOLD):
    x0, y0, x1, y1 = (int(x) for x in rect)
    draw.ellipse((x0 - 8, y0 - 8, x1 + 8, y1 + 8), fill="#08253A",
                 outline="#C68505", width=9)
    draw.ellipse((x0 - 3, y0 - 3, x1 + 3, y1 + 3), outline=ring, width=5)
    payload = cards._player_photo(name, team)
    if payload:
        try:
            pic = Image.open(io.BytesIO(payload)).convert("RGBA")
            pic = ImageOps.fit(pic, (x1 - x0, y1 - y0),
                               Image.Resampling.LANCZOS, centering=(.5, .22))
            mask = Image.new("L", pic.size, 0)
            ImageDraw.Draw(mask).ellipse((0, 0, pic.width - 1, pic.height - 1), fill=255)
            im.paste(pic, (x0, y0), mask)
            return
        except (OSError, ValueError):
            pass
    # Preview-only fallback: production strict preflight blocks missing real photos.
    _center(draw, _initials(name), (x0 + x1) / 2,
            (y0 + y1) / 2 - 39, 73 if x1 - x0 > 200 else 31,
            MUTED, x1 - x0 - 8)


def _badge(im, draw, cards, name, rect):
    cards._paste_badge(im, draw, name, rect, _font(30))


def _number(value):
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _percent(value):
    n = _number(value)
    if n is None:
        return None
    n = n * 100 if 0 <= n <= 1 else n
    return n if 0 <= n <= 100 else None


def _result_text(status):
    status = str(status or "").lower()
    return {"win": ("GEWONNEN", GREEN),
            "loss": ("VERLOREN", "#FF6B79"),
            "void": ("VOID", GOLD)}.get(status, ("OFFEN", GOLD))


def _metric(draw, box, title, value, color=GOLD):
    _box(draw, box, CYAN, "#081C30")
    x0, y0, x1, y1 = box
    _center(draw, title, (x0 + x1) / 2, y0 + 14, 23, WHITE, x1 - x0 - 14)
    line_y = y0 + (55 if (y1 - y0) < 130 else 76)
    value_size = 34 if (y1 - y0) < 130 else 47
    _center(draw, value, (x0 + x1) / 2, line_y, value_size, color, x1 - x0 - 16)


_HISTORY_COLUMN = {
    "shots": "shots", "sot": "sot", "tackles": "tackles",
    "tackles_committed": "tackles", "fouls": "fouls_committed",
    "fouls_won": "fouls_won", "yellow_cards": "yellow_cards",
    "score": "goals", "assist": "assists", "goalkeeper_saves": "saves",
    "offsides": "offsides",
}


@lru_cache(maxsize=256)
def _observed_game_log(player, team, category, match_date):
    """Read-only, exact player+team L15; never widen to fuzzy/other-team rows.

    Missing stats stop the usable series rather than silently counting older
    matches as if the incomplete fixture did not happen. No database writes.
    """
    column = _HISTORY_COLUMN.get(category)
    url = (os.getenv("SUPABASE_PLAYERS_URL") or os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = (os.getenv("SUPABASE_PLAYERS_SERVICE_KEY")
           or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
           or os.getenv("SUPABASE_KEY") or "")
    if not (column and player and team and match_date and url.startswith("https://") and key):
        return ()
    try:
        import requests
        response = requests.get(
            url + "/rest/v1/player_game_log",
            headers={"apikey": key, "Authorization": "Bearer " + key},
            params={
                "select": "player_name,team,match_date,event_id,minutes," + column,
                "player_name": "eq." + player,
                "team": "eq." + team,
                "match_date": "lt." + str(match_date)[:10],
                "order": "match_date.desc,event_id.desc",
                "limit": "40",
            },
            timeout=5,
        )
        if not response.ok:
            return ()
        rows = response.json()
        if not isinstance(rows, list):
            return ()
        result, seen = [], set()
        for row in rows:
            if not isinstance(row, dict):
                return ()
            day = str(row.get("match_date") or "")[:10]
            if (row.get("player_name") != player or row.get("team") != team or
                    not day or day >= str(match_date)[:10]):
                return ()
            event_key = (day, str(row.get("event_id") or ""))
            if event_key in seen:
                continue
            seen.add(event_key)
            minutes = _number(row.get("minutes"))
            if minutes is not None and minutes <= 0:
                continue  # Did not play: not one of the last games played.
            n = _number(row.get(column))
            if n is None or n < 0:
                break  # Do not skip a played fixture with an unknown statistic.
            result.append(n)
            if len(result) >= 15:
                break
        return tuple(result)
    except Exception:
        return ()


def _stat_series(leg, engine, match_date=""):
    raw = getattr(leg, "series", None)
    if raw is None:
        raw = engine.LEG_HISTORY.get((engine.norm(getattr(leg, "player", "")),
                                     getattr(leg, "category", "")))
    out = []
    if isinstance(raw, (list, tuple)):
        for value in raw[:15]:
            n = _number(value)
            if n is None or n < 0:
                break
            out.append(n)
    if len(out) >= 15:
        return out
    db = list(_observed_game_log(str(getattr(leg, "player", "") or ""),
                                 str(getattr(leg, "team", "") or ""),
                                 str(getattr(leg, "category", "") or ""),
                                 str(match_date or "")[:10]))
    # Never combine two unrelated or conflicting player histories.
    if db and (not out or db[:len(out)] == out):
        return db
    return out


def _form_label(series, line, count):
    # 10/15 must mean actual last 10/15 fixtures; never extrapolate L5 to L15.
    if len(series) < count:
        return "—"
    threshold = _number(line)
    if threshold is None:
        return "—"
    required = math.ceil(threshold)
    hits = sum(x >= required for x in series[:count])
    return f"{hits}/{count} ({hits/count:.0%})"


def _display_market(leg):
    from netrattler_builder_cards import builder_leg_label
    return builder_leg_label(leg)


def _builder_quote_display(pick, legs):
    """Show calculated product, but never mislabel it a bookable SGM quote."""
    model_only = bool(getattr(pick, "model_only", False))
    if model_only:
        return ("BUCHMACHERQUOTE", "—", None)
    if bool(getattr(pick, "combined_quote_verified", False)):
        quoted = _number(getattr(pick, "combined_bookmaker_quote", None))
        if quoted is not None and 1.01 <= quoted <= 100000:
            return ("BESTÄTIGTE KOMBIQUOTE", f"@ {quoted:.2f}", quoted)
    if not legs or bool(getattr(pick, "estimated_odds", False)):
        return ("BUCHMACHERQUOTE", "—", None)
    values = []
    for leg in legs:
        q = _number(getattr(leg, "odds", None))
        if (q is None or not 1.01 <= q <= 1000 or
                bool(getattr(leg, "estimated", False)) or
                not str(getattr(leg, "source", "") or "").strip()):
            return ("BUCHMACHERQUOTE", "—", None)
        values.append(q)
    # A same-game parlay may have a different bookmaker price or be unavailable.
    # This product is for reference, never used for displayed EV.
    product = math.prod(values)
    return ("EINZELQUOTEN ×", f"{product:.2f}", None)


def render_builder_card(pick):
    from netrattler_original_template_renderer import render_builder
    return render_builder(pick)

    import netrattler_stats_match_cards as cards
    import netrattler_builder_engine as engine
    from netrattler_corner_cards import kickoff_label

    legs = list(getattr(pick, "legs", []) or [])
    n = max(len(legs), 1)
    tiers = list(getattr(pick, "tiers", None) or [])
    w, h = 1200, 650 + 160 * n + 40 * len(tiers)
    im = _background(w, h)
    d = ImageDraw.Draw(im)
    glow = []
    _headline(d, w, "PROP BUILDER")

    multi = len({str(getattr(leg, "match", "")) for leg in legs}) != 1
    first = legs[0] if legs else None
    if first is not None and not multi:
        home, away = cards._teams(first.match)
        for t in (home, away):
            cards._TEAM_LEAGUE.setdefault(cards._norm(t), first.league)
        _badge(im, d, cards, home, (55, 190, 174, 292))
        _badge(im, d, cards, away, (1026, 190, 1145, 292))
        _center(d, home, 375, 210, 37, WHITE, 390)
        _center(d, away, 850, 210, 37, WHITE, 365)
        _center(d, "VS", 600, 214, 39, GOLD)
    else:
        _center(d, "CROSS-MATCH BUILDER", 600, 210, 39, GOLD)
    if first:
        day, hour = kickoff_label({"_kickoff": getattr(first, "kickoff", "")},
                                  getattr(pick, "match_date", ""))
        time_label = str(day) + ("    /    " + str(hour) + " Uhr" if
                 str(hour) not in ("", "Zeit nicht bestätigt", "TBD") else "")
        _center(d, time_label, 600, 268, 24, WHITE, 980)
    _box(d, (28, 310, 1172, 351), CYAN, "#081C2A", 16)
    _center(d, str(len(legs)) + "-LEG BUILDER", 415, 313, 32, WHITE, 670)
    head_label, head_value, _ = _builder_quote_display(pick, legs)
    if head_value != "—":
        _box(d, (760, 313, 1165, 347), GOLD, "#171A13", 12, 3)
        _center(d, head_value, 962, 315, 27, GOLD, 380)

    for i, leg in enumerate(legs):
        y = 362 + i * 160
        box = (35, y, 1165, y + 142)
        _box(d, box, CYAN, "#071724", 17)
        # Reference visual: left edge glows gold; right edge stays cyan.
        d.arc((33, y - 2, 115, y + 144), 90, 270, fill=GOLD, width=7)
        d.line((37, y + 16, 37, y + 126), fill=GOLD, width=6)
        d.line((41, y + 2, 310, y + 2), fill=GOLD, width=3)
        d.line((41, y + 140, 310, y + 140), fill=GOLD, width=3)
        glow.append((box, CYAN))
        # The photo provider caches by player/team; every row still has a portrait.
        _photo(im, d, cards, leg.player, leg.team, (49, y + 10, 159, y + 133))
        _badge(im, d, cards, leg.team, (177, y + 29, 253, y + 110))
        _center(d, leg.player, 540, y + 15, 29, WHITE, 525)
        _center(d, _display_market(leg), 540, y + 68, 27, GOLD, 525)
        d.line((855, y + 19, 855, y + 121), fill=CYAN, width=2)
        series = _stat_series(leg, engine, getattr(pick, "match_date", ""))
        for j, height in enumerate((18, 29, 40)):
            d.rectangle((867 + j * 12, y + 105 - height, 875 + j * 12, y + 105),
                        fill=(29, 182 + j * 23, 95 + j * 19))
        _center(d, "L10: " + _form_label(series, leg.line, 10),
                1044, y + 29, 23, GREEN, 244)
        _center(d, "L15: " + _form_label(series, leg.line, 15),
                1044, y + 75, 23, GREEN, 244)

    # Keep the result bar inside the PNG for both 1-leg and 6-leg layouts.
    y = 362 + len(legs) * 160
    model_only = bool(getattr(pick, "model_only", False))
    p = _percent(getattr(pick, "joint", None) if model_only else
                 getattr(pick, "joint_probability", None))
    if p is None and not model_only:
        p = _percent(getattr(pick, "probability", None))
    odds_label, odds_value, combined = _builder_quote_display(pick, legs)
    ev = (p / 100 * combined - 1) * 100 if p is not None and combined else None
    stats = ((odds_label, odds_value, GOLD),
             ("MODELL-PROB.", f"{p:.1f}%" if p is not None else "—", GREEN),
             ("EV", f"{ev:+.1f}%" if ev is not None else "—", GREEN if ev is not None and ev >= 0 else GOLD))
    for i, (title, value, color) in enumerate(stats):
        x = 30 + i * 393
        _metric(d, (x, y, x + 369, y + 113), title, value, color)
    confidence = getattr(pick, "confidence", None)
    conf = str(confidence).upper() if confidence not in (None, "") else "—"
    label, col = _result_text(getattr(pick, "status", None))
    _box(d, (30, y + 128, 560, y + 203), GOLD, "#0D1421")
    _box(d, (586, y + 128, 1170, y + 203), CYAN, "#071E2D")
    _center(d, "KONFIDENZ: " + conf, 295, y + 142, 32, GOLD, 520)
    _center(d, "AUSWERTUNG: " + label, 878, y + 142, 32, col, 575)

    # No same-game combination is advertised as a bookable bookmaker price
    # merely because its individual odds can be multiplied.
    out = io.BytesIO()
    im = _finish(im, glow)
    im.save(out, format="PNG", optimize=True)
    return out.getvalue()


def render_scorer_card(tip, target_date, result=None):
    from netrattler_original_template_renderer import render_goal
    return render_goal(tip, target_date, result)

    import netrattler_stats_match_cards as cards
    w, h = 1080, 1340
    im = _background(w, h)
    d = ImageDraw.Draw(im)
    _headline(d, w, "GOAL HUNTER")
    _center(d, "ANYTIME GOALSCORER", 540, 196, 31, WHITE, 900)
    home, away = cards._teams(tip.get("match", ""))
    player, team = str(tip.get("player") or ""), str(tip.get("team") or "")
    for t in (home, away):
        cards._TEAM_LEAGUE.setdefault(cards._norm(t), str(tip.get("league") or ""))
    _badge(im, d, cards, home, (45, 400, 280, 610))
    _badge(im, d, cards, away, (800, 400, 1035, 610))
    _photo(im, d, cards, player, team, (365, 298, 715, 653))
    _box(d, (25, 642, 350, 707), CYAN, "#081D2D")
    _box(d, (730, 642, 1055, 707), CYAN, "#081D2D")
    _center(d, home, 187, 651, 32, WHITE, 310)
    _center(d, away, 892, 651, 32, WHITE, 310)
    _center(d, "VS", 540, 653, 49, GOLD)
    _box(d, (125, 732, 955, 811), GOLD, "#071625", 18, 5)
    _center(d, player.upper() or "SPIELER UNBEKANNT", 540, 739, 57, WHITE, 795)

    odds = cards._price(tip)
    probability = cards._pct(tip.get("probability"))
    fair = _number(tip.get("fairOdds") if tip.get("fairOdds") is not None else tip.get("fair_odds"))
    if fair is None and probability and probability > 0:
        fair = 100 / probability
    gpg = _number(tip.get("goals_per_game"))
    values = (
        ("QUOTE", f"{odds:.2f}" if odds else "—", GOLD),
        ("MODELL PROB.", f"{probability:.0f}%" if probability is not None else "—", GREEN),
        ("FAIRE QUOTE", f"{fair:.2f}" if fair and fair > 0 else "—", GOLD),
        ("TORE / SPIEL", f"{gpg:.2f}" if gpg is not None and gpg >= 0 else "—", GOLD),
    )
    for i, (label, value, color) in enumerate(values):
        x = 25 + i * 268
        _metric(d, (x, 849, x + 247, 1034), label, value, color)
    _box(d, (22, 1060, 1058, 1132), CYAN, "#091E2D")
    _center(d, "ANYTIME GOALSCORER  ·  Spieler trifft jederzeit", 540, 1073,
            28, WHITE, 1005)

    status = (result.get("marks") or {}).get("0") if isinstance(result, dict) else None
    label, color = _result_text(status)
    _box(d, (35, 1185, 735, 1264), GOLD, "#081926", 22, 4)
    _center(d, "AUSWERTUNG: " + label, 385, 1200, 35, color, 665)
    _center(d, "@netrattler", 885, 1205, 29, WHITE, 280)
    if isinstance(result, dict) and result.get("ft"):
        _center(d, "ENDSTAND: " + str(result["ft"]), 540, 1144, 22, MUTED, 900)
    output = io.BytesIO()
    im = _finish(im, [((125, 732, 955, 811), GOLD), ((35, 1185, 735, 1264), GOLD)])
    im.save(output, format="PNG", optimize=True)
    return output.getvalue()
