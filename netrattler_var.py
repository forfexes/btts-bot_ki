"""Verified operator VAR markets. Observation only until rule-compatible coverage.

Dictionary: https://v2l.traincdn.com/genfiles/cms/betstemplates/betsNames_full_en.js
No absence of a VAR event is ever interpreted as a losing Yes / winning No.
"""
import math

# Group, Yes types, No types; no fuzzy market matching.
VAR_MARKETS = {
    8203: ('var_used', (7416,10043), (7417,10044)),
    8205: ('var_awarded_goal_disallowed', (7418,10045), (7419,10046)),
    8207: ('var_disallowed_goal_awarded', (7420,10049), (7421,10050)),
    8229: ('var_goal_awarded_confirmed', (7448,10051), (7449,10052)),
    8231: ('var_goal_disallowed_unconfirmed', (7450,), (7451,)),
    9365: ('var_goal_disallowed_unconfirmed', (10066,), (10067,)),
    9366: ('var_penalty_awarded_confirmed', (10068,), (10069,)),
    9367: ('var_penalty_not_awarded_unconfirmed', (10070,), (10071,)),
}


def decode_var_prices(game):
    """Main match only; require a complete Yes/No market and finite real prices."""
    if game.get('TG') or game.get('PN'):
        return []
    found = {}
    groups = [(g.get('G'), g.get('E') or []) for g in game.get('GE') or []]
    groups += [(None, game.get('E') or [])]
    for outer_group, events in groups:
        for row in events:
            for event in row if isinstance(row,list) else [row]:
                if not isinstance(event,dict):
                    continue
                try:
                    gid=int(event.get('G',outer_group)); typ=int(event.get('T'))
                    if outer_group is not None and int(outer_group)!=gid:
                        continue
                    spec=VAR_MARKETS.get(gid)
                    if not spec or event.get('P') is not None:
                        continue
                    market,yes,no=spec
                    selection='yes' if typ in yes else 'no' if typ in no else None
                    odds=float(event.get('C',0))
                    if not selection or not math.isfinite(odds) or odds<=1:
                        continue
                    found.setdefault((gid,market),{})[selection]=dict(market=market,selection=selection,
                        odds=odds,group=gid,type=typ,tip_eligible=False,
                        settlement_status='pending',reason='VAR rule-compatible result coverage unverified')
                except (TypeError,ValueError,OverflowError):
                    continue
    return [r for sides in found.values() if set(sides)=={'yes','no'} for r in sides.values()]


def normalize_var_events(events):
    """Preserve explicit provider evidence, without inferring market settlement."""
    return [dict(type='Var',detail=e.get('detail'),time=e.get('time'),team=e.get('team'))
            for e in events or [] if isinstance(e,dict) and str(e.get('type','')).lower()=='var']
