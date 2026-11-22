"""Settle original Goal Hunter Telegram tips only on verified finished FotMob scores.

Text legacy messages use editMessageText; new photo cards use editMessageMedia.
No additional Telegram messages, no inferred scores, and no repeated settlement.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import requests

import netrattler_lmg_free as common
import netrattler_lmg_fotmob as fotmob
from netrattler_lmg_next_goal import evaluate_next_goal

def pending():
    from netrattler_lmg_store import pending as sqlite_pending
    return sqlite_pending()


def finished_match(feed,fixture_id):
    for league in (feed or {}).get("leagues") or []:
        for m in league.get("matches") or []:
            if common._int(m.get("id"))!=common._int(fixture_id):
                continue
            status=m.get("status") or {}
            if status.get("finished") is not True or status.get("cancelled") is True:
                return None
            score=fotmob._score(m)
            if score is None:
                return None
            home,away=m.get("home") or {},m.get("away") or {}
            if not home.get("name") or not away.get("name"):
                return None
            return {"score":score,"home":home,"away":away,
                    "league":league.get("name") or ""}
    return None

def finished_espn_match(feed,fixture_id):
    """Only clear 90-minute final score of an exact ESPN fixture may settle."""
    for event in (feed or {}).get("events") or []:
        if common._int(event.get("id"))!=common._int(fixture_id):
            continue
        status=(event.get("status") or {}).get("type") or {}
        status_name=str(status.get("name") or "").upper()
        status_description=str(status.get("description") or "").casefold()
        # AET and penalties must not settle a regulation-time goal line.
        if (status.get("state")!="post" or status.get("completed") is not True
                or not (status_name in ("STATUS_FINAL","STATUS_FULL_TIME")
                        or (not status_name and status_description in ("final","full time")))):
            return None
        try:
            competition=(event.get("competitions") or [])[0]
            sides={x.get("homeAway"):x for x in (competition.get("competitors") or [])}
            home,away=sides["home"],sides["away"]
            score=(common._int(home.get("score")),common._int(away.get("score")))
            if any(x is None for x in score):
                return None
            hteam=home.get("team") or {}
            ateam=away.get("team") or {}
            if not hteam.get("displayName") or not ateam.get("displayName"):
                return None
            league=event.get("league") or competition.get("league") or {}
            leagues=(feed or {}).get("leagues") or []
            league_name=league.get("name") or (leagues[0].get("name") if len(leagues)==1 else "")
            return {"score":score,
                    "home":{"name":str(hteam["displayName"]),"id":None},
                    "away":{"name":str(ateam["displayName"]),"id":None},
                    "league":str(league_name)}
        except (KeyError,IndexError,TypeError,AttributeError):
            return None
    return None


def edit_original(row,final,won):
    token=os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    chat=os.getenv("TELEGRAM_GROUP_LATE_GOALS")
    if not token or not chat:
        raise RuntimeError("Telegram secrets missing")
    home,away=row["home"],row["away"]
    fixture={"home":home,"away":away,"minute":row["minute"],
             "hg":int(row["score"].split(":")[0]),
             "ag":int(row["score"].split(":")[1]),
             "league":final["league"],
             "home_logo_id":common._int(final["home"].get("id")),
             "away_logo_id":common._int(final["away"].get("id"))}
    final_text=f"{final['score'][0]}:{final['score'][1]}"
    signal_tier=row.get("signal_tier")
    if signal_tier not in (None,"STANDARD","PREMIUM"):
        raise ValueError("Invalid stored Goal Hunter tier")
    caption=(f"⚽ GOAL HUNTER · {home} – {away}\n"
             f"⏱ Tipp {row['minute']}' · {row['score']}\n"
             f"🏁 Endresultat {final_text} · {'✅ GEWONNEN' if won else '❌ VERLOREN'}\n"
             "@prophunter")
    if signal_tier:
        caption = caption.replace("🏁 Endresultat",
                                  f"🎯 Over 0.5 Restspielzeit · {signal_tier}\n🏁 Endresultat")
    if row.get("next_goal_side") in ("home","away"):
        predicted = home if row["next_goal_side"] == "home" else away
        grade = {"won":"✅ RICHTIG","lost":"❌ FALSCH",
                 "void":"KEIN WEITERES TOR","unverified":"NICHT VERIFIZIERT"}.get(
                     row.get("next_goal_result"),"OFFEN")
        caption = caption.replace("@prophunter",
                                  f"🎯 Nächstes Tor: {predicted} · {grade}\n@prophunter")
    # Old messages are text. Only new photo cards support editing the image in place.
    # Photo cards can be identified via a versioned prefix in the alert row, if persisted.
    version=row.get("message_kind")
    is_photo=version=="photo"
    is_clean_owner=version=="owner_clean_png"
    if is_clean_owner:
        from io import BytesIO
        from netrattler_lmg_card import crest
        from last_minute_owner_20261122.live_data_bridge import make_settled

        def verified_crest_png(source):
            badge=crest(source)
            if badge is None:
                raise ValueError("Verified settled Goal Hunter crest unavailable")
            with BytesIO() as buff:
                badge.save(buff,format="PNG")
                return buff.getvalue()

        # Even when a release flag changes after publication, the stored
        # per-message version guarantees the EXACT owner family is re-rendered.
        photo=make_settled(fixture,final_score=final_text,won=won,
                           next_goal_side=row.get("next_goal_side"),
                           next_goal_result=row.get("next_goal_result"),
                           crest_provider=verified_crest_png)
        media=json.dumps({"type":"photo","media":"attach://result_photo"})
        resp=requests.post(
            f"https://api.telegram.org/bot{token}/editMessageMedia",
            data={"chat_id":chat,"message_id":row["telegram_message_id"],
                  "media":media},
            files={"result_photo":("last_minute_settled.png",photo,"image/png")},
            timeout=30)
    elif is_photo:
        from netrattler_lmg_card import make_card
        photo=make_card(fixture,metrics={"tier":signal_tier or "STANDARD"},
                        final_score=final_text,won=won,
                        next_goal_side=row.get("next_goal_side"),
                        next_goal_result=row.get("next_goal_result"))
        # The original and settled photo must have NO Telegram caption.
        # Scoring details are rendered directly onto the image.
        media=json.dumps({"type":"photo","media":"attach://result_photo"})
        resp=requests.post(f"https://api.telegram.org/bot{token}/editMessageMedia",
                           data={"chat_id":chat,"message_id":row["telegram_message_id"],
                                 "media":media},
                           files={"result_photo":("result.jpg",photo,"image/jpeg")},timeout=30)
    elif version in (None,"text"):
        # Historical legacy text rows predate the SQLite message_kind field.
        # Edit in place; NEVER post an additional settlement message.
        resp=requests.post(f"https://api.telegram.org/bot{token}/editMessageText",
                           json={"chat_id":chat,"message_id":row["telegram_message_id"],
                                 "text":caption},timeout=20)
    else:
        raise ValueError("Unknown Telegram image template version; settlement deferred")
    if resp.status_code==400 and "message is not modified" in resp.text.lower():
        return  # Previous identical edit succeeded; safe to persist settlement.
    resp.raise_for_status()
    if not resp.json().get("ok"):
        raise RuntimeError("Telegram edit not confirmed")

def mark_settled(row,score,won):
    from netrattler_lmg_store import mark_settled as sqlite_mark_settled
    return sqlite_mark_settled(row,score,won)


def main():
    rows=pending()
    cache={}
    report={"pending":len(rows),"finished":0,"settled":0,"unknown":0}
    for row in rows:
        try:
            sent=common._date(row.get("sent_at"))
            if not sent:
                report["unknown"]+=1
                continue
            # Check both calendar days for matches crossing UTC midnight.
            days=[sent.strftime("%Y%m%d"),
                  (sent-dt.timedelta(days=1)).strftime("%Y%m%d"),
                  (sent+dt.timedelta(days=1)).strftime("%Y%m%d")]
            final=None
            source=row.get("source") or "fotmob"
            if source not in ("espn","fotmob"):
                report["unknown"]+=1
                continue
            for day in days:
                lookup_key=(source,day)
                if lookup_key not in cache:
                    if source=="fotmob":
                        cache[lookup_key]=fotmob.fetch_fotmob(day)
                    else:
                        cache[lookup_key]=common._get(
                            f"{common.ESPN}/all/scoreboard",
                            params={"dates":day,"limit":"1000"})
                final=(finished_match(cache[lookup_key],row["fixture_id"])
                       if source=="fotmob" else
                       finished_espn_match(cache[lookup_key],row["fixture_id"]))
                if final:break
            if final is None:
                report["unknown"]+=1
                continue
            # Prevent mistaken fixture joins even if IDs collide between providers.
            if final["home"]["name"]!=row["home"] or final["away"]["name"]!=row["away"]:
                report["unknown"]+=1
                continue
            initial=[int(v) for v in row["score"].split(":")]
            if any(a<b for a,b in zip(final["score"],initial)):
                report["unknown"]+=1
                continue
            report["finished"]+=1
            print("LMG_VERIFIED_FINAL",row["alert_key"],final["score"],flush=True)
            won=sum(final["score"])>sum(initial)
            row["next_goal_result"]=evaluate_next_goal(
                row.get("next_goal_side"),tuple(initial),final["score"])
            edit_original(row,final,won)
            mark_settled(row,final["score"],won)
            report["settled"]+=1
        except (requests.RequestException,RuntimeError,KeyError,ValueError,TypeError) as exc:
            report["unknown"]+=1
            print("LMG_SETTLE_RETRY",row.get("alert_key"),str(exc)[:120],flush=True)
    print("LMG_SETTLE_SUMMARY",json.dumps(report),flush=True)
    return report

if __name__=="__main__":
    main()
