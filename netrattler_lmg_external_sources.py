"""Read-only Goal Hunter extra-source discovery, opt-in and fail-closed.

Documented endpoints only. No scraping, Telegram sends, odds, Supabase writes,
or source-ID substitution. No automatic booking of API quotas. Use a provider
key in GitHub Actions secrets, not in this repository. Enabled providers are
used only for cross-source coverage audits and SQLite shadow snapshots.
"""
from __future__ import annotations

import datetime as dt
import os
import re
from typing import Any

import requests

import netrattler_lmg_fotmob as fotmob

SOURCE_URLS = {
    "sportmonks": "https://api.sportmonks.com/v3/football/livescores/inplay",
    "highlightly": "https://soccer.highlightly.net/matches",
    "pitchapi": "https://api.pitchapi.dev/v1/date/",
    "sportscore": "https://sportscore.com/api/widget/matches/",
}
# In particular, SportScore requires visible attribution; no deployment by
# default until the user has arranged a compliant display/licence.
SUPPORTED = frozenset(SOURCE_URLS)


def _minute(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    m = re.fullmatch(r"\s*(\d{1,3})(?:['’:]?\d{0,2})?\s*", str(value))
    if not m:
        return None
    n = int(m.group(1))
    return n if 0 <= n <= 130 else None


def _score(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, str):
        return None
    m = re.fullmatch(r"\s*(\d{1,2})\s*[-:]\s*(\d{1,2})\s*", value)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _nonnegative(value: Any) -> int | None:
    if type(value) is not int or not 0 <= value <= 99:
        return None
    return value


def _kickoff(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        result = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if result.tzinfo is None:
        return None  # never guess the timezone of a provider timestamp
    return result.astimezone(dt.timezone.utc)


def _fixture(provider: str, eid: Any, home: Any, away: Any, kickoff: Any,
             hg: Any, ag: Any, minute: Any, league: Any = "") -> dict | None:
    minute = _minute(minute)
    at = _kickoff(kickoff)
    if (not str(eid or "").strip() or type(eid) is bool or
            not isinstance(home, str) or not home.strip() or
            not isinstance(away, str) or not away.strip() or
            fotmob._club_name(home) == fotmob._club_name(away) or
            at is None or minute is None or not 60 <= minute <= 85):
        return None
    h, a = _nonnegative(hg), _nonnegative(ag)
    if h is None or a is None:
        return None
    return {"source": provider, "source_fixture_id": str(eid),
            "home": home.strip(), "away": away.strip(), "kickoff": at,
            "hg": h, "ag": a, "minute": minute, "league": str(league or "").strip()}


def parse_highlightly(body: Any) -> list[dict]:
    matches = body.get("data") if isinstance(body, dict) else None
    if not isinstance(matches, list):
        return []
    result = []
    for row in matches:
        if not isinstance(row, dict):
            continue
        state = row.get("state") or {}
        if not isinstance(state, dict) or str(state.get("description") or "").casefold() != "second half":
            continue
        score = _score((state.get("score") or {}).get("current"))
        if score is None:
            continue
        home, away, league = (row.get("homeTeam") or {}), (row.get("awayTeam") or {}), (row.get("league") or {})
        fixture = _fixture("highlightly",row.get("id"),home.get("name"),away.get("name"),
                           row.get("date"),*score,state.get("clock"),league.get("name"))
        if fixture:
            result.append(fixture)
    return result


def parse_sportscore(body: Any) -> list[dict]:
    """SportScore *documented* widget match format (verified 2026-11-23).

    The live+recent response exposes home, away, home_score, away_score,
    competition, status, status_text, time and url. It does NOT include an
    event id or a verified fixture minute field. Only trust a numeric minute
    explicitly present in status_text and an ISO timezone-aware kickoff in
    time. Everything else remains unpaired, read-only discovery evidence.
    """
    from urllib.parse import urlparse
    rows = body.get("matches") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "").casefold() not in {"live", "in_play", "second_half"}:
            continue
        home,away = row.get("home"),row.get("away")
        hs,as_ = row.get("home_score"),row.get("away_score")
        # The public widget returns scores as strings; only integer decimal
        # strings or true integers are accepted. No guessing from "–".
        def goals(v):
            if type(v) is int and 0 <= v <= 99:
                return v
            if isinstance(v,str) and re.fullmatch(r"\d{1,2}",v.strip()):
                return int(v.strip())
            return None
        slug=row.get("url")
        if not isinstance(slug,str) or not slug.strip():
            continue
        parsed=urlparse(slug)
        if parsed.scheme and (parsed.scheme != "https" or
                              parsed.hostname not in ("sportscore.com","www.sportscore.com")):
            continue
        match_path=parsed.path.strip("/")
        if not match_path.startswith("football/match/"):
            continue
        fx=_fixture("sportscore",match_path,home,away,row.get("time"),
                    goals(hs),goals(as_),row.get("status_text"),
                    row.get("competition") or "")
        if fx:
            out.append(fx)
    return out


def sportscore_discovery_report(body: Any) -> dict:
    """Report coverage of the score-only feed, even if no safe minute exists."""
    rows=body.get("matches") if isinstance(body,dict) else None
    if not isinstance(rows,list):
        raise ValueError("SportScore widget response has no matches list")
    live=[r for r in rows if isinstance(r,dict) and
          str(r.get("status") or "").casefold() in {"live","in_play","second_half"}]
    return {
        "provider":"sportscore",
        "total_matches":len(rows),
        "live_matches":len(live),
        "with_explicit_clock":sum(_minute(r.get("status_text")) is not None for r in live),
        "with_utc_kickoff":sum(_kickoff(r.get("time")) is not None for r in live),
        "strictly_matchable":len(parse_sportscore(body)),
        "telegram_messages":0,
        "sqlite_writes":0,
        "attribution_url":"https://sportscore.com/",
    }


def parse_pitchapi(body: Any) -> list[dict]:
    # The documented /v1/date endpoint has no live clock. It is NOT a live
    # score or minute feed; never infer a clock from kickoff wall time.
    # Only future verified live-snapshot adapters may promote these to live.
    return []


def parse_sportmonks(body: Any) -> list[dict]:
    rows = body.get("data") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        participants = row.get("participants")
        if not isinstance(participants,list):
            continue
        teams = {}
        for participant in participants:
            loc = (participant.get("meta") or {}).get("location") if isinstance(participant,dict) else None
            if loc in ("home","away"):
                if loc in teams:  # duplicate designation is ambiguous
                    teams = {}
                    break
                teams[loc] = participant
        if set(teams) != {"home","away"}:
            continue
        # Sportmonks v3 state and scores vary by plan/fixture. Accept only
        # explicit and unambiguous score + clock, never a guessed state_id.
        state = row.get("state") or {}
        if isinstance(state,dict) and str(state.get("state") or "").casefold() not in ("2nd half","second half","2h","inplay"):
            continue
        minute = row.get("minute")
        if minute is None and isinstance(row.get("time"),dict):
            minute = row["time"].get("minute")
        scores = row.get("scores")
        score_by_side = {}
        if isinstance(scores,list):
            for score in scores:
                if not isinstance(score,dict) or str(score.get("description") or "").upper() != "CURRENT":
                    continue
                side = (score.get("score") or {}).get("participant") if isinstance(score.get("score"),dict) else None
                goal = (score.get("score") or {}).get("goals") if isinstance(score.get("score"),dict) else None
                if side in ("home","away") and side not in score_by_side:
                    score_by_side[side] = goal
        if set(score_by_side) != {"home","away"}:
            continue
        kickoff = row.get("starting_at") or ""
        if isinstance(kickoff,str) and len(kickoff)==19 and kickoff[10]==" ":
            kickoff=kickoff.replace(" ","T")+"+00:00"  # Sportmonks v3 default UTC
        fx = _fixture("sportmonks",row.get("id"),teams["home"].get("name"),
                      teams["away"].get("name"),kickoff,
                      score_by_side["home"],score_by_side["away"],minute,
                      (row.get("league") or {}).get("name") if isinstance(row.get("league"),dict) else "")
        if fx:
            out.append(fx)
    return out


PARSERS = {"highlightly":parse_highlightly,"sportmonks":parse_sportmonks,
           "sportscore":parse_sportscore,"pitchapi":parse_pitchapi}


def pair_exact(primary: list[dict], secondary: list[dict]) -> dict:
    """A secondary match can only corroborate exactly ONE FotMob fixture."""
    pairs, ambiguous = [], 0
    used_primary=set()
    used_secondary=set()
    for extra in secondary:
        possibilities = []
        for main in primary:
            if (fotmob._club_name(extra["home"]) != fotmob._club_name(main["home"]) or
                    fotmob._club_name(extra["away"]) != fotmob._club_name(main["away"])):
                continue
            if abs((extra["kickoff"]-main["kickoff"]).total_seconds())>900:
                continue
            if (extra["hg"],extra["ag"]) != (main["hg"],main["ag"]):
                continue
            if abs(extra["minute"]-main["minute"])>5:
                continue
            possibilities.append(main)
        if len(possibilities)!=1:
            ambiguous += int(len(possibilities)>1)
            continue
        match=possibilities[0]
        a,b=match["fixture_id"],(extra["source"],extra["source_fixture_id"])
        if a in used_primary or b in used_secondary:
            ambiguous+=1
            continue
        used_primary.add(a)
        used_secondary.add(b)
        pairs.append({"fotmob_id":a,"external_provider":extra["source"],
                      "external_id":extra["source_fixture_id"]})
    return {"paired":pairs,"ambiguous":ambiguous,
            "external_unpaired":len(secondary)-len(pairs),
            "telegram_messages":0}


def provider_enabled(provider: str, env: dict | None = None) -> bool:
    env = os.environ if env is None else env
    if provider not in SUPPORTED or env.get("LMG_EXTERNAL_SOURCES_SHADOW") != "true":
        return False
    if provider=="sportscore":
        # Read-only shadow coverage only; this flag NEVER authorizes copying
        # results onto public Telegram cards or using SportScore for betting.
        return env.get("LMG_SOURCE_SPORTSCORE_READ_ONLY")=="true"
    secret = {"pitchapi":"PITCHAPI_KEY","highlightly":"HIGHLIGHTLY_API_KEY",
              "sportmonks":"SPORTMONKS_API_KEY"}.get(provider)
    return bool(secret and env.get(secret))


def fetch_provider(provider: str, *, day: str, session=None, env=None) -> list[dict]:
    """One documentation-based read per provider, never a quota-hungry retry."""
    env = os.environ if env is None else env
    if not provider_enabled(provider,env):
        return []
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}",day):
        raise ValueError("Invalid UTC day")
    http=session or requests
    if provider=="highlightly":
        url=SOURCE_URLS[provider]
        params={"date":day,"timezone":"Etc/UTC","limit":100}
        headers={"x-rapidapi-key":env["HIGHLIGHTLY_API_KEY"]}
    elif provider=="sportmonks":
        url=SOURCE_URLS[provider]
        params={"include":"participants;scores;state"}
        headers={"Authorization":"Bearer "+env["SPORTMONKS_API_KEY"]}
    elif provider=="pitchapi":
        url=SOURCE_URLS[provider]+day
        params={}
        headers={"X-API-KEY":env["PITCHAPI_KEY"]}
    else:
        url=SOURCE_URLS[provider]
        params={"sport":"football","limit":50,"src":"netrattler-readonly-qa"}
        headers={"Accept":"application/json"}
    try:
        resp=http.get(url,params=params,headers=headers,timeout=12)
        if resp.status_code in (401,403,429):
            return []
        resp.raise_for_status()
        return PARSERS[provider](resp.json())
    except (requests.RequestException,ValueError,TypeError,KeyError):
        return []


def probe_external(*, day: str, primary: list[dict], env=None, session=None) -> dict:
    """Audit only: consumes no Telegram or SQLite state, returns safe metadata."""
    result={"enabled":[],"parsed":{},"paired":{},"telegram_messages":0}
    for provider in ("sportscore","sportmonks","highlightly","pitchapi"):
        if not provider_enabled(provider,env):
            continue
        matches=fetch_provider(provider,day=day,session=session,env=env)
        result["enabled"].append(provider)
        result["parsed"][provider]=len(matches)
        result["paired"][provider]=pair_exact(primary,matches)
    return result
