"""Strict adapter from live NETRATTLER Goal Hunter data to owner-original image.

Offline by default. It does not query a feed, publish Telegram or connect to
Supabase. Callers must pass verified fixture identities, authentic crests and
observed metrics. No guessed win rate/probability can be introduced here.
"""
from __future__ import annotations
from .last_minute_dynamic_card import render_card


def _side(teamstats,side,key):
    raw=(teamstats.get(side) or {})
    if not isinstance(raw,dict):raise ValueError('Invalid verified side statistics')
    return raw.get(key)


def _pair(teamstats,key):
    home=_side(teamstats,'home',key)
    away=_side(teamstats,'away',key)
    if home is None or away is None:return None
    return (home,away)


def _fixture(fixture):
    if not isinstance(fixture,dict):raise ValueError('Verified fixture required')
    for key in ('home','away','minute','hg','ag','league'):
        if fixture.get(key) is None:raise ValueError('Missing verified fixture '+key)
    return {key:fixture[key] for key in ('home','away','minute','hg','ag','league')}


def _logos(fixture,provider):
    if not callable(provider):raise ValueError('Authentic crest provider required')
    # Exact upstream FotMob/ESPN team identifiers; never search by fuzzy name.
    ids=(fixture.get('home_logo_url') or fixture.get('home_logo_id'),
         fixture.get('away_logo_url') or fixture.get('away_logo_id'))
    if not all(ids):raise ValueError('Both verified crest IDs required')
    # An accidental duplicated provider ID displays the SAME badge for both
    # competing clubs. This is a hard identity error, not a layout issue.
    # Do not substitute an arbitrary team graphic or quietly publish it.
    if str(ids[0]).strip().casefold()==str(ids[1]).strip().casefold():
        raise ValueError('Home and away cannot share a verified crest identifier')
    home,away=provider(ids[0]),provider(ids[1])
    # Distinct IDs can still be mapped to the SAME badge by a broken CDN or
    # source alias. Compare visible pixels, not just URL or encoded metadata.
    from io import BytesIO
    from PIL import Image
    def visible_crest(raw):
        if not isinstance(raw,(bytes,bytearray)):
            return None
        try:
            with Image.open(BytesIO(raw)) as src:
                icon=src.convert('RGBA')
        except (OSError,ValueError):
            return None  # The owner renderer rejects corrupt artwork itself.
        bbox=icon.getchannel('A').point(
            lambda alpha: 255 if alpha>=24 else 0).getbbox()
        if bbox is None:
            return None
        icon=icon.crop(bbox)
        icon.thumbnail((96,96),Image.Resampling.LANCZOS)
        return icon.size,icon.tobytes()
    first,second=visible_crest(home),visible_crest(away)
    if first is not None and first == second:
        raise ValueError('Home and away resolved to identical team crest artwork')
    return home,away


def make_live(fixture, metrics, *, crest_provider, preview_only=False):
    fields=_fixture(fixture)
    if not isinstance(metrics,dict):raise ValueError('Observed metrics required')
    teamstats=metrics.get('teams') or {}
    if not isinstance(teamstats,dict):raise ValueError('Invalid teams metrics')
    for output,source in (('shots','shots'),('sot','sot'),('corners','corners'),
                          ('possession','possession'),('attacks','attacks')):
        pair=_pair(teamstats,source)
        if pair is not None:fields.setdefault('stats',{})[output]=pair
    fields['xg_home']=_side(teamstats,'home','xg')
    fields['xg_away']=_side(teamstats,'away','xg')
    # Only time-series measurements with genuine timestamps are admissible.
    history=metrics.get('xg_previous_verified')
    if isinstance(history,dict):
        fields['xg_prev_home']=history.get('home')
        fields['xg_prev_away']=history.get('away')
    # Proprietary model probabilities require explicit provenance flags.
    if metrics.get('over_probability_verified') is True:
        fields['over_probability']=metrics.get('over_probability')
    side=metrics.get('next_goal_side')
    if side not in (None,'home','away'):
        raise ValueError('Invalid predicted next goal team')
    if side and metrics.get('next_goal_verified') is True:
        fields['next_goal_team']=fixture[side]
        if metrics.get('next_probability_verified') is True:
            fields['next_probability']=metrics.get('next_probability')
    home_logo,away_logo=_logos(fixture,crest_provider)
    return render_card(fields,home_crest=home_logo,away_crest=away_logo,
                       preview_only=preview_only)


def make_settled(fixture, *, final_score, won, crest_provider,
                 next_goal_side=None, next_goal_result=None,
                 preview_only=False):
    fields=_fixture(fixture)
    if type(won) is not bool:raise ValueError('Confirmed win/loss required')
    if next_goal_side not in (None,'home','away'):
        raise ValueError('Unknown next-goal side')
    # A settlement decision must agree with the independently verified final
    # match score. No manually supplied win/loss may override real goal growth.
    if isinstance(final_score, str):
        parts = final_score.replace(' ', '').split(':')
    elif isinstance(final_score, (tuple, list)):
        parts = list(final_score)
    else:
        raise ValueError('Invalid final score')
    if len(parts) != 2:
        raise ValueError('Invalid final score')
    def _goal(value):
        if isinstance(value, bool):
            raise ValueError('Invalid final goals')
        try:
            number = int(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError('Invalid final goals') from exc
        if str(value).strip() != str(number) or number < 0 or number > 30:
            raise ValueError('Invalid final goals')
        return number
    final_home, final_away = (_goal(parts[0]), _goal(parts[1]))
    initial_home, initial_away = (_goal(fields['hg']), _goal(fields['ag']))
    if final_home < initial_home or final_away < initial_away:
        raise ValueError('Final score below tip snapshot')
    verified_won = (final_home + final_away) > (initial_home + initial_away)
    if won != verified_won:
        raise ValueError('Settlement verdict contradicts observed final score')
    fields['status']='gewonnen' if won else 'verloren'
    fields['final_score']=final_score
    if next_goal_side:
        if next_goal_result not in ('won','lost','unverified'):
            # No automatic void: the actual bookmaker must confirm how
            # an unanswered next-goal market settles before any VOID.
            raise ValueError('Verified next-goal grade required; no blanket void')
        from netrattler_lmg_next_goal import evaluate_next_goal
        provable=evaluate_next_goal(next_goal_side,
                                   (initial_home,initial_away),
                                   (final_home,final_away))
        if provable == 'unverified':
            if next_goal_result != 'unverified':
                # Both sides scored? Chronological first-scorer events are
                # needed. No further goal? Provider-specific terms are needed.
                raise ValueError('Next-goal settlement requires evidence not final score alone')
        elif next_goal_result not in ('unverified',provable):
            raise ValueError('Next-goal grade contradicts confirmed goal growth')
        fields['next_goal_team']=fixture[next_goal_side]
        fields['next_goal_result']=next_goal_result
    elif next_goal_result is not None:
        raise ValueError('Next-goal result without an original pick')
    home_logo,away_logo=_logos(fixture,crest_provider)
    return render_card(fields,home_crest=home_logo,away_crest=away_logo,
                       preview_only=preview_only)