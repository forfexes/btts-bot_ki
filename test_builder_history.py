import netrattler_builder_engine as be
from netrattler_builder_engine import PropLeg
import inspect


def _leg(**kw):
    f = {k: v for k, v in kw.items()}
    names = [p for p in inspect.signature(PropLeg).parameters]
    base = dict(player="Idrissa Gueye", category="fouls_won", line=1.5, odds=1.9, edge=0.05,
                team="X", match="X - Y", league="L", market="m", probability=0.6, source="t")
    base.update(f)
    return PropLeg(**{k: v for k, v in base.items() if k in names})


def test_history_text():
    be.LEG_HISTORY.clear()
    leg = _leg()
    assert be.history_text(leg) == ""
    be.LEG_HISTORY[(be.norm(leg.player), leg.category)] = [1, 3, 2, 3, 3, 2, 6, 4, 2, 4]
    t = be.history_text(leg)
    assert t.startswith("L10: 1,3,2,3,3,2,6,4,2,4") and "2+ in 9/10" in t
    be.LEG_HISTORY.clear()


if __name__ == "__main__":
    test_history_text(); print("ok")


def test_booking_series():
    def mk(i, p, o):
        return _leg(player=f"Spieler {chr(65+i)}", category="yellow_cards", line=0.5, odds=o, probability=p,
                    edge=3.0, match=f"H{i} - A{i}", team=f"H{i}")
    legs = [mk(0, 0.45, 2.2), mk(1, 0.40, 2.5), mk(2, 0.35, 3.0), mk(3, 0.10, 4.0)]
    out = be._booking_series_builders(legs, "2026-10-27")
    styles = [(p.style, p.variant, len(p.legs)) for p in out]
    assert styles.count(("BOOKING SINGLE", "1x BOOKED", 1)) == 3
    assert ("BOOKING SERIES", "TREBLE", 3) in styles
    assert all(p.legs[0].player != "Spieler D" for p in out)


def test_day_cap_per_match(monkeypatch=None):
    import json as _j
    sent = []
    for i in range(6):
        sent.append({"legs": _j.dumps([{"player": f"P{i}", "match": "X - Y", "category": "shots", "line": 2.0}])})

    class R:
        def __init__(self, data, ok=True): self._d, self.ok = data, ok
        def json(self): return self._d
    calls = {"n": 0}

    def fake_get(url, **kw):
        calls["n"] += 1
        return R([]) if calls["n"] == 1 else R(sent)
    orig = be.requests.get
    be.requests.get = fake_get
    try:
        l = _leg(player="Neu", category="shots", line=2.0, match="X - Y")
        pick = be.BuilderPick(builder_id="n", style="S", variant="v", legs=[l], total_odds=2.0, stake=.5,
                              estimated_odds=False, match_date="2026-10-27")
        assert be.builder_pick_exists(pick, "https://x", "k") is True
        calls["n"] = 0
        sent.pop()  # nur 5 -> noch Platz
        assert be.builder_pick_exists(pick, "https://x", "k") is False
    finally:
        be.requests.get = orig
