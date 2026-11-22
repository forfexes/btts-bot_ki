"""Offline NETRATTLER Telegram visual safety: never cover uploaded originals."""
from __future__ import annotations

import io
import os
from unittest.mock import patch

from PIL import Image, ImageDraw

from netrattler_telegram_safe_zone import (
    append_safe_margin, assert_safe_margin, telegram_safe_margin_height,
)

def make_source():
    canvas = Image.new("RGB", (1122, 1402), (3, 19, 38))
    draw = ImageDraw.Draw(canvas)
    # Model the original footer/@handle close to Telegram's overlay corner.
    draw.rectangle((810, 1270, 1100, 1380), fill=(24, 129, 220))
    draw.text((860, 1335), "@prophunter ORIGINAL", fill=(255, 255, 255))
    buf = io.BytesIO()
    canvas.save(buf, "PNG")
    return buf.getvalue()

original = make_source()
padded = append_safe_margin(original)
assert_safe_margin(original, padded)
with Image.open(io.BytesIO(padded)) as img:
    assert img.size == (1122, 1402 + telegram_safe_margin_height(1402))
print("NETRATTLER_ALL_ORIGINAL_PIXELS_PRESERVED")

import netrattler_stats_match_cards as cards
captured = []

class Response:
    ok = True
    status_code = 200
    text = ""
    def json(self):
        return {"ok": True, "result": {"message_id": 1337}}

def no_network(url, **kwargs):
    captured.append((url, kwargs))
    return Response()

with patch.dict(os.environ, {"NETRATTLER_ORIGINAL_ONLY": "1"}):
    with patch.object(cards.requests, "post", side_effect=no_network):
        new_id = cards._send_photo("TEST-NO-NETWORK", "CHAT", "", original, lambda _: None)
        assert new_id == 1337
        assert len(captured) == 1
        assert captured[0][0].endswith("/sendPhoto")
        assert_safe_margin(original, captured[0][1]["files"]["photo"][1])
        captured.clear()
        assert cards._edit_photo(
            "TEST-NO-NETWORK", "CHAT", 1337, original,
            lambda _: None, caption="Original settlement preserved",
        )
        assert len(captured) == 1
        assert captured[0][0].endswith("/editMessageMedia")
        assert captured[0][1]["data"]["message_id"] == 1337
        assert_safe_margin(original, captured[0][1]["files"]["card"][1])
        print("NETRATTLER_SAME_MESSAGE_TELEGRAM_SAFE_MARGIN")

for malformed in (b"", b"NO", b"\x89PNG\r\n\x1a\nBAD"):
    try:
        append_safe_margin(malformed)
    except (ValueError, OSError):
        pass
    else:
        raise AssertionError("Corrupt Telegram source accepted")
print("NETRATTLER_TELEGRAM_SAFE_ZONE_QA_PASSED; NO_LIVE_TELEGRAM")
