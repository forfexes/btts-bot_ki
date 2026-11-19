"""Strict preflight for NETRATTLER screenshot-style image cards.

No fictitious photographs, club badges, kickoff times, player form, or
bookmaker-combination prices. Runs before Telegram to avoid sending a partial
visual. Read-only metadata lookups; no extra Supabase tables or writes.
"""
from __future__ import annotations

import copy
import datetime as dt
import io
import os
import re
import unicodedata
from dataclasses import replace, is_dataclass
from functools import lru_cache

import requests
from PIL import Image


def strict_enabled():
    return os.getenv("NETRATTLER_STRICT_VISUAL_CARDS", "1").lower() not in ("0", "false", "off", "no")


def clean(value):
    s = unicodedata.normalize("NFKD", str(value or "").casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", s)


def club_same(a, b):
    aliases = {
        "athleticopr": "athleticoparanaense",
        "atleticopr": "athleticoparanaense",
        "atleticoparanaense": "athleticoparanaense",
        "athleticoparanaense": "athleticoparanaense",
        "chapecoensesc": "chapecoense",
    }
    a, b = clean(a), clean(b)
    a, b = aliases.get(a, a), aliases.get(b, b)
    if not a or not b or len(a) < 4 or len(b) < 4:
        return False
    if a == b:
        return True
    # Suffix variants are common in source odds (e.g. "Chapecoense-sc").
    suffixes = ("fc", "sc", "afc", "cf", "pr")
    variants = lambda s: {s} | {s[:-len(x)] for x in suffixes if s.endswith(x) and len(s) >= len(x) + 4}
    return bool(variants(a) & variants(b))


def _match_teams(match):
    from netrattler_stats_match_cards import _teams
    home, away = _teams(match)
    return home, away


def _credentials():
    return ((os.getenv("SUPABASE_PLAYERS_URL") or os.getenv("SUPABASE_URL") or "").rstrip("/"),
            os.getenv("SUPABASE_PLAYERS_SERVICE_KEY") or
            os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or "")


@lru_cache(maxsize=300)
def club_for_player(name, match, day):
    home, away = _match_teams(match)
    if not (name and home and away and day):
        return ""
    url, key = _credentials()
    if not (url.startswith("https://") and key):
        return ""
    try:
        r = requests.get(
            url + "/rest/v1/player_game_log",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            params={"select": "player_name,team,match_date", "player_name": "eq." + name,
                    "match_date": "lt." + day[:10], "order": "match_date.desc", "limit": "40"},
            timeout=6)
        if not r.ok:
            return ""
        rows = r.json()
        if not isinstance(rows, list):
            return ""
        teams = {str(row.get("team") or "") for row in rows
                 if isinstance(row, dict) and clean(row.get("player_name")) == clean(name)
                 and any(club_same(row.get("team"), side) for side in (home, away))}
        # Retain the exact stored team spelling for strict L15 photo/stat lookup.
        return next(iter(teams)) if len(teams) == 1 else ""
    except (requests.RequestException, ValueError, TypeError):
        return ""


def _iso_future(value, match_date):
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        stamp = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            return ""
        if stamp.astimezone(dt.timezone.utc).date().isoformat() < str(match_date)[:10]:
            return ""
        return stamp.isoformat()
    except (ValueError, OverflowError, TypeError):
        return ""


@lru_cache(maxsize=3)
def _day_fixtures(day):
    """At most one bounded date request per process; only confirmed provider dates."""
    keys = (os.getenv("API_FOOTBALL_KEYS") or "").replace("\n", ",").split(",")
    keys = [k.strip() for k in keys if k.strip()]
    if not keys:
        return ()
    try:
        response = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers={"x-apisports-key": keys[0]},
            params={"date": day}, timeout=9)
        data = response.json() if response.ok else {}
        if not isinstance(data, dict) or data.get("errors"):
            print(f"[builder-diag] fixtures_api_errors={str(data.get('errors'))[:200] if isinstance(data, dict) else data!r}", flush=True)
            return ()
        rows = data.get("response")
        return tuple(rows[:500]) if isinstance(rows, list) else ()
    except (requests.RequestException, ValueError, TypeError):
        return ()


def kickoff_for_match(match, day):
    home, away = _match_teams(match)
    if not (home and away and day):
        return ""
    possibilities = []
    rows_all = _day_fixtures(day[:10])
    print(f"[builder-diag] day={day[:10]} fixtures={len(rows_all)} match={match!r}", flush=True)
    for x in rows_all:
        if not isinstance(x, dict):
            continue
        teams = x.get("teams") or {}
        h = (teams.get("home") or {}).get("name")
        a = (teams.get("away") or {}).get("name")
        if not (club_same(home, h) and club_same(away, a)):
            if club_same(home, h) or club_same(away, a):
                print(f"[builder-diag] partial_match api={h!r} vs {a!r} wanted={home!r} vs {away!r}", flush=True)
            continue
        fixture = x.get("fixture") or {}
        stamp = _iso_future(fixture.get("date"), day)
        if stamp:
            possibilities.append(stamp)
    return possibilities[0] if len(set(possibilities)) == 1 else ""


def _picture_ok(payload):
    if not isinstance(payload, bytes) or len(payload) < 150:
        return False
    try:
        with Image.open(io.BytesIO(payload)) as im:
            im.verify()
        with Image.open(io.BytesIO(payload)) as im:
            return im.width >= 60 and im.height >= 60
    except (ValueError, OSError, TypeError):
        return False


def _with(leg, **kwargs):
    if is_dataclass(leg):
        return replace(leg, **kwargs)
    cp = copy.copy(leg)
    for key, value in kwargs.items():
        setattr(cp, key, value)
    return cp


def validate_builder(pick):
    """Return (prepared_pick, reasons); reasons!=[] means no photo send."""
    if not strict_enabled():
        return pick, []
    import netrattler_neon_design as neon
    import netrattler_builder_engine as engine
    import netrattler_stats_match_cards as cards

    legs = list(getattr(pick, "legs", []) or [])
    if not (2 <= len(legs) <= 6):
        return None, ["invalid_leg_count"]

    day = str(getattr(pick, "match_date", "") or "")[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        return None, ["missing_date"]
    # Combined price: a verified bookmaker price is used when present. Otherwise
    # the card shows the product of the REAL single-leg quotes (clearly labelled
    # "Einzelquoten ×", no EV claimed). Estimated/unsourced legs are rejected.
    combined = neon._number(getattr(pick, "combined_bookmaker_quote", None))
    verified_combo = bool(getattr(pick, "combined_quote_verified", False) and
                          combined is not None and 1.01 < combined <= 100000)
    if not verified_combo:
        if getattr(pick, "estimated_odds", False) or getattr(pick, "model_only", False):
            return None, ["missing_real_leg_quotes"]
        for leg in legs:
            q = neon._number(getattr(leg, "odds", None))
            if (q is None or not 1.01 <= q <= 1000 or getattr(leg, "estimated", False) or
                    not str(getattr(leg, "source", "") or "").strip()):
                return None, ["missing_real_leg_quotes"]

    reasons, fixed = set(), []
    for leg in legs:
        match, player = str(getattr(leg, "match", "") or ""), str(getattr(leg, "player", "") or "")
        h, a = _match_teams(match)
        club = str(getattr(leg, "team", "") or "")
        if not club or not (club_same(club, h) or club_same(club, a)):
            club = club_for_player(player, match, day)
        if not club:
            reasons.add("missing_verified_team")
            print(f"[builder-diag] team_missing player={player!r} match={match!r}", flush=True)
            continue
        kickoff = _iso_future(getattr(leg, "kickoff", ""), day) or kickoff_for_match(match, day)
        if not kickoff:
            reasons.add("missing_confirmed_kickoff")
            print(f"[builder-diag] kickoff_missing player={player!r} club={club!r} match={match!r}", flush=True)
            continue
        updated = _with(leg, team=club, kickoff=kickoff)
        series = neon._stat_series(updated, engine, day)
        if len(series) < 5:
            reasons.add("missing_measured_history")
        # Explicit images rather than any generic initials/FC fallback.
        if not _picture_ok(cards._player_photo(player, club)):
            reasons.add("missing_verified_photo")
            print(f"[builder-diag] photo_missing player={player!r} club={club!r}", flush=True)
        if not _picture_ok(cards._badge_bytes(club)):
            reasons.add("missing_verified_crest")
            print(f"[builder-diag] crest_missing club={club!r} url={cards._logo_url(club)!r}", flush=True)
        book_quote = neon._number(getattr(leg, "odds", None))
        if (book_quote is None or book_quote <= 1.01 or
            getattr(leg, "estimated", False) or not getattr(leg, "source", None)):
            reasons.add("missing_real_leg_price")
        fixed.append(updated)
    if len(fixed) != len(legs):
        reasons.add("incomplete_player_identity")
    if len(fixed) == len(legs):
        probabilities = [getattr(x, "probability", None) for x in fixed]
        try:
            import math
            ps = [float(v) for v in probabilities]
            if not all(0.01 <= v <= 0.99 for v in ps):
                reasons.add("missing_valid_model_probability")
            else:
                # Independently modelled leg estimates; do not claim a verified
                # correlation-adjusted number without an empirical pair model.
                model_joint = math.prod(ps)
        except (TypeError, ValueError, OverflowError):
            reasons.add("missing_valid_model_probability")
    if reasons:
        return None, sorted(reasons)
    prepared = copy.copy(pick)
    prepared.legs = fixed
    prepared.joint_probability = model_joint
    # Only label high confidence from verified sample depth *and* all leg
    # quality scores; do not promote an uncertain selection to HIGH.
    q = [getattr(x, "quality", None) for x in fixed]
    try:
        qs = [float(v) for v in q]
    except (TypeError, ValueError):
        qs = []
    prepared.confidence = ("HOCH" if len(qs) == len(fixed) and min(qs) >= 0.70
                           else "MITTEL" if len(qs) == len(fixed) and min(qs) >= 0.55
                           else "NIEDRIG")
    return prepared, []


def enrich_scorer(tip, day):
    """Display-only scorer context from observed games; no fabricated averages."""
    from netrattler_neon_design import _observed_game_log, _number
    row = dict(tip)
    player = str(row.get("player") or "").strip()
    team = str(row.get("team") or "").strip()
    if not team:
        team = club_for_player(player, str(row.get("match") or ""), str(day or "")[:10])
        if team:
            row["team"] = team
    gpg = _number(row.get("goals_per_game"))
    if team and (gpg is None or gpg < 0):
        measured = _observed_game_log(player, team, "score", str(day or "")[:10])
        if len(measured) >= 10:
            row["goals_per_game"] = round(sum(measured) / len(measured), 2)
            row["goals_per_game_sample"] = len(measured)
    # Only an offset-aware, verified fixture timestamp may appear on the card.
    # Prefer original source metadata; use a uniquely matched fixture as fallback.
    match_day = str(day or "")[:10]
    kickoff = ""
    for field in ("_kickoff", "kickoff", "kickoff_utc", "fixture_kickoff",
                  "start_time", "commence_time"):
        kickoff = _iso_future(row.get(field), match_day)
        if kickoff:
            break
    if not kickoff:
        kickoff = kickoff_for_match(str(row.get("match") or ""), match_day)
    if kickoff:
        row["_kickoff"] = kickoff  # Also persisted by save_card for result edits.
    else:
        row.pop("_kickoff", None)  # Never reuse an unverified time.
    return row


def validate_scorer(tip, day):
    if not strict_enabled():
        return []
    import netrattler_stats_match_cards as cards
    name, team = str(tip.get("player") or ""), str(tip.get("team") or "")
    home, away = _match_teams(tip.get("match", ""))
    reasons = []
    if not _iso_future(tip.get("_kickoff"), str(day or "")[:10]):
        reasons.append("missing_confirmed_kickoff")
    if not name or not team or not (club_same(team, home) or club_same(team, away)):
        reasons.append("unverified_scorer_team")
    if not (_picture_ok(cards._player_photo(name, team))):
        reasons.append("missing_scorer_photo")
    if any(not _picture_ok(cards._badge_bytes(s)) for s in (home, away)):
        reasons.append("missing_scorer_crest")
    odds = cards._price(tip)
    prob = cards._pct(tip.get("probability"))
    source = str(tip.get("_source") or tip.get("source") or
                 tip.get("bookmaker") or tip.get("odds_source") or "").strip()
    if odds is None or prob is None:
        reasons.append("missing_scorer_odds_or_probability")
    else:
        from netrattler_scorer_qualification import qualifies
        approved, why = qualifies(odds, prob, source)
        if not approved:
            reasons.append("scorer_quote_gate_" + why)
        fair = cards._number(tip.get("fairOdds") if tip.get("fairOdds") is not None
                             else tip.get("fair_odds"))
        if fair is not None and (fair <= 0 or abs(fair - 100.0 / prob) > 0.10):
            reasons.append("inconsistent_scorer_fair_odds")
    if (tip.get("_synthetic") or tip.get("synthetic") or
            tip.get("estimated_odds") or tip.get("_no_real_odds") or
            source.lower() in ("test", "test_only", "demo", "synthetic")):
        reasons.append("unverified_scorer_quote_origin")
    gpg = cards._number(tip.get("goals_per_game"))
    if gpg is None or gpg < 0:
        reasons.append("missing_scorer_goals_per_game")
    elif name and team:
        # A supplied rate must agree with actual pre-kickoff player logs when
        # there are enough observations; never trust an unexplained 0.30/0.40.
        from netrattler_neon_design import _observed_game_log
        measured = _observed_game_log(name, team, "score", str(day or "")[:10])
        if len(measured) >= 10:
            actual = sum(measured) / len(measured)
            if abs(actual - gpg) > 0.025:
                reasons.append("inconsistent_scorer_goals_per_game")
    return reasons
