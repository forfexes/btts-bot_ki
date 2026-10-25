import btts_bot as b

def test_name_variants_are_duplicates():
    b._SENT_TIPS_CACHE.clear(); b._SENT_MATCHES.clear(); b._PREFETCHED_DUP_DATES.add("2026-10-25")
    assert not b.is_duplicate_tip("Real Sociedad de Fútbol vs Levante UD", "corners", "2026-10-25")
    b.mark_tip_sent("Real Sociedad de Fútbol vs Levante UD", "corners", "2026-10-25")
    assert b.is_duplicate_tip("Real Sociedad vs Levante", "corners", "2026-10-25")
    assert b.is_duplicate_tip("Real Sociedad de Fútbol vs Levante UD", "corners", "2026-10-25")

def test_other_match_or_market_not_duplicate():
    b._SENT_TIPS_CACHE.clear(); b._SENT_MATCHES.clear(); b._PREFETCHED_DUP_DATES.add("2026-10-25")
    b.mark_tip_sent("Real Sociedad vs Levante", "corners", "2026-10-25")
    assert not b.is_duplicate_tip("Real Sociedad vs Girona", "corners", "2026-10-25")
    assert not b.is_duplicate_tip("Real Sociedad vs Levante", "over25", "2026-10-25")
    assert not b.is_duplicate_tip("Real Sociedad vs Levante", "corners", "2026-10-26")
