"""Premium NETRATTLER cards for categories that had no premium route yet.

Built on the existing premium SVG masters (header, frame, footer and the
@prophunter handle come from the master and are never redrawn). Existing
premium renderers (match adapter, Builder, Goal Hunter) are NOT touched.

Fail closed: crests are real image bytes from the caller, odds must be real
bookmaker odds, statistic panels are drawn only for values that really exist.
No Telegram, Supabase or web access in this module.
"""
from __future__ import annotations

import io
import math
from typing import Callable, Dict, List, Optional, Sequence

from PIL import Image, ImageDraw

from netrattler_premium_adapter_shared import (  # noqa
    crest_image, font, fit_font, price, split_match, status_text, number,
    GOLD, CYAN, WHITE, GREEN, RED,
)
from netrattler_premium_verified_cards import render_verified_png
from netrattler_premium_compact import compact_master

CrestProvider = Callable[[str], bytes]

# Panel grid inside the empty centre area of the 1122x1402 masters.
_COLS = (42, 396, 750)
_ROWS = (650, 820, 990)
_PW, _PH = 330, 150


def _png(im) -> bytes:
    out = io.BytesIO()
    im.convert("RGB").save(out, format="PNG")
    return out.getvalue()


def _paste_crest(im, raw, cx, top, size=116):
    crest = crest_image(raw)
    crest.thumbnail((size, size), Image.Resampling.LANCZOS)
    im.alpha_composite(crest, (int(cx - crest.width / 2), int(top + (size - crest.height) / 2)))


def _header(im, draw, home, away, crest_provider, *, league="", kickoff=""):
    for team, cx in ((home, 280), (away, 842)):
        _paste_crest(im, crest_provider(team), cx, 242)
        draw.text((cx, 361), team, font=fit_font(draw, team, 430), fill=WHITE, anchor="mm")
    draw.text((561, 300), "VS", font=font(40), fill=GOLD, anchor="mm")
    if league:
        draw.text((561, 530), league[:55], font=fit_font(draw, league[:55], 950, 26), fill=CYAN, anchor="mm")
    if kickoff:
        draw.text((561, 585), kickoff[:40], font=font(27), fill=WHITE, anchor="mm")


def _panels(draw, items: Sequence[tuple], top_row=0):
    """items: (title, value, colour). Max six; only real values are passed in."""
    for i, (title, value, colour) in enumerate(list(items)[:9]):
        x = _COLS[i % 3]
        y = _ROWS[top_row + i // 3]
        draw.rounded_rectangle((x, y, x + _PW, y + _PH), radius=16, fill="#071724", outline="#28DFFF", width=3)
        draw.text((x + _PW / 2, y + 36), str(title)[:26], font=fit_font(draw, str(title), _PW - 30, 22),
                  fill=CYAN, anchor="mm")
        draw.text((x + _PW / 2, y + 98), str(value)[:16], font=fit_font(draw, str(value), _PW - 30, 52),
                  fill=colour, anchor="mm")


def _footer(draw, shift, *, quote, prob=None, result=None, confidence=""):
    """Quote / model / value / status inside the master footer panel."""
    top = 1185 + shift
    cells = [("QUOTE", f"{quote:.2f}", GOLD)]
    if prob is not None:
        cells.append(("MODELL", f"{prob:.1f}%", GOLD))
        ev = (prob / 100 * quote - 1) * 100
        cells.append(("VALUE", f"{ev:+.1f}%", GREEN if ev >= 0 else RED))
    xs = {1: (561,), 2: (340, 782), 3: (235, 561, 885)}[len(cells)]
    for cx, (head, value, colour) in zip(xs, cells):
        draw.text((cx, top + 24), head, font=font(20), fill=CYAN, anchor="mm")
        draw.text((cx, top + 62), value, font=font(34), fill=colour, anchor="mm")
    label, colour = status_text(result)
    line = ("KONFIDENZ " + confidence.upper() + "   ·   " if confidence else "") + "AUSWERTUNG: " + label
    draw.text((561, top + 106), line[:60], font=fit_font(draw, line[:60], 980, 22), fill=colour, anchor="mm")


def _prob(tip) -> Optional[float]:
    n = number(tip.get("probability"))
    if n is None:
        return None
    n = n * 100 if 0 < n <= 1 else n
    return n if 0 <= n <= 100 else None


def _require_real(tip):
    if not isinstance(tip, dict) or tip.get("_no_real_odds") or tip.get("synthetic") or tip.get("estimated_odds"):
        raise ValueError("Unverified odds or tip cannot be rendered")
    source = (tip.get("bookmaker") or tip.get("odds_source") or tip.get("_source") or tip.get("source"))
    if not str(source or "").strip():
        raise ValueError("Real bookmaker source missing")
    return str(source)


def _single(category, tip, market, crest_provider, panels, result=None, kickoff=""):
    source = _require_real(tip)
    home, away = split_match(tip.get("match"))
    quote = price(tip)
    base = render_verified_png(category, [{"match": f"{home} vs {away}", "market": market,
                                           "bookmaker_odds": quote, "bookmaker": source}])
    im = Image.open(io.BytesIO(base)).convert("RGBA")
    draw = ImageDraw.Draw(im)
    _header(im, draw, home, away, crest_provider,
            league=str(tip.get("league") or "").strip(), kickoff=kickoff)
    _panels(draw, panels)
    _footer(draw, 0, quote=quote, prob=_prob(tip), result=result,
            confidence=str(tip.get("confidence") or "") if isinstance(tip.get("confidence"), str) else "")
    return _png(im)


def _fmt(v, d=1):
    return None if v is None else f"{v:.{d}f}".replace(".", ",")


def _first(tip, *names):
    for n in names:
        v = number(tip.get(n))
        if v is not None and v >= 0:
            return v
    return None


# ---------------------------------------------------------------- categories
def render_corner(tip, crest_provider, *, kickoff="", result=None):
    home, away = split_match(tip.get("match"))
    h10 = _first(tip, "home_corners_l10", "home_l10_corners", "home_avg_corners_l10", "home_corners_l10_avg")
    h15 = _first(tip, "home_corners_l15", "home_l15_corners", "home_avg_corners_l15", "home_corners_l15_avg")
    a10 = _first(tip, "away_corners_l10", "away_l10_corners", "away_avg_corners_l10", "away_corners_l10_avg")
    a15 = _first(tip, "away_corners_l15", "away_l15_corners", "away_avg_corners_l15", "away_corners_l15_avg")
    panels = []
    for team, a, b in ((home, h10, h15), (away, a10, a15)):
        if a is not None and b is not None:
            panels.append((team.upper()[:14] + " Ø ECKEN L10/L15", f"{_fmt(a)} / {_fmt(b)}", GREEN))
        elif a is not None:
            panels.append((team.upper()[:14] + " Ø ECKEN L10", _fmt(a), GREEN))
        elif b is not None:
            panels.append((team.upper()[:14] + " Ø ECKEN L15", _fmt(b), GREEN))
    exp = _first(tip, "expected_corners")
    if exp is not None:
        panels.append(("Ø GESAMT-ECKEN", _fmt(exp), GOLD))
    n, havg = _first(tip, "h2h_matches"), _first(tip, "h2h_avg_corners")
    if havg is not None:
        panels.append(("H2H Ø ECKEN" + (f" ({int(n)} Sp.)" if n is not None else ""), _fmt(havg), GOLD))
    for key, title in (("corner_hits_l10", "TREFFER L10"), ("corner_hits_l15", "TREFFER L15")):
        v = str(tip.get(key) or "").strip()
        if v:
            panels.append((title, v, GREEN))
    market = str(tip.get("tip") or tip.get("selection") or "").strip()
    if not market:
        raise ValueError("Corner selection missing")
    return _single("corner", tip, market, crest_provider, panels, result, kickoff)


def render_match_stats(category, tip, market, crest_provider, *, kickoff="", result=None):
    """fouls_cards, var, late_goals, live_halftime, last-minute style cards.

    tip["stats"] may hold [(label, value), ...] with REAL values only.
    """
    stats = []
    for item in tip.get("stats") or []:
        try:
            label, value = item
        except (TypeError, ValueError):
            continue
        if str(label).strip() and str(value).strip():
            stats.append((str(label), str(value), GREEN))
    score = tip.get("score")
    minute = tip.get("minute")
    live = []
    if score:
        live.append(("SPIELSTAND", str(score), WHITE))
    if minute not in (None, ""):
        live.append(("MINUTE", f"{minute}'", GOLD))
    return _single(category, tip, market, crest_provider, live + stats, result, kickoff)


# ---------------------------------------------------------------- multi rows
def _row_crests(im, row_y, row_h, crests):
    size = min(row_h - 14, 56)
    x = 56
    for raw in crests:
        crest = crest_image(raw)
        crest.thumbnail((size, size), Image.Resampling.LANCZOS)
        im.alpha_composite(crest, (x, int(row_y + (row_h - crest.height) / 2)))
        x += size + 8


def render_combo(legs: List[Dict], crest_provider, *, result=None, total_odds=None, probability=None,
                 category="combo"):
    """Combo 3..10 (or cross_mix 2..6) rows with both club crests per leg."""
    n = len(legs)
    if category == "combo" and not 3 <= n <= 10:
        raise ValueError("Combo requires 3..10 legs")
    if category == "cross_mix" and not 2 <= n <= 6:
        raise ValueError("Cross/Mix requires 2..6 legs")
    from xml.etree import ElementTree as ET
    import cairosvg
    svg = compact_master(category, n)
    im = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg))).convert("RGBA")
    root = ET.fromstring(svg)
    ns = "{http://www.w3.org/2000/svg}"
    rows = sorted((e for e in root.findall(ns + "rect") if e.get("x") == "42" and e.get("width") == "1038"
                   and float(e.get("height", "0")) < 120), key=lambda e: float(e.get("y")))
    draw = ImageDraw.Draw(im)
    odds = []
    for i, leg in enumerate(legs):
        _require_real(leg)
        home, away = split_match(leg.get("match"))
        q = price(leg)
        odds.append(q)
        y, h = int(float(rows[i].get("y"))), int(float(rows[i].get("height")))
        _row_crests(im, y, h, [crest_provider(home), crest_provider(away)])
        text_x = 56 + 2 * (min(h - 14, 56) + 8) + 6
        draw.text((24, y + h / 2), f"{i + 1}", font=font(20), fill=CYAN, anchor="mm")
        small = h < 80
        name = f"{home} vs {away}"
        draw.text((text_x, y + (22 if small else 28)), name,
                  font=fit_font(draw, name, 640, 20 if small else 24), fill=WHITE, anchor="lm")
        market = str(leg.get("market") or leg.get("tip") or "").strip()
        if not market:
            raise ValueError("Leg market missing")
        draw.text((text_x, y + (46 if small else 62)), market,
                  font=fit_font(draw, market, 640, 19 if small else 23), fill=GOLD, anchor="lm")
        draw.text((1050, y + h / 2), f"@ {q:.2f}", font=font(24), fill=GREEN, anchor="rm")
    shift = -(_max_rows(category) - n) * _step(rows, category)
    total = number(total_odds) if total_odds is not None else math.prod(odds)
    if total is None or total <= 1:
        raise ValueError("Total odds invalid")
    prob = None
    if probability is not None:
        p = number(probability)
        prob = p * 100 if p is not None and 0 < p <= 1 else p
    _footer(draw, shift, quote=total, prob=prob, result=result)
    return _png(im)


def _max_rows(category):
    return {"combo": 10, "cross_mix": 6, "builder": 6}[category]


def _step(rows, category):
    if len(rows) >= 2:
        return float(rows[1].get("y")) - float(rows[0].get("y"))
    return {"combo": 73, "cross_mix": 84, "builder": 100}[category]


# ---------------------------------------------------------------- last minute goal
def render_lmg(fixture, metrics, crest_provider, *, final_score=None, won=None,
               next_goal_side=None, next_goal_result=None):
    """Last-minute-goal premium card. Open: live stats; final: verified result only."""
    import cairosvg
    from netrattler_premium_compact import ASSETS
    svg = (ASSETS / "premium_last_minute_goal_blank.svg").read_bytes()
    im = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg))).convert("RGBA")
    draw = ImageDraw.Draw(im)
    home, away = str(fixture["home"]), str(fixture["away"])
    league = str(fixture.get("league") or "").strip()
    _header(im, draw, home, away, crest_provider, league=league)
    if final_score is None:
        draw.text((561, 585), f"{fixture['minute']}. MINUTE", font=font(30), fill=GOLD, anchor="mm")
        score = f"{fixture['hg']}:{fixture['ag']}"
    else:
        draw.text((561, 585), "ENDRESULTAT", font=font(30), fill=GOLD, anchor="mm")
        score = str(final_score)
    draw.text((561, 700), score, font=font(110), fill=WHITE, anchor="mm")
    tier = str((metrics or {}).get("tier") or "").strip()
    draw.rounded_rectangle((42, 390, 1080, 465), radius=16, fill="#071724", outline="#28DFFF", width=3)
    draw.text((66, 428), "OVER 0.5 RESTSPIELZEIT", font=font(26), fill=GOLD, anchor="lm")
    if tier:
        draw.text((1056, 428), tier[:24], font=font(24), fill=WHITE, anchor="rm")
    items = []
    teams = (metrics or {}).get("teams") or {}
    h, a = teams.get("home") or {}, teams.get("away") or {}
    if final_score is None:
        if h and a:
            for label, key in (("SCHÜSSE", "shots"), ("AUFS TOR", "sot"), ("ECKEN", "corners"), ("xG", "xg")):
                if h.get(key) is not None and a.get(key) is not None:
                    fmt = (lambda v: f"{v:.2f}") if key == "xg" else str
                    items.append((label, f"{fmt(h[key])} : {fmt(a[key])}", GREEN))
        else:
            for label, key in (("SCHÜSSE", "shots"), ("AUFS TOR", "sot"), ("ECKEN", "corners")):
                v = (metrics or {}).get(key)
                if v is not None:
                    items.append((label, str(v), GREEN))
    else:
        items.append(("TIPP-ZEITPUNKT", f"{fixture['minute']}. MIN", WHITE))
        items.append(("SPIELSTAND BEIM TIPP", f"{fixture['hg']}:{fixture['ag']}", WHITE))
    if next_goal_side is None:
        next_goal_side = (metrics or {}).get("next_goal_side")
    if next_goal_side not in (None, "home", "away"):
        raise ValueError("Unsupported next-goal team selection")
    if next_goal_side and final_score is not None and next_goal_result is None:
        raise ValueError("Original next-goal pick requires a separate verified grade")
    if next_goal_side:
        name = home if next_goal_side == "home" else away
        wording = {"won": ("RICHTIG", GREEN), "lost": ("FALSCH", RED), "void": ("KEIN WEITERES TOR", GOLD),
                   "unverified": ("NICHT VERIFIZIERT", WHITE), None: ("OFFEN", GOLD)}.get(next_goal_result)
        if wording is None:
            raise ValueError("Invalid next-goal result")
        items.append(("NÄCHSTES TOR", name[:16], GOLD))
        if final_score is not None:
            items.append(("NÄCHSTES TOR ERGEBNIS", wording[0], wording[1]))
    _panels(draw, items, top_row=1)
    if final_score is None:
        label, colour = "AUSWERTUNG: OFFEN", GOLD
    else:
        if won is not True and won is not False:
            raise ValueError("Final result requires a verified win/loss")
        label, colour = ("AUSWERTUNG: GEWONNEN", GREEN) if won else ("AUSWERTUNG: VERLOREN", RED)
    draw.text((561, 1185 + 70), label, font=font(40), fill=colour, anchor="mm")
    return _png(im)


# ---------------------------------------------------------------- Telegram (combo)
def combo_legs_from_tips(tips: Sequence[Dict]) -> List[Dict]:
    """Map generated multi-combo tips to premium rows; real odds + source only."""
    legs = []
    for t in tips:
        market = str(t.get("market") or "").strip()
        selection = str(t.get("tip") or t.get("selection") or "").strip()
        player = str(t.get("player") or "").strip()
        label = " ".join(x for x in ((player + ":") if player else market.upper(), selection) if x).strip()
        legs.append({"match": t.get("match"), "market": label, "odds": t.get("odds", t.get("oddsYes")),
                     "bookmaker": t.get("source") or t.get("_source") or t.get("bookmaker")})
    return legs


def send_combo_card(token, chat, combo: Dict, log=print):
    """Send the premium COMBO image next to the text tip. Never raises, never stores ids.

    The text tip keeps its own Telegram message id (settlement edits it).
    """
    try:
        import netrattler_stats_match_cards as cards
        tips = list(combo.get("tips") or [])
        if not token or not chat or not 3 <= len(tips) <= 10:
            return None
        payload = render_combo(combo_legs_from_tips(tips), cards._badge_bytes,
                               total_odds=combo.get("total_odds"),
                               probability=combo.get("combined_probability"))
        mid = cards._send_photo(token, chat, "", payload, log)
        return mid if isinstance(mid, int) and not isinstance(mid, bool) else None
    except Exception as exc:
        log("Combo-Karte übersprungen: " + type(exc).__name__ + ": " + str(exc)[:90])
        return None
