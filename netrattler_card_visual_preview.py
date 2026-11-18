#!/usr/bin/env python3
"""Offline reference PNGs for GitHub Actions card visual review.

Synthetic illustration, fictional fixtures and numbers; NEVER published to
Telegram. These are geometry samples, not bookmaker/player data.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageDraw

import netrattler_neon_design as neon
import netrattler_stats_match_cards as cards
from netrattler_visual_review import review_png


def fake_headshot():
    pic = Image.new("RGB", (200, 230), "#194D6B")
    dr = ImageDraw.Draw(pic)
    for y in range(230):
        dr.line((0, y, 200, y), fill=(15 + y // 10, 40 + y // 5, 80 + y // 12))
    dr.ellipse((35, 12, 165, 145), fill="#C68C64", outline="#4A2A25", width=5)
    dr.ellipse((60, 140, 142, 192), fill="#DAA17A")
    dr.polygon(((0, 230), (20, 173), (185, 168), (200, 230)), fill="#C9192E")
    dr.line((15, 200, 189, 200), fill="#F8F7E7", width=7)
    for x in (66, 121):
        dr.ellipse((x, 72, x + 8, 80), fill="#33231B")
    mem = io.BytesIO()
    pic.save(mem, "PNG")
    return mem.getvalue()


def fake_badge(im, draw, team, rect, font):
    x0, y0, x1, y1 = map(int, rect)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    rad = min(x1 - x0, y1 - y0) // 2
    draw.ellipse((cx - rad, cy - rad, cx + rad, cy + rad),
                 fill="#E8F7FF", outline="#CF971D", width=7)
    draw.polygon(((cx, cy - rad // 2), (cx - rad // 2, cy),
                  (cx, cy + rad // 2), (cx + rad // 2, cy)),
                 fill="#B2192F", outline="#081828")
    draw.ellipse((cx - 7, cy - 7, cx + 7, cy + 7), fill="#F5D866")


def demo_legs(count):
    options = [
        ("Spieler Alpha", "shots", 2, "Shots"),
        ("Spieler Beta", "sot", 1, "Shots on Target"),
        ("Spieler Gamma", "tackles_committed", 2, "Tackles"),
        ("Spieler Delta", "fouls_won", 1, "Fouls Won"),
        ("Spieler Epsilon", "shots", 3, "Shots"),
        ("Spieler Zeta", "sot", 1, "Shots on Target"),
    ]
    return [SimpleNamespace(player=name,
        team=("Beispiel FC" if i % 2 == 0 else "Test United"),
        match="Beispiel FC vs Test United", kickoff="2099-05-21T17:30:00+00:00",
        league="Demo League", category=cat, line=line, market=market,
        odds=1.5 + i / 10, source="test_only", estimated=False, quality=.78,
        probability=.62, hit_rate=.75,
        series=[3, 2, 1, 4, 2, 3, 3, 2, 1, 3, 2, 4, 3, 2, 1])
        for i, (name, cat, line, market) in enumerate(options[:count])]


def generate(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    fake_photo = fake_headshot()
    report = {}
    with patch.object(cards, "_player_photo", return_value=fake_photo), \
         patch.object(cards, "_paste_badge", side_effect=fake_badge):
        for count in (2, 4, 6):
            p = SimpleNamespace(legs=demo_legs(count), match_date="2099-05-21",
                tiers=[], model_only=False, combined_quote_verified=True,
                combined_bookmaker_quote=round(3.4 * count, 2),
                joint_probability=.23, status="pending", confidence="HOCH")
            raw = neon.render_builder_card(p)
            result = review_png(raw, "builder", legs=count)
            name = f"TEST_ONLY_builder_{count}leg.png"
            (directory / name).write_bytes(raw)
            report[name] = {"passed":result.passed,"checks":result.checks,
                            "problems":result.problems}
        tip = {"match":"Beispiel FC vs Test United", "player":"Spieler Alpha",
               "team":"Beispiel FC", "league":"Demo League", "odds":4.5,
               "probability":27, "fairOdds":3.7, "goals_per_game":0.33}
        raw = neon.render_scorer_card(tip, "2099-05-21")
        result = review_png(raw, "scorer")
        filename = "TEST_ONLY_goal_hunter.png"
        (directory / filename).write_bytes(raw)
        report[filename] = {"passed":result.passed,
                            "checks":result.checks,"problems":result.problems}
    (directory / "review.json").write_text(json.dumps(report,indent=2), encoding="utf-8")
    (directory / "README.txt").write_text(
        "Nur interne Gestaltungsvorschau: synthetische Fotos, Fantasiespieler, "
        "keine echten Buchmacherquoten. NIE auf Telegram veröffentlichen.\n",
        encoding="utf-8")
    print(json.dumps(report))
    if not all(info["passed"] for info in report.values()):
        raise SystemExit("Visual card review failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default="visual_review_previews")
    generate(parser.parse_args().outdir)
