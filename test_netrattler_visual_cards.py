import io
from PIL import Image
from unittest.mock import Mock,patch
import netrattler_stats_match_cards as cards
import netrattler_corner_cards as corner
import netrattler_builder_cards as builder_cards
import netrattler_builder_engine as engine



def _fake_reference_photo():
    """Valid synthetic raster solely for offline unit tests; never Telegram."""
    from PIL import Image
    import io
    im=Image.new("RGB",(140,140),"#20668A")
    out=io.BytesIO()
    im.save(out,"PNG")
    return out.getvalue()


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
         'expected_corners':9.8,'home_avg_corners':0,'away_avg_corners':5,
         '_kickoff':'2026-10-31T15:00:00+00:00','h2h_matches':3,'h2h_avg_corners':9.4,
         'home_corners_l10':5.5,'home_corners_l15':5.7,
         'away_corners_l10':4.2,'away_corners_l15':4.5,
         'corner_hits_l10':'7/10','corner_hits_l15':'10/15','confidence':'HIGH'}
    from netrattler_corner_template import review_corner_png
    with patch.object(cards,'_badge_bytes',return_value=_fake_reference_photo()):
        raw=cards.render_card([('corners',tip)],'2026-10-31',{'marks':{'0':'win'}})
    image=Image.open(io.BytesIO(raw))
    assert image.size==(1122,1402)
    assert review_corner_png(raw)==[]


def pick():
    leg=engine.PropLeg('Player A','Levante','Levante vs Atletico Madrid','La Liga','1+ shots','shots',.5,1.9,.65,'kambi')
    return engine.BuilderPick('visual','NATE','SAFE',[leg],1.9,.2,False,'2026-10-31')


def test_builder_keeps_verified_player_identity_and_receipt():
    p=pick()
    import pytest
    # A single leg is not a complete Builder and must not masquerade as one.
    with pytest.raises(ValueError, match="2–6 Legs"):
        builder_cards.render_builder_card(p)
    payload=b"PNG_TEST_ONLY"
    with patch.object(builder_cards,'render_builder_card',return_value=payload), \
         patch("netrattler_visual_gate.strict_enabled",return_value=False), \
         patch("netrattler_visual_review.review_png",return_value=Mock(passed=True,problems=[])), \
         patch.object(cards,'_send_photo',return_value=123):
        assert builder_cards.send_builder_card('token','chat',p)==123


def test_builder_photo_callback_persists_original_message_id():
    p=pick();send_text=Mock()
    with patch.object(engine,'deduplicate_props',return_value=[]), \
         patch.object(engine,'build_builder_picks',return_value=[p]), \
         patch.object(engine,'builder_pick_exists',return_value=False), \
         patch('netrattler_builder_limit.at_limit',return_value=False), \
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
    import pytest
    # Model-only ladders have no bookmaker combined price: never display one.
    with pytest.raises(ValueError, match="2–6 Legs"):
        builder_cards.render_builder_card(adapted)


def test_model_cross_ladder_renders_all_stages():
    from types import SimpleNamespace
    leg=lambda name,match:SimpleNamespace(player=name,team='Club',match=match,league='League',
        market='2+ Fouls',category='fouls',line=2,odds=0,series=[2]*10,kickoff='')
    pick=SimpleNamespace(legs=[leg('A','Club A vs Club B'),leg('B','Club C vs Club D')],
        style='FOUL LEITER',match_date='2026-10-31',model_only=True,joint=.5,fair=2,
        tiers=[(2,.5),(3,.2),(4,.05)],tier_shift=False)
    import pytest
    # The exact template has a two-team header and must not mislabel cross-match legs.
    with pytest.raises(ValueError, match="eindeutiges Spiel"):
        builder_cards.render_builder_card(pick)


def test_new_goal_hunter_has_reference_proportions_and_no_made_up_data():
    tip={'match':'Team A vs Team B','player':'Player X','team':'Team A',
         'league':'Test','odds':2.0,'probability':50,'goals_per_game':0.5}
    with patch.object(cards,'_badge_bytes',return_value=_fake_reference_photo()), patch.object(cards,'_paste_badge'), patch.object(cards,'_player_photo',return_value=_fake_reference_photo()):
        raw=cards.render_scorer_card(tip,'2026-11-18')
        assert Image.open(io.BytesIO(raw)).size==(1122,1402)
        updated=cards.render_scorer_card(tip,'2026-11-18',{'marks':{'0':'win'}})
        assert Image.open(io.BytesIO(updated)).size==(1122,1402)


def test_new_builder_six_legs_and_l10_l15_not_invented():
    from types import SimpleNamespace as S
    from netrattler_neon_design import _form_label
    assert _form_label([1]*10,1,10)=='10/10 (100%)'
    assert _form_label([1]*10,1,15)=='—'
    assert _form_label([1]*15,1,15)=='15/15 (100%)'
    legs=[engine.PropLeg(f'Player {i}','Team A','Team A vs Team B',
            'Test','Shots 1+','shots',1,1.9,.7,'kambi') for i in range(6)]
    from dataclasses import replace
    legs=[replace(leg,kickoff='2026-11-18T18:30:00Z') for leg in legs]
    p=S(legs=legs,style='Six',match_date='2026-11-18',stake=.2,
        variant='6 LEG',status='pending',confidence='HOCH',joint_probability=.25,
        combined_quote_verified=True,combined_bookmaker_quote=10.0)
    with patch.object(cards,'_badge_bytes',return_value=_fake_reference_photo()), \
         patch.object(cards,'_player_photo',return_value=_fake_reference_photo()), \
         patch('netrattler_neon_design._stat_series',return_value=[1]*15):
        payload=builder_cards.render_builder_card(p)
    assert Image.open(io.BytesIO(payload)).size==(1122,1402)


def test_missing_history_and_quote_not_fabricated():
    from netrattler_neon_design import _form_label, _percent
    assert _form_label([],1,10)=='—'
    assert _percent(None) is None
    assert _percent(120) is None


def test_observed_l15_game_log_exact_and_no_fabricated_stats(monkeypatch):
    import netrattler_neon_design as nd
    from types import SimpleNamespace
    nd._observed_game_log.cache_clear()
    rows = [
        {"player_name":"Verified Player","team":"Club X","match_date":f"2026-10-{30-i:02d}",
         "event_id":str(i),"minutes":90,"shots":2} for i in range(15)
    ]
    response = SimpleNamespace(ok=True,json=lambda:rows)
    with patch.dict("os.environ",{"SUPABASE_URL":"https://example.supabase.co",
                                   "SUPABASE_SERVICE_ROLE_KEY":"fake"},clear=False):
        with patch("requests.get",return_value=response) as req:
            series = nd._observed_game_log("Verified Player","Club X","shots","2026-11-18")
    assert len(series)==15 and series==tuple([2]*15)
    assert req.call_args.kwargs["params"]["player_name"]=="eq.Verified Player"
    assert req.call_args.kwargs["params"]["team"]=="eq.Club X"
    assert req.call_args.kwargs["params"]["match_date"]=="lt.2026-11-18"
    nd._observed_game_log.cache_clear()


def test_observed_history_missing_middle_game_not_zero_filled():
    import netrattler_neon_design as nd
    from types import SimpleNamespace
    nd._observed_game_log.cache_clear()
    rows = [
        {"player_name":"Known","team":"Club A","match_date":f"2026-10-{30-i:02d}",
         "event_id":str(i),"minutes":90,"sot":None if i == 10 else 2}
        for i in range(15)
    ]
    with patch.dict("os.environ",{"SUPABASE_URL":"https://example.supabase.co",
                                   "SUPABASE_SERVICE_ROLE_KEY":"fake"},clear=False):
        with patch("requests.get",return_value=SimpleNamespace(ok=True,json=lambda:rows)):
            found = nd._observed_game_log("Known","Club A","sot","2026-11-18")
    assert len(found)==10
    assert nd._form_label(found,1,10)=="10/10 (100%)"
    assert nd._form_label(found,1,15)=="—"
    nd._observed_game_log.cache_clear()


def test_builder_shows_calculated_single_prices_but_not_fabricated_sgm_ev():
    from types import SimpleNamespace as S
    from netrattler_neon_design import _builder_quote_display
    legs = [S(odds=2.00,estimated=False,source="kambi"),
            S(odds=1.50,estimated=False,source="pinnacle")]
    actual = S(estimated_odds=False,model_only=False,combined_quote_verified=False)
    assert _builder_quote_display(actual,legs) == ("EINZELQUOTEN ×","3.00",None)
    verified = S(estimated_odds=False,model_only=False,combined_quote_verified=True,
                 combined_bookmaker_quote=2.80)
    assert _builder_quote_display(verified,legs) == ("BESTÄTIGTE KOMBIQUOTE","@ 2.80",2.80)
    fake = S(estimated_odds=True,model_only=False,combined_quote_verified=False)
    assert _builder_quote_display(fake,legs) == ("BUCHMACHERQUOTE","—",None)
    assert _builder_quote_display(actual,[S(odds=2,estimated=True,source="x")]) == (
        "BUCHMACHERQUOTE","—",None)


def test_strict_guard_rejects_placeholder_builder_without_sending():
    from types import SimpleNamespace as S
    from netrattler_visual_gate import validate_builder
    p=S(legs=[S(player="Unknown One",team="",match="Home vs Away",
                category="shots",line=1,source="book",odds=1.8,
                estimated=False,kickoff=""),
              S(player="Unknown Two",team="",match="Home vs Away",
                category="shots",line=1,source="book",odds=1.8,
                estimated=False,kickoff="")],
        match_date="2026-11-18",estimated_odds=False,
        combined_quote_verified=True,combined_bookmaker_quote=3.0)
    with patch("netrattler_visual_gate.club_for_player",return_value=""), \
         patch("netrattler_visual_gate.kickoff_for_match",return_value=""):
        prepared, reasons=validate_builder(p)
        assert prepared is None
        assert "missing_verified_team" in reasons
    with patch("netrattler_visual_gate.validate_builder",return_value=(None,["missing_verified_team"])), \
         patch.object(cards,"_send_photo",return_value=99) as send:
        assert builder_cards.send_builder_card("token","chat",p) is None
        send.assert_not_called()


def test_strict_guard_rejects_scorer_without_photos():
    from netrattler_visual_gate import validate_scorer
    tip={"match":"Home vs Away","player":"Some Player","team":"Home",
         "odds":5,"probability":40,"_source":"book","goals_per_game":0.5}
    with patch.object(cards,"_player_photo",return_value=b""), \
         patch.object(cards,"_badge_bytes",return_value=b""):
        reasons=validate_scorer(tip,"2026-11-18")
    assert "missing_scorer_photo" in reasons
    assert "missing_scorer_crest" in reasons


def test_team_normalization_is_strict_but_accepts_club_suffix():
    from netrattler_visual_gate import club_same
    assert club_same("Chapecoense-sc","Chapecoense")
    assert club_same("Remo FC","Remo")
    assert not club_same("Remo","Flamengo")
    assert not club_same("FC","FC")


def test_strict_builder_complete_metadata_can_be_sent_without_placeholders():
    from types import SimpleNamespace as S
    from netrattler_visual_gate import validate_builder
    from PIL import Image
    import io
    pixels=io.BytesIO()
    Image.new("RGB",(120,120),"#245377").save(pixels,format="PNG")
    raw=pixels.getvalue()
    legs=[S(player="Player One",team="Home",match="Home vs Away",
            league="Some League",market="Shots",category="shots",
            line=1,odds=1.8,probability=.7,quality=.82,
            source="kambi",estimated=False,kickoff="2099-01-01T18:30:00Z"),
          S(player="Player Two",team="Away",match="Home vs Away",
            league="Some League",market="Shots",category="shots",
            line=1,odds=1.9,probability=.68,quality=.75,
            source="kambi",estimated=False,kickoff="2099-01-01T18:30:00Z")]
    pick=S(legs=legs,match_date="2099-01-01",estimated_odds=False,
           combined_quote_verified=True,combined_bookmaker_quote=3.10)
    with patch("netrattler_neon_design._stat_series",return_value=[1]*15), \
         patch.object(cards,"_player_photo",return_value=raw), \
         patch.object(cards,"_badge_bytes",return_value=raw):
        ready,reasons=validate_builder(pick)
    assert not reasons
    assert len(ready.legs)==2
    assert abs(ready.joint_probability - (.7 * .68))<1e-9
    assert ready.confidence=="HOCH"
    assert all(str(x.kickoff).endswith("+00:00") for x in ready.legs)


def test_exact_observed_club_returned_for_short_fixture_alias():
    from types import SimpleNamespace as S
    import netrattler_visual_gate as gate
    gate.club_for_player.cache_clear()
    row={"player_name":"Giovanni Augusto","team":"Chapecoense","match_date":"2026-11-14"}
    response=S(ok=True,json=lambda:[row])
    with patch.dict("os.environ",{"SUPABASE_URL":"https://example.supabase.co",
                                   "SUPABASE_SERVICE_ROLE_KEY":"fake"}), \
         patch.object(gate.requests,"get",return_value=response):
        club=gate.club_for_player("Giovanni Augusto","Remo vs Chapecoense-sc","2026-11-18")
    assert club=="Chapecoense"
    gate.club_for_player.cache_clear()


def test_safely_alias_atletico_paranaense_without_confusing_mg():
    from netrattler_visual_gate import club_same
    assert club_same("Athletico-PR","Atletico Paranaense")
    assert club_same("Atletico Paranaense","Athletico Paranaense")
    assert not club_same("Atlético-MG","Atletico Paranaense")


def test_goal_hunter_observed_goals_per_game_not_invented():
    from netrattler_visual_gate import enrich_scorer
    tip={"match":"Home vs Away","team":"Home","player":"Real Player"}
    with patch("netrattler_neon_design._observed_game_log",return_value=tuple([1,0,0,1,0,0,0,0,0,0])):
        out=enrich_scorer(tip,"2026-11-18")
    assert out["goals_per_game"]==0.20
    assert out["goals_per_game_sample"]==10
    assert "goals_per_game" not in tip
    with patch("netrattler_neon_design._observed_game_log",return_value=tuple([1]*4)):
        assert "goals_per_game" not in enrich_scorer(tip,"2026-11-18")

def test_brazilian_club_logo_uses_canonical_name_without_dummy_crest():
    # Visual QA detected Athletico-PR as the only missing badge in the asset probe.
    seen = []
    with patch.object(cards, "_crest_from_index", return_value="") as indexed, \
         patch.object(cards, "_fl_logo", return_value=""), \
         patch.object(cards, "_wikidata_logo", return_value=""), \
         patch.object(cards, "_apifootball_logo", side_effect=lambda name, league="": seen.append(name) or "https://example.org/real-logo.png"), \
         patch.object(cards, "_LOGO_CACHE", {}):
        result = cards._logo_url("Athletico-PR")
    assert result == "https://example.org/real-logo.png"
    assert seen and seen[-1] == "Athletico Paranaense"


def test_scorer_rejects_coutinho_unverified_high_quote_and_fake_rate():
    from netrattler_visual_gate import validate_scorer
    tip={"match":"Coritiba vs Santos","player":"Philippe Coutinho","team":"Santos",
         "odds":9.50,"probability":18,"fairOdds":5.56,
         "_source":"test_only","goals_per_game":0.30,
         "_kickoff":"2099-01-01T22:30:00+00:00"}
    with patch.object(cards,"_player_photo",return_value=_fake_reference_photo()), \
         patch.object(cards,"_badge_bytes",return_value=_fake_reference_photo()), \
         patch("netrattler_neon_design._observed_game_log",return_value=(0,)*15):
        reasons=validate_scorer(tip,"2099-01-01")
    assert "unverified_scorer_quote_origin" in reasons
    assert "scorer_quote_gate_below_probability" in reasons
    assert "inconsistent_scorer_goals_per_game" in reasons


def test_scorer_rejects_probability_fair_quote_mismatch():
    from netrattler_visual_gate import validate_scorer
    tip={"match":"Coritiba vs Santos","player":"Verified Player","team":"Santos",
         "odds":2.50,"probability":45,"fairOdds":5.56,
         "_source":"kambi","goals_per_game":0.20,
         "_kickoff":"2099-01-01T22:30:00+00:00"}
    with patch.object(cards,"_player_photo",return_value=_fake_reference_photo()), \
         patch.object(cards,"_badge_bytes",return_value=_fake_reference_photo()), \
         patch("netrattler_neon_design._observed_game_log",return_value=(1,0,0,1,0,0,0,0,0,0)):
        reasons=validate_scorer(tip,"2099-01-01")
    assert "inconsistent_scorer_fair_odds" in reasons
    assert "inconsistent_scorer_goals_per_game" not in reasons


def test_goal_hunter_silhouette_detection_blocks_monochrome_placeholder():
    from netrattler_visual_review import _looks_like_grey_placeholder
    from PIL import Image, ImageDraw
    silhouette = Image.new("RGB",(160,160),(210,211,212))
    draw=ImageDraw.Draw(silhouette)
    draw.ellipse((53,27,107,84),fill=(138,139,140))
    draw.rounded_rectangle((31,77,129,156),radius=30,fill=(138,139,140))
    assert _looks_like_grey_placeholder(silhouette,(0,0,160,160))
    portrait=Image.new("RGB",(160,160),(43,94,150))
    ImageDraw.Draw(portrait).ellipse((53,27,107,84),fill=(194,135,99))
    assert not _looks_like_grey_placeholder(portrait,(0,0,160,160))


def test_coutinho_santos_photo_fallback_uses_exact_fotmob_id():
    from types import SimpleNamespace
    import netrattler_stats_match_cards as cards
    player="Philippe Coutinho"
    raw=_fake_reference_photo()
    requested=[]
    def mock_get(url,*args,**kwargs):
        requested.append(url)
        if url=="https://images.fotmob.com/image_resources/playerimages/184536.png":
            return SimpleNamespace(ok=True,content=raw,status_code=200)
        return SimpleNamespace(ok=False,content=b"",status_code=404)
    with patch.object(cards,"_PLAYER_CACHE",{}), \
         patch.object(cards.requests,"get",side_effect=mock_get), \
         patch("netrattler_espn_photo.espn_photo",return_value=""), \
         patch("netrattler_api_portraits.portrait",return_value=""), \
         patch("netrattler_commons_photos.commons_photo",return_value=""), \
         patch("netrattler_apif_profile_photo.profile_photo",return_value=""), \
         patch("netrattler_reference_images.player_urls",return_value=[]):
        assert cards._player_photo(player,"Santos")==raw
        assert requested[0]=="https://images.fotmob.com/image_resources/playerimages/184536.png"
        requested.clear()
        cards._player_photo(player,"Coritiba")
        assert "https://images.fotmob.com/image_resources/playerimages/184536.png" not in requested
