#!/usr/bin/env python3
"""Trace where full-time BTTS quotes come from (no Telegram, read-only). Writes probe 'btts_trace'."""
import os, json, requests
import netrattler_runtime_patch as patch
patch.install_pre_guard()
import btts_bot as bot
patch.install_bot(bot)
import netrattler_odds_cache_guard as cache_guard
cache_guard.install(bot)
import netrattler_builder_guard as guard
guard._install_pinnacle_guard(bot)

_DEFAULT = "Brighton|Crystal Palace,Udinese|Lecce,PEC Zwolle|Go Ahead Eagles,Fiorentina|Como,Angers|Marseille"
TARGETS = [t.split("|") for t in (os.environ.get("TRACE_MATCHES") or _DEFAULT).split(",") if "|" in t]
out = {"probe": "btts_trace", "matches": []}
try:
    mus = bot.fetch_pinnacle_matchups() or []
    out["pinnacle_matchups"] = len(mus)
except Exception as e:
    mus = []; out["pinnacle_err"] = str(e)[:120]
for home, away in TARGETS:
    rec = {"match": f"{home} vs {away}"}
    try:
        ro = bot.get_pinnacle_match_odds(home, away) or {}
        rec["btts_yes"] = ro.get("btts_yes")
        rec["over_25"] = ro.get("over_25")
        rec["field_sources"] = ro.get("_ntr_field_sources")
        rec["keys"] = sorted(k for k in ro if not k.startswith("_"))[:40]
        rec["meta"] = {k: str(v)[:60] for k, v in ro.items() if k.startswith("_") and k != "_ntr_field_sources"}
    except Exception as e:
        rec["err"] = f"{type(e).__name__}: {str(e)[:160]}"
    # raw pinnacle related list for this match
    try:
        hn, an = bot._normalize_name(home), bot._normalize_name(away)
        for m in mus:
            if hn.split()[0] in bot._normalize_name(m["home"]) and an.split()[0] in bot._normalize_name(m["away"]):
                rid = m["match_id"]; rec["pin_id"] = rid
                r2 = bot.requests.get(f"{bot.PINNACLE_BASE}/matchups/{rid}/related", headers=bot.PINNACLE_HEADERS, timeout=15)
                rec["related_status"] = r2.status_code
                subs = []
                for sub in (r2.json() if r2.ok else [])[:60]:
                    desc = str((sub.get("special") or {}).get("description") or sub.get("description") or "")
                    if "score" in desc.lower() or "btts" in desc.lower():
                        sid = sub.get("id")
                        rs = bot.requests.get(f"{bot.PINNACLE_BASE}/matchups/{sid}/markets/straight", headers=bot.PINNACLE_HEADERS, timeout=15)
                        prices = []
                        for mk in (rs.json() if rs.ok else []):
                            for p in mk.get("prices") or []:
                                prices.append([mk.get("period"), p.get("designation"), p.get("participantId"), p.get("price")])
                        parts = [[x.get("id"), x.get("name")] for x in (sub.get("participants") or [])]
                        subs.append({"desc": desc[:80], "kind": guard._pin_btts_kind(desc), "prices": prices[:8], "parts": parts[:4]})
                rec["pin_btts_subs"] = subs[:10]
                break
    except Exception as e:
        rec["pin_err"] = str(e)[:160]
    out["matches"].append(rec)
url = os.environ["SUPABASE_URL"].rstrip("/"); key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_KEY"]
requests.post(f"{url}/rest/v1/netrattler_card_diag", headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Prefer": "return=minimal"},
              data=json.dumps({"info": out}, default=str), timeout=30)
print(json.dumps(out, default=str)[:3000])
