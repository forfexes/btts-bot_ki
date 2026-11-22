"""Pixel-preserving Telegram chat-preview padding for NETRATTLER originals.

The client overlays message time/edited-status at the photo's bottom right.
Do not repaint the owner's supplied stadium, crests, caption or settlement.
Instead append a bottom metadata-only area composed of the last actual image
scanline. Existing original pixels are untouched.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageChops

PNG = b"\x89PNG\r\n\x1a\n"


def telegram_safe_margin_height(height: int) -> int:
    if height < 400:
        raise ValueError("Premium original image is too short")
    # Compact Android time/edited overlay zone. The former 16% black
    # extension was visually oversized; preserve actual original pixels.
    return max(112, round(height * 0.075))


def append_safe_margin(png: bytes) -> bytes:
    if not isinstance(png, (bytes, bytearray)) or not png.startswith(PNG):
        raise ValueError("NETRATTLER original must be PNG")
    with Image.open(BytesIO(png)) as source:
        if source.format != "PNG" or min(source.size) < 600:
            raise ValueError("NETRATTLER photo has invalid premium dimensions")
        original = source.convert("RGB")
    width, height = original.size
    margin = telegram_safe_margin_height(height)
    # No text, player or old example is covered or duplicated. The added area
    # is exactly the source's text-free bottom scanline, continued vertically.
    strip = original.crop((0, height - 1, width, height)).resize(
        (width, margin), Image.Resampling.NEAREST
    )
    output = Image.new("RGB", (width, height + margin))
    output.paste(original, (0, 0))
    output.paste(strip, (0, height))
    buf = BytesIO()
    output.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def assert_safe_margin(original: bytes, padded: bytes):
    """Offline render QA: byte-exact RGB pixels of owner art must be retained."""
    with Image.open(BytesIO(original)) as old, Image.open(BytesIO(padded)) as new:
        a, b = old.convert("RGB"), new.convert("RGB")
    w, h = a.size
    if b.size != (w, h + telegram_safe_margin_height(h)):
        raise AssertionError("Telegram photo margin dimensions differ")
    if ImageChops.difference(a, b.crop((0, 0, w, h))).getbbox():
        raise AssertionError("Source original pixels were changed/overpainted")
    expected = a.crop((0, h - 1, w, h)).resize(
        (w, b.height - h), Image.Resampling.NEAREST
    )
    if ImageChops.difference(expected, b.crop((0, h, w, b.height))).getbbox():
        raise AssertionError("Telegram metadata area contains unwanted content")
