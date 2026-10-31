import io
from PIL import Image
from unittest.mock import Mock,patch
import netrattler_stats_match_cards as cards
import netrattler_corner_cards as corner
import netrattler_builder_cards as builder_cards
import netrattler_builder_engine as engine


def test_kickoff_uses_swiss_time_and_never_tbd():
    assert corner.kickoff_label({'time':'TBD','_kickoff':'2026-10-31T15:00:00Z'},'2026-10-31')==('2026-10-31','16:00')
    assert corner.kickoff_label({'time':'TBD'},'2026-10-31')[1]=='Zeit nicht bestätigt'
    assert corner.kickoff_label({'time_local':'18:30'},'2026-10-31')[1]=='18:30'
    assert corner.kickoff_label({'_kickoff':'2026-10-31T15:00:00'},'2026-10-31')[1]=='Zeit nicht bestätigt'


def test_direct_api_header_for_h2h():
    response=Mock(ok=True);response.json.return_value={'response':[]}
    with patch.object(cards.requests,'get',return_value=response) as get:
        cards._af_get('/teams',{'search':'Levante'},['test-key'],{'calls':0,'max':3})
    assert get.call_args.kwargs['headers']=={'x-apisports-key':'test-key'}


def test_h2h_excludes_future_live_and_wrong_pair_but_keeps_zero():
    tip={'match':'Home vs Away','league':'Test'}
    def fx(home,away,status,day,goals):
        return {'fixture':{'status':{'short':status},'date':day},
                'teams':{'home':{'id':home},'away':{'id':away}},'goals':dict(zip(('home','away'),goals))}
    matches=[fx(1,2,'FT','2026-10-01',(0,0)),fx(1,2,'NS','2099-01-01',(1,1)),
             fx(1,2,'1H','2026-10-02',(1,1)),fx(3,4,'FT','2026-10-03',(3,3))]
    with patch.dict('os.environ',{'API_FOOTBALL_KEYS':'test'}), \
         patch.object(cards,'_af_team_id',side_effect=[1,2]), \
         patch.object(cards,'_af_get',return_value=matches):
        assert cards.attach_h2h_api({'corners':[tip]})==1
    assert tip['h2h_matches']==1 and tip['h2h_avg_goals']==0


def test_corner_dispatch_and_settlement_render():
    tip={'match':'Home vs Away','tip':'Over 8.5 Ecken','odds':1.9,'probability':61,'_source':'kambi',
         'expected_corners':9.8,'home_avg_corners':0,'away_avg_corners':5,'time':'TBD'}
    with patch.object(cards,'_paste_badge'):
        image=Image.open(io.BytesIO(cards.render_card([('corners',tip)],'2026-10-31',{'marks':{'0':'win'}})))
    assert image.size==(1200,900)
    assert image.getpixel((600,899))[2] < 70


def pick():
    leg=engine.PropLeg('Player A','Levante','Levante vs Atletico Madrid','La Liga','1+ shots','shots',.5,1.9,.65,'kambi')
    return engine.BuilderPick('visual','NATE','SAFE',[leg],1.9,.2,False,'2026-10-31')


def test_builder_keeps_verified_player_identity_and_receipt():
    p=pick()
    with patch.object(cards,'_paste_badge'),patch.object(cards,'_player_photo',return_value=b'') as photo:
        payload=builder_cards.render_builder_card(p)
    photo.assert_called_once_with('Player A','Levante')
    assert Image.open(io.BytesIO(payload)).size==(1200,690)
    with patch.object(builder_cards,'render_builder_card',return_value=payload), \
         patch.object(cards,'_send_photo',return_value=123):
        assert builder_cards.send_builder_card('token','chat',p)==123


def test_builder_photo_callback_persists_original_message_id():
    p=pick();send_text=Mock()
    with patch.object(engine,'deduplicate_props',return_value=[]), \
         patch.object(engine,'build_builder_picks',return_value=[p]), \
         patch.object(engine,'builder_pick_exists',return_value=False), \
         patch.object(engine,'persist_builder_pick',return_value=True) as persist:
        # Store the same original photo receipt used by settlement.
        sent,_=engine.run_builder_engine([],send_text,supabase_url='url',supabase_key='key',
                                         chat_id=42,send_pick=lambda pick,text:456)
    assert sent==1
    send_text.assert_not_called()
    assert persist.call_args.kwargs['telegram_message_id']==456
    assert persist.call_args.kwargs['telegram_chat_id']==42


def test_h2h_resolver_never_prefers_youth_squad_over_senior_alias():
    response=[{'team':{'id':100,'name':'Derby County U21','country':'England'}},
              {'team':{'id':69,'name':'Derby','country':'England'}}]
    with patch.object(cards,'_AF_TEAM_ID',{}),patch.object(cards,'_af_get',return_value=response) as get, \
         patch.object(cards,'_country_of',return_value='England'):
        assert cards._af_team_id('Derby County','England - Championship',['test'],{'calls':0,'max':5})==69
        assert get.call_args.args[1]['search']=='Derby'
    assert not cards._same_squad('Levante','Levante II')
    assert not cards._same_squad('Millwall','Millwall U21')
    assert cards._same_squad('Millwall U21','Millwall U21')


def test_model_card_preserves_no_quote_and_original_receipt():
    from types import SimpleNamespace
    model={'title':'FOUL BUILDER','joint':.67,'fair':1.49,'legs':[{
        'player':'Lamine Yamal','team':'Barcelona','match':'Barcelona vs Alaves','league':'La Liga',
        'market':'1+ Fouls gezogen','category':'fouls_won','line':1,'odds':0,
        'series':[3,6,1,1,1,2,3,1,1,0],'kickoff':'2099-01-01T15:00:00Z'}]}
    with patch.dict('os.environ',{'TELEGRAM_TOKEN':'test','TELEGRAM_GROUP_BUILDER':'42'}), \
         patch.object(builder_cards,'send_builder_card',return_value=123) as send:
        receipt=builder_cards.send_model_builder_card(model,'2099-01-01','original')
    adapted=send.call_args.args[2]
    assert adapted.model_only and adapted.legs[0].odds==0
    assert adapted.legs[0].series==model['legs'][0]['series']
    assert receipt=={'message_id':123,'chat_id':'42','text':'original'}
    with patch.object(cards,'_paste_badge'),patch.object(cards,'_player_photo',return_value=b''):
        assert Image.open(io.BytesIO(builder_cards.render_builder_card(adapted))).size==(1200,690)


def test_model_cross_ladder_renders_all_stages():
    from types import SimpleNamespace
    leg=lambda name,match:SimpleNamespace(player=name,team='Club',match=match,league='League',
        market='2+ Fouls',category='fouls',line=2,odds=0,series=[2]*10,kickoff='')
    pick=SimpleNamespace(legs=[leg('A','Club A vs Club B'),leg('B','Club C vs Club D')],
        style='FOUL LEITER',match_date='2026-10-31',model_only=True,joint=.5,fair=2,
        tiers=[(2,.5),(3,.2),(4,.05)],tier_shift=False)
    with patch.object(cards,'_player_photo',return_value=b''):
        assert Image.open(io.BytesIO(builder_cards.render_builder_card(pick))).size==(1200,970)
