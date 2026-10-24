import netrattler_settlement_v16_final as s
def test_learned():
    rows=[{"market_group":"builder","telegram_chat_id":"-100123"}]*3+[{"market_group":"builder","telegram_chat_id":s.TG_DEFAULT or "1"}]
    s.GROUPS["builder"]=s.TG_DEFAULT
    assert s.learned_chat("builder",rows)=="-100123"
    s.GROUPS["builder"]="-9"
    assert s.learned_chat("builder",rows)=="-9"
