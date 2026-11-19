"""NETRATTLER GOAL HUNTER cards rendered over the approved neon artwork.

Every statistic and result remains dynamic; none is taken from the sample template.
"""
from __future__ import annotations

import io
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
BW, BH = 1122, 1402
TEMPLATE = Path(__file__).resolve().parent / "assets" / "goal_hunter_neon_frame.webp"
ORIGINAL_HEADER = Path(__file__).resolve().parent / "assets" / "goal_hunter_original_header.webp"
WHITE = (255, 255, 250)
GOLD = (255, 212, 30)
GREEN = (55, 250, 75)
RED = (255, 83, 75)


def font(size, italic=True):
    path = ("/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"
            if italic else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    return ImageFont.truetype(path, size)


def center(d, text, x, y, size, color=WHITE, max_width=None, italic=True, outline=2):
    text = str(text)
    f = font(size, italic)
    while max_width and d.textbbox((0, 0), text, font=f)[2] > max_width and size > 18:
        size -= 2
        f = font(size, italic)
    d.text((x, y), text, anchor="mm", font=f, fill=color,
           stroke_width=outline, stroke_fill=(0, 0, 0))


def wrap_team(d, text, x, y):
    words = str(text).upper().split()
    if not words:
        return
    if len(words) == 1:
        center(d, words[0], x, y, 32, max_width=340)
        return
    best = min(range(1, len(words)),
               key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    lines = (" ".join(words[:best]), " ".join(words[best:]))
    for line, yy in zip(lines, (y - 14, y + 17)):
        center(d, line, x, yy, 31, max_width=340)


def crest(team_id):
    """Retrieve an actual club logo by verified FotMob team ID, never approximate it."""
    if not team_id or not str(team_id).isdigit():
        return None
    url = f"https://images.fotmob.com/image_resources/logo/teamlogo/{team_id}.png"
    try:
        response = requests.get(url, timeout=10, headers={"Accept": "image/png,image/*"})
        response.raise_for_status()
        if (not response.headers.get("Content-Type", "").startswith("image/")
                or len(response.content) > 1_000_000):
            return None
        image = Image.open(io.BytesIO(response.content)).convert("RGBA")
        image.thumbnail((211, 211), Image.Resampling.LANCZOS)
        return image
    except (requests.RequestException, OSError, ValueError):
        return None


def _stats(d, metrics, *, next_team=False):
    teams = (metrics or {}).get("teams") or {}
    home, away = teams.get("home") or {}, teams.get("away") or {}
    if home and away:
        center(d, "TEAMSTATISTIK", 567, 879 if next_team else 842,
               37 if next_team else 40, WHITE, max_width=590)
        rows = [("SCHÜSSE", "shots"), ("AUFS TOR", "sot"), ("ECKEN", "corners")]
        if home.get("xg") is not None and away.get("xg") is not None:
            rows.append(("xG", "xg"))
        for i, (label, key) in enumerate(rows):
            y = (930 + i * 51) if next_team else (913 + i * 60)
            left = home.get(key)
            right = away.get(key)
            def val(n):
                return "–" if n is None else (f"{n:.2f}" if key == "xg" else str(n))
            center(d, val(left), 231, y, 37 if next_team else 42,
                   WHITE, max_width=154)
            center(d, label, 556, y, 30 if next_team else 34,
                   GOLD, max_width=310)
            center(d, val(right), 872, y, 37 if next_team else 42,
                   WHITE, max_width=155)
            if i < len(rows)-1:
                d.line((346, y+28, 780, y+28), fill=(169, 117, 25), width=2)
    else:
        center(d, "GESAMTSTATISTIK", 560, 882 if next_team else 826, 37, WHITE)
        for i, (label, key) in enumerate((("SCHÜSSE", "shots"), ("AUFS TOR", "sot"), ("ECKEN", "corners"))):
            val = (metrics or {}).get(key)
            if val is not None:
                center(d, label, 421, (944+i*54) if next_team else (914+i*66), 34, GOLD)
                center(d, str(val), 742, (944+i*54) if next_team else (914+i*66), 43, WHITE)


def make_card(fixture, metrics=None, *, final_score=None, won=None,
              next_goal_side=None, next_goal_result=None):
    """Premium LAST MINUTE GOAL card (JPEG bytes). Real FotMob crests only."""
    from netrattler_premium_extra import render_lmg

    def provider(team):
        side = "home_logo_id" if team == str(fixture["home"]) else "away_logo_id"
        badge = crest(fixture.get(side))
        if badge is None:
            raise ValueError("Real club crest missing: no placeholder allowed")
        out = io.BytesIO()
        badge.save(out, "PNG")
        return out.getvalue()

    png = render_lmg(fixture, metrics, provider, final_score=final_score, won=won,
                     next_goal_side=next_goal_side, next_goal_result=next_goal_result)
    im = Image.open(io.BytesIO(png)).convert("RGB")
    out = io.BytesIO()
    im.save(out, format="JPEG", quality=92, optimize=True)
    return out.getvalue()
