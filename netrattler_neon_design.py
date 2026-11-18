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
    from netrattler_card_theme import midnight_arena
    im = midnight_arena(w, h)
    d = ImageDraw.Draw(im)
    # Theatre spotlights, stands and pitch; no third-party background or photos.
    for x in (30, w - 30):
        for j in range(5):
            dx = j * 20 - 40
            y = 22 + (j % 2) * 9
            d.ellipse((x + dx - 13, y - 13, x + dx + 13, y + 13),
                      fill="#DDF9FF", outline=CYAN, width=4)
        for k in range(8):
            xx = w // 2 + (x - w // 2) * (8 - k) // 8
            yy = int(h * .22 + k * h * .04)
            d.line((x, 60, xx, yy), fill=(8, 49 + k * 3, 67 + k * 3), width=2)
    for y in (int(h * .61), int(h * .68), int(h * .76)):
        d.arc((-w // 4, y - 150, w + w // 4, y + 90), 0, 180,
              fill="#0C3A60", width=5)
    d.line((0, h - 28, w, h - 28), fill="#146177", width=4)
    return im


def _finish(im, glow):
    layer = Image.new("RGB", im.size, "black")
    g = ImageDraw.Draw(layer)
    for rect, color in glow:
        g.rounded_rectangle(rect, radius=19, outline=color, width=7)
    return ImageChops.screen(im, layer.filter(ImageFilter.GaussianBlur(9)))


def _headline(draw, w, label):
    # Logo and gold ribbon match the new reference design.
    _center(draw, "NETRATTLER", w / 2, 16, 82, WHITE, w - 70)
    draw.polygon([(w // 2 - 26, 10), (w // 2 - 13, 0),
                  (w // 2, 11), (w // 2 + 15, 0),
                  (w // 2 + 28, 10), (w // 2 + 20, 22),
                  (w // 2 - 20, 22)], fill=GOLD)
    _box(draw, (w * .16, 117, w * .84, 184), GOLD, "#0D1922", 17, 4)
    _center(draw, label, w / 2, 122, 49, GOLD, w * .64)


def _initials(name):
    parts = str(name or "").split()
    return "".join(p[:1].upper() for p in parts[:2]) or "?"


def _photo(im, draw, cards, name, team, rect, ring=GOLD):
    x0, y0, x1, y1 = (int(x) for x in rect)
    draw.ellipse((x0 - 6, y0 - 6, x1 + 6, y1 + 6), fill="#08253A",
                 outline=ring, width=7)
    payload = cards._player_photo(name, team)
    if payload:
        try:
            pic = Image.open(io.BytesIO(payload)).convert("RGBA")
            pic = ImageOps.fit(pic, (x1 - x0, y1 - y0),
                               Image.Resampling.LANCZOS, centering=(.5, .26))
            mask = Image.new("L", pic.size, 0)
            ImageDraw.Draw(mask).ellipse((0, 0, pic.width - 1, pic.height - 1), fill=255)
            im.paste(pic, (x0, y0), mask)
            return
        except (OSError, ValueError):
            pass
    _center(draw, _initials(name), (x0 + x1) / 2, (y0 + y1) / 2 - 39,
            73 if (x1 - x0) > 200 else 31, WHITE, x1 - x0 - 8)


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
    except (ValueError, TypeError, OSError, RuntimeError, Exception):
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


def render_builder_card(pick):
    import netrattler_stats_match_cards as cards
    import netrattler_builder_engine as engine
    from netrattler_corner_cards import kickoff_label

    legs = list(getattr(pick, "legs", []) or [])
    n = max(len(legs), 1)
    tiers = list(getattr(pick, "tiers", None) or [])
    w, h = 1200, 530 + 160 * n + 40 * len(tiers)
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
        _center(d, str(day) + "   /   " + str(hour) + " Uhr", 600, 268, 23,
                MUTED, 980)
    _box(d, (28, 310, 1172, 351), CYAN, "#0B2332", 16)
    _center(d, str(len(legs)) + "-LEG BUILDER", 600, 313, 32, WHITE)

    for i, leg in enumerate(legs):
        y = 362 + i * 160
        box = (35, y, 1165, y + 142)
        _box(d, box, CYAN, "#071724", 17)
        glow.append((box, CYAN))
        # The photo provider caches by player/team; every row still has a portrait.
        _photo(im, d, cards, leg.player, leg.team, (49, y + 10, 159, y + 133))
        _badge(im, d, cards, leg.team, (177, y + 29, 253, y + 110))
        _center(d, leg.player, 540, y + 15, 29, WHITE, 525)
        _center(d, _display_market(leg), 540, y + 68, 27, GOLD, 525)
        d.line((855, y + 19, 855, y + 121), fill=CYAN, width=2)
        series = _stat_series(leg, engine, getattr(pick, "match_date", ""))
        _center(d, "L10: " + _form_label(series, leg.line, 10),
                1015, y + 29, 23, GREEN, 295)
        _center(d, "L15: " + _form_label(series, leg.line, 15),
                1015, y + 75, 23, GREEN, 295)

    # Keep the result bar inside the PNG for both 1-leg and 6-leg layouts.
    y = 362 + len(legs) * 160
    model_only = bool(getattr(pick, "model_only", False))
    p = _percent(getattr(pick, "joint", None) if model_only else
                 getattr(pick, "joint_probability", None))
    if p is None and not model_only:
        p = _percent(getattr(pick, "probability", None))
    verified = bool(getattr(pick, "combined_quote_verified", False))
    combined = _number(getattr(pick, "combined_bookmaker_quote", None)) if verified else None
    if combined is None or combined <= 1:
        combined = None
    odds_label, odds_value = "KOMBIQUOTE", f"@ {combined:.2f}" if combined else "—"
    if combined is None:
        odds_label = "BUCHBARE KOMBIQUOTE"
    ev = (p / 100 * combined - 1) * 100 if p is not None and combined else None
    stats = (("BUCHBARE KOMBIQUOTE", odds_value, GOLD),
             ("MODELL-PROB.", f"{p:.1f}%" if p is not None else "—", GREEN),
             ("EV", f"{ev:+.1f}%" if ev is not None else "—", GREEN if ev is not None and ev >= 0 else GOLD))
    for i, (title, value, color) in enumerate(stats):
        x = 30 + i * 393
        _metric(d, (x, y, x + 369, y + 103), title, value, color)
    confidence = getattr(pick, "confidence", None)
    conf = str(confidence).upper() if confidence not in (None, "") else "—"
    label, col = _result_text(getattr(pick, "status", None))
    _box(d, (31, y + 114, 566, y + 162), GOLD, "#081C30")
    _box(d, (588, y + 114, 1167, y + 162), CYAN, "#081C30")
    _center(d, "KONFIDENZ: " + conf, 300, y + 124, 25, GOLD, 510)
    _center(d, "AUSWERTUNG: " + label, 879, y + 124, 25, col, 555)

    # No same-game combination is advertised as a bookable bookmaker price
    # merely because its individual odds can be multiplied.
    out = io.BytesIO()
    im = _finish(im, glow)
    im.save(out, format="PNG", optimize=True)
    return out.getvalue()


def render_scorer_card(tip, target_date, result=None):
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
