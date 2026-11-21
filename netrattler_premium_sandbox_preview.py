"""Offline-only NETRATTLER premium card previews for sandbox artifacts.

All names/odds/logo shapes below are TEST FIXTURES, never live picks. This
module never calls Telegram, Supabase or web services.
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw
from netrattler_premium_telegram_adapter import render

MARKETS = ("over25", "btts", "btts_ht", "over15_ht", "1x2", "combo")


def _example_crest(team: str):
    im = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    color = "#20B1CB" if "Demo United" in team else "#E7A629"
    d.ellipse((5, 5, 115, 115), fill=color, outline="#FAFCFF", width=6)
    d.text((60, 60), "DEMO", anchor="mm", fill="#071724")
    with io.BytesIO() as output:
        im.save(output, "PNG")
        return output.getvalue()


def main(path="premium-sandbox-preview"):
    folder = Path(path)
    folder.mkdir(exist_ok=True, parents=True)
    for market in MARKETS:
        tip = {
            "match": "Demo United vs Demo City",
            "league": "OFFLINE SANDBOX – NO LIVE PICK",
            "time_local": "DEMO 19:00",
            "oddsYes": 1.75, "probability": 65.0,
            "bookmaker": "offline_verified_fixture",
            "selection": "1" if market == "1x2" else "YES",
        }
        if market == "combo":
            # Synthetic QA-only ticket: exercise confirmed-total gate without
            # ever publishing these fictional names or prices to Telegram.
            tip.update(odds=3.25, combined_odds_observed=True,
                       combined_quote_id="OFFLINE-QA-ONLY")
        payload = render([(market, tip)], "2026-11-19",
                         crest_provider=_example_crest)
        outfile = folder / f"demo-{market}.png"
        outfile.write_bytes(payload)
        with Image.open(io.BytesIO(payload)) as im:
            if im.size != (1122, 1402) or im.format != "PNG":
                raise RuntimeError("sandbox_premium_preview_invalid")
        print("SANDBOX_PREVIEW_DEMO_ONLY", outfile, len(payload), flush=True)


if __name__ == "__main__":
    main()
