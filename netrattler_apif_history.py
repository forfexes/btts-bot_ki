"""Bounded API-Football history for upcoming teams. No Telegram, raw dumps or invented zeros."""
import os
import json
from datetime import datetime, timezone, timedelta
import requests
from netrattler_apif_response import checked_response, number
from netrattler_apifootball_players import PRIORITY

BASE = 'https://v3.football.api-sports.io'


def completed(fx, today):
    f = fx.get('fixture') or {}
    return (f.get('status') or {}).get('short') == 'FT' and bool(f.get('date')) and f['date'][:10] < today


def player_rows(payload, fx):
    out = []
    teams = fx['teams']
    for team in payload:
        tid = (team.get('team') or {}).get('id')
        if tid not in (teams['home']['id'], teams['away']['id']):
            continue
        own = teams['home'] if tid == teams['home']['id'] else teams['away']
        opp = teams['away'] if tid == teams['home']['id'] else teams['home']
        for p in team.get('players') or []:
            stats = p.get('statistics') or []
            if len(stats) != 1:
                continue
            s = stats[0]; g = s.get('games') or {}; person = p.get('player') or {}
            if not person.get('id') or not person.get('name') or not number(g.get('minutes')):
                continue
            row = dict(match_id='apif:' + str(fx['fixture']['id']), player_id=person['id'],
                       player_name=person['name'], team=own['name'], opponent=opp['name'],
                       league=fx['league']['name'], match_date=fx['fixture']['date'][:10],
                       minutes=number(g.get('minutes')), position=g.get('position'), source='apif')
            for col, group, field in [('shots','shots','total'),('shots_on','shots','on'),
                ('fouls_committed','fouls','committed'),('fouls_drawn','fouls','drawn'),
                ('tackles','tackles','total'),('interceptions','tackles','interceptions'),
                ('yellow','cards','yellow'),('red','cards','red'),('goals','goals','total'),
                ('assists','goals','assists'),('saves','goals','saves')]:
                row[col] = number((s.get(group) or {}).get(field))
            out.append(row)
    return out


def corner_row(payload, fx):
    vals = {}
    for item in payload:
        tid = (item.get('team') or {}).get('id')
        for stat in item.get('statistics') or []:
            if stat.get('type') == 'Corner Kicks':
                vals[tid] = number(stat.get('value'))
    h, a = fx['teams']['home'], fx['teams']['away']
    hc, ac = vals.get(h['id']), vals.get(a['id'])
    gh, ga = number((fx.get('goals') or {}).get('home')), number((fx.get('goals') or {}).get('away'))
    if None in (hc, ac, gh, ga) or max(hc, ac) > 30:
        return None
    return dict(fixture_id=fx['fixture']['id'], league_id=fx['league']['id'],
                match_date=fx['fixture']['date'][:10], home_team=h['name'], away_team=a['name'],
                home_corners=hc, away_corners=ac, home_goals=gh, away_goals=ga)


class Importer:
    def __init__(self):
        self.sb = os.environ['SUPABASE_URL'].rstrip('/')
        self.key = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.environ['SUPABASE_KEY']
        self.h = {'apikey': self.key, 'Authorization': 'Bearer ' + self.key}
        keys = (os.getenv('API_FOOTBALL_KEYS') or '').replace('\n', ',').split(',')
        self.api_key = next((k.strip() for k in keys if k.strip()), '')
        if not self.api_key:
            raise RuntimeError('API-Football configuration missing')
        self.calls = 0
        self.max_calls = min(600, int(os.getenv('APIF_HISTORY_MAX_CALLS', '400')))
        self.ceiling = min(430, float(os.getenv('APIF_HISTORY_MAX_MB', '430')))
        self.initial_mb = self.capacity()

    def capacity(self):
        r = requests.post(self.sb + '/rest/v1/rpc/db_size_mb', headers=self.h, json={}, timeout=30)
        r.raise_for_status(); value = r.json()
        mb = float(value['mb'])
        if not 0 < mb < self.ceiling:
            raise RuntimeError('History import paused: database capacity reserve')
        return mb

    def api(self, path, params):
        if self.calls >= self.max_calls:
            raise RuntimeError('History API budget reached')
        self.calls += 1
        r = requests.get(BASE + path, headers={'x-apisports-key': self.api_key}, params=params, timeout=25)
        return checked_response(r)

    def rest(self, table, params):
        r = requests.get(self.sb + '/rest/v1/' + table, headers=self.h, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def save(self, table, rows, conflict):
        if not rows:
            return 0
        self.capacity()
        r = requests.post(self.sb + '/rest/v1/' + table, params={'on_conflict': conflict},
                          headers={**self.h, 'Prefer': 'resolution=ignore-duplicates,return=representation'},
                          json=rows, timeout=40)
        r.raise_for_status()
        return len(r.json())

    def run(self):
        today = datetime.now(timezone.utc).date()
        fixtures = []
        for d in range(3):
            fixtures.extend(self.api('/fixtures', {'date': (today + timedelta(days=d)).isoformat()}))
        fixtures = [f for f in fixtures if (f.get('league') or {}).get('id') in PRIORITY
                    and (f.get('fixture') or {}).get('status', {}).get('short') in ('NS', 'TBD')]
        fixtures.sort(key=lambda f: (PRIORITY.index(f['league']['id']), f['fixture']['date']))
        # Round-robin leagues so a full PL schedule cannot starve other groups.
        grouped = {lid: [f for f in fixtures if f['league']['id'] == lid] for lid in PRIORITY}
        fixtures = [grouped[lid][i] for i in range(max((len(v) for v in grouped.values()), default=0))
                    for lid in PRIORITY if len(grouped[lid]) > i]
        targets, teams = [], set()
        for fx in fixtures:
            for side in ('home', 'away'):
                tid = fx['teams'][side]['id']
                if tid not in teams:
                    targets.append((tid, fx['league']['id'], fx['league']['season']))
                    teams.add(tid)
        targets = targets[:min(32, int(os.getenv('APIF_HISTORY_MAX_TEAMS', '16')))]
        history = {}
        for tid, lid, season in targets:
            for fx in self.api('/fixtures', {'team': tid, 'league': lid, 'last': 15, 'status': 'FT'}):
                if completed(fx, today.isoformat()):
                    history[fx['fixture']['id']] = fx
        # Prioritise complete team windows in target order, not random leagues.
        saved_players = saved_corners = player_calls = corner_calls = 0
        player_budget_full = False
        max_rows = min(3000, int(os.getenv('APIF_HISTORY_MAX_PLAYER_ROWS', '2400')))
        for fid, fx in history.items():
            if self.calls + 2 > self.max_calls:
                break
            if not player_budget_full and saved_players < max_rows:
                existing = self.rest('fplci_player_match', {'select':'player_id', 'match_id':'eq.apif:' + str(fid), 'limit':'1'})
                if not existing:
                    rows = player_rows(self.api('/fixtures/players', {'fixture':fid}), fx)
                    player_calls += 1
                    # Never truncate a match's roster; retry that match in a later run.
                    if rows and saved_players + len(rows) <= max_rows:
                        saved_players += self.save('fplci_player_match', rows, 'match_id,player_id')
                        from netrattler_game_log_sync import to_log_row
                        logs = [to_log_row(r) for r in rows]
                        self.save('player_game_log', [r for r in logs if r], 'player_key,event_id')
                    elif rows:
                        player_budget_full = True
            existing = self.rest('netrattler_api_corner_history', {'select':'fixture_id', 'fixture_id':'eq.' + str(fid)})
            if not existing:
                row = corner_row(self.api('/fixtures/statistics', {'fixture':fid}), fx)
                corner_calls += 1
                if row:
                    saved_corners += self.save('netrattler_api_corner_history', [row], 'fixture_id')
        report = dict(probe='apif_history', teams=len(targets), available_history_fixtures=len(history),
                      api_calls=self.calls, player_calls=player_calls, corner_calls=corner_calls,
                      inserted_players=saved_players, inserted_corners=saved_corners,
                      before_mb=self.initial_mb, after_mb=self.capacity(), player_row_cap=max_rows)
        print(json.dumps(report))
        return report


if __name__ == '__main__':
    Importer().run()
