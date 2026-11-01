"""Reviewed fixture-specific corner evidence. No scraped pages or DB raw imports.

Keys bind evidence to the original tip ID; provider dates remain unchanged.
Only observed full-match counts are supplied, never inferred player values.
"""
from copy import deepcopy

# tip ID, actual match day, teams, FT score, observed corners, evidence URL
EVIDENCE = [
    ('corners_América_vs_Tijuana_2026-10-28', '2026-10-28', 'América', 'Tijuana', 1, 1, 9, 2,
     'https://previa90.com/en/match-report/club-america-vs-club-tijuana-2026-10-28/'),
    ('corners_Bahia_vs_São_Paulo_2026-10-28', '2026-10-28', 'Bahia', 'São Paulo', 3, 2, 7, 11,
     'https://placar.com.br/salvador-bahia/futebol/brasileiro-serie-a-2026/jogo/10-2026/147479/bahia-sao-paulo/'),
    ('corners_Cuarte_vs_Girona_2026-10-27', '2026-10-27', 'Cuarte', 'Girona', 0, 2, 5, 2,
     'https://statz.ai/h2h/cuarte-industrial-vs-girona/19893306'),
    ('corners_Sonnenhof_Grossaspach_vs_Augsburg_2026-10-26', '2026-10-27', 'Sonnenhof Großaspach', 'Augsburg', 2, 4, 2, 5,
     'https://sport.sky.de/fussball/grossaspach-vs-augsburg/daten/578231'),
    ('corners_Rot-Weiss_Essen_vs_RB_Leipzig_2026-10-26', '2026-10-27', 'Rot-Weiss Essen', 'RB Leipzig', 1, 2, 5, 7,
     'https://videos.sport.sky.de/fussball/rw-essen-vs-rb-leipzig/daten/578229'),
]


def collect(tips, match_parts, row_date, same):
    """Require original ID, tip date and both ordered teams, including legacy aliases."""
    rows = []
    for tip in tips:
        tid = str(tip.get('tip_id') or '')
        for key, day, home, away, hs, aw, hc, ac, url in EVIDENCE:
            if tid != key or row_date(tip) != key[-10:]:
                continue
            th, ta, _ = match_parts(tip)
            if not (same(th, home) and same(ta, away)):
                continue
            rows.append(dict(source='reviewed_corner_evidence', _result_table='reviewed_corner_evidence',
                             match_date=day, home_team=home, away_team=away,
                             home_score=hs, away_score=aw,
                             raw=dict(home_corners=hc, away_corners=ac,
                                      corners_source=url, evidence_tip_id=key,
                                      evidence_checked_at='2026-11-01')))
    return deepcopy(rows)
