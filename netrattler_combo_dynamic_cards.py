"""NETRATTLER 3–12-leg COMBO renderer using only uploaded owner originals.

3–7 legs use the real COMBO-7 PNG, 8–12 legs use the COMBO-9 PNG.
No procedural, technical SVG or generic fallback is permitted in Telegram.
"""
from __future__ import annotations

from netrattler_combo_owner_original import render_original_combo


def render_combo(legs, *, combined_odds=None, probability, ev=None, confidence,
                 status="OFFEN", crest_provider=None, stake=1.0,
                 combined_odds_observed=False, combined_quote_id="", bookmaker=""):
    """Render true-original 3–12-leg artwork with real crests and decimal odds.

    The combined bookmaker ticket is optional. When missing, only the product
    of authentic supplied leg prices is shown, explicitly labelled BERECHNET.
    """
    return render_original_combo(
        legs, combined_odds=combined_odds, probability=probability, ev=ev,
        confidence=confidence, status=status, stake=stake,
        combined_odds_observed=combined_odds_observed,
        combined_quote_id=combined_quote_id, bookmaker=bookmaker,
        crest_provider=crest_provider,
    )
