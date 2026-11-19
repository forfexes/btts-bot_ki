"""Strict, data-filled premium SVG card renderer for all 16 categories.

This is a separate opt-in renderer; existing Telegram publishing is unchanged.
It refuses unverified odds and missing required values rather than inventing data.
"""
import io
import math
from pathlib import Path
from xml.etree import ElementTree as ET

from netrattler_premium_compact import ASSETS, NS, compact_master

CATEGORIES = (
    "builder", "goal", "corner", "btts", "over", "btts_halftime",
    "over_halftime", "match_result", "combo", "player_props",
    "fouls_cards", "var", "last_minute_goal", "late_goals",
    "live_halftime", "cross_mix",
)
ET.register_namespace("", NS)


def _verified_leg(leg):
    if not isinstance(leg, dict):
        raise ValueError("Each leg must be a dict")
    if leg.get("estimated") or leg.get("synthetic") or leg.get("model_odds"):
        raise ValueError("Estimated odds are forbidden")
    team = str(leg.get("match") or "").strip()
    market = str(leg.get("market") or "").strip()
    if not team or not market:
        raise ValueError("Confirmed match and market required")
    raw = leg.get("bookmaker_odds")
    try:
        odds = float(raw)
    except (ValueError, TypeError):
        raise ValueError("Real bookmaker odds required") from None
    if not math.isfinite(odds) or odds <= 1:
        raise ValueError("Invalid bookmaker odds")
    if not str(leg.get("bookmaker") or "").strip():
        raise ValueError("Bookmaker source required")
    return team, market, odds


def _add_text(root, x, y, value, size=27, color="#FAFCFF"):
    element = ET.SubElement(root, f"{{{NS}}}text", {
        "x": str(x), "y": str(y), "font-family": "DejaVu Sans,sans-serif",
        "font-size": str(size), "fill": color,
    })
    element.text = value


def render_verified_svg(category, legs):
    """Build a card with verified labels/odds; not yet the production Telegram route.

    Multi-row layouts support Builder 3..6 and Combo 3..10. Single-row
    categories require exactly one selection.
    """
    if category not in CATEGORIES:
        raise ValueError("Unknown premium category")
    if not isinstance(legs, (list, tuple)) or not legs:
        raise ValueError("At least one verified selection required")
    if category in ("builder", "combo"):
        master = compact_master(category, len(legs))
    else:
        if len(legs) != 1:
            raise ValueError("Single-selection category cannot contain multiple legs")
        master = (ASSETS / f"premium_{category}_blank.svg").read_bytes()
    verified = [_verified_leg(leg) for leg in legs]
    root = ET.fromstring(master)
    # The footer uses the same x/width as a selection. Identify rows by
    # their slot height instead of a canvas-relative y threshold.
    rows = sorted((e for e in root.findall(f"{{{NS}}}rect")
                   if e.get("x") == "42" and e.get("width") == "1038"
                   and float(e.get("height", "0")) < 120),
                  key=lambda e: float(e.get("y")))
    if len(rows) < len(verified):
        raise ValueError("Master lacks sufficient selection rows")
    for i, (match, market, odds) in enumerate(verified):
        y = int(float(rows[i].get("y")))
        # Fit within the actual slot; no logos or portraits are invented.
        if len(match) > 47 or len(market) > 44:
            raise ValueError("Selection text too long for verified card")
        short = float(rows[i].get("height")) < 80
        _add_text(root, 66, y + (25 if short else 34), match, 20 if short else 24)
        _add_text(root, 66, y + (51 if short else 69), market, 19 if short else 23, "#FFE16A")
        _add_text(root, 927, y + (43 if short else 56), f"@ {odds:.2f}", 24, "#40F58A")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def render_verified_png(category, legs):
    """Rasterize verified selections to a PNG, without sending Telegram."""
    import cairosvg
    from PIL import Image
    png = cairosvg.svg2png(bytestring=render_verified_svg(category, legs))
    with Image.open(io.BytesIO(png)) as im:
        output = io.BytesIO()
        im.convert("RGB").save(output, "PNG")
        return output.getvalue()
