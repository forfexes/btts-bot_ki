"""Ground-truth inventory of NETRATTLER's 16 requested premium card types.

A source screenshot is NOT a data-free, visually approved owner master.
A technical premium_*_blank.svg is NOT the user's source artwork.
This module is read-only and never uploads/sends or 'approves' artwork.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from PIL import Image

ROOT=Path(__file__).resolve().parent
ASSET=ROOT/"assets"
ORIGINAL=ASSET/"original_templates"
APPROVED=ASSET/"approved_original_masters"

# The six families with real source references (not necessarily clean).
REFERENCES={
    "builder":ORIGINAL/"prop_builder_original.webp",
    "goal":ORIGINAL/"NETRATTLER_GOAL_HUNTER_originalkarte.png",
    "corner":ORIGINAL/"corner_sniper_original.webp",
    "btts":ORIGINAL/"NETRATTLER_BTTS_originalkarte.png",
    "combo":ORIGINAL/"NETRATTLER_COMBO_7_originalkarte.png",
    "last_minute_goal":ROOT/"last_minute_owner_20261122"/"last_minute_user_original.png",
}
CLEAN_CANDIDATES={
    # This is a verified source-derived CLEAN candidate, but its visual
    # appearance in the real Telegram client is not yet approved.
    "last_minute_goal":ROOT/"last_minute_owner_20261122"/"last_minute_clean_plate.png",
}


def _hash(path):
    sha=hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda:f.read(1024*1024),b""):
            sha.update(part)
    return sha.hexdigest()


def audit(root=ROOT):
    from netrattler_premium_verified_cards import CATEGORIES
    root=Path(root)
    def under(rel):
        return root / rel
    reports={}
    for category in CATEGORIES:
        src=REFERENCES.get(category)
        clean=CLEAN_CANDIDATES.get(category)
        source=under(src.relative_to(ROOT)) if src else None
        plate=under(clean.relative_to(ROOT)) if clean else None
        reference_exists=bool(source and source.is_file())
        candidate_exists=bool(plate and plate.is_file())
        # A separately approved owner master requires the original source,
        # the exact CLEAN PNG, and a human-signoff attestation matching
        # both file hashes. Merely copying or renaming an SVG is insufficient.
        approved_file=under(Path("assets")/"approved_original_masters"/(category+".png"))
        attestation=under(Path("assets")/"approved_original_masters"/(category+".json"))
        verified=False
        # An editable JSON in a public GitHub repository cannot, by
        # itself, prove the owner's approval. The separate protected
        # environment must explicitly pin the approved PNG's digest.
        protected_digest=os.getenv(
            "NETRATTLER_APPROVED_MASTER_"+category.upper(),"").strip().lower()
        if (reference_exists and approved_file.is_file()
                and attestation.is_file() and len(protected_digest)==64):
            try:
                evidence=json.loads(attestation.read_text(encoding="utf-8"))
                with Image.open(approved_file) as image:
                    # A disguised SVG/text blob is not a genuine clean PNG.
                    valid_png=(image.format=="PNG" and min(image.size)>=512)
                    image.verify()
                verified=(
                    valid_png
                    and evidence.get("original_source_sha256")==_hash(source)
                    and evidence.get("approved_png_sha256")==_hash(approved_file)
                    and protected_digest == _hash(approved_file)
                    and evidence.get("human_visual_approved") is True
                    and evidence.get("telegram_android_qa_approved") is True
                )
            except (ValueError,OSError,TypeError,Image.UnidentifiedImageError):
                verified=False
        reports[category]={
            "source_reference":str(src.relative_to(ROOT)) if src else None,
            "reference_present":reference_exists,
            "clean_candidate_present":candidate_exists,
            "approved_for_telegram":verified,
            "state":("approved" if verified else
                     "clean_candidate_not_approved" if candidate_exists else
                     "reference_needs_clean_master" if reference_exists else
                     "source_original_missing"),
            "technical_svg_only":(not reference_exists and
                 under(Path("assets")/f"premium_{category}_blank.svg").is_file()),
        }
    return reports


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--json",action="store_true")
    parser.add_argument("--require-all-approved",action="store_true")
    args=parser.parse_args()
    states=audit()
    counts={state:sum(r["state"]==state for r in states.values())
            for state in ("approved","clean_candidate_not_approved",
                          "reference_needs_clean_master","source_original_missing")}
    if args.json:
        print(json.dumps({"totals":counts,"categories":states},
                         indent=2,ensure_ascii=False))
    else:
        for category,info in states.items():
            print(f"{category:20} {info['state']}")
        print("SUMMARY",counts)
    if args.require_all_approved and counts["approved"] != len(states):
        raise SystemExit("NO FULL TELEGRAM RELEASE: owner-original assets incomplete")


if __name__=="__main__":
    main()
