#!/usr/bin/env python3
from netrattler_identity_hub import teams_match
from netrattler_source_hub import parse_openfootball_json, parse_football_txt, source_health_snapshot

assert teams_match('England', 'New England Revolution II') is False
assert teams_match('Columbus Crew II', 'Columbus Crew 2') is True
payload = {'matches': [{'date': '2026-07-15', 'team1': 'England', 'team2': 'Argentina', 'score': {'ft': [1, 1]}}]}
assert parse_openfootball_json(payload, '2026-07-15', source='x')[0]['home_score'] == 1
text = '2026-07-15\nEngland 2-1 Argentina\n'
assert parse_football_txt(text, '2026-07-15', source='txt')[0]['away_team'] == 'Argentina'
assert len(source_health_snapshot()) >= 10
print('Source Hub V30 tests OK')
