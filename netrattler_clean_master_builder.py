"""Produce CLEAN, EMPTY, owner-DERIVED QA masters for the ten missing categories.

These masters preserve a real source card's crown/frame artwork but rebuild
its data-bearing centre. They are NOT additional user-uploaded originals and
must NOT be enabled for production without visual approval. No Telegram I/O.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
W, H = 1122, 1402
SOURCE_DIR = ROOT / "assets" / "original_templates"
SOURCE_MAP = {
    "over": SOURCE_DIR / "NETRATTLER_BTTS_originalkarte.png",
    "btts_halftime": SOURCE_DIR / "NETRATTLER_BTTS_originalkarte.png",
    "over_halftime": SOURCE_DIR / "NETRATTLER_BTTS_originalkarte.png",
    "match_result": SOURCE_DIR / "NETRATTLER_BTTS_originalkarte.png",
    "player_props": SOURCE_DIR / "goal_hunter_original.webp",
    "fouls_cards": SOURCE_DIR / "goal_hunter_original.webp",
    "var": ROOT / "assets" / "netrattler_template_corner_original.webp",
    "last_minute_goal": ROOT / "assets" / "netrattler_template_corner_original.webp",
    "late_goals": ROOT / "assets" / "netrattler_template_corner_original.webp",
    "live_halftime": SOURCE_DIR / "NETRATTLER_BTTS_originalkarte.png",
    "cross_mix": SOURCE_DIR / "NETRATTLER_COMBO_7_originalkarte.png",
}
TITLE = {
    "over": "OVER 1.5 / 2.5 / 3.5",
    "btts_halftime": "BTTS HALBZEIT",
    "over_halftime": "OVER 1.5 HALBZEIT",
    "match_result": "1X2 / DOUBLE CHANCE",
    "player_props": "PLAYER PROPS",
    "fouls_cards": "FOULS / TACKLES / KARTEN",
    "var": "VAR",
    "last_minute_goal": "LAST MINUTE GOAL",
    "late_goals": "LATE GOALS",
    "live_halftime": "LIVE HALBZEIT",
    "cross_mix": "CROSS / MIX",
}
LABELS = {
    "over": ("OVER 1.5", "OVER 2.5", "OVER 3.5"),
    "btts_halftime": ("BEIDE TEAMS TREFFEN", "HEIM / AUSW", "1. HALBZEIT"),
    "over_halftime": ("TORLINIE", "HEIM / AUSW", "1. HALBZEIT"),
    "match_result": ("HEIMSIEG", "UNENTSCHIEDEN", "AUSWAERTSSIEG"),
    "player_props": ("MARKT / LINIE", "L5 / L10 / L15", "SPIELER"),
    "fouls_cards": ("FOULS", "TACKLES", "KARTEN"),
    "var": ("BUCHMACHER-REGEL", "ANSTOSS / EVENT", "VAR-MARKT"),
    "last_minute_goal": ("SPIELMINUTE / SCORE", "LIVE-DRUCK", "TORCHANCE"),
    "late_goals": ("TORE AB 75'", "LIVE-DRUCK", "FORM L10"),
    "live_halftime": ("SPIELSTAND", "SCHUESSE / XG", "BALLBESITZ"),
    "cross_mix": ("AUSWAHL 1", "AUSWAHL 2", "AUSWAHL 3"),
}

def _font(size=32):
    for name in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()

def _fitted(draw, value, max_width, initial):
    size = initial
    while size >= 18 and draw.textbbox((0, 0), value, font=_font(size))[2] > max_width:
        size -= 1
    if size < 18:
        raise ValueError("Category heading exceeds clean-master space")
    return _font(size)

def _source(path):
    if not path.exists():
        raise FileNotFoundError("User-sourced original missing: " + path.name)
    with Image.open(path) as original:
        original.load()
        if min(original.size) < 500:
            raise ValueError("Original source has insufficient resolution")
        result = original.convert("RGBA").resize((W, H), Image.Resampling.LANCZOS)
    return result

def render_clean_master(category):
    if category not in SOURCE_MAP:
        raise ValueError("No owner-derived source mapping for category: " + str(category))
    source_path = SOURCE_MAP[category]
    original = _source(source_path)
    result = original.copy()

    # Preserve the authentic owner-image perimeter, top crown, and lighting.
    # Mask ALL baked-in sample faces, match crests, names, prices, results,
    # old category titles, and demo statistics in the interior.
    interior = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    p = ImageDraw.Draw(interior)
    p.rounded_rectangle((78, 145, 1044, 1307), radius=18,
                        fill=(3, 16, 29, 255))
    # Blue stadium glass is category-specific, but has no fake sports data.
    for i in range(13):
        y = 258 + i * 70
        p.line((99, y, 1023, y), fill=(20, 98 + (i % 3) * 15, 145, 40), width=2)
    for x in (92, 1030):
        p.line((x, 166, x, 1300), fill=(26, 213, 249, 180), width=6)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((45, 170, 610, 760), fill=(0, 100, 185, 42))
    gd.ellipse((510, 370, 1110, 930), fill=(0, 160, 185, 32))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    interior = Image.alpha_composite(interior, glow)
    result = Image.alpha_composite(result, interior)
    # Preserve the uploaded owner's crown/header pixel-for-pixel even when
    # the background stadium glow reaches the top of the canvas.
    result.paste(original.crop((0, 0, W, 140)), (0, 0))

    draw = ImageDraw.Draw(result)
    draw.rounded_rectangle((145, 163, 977, 275), radius=23,
                           fill="#061421", outline="#FDD348", width=5)
    title = TITLE[category]
    draw.text((561, 215), title, font=_fitted(draw, title, 794, 51),
              anchor="mm", fill="#FFE56C",
              stroke_width=2, stroke_fill="#1A1010")
    draw.rounded_rectangle((131, 330, 991, 596), radius=22,
                           fill="#071926", outline="#25DFFF", width=4)
    # Owner rule for all eleven derived categories: REAL team crests
    # FLOAT freely over the existing dark fixture stadium. Do NOT
    # manufacture gold-outlined crest rectangles, circles, shields, or
    # name-stickers here. These spaces stay EMPTY until genuine provider
    # PNG/WebP artwork is alpha-composited by the verified card renderer.
    # The central VS/fixture field is text-only and does not touch them.
    draw.rounded_rectangle((369, 387, 753, 528), radius=16,
                           fill="#0A1A2A", outline="#136B91", width=2)

    slots = {}
    for i, label in enumerate(LABELS[category]):
        y = 638 + i * 142
        rect = (131, y, 991, y + 114)
        draw.rounded_rectangle(rect, radius=18, fill="#081A29",
                               outline="#25CFF4", width=3)
        draw.text((157, y + 28), label, font=_fitted(draw, label, 480, 27),
                  fill="#F4D05D")
        slots["stat_" + str(i + 1)] = {"x": 555, "y": y + 24, "width": 388,
                                    "height": 66}
    draw.rounded_rectangle((135, 1102, 986, 1233), radius=24,
                           fill="#251B0A", outline="#EAC441", width=5)
    draw.text((190, 1146), "TIPP / QUOTE",
              font=_font(32), fill="#F9E49A")
    draw.rounded_rectangle((350, 1241, 772, 1299), radius=18,
                           fill="#03121F", outline="#20DFFF", width=3)
    # Repaint the complete original footer region so no old handles/results
    # from the source can survive. The outer pixel-art rim stays intact.
    draw.rounded_rectangle((100, 1310, 1022, 1383), radius=16,
                           fill="#06131F", outline="#1DCFF2", width=3)
    draw.text((561, 1347), "@prophunter", anchor="mm",
              font=_font(39), fill="#FCFCFF")

    out = io.BytesIO()
    result.convert("RGB").save(out, "PNG", optimize=True)
    data = out.getvalue()
    return data, {
        "category": category,
        "source_file": source_path.name,
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "classification": "owner-derived_clean_QA_NOT_user_original",
        "production_approved": False,
        "required_dynamic_fields": [
            "verified_fixture", "real_crests_or_player_photo_if_relevant",
            "verified_selection", "real_bookmaker_odds", "market_statistics",
        ],
        "blank_slots": slots,
        # These are empty coordinate reservations, not visible logo holders.
        # No placeholder emblem may be drawn if either authentic crest fails.
        "floating_crest_slots": [
            {"center_x": 250, "center_y": 456, "max_width": 194, "max_height": 195},
            {"center_x": 872, "center_y": 456, "max_width": 194, "max_height": 195},
        ],
        "logo_backplates": False,
        "size": [W, H],
    }

def write_all(outdir):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for category in SOURCE_MAP:
        png, info = render_clean_master(category)
        (outdir / (category + "_CLEAN_DERIVED_QA.png")).write_bytes(png)
        manifest.append(info)
    (outdir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default="output/netrattler_clean_masters")
    args = parser.parse_args()
    built = write_all(args.outdir)
    print("Clean QA masters:", len(built),
          "- not approved owner originals; Telegram not touched")
