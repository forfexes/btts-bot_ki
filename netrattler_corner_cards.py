"""NETRATTLER corner cards and explicit, timezone-aware kickoff presentation."""
from datetime import datetime
from zoneinfo import ZoneInfo
import re


def kickoff_label(tip, target_date):
    for key in ('_kickoff','kickoff','starts','commence_time','time_utc'):
        try:
            stamp=datetime.fromisoformat(str(tip.get(key) or '').replace('Z','+00:00'))
            if stamp.tzinfo is not None:
                local=stamp.astimezone(ZoneInfo('Europe/Zurich'))
                return local.strftime('%Y-%m-%d'),local.strftime('%H:%M')
        except (ValueError,TypeError):
            pass
    for key in ('time_local','time'):
        text=str(tip.get(key) or '').strip()
        if re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',text):
            return str(target_date)[:10],text
    return str(target_date)[:10],'Zeit nicht bestätigt'


def render_corner_card(tip, target_date, result=None):
    """The user's original Corner Sniper art with verified live NETRATTLER AI data."""
    from netrattler_corner_template import render_corner_template
    return render_corner_template(tip, target_date, result)


def send_corner_card(token,chat,tip,target_date,log=print):
    import os
    import netrattler_stats_match_cards as cards
    if os.getenv("NETRATTLER_ORIGINAL_ONLY", "0") == "1":
        from netrattler_candidate_dispatch import send_single
        return send_single(cards,token,chat,"corner",tip,target_date,log)
    if not token or not chat or not cards._valid(tip):return None
    try:
        cards._crest_cache_load()
        cards.attach_h2h_api({'corners':[tip]},log=log)
        from netrattler_corner_template import validate_corner, review_corner_png
        reasons=validate_corner(tip,target_date,cards)
        if reasons:
            log('Corner-Sniper Qualitätsstopp: '+','.join(reasons))
            return None
        payload=render_corner_card(tip,target_date)
        issues=review_corner_png(payload)
        if issues:
            log('Corner-Sniper Pixelcheck fehlgeschlagen: '+','.join(issues))
            return None
        mid=cards._send_photo(token,chat,'',payload,log)
        if isinstance(mid,int) and not isinstance(mid,bool) and mid>0:
            cards.save_card(chat,mid,[('corners',tip)],target_date,log)
            return mid
    except Exception as exc:
        log('Corner-Card nicht verfügbar: '+type(exc).__name__)
    return None
