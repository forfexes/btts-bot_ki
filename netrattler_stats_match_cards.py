"""Optional NETRATTLER match preview images for the explicit Stats Telegram group.

Display-only: consumes final guarded tips; never creates prices, tips or bets.
"""
import io
import os
from collections import defaultdict

import requests


def _number(value):
    try:
        n = float(value)
        return n if n == n and n not in (float("inf"), float("-inf")) else None
    except (TypeError, ValueError):
        return None


def _price(tip):
    for key in ("oddsYes", "odds", "odd", "price"):
        value = _number(tip.get(key))
        if value is not None and 1.01 <= value <= 100:
            return value
    return None


def _valid(tip):
    if not isinstance(tip, dict) or tip.get("_no_real_odds"):
        return False
    if tip.get("_synthetic") or tip.get("synthetic") or tip.get("estimated_odds"):
        return False
    if not (tip.get("_source") or tip.get("source") or tip.get("bookmaker") or tip.get("odds_source")):
        return False
    if not str(tip.get("match", "")).strip():
        return False
    return _price(tip) is not None


def _label(market, tip):
    labels = {
        "btts": "BEIDE TREFFEN", "over25": "OVER 2.5 TORE",
        "combo": "BTTS + OVER 2.5", "btts_ht": "BTTS HALBZEIT",
        "over15_ht": "OVER 1.5 HZ", "1x2": "1X2 / GOAL HUNTER",
        "corners": "CORNERS", "cards": "KARTEN",
        "props": "PLAYER PROPS", "builder": "BUILDER",
    }
    value = str(tip.get("tip") or "").strip()
    return labels.get(market, market.upper()) + (("  ·  " + value[:28]) if value and value.upper() not in ("YES", "JA") else "")


def select_cards(tips_by_market, max_cards=0):
    matches = defaultdict(list)
    for market, tips in (tips_by_market or {}).items():
        for tip in tips or []:
            if not _valid(tip):
                continue
            match = str(tip["match"]).strip()
            matches[match.casefold()].append((market, tip))
    ranked = []
    for key, entries in matches.items():
        # At least two independently priced markets for a meaningful match card.
        unique = {}
        for market, tip in entries:
            if market not in unique:
                unique[market] = tip
        if len(unique) < 2:
            continue
        entries = list(unique.items())
        entries.sort(key=lambda x: (
            -(_number(x[1].get("probability")) or 0),
            -(_number(x[1].get("confidence")) or 0),
        ))
        ranked.append((len(unique), max((_number(t.get("probability")) or 0) for _, t in entries), entries))
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    limit = int(max_cards or 0)
    chosen = ranked if limit <= 0 else ranked[:limit]
    return [x[2] for x in chosen]


def render_card(entries, target_date):
    from PIL import Image, ImageDraw, ImageFont
    w, h = 1080, 900
    im = Image.new("RGB", (w, h), "#081325")
    draw = ImageDraw.Draw(im)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    def font(size, bold=False):
        try:
            return ImageFont.truetype(bold_path if bold else font_path, size)
        except OSError:
            return ImageFont.load_default()
    draw.rounded_rectangle((26, 25, 1054, 875), radius=28, fill="#101f38", outline="#2878bd", width=3)
    draw.text((58, 55), "NETRATTLER", font=font(61, True), fill="#ffce61")
    draw.text((60, 131), "MATCH ANALYSE  |  REAL ODDS ONLY", font=font(25), fill="#8bd6ef")
    _, first = entries[0]
    match = str(first.get("match", ""))
    # Never use uncontrolled text to render outside the image.
    draw.text((60, 203), match[:43], font=font(39, True), fill="#ffffff")
    draw.text((60, 265), (str(first.get("league", ""))[:45] + "   |   " + str(target_date)[:16]), font=font(24), fill="#b6c9df")
    draw.line((60, 327, 1018, 327), fill="#3477b0", width=3)
    draw.text((62, 347), "MARKT / TIPP", font=font(23, True), fill="#94aeca")
    draw.text((705, 347), "QUOTE", font=font(23, True), fill="#94aeca")
    draw.text((852, 347), "PROB.", font=font(23, True), fill="#94aeca")
    for i, (market, tip) in enumerate(entries[:6]):
        y = 405 + i * 69
        draw.rounded_rectangle((55, y-10, 1024, y+52), radius=12, fill="#172e4d")
        draw.text((70, y), _label(market, tip)[:31], font=font(24, True), fill="#eaf4ff")
        draw.text((704, y), f"{_price(tip):.2f}", font=font(28, True), fill="#ffce61")
        prob = _number(tip.get("probability"))
        if prob is not None:
            pct = prob * 100 if 0 <= prob <= 1 else prob
            if 0 <= pct <= 100:
                draw.text((853, y), f"{pct:.0f}%", font=font(28, True), fill="#54e5bc")
    draw.text((60, 830), "Nur validierte Tipps · Keine geschätzten Quoten", font=font(21), fill="#96afc9")
    data = io.BytesIO()
    im.save(data, format="PNG", optimize=True)
    return data.getvalue()


def send_cards(tips_by_market, target_date, token, stats_chat, log=print):
    if os.getenv("ENABLE_STATS_MATCH_CARDS", "true").lower() not in ("1", "true", "yes", "on"):
        return 0
    if not token or not stats_chat:
        log("Match-Cards: kein expliziter Stats-Chat oder Telegram-Token; übersprungen")
        return 0
    try:
        cards = select_cards(tips_by_market, os.getenv("STATS_MATCH_CARDS_MAX", "0"))
        sent = 0
        for entries in cards:
            match = str(entries[0][1].get("match", "Match"))[:100]
            payload = render_card(entries, target_date)
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": stats_chat, "caption": "NETRATTLER | " + match},
                files={"photo": ("netrattler_match.png", payload, "image/png")},
                timeout=15,
            )
            if resp.ok and resp.json().get("ok"):
                sent += 1
            else:
                log(f"Match-Card Telegram HTTP {resp.status_code}; Text-Tipps bleiben aktiv")
        return sent
    except Exception as exc:
        log(f"Match-Cards optional übersprungen: {type(exc).__name__}: {str(exc)[:90]}")
        return 0
