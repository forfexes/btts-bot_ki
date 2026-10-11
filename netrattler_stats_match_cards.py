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
STATS = {"tsdb_ok": 0, "tsdb_429": 0, "tsdb_empty": 0, "tsdb_err": 0,
         "wiki_ok": 0, "wiki_empty": 0, "wiki_err": 0, "fallback_initials": 0, "err_sample": ""}


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


_CREST_INDEX = None
_CREST_STOP = {
    "fc", "cf", "afc", "sc", "ac", "as", "ss", "us", "sv", "vfb", "vfl", "fk", "sk", "kv", "krc", "kaa",
    "kvc", "rsc", "raal", "rc", "cd", "ud", "ca", "bk", "if", "ik", "sd", "fsv", "tsg", "rb", "ssc",
    "de", "la", "le", "real", "royal", "club", "calcio", "1", "04", "05", "1899", "1846", "vv", "sp", "1909", "65", "71", "46",
}


def _tokens(value):
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return [t for t in re.split(r"[^a-z0-9]+", text) if t]


def _load_crest_index():
    global _CREST_INDEX
    if _CREST_INDEX is not None:
        return _CREST_INDEX
    _CREST_INDEX = {"sha": "", "rows": []}
    try:
        import json
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "netrattler_crest_index.json")
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        rows = []
        for name, rel in data.get("clubs", []):
            toks = _tokens(name)
            core = [t for t in toks if t not in _CREST_STOP] or toks
            rows.append((name, rel, set(toks), set(core), _norm(name)))
        _CREST_INDEX = {"sha": data.get("sha", "master"), "repo": data.get("repo", ""), "rows": rows}
    except Exception:
        pass
    return _CREST_INDEX


def _crest_from_index(team):
    """Free GitHub crest collection (top leagues). Conservative fuzzy match."""
    idx = _load_crest_index()
    rows = idx.get("rows") or []
    team = {"rennes": "Stade Rennais", "bayern": "Bayern Munich", "psg": "Paris Saint-Germain"}.get(
        str(team or "").strip().lower(), team)
    toks = _tokens(team)
    if not toks or not rows:
        return ""
    core = {t for t in toks if t not in _CREST_STOP} or set(toks)
    key = _norm(team)
    best, best_score = None, 0.0
    for name, rel, ntoks, ncore, nkey in rows:
        if nkey == key:
            score = 10.0
        elif core and ncore and (core <= ncore or ncore <= core):
            score = 2.0 + len(core & ncore) / max(len(core | ncore), 1)
        elif len(core) == 1 and len(next(iter(core))) >= 5 and any(
            t.startswith(next(iter(core))[:5]) or next(iter(core)).startswith(t[:5])
            for t in ncore if len(t) >= 5
        ):
            score = 1.0
        else:
            continue
        if score > best_score:
            best, best_score = rel, score
    if not best:
        return ""
    from urllib.parse import quote
    return f"https://raw.githubusercontent.com/{idx.get('repo')}/{idx.get('sha')}/logos/{quote(best)}"


def _query_variants(team):
    base = str(team or "").strip()
    out = [base]
    stripped = re.sub(r"\b(fc|cf|afc|sc|ac|as|ss|us|sv|vfb|vfl|fk|sk|kv|krc|rc|cd|ud|ca)\b\.?", " ", base, flags=re.I)
    stripped = " ".join(stripped.split())
    if stripped and stripped.lower() != base.lower():
        out.append(stripped)
    for sep in ("-", "/"):
        if sep in base:
            out.append(base.replace(sep, " "))
    words = stripped.split() or base.split()
    if len(words) > 1:
        out.append(words[0])
        out.append(words[-1])
    seen, res = set(), []
    for q in out:
        if q and q.lower() not in seen:
            seen.add(q.lower())
            res.append(q)
    return res[:4]


def _wiki_badge(team):
    """Fallback crest from the club's Wikipedia infobox image."""
    try:
        r = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query", "generator": "search", "gsrsearch": f"{team} football club",
                "gsrlimit": 1, "prop": "pageimages", "piprop": "thumbnail", "pithumbsize": 300,
                "format": "json",
            },
            headers={"User-Agent": "NETRATTLER-cards/1.0 (match card crests)"},
            timeout=6,
        )
        pages = ((r.json() or {}).get("query") or {}).get("pages") or {}
        for page in pages.values():
            url = str((page.get("thumbnail") or {}).get("source") or "")
            if url:
                STATS["wiki_ok"] += 1
                return url
        STATS["wiki_empty"] += 1
    except Exception as exc:
        STATS["wiki_err"] += 1
        STATS["err_sample"] = f"wiki:{type(exc).__name__}"
    return ""


_TSDB_LAST = 0.0
_TEAM_LEAGUE = {}
_FL_COUNTRY = {}
_FL_ALIAS = {"usa": "usa", "united-states": "usa", "korea-republic": "south-korea", "south-korea": "south-korea",
             "czech-republic": "czechia", "bosnia-herzegovina": "bosnia-and-herzegovina", "uae": "uae",
             "united-arab-emirates": "uae", "ireland": "republic-of-ireland", "turkiye": "turkey"}
_FL_STOP = {"fc", "cf", "cd", "sc", "ac", "afc", "ca", "club", "de", "sd", "ud", "fk", "sk", "if", "bk", "cs",
            "sv", "vfl", "vfb", "rcd", "rc", "ssc", "as", "us", "ss", "the", "atletico", "deportivo"}


def _slug(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _fl_get(url):
    try:
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0 NETRATTLER-cards/1.0"})
        return r.text if r.ok else ""
    except Exception:
        STATS["fl_err"] = STATS.get("fl_err", 0) + 1
        return ""


def _fl_country_slugs(country):
    if country in _FL_COUNTRY:
        return _FL_COUNTRY[country]
    html = _fl_get(f"https://football-logos.cc/{country}/")
    slugs = sorted(set(re.findall(r'href="(?:https://football-logos\.cc)?/%s/([a-z0-9-]+)/"' % re.escape(country), html)))
    _FL_COUNTRY[country] = slugs
    return slugs


def _fl_logo(team, league):
    """Club crest from football-logos.cc: club page -> 700x700 PNG."""
    if os.getenv("ENABLE_FOOTBALL_LOGOS_CC", "true").lower() not in ("1", "true", "yes", "on"):
        return ""
    country = _slug(str(league or "").split(" - ")[0])
    country = _FL_ALIAS.get(country, country)
    if not country:
        return ""
    full = _slug(team)
    core = "-".join(t for t in full.split("-") if t not in _FL_STOP) or full
    cands = []
    for c in (full, core):
        if c and c not in cands:
            cands.append(c)
    want = set(core.split("-"))
    best, best_score = "", 0.0
    for sl in _fl_country_slugs(country):
        toks = set(t for t in sl.split("-") if t not in _FL_STOP)
        if not toks:
            continue
        inter = len(toks & want)
        score = inter / max(len(toks | want), 1)
        if inter and score > best_score:
            best, best_score = sl, score
    if best and best_score >= 0.5 and best not in cands:
        cands.insert(0 if best_score >= 0.99 else 1, best)
    for sl in cands[:3]:
        html = _fl_get(f"https://football-logos.cc/{country}/{sl}/")
        m = re.search(r"https://assets\.football-logos\.cc/logos/[a-z0-9-]+/(?:700x700|512x512|256x256)/[a-z0-9-]+\.[0-9a-f]+\.png", html)
        if m:
            STATS["fl_ok"] = STATS.get("fl_ok", 0) + 1
            return m.group(0)
    STATS["fl_miss"] = STATS.get("fl_miss", 0) + 1
    return ""


def _search_badge(query, api_key, key):
    """Return (url, rate_limited). Retries politely on HTTP 429."""
    global _TSDB_LAST
    gap = float(os.getenv("TSDB_MIN_GAP_SEC", "2.3"))
    for attempt in range(3):
        wait = _TSDB_LAST + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        _TSDB_LAST = time.time()
        r = requests.get(
            f"https://www.thesportsdb.com/api/v1/json/{api_key}/searchteams.php",
            params={"t": query},
            timeout=6,
        )
        if r.status_code == 429:
            STATS["tsdb_429"] += 1
            time.sleep(1.5 + attempt * 1.5)
            continue
        if not r.ok:
            STATS["tsdb_err"] += 1
            STATS["err_sample"] = f"tsdb:HTTP{r.status_code}"
            return "", False
        try:
            rows = (r.json() or {}).get("teams") or []
        except Exception:
            return "", False
        soccer = [x for x in rows if str(x.get("strSport") or "").lower() == "soccer"]
        rows = soccer or rows
        if not rows:
            STATS["tsdb_empty"] += 1
            return "", False
        exact = next((x for x in rows if _norm(x.get("strTeam")) == key), rows[0])
        found = str(exact.get("strBadge") or exact.get("strLogo") or "").strip()
        if found:
            STATS["tsdb_ok"] += 1
        return found, False
    return "", True


def _logo_url(team):
    key = _norm(team)
    if not key:
        return ""
    if key in _LOGO_CACHE:
        return _LOGO_CACHE[key]
    url = _crest_from_index(team)
    if url:
        STATS["index_ok"] = STATS.get("index_ok", 0) + 1
        _LOGO_CACHE[key] = url
        return url
    url = _fl_logo(team, _TEAM_LEAGUE.get(key, ""))
    if url:
        _LOGO_CACHE[key] = url
        return url
    limited = False
    api_key = os.getenv("THESPORTSDB_API_KEY", "3").strip() or "3"
    for query in _query_variants(team):
        try:
            url, limited = _search_badge(query, api_key, key)
        except Exception as exc:
            url, limited = "", False
            STATS["tsdb_err"] += 1
            STATS["err_sample"] = f"tsdb:{type(exc).__name__}"
        if url or limited:
            break
    if not url:
        url = _wiki_badge(team)
    if url or not limited:  # do not cache a rate-limit failure
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
    STATS["fallback_initials"] += 1
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


def render_card(entries, target_date, result=None):
    """Neon-blue premium match card (NETRATTLER branding, display-only).

    Every block is optional: it is drawn only when the tip carries the real
    value. Nothing here is invented or estimated.
    """
    from PIL import Image, ImageDraw, ImageFont

    rows = entries[:5]
    if len(rows) == 1 and str(rows[0][0]) == "scorer" and rows[0][1].get("player"):
        return render_scorer_card(rows[0][1], target_date, result)
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
    result = result if isinstance(result, dict) else None
    marks = (result or {}).get("marks") or {}
    if result:
        draw.rounded_rectangle((420, 176, 660, 208), radius=14, fill="#1fbf5b")
        text_c("ABGESCHLOSSEN", w / 2, 181, font(17, True), "#ffffff")
    else:
        draw.rounded_rectangle((420, 176, 660, 208), radius=14, fill="#d62839")
        text_c("PRE-KICKOFF", w / 2, 181, font(17, True), "#ffffff")

    _paste_badge(im, draw, home, (70, 130, 250, 310), font(44, True))
    _paste_badge(im, draw, away, (830, 130, 1010, 310), font(44, True))
    if result and result.get("ft"):
        text_c(str(result["ft"]).replace("-", " : "), w / 2, 212, font(60, True), "#ffffff")
    else:
        text_c("VS", w / 2, 218, font(54, True), "#ffffff")
    shown_date = str(target_date)[:10]
    try:
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo as _ZI
        ko = str(first.get("_kickoff") or "")
        if ko[:2] == "20":
            shown_date = _dt.fromisoformat(ko).astimezone(_ZI("Europe/Zurich")).strftime("%Y-%m-%d")
    except Exception:
        pass
    meta = "  ·  ".join(x for x in (kickoff, shown_date) if x)
    if result and result.get("ht"):
        meta = f"Halbzeit {result['ht']}  ·  {shown_date}"
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
    if len(label) > 20 and "·" in label:
        label = label.split("·")[0].strip()
    draw.text((56, 466), label[:22], font=font(28 if len(label) < 16 else 22, True), fill="#ffffff")
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
    draw.text((880, top + 16), "PROB.", font=font(15, True), fill="#9fc2ff")
    for i, (market, tip) in enumerate(rows):
        y = top + 48 + i * 58
        mk = marks.get(str(i)) or marks.get(i)
        rowfill = "#0a1c66" if i % 2 == 0 else "#08175a"
        if mk == "win":
            rowfill = "#0b4a3a"
        elif mk == "loss":
            rowfill = "#5a1426"
        draw.rounded_rectangle((48, y, 1032, y + 50), radius=10, fill=rowfill)
        draw.text((66, y + 12), _label(market, tip)[:40], font=font(22, True), fill="#eef7ff")
        draw.text((762, y + 11), f"{_price(tip):.2f}", font=font(26, True), fill="#ffd166")
        p = _pct(tip.get("probability"))
        if p is not None:
            draw.text((880, y + 11), f"{p:.0f}%", font=font(26, True), fill="#27e0c0")
        if mk in ("win", "loss"):
            draw.text((972, y + 8), "✔" if mk == "win" else "✖", font=font(30, True),
                      fill="#27e0c0" if mk == "win" else "#ff5468")

    # Context stats: drawn only for values that really exist on the tips.
    ctx = {}
    for _, t in rows:
        for k in ("xg_home", "xg_away", "btts_rate_home", "btts_rate_away", "homeForm", "awayForm",
                  "h2h_btts", "h2h_avg_goals", "avg_goals_home", "avg_goals_away", "exp_goals_home", "exp_goals_away"):
            v = t.get(k)
            if k == "homeForm" and v in (None, ""):
                v = t.get("home_form")
            if k == "awayForm" and v in (None, ""):
                v = t.get("away_form")
            if v in (None, "", 0, 0.0, "0", "0.0"):
                continue
            if ctx.get(k) in (None, ""):
                ctx[k] = v
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
    has_form = bool(_form_chars(ctx.get('homeForm')) or _form_chars(ctx.get('awayForm')))
    if blocks or has_form:
        panel((34, y, 1046, y + 150))
        draw.text((56, y + 10), "FORM & STATS", font=font(20, True), fill="#ffffff")
        bw = (980 - 10 * (len(blocks) - 1)) / max(len(blocks), 1)
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
                data=({"chat_id": chat, "caption": caption} if caption else {"chat_id": chat}),
                files={"photo": ("netrattler_match.png", payload, "image/png")},
                timeout=20,
            )
            body = {}
            try:
                body = resp.json() or {}
            except Exception:
                body = {}
            if resp.ok and body.get("ok"):
                try:
                    return int((body.get("result") or {}).get("message_id") or 0) or True
                except Exception:
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

    # Badge lookup is presentation-only. Persistent cache first, then throttled lookups.
    try:
        teams, seen_teams = [], set()
        for entries in cards:
            if not entries:
                continue
            home, away = _teams(entries[0][1].get("match", ""))
            for team in (home, away):
                key = _norm(team)
                if key and entries[0][1].get("league"):
                    _TEAM_LEAGUE.setdefault(key, str(entries[0][1].get("league")))
                if key and key not in seen_teams:
                    seen_teams.add(key)
                    teams.append(team)
        _crest_cache_load()
        budget = float(os.getenv("CREST_PREFETCH_BUDGET_SEC", "240"))
        t0 = time.time()
        for rnd in range(2):
            todo = [t for t in teams if not _BADGE_CACHE.get(_norm(t))]
            for team in todo:
                if time.time() - t0 > budget:
                    break
                _BADGE_CACHE.pop(_norm(team), None)
                _badge_bytes(team)
            if rnd == 0 and any(not _BADGE_CACHE.get(_norm(t)) for t in teams) and time.time() - t0 < budget - 40:
                time.sleep(20)  # let the rate limit recover, retry the rest once
                for t in teams:
                    if not _BADGE_CACHE.get(_norm(t)):
                        _LOGO_CACHE.pop(_norm(t), None)
            else:
                break
        _crest_cache_save(teams)
        STATS["teams_total"] = len(teams)
        STATS["teams_with_badge"] = sum(1 for t in teams if _BADGE_CACHE.get(_norm(t)))
    except Exception as exc:
        log(f"Crest-Prefetch Fehler: {type(exc).__name__}")

    sent = 0
    pause = max(0.0, float(os.getenv("STATS_MATCH_CARDS_SEND_DELAY_SEC", "1.2")))
    for entries in cards:
        try:
            match = str(entries[0][1].get("match", "Match"))[:100]
            payload = render_card(entries, target_date)
            mid = _send_photo(token, stats_chat, "", payload, log)
            if mid:
                sent += 1
                if mid is not True:
                    save_card(stats_chat, mid, entries, target_date, log)
            if pause:
                time.sleep(pause)
        except Exception as exc:
            log(f"Match-Card optional übersprungen: {type(exc).__name__}: {str(exc)[:90]}")
    return sent


# ---------------------------------------------------------------- in-image results
def _sb():
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if not url or not key:
        return None, None
    return f"{url}/rest/v1/netrattler_match_cards", {
        "apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def match_key(match):
    return _norm(" ".join(_teams(match)))


def save_card(chat, message_id, entries, target_date, log=print):
    """Remember the sent card so settlement can edit the same image later."""
    try:
        url, hdr = _sb()
        if not url:
            return False
        import json as _json
        rows = []
        for market, tip in entries[:5]:
            rows.append([market, {k: v for k, v in tip.items()
                                  if isinstance(v, (str, int, float, bool, type(None)))}])
        first = entries[0][1]
        body = {
            "chat_id": str(chat), "message_id": int(message_id),
            "match": str(first.get("match", ""))[:200], "match_key": match_key(first.get("match", "")),
            "card_date": str(target_date)[:10], "entries": _json.loads(_json.dumps(rows, default=str)),
        }
        r = requests.post(url, headers=hdr, json=body, timeout=15)
        if not r.ok:
            log(f"Card-Speicher HTTP {r.status_code}")
        return r.ok
    except Exception as exc:
        log(f"Card-Speicher Fehler: {type(exc).__name__}")
        return False


def _edit_photo(token, chat, message_id, payload, log):
    import json as _json
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/editMessageMedia",
            data={"chat_id": chat, "message_id": int(message_id),
                  "media": _json.dumps({"type": "photo", "media": "attach://card"})},
            files={"card": ("netrattler_result.png", payload, "image/png")}, timeout=25,
        )
        if r.status_code == 429:
            time.sleep(min(30, int((r.json().get("parameters") or {}).get("retry_after") or 3) + 1))
            return False
        if not r.ok:
            log(f"Card-Edit HTTP {r.status_code}: {r.text[:100]}")
        return r.ok
    except Exception as exc:
        log(f"Card-Edit Fehler: {type(exc).__name__}")
        return False


def update_cards_with_results(token, results, log=print):
    """results: list of dicts {match, status('win'/'loss'), odds, group, ft, ht}.
    Re-renders the stored card of that match with a ✔/✖ per settled market and edits
    the original photo message (no new post)."""
    if os.getenv("ENABLE_RESULT_IN_CARD", "true").lower() not in ("1", "true", "yes", "on"):
        return 0
    url, hdr = _sb()
    if not url or not token or not results:
        return 0
    import json as _json
    by_key = defaultdict(list)
    for res in results:
        by_key[match_key(res.get("match", ""))].append(res)
    done = 0
    for mk, res_list in by_key.items():
        try:
            r = requests.get(url, headers=hdr, timeout=20,
                             params={"match_key": f"eq.{mk}", "select": "*", "order": "created_at.desc", "limit": "10"})
            cards = r.json() if r.ok else []
            for card in cards if isinstance(cards, list) else []:
                entries = [(m, t) for m, t in (card.get("entries") or [])]
                if not entries:
                    continue
                old = card.get("result") or {}
                marks = dict(old.get("marks") or {})
                ft = old.get("ft") or ""
                ht = old.get("ht") or ""
                for res in res_list:
                    ft = res.get("ft") or ft
                    ht = res.get("ht") or ht
                    for i, (m, t) in enumerate(entries):
                        odds_t = _number(t.get("odds") or t.get("oddsYes"))
                        odds_r = _number(res.get("odds"))
                        same_odds = odds_t is not None and odds_r is not None and abs(odds_t - odds_r) < 0.011
                        if str(m) == str(res.get("group")) or same_odds:
                            if str(m) == str(res.get("group")) and odds_t and odds_r and not same_odds and len(
                                    [1 for mm, _ in entries if str(mm) == str(m)]) > 1:
                                continue
                            marks[str(i)] = res.get("status")
                if not marks:
                    continue
                payload = render_card(entries, card.get("card_date") or "",
                                      {"marks": marks, "ft": ft, "ht": ht})
                if _edit_photo(token, card["chat_id"], card["message_id"], payload, log):
                    done += 1
                    requests.patch(url, headers=hdr, timeout=15, params={"card_id": f"eq.{card.get('card_id')}"},
                                   json={"result": {"marks": marks, "ft": ft, "ht": ht}})
                time.sleep(1.2)
        except Exception as exc:
            log(f"Card-Result optional übersprungen: {type(exc).__name__}")
    return done


# ---------------------------------------------------------------- goalscorer card
_PLAYER_CACHE = {}


def _player_photo(name, team=""):
    """Public player image (TheSportsDB cutout/thumb, then Wikipedia). Presentation only."""
    key = _norm(name)
    if not key:
        return b""
    if key in _PLAYER_CACHE:
        return _PLAYER_CACHE[key]
    urls = []
    try:
        r = requests.get("https://www.thesportsdb.com/api/v1/json/%s/searchplayers.php" %
                         (os.getenv("THESPORTSDB_API_KEY", "3").strip() or "3"),
                         params={"p": name}, timeout=6)
        rows = (r.json() or {}).get("player") or [] if r.ok else []
        rows = [x for x in rows if str(x.get("strSport") or "").lower() == "soccer"] or rows
        exact = next((x for x in rows if _norm(x.get("strPlayer")) == key), rows[0] if rows else None)
        if exact:
            for f in ("strCutout", "strThumb", "strRender"):
                if exact.get(f):
                    urls.append(str(exact[f]))
    except Exception:
        STATS["player_tsdb_err"] = STATS.get("player_tsdb_err", 0) + 1
    try:
        r = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "query", "generator": "search", "gsrsearch": f"{name} footballer",
                    "gsrlimit": 1, "prop": "pageimages", "piprop": "thumbnail", "pithumbsize": 400,
                    "format": "json"},
            headers={"User-Agent": "NETRATTLER-cards/1.0 (match card player image)"}, timeout=6)
        for page in (((r.json() or {}).get("query") or {}).get("pages") or {}).values():
            u = str((page.get("thumbnail") or {}).get("source") or "")
            if u:
                urls.append(u)
    except Exception:
        STATS["player_wiki_err"] = STATS.get("player_wiki_err", 0) + 1
    payload = b""
    for u in urls:
        try:
            r = requests.get(u, timeout=8)
            if r.ok and r.content:
                payload = r.content
                break
        except Exception:
            continue
    STATS["player_photo_ok" if payload else "player_photo_missing"] = \
        STATS.get("player_photo_ok" if payload else "player_photo_missing", 0) + 1
    _PLAYER_CACHE[key] = payload
    return payload


def render_scorer_card(tip, target_date, result=None):
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    w, h = 1080, 880
    im = Image.new("RGB", (w, h), "#020a2a")
    draw = ImageDraw.Draw(im)
    fp = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    fb = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    def font(size, bold=False):
        try:
            return ImageFont.truetype(fb if bold else fp, size)
        except OSError:
            return ImageFont.load_default()

    def text_c(text, cx, y, f, fill):
        bb = draw.textbbox((0, 0), text, font=f)
        draw.text((cx - (bb[2] - bb[0]) / 2, y), text, font=f, fill=fill)

    def panel(box, outline="#2d6bff", fill="#06124a", radius=18):
        x0, y0, x1, y1 = box
        draw.rounded_rectangle((x0 - 2, y0 - 2, x1 + 2, y1 + 2), radius=radius + 2, outline="#12307f", width=3)
        draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)

    result = result if isinstance(result, dict) else None
    mark = ((result or {}).get("marks") or {}).get("0")
    for i in range(0, 300, 6):
        draw.line((0, i, w, i), fill=(2, 10 + i // 14, 42 + i // 5))
    match = str(tip.get("match", ""))
    home, away = _teams(match)
    player = str(tip.get("player", ""))
    text_c("NETRATTLER", w / 2, 30, font(62, True), "#ffffff")
    text_c("GOAL HUNTER · ANYTIME GOALSCORER", w / 2, 100, font(20, True), "#9fc2ff")
    draw.rounded_rectangle((300, 132, 780, 166), radius=16, fill="#0b1f6e", outline="#3b82ff", width=2)
    text_c(str(tip.get("league") or "FUSSBALL")[:48], w / 2, 138, font(18, True), "#d6e6ff")
    if result:
        draw.rounded_rectangle((420, 176, 660, 208), radius=14, fill="#1fbf5b")
        text_c("ABGESCHLOSSEN", w / 2, 181, font(17, True), "#ffffff")
    else:
        draw.rounded_rectangle((420, 176, 660, 208), radius=14, fill="#d62839")
        text_c("PRE-KICKOFF", w / 2, 181, font(17, True), "#ffffff")
    _paste_badge(im, draw, home, (50, 150, 220, 320), font(40, True))
    _paste_badge(im, draw, away, (860, 150, 1030, 320), font(40, True))
    text_c(home[:20], 135, 330, font(24, True), "#ffffff")
    text_c(away[:20], 945, 330, font(24, True), "#ffffff")

    # player photo (circle) in the middle
    cx0, cy0, size = 420, 215, 240
    photo = _player_photo(player, str(tip.get("team", "")))
    shown = False
    if photo:
        try:
            ph = Image.open(io.BytesIO(photo)).convert("RGBA")
            ph = ImageOps.fit(ph, (size, size), Image.Resampling.LANCZOS, centering=(0.5, 0.2))
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
            draw.ellipse((cx0 - 5, cy0 - 5, cx0 + size + 5, cy0 + size + 5), fill="#27e0c0")
            im.paste(ph, (cx0, cy0), mask)
            shown = True
        except Exception:
            shown = False
    if not shown:
        draw.ellipse((cx0, cy0, cx0 + size, cy0 + size), fill="#172f50", outline="#27e0c0", width=5)
        ini = "".join(x[:1] for x in re.findall(r"[A-Za-z]+", player)[-2:]).upper() or "?"
        text_c(ini, cx0 + size / 2, cy0 + size / 2 - 40, font(80, True), "#ffffff")

    text_c(player[:26], w / 2, 476, font(46, True), "#ffffff")
    sub = str(tip.get("team") or "")
    if result and result.get("ft"):
        sub = (sub + "  ·  " if sub else "") + "Endstand " + str(result["ft"]).replace("-", " : ")
    if sub:
        text_c(sub[:60], w / 2, 536, font(22, True), "#9fc2ff")

    top = 584
    outline = "#2d6bff"
    if mark == "win":
        outline = "#27e0c0"
    elif mark == "loss":
        outline = "#ff5468"
    panel((34, top, 1046, top + 190), outline=outline)
    odds = _number(tip.get("odds") or tip.get("oddsYes"))
    pct = _pct(tip.get("probability"))
    fair = _number(tip.get("fairOdds") or tip.get("fair_odds"))
    cells = []
    if odds:
        cells.append(("QUOTE", f"{odds:.2f}", "#ffd166"))
    if pct is not None:
        cells.append(("MODEL PROB.", f"{pct:.0f}%", "#27e0c0"))
    if fair:
        cells.append(("FAIR", f"{fair:.2f}", "#ffd166"))
    gpg = _number(tip.get("goals_per_game"))
    if gpg:
        cells.append(("TORE / SPIEL", f"{gpg:.2f}", "#ffffff"))
    cw = 980 / max(len(cells), 1)
    for i, (k, v, col) in enumerate(cells):
        x0 = 50 + i * cw
        draw.rounded_rectangle((x0 + 4, top + 18, x0 + cw - 4, top + 110), radius=12, fill="#0a1c66", outline="#2d6bff", width=1)
        text_c(k, x0 + cw / 2, top + 26, font(15, True), "#9fc2ff")
        text_c(v, x0 + cw / 2, top + 56, font(40, True), col)
    if mark in ("win", "loss"):
        text_c("✔ TORSCHÜTZE – TREFFER" if mark == "win" else "✖ KEIN TOR – KEIN TREFFER", w / 2, top + 128,
               font(32, True), "#27e0c0" if mark == "win" else "#ff5468")
    else:
        text_c("ANYTIME GOALSCORER · Spieler trifft jederzeit", w / 2, top + 134, font(20, True), "#d6e6ff")
    fy = top + 214
    draw.line((60, fy, w - 60, fy), fill="#1f55e8", width=2)
    text_c("NETRATTLER  |  Nur finale, validierte Picks · keine geschätzten Quoten", w / 2, fy + 12, font(16, True), "#9fc2ff")
    final_h = fy + 52
    draw.rounded_rectangle((14, 14, w - 14, final_h - 14), radius=26, outline="#1f55e8", width=3)
    im = im.crop((0, 0, w, final_h))
    data = io.BytesIO()
    im.save(data, format="PNG", optimize=True)
    return data.getvalue()


def send_scorer_card(token, chat, tip, target_date, log=print):
    if os.getenv("ENABLE_SCORER_CARDS", "true").lower() not in ("1", "true", "yes", "on"):
        return False
    if not token or not chat or not _valid(tip) or not tip.get("player"):
        return False
    for t in _teams(tip.get("match", "")):
        if _norm(t) and tip.get("league"):
            _TEAM_LEAGUE.setdefault(_norm(t), str(tip.get("league")))
    try:
        payload = render_scorer_card(tip, target_date)
    except Exception as exc:
        log(f"Scorer-Card übersprungen: {type(exc).__name__}: {str(exc)[:80]}")
        return False
    mid = _send_photo(token, chat, "", payload, log)
    if mid and mid is not True:
        save_card(chat, mid, [("scorer", tip)], target_date, log)
    return bool(mid)


def _crest_cache_load():
    try:
        url, hdr = _sb()
        if not url:
            return
        base = url.replace("netrattler_match_cards", "netrattler_crest_cache")
        r = requests.get(base, headers=hdr, params={"select": "team_key,url", "limit": "5000"}, timeout=15)
        if r.ok:
            n = 0
            for row in r.json():
                if row.get("team_key") and row.get("url") and row["team_key"] not in _LOGO_CACHE:
                    _LOGO_CACHE[row["team_key"]] = row["url"]
                    n += 1
            STATS["crest_cache_loaded"] = n
    except Exception:
        pass


def _crest_cache_save(teams):
    try:
        url, hdr = _sb()
        if not url:
            return
        base = url.replace("netrattler_match_cards", "netrattler_crest_cache")
        rows = []
        for t in teams:
            k = _norm(t)
            u = _LOGO_CACHE.get(k)
            if u and _BADGE_CACHE.get(k):
                rows.append({"team_key": k, "team": t[:80], "url": u})
        if rows:
            h = dict(hdr)
            h["Prefer"] = "resolution=merge-duplicates,return=minimal"
            r = requests.post(base + "?on_conflict=team_key", headers=h, json=rows, timeout=20)
            STATS["crest_cache_saved"] = len(rows) if r.ok else 0
    except Exception:
        pass
