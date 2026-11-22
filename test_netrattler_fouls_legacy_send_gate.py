"""Legacy model-only Fouls Builder must not bypass the owner premium artwork."""
from unittest.mock import patch
import netrattler_builder_cards as cards


def test_no_fouls_or_fouls_won_legacy_card_reaches_telegram():
    for category in ("fouls", "fouls_won", "fouls_committed", "fouls_drawn",
                     "shots", "sot", "cards", "yellow", "tackles"):
        model = {
            "title": "FOUL BUILDER", "joint": 0.45, "fair": 2.22,
            "legs": [{
                "player": "Example Athlete", "team": "Example Club",
                "match": "Example Club vs Example Opponent", "league": "QA",
                "market": "2+ Fouls", "category": category,
                "line": 2, "odds": 0.0,
                "series": [2] * 10, "kickoff": "2099-01-01T12:00:00+00:00",
            }],
        }
        with patch.dict("os.environ", {
            "TELEGRAM_TOKEN": "offline-test",
            "TELEGRAM_GROUP_BUILDER": "-100999",
        }), patch.object(cards, "send_builder_card",
                        side_effect=AssertionError("No old Telegram card")) as send:
            messages = []
            result = cards.send_model_builder_card(model, "2099-01-01",
                                                   "QA ONLY", messages.append)
            assert result is None
            send.assert_not_called()
            assert any("owner_original_and_bookmaker_ticket_required" in m
                       for m in messages)
