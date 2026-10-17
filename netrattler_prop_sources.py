"""
NETRATTLER — Extra Player-Prop Sources (fault-tolerant fallback chain)
=====================================================================

Ziel: Zusaetzliche Player-Prop-Quellen neben Pinnacle und bet365/SofaScore.
Jede Quelle ist in try/except gekapselt: liefert sie nichts (Block, Timeout,
Strukturaenderung), wird sie uebersprungen und die naechste probiert.

Alle Quellen geben dasselbe normalisierte Dict-Format zurueck, damit sie
direkt in _ntr_collect_prop() / den Builder-Pool wandern koennen:

    {
        "player":   "Lamine Yamal",
        "team":     "",
        "match":    "Spain vs Argentina",
        "league":   "",
        "market":   "Player Shots on Target",
        "category": "sot",
        "line":     1.5,
        "odds":     2.1,
        "source":   "kambi_unibet",
    }

Kein Modul-Import darf den Bot brechen: btts_bot importiert dies in try/except.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore


# ------------------------------------------------------------------
# HTTP-Helfer: nutzt cloudscraper falls vorhanden, sonst requests.
# ------------------------------------------------------------------
_HTTP_SESSION = None

def _session():
    global _HTTP_SESSION
    if _HTTP_SESSION is not None:
        return _HTTP_SESSION
    try:
        import cloudscraper as _cs
        _HTTP_SESSION = _cs.create_scraper()
    except Exception:
        if requests is None:
            return None
        _HTTP_SESSION = requests.Session()
    return _HTTP_SESSION


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


# Measurement before removing the block-evading fallbacks: which fetch path
# actually delivered each JSON response (per host). Written to
# netrattler_card_diag at the end of collect_extra_player_props.
FETCH_PATHS: Dict[str, Dict[str, int]] = {}


def _count_path(url: str, path: str) -> None:
    try:
        from urllib.parse import urlparse as _up
        host = (_up(url).hostname or "?")[:60]
    except Exception:
        host = "?"
    bucket = FETCH_PATHS.setdefault(host, {})
    bucket[path] = bucket.get(path, 0) + 1


# Circuit breaker: a host that answered N times in a row with a hard
# "no" (400/403/404/418) is skipped for the rest of the run instead of being
# hammered once per fixture (footymetrics alone burned 48 failed requests).
_HOST_FAIL_STREAK: Dict[str, int] = {}
_HOST_SKIP_AFTER = 4
_HARD_NO = {400, 403, 404, 418}


def _host_of(url: str) -> str:
    try:
        from urllib.parse import urlparse as _up
        return (_up(url).hostname or "?")[:60]
    except Exception:
        return "?"


def _get_json(url: str, params: Optional[dict] = None, timeout: int = 6):
    """Fast JSON fetch via requests/cloudscraper (no impersonation fallback)."""
    host = _host_of(url)
    if _HOST_FAIL_STREAK.get(host, 0) >= _HOST_SKIP_AFTER:
        _count_path(url, "skipped_after_blocks")
        return None
    sess = _session()
    status = None
    if sess is not None:
        try:
            r = sess.get(url, params=params or {}, headers=_HEADERS, timeout=timeout)
            status = getattr(r, "status_code", None)
            if getattr(r, "ok", False):
                data = r.json()
                _count_path(url, "cloudscraper_ok" if type(sess).__name__ != "Session" else "plain_ok")
                _HOST_FAIL_STREAK[host] = 0
                return data
        except Exception:
            pass
    if status in _HARD_NO or status is None:
        _HOST_FAIL_STREAK[host] = _HOST_FAIL_STREAK.get(host, 0) + 1
    # curl_cffi Chrome impersonation removed 2026-10-17: a 403/429 block is
    # respected, not evaded.
    _count_path(url, f"failed_{status}")
    return None


# ------------------------------------------------------------------
# Gemeinsamer Kategorie-Mapper (quellen-unabhaengig).
# Haelt die Kategorien synchron mit _SHARP_PLAYER_CATS_V31 im Builder.
# ------------------------------------------------------------------
def flip_comma_name(value: str) -> str:
    """'Gregoritsch, Michael' -> 'Michael Gregoritsch' (Kambi lists surname first)."""
    v = str(value or "").strip()
    if "," in v:
        last, _, first = v.partition(",")
        last, first = last.strip(), first.strip()
        if last and first and "," not in first:
            return f"{first} {last}"
    return v


def _norm_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _valid_player_candidate(player: str, home: str, away: str) -> bool:
    """Reject team/generic selections that a sportsbook exposed as player-shaped props."""
    p = _norm_name(player)
    h = _norm_name(home)
    a = _norm_name(away)
    if not p or p in {"over", "under", "yes", "no", "home", "away", "draw", "team", "player"}:
        return False
    if p == h or p == a:
        return False
    if len(p) >= 5 and ((h and p in h) or (a and p in a)):
        return False
    if (len(h) >= 4 and h in p) or (len(a) >= 4 and a in p):
        return False
    try:
        from difflib import SequenceMatcher
        if any(SequenceMatcher(None, p, t).ratio() >= 0.78 for t in (h, a) if t):
            return False
    except Exception:
        pass
    return True


def map_category(text: str) -> str:
    low = str(text or "").lower()
    # Team-/Matchmaerkte zuerst aussortieren.
    if "both teams" in low or "either team" in low or "team to score" in low:
        return "other"
    if ("outside box" in low or "outside the box" in low or "from outside" in low) and (
        "shot on target" in low or "shots on target" in low
    ):
        return "sot_outside_box"
    if "shots on target" in low or "shot on target" in low or "on target" in low:
        return "sot"
    if "headed" in low and "shot" in low:
        return "sot"
    if "shot" in low:
        return "shots"
    if "tackles received" in low or "to be tackled" in low:
        return "tackles_received"
    if "tackle" in low:
        return "tackles_committed"
    if "fouls won" in low or "to be fouled" in low or "fouled" in low:
        return "fouls_won"
    if "foul" in low:
        return "fouls"
    if "booking" in low or "booked" in low or "carded" in low or "card" in low:
        return "yellow_cards"
    if "first goalscorer" in low or "first scorer" in low:
        return "first_scorer"
    if "last goalscorer" in low or "last scorer" in low:
        return "last_scorer"
    if "goalscorer" in low or "to score" in low or "anytime scorer" in low:
        return "score"
    if "assist" in low:
        return "assist"
    if "save" in low:
        return "saves"
    if "offside" in low:
        return "offsides"
    if "pass" in low:
        return "passes"
    return "other"


def _line_from(text: str, default: float = 0.5) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)", str(text or ""))
    return float(m.group(1)) if m else float(default)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _teams_match(cand: str, home: str, away: str) -> bool:
    c = _norm(cand)
    h, a = _norm(home), _norm(away)
    if not c or not h or not a:
        return False
    h_ok = h[:6] in c or c[:6] in h if len(h) >= 4 else h in c
    a_ok = a[:6] in c or c[:6] in a if len(a) >= 4 else a in c
    return bool(h_ok and a_ok)


# ==================================================================
# QUELLE: Kambi (powers Unibet, Betsson, NordicBet, ComeOn, Rizk ...)
#   Oeffentliche offering-API, sauberes JSON, kein Login.
# ==================================================================
_KAMBI_BRANDS = ["ub", "bs", "888", "nb"]  # unibet, betsson, 888sport, nordicbet
_KAMBI_HOSTS = [
    "https://eu-offering-api.kambicdn.com",
    "https://e0-api.kambi.com",
]
_KAMBI_LIST_CACHE: Dict[tuple, Any] = {}
_KAMBI_OFFER_CACHE: Dict[tuple, Any] = {}


def fetch_kambi_player_props(home: str, away: str, brand: str = "ub") -> List[Dict[str, Any]]:
    """Holt Player-Props fuer ein Spiel ueber die Kambi offering-API."""
    props: List[Dict[str, Any]] = []
    event_id = None
    host_used = None
    for host in _KAMBI_HOSTS:
        _lk = (host, brand)
        if _lk not in _KAMBI_LIST_CACHE:
            _KAMBI_LIST_CACHE[_lk] = _get_json(
                f"{host}/offering/v2018/{brand}/listView/football/all/all/all/matches.json",
                params={"lang": "en_GB", "market": "GB"},
            )
        data = _KAMBI_LIST_CACHE.get(_lk)
        if not data:
            continue
        events = data.get("events") or []
        for ev in events:
            e = ev.get("event") or ev
            name = e.get("name") or e.get("englishName") or ""
            home_n = e.get("homeName") or ""
            away_n = e.get("awayName") or ""
            combo = f"{home_n} {away_n}".strip() or name.replace(" - ", " ")
            if _teams_match(combo, home, away):
                event_id = e.get("id")
                host_used = host
                break
        if event_id:
            break
    if not event_id or not host_used:
        return []

    _ok = (host_used, brand, str(event_id))
    if _ok not in _KAMBI_OFFER_CACHE:
        _KAMBI_OFFER_CACHE[_ok] = _get_json(
            f"{host_used}/offering/v2018/{brand}/betoffer/event/{event_id}.json",
            params={"lang": "en_GB", "market": "GB"},
        )
    offer = _KAMBI_OFFER_CACHE.get(_ok)
    if not offer:
        return []

    match_name = f"{home} vs {away}"
    for bo in offer.get("betOffers") or []:
        crit = (bo.get("criterion") or {}).get("label", "")
        offer_type = str((bo.get("betOfferType") or {}).get("name") or "")
        cat = map_category(crit)
        if cat == "score":
            # A generic "Goalscorer" criterion can include *first/last* scorer
            # offers. These carry much larger prices and must never be used
            # as "anytime" scorer quotes; inspect the actual offer subtype.
            descriptor = f"{crit} {offer_type}".lower()
            if re.search(r"\b(first|last|next|opening|2nd|second|third|3rd|half|period|assist)\b|"
                         r"(two or more|three or more|2\+|3\+|hat.trick|own goal)", descriptor):
                continue
            if not re.search(r"any\s*time|to score(?: a goal)?\b", descriptor):
                # Only explicitly identified anytime scorer offers go to live
                # player props. Ambiguous "Goalscorer" stays unavailable.
                continue
        if cat == "other":
            continue
        for oc in bo.get("outcomes") or []:
            player = flip_comma_name(oc.get("participant") or oc.get("label") or "")
            if not player or str(oc.get("label", "")).lower() in {"under", "no"}:
                continue
            try:
                odds = float(oc.get("odds", 0)) / 1000.0  # Kambi: millidds
            except (TypeError, ValueError):
                continue
            if odds <= 1.20:
                continue
            line = oc.get("line")
            line = float(line) / 1000.0 if line else _line_from(oc.get("label", ""), 0.5)
            if not _valid_player_candidate(player, home, away):
                continue
            props.append({
                "player": player, "team": "", "match": match_name, "league": "",
                "market": (f"{crit} | {offer_type}" if cat == "score" and offer_type else crit),
                "category": cat, "line": line, "odds": odds,
                "source": f"kambi_{brand}",
            })
    return props


# ==================================================================
# QUELLE: 1xbet-Familie (Melbet, Megapari, 888starz, Betwinner ...)
#   LineFeed-JSON. Groesste Prop-Tiefe, aber Bot-Schutz auf Single-IP.
# ==================================================================
_1X_HOSTS = ["https://22bet.com", "https://melbet.com", "https://betwinner.com"]  # 1xbet.com itself blocks runners
_1X_LIST_CACHE: Dict[str, Any] = {}
_1X_GAME_CACHE: Dict[tuple, Any] = {}
# 1xbet bet-group IDs fuer Player-Props (aus dem LineFeed-Schema):
_1X_PLAYER_GROUPS = {
    2059: "shots", 2060: "sot", 2061: "fouls", 2062: "tackles",
    2101: "yellow_cards", 15: "score", 2201: "offsides", 2205: "passes",
}


# Evidence collection for the unknown 1xBet group ids (fouls / tackles ...):
# store (G, T, line, odds, player) of the "Players' stats" sub-games. Once the
# matches are over, G/T can be matched against player_game_log to PROVE which
# group is which - no guessing. Bounded: few matches per run, capped rows.
X1_SNAPSHOT: List[Dict[str, Any]] = []
_X1_SNAPSHOT_MATCHES = 6
_X1_SNAPSHOT_MAX_ROWS = 1500


def _snapshot_x1_player_markets(host: str, val: Dict[str, Any], match_name: str) -> None:
    try:
        if len({r["match_name"] for r in X1_SNAPSHOT}) >= _X1_SNAPSHOT_MATCHES and \
                match_name not in {r["match_name"] for r in X1_SNAPSHOT}:
            return
        if len(X1_SNAPSHOT) >= _X1_SNAPSHOT_MAX_ROWS:
            return
        for sg in (val.get("SG") or [])[:60]:
            title = str(sg.get("TG") or sg.get("PN") or "")
            if "players' stats" not in title.lower():
                continue
            sub = _get_json(f"{host}/service-api/LineFeed/GetGameZip",
                            params={"id": sg.get("CI"), "lng": "en", "cfview": 0, "grMode": 4,
                                    "country": 1, "marketType": 1})
            sv = (sub or {}).get("Value") or {}
            for e in (sv.get("E") or []):
                if not isinstance(e, dict):
                    continue
                pl = e.get("PL") or {}
                name = pl.get("N") if isinstance(pl, dict) else None
                if not name or e.get("G") is None or e.get("T") is None:
                    continue
                try:
                    odds = float(e.get("C") or 0)
                except (TypeError, ValueError):
                    continue
                X1_SNAPSHOT.append({
                    "match_name": match_name, "subgame_title": title[:60],
                    "g": int(e["G"]), "t": int(e["T"]),
                    "line": e.get("P") if isinstance(e.get("P"), (int, float)) else None,
                    "odds": odds, "player": str(name)[:80],
                    "side": pl.get("T") if isinstance(pl.get("T"), int) else None,
                })
                if len(X1_SNAPSHOT) >= _X1_SNAPSHOT_MAX_ROWS:
                    return
    except Exception:
        return


def fetch_1xbet_player_props(home: str, away: str) -> List[Dict[str, Any]]:
    """Best-effort Player-Props aus dem 1xbet LineFeed (JSON)."""
    props: List[Dict[str, Any]] = []
    event_id = None
    host_used = None
    for host in _1X_HOSTS:
        if host not in _1X_LIST_CACHE:
            _1X_LIST_CACHE[host] = _get_json(
                f"{host}/service-api/LineFeed/Get1x2_VZip",
                params={"sports": 1, "count": 500, "lng": "en", "mode": 4, "country": 1},
            )
        data = _1X_LIST_CACHE.get(host)
        if not data:
            continue
        for g in (data.get("Value") or []):
            o1 = g.get("O1") or g.get("HomeTeam") or ""
            o2 = g.get("O2") or g.get("AwayTeam") or ""
            if _teams_match(f"{o1} {o2}", home, away):
                event_id = g.get("I") or g.get("CI")
                host_used = host
                break
        if event_id:
            break
    if not event_id or not host_used:
        return []

    _gk = (host_used, str(event_id))
    if _gk not in _1X_GAME_CACHE:
        _1X_GAME_CACHE[_gk] = _get_json(
            f"{host_used}/service-api/LineFeed/GetGameZip",
            params={"id": event_id, "lng": "en", "cfview": 0, "grMode": 4, "country": 1},
        )
    game = _1X_GAME_CACHE.get(_gk)
    if not game:
        return []
    val = game.get("Value") or {}
    match_name = f"{home} vs {away}"
    _snapshot_x1_player_markets(host_used, val, match_name)
    # Player-Props liegen in GE (GroupEvents) / E (Events) mit Spielernamen im PN-Feld.
    for grp in (val.get("GE") or []):
        gid = grp.get("G")
        cat = _1X_PLAYER_GROUPS.get(gid) or map_category(grp.get("GS", ""))
        if cat == "other":
            continue
        for row in (grp.get("E") or []):
            for e in (row if isinstance(row, list) else [row]):
                player = e.get("PN") or e.get("P") or ""
                try:
                    odds = float(e.get("C", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if not player or odds <= 1.20:
                    continue
                line = e.get("P") if isinstance(e.get("P"), (int, float)) else _line_from(e.get("PN", ""), 0.5)
                if not _valid_player_candidate(player, home, away):
                    continue
                props.append({
                    "player": str(player), "team": "", "match": match_name, "league": "",
                    "market": grp.get("GS", cat), "category": cat,
                    "line": float(line or 0.5), "odds": odds, "source": "1xbet",
                })
    return props



def fetch_kambi_match_corners(home: str, away: str, brand: str = "ub") -> List[Dict[str, Any]]:
    """Observed Kambi match-total corner prices for Corner Sniper.

    Reuses the same cached Kambi event/offer payload as player props, so calling
    this after player-prop collection is normally cache-only. No synthetic odds.
    """
    event_id = None
    host_used = None
    for host in _KAMBI_HOSTS:
        _lk = (host, brand)
        if _lk not in _KAMBI_LIST_CACHE:
            _KAMBI_LIST_CACHE[_lk] = _get_json(
                f"{host}/offering/v2018/{brand}/listView/football/all/all/all/matches.json",
                params={"lang": "en_GB", "market": "GB"},
            )
        data = _KAMBI_LIST_CACHE.get(_lk)
        if not data:
            continue
        for ev in data.get("events") or []:
            e = ev.get("event") or ev
            name = e.get("name") or e.get("englishName") or ""
            home_n = e.get("homeName") or ""
            away_n = e.get("awayName") or ""
            combo = f"{home_n} {away_n}".strip() or name.replace(" - ", " ")
            if _teams_match(combo, home, away):
                event_id = e.get("id")
                host_used = host
                break
        if event_id:
            break
    if not event_id or not host_used:
        return []
    _ok = (host_used, brand, str(event_id))
    if _ok not in _KAMBI_OFFER_CACHE:
        _KAMBI_OFFER_CACHE[_ok] = _get_json(
            f"{host_used}/offering/v2018/{brand}/betoffer/event/{event_id}.json",
            params={"lang": "en_GB", "market": "GB"},
        )
    offer = _KAMBI_OFFER_CACHE.get(_ok)
    if not offer:
        return []
    out=[]
    for bo in offer.get("betOffers") or []:
        crit = str((bo.get("criterion") or {}).get("label", ""))
        low = crit.lower()
        # Match-total corners only. Exclude team/player/handicap/1H markets because
        # Corner Sniper's probability model is for full-match total corners.
        if "corner" not in low or any(tok in low for tok in ("team corner", "player corner", "1st half", "first half", "handicap")):
            continue
        for oc in bo.get("outcomes") or []:
            lab = str(oc.get("label") or oc.get("type") or "")
            if not lab.lower().startswith("over"):
                continue
            try:
                odds = float(oc.get("odds", 0) or 0) / 1000.0
                raw_line = oc.get("line")
                line = float(raw_line) / 1000.0 if raw_line not in (None, "", 0) else _line_from(lab, 0.0)
            except (TypeError, ValueError):
                continue
            if odds <= 1.05 or not (6.5 <= line <= 14.5):
                continue
            out.append({"home":home,"away":away,"match":f"{home} vs {away}","line":line,"odds":odds,"source":f"kambi_{brand}"})
    return out



def _extract_kambi_team_specials(offer: Dict[str, Any]) -> Dict[str, float]:
    """Parse observed Kambi special markets from one event offer payload.

    Kambi labels are not identical across brands.  Keep the parser permissive
    on wording but strict on the actual selection: only observed outcome odds
    are returned; no synthetic/multiplied prices are ever created.
    """
    out: Dict[str, float] = {}
    for bo in (offer or {}).get("betOffers") or []:
        crit = str((bo.get("criterion") or {}).get("label", "") or "")
        low = crit.lower().replace("½", "1/2")
        outcomes = bo.get("outcomes") or []
        period = str(bo.get("period") or bo.get("betOfferType", {}).get("name") or "").lower()
        combined_market_text = f"{low} {period}"
        is_first_half = any(t in combined_market_text for t in (
            "1st half", "first half", "1st-half", "first-half", "1h",
            "half time", "halftime", "1. half", "1 half",
        ))
        is_btts = any(t in low for t in (
            "both teams to score", "both teams score", "both to score", "btts",
        ))
        is_combo_criterion = is_btts and any(t in low for t in (
            "total goals", "over/under", "over 2.5", "and total", "& total",
        ))

        for oc in outcomes:
            label = str(oc.get("label") or oc.get("type") or "")
            olow = label.lower().strip()
            try:
                raw_odds = float(oc.get("odds", 0) or 0)
            except (TypeError, ValueError):
                continue
            # Kambi API normally returns milli-decimal (e.g. 1850 -> 1.85),
            # but a few white-label mirrors expose decimal already.
            odds = raw_odds / 1000.0 if raw_odds > 100 else raw_odds
            if odds <= 1.05 or odds > 100.0:
                continue

            raw_line = oc.get("line")
            try:
                line = float(raw_line) / 1000.0 if raw_line not in (None, "", 0) else _line_from(label, 0.0)
            except (TypeError, ValueError):
                line = _line_from(label, 0.0)

            outcome_text = f"{low} {olow}"
            positive_yes = (
                olow in {"yes", "ja"}
                or olow.startswith("yes ")
                or " yes " in f" {olow} "
            )

            # Exact BTTS full-time / first-half Yes.
            if is_btts and not is_combo_criterion and positive_yes:
                key = "btts_yes_ht" if is_first_half else "btts_yes"
                if odds > out.get(key, 0):
                    out[key] = round(odds, 3)

            # Observed BTTS + Over 2.5 combined market only.  Some brands put
            # the 2.5 line in oc.line and label the outcome merely "Yes & Over".
            _has_btts = any(t in outcome_text for t in (
                "both teams to score", "both teams score", "both to score", "btts"
            ))
            _has_over_word = any(t in outcome_text for t in ("over", "2.5 or more", "3 or more"))
            _has_25_text = bool(re.search(r"(?:over|o)\s*2[\.,]5", outcome_text)) or "2.5 or more" in outcome_text
            _has_25_line = abs(line - 2.5) <= 0.11
            _positive_combo = positive_yes or "yes & over" in outcome_text or "yes and over" in outcome_text
            if _has_btts and (_has_25_text or (_has_over_word and _has_25_line)) and _positive_combo:
                if odds > out.get("btts_over25_combo", 0):
                    out["btts_over25_combo"] = round(odds, 3)

            # First-half Over 1.5 goals.  Period can be encoded either in the
            # criterion or in the offer metadata, line either in label or oc.line.
            goal_market = any(t in low for t in (
                "total goals", "goals over/under", "over/under goals", "goals", "total"
            ))
            is_over = olow.startswith("over") or str(oc.get("type") or "").upper() in {"O", "OVER"}
            if is_first_half and goal_market and is_over and abs(line - 1.5) <= 0.11:
                if odds > out.get("over_15_ht", 0):
                    out["over_15_ht"] = round(odds, 3)
    return out


def fetch_kambi_team_specials(home: str, away: str, brand: str = "ub") -> Dict[str, float]:
    """Observed Kambi team/special prices used when Pinnacle specials are blocked.

    Returns only bookmaker-observed prices; it never synthesizes a combo from
    separate markets. Supported keys: btts_yes, btts_yes_ht,
    btts_over25_combo, over_15_ht.
    """
    event_id = None
    host_used = None
    for host in _KAMBI_HOSTS:
        _lk = (host, brand)
        if _lk not in _KAMBI_LIST_CACHE:
            _KAMBI_LIST_CACHE[_lk] = _get_json(
                f"{host}/offering/v2018/{brand}/listView/football/all/all/all/matches.json",
                params={"lang": "en_GB", "market": "GB"},
            )
        data = _KAMBI_LIST_CACHE.get(_lk)
        if not data:
            continue
        for ev in data.get("events") or []:
            e = ev.get("event") or ev
            name = e.get("name") or e.get("englishName") or ""
            home_n = e.get("homeName") or ""
            away_n = e.get("awayName") or ""
            combo = f"{home_n} {away_n}".strip() or name.replace(" - ", " ")
            if _teams_match(combo, home, away):
                event_id = e.get("id")
                host_used = host
                break
        if event_id:
            break
    if not event_id or not host_used:
        return {}

    _ok = (host_used, brand, str(event_id))
    if _ok not in _KAMBI_OFFER_CACHE:
        _KAMBI_OFFER_CACHE[_ok] = _get_json(
            f"{host_used}/offering/v2018/{brand}/betoffer/event/{event_id}.json",
            params={"lang": "en_GB", "market": "GB"},
        )
    offer = _KAMBI_OFFER_CACHE.get(_ok)
    if not offer:
        return {}
    return _extract_kambi_team_specials(offer)

def collect_extra_corner_odds(fixtures: List[Dict[str, str]], log: Optional[Callable[[str], Any]] = None, max_matches: int = 24) -> List[Dict[str, Any]]:
    """Collect observed match-total corner odds from Kambi brands, bounded for runtime."""
    def _log(m):
        if log:
            try: log(m)
            except Exception: pass
    best={}
    checked=0
    matched=set()
    for fx in (fixtures or [])[:max_matches]:
        home=str(fx.get("home","")).strip(); away=str(fx.get("away","")).strip()
        if not home or not away: continue
        checked += 1
        for brand in _KAMBI_BRANDS:
            try: rows=fetch_kambi_match_corners(home,away,brand=brand) or []
            except Exception: rows=[]
            for row in rows:
                key=(_norm_name(home),_norm_name(away),round(float(row.get("line") or 0),2))
                prev=best.get(key)
                if prev is None or float(row.get("odds") or 0) > float(prev.get("odds") or 0):
                    best[key]=row
                matched.add(f"{home} vs {away}")
            if rows:
                break
    out=list(best.values())
    _log(f"   🔵 Extra Corner Odds: {len(out)} Linien · {len(matched)} Matches · {checked} Fixtures geprüft")
    return out

# ==================================================================
# Einheitliche Sammel-Funktion: probiert alle Quellen der Reihe nach.
# ==================================================================
# ==================================================================
# QUELLE: Oddspedia (Aggregator, Player-Props / Spezialmärkte)
#   Oeffentliche JSON-API; aggregiert viele Buchmacher inkl. Player-Props.
# ==================================================================
_ODDSPEDIA_HOSTS = ["https://oddspedia.com", "https://www.oddspedia.com"]
_ODDSPEDIA_LIST_CACHE: Dict[str, Any] = {}
_ODDSPEDIA_ODDS_CACHE: Dict[tuple, Any] = {}


def fetch_oddspedia_player_props(home: str, away: str) -> List[Dict[str, Any]]:
    """Best-effort Player-Props von Oddspedia (Aggregator-JSON)."""
    props: List[Dict[str, Any]] = []
    match_id = None
    host_used = None
    for host in _ODDSPEDIA_HOSTS:
        if host not in _ODDSPEDIA_LIST_CACHE:
            _ODDSPEDIA_LIST_CACHE[host] = _get_json(
                f"{host}/api/v1/getMatchList",
                params={"sport": "football", "type": "upcoming", "language": "en"},
            )
        data = _ODDSPEDIA_LIST_CACHE.get(host)
        if not data:
            continue
        rows = (data.get("data") or {}).get("matchList") or data.get("data") or []
        if isinstance(rows, dict):
            rows = rows.get("matches", [])
        for mt in rows or []:
            name = f"{mt.get('ht','')} {mt.get('at','')}" or mt.get("name", "")
            if _teams_match(name, home, away):
                match_id = mt.get("id") or mt.get("matchId")
                host_used = host
                break
        if match_id:
            break
    if not match_id or not host_used:
        return []

    _mk = (host_used, str(match_id))
    if _mk not in _ODDSPEDIA_ODDS_CACHE:
        _ODDSPEDIA_ODDS_CACHE[_mk] = _get_json(
            f"{host_used}/api/v1/getMatchOdds",
            params={"matchId": match_id, "oddType": "player", "language": "en"},
        )
    offers = _ODDSPEDIA_ODDS_CACHE.get(_mk)
    if not offers:
        return []
    match_name = f"{home} vs {away}"
    market_rows = (offers.get("data") or {}).get("markets") or offers.get("data") or []
    for mk in market_rows if isinstance(market_rows, list) else []:
        label = str(mk.get("name") or mk.get("marketName") or "")
        cat = map_category(label)
        if cat == "other":
            continue
        for oc in mk.get("outcomes") or mk.get("selections") or []:
            player = oc.get("player") or oc.get("participant") or oc.get("name") or ""
            _ll = str(oc.get("handicap") or oc.get("line") or oc.get("label") or "")
            if "under" in _ll.lower() or str(oc.get("name", "")).lower() == "no":
                continue
            try:
                odds = float(oc.get("odds") or oc.get("price") or 0)
            except (TypeError, ValueError):
                continue
            if not player or odds <= 1.20:
                continue
            if not _valid_player_candidate(player, home, away):
                continue
            props.append({
                "player": str(player), "team": "", "match": match_name, "league": "",
                "market": label, "category": cat, "line": _line_from(_ll, 0.5),
                "odds": odds, "source": "oddspedia",
            })
    return props


# ==================================================================
# QUELLE: FootyMetrics (Fussball-Player-Props)
# ==================================================================
_FOOTYMETRICS_HOSTS = ["https://api.footymetrics.com", "https://footymetrics.com"]


def fetch_footymetrics_player_props(home: str, away: str) -> List[Dict[str, Any]]:
    """Best-effort Player-Props von FootyMetrics."""
    props: List[Dict[str, Any]] = []
    for host in _FOOTYMETRICS_HOSTS:
        data = _get_json(
            f"{host}/v1/props",
            params={"home": home, "away": away, "sport": "football"},
        )
        if not data:
            continue
        rows = data.get("props") or data.get("data") or []
        match_name = f"{home} vs {away}"
        for r in rows if isinstance(rows, list) else []:
            label = str(r.get("market") or r.get("type") or "")
            cat = map_category(label)
            if cat == "other":
                continue
            player = r.get("player") or r.get("name") or ""
            side = str(r.get("side") or r.get("selection") or "over").lower()
            if "under" in side or side == "no":
                continue
            try:
                odds = float(r.get("odds") or r.get("price") or 0)
            except (TypeError, ValueError):
                continue
            if not player or odds <= 1.20:
                continue
            if not _valid_player_candidate(player, home, away):
                continue
            props.append({
                "player": str(player), "team": "", "match": match_name, "league": "",
                "market": label, "category": cat,
                "line": _line_from(str(r.get("line", "")), 0.5),
                "odds": odds, "source": "footymetrics",
            })
        if props:
            break
    return props


def collect_extra_player_props(
    fixtures: List[Dict[str, str]],
    log: Optional[Callable[[str], Any]] = None,
    max_matches: int = 60,
) -> List[Dict[str, Any]]:
    """Collect real player props with category-depth first, not raw row count.

    Kambi brands do not expose identical player markets. We therefore merge a few
    brands per selected match and then add 1xbet/Oddspedia/FootyMetrics only when
    they contribute additional categories. Everything is deduped by player+market+line.
    """
    from collections import Counter

    def _log(m):
        if log:
            try:
                log(m)
            except Exception:
                pass

    out_best: Dict[tuple, Dict[str, Any]] = {}
    per_source: Dict[str, int] = {}
    per_cat: Counter = Counter()
    matched_matches = set()

    import threading as _th
    _lock = _th.Lock()

    def _add(rows, home, away, league, source_name):
        with _lock:
            return _add_locked(rows, home, away, league, source_name)

    def _add_locked(rows, home, away, league, source_name):
        added = 0
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            row = dict(row)
            row["league"] = row.get("league") or league or ""
            row["match"] = row.get("match") or f"{home} vs {away}"
            cat = row.get("category") or map_category(row.get("market", ""))
            if cat == "other":
                continue
            row["category"] = cat
            try:
                odds = float(row.get("odds") or 0)
                line = float(row.get("line") or 0.5)
            except (TypeError, ValueError):
                continue
            if odds <= 1.20 or not _valid_player_candidate(row.get("player", ""), home, away):
                continue
            key = (_norm_name(row.get("player", "")), _norm_name(row.get("match", "")), cat, round(line, 2))
            prev = out_best.get(key)
            if prev is None or float(prev.get("odds") or 0) < odds:
                out_best[key] = row
            added += 1
            per_cat[cat] += 1
        if added:
            per_source[source_name] = per_source.get(source_name, 0) + added
            matched_matches.add(f"{home} vs {away}")
        return added

    desired_depth = {"sot", "shots", "fouls", "fouls_won", "tackles_committed", "tackles_received", "yellow_cards", "score", "assist"}

    # Wall-clock budget: a busy Saturday (29+ fixtures) must never push the
    # whole tip run past the workflow timeout and lose every tip.
    import os as _os_b, time as _time_b
    _budget = float(_os_b.environ.get("NETRATTLER_PROP_BUDGET_SEC", "540") or 540)
    _t0 = _time_b.time()

    def _do_fixture(fx):
        if _time_b.time() - _t0 > _budget:
            return
        home = str(fx.get("home", "")).strip()
        away = str(fx.get("away", "")).strip()
        league = str(fx.get("league", "")).strip()
        if not home or not away:
            return

        before_cats = set(per_cat)
        local_cats = set()
        # Kambi market depth differs by brand. Merge brands but stop early once
        # a match already has broad coverage, keeping runtime bounded.
        for brand in _KAMBI_BRANDS:
            try:
                rows = fetch_kambi_player_props(home, away, brand=brand) or []
            except Exception as exc:
                _log(f"   🔌 kambi_{brand} Fehler ({home} vs {away}): {str(exc)[:60]}")
                rows = []
            _add(rows, home, away, league, f"kambi_{brand}")
            local_cats.update((r.get("category") or map_category(r.get("market", ""))) for r in rows if isinstance(r, dict))
            local_cats.discard("other")
            _has_tackle = bool(local_cats & {"tackles_committed", "tackles_received"})
            _has_foul = bool(local_cats & {"fouls", "fouls_won"})
            # Do not stop at the first brand just because it has five categories.
            # The screenshots/user target specifically needs contact markets, and
            # Kambi brands can expose different fouls/tackles menus for the same event.
            if len(local_cats & desired_depth) >= 6 and _has_tackle and _has_foul and len(rows) >= 10:
                break

        # 1xbet is the best chance for tackles/fouls/shots depth, so try it next.
        try:
            rows = fetch_1xbet_player_props(home, away) or []
        except Exception as exc:
            _log(f"   🔌 1xbet Fehler ({home} vs {away}): {str(exc)[:60]}")
            rows = []
        _add(rows, home, away, league, "1xbet")
        local_cats.update((r.get("category") or map_category(r.get("market", ""))) for r in rows if isinstance(r, dict))

        # Aggregator fallbacks only if the match still lacks breadth.
        if len(local_cats & desired_depth) < 5:
            for name, fn in (
                ("oddspedia", fetch_oddspedia_player_props),
                ("footymetrics", fetch_footymetrics_player_props),
            ):
                try:
                    rows = fn(home, away) or []
                except Exception as exc:
                    _log(f"   🔌 {name} Fehler ({home} vs {away}): {str(exc)[:60]}")
                    rows = []
                _add(rows, home, away, league, name)
                local_cats.update((r.get("category") or map_category(r.get("market", ""))) for r in rows if isinstance(r, dict))
    _workers = max(1, int(_os_b.environ.get("NETRATTLER_PROP_WORKERS", "4") or 4))
    _fx_list = list((fixtures or [])[:max_matches])
    if _workers == 1:
        for _fx in _fx_list:
            _do_fixture(_fx)
    else:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=_workers) as _pool:
            list(_pool.map(lambda _f: _do_fixture(_f), _fx_list))
    if _time_b.time() - _t0 > _budget:
        _log(f"   ⏱ Prop-Budget {int(_budget)}s erreicht - Rest uebersprungen")

    # --- Transfermarkt Nationalteam-Kandidaten (kein odds, nur Struktur) ---
    try:
        from netrattler_transfermarkt_props import fetch_transfermarkt_nt_props, is_international_match
        _tm_added = 0
        for fx in (fixtures or [])[:max_matches]:
            home = str(fx.get("home", "")).strip()
            away = str(fx.get("away", "")).strip()
            league = str(fx.get("league", "")).strip()
            if not home or not away:
                continue
            if not is_international_match(league):
                continue
            _tm_rows = fetch_transfermarkt_nt_props(home, away, league=league, log=log)
            for row in _tm_rows:
                cat = row.get("category") or map_category(row.get("market", ""))
                if cat == "other":
                    continue
                row["category"] = cat
                # Nur einfügen wenn noch kein echter Prop für diesen Spieler+Markt existiert
                key = (_norm_name(row.get("player", "")), _norm_name(row.get("match", "")), cat, round(float(row.get("line") or 0.5), 2))
                if key not in out_best:
                    out_best[key] = row
                    _tm_added += 1
                    per_cat[cat] += 1
        if _tm_added:
            _log(f"   🌍 TM-NT: {_tm_added} Nationalteam-Kandidaten hinzugefügt")
    except Exception as _tm_exc:
        _log(f"   🌍 TM-NT: Fehler {str(_tm_exc)[:80]}")

    out = list(out_best.values())
    try:
        import os as _os
        import requests as _rq
        _u = (_os.getenv("SUPABASE_URL") or "").rstrip("/")
        _k = _os.getenv("SUPABASE_SERVICE_ROLE_KEY") or _os.getenv("SUPABASE_KEY") or ""
        if _u and _k:
            _rq.post(f"{_u}/rest/v1/netrattler_card_diag", timeout=8,
                     headers={"apikey": _k, "Authorization": f"Bearer {_k}", "Content-Type": "application/json"},
                     json={"info": {"probe": "prop_fetch_paths", "paths": FETCH_PATHS,
                                    "per_source": per_source, "per_cat": dict(per_cat), "unique": len(out)}})
    except Exception:
        pass
    try:
        if X1_SNAPSHOT:
            import os as _os2
            import requests as _rq2
            _u2 = (_os2.getenv("SUPABASE_URL") or "").rstrip("/")
            _k2 = _os2.getenv("SUPABASE_SERVICE_ROLE_KEY") or _os2.getenv("SUPABASE_KEY") or ""
            if _u2 and _k2:
                _rq2.post(f"{_u2}/rest/v1/x1_player_snapshots", timeout=20,
                          headers={"apikey": _k2, "Authorization": f"Bearer {_k2}",
                                   "Content-Type": "application/json", "Prefer": "return=minimal"},
                          json=list(X1_SNAPSHOT))
    except Exception:
        pass
    if per_source:
        summary = ", ".join(f"{k}={v}" for k, v in sorted(per_source.items()))
        cats = ", ".join(f"{k}={v}" for k, v in per_cat.most_common())
        _log(f"   🔌 Extra-Prop-Quellen: {summary} · unique={len(out)} · matches={len(matched_matches)}")
        _log(f"   🔌 Extra-Prop-Kategorien: {cats}")
    else:
        _log(f"   🔌 Extra-Prop-Quellen: 0 Props aus {min(len(fixtures or []), max_matches)} geprüften Fixtures")
    return out


__all__ = [
    "fetch_kambi_player_props",
    "fetch_kambi_match_corners",
    "fetch_kambi_team_specials",
    "collect_extra_corner_odds",
    "fetch_1xbet_player_props",
    "fetch_oddspedia_player_props",
    "fetch_footymetrics_player_props",
    "collect_extra_player_props",
    "map_category",
    "fetch_transfermarkt_nt_props",
]
