"""NETRATTLER AI PREMIUM: offline-only, original-preserving variable-height card renderer.

Never sends to Telegram. Requires the exact approved master image path.
Original pixels are copied unchanged; no repainting or fallback templates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

MASTER_PATH = Path(__file__).resolve().parent / "assets/premium_master/NETRATTLER_AI_PREMIUM_MASTER.png"
MASTER_SHA256 = "e87a7a98d284ff5429ac26e6cc59ae37c6ed0dfa0aff690c29368ca386575209"

CATEGORIES = frozenset(("single", "btts", "btts_halftime", "over",
    "over_halftime", "match_result", "goal", "corner", "player_props",
    "fouls_cards", "var", "last_minute_goal", "late_goals",
    "live_halftime", "builder", "combo", "cross_mix", "lottery"))
MULTI = frozenset(("builder", "combo", "cross_mix", "lottery"))
BG = (5, 18, 32)
PANEL = (9, 30, 49)
GOLD = (244, 190, 53)
CYAN = (46, 211, 239)
WHITE = (243, 248, 255)


def _font(size, bold=False):
    names = ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf") if bold else (
        "DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
    for name in names:
        for path in ("/usr/share/fonts/truetype/dejavu/", ""):
            try:
                return ImageFont.truetype(path + name, size)
            except OSError:
                pass
    return ImageFont.load_default()


def _fit(draw, text, width, size=28, min_size=18):
    for n in range(size, min_size - 1, -1):
        font = _font(n, True)
        bounds = draw.textbbox((0, 0), text, font=font)
        if bounds[2] - bounds[0] <= width:
            return font
    raise ValueError("Text would overflow allocated card slot")


def _odds(raw, label):
    try:
        n = float(raw)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(label + ": observed bookmaker quote required") from None
    if not math.isfinite(n) or n <= 1:
        raise ValueError(label + ": invalid decimal quote")
    return n


def validate(data):
    if not isinstance(data, dict):
        raise ValueError("Data must be an object")
    category = str(data.get("category") or "").lower()
    if category not in CATEGORIES:
        raise ValueError("Unknown card category")
    legs = data.get("legs")
    if not isinstance(legs, list) or not 1 <= len(legs) <= 10:
        raise ValueError("Between 1 and 10 selections required")
    if (category in MULTI and len(legs) < 2) or (
            category not in MULTI and len(legs) != 1):
        raise ValueError("Wrong selection count for category")
    if data.get("synthetic") or data.get("estimated"):
        raise ValueError("Unverified sample tip forbidden")
    if float(data.get("stake_units", 1)) != 1:
        raise ValueError("Exactly 1 unit required")
    for i, leg in enumerate(legs, 1):
        if not isinstance(leg, dict):
            raise ValueError("Each selection must be an object")
        if not str(leg.get("match") or "").strip() or not str(leg.get("market") or "").strip():
            raise ValueError("Real fixture and market required")
        if not str(leg.get("bookmaker") or "").strip():
            raise ValueError("Observed bookmaker source required")
        if leg.get("estimated") or leg.get("odds_calculated"):
            raise ValueError("Calculated leg quote is not a book price")
        _odds(leg.get("bookmaker_odds"), "selection " + str(i))
        for field in ("player_photo", "team_logo"):
            if leg.get(field):
                path = Path(leg[field])
                if not path.is_file():
                    raise ValueError("Missing real image: " + field)
                with Image.open(path) as im:
                    im.verify()
    if category in MULTI:
        if data.get("combined_odds_observed") is not True or not str(
                data.get("combined_ticket_id") or "").strip():
            raise ValueError("Observed full bookmaker ticket required")
        if data.get("combined_odds_calculated") or data.get("price_type") in (
                "estimated", "calculated_from_leg_odds"):
            raise ValueError("Estimated book ticket forbidden")
        _odds(data.get("combined_odds"), "combined")
    p = data.get("model_probability")
    if p is not None and (not math.isfinite(float(p)) or not 0 <= float(p) <= 100):
        raise ValueError("Invalid model probability")
    return category, legs


def _asset(canvas, path, xy, size):
    if not path:
        return
    with Image.open(path) as source:
        rgba = source.convert("RGBA")
    if rgba.getextrema()[3][0] == 255:
        raise ValueError("Player/logo image must have a transparent background")
    rgba.thumbnail(size, Image.Resampling.LANCZOS)
    x, y = xy
    canvas.paste(rgba, (x + (size[0] - rgba.width) // 2,
                        y + (size[1] - rgba.height) // 2), rgba)


def render(master_path, data):
    category, legs = validate(data)
    path = Path(master_path)
    if path.resolve() == MASTER_PATH.resolve():
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != MASTER_SHA256:
            raise ValueError("Immutable NETRATTLER AI PREMIUM source hash mismatch")
    with Image.open(master_path) as source:
        if source.format != "PNG" or source.width != 1080 or source.height < 400:
            raise ValueError("Exact 1080px-wide approved PNG master required")
        master = source.convert("RGB")
    w = master.width
    row_height, gap, margin, header_height, footer_height = 176, 13, 43, 105, 220
    top = master.height + 32
    height = top + header_height + 25 + (row_height + gap) * len(legs) + footer_height + 48
    canvas = Image.new("RGB", (w, height), BG)
    canvas.paste(master, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.line((margin, master.height + 12, w-margin, master.height + 12), fill=GOLD, width=2)
    draw.rounded_rectangle((margin, top, w-margin, top+header_height),
                           radius=20, fill=PANEL, outline=GOLD, width=3)
    title = category.replace("_", " ").upper()
    if len(legs) > 1:
        title += " · " + str(len(legs)) + " AUSWAHLEN"
    title_font = _fit(draw, title, w-2*margin-48, 37)
    textw = draw.textbbox((0, 0), title, font=title_font)[2]
    draw.text(((w-textw)//2, top+31), title, font=title_font, fill=WHITE)
    y = top+header_height+25
    for leg in legs:
        draw.rounded_rectangle((margin, y, w-margin, y+row_height),
                               radius=17, fill=PANEL, outline=CYAN, width=2)
        _asset(canvas, leg.get("team_logo"), (margin+17, y+21), (96, 60))
        _asset(canvas, leg.get("player_photo"), (margin+17, y+83), (96, 78))
        x = margin+135
        width = w-x-margin-16
        for text, dy, color, fontsize in (
                (str(leg["match"]), 13, WHITE, 26),
                (str(leg["market"]), 57, GOLD, 27),
                (str(leg.get("player") or ""), 99, WHITE, 22),
                ("@" + format(_odds(leg["bookmaker_odds"], "leg"), ".2f")
                 + "   " + str(leg.get("form") or ""), 137, CYAN, 21)):
            if text.strip():
                draw.text((x, y+dy), text, font=_fit(draw, text, width, fontsize),
                          fill=color)
        y += row_height + gap
    draw.rounded_rectangle((margin, y+10, w-margin, y+footer_height),
                           radius=18, fill=PANEL, outline=GOLD, width=3)
    q = _odds(data["combined_odds"], "combined") if category in MULTI else _odds(
        legs[0]["bookmaker_odds"], "single")
    quote = "QUOTE: @" + format(q, ".2f") + " (BUCHMACHER)"
    probability = data.get("model_probability")
    textprob = "—" if probability is None else format(float(probability), ".1f") + "%"
    footer = (
        (quote, 25, GOLD, 28),
        ("MODELL-WAHRSCHEINLICHKEIT: " + textprob, 76, CYAN, 26),
        ("EINSATZ: 1 UNIT", 128, WHITE, 26),
        ("AUSWERTUNG: " + str(data.get("status") or "OFFEN"), 172, WHITE, 25),
    )
    for text, dy, color, size in footer:
        draw.text((margin+25, y+dy), text,
                  font=_fit(draw, text, w-2*margin-50, size), fill=color)
    if canvas.crop((0, 0, w, master.height)).tobytes() != master.tobytes():
        raise AssertionError("Source master pixels changed")
    return canvas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", default=MASTER_PATH, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = render(args.master, json.loads(args.data.read_text(encoding="utf-8")))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    result.save(args.out)
    print(json.dumps({"image": str(args.out), "size": result.size, "telegram_posted": False,
        "master_sha256": hashlib.sha256(args.master.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
