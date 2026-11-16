"""Gegner-Signal (Matchup): erwartete Tore aus Offensive des einen und Defensive des anderen Teams
(match_results, letzte Wochen). Liefert nur einen milden Faktor fuer Over 2.5 / BTTS."""
import os
import re
import unicodedata
from datetime import date, timedelta

DAYS = int(os.getenv("NETRATTLER_MATCHUP_DAYS", "75"))
MIN_GAMES = int(os.getenv("NETRATTLER_MATCHUP_MIN_GAMES", "6"))
_TEAMS = None
_MEAN = None


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\b(fc|cf|sc|ac|afc|real|club|de|the)\b", " ", s)
    return re.sub(r"[^a-z0-9]", "", s)


def aggregate(rows):
    teams, total, n = {}, 0.0, 0
    for r in rows:
        try:
            hs, as_ = float(r["home_score"]), float(r["away_score"])
        except (TypeError, ValueError, KeyError):
            continue
        for team, gf, ga in ((r.get("home_team"), hs, as_), (r.get("away_team"), as_, hs)):
            k = norm(team)
            if not k:
                continue
            t = teams.setdefault(k, [0, 0.0, 0.0])
            t[0] += 1; t[1] += gf; t[2] += ga
        total += hs + as_; n += 1
    mean = total / (2 * n) if n else 0.0
    return {k: (g, gf / g, ga / g) for k, (g, gf, ga) in teams.items() if g >= MIN_GAMES}, mean


def _load(url, key):
    global _TEAMS, _MEAN
    if _TEAMS is not None:
        return
    _TEAMS, _MEAN = {}, 0.0
    if not url or not key:
        return
    try:
        import requests
        since = (date.today() - timedelta(days=DAYS)).isoformat()
        rows, off = [], 0
        while off < 20000:
            r = requests.get(f"{url}/rest/v1/match_results", timeout=20,
                             headers={"apikey": key, "Authorization": f"Bearer {key}"},
                             params={"select": "home_team,away_team,home_score,away_score,source", "match_date": f"gte.{since}",
                                     "limit": 1000, "offset": off})
            if not r.ok:
                break
            b = r.json(); rows += b
            if len(b) < 1000:
                break
            off += 1000
        seen, uniq = set(), []
        for x in rows:  # gleiche Partie aus mehreren Quellen nur einmal
            k = (norm(x.get("home_team")), norm(x.get("away_team")), x.get("home_score"), x.get("away_score"))
            if k not in seen:
                seen.add(k); uniq.append(x)
        _TEAMS, _MEAN = aggregate(uniq)
    except Exception:
        pass


def _find(name):
    k = norm(name)
    if k in _TEAMS:
        return _TEAMS[k]
    hits = [v for t, v in _TEAMS.items() if len(k) >= 5 and len(t) >= 5 and (k in t or t in k)]
    return hits[0] if len(hits) == 1 else None


def factor_from(h, a, mean, market):
    if not h or not a or mean <= 0:
        return 1.0
    clamp = lambda v, lo, hi: max(lo, min(hi, v))
    rh, ra = (h[1] + a[2]) / 2 / mean, (a[1] + h[2]) / 2 / mean  # erwartete Tore je Seite relativ zum Schnitt
    if market == "over25":
        return clamp(1 + 0.6 * ((rh + ra) / 2 - 1), 0.85, 1.08)
    if market == "btts":
        return clamp(1 + 0.4 * (min(rh, ra) - 1), 0.85, 1.06)
    return 1.0


def matchup_factor(url, key, market, match):
    if market not in ("over25", "btts") or " vs " not in str(match):
        return 1.0
    _load(url, key)
    home, away = str(match).split(" vs ", 1)
    return factor_from(_find(home), _find(away), _MEAN, market)
