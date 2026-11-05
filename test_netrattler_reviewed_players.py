import unittest
from netrattler_reviewed_players import collect,recoverable
from netrattler_settlement_v16_final import match_parts,row_date,_strict_team_match,settle_player_market,unpack

class ReviewedPlayers(unittest.TestCase):
    def tip(self):
        return dict(tip_id='x',match_date='2026-10-29',match='Benfica vs Gil Vicente',
                    player='Gianluca Prestianni',team='Benfica',category='sot',line=1)
    def test_observed_zero_unknown_and_wrong_fixture(self):
        tip=self.tip();r,p=collect([tip],match_parts,row_date,_strict_team_match)
        self.assertEqual(settle_player_market(tip,p,None)[0],'loss')
        self.assertEqual(settle_player_market(dict(tip,category='shots'),p,None)[0],'pending')
        for change in ({'player':'Other'},{'team':'Gil Vicente'},{'match_date':'2026-10-30'},{'match':'Benfica vs Porto'}):
            self.assertEqual(collect([dict(tip,**change)],match_parts,row_date,_strict_team_match),([],[]))
    def test_timeout_void_recovery_requires_receipt(self):
        tip=self.tip();row=dict(status='void',reason='void: kein Ergebnis nach 3 Tagen',tip_payload=tip)
        self.assertEqual(len(recoverable([row],unpack,lambda t:True,match_parts,row_date,_strict_team_match)),1)
        self.assertEqual(recoverable([row],unpack,lambda t:False,match_parts,row_date,_strict_team_match),[])
        self.assertEqual(recoverable([dict(row,reason='void: Spieler ohne Einsatz')],unpack,lambda t:True,match_parts,row_date,_strict_team_match),[])
    def test_observed_fouls_won(self):
        tip=dict(self.tip(),match='Braga vs Famalicao',team='Famalicao',player='Pedro Bondo',category='fouls_won')
        r,p=collect([tip],match_parts,row_date,_strict_team_match)
        self.assertEqual(settle_player_market(tip,p,None)[0],'win')
        self.assertEqual(p[0]['fouls_won'],3)

def test_rrahmani_measured_zero_keeps_other_stats_unknown():
    tip=dict(match_date='2026-11-04',match='FC Porto vs SSC Napoli',
             player='Amir Rrahmani',team='Napoli',category='shots',line=1)
    r,p=collect([tip],match_parts,row_date,_strict_team_match)
    assert len(p)==1 and p[0]['minutes']==90 and p[0]['shots']==0
    assert settle_player_market(tip,p,None)[0]=='loss'
    assert settle_player_market(dict(tip,category='sot'),p,None)[0]=='loss'
    assert settle_player_market(dict(tip,category='fouls'),p,None)[0]=='pending'
    assert collect([dict(tip,match='Porto vs Benfica')],match_parts,row_date,_strict_team_match)==([],[])

if __name__=='__main__':unittest.main()
