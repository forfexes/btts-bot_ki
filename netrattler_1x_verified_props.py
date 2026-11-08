"""Strict player-market decoder; operator dictionary verified 2026-11-04.

Reference: https://v2l.traincdn.com/genfiles/cms/betstemplates/betsNames_full_en.js
Both group and outcome type are required. Unknown markets are never guessed.
"""
import math

# (group, outcome): (category, exact operator template, binary yes)
MARKETS = {
    (775, 1515): ('yellow_cards', '[] Will Get Yellow Card - Yes', True),
    (3201, 4365): ('yellow_cards', '[] Total Yellow Cards Over ()', False),
    (2651, 3174): ('shots', '[] Total Shots Over ()', False),
    (3539, 4937): ('shots', '[] - Total Shots Over ()', False),
    (3217, 4416): ('sot', '[] Total Shots On Target Over ()', False),
    (3085, 4197): ('fouls_won', 'Total Fouls Committed On [] Over ()', False),
    (3305, 4544): ('fouls', 'Total Fouls Committed By [] Over ()', False),
    # Added 2026-11-08 from operator dictionary names resolved via observed (G,T) pairs.
    (4734, 14733): ('saves', '[] Total Saves Over ()', False),
    (2907, 9290): ('tackles_committed', '[], Tackles Over ()', False),
    (5564, 16699): ('tackles_committed', '[] Total Tackles Including Substitutions Over ()', False),
    (5562, 16695): ('fouls_won', 'Total Fouls Committed On [] Including Substitutions Over ()', False),
    (5563, 16697): ('fouls', '[] Total Fouls Committed Including Substitutions Over ()', False),
    (5267, 15988): ('sot', '[] Total Shots On Target Including Substitutions Over ()', False),
    (1368, 4720): ('offsides', '[] Total Offsides Over ()', False),
}

# Observed 22bet GetGameZip group IDs (2026-11-05), paired with the exact
# dictionary outcome types above. IdG in the dictionary is a presentation group,
# not always the LineFeed G. Do not generalize unobserved group/type pairs.
for observed, canonical in {
    (1175, 4197): (3085, 4197),
    (1236, 4365): (3201, 4365),
    (1250, 4416): (3217, 4416),
}.items():
    MARKETS[observed] = MARKETS[canonical]


def decode_player_props(parent, sub, source='1xbet'):
    """Decode full-match, single-player, explicitly verified Over/Yes offers."""
    if sub.get('TG') != "Players' stats" or str(sub.get('PN') or '').strip():
        return []
    teams = (parent.get('O1'), parent.get('O2'))
    if not all(teams) or (sub.get('O1'), sub.get('O2')) != teams:
        return []
    result, seen = [], set()
    for group in sub.get('GE') or []:
        for row in group.get('E') or []:
            for event in row if isinstance(row, list) else [row]:
                if not isinstance(event, dict):
                    continue
                try:
                    key = (int(group.get('G')), int(event.get('T')))
                    spec = MARKETS.get(key)
                    if not spec or (event.get('G') is not None and int(event['G']) != key[0]):
                        continue
                    category, label, binary = spec
                    pl = event.get('PL') or {}
                    player, side = str(pl.get('N') or '').strip(), int(pl.get('T', 0))
                    odds = float(event.get('C', 0))
                    raw_line = event.get('P')
                    if isinstance(raw_line, bool) or (raw_line is None and not binary):
                        continue
                    line = .5 if binary else float(raw_line)
                    if not player or side not in (1, 2) or '/' in player or ' & ' in player:
                        continue
                    if not math.isfinite(odds) or odds <= 1.20 or not math.isfinite(line) or line < .5:
                        continue
                    if line % 1 != .5:
                        continue
                except (TypeError, ValueError, OverflowError):
                    continue
                identity = (player, side, category, line)
                if identity in seen:
                    continue
                seen.add(identity)
                result.append(dict(player=player, team=teams[side-1],
                    match=f'{teams[0]} vs {teams[1]}', league=parent.get('L', ''),
                    category=category, market=label.replace('[]', player).replace('()', str(line)),
                    line=line, odds=odds, source=source,
                    provider_player_id=pl.get('I'), provider_group=key[0], provider_type=key[1]))
    return result
