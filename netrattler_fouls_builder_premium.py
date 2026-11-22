"""NETRATTLER AI – same-match Fouls Builder with real-ticket release gate.

Bookmaker quote input must come from a trusted, observed bookmaker ticket,
NOT a screenshot, multiplied single quotes, fair odds, or estimated payout.
This module never sends Telegram and never fabricates a joint probability.
All player/fixture/lineup matches deliberately fail closed.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import math
import re
import unicodedata
from netrattler_foul_props import same_team

_ALLOWED = {"fouls_committed": "fouls", "fouls_won": "fouls_won"}
_MARKET = {"fouls_committed": "Fouls begangen",
           "fouls_won": "Fouls erlitten"}
_BAD_BOOKS = {"model", "calculated", "estimated", "synthetic", "unknown", "demo"}
MIN_GAMES = 15
MAX_QUOTE_AGE = timedelta(minutes=20)


def _key(value):
    txt = unicodedata.normalize("NFKD", str(value or "")).casefold()
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", txt))


def _time(value):
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid_utc_time") from exc
    else:
        raise ValueError("missing_utc_time")
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timezone_required")
    return dt.astimezone(timezone.utc)


def _ident(value, field):
    if type(value) is not int or value < 1:
        raise ValueError(field + "_invalid")
    return value


def _count(value):
    if type(value) is not int or not 0 <= value <= 30:
        raise ValueError("invalid_observed_foul_count")
    return value


def _fixture(fixture, now):
    if not isinstance(fixture, dict):
        raise ValueError("verified_fixture_required")
    event = _ident(fixture.get("fixture_id"), "fixture_id")
    home_id = _ident(fixture.get("home_team_id"), "home_team_id")
    away_id = _ident(fixture.get("away_team_id"), "away_team_id")
    home, away = (str(fixture.get(x) or "").strip() for x in ("home", "away"))
    if home_id == away_id or not home or not away or _key(home) == _key(away):
        raise ValueError("ambiguous_fixture_identity")
    if fixture.get("status") != "NS":
        raise ValueError("fixture_already_started")
    kickoff = _time(fixture.get("kickoff"))
    if not now < kickoff <= now + timedelta(hours=3):
        raise ValueError("fixture_not_in_verified_prematch_window")
    if not str(fixture.get("league") or "").strip():
        raise ValueError("missing_verified_league")
    return event, home_id, away_id, home, away, kickoff


def _lineup(fixture, lineup, now):
    event, hid, aid, home, away, kickoff = _fixture(fixture, now)
    if not isinstance(lineup, dict) or lineup.get("confirmed") is not True:
        raise ValueError("confirmed_starting_eleven_required")
    if lineup.get("source") not in ("api_football", "official_club"):
        raise ValueError("unsupported_lineup_provenance")
    if lineup.get("fixture_id") != event:
        raise ValueError("wrong_lineup_fixture")
    confirmed_at = _time(lineup.get("confirmed_at"))
    if not now - timedelta(hours=2) <= confirmed_at <= now:
        raise ValueError("stale_or_future_lineup")
    roster = {}
    for side, expected in (("home", hid), ("away", aid)):
        data = lineup.get(side)
        if not isinstance(data, dict) or data.get("team_id") != expected:
            raise ValueError("lineup_team_identity_mismatch")
        starters = data.get("starters")
        if not isinstance(starters, list) or len(starters) != 11:
            raise ValueError("incomplete_starting_eleven")
        names = [_key(name) for name in starters]
        if not all(names) or len(set(names)) != 11:
            raise ValueError("ambiguous_starting_eleven")
        roster[expected] = set(names)
    if roster[hid] & roster[aid]:
        raise ValueError("player_on_both_teams")
    return roster



def lineup_from_api_football(fixture, provider_lineups, *, observed_at):
    """Parse actual /fixtures/lineups response with exact provider team IDs.

    Never flatten two teams' starters into one name list; that would permit
    a player to be assigned to the wrong side of the game.
    """
    when = _time(observed_at)
    event, hid, aid, home, away, kickoff = _fixture(fixture, when)
    if not isinstance(provider_lineups, list) or len(provider_lineups) != 2:
        raise ValueError("two_verified_provider_lineups_required")
    result = {
        "fixture_id": event, "confirmed": True, "source": "api_football",
        "confirmed_at": when.isoformat(),
    }
    found = set()
    for entry in provider_lineups:
        if not isinstance(entry, dict):
            raise ValueError("malformed_provider_lineup")
        team = entry.get("team") or {}
        if not isinstance(team, dict):
            raise ValueError("malformed_provider_team")
        tid = team.get("id")
        side = "home" if tid == hid else "away" if tid == aid else None
        if side is None or tid in found:
            raise ValueError("provider_team_does_not_match_fixture")
        found.add(tid)
        raw = entry.get("startXI")
        if not isinstance(raw, list) or len(raw) != 11:
            raise ValueError("incomplete_starting_eleven")
        names = []
        for item in raw:
            if not isinstance(item, dict) or not isinstance(item.get("player"), dict):
                raise ValueError("invalid_provider_starter")
            player = item["player"]
            if type(player.get("id")) is not int or player["id"] < 1:
                raise ValueError("missing_provider_player_identity")
            names.append(str(player.get("name") or "").strip())
        result[side] = {"team_id": tid, "starters": names}
    _lineup(fixture, result, when)
    return result

def _history(profile, market, threshold):
    if not isinstance(profile, dict) or profile.get("source") != "foul_profile":
        raise ValueError("unverified_player_history")
    if profile.get("history_order") != "latest_first":
        raise ValueError("history_order_unverified")
    series = profile.get(_ALLOWED[market])
    if not isinstance(series, list) or len(series) < MIN_GAMES:
        raise ValueError("l15_history_missing")
    values = [_count(x) for x in series[:MIN_GAMES]]
    last10 = values[:10]
    minutes = profile.get("minutes_series")
    per90 = None
    if isinstance(minutes, list) and len(minutes) >= MIN_GAMES:
        m = minutes[:MIN_GAMES]
        if all(type(v) in (int, float) and math.isfinite(v)
               and 0 < v <= 130 for v in m):
            total = sum(m)
            if total / MIN_GAMES >= 55:
                per90 = round(sum(values) * 90 / total, 2)
    return {
        "L5": sum(v >= threshold for v in values[:5]),
        "L10": sum(v >= threshold for v in last10),
        "L15": sum(v >= threshold for v in values),
        "last10_games": 10,
        "last15_games": 15,
        "average_l15": round(sum(values) / 15, 2),
        "per90_l15": per90,
        "market": market,
        "threshold": threshold,
    }


def _profile_for(leg, profiles, fixture):
    player = _key(leg.get("player"))
    team_id = leg.get("team_id")
    if not player or len(player.split()) < 2:
        raise ValueError("player_full_name_required")
    home_id, away_id = fixture["home_team_id"], fixture["away_team_id"]
    side = "home" if team_id == home_id else "away" if team_id == away_id else None
    if side is None:
        raise ValueError("player_belongs_to_another_fixture")
    name = fixture[side]
    expected_match = _key(fixture["home"] + " vs " + fixture["away"])
    matches = [p for p in profiles if
               isinstance(p, dict)
               and _key(p.get("player")) == player
               and _key(p.get("match")) == expected_match
               and same_team(p.get("team"), name)]
    if len(matches) != 1:
        raise ValueError("player_history_or_fixture_ambiguous")
    return matches[0]


def _check_leg(leg, lineup, fixture, profiles):
    if not isinstance(leg, dict):
        raise ValueError("bookmaker_leg_missing")
    market = leg.get("market")
    if market not in _ALLOWED:
        raise ValueError("foul_market_semantics_unverified")
    threshold = leg.get("threshold")
    if type(threshold) is not int or threshold not in (2, 3, 4):
        raise ValueError("unsupported_foul_line")
    team_id = leg.get("team_id")
    if team_id not in lineup:
        raise ValueError("player_belongs_to_another_fixture")
    key = _key(leg.get("player"))
    if key not in lineup[team_id]:
        raise ValueError("player_not_in_confirmed_team_lineup")
    if not str(leg.get("selection_id") or "").strip():
        raise ValueError("missing_bookmaker_leg_selection_id")
    profile = _profile_for(leg, profiles, fixture)
    form = _history(profile, market, threshold)
    if form["L10"] < 3 or form["L15"] < 4:
        raise ValueError("weak_l10_l15_foul_evidence")
    side = "home" if team_id == fixture["home_team_id"] else "away"
    return {
        "player": str(leg["player"]).strip(),
        "team": fixture[side],
        "team_id": team_id,
        "selection_id": str(leg["selection_id"]).strip(),
        "market": market,
        "market_label": _MARKET[market],
        "threshold": threshold,
        **form,
    }


def prepare_quoted_builder(fixture, lineup, profiles, quote, *, now=None):
    """Return only a ticket-backed, data-valid builder; no Telegram action.

    One bookmaker offer must contain all legs and a genuine *combined*
    decimal price. Per-leg odds or multiplication are not accepted.
    This is a metadata/consistency gate: it does NOT itself contact a
    bookmaker or independently attest that the provider's claim is true.
    """
    now = _time(now or datetime.now(timezone.utc))
    event, home_id, away_id, home, away, kickoff = _fixture(fixture, now)
    roster = _lineup(fixture, lineup, now)
    if not isinstance(quote, dict) or quote.get("observed") is not True:
        raise ValueError("unobserved_combined_bookmaker_quote")
    if quote.get("quote_source") != "bookmaker_direct":
        raise ValueError("bookmaker_api_ticket_required")
    bookmaker = str(quote.get("bookmaker") or "").strip()
    if not bookmaker or _key(bookmaker) in _BAD_BOOKS:
        raise ValueError("actual_bookmaker_required")
    quote_id = str(quote.get("quote_id") or "").strip()
    if not quote_id:
        raise ValueError("combined_bookmaker_ticket_id_required")
    if (quote.get("fixture_id") != event
            or quote.get("home_team_id") != home_id
            or quote.get("away_team_id") != away_id):
        raise ValueError("bookmaker_ticket_fixture_mismatch")
    observed_at = _time(quote.get("observed_at"))
    if not now - MAX_QUOTE_AGE <= observed_at <= now or observed_at >= kickoff:
        raise ValueError("stale_or_future_bookmaker_quote")
    price = quote.get("combined_decimal_odds")
    if type(price) not in (int, float) or not math.isfinite(price) or not 1.01 < price <= 5000:
        raise ValueError("invalid_observed_combined_decimal_odds")
    legs = quote.get("legs")
    if not isinstance(legs, list) or not 3 <= len(legs) <= 6:
        raise ValueError("fouls_builder_requires_3_to_6_legs")
    if not isinstance(profiles, list):
        raise ValueError("verified_profiles_required")
    checked = [_check_leg(leg, roster, fixture, profiles) for leg in legs]
    names = [_key(x["player"]) for x in checked]
    selections = [x["selection_id"] for x in checked]
    if len(set(names)) != len(names) or len(set(selections)) != len(selections):
        raise ValueError("duplicate_player_or_selection")
    if {x["market"] for x in checked} != set(_ALLOWED):
        raise ValueError("both_foul_directions_required")
    return {
        "type": "same_match_fouls_builder",
        "fixture_id": event,
        "match": home + " vs " + away,
        "league": fixture["league"],
        "kickoff": kickoff.isoformat(),
        "lineup_verified": True,
        "legs": checked,
        "legs_count": len(checked),
        "bookmaker": bookmaker,
        "combined_quote_id": quote_id,
        "combined_odds_observed": True,
        "combined_decimal_odds": float(price),
        "combined_implied_probability": round(100 / price, 3),
        "combined_model_probability": None,
        "combined_model_edge": None,
        "joint_model_calibrated": False,
        "stake_units": 1,
        "published": False,
        "render_status": "OWNER_FOULS_ORIGINAL_REQUIRED",
        "quote_observed_at": observed_at.isoformat(),
    }
