import os
import netrattler_builder_styles as st

def test_losing_styles_disabled_by_default():
    os.environ.pop("NETRATTLER_BUILDER_DISABLED_STYLES", None)
    d = st.disabled_styles()
    assert {"SAME GAME MIXED", "CROSS MATCH", "SOT LADDER"} <= d
    assert "NATE CATEGORY" not in d and "TIPS BIBLE" not in d

def test_override_none():
    os.environ["NETRATTLER_BUILDER_DISABLED_STYLES"] = "-"
    try:
        assert st.disabled_styles() == set()
    finally:
        os.environ.pop("NETRATTLER_BUILDER_DISABLED_STYLES", None)
