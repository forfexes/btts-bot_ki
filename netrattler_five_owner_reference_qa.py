"""Five remaining NETRATTLER owner-reference poster drafts (offline, no Telegram).

These use only the five actual, versioned original screenshots to create
clean, data-free QA backgrounds. This is NOT approval to publish; the
unmodified source remains the only owner-original reference.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from netrattler_clean_master_builder import ROOT, render_clean_master_from_reference

BASE = ROOT / "assets" / "original_templates"

SPECS = {
    "btts": (
        BASE / "NETRATTLER_BTTS_originalkarte.png",
        "BTTS · BEIDE TREFFEN",
        ("HEIMFORM L10", "AUSWAERTSFORM L10", "BTTS L10 / L15"),
    ),
    "goal": (
        BASE / "NETRATTLER_GOAL_HUNTER_originalkarte.png",
        "GOAL HUNTER",
        ("TORPROGNOSE / XG", "FORM L10 / L15", "TEAMSTAERKE"),
    ),
    "corner": (
        BASE / "corner_sniper_original.webp",
        "CORNER SNIPER",
        ("ECKEN L10 / L15", "SCHUESSE / ECKEN", "CORNERS OVER / UNDER"),
    ),
    "builder": (
        BASE / "prop_builder_original.webp",
        "PREMIUM BUILDER",
        ("AUSWAHL 1", "AUSWAHL 2", "AUSWAHL 3"),
    ),
    "combo": (
        BASE / "NETRATTLER_COMBO_7_originalkarte.png",
        "COMBO / MULTI",
        ("LEG 1", "LEG 2", "LEG 3"),
    ),
}


def build(category: str):
    if category not in SPECS:
        raise ValueError("Not one of the five original-source QA families")
    source, title, labels = SPECS[category]
    png, manifest = render_clean_master_from_reference(
        category, source, title, labels)
    manifest["owner_reference_family"] = category
    manifest["source_reference"] = str(source.relative_to(ROOT))
    manifest["human_visual_approved"] = False
    manifest["telegram_android_qa_approved"] = False
    manifest["owner_original_source_unmodified"] = True
    return png, manifest


def export(outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)
    records = []
    for category in SPECS:
        png, info = build(category)
        (outdir / f"{category}_SOURCE_DERIVED_SANDBOX.png").write_bytes(png)
        records.append(info)
    (outdir / "manifest.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", type=Path,
                        default=ROOT / "output/netrattler_five_owner_qa")
    args = parser.parse_args()
    print("OFFLINE SOURCE-REFERENCE QA: ", len(export(args.outdir)),
          "unapproved drafts; no Telegram access")
