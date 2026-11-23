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
    if isinstance(team_id, str) and team_id.startswith("https://"):
        # Accept only the official ESPN crest CDN; never fetch arbitrary URLs.
        from urllib.parse import urlsplit
        parsed = urlsplit(team_id)
        if parsed.netloc not in ("a.espncdn.com", "a.espncdn.com:443"):
            return None
        url = team_id
    elif team_id and str(team_id).isdigit():
        url = f"https://images.fotmob.com/image_resources/logo/teamlogo/{team_id}.png"
    else:
        return None
    try:
        response = requests.get(url, timeout=10, headers={"Accept": "image/png,image/*"})
        response.raise_for_status()
        if (not response.headers.get("Content-Type", "").startswith("image/")
                or len(response.content) > 1_000_000):
            return None
        with Image.open(io.BytesIO(response.content)) as source:
            source.load()
            image = source.convert("RGBA")
        # ESPN/FotMob can serve JPEG-like logo tiles with an opaque white
        # rectangle. They are not free-floating team emblems. The original
        # team artwork must contain transparency, not a painted replacement.
        alpha=image.getchannel("A")
        if alpha.getextrema()[0]>=255:
            return None
        visible=alpha.point(lambda a:255 if a>=24 else 0).getbbox()
        if visible is None:
            return None
        image=image.crop(visible)
        if min(image.size)<12:
            return None
        scale=min(211/image.width,211/image.height)
        if scale>4:
            return None
        image=image.resize((max(1,round(image.width*scale)),
                            max(1,round(image.height*scale))),
                           Image.Resampling.LANCZOS)
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
    """Open: verified team statistics; finished: only verified final score and outcome."""
    if not TEMPLATE.is_file():
        raise RuntimeError("Approved GOAL HUNTER neon template missing")
    with Image.open(TEMPLATE) as source:
        if source.size != (BW, BH):
            raise RuntimeError("Goal Hunter artboard dimensions do not match the approved design")
        im = source.convert("RGB")
    d = ImageDraw.Draw(im)
    center(d, fixture.get("league") or "Fussball", 588, 280, 34, max_width=600)
    home, away = str(fixture["home"]), str(fixture["away"])
    for side, x, logo_id in ((home, 215, fixture.get("home_logo_url") or fixture.get("home_logo_id")),
                             (away, 891, fixture.get("away_logo_url") or fixture.get("away_logo_id"))):
        badge = crest(logo_id)
        if badge is None:
            raise ValueError(
                f"Verified team crest missing for {side!r}; do not publish a placeholder card"
            )
        im.paste(badge, (x - badge.width // 2, 411 - badge.height // 2), badge)
        wrap_team(d, side, x, 574)
    if final_score is None:
        center(d, f"{fixture['minute']}. MINUTE", 565, 367, 39, GOLD, max_width=225)
        score = f"{fixture['hg']}:{fixture['ag']}"
    else:
        center(d, "ENDRESULTAT", 565, 367, 35, GOLD, max_width=225)
        score = str(final_score)
    center(d, score, 564, 465, 100, WHITE, max_width=302, italic=True, outline=3)
    if next_goal_side is None:
        next_goal_side = (metrics or {}).get("next_goal_side")
    if next_goal_side not in (None, "home", "away"):
        raise ValueError("Unsupported next-goal team selection")
    # The live bet line is a fixed market; only the tier is dynamic.
    center(d, (metrics or {}).get("tier") or "STANDARD", 853, 734, 32, GOLD, max_width=240)
    if final_score is None:
        _stats(d, metrics, next_team=bool(next_goal_side))
        if next_goal_side:
            next_name = home if next_goal_side == "home" else away
            center(d, "NÄCHSTES TOR: " + next_name, 565, 833, 29, GOLD,
                   max_width=855)
        center(d, "AUSWERTUNG: OFFEN", 602, 1204, 47, GOLD, max_width=815)
    else:
        # Final image: a clean, two-column tip snapshot. The main green/red
        # result below refers ONLY to Over 0.5 Restspielzeit.
        d.rounded_rectangle((100, 814, 1001, 1111), radius=18, fill=(4, 13, 20))
        d.line((560, 847, 560, 986), fill=(39, 148, 180), width=3)
        center(d, "TIPP-ZEITPUNKT", 322, 870, 33, GOLD, max_width=390)
        center(d, f"{fixture['minute']}. MINUTE", 322, 943, 58, WHITE, max_width=405)
        center(d, "SPIELSTAND BEIM TIPP", 782, 870, 29, GOLD,
               max_width=394)
        center(d, f"{fixture['hg']}:{fixture['ag']}", 782, 943, 70, WHITE,
               max_width=280)

        # Only evaluate a next-goal pick when that side was on the ORIGINAL
        # Telegram tip. This row is separate from the main Over 0.5 result.
        if next_goal_side is not None:
            if next_goal_result is None:
                raise ValueError("Original next-goal pick requires a separate verified grade")
            next_name = home if next_goal_side == "home" else away
            wording = {"won": "✓ RICHTIG", "lost": "✕ FALSCH",
                       "void": "KEIN WEITERES TOR",
                       "unverified": "NICHT VERIFIZIERT",
                       None: "NOCH OFFEN"}.get(next_goal_result)
            if wording is None:
                raise ValueError("Invalid next-goal result")
            tint = (GREEN if next_goal_result == "won"
                    else RED if next_goal_result == "lost" else WHITE)
            d.rounded_rectangle((132, 993, 969, 1097), radius=17,
                                fill=(6, 22, 28),
                                outline=tint, width=3)
            center(d, "NÄCHSTES TOR: " + next_name, 560, 1027, 29, WHITE,
                   max_width=795)
            center(d, wording, 560, 1070, 34, tint, max_width=760)
        if won is not True and won is not False:
            raise ValueError("Final result requires a verified win/loss")
        color = GREEN if won else RED
        if not won:
            for expand in (0, 5, 10):
                d.rounded_rectangle((50-expand, 1159-expand, 1061+expand,
                                     1260+expand), radius=25,
                                    outline=(220 if expand == 0 else 96, 38, 36),
                                    width=5)
        center(d, ("✓ GEWONNEN" if won else "✕ VERLOREN"),
               603, 1204, 57, color, max_width=790)
    out = io.BytesIO()
    im.resize((W, H), Image.Resampling.LANCZOS).save(out, format="JPEG", quality=91, optimize=True)
    return out.getvalue()