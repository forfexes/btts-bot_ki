# NETRATTLER AI — LAST MINUTE GOAL (Owner original, offline prototype)

Source image: the 512×512 user-provided Gambia vs Ivory Coast original from 22 Nov 2026. The branding, stadium art, gold/cyan frame, original fixed labels, prognoses and `@prophunter` are preserved from the actual user's image; this is **not** a newly generated design.

- `last_minute_user_original.png`: immutable source photograph, **never use as a runtime background** because it has sample scores/figures.
- `build_master.py`: one-time background preparation from that source. It reconstructs only dynamic fields and creates `last_minute_clean_plate.png`. The static image stays separate and is never modified by the live renderer.
- `last_minute_clean_plate.png`: blank, true-source-derived poster (not an SVG and not a transparent vector file). The background of any removed old data is *reconstructed*; exact pixel recovery underneath old text is mathematically impossible from the flattened screenshot.
- `live_data_bridge.py`: maps exact verified event/team IDs, real FotMob/ESPN statistics and explicitly verified probabilities into the renderer. Offline only; missing crests fail closed.
- `test_live_data_bridge.py`: validates live and final fixtures, rejects stale or invented values.
- `last_minute_dynamic_card.py`: all team names, authentic logos, goal count, minute, xG, match stats, player probabilities, result come from explicitly supplied dynamic data. No sample text is covered by the rendering code. Missing crests fail closed; missing statistics show an em dash. A `SANDBOX · KEIN TIPP` preview can be generated without any network call.
- `last_minute_render_test.png`: synthetic **sandbox-only** demonstration using QA logos. Not a live tip.
- `test_last_minute_dynamic_card.py`: offline tests for original-pixel preservation, data validation, no legacy sample-photo use, missing-asset failure and picture output.

Run locally:

```sh
python -m pip install Pillow opencv-python-headless numpy
python build_master.py
python -m unittest -v test_last_minute_dynamic_card
python last_minute_dynamic_card.py
```

**Release gate:** not yet enabled on GitHub production or Telegram. Before production, verify actual logos, harden source provenance, visually review full-resolution PNG and Telegram rendering, and integrate the exact source-derived clean plate and renderer into `forfexes/btts-bot_ki`. The existing fallback must not be enabled. Test logos and synthetic values are not valid for publication.

**GitHub QA:** `NETRATTLER Last Minute Owner Original QA` checks 7 plate/renderer tests and 4 live-data bridge tests. The new card is not enabled for production; no Telegram post is made by these tests.