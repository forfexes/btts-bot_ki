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
            chosen, players = [], set()
            for leg in legs:
                if leg["player"] in players:
                    continue
                chosen.append(leg); players.add(leg["player"])
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


def message(pick, match_date):
    lines = ["🧪 <b>MODELL-BUILDER</b> · <i>keine Buchmacherquote</i>",
             f"⚽ {html.escape(pick['match'])}", ""]
    for leg in pick["legs"]:
        s = leg["series"]
        hits = sum(1 for v in s if v >= leg["line"])
        lines.append(f"• <b>{html.escape(leg['market'])}</b>")
        lines.append(f"    📈 <i>L{len(s)}: {','.join(str(v) for v in s)} ({int(leg['line'])}+ in {hits}/{len(s)})</i>")
    lines += ["", f"📊 Modell-Wahrscheinlichkeit: {pick['joint'] * 100:.0f}% · faire Quote: {pick['fair']:.2f}",
              "💡 Nur setzen, wenn dein Buchmacher mindestens diese Quote bietet."]
    return "\n".join(lines)


def row_for_db(pick, match_date):
    return {
        "builder_id": pick["builder_id"], "tip_id": pick["builder_id"], "style": "MODEL BUILDER",
        "variant": f"{pick['size']} LEGS", "market_group": "builder", "match_date": match_date,
        "status": "pending", "stake": 0, "total_odds": None, "estimated_odds": True,
        "leg_count": pick["size"], "source": "MODEL_LINE",
        "joint_probability": round(pick["joint"], 4), "telegram_sent": True,
        "legs": [{k: v for k, v in leg.items() if k != "series"} | {"series": leg["series"]} for leg in pick["legs"]],
    }


def run(rows, match_date, send, url, key, logger=print):
    if os.getenv("NETRATTLER_MODEL_BUILDERS", "on").lower() == "off":
        return 0
    sent = 0
    for pick in build(rows, match_date):
        hdr = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json",
               "Prefer": "resolution=ignore-duplicates,return=representation"}
        try:
            r = requests.post(f"{url}/rest/v1/netrattler_builder_picks?on_conflict=builder_id", headers=hdr,
                              data=json.dumps(row_for_db(pick, match_date)), timeout=20)
            if r.ok and r.json() == []:
                continue  # schon gesendet
        except Exception as exc:
            logger(f"Modell-Builder speichern fehlgeschlagen: {type(exc).__name__}")
        send(message(pick, match_date))
        sent += 1
    logger(f"Modell-Builder: {sent} gesendet")
    return sent
