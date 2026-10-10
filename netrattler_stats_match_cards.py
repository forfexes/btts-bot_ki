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
_BADGE_CACHE = {}


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


def _badge_bytes(team):
    key = _norm(team)
    if not key:
        return b""
    if key in _BADGE_CACHE:
        return _BADGE_CACHE[key]
    payload = b""
    url = _logo_url(team)
    if url:
        try:
            r = requests.get(url, timeout=6)
            if r.ok and r.content:
                payload = r.content
        except Exception:
            payload = b""
    _BADGE_CACHE[key] = payload
    return payload


def _paste_badge(im, draw, team, box, font):
    from PIL import Image
    x0, y0, x1, y1 = box
    size = min(x1 - x0, y1 - y0)
    loaded = False
    payload = _badge_bytes(team)
    if payload:
        try:
            badge = Image.open(io.BytesIO(payload)).convert("RGBA")
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


def _pct(value):
    n = _number(value)
    if n is None:
        return None
    n = n * 100 if 0 <= n <= 1 else n
    return n if 0 <= n <= 100 else None


def _form_chars(value):
    chars = [c for c in str(value or "").upper() if c in "WDL"]
    return chars[-5:]


def render_card(entries, target_date):
    """Neon-blue premium match card (NETRATTLER branding, display-only).

    Every block is optional: it is drawn only when the tip carries the real
    value. Nothing here is invented or estimated.
    """
    from PIL import Image, ImageDraw, ImageFont

    rows = entries[:5]
    w, h = 1080, 1130
    im = Image.new("RGB", (w, h), "#020a2a")
    draw = ImageDraw.Draw(im)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    def font(size, bold=False):
        try:
            return ImageFont.truetype(bold_path if bold else font_path, size)
        except OSError:
            return ImageFont.load_default()

    def text_c(text, cx, y, f, fill):
        bb = draw.textbbox((0, 0), text, font=f)
        draw.text((cx - (bb[2] - bb[0]) / 2, y), text, font=f, fill=fill)

    def panel(box, outline="#2d6bff", fill="#06124a", radius=18):
        x0, y0, x1, y1 = box
        draw.rounded_rectangle((x0 - 2, y0 - 2, x1 + 2, y1 + 2), radius=radius + 2, outline="#12307f", width=3)
        draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)

    # Background glow stripes + frame
    for i in range(0, 300, 6):
        draw.line((0, i, w, i), fill=(2, 10 + i // 14, 42 + i // 5))
    _, first = rows[0]
    match = str(first.get("match", ""))
    home, away = _teams(match)
    league = str(first.get("league", ""))[:48]
    kickoff = str(first.get("time") or first.get("time_local") or "")

    # Header
    text_c("NETRATTLER", w / 2, 30, font(62, True), "#ffffff")
    text_c("PREMIUM MATCH INTELLIGENCE", w / 2, 100, font(20, True), "#9fc2ff")
    draw.text((46, 38), "REAL ODDS.", font=font(20, True), fill="#ffffff")
    draw.text((46, 62), "REAL CONTEXT.", font=font(20, True), fill="#ffffff")
    draw.text((w - 250, 38), "BETTER PICKS.", font=font(20, True), fill="#ffffff")
    draw.text((w - 250, 62), "CLEANER CARDS.", font=font(20, True), fill="#ffffff")
    draw.rounded_rectangle((300, 132, 780, 166), radius=16, fill="#0b1f6e", outline="#3b82ff", width=2)
    text_c(league or "FUSSBALL", w / 2, 138, font(18, True), "#d6e6ff")
    draw.rounded_rectangle((420, 176, 660, 208), radius=14, fill="#d62839")
    text_c("PRE-KICKOFF", w / 2, 181, font(17, True), "#ffffff")

    _paste_badge(im, draw, home, (70, 130, 250, 310), font(44, True))
    _paste_badge(im, draw, away, (830, 130, 1010, 310), font(44, True))
    text_c("VS", w / 2, 218, font(54, True), "#ffffff")
    meta = "  ·  ".join(x for x in (kickoff, str(target_date)[:10]) if x)
    text_c(meta, w / 2, 288, font(19, True), "#d6e6ff")
    text_c(home[:22], 160, 322, font(30, True), "#ffffff")
    text_c(away[:22], 920, 322, font(30, True), "#ffffff")

    # Direction panel (top pick)
    main_market, main_tip = rows[0]
    pct = _pct(main_tip.get("probability"))
    panel((34, 376, 560, 560))
    draw.text((56, 390), "NETRATTLER DIRECTION", font=font(22, True), fill="#ffffff")
    draw.rounded_rectangle((56, 424, 196, 452), radius=10, outline="#ffd166", width=2)
    draw.text((70, 428), "MODEL EDGE" if main_market == "1x2" else "TOP PICK", font=font(15, True), fill="#ffd166")
    label = _label(main_market, main_tip)
    label = label.replace("1X2 / GOAL HUNTER", "1X2")
    draw.text((56, 466), label[:20], font=font(28 if len(label) < 16 else 22, True), fill="#ffffff")
    if pct is not None:
        draw.rounded_rectangle((376, 400, 544, 500), radius=14, fill="#063a4a", outline="#27e0c0", width=2)
        text_c(f"{pct:.0f}%", 460, 410, font(50, True), "#27e0c0")
        text_c("MODEL PROB.", 460, 472, font(14, True), "#27e0c0")
    cells = [("QUOTE", f"{_price(main_tip):.2f}")]
    fair = _number(main_tip.get("fairOdds"))
    if fair:
        cells.append(("FAIR", f"{fair:.2f}"))
    cells.append(("MÄRKTE", str(len(rows))))
    cw = (526 - 24) / len(cells)
    for i, (k, v) in enumerate(cells):
        x0 = 46 + i * cw
        draw.rounded_rectangle((x0 + 4, 506, x0 + cw - 4, 550), radius=10, fill="#0a1c66", outline="#2d6bff", width=1)
        text_c(k, x0 + cw / 2, 508, font(12, True), "#9fc2ff")
        text_c(v, x0 + cw / 2, 524, font(22, True), "#ffd166")

    # 1X2 model panel (only with real model probabilities) else market outlook
    panel((574, 376, 1046, 560))
    p1, px, p2 = (_pct(main_tip.get(k)) for k in ("p_home", "p_draw", "p_away"))
    if None not in (p1, px, p2):
        draw.text((596, 390), "NETRATTLER 1X2 MODEL", font=font(22, True), fill="#ffffff")
        for i, (val, name, col) in enumerate(((p1, home, "#ffffff"), (px, "Draw", "#ffffff"), (p2, away, "#ffffff"))):
            x0 = 592 + i * 150
            draw.rounded_rectangle((x0, 424, x0 + 140, 494), radius=12, fill="#0a1c66", outline="#3b82ff", width=2)
            text_c(f"{val:.0f}%", x0 + 70, 430, font(38, True), col)
            text_c(str(name)[:12], x0 + 70, 474, font(13, True), "#9fc2ff")
        tot = max(p1 + px + p2, 1)
        bx0, bx1, by = 592, 1028, 512
        a = bx0 + (bx1 - bx0) * p1 / tot
        b2 = a + (bx1 - bx0) * px / tot
        draw.rounded_rectangle((bx0, by, bx1, by + 14), radius=7, fill="#2d6bff")
        draw.rectangle((a, by, b2, by + 14), fill="#9fb4d8")
        draw.rectangle((b2, by, bx1, by + 14), fill="#d62839")
        text_c(f"{home[:12]} {p1:.0f}%   ·   Draw {px:.0f}%   ·   {away[:12]} {p2:.0f}%", 810, 532, font(14, True), "#d6e6ff")
    else:
        draw.text((596, 390), "MODEL MARKET OUTLOOK", font=font(22, True), fill="#ffffff")
        shown = [(m, t) for m, t in rows if _pct(t.get("probability")) is not None][:3]
        for i, (m, t) in enumerate(shown):
            x0 = 592 + i * 150
            draw.rounded_rectangle((x0, 424, x0 + 140, 540), radius=12, fill="#063a4a", outline="#27e0c0", width=2)
            text_c(_label(m, t).split("  ·  ")[0][:16], x0 + 70, 432, font(13, True), "#d6e6ff")
            text_c(f"{_pct(t.get('probability')):.0f}%", x0 + 70, 466, font(38, True), "#27e0c0")
            text_c(f"@ {_price(t):.2f}", x0 + 70, 514, font(15, True), "#ffd166")

    # Qualified markets table
    top = 586
    panel((34, top, 1046, top + 52 + len(rows) * 58))
    draw.text((56, top + 12), "QUALIFIZIERTE MÄRKTE", font=font(20, True), fill="#ffffff")
    draw.text((760, top + 16), "QUOTE", font=font(15, True), fill="#9fc2ff")
    draw.text((930, top + 16), "PROB.", font=font(15, True), fill="#9fc2ff")
    for i, (market, tip) in enumerate(rows):
        y = top + 48 + i * 58
        draw.rounded_rectangle((48, y, 1032, y + 50), radius=10, fill="#0a1c66" if i % 2 == 0 else "#08175a")
        draw.text((66, y + 12), _label(market, tip)[:40], font=font(22, True), fill="#eef7ff")
        draw.text((762, y + 11), f"{_price(tip):.2f}", font=font(26, True), fill="#ffd166")
        p = _pct(tip.get("probability"))
        if p is not None:
            draw.text((930, y + 11), f"{p:.0f}%", font=font(26, True), fill="#27e0c0")

    # Context stats: drawn only for values that really exist on the tips.
    ctx = {}
    for _, t in rows:
        for k in ("xg_home", "xg_away", "btts_rate_home", "btts_rate_away", "homeForm", "awayForm",
                  "h2h_btts", "h2h_avg_goals", "avg_goals_home", "avg_goals_away", "exp_goals_home", "exp_goals_away"):
            if ctx.get(k) in (None, "") and t.get(k) not in (None, ""):
                ctx[k] = t.get(k)
    y = top + 52 + len(rows) * 58 + 24
    blocks = []
    gh = _number(ctx.get("xg_home") or ctx.get("avg_goals_home") or ctx.get("exp_goals_home"))
    ga = _number(ctx.get("xg_away") or ctx.get("avg_goals_away") or ctx.get("exp_goals_away"))
    if gh is not None and ga is not None:
        blocks.append(("TORE / SPIEL", f"{gh:.1f}  ·  {ga:.1f}"))
    bh, ba = _pct(ctx.get("btts_rate_home")), _pct(ctx.get("btts_rate_away"))
    if bh is not None and ba is not None:
        blocks.append(("BTTS-RATE", f"{bh:.0f}%  ·  {ba:.0f}%"))
    if ctx.get("h2h_btts"):
        blocks.append(("H2H BTTS", str(ctx["h2h_btts"])))
    h2g = _number(ctx.get("h2h_avg_goals"))
    if h2g is not None:
        blocks.append(("H2H Ø TORE", f"{h2g:.1f}"))
    if blocks:
        panel((34, y, 1046, y + 150))
        draw.text((56, y + 10), "FORM & STATS", font=font(20, True), fill="#ffffff")
        bw = (980 - 10 * (len(blocks) - 1)) / len(blocks)
        for i, (k, v) in enumerate(blocks[:4]):
            x0 = 50 + i * (bw + 10)
            draw.rounded_rectangle((x0, y + 44, x0 + bw, y + 100), radius=10, fill="#0a1c66", outline="#2d6bff", width=1)
            text_c(k, x0 + bw / 2, y + 48, font(13, True), "#9fc2ff")
            text_c(v, x0 + bw / 2, y + 68, font(24, True), "#ffffff")
        colors = {"W": "#1fbf5b", "D": "#e0a800", "L": "#d62839"}
        for side, key, x0 in ((home, "homeForm", 56), (away, "awayForm", 560)):
            chars = _form_chars(ctx.get(key))
            if chars:
                draw.text((x0, y + 112), f"{side[:14]}", font=font(14, True), fill="#d6e6ff")
                for j, c in enumerate(chars):
                    cx = x0 + 150 + j * 34
                    draw.rounded_rectangle((cx, y + 110, cx + 28, y + 136), radius=6, fill=colors[c])
                    text_c(c, cx + 14, y + 113, font(16, True), "#ffffff")
        y += 150 + 18
    fy = y + 6
    draw.line((60, fy, w - 60, fy), fill="#1f55e8", width=2)
    text_c("NETRATTLER  |  Nur finale, validierte Picks · keine geschätzten Quoten", w / 2, fy + 12, font(16, True), "#9fc2ff")
    final_h = fy + 52
    draw.rounded_rectangle((14, 14, w - 14, final_h - 14), radius=26, outline="#1f55e8", width=3)
    im = im.crop((0, 0, w, final_h))
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

    # Badge lookup is presentation-only; prefetch concurrently so dozens of cards
    # do not serialize two network calls per team.
    try:
        from concurrent.futures import ThreadPoolExecutor
        teams = []
        seen_teams = set()
        for entries in cards:
            if not entries:
                continue
            home, away = _teams(entries[0][1].get("match", ""))
            for team in (home, away):
                key = _norm(team)
                if key and key not in seen_teams:
                    seen_teams.add(key)
                    teams.append(team)
        if teams:
            with ThreadPoolExecutor(max_workers=min(10, len(teams))) as ex:
                list(ex.map(_badge_bytes, teams))
    except Exception:
        pass

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
