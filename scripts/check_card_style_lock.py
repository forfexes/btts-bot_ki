"""Fail closed when original/approved owner card artwork changes without review.

Git blob SHA-1 is calculated on BYTES, not image RGB: even metadata edits
count as new artwork. No image-generation, network or Telegram side effects.
"""
from __future__ import annotations
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCKED = {
    "assets/original_templates/NETRATTLER_BTTS_originalkarte.png": "4dcc2a93a09dfbd26067363116d22ddf67e38e42",
    "assets/original_templates/NETRATTLER_BUILDER_4_originalkarte.png": "21cf9ba19a45556b26419fc6115ccf51e138593e",
    "assets/original_templates/NETRATTLER_COMBO_7_originalkarte.png": "eb290f06373d70d34e10b7bc63e4e58f7f216744",
    "assets/original_templates/NETRATTLER_COMBO_9_originalkarte.png": "2e9e19257eda5697eed686aeccc8a6bbc0aff504",
    "assets/original_templates/NETRATTLER_GOAL_HUNTER_originalkarte.png": "0827f43418e7c809cc53773117e884feb3524260",
    "assets/original_templates/corner_sniper_original.webp": "5730e9c7f4574db511393ee02a28923e69f5c240",
    "assets/original_templates/goal_hunter_neon_frame.webp": "ff545d5a4373bcf7c801760e1e4c8704f272286e",
    "assets/original_templates/goal_hunter_original.webp": "38e285043ab9500792d88a91c27262e7a30edadb",
    "assets/original_templates/goal_hunter_original_header.webp": "2b44070f9f659479b31e5e9fdc178a5e6aef2701",
    "assets/original_templates/prop_builder_original.webp": "1223da0cf5f5a0e69bd046a29b520af888f9b746"
}


def git_blob_sha1(content: bytes) -> str:
    return hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()


def verify() -> None:
    for path, expected in LOCKED.items():
        full = ROOT / path
        if not full.is_file():
            raise AssertionError(f"Missing mandatory owner artwork: {path}")
        actual = git_blob_sha1(full.read_bytes())
        if actual != expected:
            raise AssertionError(f"Unauthorized card-style artwork change: {path}")
    print(f"CARD_STYLE_LOCK_OK: {len(LOCKED)} immutable owner artworks")


if __name__ == "__main__":
    verify()
