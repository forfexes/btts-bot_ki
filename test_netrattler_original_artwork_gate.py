"""Original-artwork acceptance gate for NETRATTLER (offline, no Telegram).

The existing premium SVG tests measure technical layout, not whether uploaded
artwork was retained. These tests intentionally remain red until cleaned,
data-free derivatives of the *real* originals are wired into production.
Never replace, modify or publish the source original images.
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parent
SOURCES = {
    "builder": ROOT / "assets/original_templates/NETRATTLER_BUILDER_4_originalkarte.png",
    "goal": ROOT / "assets/original_templates/NETRATTLER_GOAL_HUNTER_originalkarte.png",
}


def test_source_originals_are_present_and_retained():
    for category, source in SOURCES.items():
        assert source.is_file(), f"Original {category} was removed: {source}"
        assert source.stat().st_size > 100_000, f"Original {category} is unexpectedly small"
        with Image.open(source) as im:
            im.verify()


def test_production_uses_distinct_cleaned_original_artwork_not_svg():
    from netrattler_original_template_renderer import BUILDER_IMAGE, GOAL_IMAGE

    for category, master in {"builder": BUILDER_IMAGE, "goal": GOAL_IMAGE}.items():
        master = Path(master)
        source = SOURCES[category]
        assert master.resolve() != source.resolve(), (
            f"{category}: never paint live data into or overwrite the uploaded source"
        )
        assert master.suffix.lower() in {".png", ".webp"}, (
            f"{category}: a generated SVG is not the approved original artwork"
        )
        assert "cleaned_original_templates" in master.parts, (
            f"{category}: expected a separate reviewed, data-free original-derived master"
        )
        assert master.is_file(), f"{category}: cleaned production master missing"


def test_cleaned_masters_keep_the_original_header_and_proportions():
    """Catch replacement mockups while allowing variable data lower down."""
    from netrattler_original_template_renderer import BUILDER_IMAGE, GOAL_IMAGE

    for category, master in {"builder": BUILDER_IMAGE, "goal": GOAL_IMAGE}.items():
        with Image.open(SOURCES[category]) as original, Image.open(master) as derived:
            original = original.convert("RGB")
            derived = derived.convert("RGB")
            source_ratio = original.width / original.height
            derived_ratio = derived.width / derived.height
            assert abs(source_ratio - derived_ratio) < 0.03, (
                f"{category}: the original aspect ratio has changed"
            )
            # Align dimensions to compare the source's untouched decorative top band.
            scaled = derived.resize(original.size, Image.Resampling.LANCZOS)
            header_height = max(1, int(original.height * 0.10))
            delta = ImageChops.difference(
                original.crop((0, 0, original.width, header_height)),
                scaled.crop((0, 0, original.width, header_height)),
            )
            mean_difference = sum(ImageStat.Stat(delta).mean) / 3
            assert mean_difference < 18, (
                f"{category}: original header/crown artwork differs "
                f"(mean channel difference {mean_difference:.1f})"
            )
