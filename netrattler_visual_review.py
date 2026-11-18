"""NETRATTLER image-level visual quality assurance (read-only, before send).

Inspect the actual encoded PNG, not just its input data. Check card geometry,
leg rows, photo/crest content, title, numeric values, form and footer. A failed
review blocks Telegram publication. It does *not* authenticate a player's
identity or a bookmaker price; those checks are separate in visual_gate.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import List

from PIL import Image, ImageStat


@dataclass
class Review:
    kind: str
    passed: bool
    problems: List[str] = field(default_factory=list)
    checks: int = 0

    def describe(self):
        return ("PASS" if self.passed else "FAIL") + " " + self.kind + (
            " " + ",".join(self.problems) if self.problems else ""
        )


def _light(rgb):
    r, g, b = rgb[:3]
    return min(r, g, b) >= 130 and max(r, g, b) - min(r, g, b) < 100


def _gold(rgb):
    r, g, b = rgb[:3]
    return r >= 175 and g >= 105 and b < 0.88 * g and r >= g


def _green(rgb):
    r, g, b = rgb[:3]
    return g >= 150 and g >= r * 1.30 and g >= b * 1.10


def _cyan(rgb):
    r, g, b = rgb[:3]
    return b >= 135 and g >= 135 and b >= r * 1.15


def _color_count(im, box, predicate):
    patch = im.crop(tuple(int(x) for x in box))
    # Keep inspection bounded on mobile-sized PNGs.
    return sum(1 for p in list(patch.getdata())[::4] if predicate(p))


def _texture(im, box):
    patch = im.crop(tuple(int(x) for x in box)).convert("RGB")
    stat = ImageStat.Stat(patch)
    return sum(stat.stddev)


def _review_user_master(im, kind, legs):
    """Check original user artwork and all freshly rendered dynamic regions."""
    from PIL import ImageChops
    from netrattler_original_template_renderer import _base, BUILDER_IMAGE, GOAL_IMAGE
    problems=[]
    checks=0
    def check(ok,label):
        nonlocal checks
        checks+=1
        if not ok: problems.append(label)
    expected=(1122,{2:994,4:1194,6:1402}.get(legs,0)) if kind=="builder" else (1122,1402)
    check(im.size==expected,"master_dimensions")
    if im.size!=expected: return Review(kind,False,problems,checks)
    source=_base(str(BUILDER_IMAGE if kind=="builder" else GOAL_IMAGE))
    check(ImageChops.difference(im.crop((0,0,1122,170)),
                               source.crop((0,0,1122,170))).getbbox() is None,
          "user_original_header_was_redrawn")
    def count(box,tone,label):
        check(_color_count(im,box,tone)>7,label)
    def edited(box,label):
        change=ImageChops.difference(im.crop(box),source.crop(box))
        # Any nontrivial pixel change confirms the user's baked-in demo asset
        # was replaced; portraits can share similar colors without being identical.
        check(sum(ImageStat.Stat(change).mean)>5,label)
    if kind=="builder":
        count((324,273,800,309),_light,"kickoff")
        count((230,322,634,385),_light,"legs")
        for i in range(legs):
            y=409+i*100
            edited((106,y+4,225,y+76),f"player_photo_replaced_{i+1}")
            check(_texture(im,(106,y+4,225,y+76))>18,f"photo_texture_{i+1}")
            check(_texture(im,(278,y+9,339,y+74))>12,f"crest_texture_{i+1}")
            count((370,y+3,741,y+41),_light,f"player_name_{i+1}")
            count((382,y+42,740,y+85),_gold,f"market_{i+1}")
            count((805,y+5,1053,y+84),_green,f"l10_l15_{i+1}")
        dy=0 if legs==6 else 405+100*legs-1013
        count((839,1203+dy,1053,1267+dy),
              lambda p:_green(p) or _gold(p) or (p[0]>185 and p[1]<135),
              "builder_settlement")
        check(1270+dy<im.height-20,"builder_footer_clipped")
    else:
        edited((343,830,781,859),"scorer_kickoff_displayed")
        edited((395,376,703,582),"scorer_photo_replaced")
        check(_texture(im,(395,376,703,582))>22,"scorer_photo_texture")
        check(_texture(im,(105,447,261,593))>12,"home_badge")
        check(_texture(im,(835,447,997,593))>12,"away_badge")
        count((252,759,850,828),_light,"scorer_name")
        for label,box,tone in [
            ("scorer_odds",(53,943,269,1018),_gold),
            ("scorer_model",(327,943,543,1018),_green),
            ("scorer_fair",(588,943,797,1018),_gold),
            ("goals_per_match",(853,943,1068,1018),_gold)]:
            count(box,tone,label)
        count((460,1215,643,1280),
              lambda p:_green(p) or _gold(p) or (p[0]>185 and p[1]<130),
              "scorer_settlement")
    return Review(kind,not problems,problems,checks)


def review_png(payload: bytes, kind: str, *, legs: int = 0) -> Review:
    problems, count = [], 0

    def check(ok, code):
        nonlocal count
        count += 1
        if not ok:
            problems.append(code)

    try:
        with Image.open(io.BytesIO(payload)) as parsed:
            if parsed.format != "PNG":
                return Review(kind, False, ["not_png"], 1)
            parsed.load()
            im = parsed.convert("RGB")
    except (OSError, ValueError, TypeError):
        return Review(kind, False, ["invalid_image"], 1)

    w, h = im.size
    if w == 1122 and kind in ("builder", "scorer"):
        return _review_user_master(im, kind, legs)
    if kind == "builder":
        if not 2 <= legs <= 6:
            return Review(kind, False, ["leg_count"], 1)
        check((w, h) == (1200, 650 + 160 * legs), "dimensions")
    elif kind == "scorer":
        check((w, h) == (1080, 1340), "dimensions")
    else:
        return Review(kind, False, ["unknown_card_type"], 1)

    if problems:
        return Review(kind, False, problems, count)

    def text(box, tone, label, minimum=8):
        check(_color_count(im, box, tone) >= minimum, label)

    text((w * .25, 33, w * .75, 113), _light, "logo_text")
    text((w * .22, 123, w * .78, 183), _gold, "gold_title_ribbon", 20)
    check(_texture(im, (20, 190, w - 20, min(295, h - 1))) >= 12,
          "empty_stadium_header")

    if kind == "builder":
        text((345, 258, 845, 304), _light, "kickoff_text")
        text((120, 311, 670, 346), _light, "leg_count_text")
        for i in range(legs):
            y = 362 + 160 * i
            check(_texture(im, (74, y + 24, 139, y + 116)) >= 25,
                  f"photo_{i + 1}")
            check(_texture(im, (190, y + 42, 239, y + 101)) >= 16,
                  f"crest_{i + 1}")
            text((285, y + 18, 799, y + 56), _light, f"player_name_{i + 1}")
            text((285, y + 70, 800, y + 109), _gold, f"market_{i + 1}")
            text((884, y + 28, 1143, y + 66), _green, f"l10_{i + 1}")
            text((884, y + 75, 1143, y + 114), _green, f"l15_{i + 1}")
        y = 362 + 160 * legs
        for index, tone in enumerate((_gold, _green, None)):
            x = 30 + index * 393
            text((x + 26, y + 51, x + 342, y + 105),
                 tone or (lambda p: _green(p) or _gold(p)),
                 ("bookmaker_quote", "model_probability", "ev")[index])
        text((79, y + 143, 520, y + 192), _gold, "confidence")
        text((629, y + 143, 1143, y + 192),
             lambda p: _gold(p) or _green(p), "settlement_footer")
        check(y + 203 < h - 45, "footer_clipped")
    else:
        check(_texture(im, (416, 343, 665, 611)) >= 37, "scorer_photo")
        check(_texture(im, (82, 440, 243, 580)) >= 17, "home_crest")
        check(_texture(im, (845, 440, 997, 580)) >= 17, "away_crest")
        text((246, 746, 840, 803), _light, "scorer_name")
        for i, tone in enumerate((_gold, _green, _gold, _gold)):
            x = 25 + 268 * i
            text((x + 13, 919, x + 230, 1000), tone,
                 ("scorer_quote", "scorer_probability", "fair_quote", "goals_per_game")[i])
        text((92, 1200, 706, 1257),
             lambda p: _gold(p) or _green(p), "scorer_settlement")
        check(1264 < h - 35, "footer_clipped")

    return Review(kind, not problems, problems, count)
