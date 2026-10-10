"""NETRATTLER premium match cards.

Display-only: consumes final guarded REAL_ODDS tips. It never invents prices,
probabilities or selections. Club badges are presentation-only and best-effort.
"""
import io
import os
import re
import time
import unicodedata
from collections import defaultdict

import requests

_LOGO_CACHE = {}


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
        "props": "PLAYER PROP", "advanced_props": "PLAYER PROP",
        "scorer": "ANYTIME GOALSCORER", "builder": "BUILDER",
    }
    value = str(tip.get("tip") or tip.get("selection") or "").strip()
    base = labels.get(market, market.upper())
    if value and value.upper() not in ("YES", "JA"):
        return f"{base}  ·  {value[:34]}"
    return base


def _norm(value):
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", text)


def _teams(match):
    text = str(match or "").strip()
    for sep in (" vs ", " v ", " - "):
        if sep in text:
            a, b = text.split(sep, 1)
            return a.strip(), b.strip()
    return text, ""


def _logo_url(team):
    key = _norm(team)
    if not key:
        return ""
    if key in _LOGO_CACHE:
        return _LOGO_CACHE[key]
    url = ""
    try:
        api_key = os.getenv("THESPORTSDB_API_KEY", "3").strip() or "3"
        r = requests.get(
            f"https://www.thesportsdb.com/api/v1/json/{api_key}/searchteams.php",
            params={"t": team},
            timeout=6,
        )
        if r.ok:
            rows = (r.json() or {}).get("teams") or []
            soccer = [x for x in rows if str(x.get("strSport") or "").lower() == "soccer"]
            rows = soccer or rows
            if rows:
                exact = next(
                    (x for x in rows if _norm(x.get("strTeam")) == key),
                    rows[0],
                )
                url = str(exact.get("strBadge") or exact.get("strLogo") or "").strip()
    except Exception:
        url = ""
    _LOGO_CACHE[key] = url
    return url


def _paste_badge(im, draw, team, box, font):
    from PIL import Image
    x0, y0, x1, y1 = box
    size = min(x1 - x0, y1 - y0)
    loaded = False
    url = _logo_url(team)
    if url:
        try:
            r = requests.get(url, timeout=6)
            if r.ok:
                badge = Image.open(io.BytesIO(r.content)).convert("RGBA")
                badge.thumbnail((size, size), Image.Resampling.LANCZOS)
                px = x0 + (x1 - x0 - badge.width) // 2
                py = y0 + (y1 - y0 - badge.height) // 2
                im.paste(badge, (px, py), badge)
                loaded = True
        except Exception:
            loaded = False
    if loaded:
        return
    # Clean fallback when no public badge is available.
    draw.ellipse((x0, y0, x1, y1), fill="#172f50", outline="#39b9e7", width=4)
    initials = "".join(part[:1] for part in re.findall(r"[A-Za-z0-9]+", team)[:3]).upper()[:3] or "FC"
    bbox = draw.textbbox((0, 0), initials, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((x0 + (x1-x0-tw)/2, y0 + (y1-y0-th)/2 - 4), initials, font=font, fill="#ffffff")


def select_cards(tips_by_market, max_cards=0):
    matches = defaultdict(list)
    for market, tips in (tips_by_market or {}).items():
        for tip in tips or []:
            if not _valid(tip):
                continue
            match = str(tip["match"]).strip()
            matches[match.casefold()].append((market, tip))

    ranked = []
    for entries in matches.values():
        # Keep the best final tip per market; never add an unqualified market.
        unique = {}
        for market, tip in entries:
            old = unique.get(market)
            score = (_number(tip.get("probability")) or 0, _number(tip.get("confidence")) or 0)
            old_score = (
                _number(old.get("probability")) or 0,
                _number(old.get("confidence")) or 0,
            ) if old else (-1, -1)
            if old is None or score > old_score:
                unique[market] = tip
        rows = list(unique.items())
        rows.sort(key=lambda x: (
            _number(x[1].get("probability")) or 0,
            _number(x[1].get("confidence")) or 0,
        ), reverse=True)
        ranked.append((len(rows), max((_number(t.get("probability")) or 0) for _, t in rows), rows))

    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    limit = int(max_cards or 0)
    chosen = ranked if limit <= 0 else ranked[:limit]
    return [x[2] for x in chosen]


def render_card(entries, target_date):
    from PIL import Image, ImageDraw, ImageFont

    rows = entries[:6]
    h = max(760, 650 + len(rows) * 72)
    w = 1080
    im = Image.new("RGB", (w, h), "#06101f")
    draw = ImageDraw.Draw(im)

    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    def font(size, bold=False):
        try:
            return ImageFont.truetype(bold_path if bold else font_path, size)
        except OSError:
            return ImageFont.load_default()

    # Premium frame / header.
    draw.rounded_rectangle((24, 22, 1056, h-22), radius=32, fill="#0d1c33", outline="#2b84bd", width=3)
    draw.rounded_rectangle((38, 36, 1042, 136), radius=22, fill="#112744")
    draw.text((64, 53), "NETRATTLER", font=font(50, True), fill="#ffd166")
    draw.text((64, 106), "PREMIUM MATCH INTELLIGENCE", font=font(19, True), fill="#75d7f0")
    draw.rounded_rectangle((772, 63, 1014, 111), radius=20, fill="#143a43")
    draw.text((797, 74), "REAL ODDS VERIFIED", font=font(18, True), fill="#5ce1b8")

    _, first = rows[0]
    match = str(first.get("match", ""))
    home, away = _teams(match)

    # Club badges and versus block.
    _paste_badge(im, draw, home, (105, 168, 265, 328), font(39, True))
    _paste_badge(im, draw, away, (815, 168, 975, 328), font(39, True))
    draw.text((493, 211), "VS", font=font(43, True), fill="#ffd166")

    def centered(text, center_x, y, max_chars=25):
        value = str(text or "")[:max_chars]
        bbox = draw.textbbox((0, 0), value, font=font(28, True))
        tw = bbox[2] - bbox[0]
        draw.text((center_x - tw/2, y), value, font=font(28, True), fill="#ffffff")

    centered(home, 185, 343, 25)
    centered(away, 895, 343, 25)

    league = str(first.get("league", ""))[:45]
    kickoff = str(first.get("time") or first.get("time_local") or "")
    meta = "  ·  ".join(x for x in (league, kickoff, str(target_date)[:10]) if x)
    bbox = draw.textbbox((0, 0), meta, font=font(20))
    draw.text(((w-(bbox[2]-bbox[0]))/2, 389), meta, font=font(20), fill="#9fb4ca")

    # Main pick spotlight.
    main_market, main_tip = rows[0]
    prob = _number(main_tip.get("probability"))
    pct = prob * 100 if prob is not None and 0 <= prob <= 1 else prob
    main_label = _label(main_market, main_tip)
    draw.rounded_rectangle((58, 432, 1022, 535), radius=22, fill="#15365b", outline="#2fa8db", width=2)
    draw.text((83, 450), "TOP PICK", font=font(18, True), fill="#75d7f0")
    draw.text((83, 480), main_label[:46], font=font(28, True), fill="#ffffff")
    draw.text((755, 464), f"{_price(main_tip):.2f}", font=font(38, True), fill="#ffd166")
    if pct is not None and 0 <= pct <= 100:
        draw.text((895, 464), f"{pct:.0f}%", font=font(38, True), fill="#5ce1b8")

    # Qualified-market rows.
    top = 568
    draw.text((65, top), "QUALIFIZIERTE MÄRKTE", font=font(18, True), fill="#91a8c1")
    draw.text((765, top), "QUOTE", font=font(18, True), fill="#91a8c1")
    draw.text((905, top), "PROB.", font=font(18, True), fill="#91a8c1")
    y0 = top + 34
    for i, (market, tip) in enumerate(rows):
        y = y0 + i * 67
        fill = "#132b49" if i % 2 == 0 else "#10263f"
        draw.rounded_rectangle((56, y-7, 1024, y+50), radius=11, fill=fill)
        draw.text((74, y+5), _label(market, tip)[:43], font=font(22, True), fill="#eef7ff")
        draw.text((767, y+4), f"{_price(tip):.2f}", font=font(25, True), fill="#ffd166")
        p = _number(tip.get("probability"))
        p = p * 100 if p is not None and 0 <= p <= 1 else p
        if p is not None and 0 <= p <= 100:
            draw.text((906, y+4), f"{p:.0f}%", font=font(25, True), fill="#5ce1b8")

    footer_y = h - 58
    draw.line((58, footer_y-14, 1022, footer_y-14), fill="#234767", width=2)
    draw.text((64, footer_y), "Nur finale, validierte Picks · keine geschätzten Quoten", font=font(18), fill="#7892ad")

    data = io.BytesIO()
    im.save(data, format="PNG", optimize=True)
    return data.getvalue()


def _send_photo(token, chat, caption, payload, log):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    max_retries = max(1, int(os.getenv("STATS_MATCH_CARDS_RETRIES", "4")))
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                url,
                data={"chat_id": chat, "caption": caption},
                files={"photo": ("netrattler_match.png", payload, "image/png")},
                timeout=20,
            )
            body = {}
            try:
                body = resp.json() or {}
            except Exception:
                body = {}
            if resp.ok and body.get("ok"):
                return True
            if resp.status_code == 429:
                retry_after = int((body.get("parameters") or {}).get("retry_after") or 2)
                wait = max(1, min(30, retry_after + 1))
                log(f"Match-Card Telegram 429 · Retry in {wait}s ({attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            log(f"Match-Card Telegram HTTP {resp.status_code}; Text-Tipps bleiben aktiv")
            return False
        except Exception as exc:
            if attempt + 1 >= max_retries:
                log(f"Match-Card Telegram Fehler: {type(exc).__name__}")
                return False
            time.sleep(min(6, 1 + attempt * 2))
    return False


def send_cards(tips_by_market, target_date, token, stats_chat, log=print):
    if os.getenv("ENABLE_STATS_MATCH_CARDS", "true").lower() not in ("1", "true", "yes", "on"):
        return 0
    if not token or not stats_chat:
        log("Match-Cards: kein Ziel-Chat oder Telegram-Token; übersprungen")
        return 0

    cards = select_cards(tips_by_market, os.getenv("STATS_MATCH_CARDS_MAX", "0"))
    sent = 0
    pause = max(0.0, float(os.getenv("STATS_MATCH_CARDS_SEND_DELAY_SEC", "1.2")))
    for entries in cards:
        try:
            match = str(entries[0][1].get("match", "Match"))[:100]
            payload = render_card(entries, target_date)
            if _send_photo(token, stats_chat, "NETRATTLER | " + match, payload, log):
                sent += 1
            if pause:
                time.sleep(pause)
        except Exception as exc:
            log(f"Match-Card optional übersprungen: {type(exc).__name__}: {str(exc)[:90]}")
    return sent
