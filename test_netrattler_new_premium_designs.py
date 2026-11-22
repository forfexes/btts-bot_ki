"""Offline integrity checks for the eleven newly designed editable NETRATTLER masters.

These are NEW designs, not user-supplied original artwork. No Telegram send.
"""
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent / "assets" / "new_premium_designs"
NAMES = (
    "over", "btts_halftime", "over_halftime", "match_result",
    "player_props", "fouls_cards", "var", "last_minute_goal",
    "late_goals", "live_halftime", "cross_mix",
)
NS = "{http://www.w3.org/2000/svg}"


def test_all_eleven_new_designs_are_editable_clean_svgs():
    assert sorted(p.stem for p in ROOT.glob("*.svg")) == sorted(NAMES)
    for name in NAMES:
        data = (ROOT / f"{name}.svg").read_text(encoding="utf-8")
        root = ET.fromstring(data)
        assert root.tag == NS + "svg"
        assert root.attrib["viewBox"] == "0 0 1122 1402"
        texts = ["".join(t.itertext()) for t in root.findall(NS + "text")]
        assert "NETRATTLER" in texts
        assert any("@prophunter" in t for t in texts)
        assert any("NEW DESIGN / QA ONLY" in t for t in texts)
        assert not any("1.75" in t or "65.0%" in t for t in texts)
        assert "#27D9F6" in data and "url(#gold)" in data
