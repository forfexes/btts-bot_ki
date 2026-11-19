"""Small shared drawing helpers for premium cards (no network, no Telegram)."""
from __future__ import annotations

import io
import math

from PIL import Image, ImageFont

GOLD, CYAN, WHITE, GREEN, RED = "#FFE16A", "#27E6FF", "#FAFCFF", "#3AFD75", "#FF6C6C"


def font(size=28):
    for name in ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def fit_font(draw, text, maxwidth, size=26):
    text = str(text or "").strip()
    for n in range(size, 13, -1):
        f = font(n)
        if draw.textbbox((0, 0), text, font=f)[2] <= maxwidth:
            return f
    raise ValueError("Text would overflow premium layout: " + text[:40])


def crest_image(raw):
    if not isinstance(raw, (bytes, bytearray)) or len(raw) < 150:
        raise ValueError("Real image missing: no placeholders allowed")
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
    except (OSError, ValueError) as exc:
        raise ValueError("Invalid genuine image") from exc
    if min(im.size) < 24:
        raise ValueError("Image has insufficient resolution")
    return im.convert("RGBA")


def number(value):
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        n = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def price(tip):
    for key in ("oddsYes", "odds", "odd", "price", "bookmaker_odds"):
        n = number(tip.get(key))
        if n is not None and 1.01 <= n <= 1000:
            return n
    raise ValueError("Verified original bookmaker odds missing")


def split_match(name):
    name = str(name or "")
    for sep in (" vs ", " - "):
        if sep in name:
            home, away = [p.strip() for p in name.split(sep, 1)]
            if home and away and home != away:
                return home, away
    raise ValueError("Two verified club names required")


def status_text(result):
    mark = None
    if isinstance(result, dict):
        marks = result.get("marks") or {}
        mark = marks.get("0") if isinstance(marks, dict) else None
        mark = mark or result.get("status")
    return {"win": ("GEWONNEN", GREEN), "won": ("GEWONNEN", GREEN),
            "loss": ("VERLOREN", RED), "lost": ("VERLOREN", RED),
            "void": ("VOID", GOLD)}.get(str(mark).lower(), ("OFFEN", GOLD))
