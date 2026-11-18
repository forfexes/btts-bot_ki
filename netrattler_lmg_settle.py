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
    url,headers=common._db()
    resp=requests.get(url,headers=headers,params={
        "select":"alert_key,fixture_id,home,away,minute,score,status,telegram_message_id,sent_at,message_kind,next_goal_side",
        "status":"eq.sent","telegram_message_id":"not.is.null",
        "order":"sent_at.asc","limit":"80"},timeout=15)
    resp.raise_for_status()
    return resp.json()

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
    caption=(f"⚽ GOAL HUNTER · {home} – {away}\n"
             f"⏱ Tipp {row['minute']}' · {row['score']}\n"
             f"🏁 Endresultat {final_text} · {'✅ GEWONNEN' if won else '❌ VERLOREN'}\n"
             "@prophunter")
    if row.get("next_goal_side") in ("home","away"):
        predicted = home if row["next_goal_side"] == "home" else away
        grade = {"won":"✅ RICHTIG","lost":"❌ FALSCH",
                 "void":"KEIN WEITERES TOR","unverified":"NICHT VERIFIZIERT"}.get(
                     row.get("next_goal_result"),"OFFEN")
        caption = caption.replace("@prophunter",
                                  f"🎯 Nächstes Tor: {predicted} · {grade}\\n@prophunter")
    # Old messages are text. Only new photo cards support editing the image in place.
    # Photo cards can be identified via a versioned prefix in the alert row, if persisted.
    is_photo=row.get("message_kind")=="photo"
    if is_photo:
        from netrattler_lmg_card import make_card
        photo=make_card(fixture,final_score=final_text,won=won,
                        next_goal_side=row.get("next_goal_side"),
                        next_goal_result=row.get("next_goal_result"))
        media=json.dumps({"type":"photo","media":"attach://result_photo","caption":caption})
        resp=requests.post(f"https://api.telegram.org/bot{token}/editMessageMedia",
                           data={"chat_id":chat,"message_id":row["telegram_message_id"],
                                 "media":media},
                           files={"result_photo":("result.jpg",photo,"image/jpeg")},timeout=30)
    else:
        resp=requests.post(f"https://api.telegram.org/bot{token}/editMessageText",
                           json={"chat_id":chat,"message_id":row["telegram_message_id"],
                                 "text":caption},timeout=20)
    if resp.status_code==400 and "message is not modified" in resp.text.lower():
        return  # Previous identical edit succeeded; safe to persist settlement.
    resp.raise_for_status()
    if not resp.json().get("ok"):
        raise RuntimeError("Telegram edit not confirmed")

def mark_settled(row,score,won):
    url,headers=common._db()
    response=requests.patch(url,headers={**headers,"Prefer":"return=minimal"},
        params={"alert_key":"eq."+row["alert_key"],"status":"eq.sent"},
        json={"status":"won" if won else "lost",
              "final_score":f"{score[0]}:{score[1]}",
              "settled_at":dt.datetime.now(dt.timezone.utc).isoformat(),
              "next_goal_result":row.get("next_goal_result")},
        timeout=15)
    response.raise_for_status()

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
            for day in days:
                if day not in cache:
                    cache[day]=fotmob.fetch_fotmob(day)
                final=finished_match(cache[day],row["fixture_id"])
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
