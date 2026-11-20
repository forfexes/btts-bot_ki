"""No unobserved combined odds may reach NETRATTLER Telegram.

The bookmaker combined ticket must exist independently. Multiplication of
real leg prices alone is insufficient, even if each leg's odds are genuine.
"""
from pathlib import Path
from netrattler_combo_quote_guard import publishable_combo


def legs(n):
    return [{"match":f"HOME {i+1} vs AWAY {i+1}",
             "market":"btts","odds":1.65} for i in range(n)]


base=dict(tips=legs(7),total_odds=42.5,
          combined_odds_observed=False,combined_quote_id="",
          bookmaker="")
assert not publishable_combo(base)
assert not publishable_combo(dict(base,combined_odds_observed=True))
assert not publishable_combo(dict(base,combined_odds_observed=True,
                                  combined_quote_id="QA_TEST"))
observed=dict(base,combined_odds_observed=True,
              combined_quote_id="QA_TEST",bookmaker="TEST_ONLY")
assert publishable_combo(observed)
for mutation in (
    {"total_odds":float("nan")},
    {"total_odds":float("inf")},
    {"total_odds":1.0},
    {"tips":[]},
    {"tips":legs(2)},
    {"tips":legs(12)},
    {"tips":[dict(legs(7)[0],synthetic=True)]+legs(6)},
    {"tips":[dict(legs(7)[0],_no_real_odds=True)]+legs(6)},
    {"tips":[dict(legs(7)[0],odds=None)]+legs(6)},
):
    assert not publishable_combo(dict(observed,**mutation)),mutation

source=Path("btts_bot.py").read_text(encoding="utf-8")
latest_generator=source[source.rfind("def generate_multi_combo_bets"):
                        source.rfind("def format_combo_telegram_message")]
assert '"combined_odds_observed": False' in latest_generator
send_route=source[source.rfind("for n in _combo_sizes:"):]
assert "if not publishable_combo(combo):" in send_route
print("NETRATTLER REAL COMBINED-PRICE GATE PASS: no multiplication-as-bookmaker quote")
