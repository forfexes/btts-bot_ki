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


def _rate(series, line):
    n = len(series)
    return (sum(1 for v in series if v >= line) + 1.0) / (n + 2.0)  # geglaettet


def _profiles_by_match(rows, *keys):
    by_match = {}
    for r in rows:
        if r.get("source") == "foul_profile" and all(k in r for k in keys):
            by_match.setdefault(r["match"], []).append(r)
    return by_match


def _leg_from(r, key, line, label, category):
    ser = r[key]
    return {"player": r["player"], "team": r["team"], "match": r["match"], "league": r["league"],
            "market": f"{r['player']} {line}+ {label}", "category": category, "line": float(line), "odds": 0.0,
            "probability": round(_rate(ser, line) * 100, 1), "series": ser, "source": "model_line_fouls",
            "kickoff": r.get("kickoff", ""), "games": len(ser),
            "hit_rate": round(100.0 * sum(1 for v in ser if v >= line) / len(ser), 1)}


def _tiers(spec, lines, floor=0.01):
    out = []
    for t in lines:
        p = 1.0
        for r, key, _label, _cat in spec:
            p *= _rate(r[key], t)
        p *= CORR ** (len(spec) - 1)
        if p >= floor:
            out.append((t, p))
    return out


def _ladder_pick(match, spec, lines, title, style, prefix, match_date, base_line, extra=None, min_base=0.20):
    tiers = _tiers(spec, lines)
    if not tiers or tiers[0][1] < min_base:
        return None
    legs = [_leg_from(r, key, base_line, label, cat) for r, key, label, cat in spec]
    keyset = tuple(sorted((l["player"], l["category"]) for l in legs))
    pick = {"builder_id": prefix + hashlib.sha1((match_date + match + repr(keyset)).encode()).hexdigest()[:24],
            "match": match, "legs": legs, "joint": tiers[0][1], "fair": round(1 / tiers[0][1], 2),
            "size": len(legs), "title": title, "style": style, "tiers": tiers}
    if extra:
        pick["extra_lines"] = extra
    return pick


def build_ladders(rows, match_date):
    """Foul-Leiter wie Bet Builder X (Nate): dieselben Spieler liefern BEIDE Staten.
    Basis: 2 Spieler x (Fouls + Fouls gezogen) = 4 Beine, alle auf derselben Linie, Leiter 2+/3+/4+ (je eigener Builder/Quote).
    XL: 3 Spieler x beide Staten + 1 weiterer Spieler Fouls = 7 Beine, Leiter 2+/3+."""
    base, xl = [], []
    for match, profs in _profiles_by_match(rows, "fouls", "fouls_won").items():
        if len(profs) < 2:
            continue
        ranked = sorted(profs, key=lambda r: -(_rate(r["fouls"], 2) * _rate(r["fouls_won"], 2)))
        p1, p2 = ranked[0], ranked[1]
        spec = [(p1, "fouls", "Fouls", "fouls"), (p2, "fouls", "Fouls", "fouls"),
                (p2, "fouls_won", "Fouls gezogen", "fouls_won"), (p1, "fouls_won", "Fouls gezogen", "fouls_won")]
        pk = _ladder_pick(match, spec, (2, 3, 4), "FOUL LEITER", "MODEL FOULS LADDER", "ml_", match_date, 2, min_base=0.15)
        if pk:
            base.append(pk)
        if len(ranked) >= 4:
            p3, p4 = ranked[2], ranked[3]
            spec7 = [(p, "fouls", "Fouls", "fouls") for p in (p1, p2, p3, p4)] + \
                    [(p, "fouls_won", "Fouls gezogen", "fouls_won") for p in (p1, p2, p3)]
            pk7 = _ladder_pick(match, spec7, (2, 3), "FOUL LEITER XL · 7 BEINE", "MODEL FOULS LADDER", "mx_", match_date, 2, min_base=0.03)
            if pk7:
                pk7["xl"] = True
                xl.append(pk7)
    base.sort(key=lambda p: -p["joint"])
    xl.sort(key=lambda p: -p["joint"])
    return base[:3] + xl[:2]


def _shift_tiers(spec, shifts=(0, 1, 2), floor=0.01):
    """spec: [(profil, key, label, cat, basislinie)] -> [(shift, p)]; jede Linie wird um 'shift' erhoeht."""
    out = []
    for sh in shifts:
        p = 1.0
        for r, key, _l, _c, ln in spec:
            p *= _rate(r[key], ln + sh)
        p *= CORR ** (len(spec) - 1)
        if p >= floor:
            out.append((sh, p))
    return out


def build_nate_mix(rows, match_date):
    """Nate-Mix: 4-5 Beine im selben Spiel aus Fouls, Fouls gezogen, Tackles und Schuessen, jedes Bein auf seiner eigenen
    stabilen Linie (2+ oder 3+). Leiter = alle Linien +1 / +2."""
    cats = (("fouls", "Fouls", "fouls"), ("fouls_won", "Fouls gezogen", "fouls_won"),
            ("tackles", "Tackles", "tackles"), ("shots", "Schüsse", "shots"))
    out = []
    for match, profs in _profiles_by_match(rows, "fouls").items():
        cands = []
        for r in profs:
            for key, label, cat in cats:
                if key not in r:
                    continue
                best = None
                for ln in (2, 3):
                    pr = _rate(r[key], ln)
                    if pr >= 0.62:
                        best = (pr, ln)
                if best:
                    cands.append((best[0], r, key, label, cat, best[1]))
        cands.sort(key=lambda c: -c[0])
        spec, per_player, per_key = [], {}, {}
        for pr, r, key, label, cat, ln in cands:
            if per_player.get(r["player"], 0) >= 2 or per_key.get(key, 0) >= (3 if key == "shots" else 2):
                continue
            spec.append((r, key, label, cat, ln))
            per_player[r["player"]] = per_player.get(r["player"], 0) + 1
            per_key[key] = per_key.get(key, 0) + 1
            if len(spec) == 5:
                break
        if len(spec) < 4 or len({k for _r, k, *_ in spec}) < 2:
            continue
        tiers = _shift_tiers(spec)
        if not tiers or tiers[0][1] < 0.12:
            continue
        legs = [_leg_from(r, key, ln, label, cat) for r, key, label, cat, ln in spec]
        keyset = tuple(sorted((l["player"], l["category"], l["line"]) for l in legs))
        out.append({"builder_id": "mn_" + hashlib.sha1((match_date + match + repr(keyset)).encode()).hexdigest()[:24],
                    "match": match, "legs": legs, "joint": tiers[0][1], "fair": round(1 / tiers[0][1], 2), "size": len(legs),
                    "title": "BET BUILDER · NATE MIX", "style": "MODEL NATE MIX", "tiers": tiers, "tier_shift": True, "xl": True})
    out.sort(key=lambda p: -p["joint"])
    return out[:3]


def build_shot_ladders(rows, match_date):
    """Schuss-Leiter: 2 Spieler im selben Spiel auf 2+/3+/4+ Schuesse; SOT-Leiter auf 1+/2+."""
    out = []
    for match, profs in _profiles_by_match(rows, "shots").items():
        if len(profs) < 2:
            continue
        ranked = sorted(profs, key=lambda r: -_rate(r["shots"], 2))
        pk = None
        if len(ranked) >= 3:
            pk = _ladder_pick(match, [(r, "shots", "Schüsse", "shots") for r in ranked[:3]], (2, 3, 4), "SCHUSS LEITER",
                              "MODEL SHOT LADDER", "ms_", match_date, 2, min_base=0.2)
        if pk is None:
            pk = _ladder_pick(match, [(r, "shots", "Schüsse", "shots") for r in ranked[:2]], (2, 3, 4), "SCHUSS LEITER",
                              "MODEL SHOT LADDER", "ms_", match_date, 2, min_base=0.25)
        if pk:
            out.append(pk)
    for match, profs in _profiles_by_match(rows, "sot").items():
        if len(profs) < 2:
            continue
        top = sorted(profs, key=lambda r: -_rate(r["sot"], 1))[:2]
        pk = _ladder_pick(match, [(r, "sot", "Schüsse aufs Tor", "sot") for r in top], (1, 2, 3), "SOT LEITER",
                          "MODEL SOT LADDER", "mo_", match_date, 1, min_base=0.25)
        if pk:
            out.append(pk)
    out.sort(key=lambda p: -p["joint"])
    return out[:4]


def build_cards(rows, match_date):
    """Karten: beste 'Player to be Booked'-Kandidaten (Gelbe in den letzten Spielen) als Doppel aus zwei Spielen."""
    cands = []
    for r in rows:
        if r.get("source") == "foul_profile" and "yellow" in r:
            rate = _rate(r["yellow"], 1)
            if rate >= 0.55:
                cands.append((rate, r))
    cands.sort(key=lambda x: -x[0])
    picks, used = [], set()
    seen_players = set()
    for rate, r in cands:
        if r["match"] in used or r["player"] in seen_players:
            continue
        used.add(r["match"])
        seen_players.add(r["player"])
        picks.append((rate, r))
        if len(picks) == 4:
            break
    if len(picks) < 2:
        return []
    legs = []
    for rate, r in picks[:2]:
        leg = _leg_from(r, "yellow", 1, "Karte", "yellow_cards")
        leg["market"] = f"{r['player']} Karte (booked)"
        legs.append(leg)
    jp = joint_probability(legs)
    extra = ["Weitere Kandidaten:"] + [f"    {r['player']} ({r['match']}): {sum(1 for v in r['yellow'] if v >= 1)}/{len(r['yellow'])} Spiele mit Karte" for _, r in picks[2:]]
    return [{"builder_id": "mk_" + hashlib.sha1((match_date + repr(sorted(l['player'] for l in legs))).encode()).hexdigest()[:24],
             "match": "Cross-Match", "legs": legs, "joint": jp, "fair": round(1 / jp, 2), "size": 2,
             "title": "KARTEN DOPPEL", "style": "MODEL CARDS", "extra_lines": extra if len(extra) > 1 else None}]


def message(pick, match_date):
    lines = [f"🧪 <b>{pick.get('title', 'MODELL-BUILDER')}</b> · <i>keine Buchmacherquote</i>",
             f"⚽ {html.escape(pick['match'])}"]
    if os.getenv("NETRATTLER_LINEUP_CONFIRMED") == "1":
        lines.append("✅ <b>Startelf bestätigt</b>")
    lines.append("")
    multi = len({l['match'] for l in pick["legs"]}) > 1
    for leg in pick["legs"]:
        s = leg["series"]
        hits = sum(1 for v in s if v >= leg["line"])
        lines.append(f"• <b>{html.escape(leg['market'])}</b>" + (f" <i>({html.escape(leg['match'])})</i>" if multi else ""))
        lines.append(f"    📈 <i>L{len(s)}: {','.join(str(v) for v in s)} ({int(leg['line'])}+ in {hits}/{len(s)})</i>")
    if pick.get("tiers"):
        lines += ["", "🪜 <b>Leiter</b> (jedes Bein eine Stufe höher):" if pick.get("tier_shift") else "🪜 <b>Leiter</b> (alle Beine auf derselben Linie):"]
        for t, jp in pick["tiers"]:
            lbl = ("Basis" if t == 0 else f"alle Linien +{t}") if pick.get("tier_shift") else f"{t}+ bei allen Beinen"
            lines.append(f"    {lbl} · {jp * 100:.1f}% · faire Quote {1 / jp:.1f}")
        if pick.get("extra_lines"):
            lines += [""] + pick["extra_lines"]
        lines += ["", "💡 Nur setzen, wenn dein Buchmacher mindestens die faire Quote der gewählten Stufe bietet."]
        return "\n".join(lines)
    if pick.get("extra_lines"):
        lines += [""] + pick["extra_lines"]
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


def dedupe_overlap(picks):
    """Reihenfolge = Prioritaet (Leiter > Foul-Builder > gemischt). Pro Spiel keine zwei Builder mit >=2 gleichen Spielern."""
    kept = []
    for p in picks:
        names = {l["player"] for l in p["legs"]}
        # XL-Leiter (7 Beine) darf neben der 4-Beine-Leiter desselben Spiels stehen; sonst keine Dubletten
        if p["match"] != "Cross-Match" and any(
                k["match"] == p["match"] and (not p.get("xl") or (k.get("xl") and k.get("style") == p.get("style")))
                and len(names & {l["player"] for l in k["legs"]}) >= 2 for k in kept):
            continue
        kept.append(p)
    return kept


def run(rows, match_date, send, url, key, logger=print):
    """Reserve each deterministic builder before sending; record actual Telegram receipt.

    A failed/ambiguous DB insert must never send an untracked Telegram message.
    An inserted reservation is never resent automatically, even if delivery or
    receipt persistence fails (duplicate-send protection).
    """
    if os.getenv("NETRATTLER_MODEL_BUILDERS", "on").lower() == "off":
        return 0
    sent = 0
    for pick in dedupe_overlap(build_ladders(rows, match_date) + build_nate_mix(rows, match_date) + build_shot_ladders(rows, match_date) + build_cards(rows, match_date) + build_fouls(rows, match_date) + build(rows, match_date)):
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
