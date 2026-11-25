"""Read compact API-Football corner history into the existing measured-history path."""
from datetime import date, timedelta
import os
import requests


def install(bot):
    original = getattr(bot, '_fd_co_uk_load_csv', None)
    if not callable(original) or getattr(getattr(bot, '_ntr_corner_history', None), '_api_corner_store', False):
        return
    cache = {}

    def load(league):
        base = list(original(league) or [])
        lid = getattr(bot, 'API_FOOTBALL_LEAGUES', {}).get(league)
        if not lid:
            return base
        if lid not in cache:
            cache[lid] = []
            sb = os.getenv('SUPABASE_URL', '').rstrip('/')
            key = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_KEY', '')
            if sb and key:
                try:
                    rows = []
                    cutoff = (date.today() - timedelta(days=540)).isoformat()
                    # PostgREST can cap each response independently of limit.
                    # Use a stable unique tie-breaker and advance by returned rows.
                    while len(rows) < 3000:
                        r = requests.get(sb + '/rest/v1/netrattler_api_corner_history',
                            headers={'apikey':key, 'Authorization':'Bearer ' + key},
                            params={'league_id':'eq.' + str(lid),
                                    'order':'match_date.desc,fixture_id.desc',
                                    'limit':str(min(1000, 3000 - len(rows))),
                                    'offset':str(len(rows)),
                                    'match_date':'gte.' + cutoff}, timeout=12)
                        r.raise_for_status()
                        page = r.json()
                        if not isinstance(page, list):
                            raise ValueError('invalid corner history response')
                        if not page:
                            break
                        rows.extend(page[:3000 - len(rows)])
                    cache[lid] = [dict(Date=x['match_date'], HomeTeam=x['home_team'], AwayTeam=x['away_team'],
                        HC=x['home_corners'], AC=x['away_corners'], FTHG=x['home_goals'], FTAG=x['away_goals'],
                        _source='api-football') for x in rows]
                except (requests.RequestException, ValueError, TypeError, KeyError):
                    bot.log('API corner history unavailable; using existing measured history', 'WARN')
        # Prefer the existing CSV when both sources contain the same match.
        return cache[lid] + base

    load._api_corner_store = True
    bot._ntr_corner_history = load
