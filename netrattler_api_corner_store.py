"""Read compact API-Football corner history into the existing measured-history path."""
from datetime import date, timedelta
import os
import requests


def install(bot):
    original = getattr(bot, '_fd_co_uk_load_csv', None)
    if not callable(original) or getattr(original, '_api_corner_store', False):
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
                    r = requests.get(sb + '/rest/v1/netrattler_api_corner_history',
                        headers={'apikey':key, 'Authorization':'Bearer ' + key},
                        params={'league_id':'eq.' + str(lid), 'order':'match_date.desc', 'limit':'1000',
                                'match_date':'gte.' + (date.today()-timedelta(days=180)).isoformat()}, timeout=12)
                    r.raise_for_status()
                    cache[lid] = [dict(Date=x['match_date'], HomeTeam=x['home_team'], AwayTeam=x['away_team'],
                        HC=x['home_corners'], AC=x['away_corners'], FTHG=x['home_goals'], FTAG=x['away_goals'],
                        _source='api-football') for x in r.json()]
                except (requests.RequestException, ValueError, TypeError, KeyError):
                    bot.log('API corner history unavailable; using existing measured history', 'WARN')
        # Prefer the existing CSV when both sources contain the same match.
        return cache[lid] + base

    load._api_corner_store = True
    bot._fd_co_uk_load_csv = load
