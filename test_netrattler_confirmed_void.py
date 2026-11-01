from unittest.mock import patch
import netrattler_settlement_v16_final as s


def row(reason='void: Spieler ohne Einsatz (Spiel in Spielerdaten, Spieler nicht gelistet)'):
    return {'status':'void','market_group':'builder','tip_id':'v','source_table':'netrattler_builder_picks',
            'reason':'0/2 Legs gewonnen · 0 verloren · 0 offen · 2 void',
            'tip_payload':{'builder_id':'v','status':'pending','message_text':'original','telegram_msg_id':123,'telegram_chat_id':42},
            'profit':0,'profit_units':0,'legs_payload':[{'status':'void','reason':reason} for _ in range(2)]}


def test_confirmed_void_updates_source_without_classifying_as_loss():
    r=row()
    assert s._confirmed_all_void(r) and s._writes_to_source(r)
    assert 'VOID' in s.format_direct_summary(r) and 'Miss' not in s.format_direct_summary(r)
    with patch.object(s,'UPDATE_SOURCE_TIPS',True),patch.object(s,'sb_patch',return_value=True) as update:
        s.update_source_tip(r)
    assert update.call_args.args[3]['status']=='void'


def test_missing_data_void_and_partially_open_legs_are_not_published():
    r=row('Spielerdaten fehlen')
    assert not s._confirmed_all_void(r) and not s._writes_to_source(r)
    r=row();r['legs_payload'][0]['status']='pending'
    assert not s._confirmed_all_void(r)
    r=row();r['legs_payload']=[]
    assert not s._confirmed_all_void(r)
