import datetime as _dt
from unittest.mock import Mock,patch
import netrattler_scorer_identity as identity
import netrattler_api_portraits as portraits
import netrattler_settlement_v16_final as s


D=(_dt.date.today()-_dt.timedelta(days=1)).isoformat()  # frisch, sonst greift Stale-Void (>7 Tage)


def legacy():
    return {'tip_id':'scorer_R._Cherki_Manchester_City_vs_Brighton_'+D+'',
            'market':'scorer','group_key':'scorer','match':'Manchester City vs Brighton',
            'date':D,'odds':'6.5','units':.75,'status':'pending'}


def test_legacy_scorer_is_player_market_and_settles_from_real_goals():
    tip=legacy()
    assert s.unpack(tip)['player']=='R. Cherki' and s.category_of(tip)=='score'
    stat={'player_name':'R. Cherki','team':'Manchester City','opponent':'Brighton',
          'match_date':D,'minutes':90,'goals':0}
    result={'home_team':'Manchester City','away_team':'Brighton','match_date':D,
            'home_score':0,'away_score':1}
    settled=s.settle_tip(tip,[result],[stat])
    assert settled['status']=='loss' and 'Markt nicht erkannt' not in settled['reason']
    stat['goals']=1
    assert s.settle_tip(tip,[{**result,'home_score':1}],[stat])['status']=='win'
    stat['goals']=None
    assert s.settle_tip(tip,[result],[stat])['status']=='pending'


def test_abbreviated_club_names_dedupe_same_player_only():
    row={'market':'scorer','tip_id':'scorer_O._Afolayan_Swansea_vs_Blackburn_2026-10-31',
         'match':'Swansea vs Blackburn','date':'2026-10-31','telegram_msg_id':807}
    dedupe=identity.ReceiptDedupe([row])
    assert dedupe.contains({'match':'Swansea City AFC vs Blackburn Rovers FC','player':'O. Afolayan'})
    assert not dedupe.contains({'match':'Swansea City AFC vs Blackburn Rovers FC','player':'Andri Gudjohnsen'})
    assert not identity.recover({**row,'tip_id':'unrelated'}) .get('player')


def test_api_portrait_requires_unique_id_and_own_club():
    response=Mock(ok=True);response.json.return_value=[{'player_name':'Rayan Cherki','team':'Manchester City','player_id':123}]
    with patch.dict('os.environ',{'SUPABASE_URL':'https://example.test','SUPABASE_KEY':'test'}), \
         patch.object(portraits,'_CALLS',0),patch.object(portraits.requests,'get',return_value=response):
        assert portraits.portrait('R. Cherki','Manchester City').endswith('/123.png')
        assert not portraits.portrait('R. Cherki','Brighton')
        response.json.return_value.append({'player_name':'Robert Cherki','team':'Manchester City','player_id':456})
        assert not portraits.portrait('R. Cherki','Manchester City')


def test_scorer_alias_duplicate_counts_once_in_statistics():
    a=legacy();b={**a,'match':'Manchester City vs Brighton & Hove Albion','player_name':'R. Cherki'}
    rows=[{'market_group':'scorer','tip_payload':t,'tip_date':'2026-10-31','settled_at':'2026-11-01'} for t in (a,b)]
    # The explicit alias is Brighton Hove Albion; punctuation is normalized.
    assert len(identity.dedupe_history(rows))==1


def test_initial_and_full_name_are_same_player():
    from netrattler_scorer_identity import ReceiptDedupe, person
    assert person("A. Gouiri") == person("Amine Gouiri")
    assert person("Amine Gouiri") != person("Jonathan Gouiri2")
    seen = ReceiptDedupe([{"match": "Marseille vs Toulouse", "market": "scorer", "player": "A. Gouiri", "telegram_msg_id": 1}])
    assert seen.contains({"match": "Marseille vs Toulouse", "player": "Amine Gouiri"})
    assert not seen.contains({"match": "Marseille vs Toulouse", "player": "Mason Greenwood"})


def test_real_scorer_fixture_aliases_dedupe_without_merging_unrelated_clubs():
    # Both alias pairs were published twice on 2026-11-01 before normalization.
    from netrattler_scorer_identity import ReceiptDedupe, fixture
    assert fixture("Académico de Viseu FC vs Rio Ave FC") == fixture("Academico Viseu vs Rio Ave")
    assert fixture("Olympique de Marseille vs Toulouse FC") == fixture("Marseille vs Toulouse")
    sent = ReceiptDedupe([
        {"match": "Académico de Viseu FC vs Rio Ave FC", "market": "scorer",
         "player_name": "André Clóvis", "telegram_msg_id": 111},
        {"match": "Olympique de Marseille vs Toulouse FC", "market": "scorer",
         "player_name": "A. Gouiri", "telegram_msg_id": 222},
    ])
    assert sent.contains({"match": "Academico Viseu vs Rio Ave", "player": "André Clóvis"})
    assert sent.contains({"match": "Marseille vs Toulouse", "player": "Amine Gouiri"})
    assert not sent.contains({"match": "Paris FC vs Toulouse", "player": "Amine Gouiri"})
    assert not sent.contains({"match": "Marseille vs Toulouse", "player": "Mason Greenwood"})


def test_team_name_variants_are_same_fixture():
    from netrattler_scorer_identity import ReceiptDedupe
    seen = ReceiptDedupe([{"match": "Marseille vs Toulouse", "market": "scorer", "player": "A. Gouiri", "telegram_msg_id": 1}])
    assert seen.contains({"match": "Olympique de Marseille vs Toulouse FC", "player": "Amine Gouiri"})
    assert not seen.contains({"match": "Lyon vs Nice", "player": "A. Gouiri"})
    s2 = ReceiptDedupe([{"match": "Academico Viseu vs Rio Ave", "market": "scorer", "player": "André Clóvis", "telegram_msg_id": 1}])
    assert s2.contains({"match": "Académico de Viseu FC vs Rio Ave FC", "player": "Andre Clovis"})
    s3 = ReceiptDedupe([{"match": "Swansea vs Blackburn", "market": "scorer", "player": "O. Afolayan", "telegram_msg_id": 1}])
    assert s3.contains({"match": "Swansea City AFC vs Blackburn Rovers FC", "player": "O. Afolayan"})
