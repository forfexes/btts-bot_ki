"""Bounded, attributed historical references. Never supplies a publishable price.

Snapshot revisions are pinned. Predictions are benchmark inputs only. Only
observed scores can enter result enrichment, with exact date/ordered teams.
No Supabase writes and no broad historical player-data imports.
"""
import csv
import io
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

SOURCES = {
 'tipsaudit': dict(dataset='tipsaudit/football-predictions-closing-odds-margins',
  revision='2229336aae1894dff776fe394c24ba4e59012bdd', file='tipsaudit-predictions.csv',
  license='CC-BY-4.0', attribution='TipsAudit https://tipsaudit.com', end='2026-10-27', purpose='1X2 benchmark only'),
 'footinsights': dict(dataset='footinsights/football-predictions-settled',
  revision='589784dfa798b892eed6a32ea71196d7933a8038', file='predictions.csv',
  license='CC-BY-4.0', attribution='FootInsights https://footinsights.com/data/', end='2026-10-26', purpose='historical scores and external model benchmark'),
 'minmaxxxer': dict(dataset='minmaxxxer/premier-league-odds-2026-27',
  revision='ad822acbb8e7fc7e1128715c247cb97e5746c328', file='premier_league_2026_27_odds.csv',
  license='CC-BY-4.0', attribution='minmaxxxer https://huggingface.co/minmaxxxer', end='2026-10-25', purpose='historical scores and consensus benchmark'),
}
REVIEW = {
 'margussellin/oddsintel-football-closes-sample': 'CC-BY-NC-4.0; non-commercial snapshot only; excluded from production',
 'Oscar343/soccer-dataset': 'CC-BY-4.0; verified FT coverage ends 2026-07-04; excludes October settlement; no bulk import',
 'oliviersportsdata/European-Football-Timestamped-Odds-Pinnacle-Match-Stats': 'custom license; 20-match sample; excluded from production',
 'oliviersportsdata/World-Football-Timestamped-Odds-Pinnacle-Match-Stats': 'custom license; 20-match sample; excluded from production',
}
MAX_BYTES = 16 * 1024 * 1024
MAX_ROWS = 50000
_CACHE = {}


def read_rows(key):
    if key in _CACHE:
        return _CACHE[key]
    spec = SOURCES[key]
    url = f"https://huggingface.co/datasets/{spec['dataset']}/resolve/{spec['revision']}/{spec['file']}"
    with urlopen(Request(url, headers={'User-Agent': 'NETRATTLER-Reference/1.0'}), timeout=20) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('reference byte budget exceeded')
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    rows = []
    for row in reader:
        if len(rows) >= MAX_ROWS:
            raise ValueError('reference row budget exceeded')
        rows.append(row)
    _CACHE[key] = rows
    return rows


def observed(value, maximum=30):
    if value is None or isinstance(value, bool) or value == '':
        return None
    try:
        v = float(value)
        return int(v) if math.isfinite(v) and v.is_integer() and 0 <= v <= maximum else None
    except (ValueError, TypeError):
        return None


def fixtures(rows):
    """One fixture per UTC kickoff and ordered teams; conflicting scores excluded."""
    grouped = defaultdict(list)
    for row in rows:
        home, away = row.get('home_team'), row.get('away_team')
        hs, aw = observed(row.get('home_goals')), observed(row.get('away_goals'))
        try:
            kickoff = datetime.fromisoformat(str(row.get('kickoff_utc') or '').replace('Z', '+00:00'))
            if kickoff.tzinfo is None or kickoff > datetime.now(timezone.utc):
                continue
        except ValueError:
            continue
        if not home or not away or home == away or hs is None or aw is None:
            continue
        grouped[(kickoff.isoformat(), home, away)].append(row)
    out = []
    for key, items in grouped.items():
        if len({(observed(x.get('home_goals')), observed(x.get('away_goals'))) for x in items}) != 1:
            continue
        # Repeated market calls cannot count as repeated matches.
        out.append(dict(items[0]))
    return out


def collect(tips, match_parts, row_date, same, log=print):
    wanted = [(row_date(t), *match_parts(t)[:2]) for t in tips]
    result = []
    for source in ('footinsights', 'minmaxxxer'):
        spec = SOURCES[source]
        # Avoid network work when the pinned snapshot cannot cover any requested day.
        if not any(d and d <= spec['end'] and h and a for d, h, a in wanted):
            continue
        try:
            for row in fixtures(read_rows(source)):
                day = datetime.fromisoformat(row['kickoff_utc'].replace('Z', '+00:00')).astimezone(timezone.utc).date().isoformat()
                home, away = row['home_team'], row['away_team']
                if not any(d == day and same(h, home) and same(a, away) for d, h, a in wanted):
                    continue
                item = dict(source='hf_reference:' + source, _result_table='hf_reference:' + source,
                            match_date=day, home_team=home, away_team=away,
                            home_score=observed(row['home_goals']), away_score=observed(row['away_goals']),
                            raw={'attribution': spec['attribution'], 'revision': spec['revision'],
                                 'license': spec['license']})
                hh, ha = observed(row.get('ht_home_goals')), observed(row.get('ht_away_goals'))
                if hh is not None and ha is not None and hh <= item['home_score'] and ha <= item['away_score']:
                    item.update(home_score_ht=hh, away_score_ht=ha)
                result.append(item)
        except Exception as exc:
            log('HF reference unavailable: ' + source + ' ' + type(exc).__name__)
    log(f'HF historical reference: results={len(result)} db_raw_writes=0')
    return result


def benchmark(key, rows):
    cols = {'tipsaudit': ('fair_prob_home', 'fair_prob_draw', 'fair_prob_away'),
            'footinsights': ('p_home', 'p_draw', 'p_away'),
            'minmaxxxer': ('close_home_prob', 'close_draw_prob', 'close_away_prob')}[key]
    samples = rows if key == 'tipsaudit' else fixtures(rows)
    seen, scores, days = set(), [], []
    for row in samples:
        identity = (row.get('kickoff_utc'), row.get('home_team') or row.get('home'), row.get('away_team') or row.get('away'))
        if identity in seen:
            continue
        outcome = row.get('result')
        if key == 'tipsaudit':
            if row.get('void_reason'):
                continue
            outcome = {'1': 'home', 'X': 'draw', '2': 'away'}.get(outcome)
        elif key == 'footinsights':
            h, a = observed(row['home_goals']), observed(row['away_goals'])
            outcome = 'home' if h > a else ('away' if a > h else 'draw')
        if outcome not in ('home', 'draw', 'away'):
            continue
        try:
            p = [float(row[c]) for c in cols]
            if not all(math.isfinite(v) and 0 <= v <= 1 for v in p) or abs(sum(p) - 1) > 0.015:
                continue
        except (ValueError, KeyError, TypeError):
            continue
        seen.add(identity)
        scores.append(sum((v - int(i == ('home', 'draw', 'away').index(outcome))) ** 2 for i, v in enumerate(p)))
        days.append(str(row.get('kickoff_utc') or '')[:10])
    return dict(input_rows=len(rows), scored_fixtures=len(scores), brier_1x2=sum(scores)/len(scores) if scores else None,
                date_min=min(days) if days else None, date_max=max(days) if days else None,
                usage='external_reference_only; never a tip quote or automatic model replacement')


def main():
    report = {'sources': SOURCES, 'reviewed_exclusions': REVIEW, 'db_writes': 0, 'benchmarks': {}}
    for key in SOURCES:
        try:
            report['benchmarks'][key] = benchmark(key, read_rows(key))
        except Exception as exc:
            report['benchmarks'][key] = {'error': type(exc).__name__}
    Path('hf_reference_report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if not any(x.get('scored_fixtures') for x in report['benchmarks'].values()):
        raise SystemExit(1)

if __name__ == '__main__': main()
