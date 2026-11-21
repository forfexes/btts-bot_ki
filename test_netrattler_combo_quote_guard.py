"""NETRATTLER real-legged COMBO: allow missing ticket quote without fake ROI."""
import math
from pathlib import Path
from netrattler_combo_quote_guard import publishable_combo


def legs(n):
    return [{"match":f"HOME {i+1} vs AWAY {i+1}",
             "market":"btts","odds":1.65} for i in range(n)]


for n in range(3, 13):
    combo=dict(tips=legs(n),total_odds=42.5,
               combined_odds_observed=False,combined_quote_id="",bookmaker="")
    assert publishable_combo(combo),n
    assert not combo["combined_odds_observed"],n
    assert combo["combined_quote_calculated"],n
    assert combo["odds_source_type"] == "calculated_from_observed_leg_odds",n
    assert abs(combo["total_odds"]-1.65**n)<0.001,n

observed=dict(tips=legs(7),total_odds=42.5,combined_odds_observed=True,
              combined_quote_id="QA_TEST",bookmaker="TEST_ONLY")
assert publishable_combo(observed)
assert observed["total_odds"]==42.5, "Genuine bookmaker quote must prevail"
assert observed["combined_quote_calculated"] is False

for mutation in (
    {"total_odds":float("nan")},
    {"total_odds":float("inf")},
    {"total_odds":1.0},
    {"tips":[]},
    {"tips":legs(2)},
    {"tips":legs(13)},
    {"tips":[dict(legs(7)[0],synthetic=True)]+legs(6)},
    {"tips":[dict(legs(7)[0],_no_real_odds=True)]+legs(6)},
    {"tips":[dict(legs(7)[0],odds=None)]+legs(6)},
):
    assert not publishable_combo(dict(observed,**mutation)),mutation
for mutation in (
    {"tips":[dict(legs(7)[0],estimated_odds=True)]+legs(6)},
    {"tips":legs(13)},
    {"tips":[dict(legs(7)[0],odds=float("nan"))]+legs(6)},
):
    assert not publishable_combo(dict(tips=legs(7),combined_odds_observed=False,**mutation))

# Require the production formatter to avoid fictional profit for derived prices.
source=Path("btts_bot.py").read_text(encoding="utf-8")
latest_generator=source[source.rfind("def generate_multi_combo_bets"):
                        source.rfind("def format_combo_telegram_message")]
assert '"combined_odds_observed": False' in latest_generator
formatter=source[source.rfind("def format_combo_telegram_message"):
                 source.find("\ndef ",source.rfind("def format_combo_telegram_message")+1)]
assert "publishable_combo(combo)" in formatter
assert "Berechnete Gesamtquote" in formatter
assert "Kein bestätigter Buchmachergewinn" in formatter
assert "quote_confirmed" in formatter
send_route=source[source.rfind("for n in _combo_sizes:"):]
assert "if not publishable_combo(combo):" in send_route
assert 'min(12, int(env("NETRATTLER_MULTI_COMBO_MAX_LEGS"' in source
print("NETRATTLER COMBO 3-12 MULTIPLIED-QUOTE GATE PASSED (UNVERIFIED, NO FAKE ROI)")
