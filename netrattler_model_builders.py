"""Modell-Builder (ohne Buchmacherquote): Fouls-/Tackles-Legs aus der Spielerhistorie, Nate-Stil.
Die Quote ist die FAIRE Modellquote (1/p), keine Buchmacherquote -> klar gekennzeichnet, nie in der ROI-Zahl.
Gesetzt wird nur, wenn der Buchmacher mindestens die faire Quote bietet."""
import hashlib, html, json, os
import requests

MODEL_SOURCES = {"model_line_fouls"}
MAX_PER_RUN = int(os.getenv("NETRATTLER_MODEL_BUILDERS_MAX", "6"))
MAX_PER_MATCH = int(os.getenv("NETRATTLER_MODEL_BUILDERS_PER_MATCH", "1"))
MIN_JOINT = {2: 0.40, 3: 0.30}
CORR = 0.97  # kleiner Abschlag je zusaetzlichem Bein (Spielverlauf-Korrelation)


def joint_probability(legs):
    p = 1.0
    for leg in legs:
        p *= max(0.01, min(0.99, float(leg["probability"]) / 100.0))
    return p * (CORR ** (len(legs) - 1))


def _label(leg):
    return leg["market"]


def build(rows, match_date):
    pool = [r for r in rows if r.get("source") in MODEL_SOURCES and r.get("series")]
    by_match = {}
    for r in pool:
        by_match.setdefault(r["match"], []).append(r)
    picks = []
    for match, legs in by_match.items():
        legs = sorted(legs, key=lambda x: (-x["probability"], -x["line"]))
        used, made = set(), 0
        for size in (3, 2):
            chosen, players, cats = [], set(), {}
            for leg in legs:
                if leg["player"] in players or cats.get(leg["category"], 0) >= 2:
                    continue
                chosen.append(leg); players.add(leg["player"])
                cats[leg["category"]] = cats.get(leg["category"], 0) + 1
                if len(chosen) == size:
                    break
            if len(chosen) < size:
                continue
            key = tuple(sorted((x["player"], x["category"], x["line"]) for x in chosen))
            if key in used:
                continue
            jp = joint_probability(chosen)
            if jp < MIN_JOINT[size]:
                continue
            used.add(key)
            bid = "mb_" + hashlib.sha1((match_date + match + repr(key)).encode()).hexdigest()[:24]
            picks.append({"builder_id": bid, "match": match, "legs": chosen, "joint": jp, "fair": round(1 / jp, 2), "size": size})
            made += 1
            if made >= MAX_PER_MATCH:
                break
    picks.sort(key=lambda p: -p["joint"])
    return picks[:MAX_PER_RUN]


FOUL_CATS = {"fouls", "fouls_won"}


def build_fouls(rows, match_date):
    """Eigene Foul-Builder: 3 Foul-Spieler pro Spiel (beide Teams) + ein Cross-Match-Builder aus den besten Spielen."""
    pool = [r for r in rows if r.get("source") in MODEL_SOURCES and r.get("series") and r.get("category") in FOUL_CATS]
    by_match = {}
    for r in pool:
        by_match.setdefault(r["match"], []).append(r)
    picks = []
    for match, legs in by_match.items():
        legs = sorted(legs, key=lambda x: (-x["probability"], -x["line"]))
        chosen, players = [], set()
        for leg in legs:
            if leg["player"] in players:
                continue
            chosen.append(leg); players.add(leg["player"])
            if len(chosen) == 3:
                break
        if len(chosen) < 2:
            continue
        jp = joint_probability(chosen)
        if jp < MIN_JOINT[len(chosen)]:
            continue
        key = tuple(sorted((x["player"], x["category"], x["line"]) for x in chosen))
        picks.append({"builder_id": "mf_" + hashlib.sha1((match_date + match + repr(key)).encode()).hexdigest()[:24],
                      "match": match, "legs": chosen, "joint": jp, "fair": round(1 / jp, 2), "size": len(chosen),
                      "title": "FOUL BUILDER", "style": "MODEL FOULS BUILDER"})
    picks.sort(key=lambda p: -p["joint"])
    picks = picks[:MAX_PER_RUN]
    # Cross-Match: bestes Foul-Bein je Spiel, 4 Spiele
    best = []
    for match, legs in by_match.items():
        top = max(legs, key=lambda x: (x["probability"], x["line"]))
        best.append(top)
    best = sorted(best, key=lambda x: -x["probability"])[:4]
    if len(best) >= 3:
        jp = joint_probability(best)
        if jp >= 0.20:
            key = tuple(sorted((x["player"], x["category"], x["line"]) for x in best))
            picks.append({"builder_id": "mf_" + hashlib.sha1((match_date + "CROSS" + repr(key)).encode()).hexdigest()[:24],
                          "match": "Cross-Match", "legs": best, "joint": jp, "fair": round(1 / jp, 2), "size": len(best),
                          "title": "FOUL BUILDER · CROSS", "style": "MODEL FOULS BUILDER"})
    return picks


def message(pick, match_date):
    lines = [f"🧪 <b>{pick.get('title', 'MODELL-BUILDER')}</b> · <i>keine Buchmacherquote</i>",
             f"⚽ {html.escape(pick['match'])}", ""]
    multi = len({l['match'] for l in pick["legs"]}) > 1
    for leg in pick["legs"]:
        s = leg["series"]
        hits = sum(1 for v in s if v >= leg["line"])
        lines.append(f"• <b>{html.escape(leg['market'])}</b>" + (f" <i>({html.escape(leg['match'])})</i>" if multi else ""))
        lines.append(f"    📈 <i>L{len(s)}: {','.join(str(v) for v in s)} ({int(leg['line'])}+ in {hits}/{len(s)})</i>")
    lines += ["", f"📊 Modell-Wahrscheinlichkeit: {pick['joint'] * 100:.0f}% · faire Quote: {pick['fair']:.2f}",
              "💡 Nur setzen, wenn dein Buchmacher mindestens diese Quote bietet."]
    return "\n".join(lines)


def row_for_db(pick, match_date, message_text=None):
    return {
        "builder_id": pick["builder_id"], "tip_id": pick["builder_id"], "style": pick.get("style", "MODEL BUILDER"),
        "variant": f"{pick['size']} LEGS", "market_group": "builder", "match_date": match_date,
        "status": "pending", "stake": 0, "total_odds": None, "estimated_odds": True,
        "leg_count": pick["size"], "source": "MODEL_LINE",
        "joint_probability": round(pick["joint"], 4), "telegram_sent": False,
        "message_text": message_text,
        "legs": [{k: v for k, v in leg.items() if k != "series"} | {"series": leg["series"]} for leg in pick["legs"]],
    }


def run(rows, match_date, send, url, key, logger=print):
    """Reserve each deterministic builder before sending; record actual Telegram receipt.

    A failed/ambiguous DB insert must never send an untracked Telegram message.
    An inserted reservation is never resent automatically, even if delivery or
    receipt persistence fails (duplicate-send protection).
    """
    if os.getenv("NETRATTLER_MODEL_BUILDERS", "on").lower() == "off":
        return 0
    sent = 0
    for pick in build(rows, match_date) + build_fouls(rows, match_date):
        msg = message(pick, match_date)
        hdr = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json",
               "Prefer": "resolution=ignore-duplicates,return=representation"}
        try:
            r = requests.post(f"{url}/rest/v1/netrattler_builder_picks?on_conflict=builder_id", headers=hdr,
                              data=json.dumps(row_for_db(pick, match_date, msg)), timeout=20)
            if not r.ok:
                logger(f"Modell-Builder DB-Reservierung fehlgeschlagen: HTTP {r.status_code}; kein Telegram-Send")
                continue
            inserted = r.json()
            if not isinstance(inserted, list):
                logger("Modell-Builder DB-Antwort unklar; kein Telegram-Send")
                continue
            if not inserted:
                continue  # Bereits reserviert: niemals erneut senden.
        except Exception as exc:
            logger(f"Modell-Builder DB-Reservierung fehlgeschlagen: {type(exc).__name__}; kein Telegram-Send")
            continue

        try:
            receipt = send(msg)
        except Exception as exc:
            logger(f"Modell-Builder Telegram-Send fehlgeschlagen: {type(exc).__name__}")
            continue  # Reservierung bleibt bestehen, kein automatischer Zweitversuch.

        if isinstance(receipt, dict):
            msg_id = receipt.get("message_id")
            tg_chat = receipt.get("chat_id")
            actual_text = receipt.get("text") or msg
        else:
            msg_id = receipt
            # Identische Fallback-Reihenfolge wie TELEGRAM_GROUPS['builder'].
            tg_chat = (os.getenv("TELEGRAM_GROUP_BUILDER")
                       or os.getenv("TELEGRAM_GROUP_PLAYER_PROPS")
                       or os.getenv("TELEGRAM_GROUP_STATS")
                       or os.getenv("TELEGRAM_CHAT_ID"))
            actual_text = msg

        if isinstance(msg_id, bool) or not msg_id or not tg_chat:
            logger("Modell-Builder Telegram-Receipt unvollstaendig; reserviert, nicht erneut senden")
            continue

        patch = {"telegram_sent": True, "telegram_msg_id": str(msg_id),
                 "telegram_chat_id": str(tg_chat), "message_text": actual_text}
        try:
            confirm = requests.patch(
                f"{url}/rest/v1/netrattler_builder_picks",
                params={"builder_id": f"eq.{pick['builder_id']}"},
                headers={**hdr, "Prefer": "return=representation"},
                data=json.dumps(patch), timeout=20)
            if not confirm.ok or not isinstance(confirm.json(), list) or not confirm.json():
                logger("Modell-Builder Telegram gesendet, aber Receipt-DB-Update nicht bestaetigt")
                continue
        except Exception as exc:
            logger(f"Modell-Builder Telegram gesendet, Receipt-DB-Update fehlgeschlagen: {type(exc).__name__}")
            continue
        sent += 1
    logger(f"Modell-Builder: {sent} gesendet und mit Telegram-Receipt bestaetigt")
    return sent
