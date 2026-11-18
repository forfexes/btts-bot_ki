import netrattler_settlement_v16_final as s


def row():
    return dict(status='void', reason='void: kein Ergebnis nach 3 Tagen verfuegbar (Liga ohne Datenquelle)',
                market_group='builder', profit=0, tip_date='2026-10-28', settled_at=s.TODAY.isoformat(),
                settlement_id='test',tip_id='test',raw={},
                tip_payload={'telegram_msg_id':123,'telegram_chat_id':'test-chat','message_text':'Original pick'})


def test_data_gap_is_a_notice_not_sporting_void_or_profit():
    r=row()
    assert s._data_gap_notice(r) and s._original_update_allowed(r)
    assert not s._confirmed_all_void(r)
    text=s.format_direct_summary(r)
    assert 'Daten fehlen' in text and 'Nicht in Trefferquote oder ROI' in text
    assert 'VOID' not in text and 'Units' not in text and 'Miss' not in text
    assert not s._original_update_allowed({'status':'pending'})
    assert not s._original_update_allowed({'status':'void','reason':'unknown'})


def test_notice_edits_only_original_and_saves_receipt_on_replay(monkeypatch):
    edits=[];receipts=[]
    monkeypatch.setattr(s,'telegram_edit',lambda chat,mid,text:edits.append((chat,mid,text)) or True)
    monkeypatch.setattr(s,'sb_patch',lambda *args:receipts.append(args) or True)
    monkeypatch.setattr(s,'BUILDER_RESULT_IN_TIP',True)
    r=row()
    assert s.retry_unedited_originals([r],[])==(1,1)
    assert edits[0][1]==123 and edits[0][2].startswith('Original pick')
    assert r['raw']['telegram_edit_ok'] is True
    assert receipts
    assert s.retry_unedited_originals([r],[])==(0,0)


def test_scorer_void_without_legs_edits_original_telegram_post(monkeypatch):
    # Regression: five published scorer picks were VOID due to verified
    # non-appearance, but all were left without a Telegram edit receipt.
    r = dict(status="void",
             reason="void: Spieler ohne Einsatz (Spiel in Spielerdaten, Spieler nicht gelistet)",
             market_group="scorer", legs_payload=[], tip_date=s.TODAY.isoformat(),
             settled_at=s.NOW.isoformat(), settlement_id="scorer-no-play",
             tip_id="scorer-no-play", profit=0, raw={},
             tip_payload={"telegram_msg_id":789,
                          "telegram_chat_id":"test-chat",
                          "message_text":"Original Goal Hunter Tipp"})
    assert s._confirmed_scorer_no_appearance(r)
    assert s._original_update_allowed(r) and s._writes_to_source(r)
    edits = []
    monkeypatch.setattr(s, "telegram_edit", lambda chat, mid, text: edits.append((chat, mid, text)) or True)
    monkeypatch.setattr(s, "sb_patch", lambda *args, **kwargs: True)
    assert s.retry_unedited_originals([r], []) == (1, 1)
    assert len(edits) == 1 and edits[0][1] == 789
    assert "VOID" in edits[0][2]
    assert "ohne Einsatz" in edits[0][2]
    assert r["raw"]["telegram_edit_ok"] is True
    # Idempotency: never send a new post or re-edit a correctly edited one.
    assert s.retry_unedited_originals([r], []) == (0, 0)


def test_only_exact_scorer_nonappearance_is_eligible_for_void_edit():
    assert not s._confirmed_scorer_no_appearance({
        "status":"void","market_group":"scorer","reason":"void: Player-Stats fehlen"})
    assert not s._confirmed_scorer_no_appearance({
        "status":"void","market_group":"scorer",
        "reason":"void: Spieler ohne Einsatz (Spiel in Spielerdaten, Spieler nicht gelistet)",
        "legs_payload":[{"status":"pending"}]})
    assert not s._confirmed_scorer_no_appearance({
        "status":"pending","market_group":"scorer",
        "reason":"void: Spieler ohne Einsatz (Spiel in Spielerdaten, Spieler nicht gelistet)"})
