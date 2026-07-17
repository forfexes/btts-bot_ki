#!/usr/bin/env python3
"""NETRATTLER V36 autonomous learning engine.

The engine is deliberately conservative:
- discovers repositories and public data sources;
- never executes unknown third-party code;
- tests repository metadata and sample CSV/JSON files in quarantine;
- promotes only sources with recognised football schemas;
- learns calibration, source/market/league/player/builder weights from settled picks;
- writes a compact runtime policy consumed by the bot and builder engine.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

import requests

UTC_NOW = lambda: datetime.now(timezone.utc).isoformat()
UA = "NETRATTLER-SelfLearning/36.0 (+https://github.com/forfexes/btts-bot_ki)"
POLICY_FILE = Path(os.getenv("NETRATTLER_POLICY_FILE", "netrattler_active_policy.json"))
SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or ""
HTTP_TIMEOUT = int(os.getenv("NETRATTLER_HTTP_TIMEOUT", "25"))

KNOWN_REPOS = [
    "openfootball/football.json", "openfootball/worldcup.json",
    "openfootball/south-america", "openfootball/europe",
    "openfootball/champions-league", "openfootball/internationals",
    "openfootball/players", "openfootball/clubs",
    "martj42/international_results", "martj42/womens-international-results",
    "statsbomb/open-data", "probberechts/soccerdata",
    "davidrocha9/fotmob-scraper", "withqwerty/reep",
    "jordantete/OddsHarvester", "salimt/football-datasets",
    "eddwebster/football_analytics", "Simatwa/livescore-api",
    "Mg30/odds-portal-scraper", "gingeleski/odds-portal-scraper",
    "morrisndurere/Sports-Betting-Data-Scraping",
    "davccavalcante/bet365-api-scraper",
    "datasets/football-datasets", "openfootball/awesome-football",
]

GITHUB_QUERIES = [
    'football soccer results dataset language:Python',
    'football player stats scraper stars:>3',
    'soccer odds scraper oddsportal playwright',
    'bet365 football odds scraper',
    'fotmob sofascore fbref understat scraper',
    'football entity mapping player team ids',
    'soccer expected goals event data csv json',
    'football closing odds dataset',
]

RESULT_ALIASES = {
    "date": {"date", "match_date", "datetime", "utcdate", "game_date"},
    "home_team": {"home_team", "hometeam", "home", "team1", "localteam"},
    "away_team": {"away_team", "awayteam", "away", "team2", "visitorteam"},
    "home_score": {"home_score", "fthg", "score_home", "home_goals", "goals_home"},
    "away_score": {"away_score", "ftag", "score_away", "away_goals", "goals_away"},
}
PLAYER_ALIASES = {
    "player": {"player", "player_name", "name", "athlete"},
    "team": {"team", "team_name", "club", "squad"},
    "date": {"date", "match_date", "game_date"},
    "minutes": {"minutes", "mins", "min"},
    "shots": {"shots", "total_shots"},
    "sot": {"sot", "shots_on_target"},
    "tackles": {"tackles", "tackles_won"},
    "fouls": {"fouls", "fouls_committed"},
    "passes": {"passes", "passes_completed"},
}
ODDS_ALIASES = {
    "date": {"date", "match_date", "commence_time"},
    "home_team": RESULT_ALIASES["home_team"],
    "away_team": RESULT_ALIASES["away_team"],
    "odds": {"odds", "price", "decimal_odds", "b365h", "psh"},
    "bookmaker": {"bookmaker", "bookie", "sportsbook"},
    "market": {"market", "market_key", "bet_type"},
}


def log(message: str, level: str = "INFO") -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"{ts} {level:<7} {message}", flush=True)


def norm(value: Any) -> str:
    text = str(value or "").lower().strip()
    text = re.sub(r"[^a-z0-9äöüßáéíóúàèìòùâêîôûãõñç._+/-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def stable_hash(*parts: Any) -> str:
    raw = "||".join(json.dumps(p, sort_keys=True, ensure_ascii=False, default=str) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def github_headers() -> Dict[str, str]:
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


class SupabaseRest:
    def __init__(self, url: str = SUPABASE_URL, key: str = SUPABASE_KEY) -> None:
        self.url = url.rstrip("/")
        self.key = key

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.key)

    def headers(self, prefer: str = "return=minimal") -> Dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": prefer,
        }

    def get(self, table: str, *, select: str = "*", filters: Optional[Mapping[str, str]] = None,
            order: str = "", limit_total: int = 50000, page_size: int = 1000) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        output: List[Dict[str, Any]] = []
        offset = 0
        while offset < limit_total:
            params: Dict[str, Any] = {"select": select, "limit": min(page_size, limit_total - offset), "offset": offset}
            if order:
                params["order"] = order
            params.update(filters or {})
            response = requests.get(
                f"{self.url}/rest/v1/{table}", headers=self.headers(), params=params, timeout=HTTP_TIMEOUT
            )
            if not response.ok:
                if response.status_code not in (404, 400):
                    log(f"Supabase GET {table} {response.status_code}: {response.text[:240]}", "WARN")
                break
            batch = response.json()
            if not isinstance(batch, list) or not batch:
                break
            output.extend(batch)
            if len(batch) < params["limit"]:
                break
            offset += len(batch)
        return output

    def upsert(self, table: str, rows: Sequence[Dict[str, Any]], conflict: str, chunk_size: int = 200) -> Tuple[int, int]:
        if not rows:
            return 0, 0
        if not self.enabled:
            return 0, len(rows)
        ok = fail = 0
        for index in range(0, len(rows), chunk_size):
            chunk = list(rows[index:index + chunk_size])
            response = requests.post(
                f"{self.url}/rest/v1/{table}",
                headers=self.headers("resolution=merge-duplicates,return=minimal"),
                params={"on_conflict": conflict}, json=chunk, timeout=HTTP_TIMEOUT,
            )
            if response.ok:
                ok += len(chunk)
            else:
                fail += len(chunk)
                log(f"Supabase UPSERT {table} {response.status_code}: {response.text[:260]}", "WARN")
        return ok, fail

    def patch(self, table: str, filters: Mapping[str, str], payload: Mapping[str, Any]) -> bool:
        if not self.enabled:
            return False
        response = requests.patch(
            f"{self.url}/rest/v1/{table}", headers=self.headers(), params=dict(filters),
            json=dict(payload), timeout=HTTP_TIMEOUT,
        )
        return response.ok


@dataclass
class SourceTest:
    source_id: str
    source_name: str
    repo_full_name: str
    url: str
    category: str
    status: str
    trust_score: float
    reliability_score: float
    schema_score: float
    freshness_score: float
    cost: str
    license: str
    auto_ingest: bool
    adapter: str
    latency_ms: int
    metadata: Dict[str, Any]
    tested_at: str


def _alias_hit(columns: Iterable[str], aliases: Mapping[str, set]) -> Tuple[int, Dict[str, str]]:
    normalized = {norm(c).replace(" ", "_"): c for c in columns}
    mapping: Dict[str, str] = {}
    for target, names in aliases.items():
        for name in names:
            key = norm(name).replace(" ", "_")
            if key in normalized:
                mapping[target] = normalized[key]
                break
    return len(mapping), mapping


def infer_schema(columns: Iterable[str]) -> Tuple[str, float, Dict[str, str]]:
    cols = list(columns)
    result_hits, result_map = _alias_hit(cols, RESULT_ALIASES)
    player_hits, player_map = _alias_hit(cols, PLAYER_ALIASES)
    odds_hits, odds_map = _alias_hit(cols, ODDS_ALIASES)
    if result_hits >= 5:
        return "match_results", min(1.0, result_hits / len(RESULT_ALIASES)), result_map
    if player_hits >= 4 and "player" in player_map:
        return "player_stats", min(1.0, player_hits / 6.0), player_map
    if odds_hits >= 5 and "odds" in odds_map:
        return "odds", min(1.0, odds_hits / len(ODDS_ALIASES)), odds_map
    if player_hits >= 2 and ("player" in player_map or "team" in player_map):
        return "identity", min(0.75, player_hits / 5.0), player_map
    return "unknown", 0.0, {}


def _parse_sample(content: bytes, path: str) -> Tuple[str, float, Dict[str, str], int]:
    lower = path.lower()
    try:
        if lower.endswith((".csv", ".tsv")):
            text = content.decode("utf-8-sig", errors="replace")
            dialect = csv.excel_tab if lower.endswith(".tsv") else csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
            reader = csv.DictReader(io.StringIO(text), dialect=dialect)
            schema, score, mapping = infer_schema(reader.fieldnames or [])
            rows = sum(1 for _, _row in zip(range(25), reader))
            return schema, score, mapping, rows
        if lower.endswith(".json"):
            data = json.loads(content.decode("utf-8-sig", errors="replace"))
            candidate: Any = data
            if isinstance(data, dict):
                for key in ("matches", "games", "results", "data", "events", "players", "odds"):
                    if isinstance(data.get(key), list) and data[key]:
                        candidate = data[key]
                        break
            if isinstance(candidate, list) and candidate and isinstance(candidate[0], dict):
                schema, score, mapping = infer_schema(candidate[0].keys())
                return schema, score, mapping, min(25, len(candidate))
            if isinstance(candidate, dict):
                schema, score, mapping = infer_schema(candidate.keys())
                return schema, score, mapping, 1
    except Exception:
        pass
    return "unknown", 0.0, {}, 0


def discover_repositories() -> List[Dict[str, Any]]:
    session = requests.Session()
    session.headers.update(github_headers())
    repos: Dict[str, Dict[str, Any]] = {}
    for repo in KNOWN_REPOS:
        try:
            response = session.get(f"https://api.github.com/repos/{repo}", timeout=HTTP_TIMEOUT)
            if response.ok:
                repos[repo.lower()] = response.json()
        except requests.RequestException:
            pass
    for query in GITHUB_QUERIES:
        try:
            response = session.get(
                "https://api.github.com/search/repositories",
                params={"q": query, "sort": "updated", "order": "desc", "per_page": 20},
                timeout=HTTP_TIMEOUT,
            )
            if not response.ok:
                log(f"GitHub search '{query}' {response.status_code}", "WARN")
                continue
            for item in response.json().get("items", []):
                full_name = str(item.get("full_name") or "").lower()
                if full_name:
                    item["discovery_query"] = query
                    repos[full_name] = item
            time.sleep(0.8)
        except requests.RequestException as exc:
            log(f"GitHub search '{query}': {exc}", "WARN")
    return list(repos.values())


def test_repository(repo: Mapping[str, Any]) -> SourceTest:
    full_name = str(repo.get("full_name") or "")
    start = time.monotonic()
    session = requests.Session()
    session.headers.update(github_headers())
    default_branch = str(repo.get("default_branch") or "main")
    metadata = dict(repo)
    tree_items: List[Dict[str, Any]] = []
    readme_text = ""
    errors: List[str] = []
    try:
        tree_response = session.get(
            f"https://api.github.com/repos/{full_name}/git/trees/{default_branch}",
            params={"recursive": "1"}, timeout=HTTP_TIMEOUT,
        )
        if tree_response.ok:
            tree_items = list(tree_response.json().get("tree") or [])
        else:
            errors.append(f"tree:{tree_response.status_code}")
    except requests.RequestException as exc:
        errors.append(f"tree:{exc}")
    try:
        readme_response = session.get(f"https://api.github.com/repos/{full_name}/readme", timeout=HTTP_TIMEOUT)
        if readme_response.ok:
            download_url = readme_response.json().get("download_url")
            if download_url:
                rr = session.get(download_url, timeout=HTTP_TIMEOUT)
                if rr.ok:
                    readme_text = rr.text[:120000]
    except requests.RequestException as exc:
        errors.append(f"readme:{exc}")

    data_files = []
    code_files = []
    for item in tree_items:
        if item.get("type") != "blob":
            continue
        path = str(item.get("path") or "")
        lower = path.lower()
        if any(part in lower for part in ("node_modules/", "vendor/", ".git/", "tests/fixtures/")):
            continue
        if lower.endswith((".csv", ".json", ".tsv", ".parquet")) and int(item.get("size") or 0) <= 5_000_000:
            data_files.append(item)
        if lower.endswith((".py", ".js", ".ts")):
            code_files.append(item)

    best_schema = "unknown"
    best_score = 0.0
    best_mapping: Dict[str, str] = {}
    best_path = ""
    sample_rows = 0
    for item in sorted(data_files, key=lambda x: int(x.get("size") or 0), reverse=True)[:8]:
        path = str(item.get("path") or "")
        if path.lower().endswith(".parquet"):
            continue
        raw_url = f"https://raw.githubusercontent.com/{full_name}/{default_branch}/{path}"
        try:
            response = session.get(raw_url, timeout=HTTP_TIMEOUT)
            if not response.ok:
                continue
            schema, score, mapping, rows = _parse_sample(response.content, path)
            if score > best_score:
                best_schema, best_score, best_mapping, best_path, sample_rows = schema, score, mapping, path, rows
        except requests.RequestException:
            continue

    pushed = str(repo.get("pushed_at") or repo.get("updated_at") or "")
    freshness = 0.35
    if pushed:
        try:
            age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(pushed.replace("Z", "+00:00"))).days
            freshness = clamp(1.0 - age_days / 1095.0, 0.05, 1.0)
        except ValueError:
            pass
    license_id = str((repo.get("license") or {}).get("spdx_id") or "NOASSERTION")
    license_score = 1.0 if license_id not in {"", "NOASSERTION", "OTHER"} else 0.45
    archived = bool(repo.get("archived"))
    stars = int(repo.get("stargazers_count") or 0)
    issues = int(repo.get("open_issues_count") or 0)
    reliability = clamp(0.35 + min(0.25, math.log1p(stars) / 20.0) + freshness * 0.35 + (0.10 if tree_items else 0), 0, 1)
    text = norm(" ".join([str(repo.get("description") or ""), readme_text[:50000]]))
    paid_words = ("paid api", "subscription", "pricing plan", "purchase api", "commercial license")
    cost = "paid" if any(word in text for word in paid_words) else "free"

    relevant_code = any(word in text for word in (
        "football", "soccer", "fbref", "sofascore", "fotmob", "understat",
        "oddsportal", "bet365", "pinnacle", "bookmaker", "statsbomb",
    ))
    adapter = "generic_data" if best_schema != "unknown" else ("adapter_needed" if relevant_code and code_files else "none")
    auto_ingest = best_schema in {"match_results", "player_stats", "odds", "identity"} and cost == "free"
    category = best_schema if best_schema != "unknown" else ("scraper_code" if relevant_code else "unknown")

    trust = (
        best_score * 0.40 + reliability * 0.25 + freshness * 0.15 +
        license_score * 0.10 + (0.10 if relevant_code else 0.0)
    )
    if archived:
        trust *= 0.45
    if cost == "paid":
        trust *= 0.50
    trust = clamp(trust, 0, 1)
    if auto_ingest and trust >= 0.70:
        status = "active"
    elif (auto_ingest or adapter == "adapter_needed") and trust >= 0.52:
        status = "fallback"
    elif archived or not relevant_code:
        status = "blocked"
    else:
        status = "quarantine"

    metadata.update({
        "default_branch": default_branch,
        "data_files": [x.get("path") for x in data_files[:50]],
        "code_file_count": len(code_files),
        "best_data_path": best_path,
        "schema_mapping": best_mapping,
        "sample_rows": sample_rows,
        "errors": errors,
        "archived": archived,
        "open_issues": issues,
    })
    elapsed = int((time.monotonic() - start) * 1000)
    return SourceTest(
        source_id=stable_hash("github", full_name)[:32],
        source_name=full_name,
        repo_full_name=full_name,
        url=str(repo.get("html_url") or f"https://github.com/{full_name}"),
        category=category,
        status=status,
        trust_score=round(trust, 4),
        reliability_score=round(reliability, 4),
        schema_score=round(best_score, 4),
        freshness_score=round(freshness, 4),
        cost=cost,
        license=license_id,
        auto_ingest=auto_ingest,
        adapter=adapter,
        latency_ms=elapsed,
        metadata=metadata,
        tested_at=UTC_NOW(),
    )


def run_source_lab(max_repos: int = 80, db: Optional[SupabaseRest] = None) -> List[SourceTest]:
    db = db or SupabaseRest()
    repos = discover_repositories()
    # Known repositories first, then highest stars/recent.
    known = {x.lower() for x in KNOWN_REPOS}
    repos.sort(key=lambda r: (str(r.get("full_name") or "").lower() in known, int(r.get("stargazers_count") or 0)), reverse=True)
    tests: List[SourceTest] = []
    for repo in repos[:max_repos]:
        try:
            test = test_repository(repo)
            tests.append(test)
            log(f"SOURCE {test.status:<10} {test.trust_score:.2f} {test.source_name} [{test.category}]")
        except Exception as exc:
            log(f"Source test {repo.get('full_name')}: {exc}", "WARN")
    candidate_rows = []
    test_rows = []
    for item in tests:
        row = asdict(item)
        row["updated_at"] = UTC_NOW()
        candidate_rows.append(row)
        test_rows.append({
            "test_id": stable_hash(item.source_id, item.tested_at)[:40],
            "source_id": item.source_id,
            "status": item.status,
            "trust_score": item.trust_score,
            "latency_ms": item.latency_ms,
            "details": item.metadata,
            "tested_at": item.tested_at,
        })
    if db.enabled:
        db.upsert("netrattler_source_candidates", candidate_rows, "source_id")
        db.upsert("netrattler_source_tests", test_rows, "test_id")
    return tests


def _status_outcome(status: Any) -> Optional[int]:
    value = norm(status)
    if value in {"win", "won", "green", "success"}:
        return 1
    if value in {"loss", "lost", "red", "failed"}:
        return 0
    return None


def _odds_bucket(odds: float) -> str:
    if odds < 1.50:
        return "<1.50"
    if odds < 1.80:
        return "1.50-1.79"
    if odds < 2.20:
        return "1.80-2.19"
    if odds < 3.00:
        return "2.20-2.99"
    if odds < 5.00:
        return "3.00-4.99"
    return "5.00+"


def _pick_key(tip: Mapping[str, Any]) -> str:
    return str(tip.get("tip_id") or tip.get("id") or stable_hash(
        tip.get("date"), tip.get("match"), tip.get("market"), tip.get("tip"), tip.get("odds")
    )[:40])


def _tip_probability(tip: Mapping[str, Any]) -> float:
    value = to_float(tip.get("calibrated_probability") or tip.get("probability") or tip.get("prob") or 0)
    if value > 1:
        value /= 100.0
    return clamp(value, 0.01, 0.99)


def _tip_source(tip: Mapping[str, Any]) -> str:
    return str(tip.get("edge_source") or tip.get("bookie") or tip.get("source") or "unknown")


def _builder_type(tip: Mapping[str, Any]) -> str:
    pick_type = norm(tip.get("pick_type") or tip.get("market"))
    legs = int(to_float(tip.get("builder_total_legs") or 1, 1))
    if "builder" in pick_type or "combo" in pick_type or legs > 1:
        if legs >= 7:
            return "lottery"
        if legs >= 5:
            return "risky"
        if legs >= 3:
            return "value_builder"
        return "safe_builder"
    return "single"


def _profit(tip: Mapping[str, Any], outcome: int, odds: float) -> float:
    explicit = tip.get("profit_units")
    if explicit not in (None, ""):
        return to_float(explicit)
    stake = max(0.0, to_float(tip.get("units") or tip.get("stake") or 1.0, 1.0))
    return stake * (odds - 1.0) if outcome else -stake


def build_learning_events(tips: Sequence[Mapping[str, Any]], clv_rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    clv_by_tip: Dict[str, Mapping[str, Any]] = {}
    for row in clv_rows:
        key = str(row.get("tip_id") or row.get("pick_key") or "")
        if key:
            clv_by_tip[key] = row
    events: List[Dict[str, Any]] = []
    for tip in tips:
        outcome = _status_outcome(tip.get("status"))
        if outcome is None:
            continue
        key = _pick_key(tip)
        probability = _tip_probability(tip)
        odds = max(1.01, to_float(tip.get("odds") or tip.get("bet365_quote") or tip.get("oddsYes") or 1.01, 1.01))
        clv_row = clv_by_tip.get(key) or {}
        closing_odds = to_float(clv_row.get("closing_odds") or tip.get("closing_odds") or 0)
        clv = to_float(clv_row.get("clv") or tip.get("clv") or 0)
        if not clv and closing_odds > 1:
            clv = (odds / closing_odds) - 1.0
        brier = (probability - outcome) ** 2
        logloss = -(outcome * math.log(probability) + (1 - outcome) * math.log(1 - probability))
        legs = max(1, int(to_float(tip.get("builder_total_legs") or 1, 1)))
        event = {
            "event_id": stable_hash("learning", key)[:40],
            "pick_key": key,
            "tip_date": str(tip.get("date") or tip.get("tip_date") or "")[:10] or None,
            "market": norm(tip.get("market") or tip.get("market_name") or "unknown"),
            "league": norm(tip.get("league") or "unknown"),
            "source": norm(_tip_source(tip)),
            "player": norm(tip.get("player") or tip.get("player_name") or ""),
            "builder_type": _builder_type(tip),
            "legs": legs,
            "odds_bucket": _odds_bucket(odds),
            "probability": round(probability, 6),
            "odds": round(odds, 4),
            "closing_odds": round(closing_odds, 4) if closing_odds > 1 else None,
            "clv": round(clv, 6),
            "outcome": outcome,
            "profit_units": round(_profit(tip, outcome, odds), 6),
            "brier": round(brier, 6),
            "logloss": round(logloss, 6),
            "payload": dict(tip),
            "settled_at": str(tip.get("settled_at") or tip.get("updated_at") or UTC_NOW()),
            "created_at": UTC_NOW(),
        }
        events.append(event)
    return events


def _dimension_rows(events: Sequence[Mapping[str, Any]], dimension: str, key_fn) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for event in events:
        key = norm(key_fn(event)) or "unknown"
        groups[key].append(event)
    rows: List[Dict[str, Any]] = []
    for key, group in groups.items():
        n = len(group)
        wins = sum(int(x["outcome"]) for x in group)
        profit = sum(to_float(x.get("profit_units")) for x in group)
        stake_proxy = sum(max(0.05, abs(to_float(x.get("profit_units")))) for x in group)
        roi = profit / max(1.0, stake_proxy)
        brier = statistics.fmean(to_float(x.get("brier")) for x in group)
        clv_values = [to_float(x.get("clv")) for x in group if x.get("clv") is not None]
        mean_clv = statistics.fmean(clv_values) if clv_values else 0.0
        actual_rate = (wins + 5.0) / (n + 10.0)
        predicted_rate = statistics.fmean(to_float(x.get("probability")) for x in group)
        calibration_error = abs(actual_rate - predicted_rate)
        sample_confidence = 1.0 - math.exp(-n / 40.0)
        score = (
            0.45 * clamp(1.0 - calibration_error / 0.20, 0, 1) +
            0.25 * clamp(0.5 + roi, 0, 1) +
            0.20 * clamp(0.5 + mean_clv * 5.0, 0, 1) +
            0.10 * clamp(1.0 - brier / 0.35, 0, 1)
        )
        weight = 1.0 + (score - 0.5) * 0.70 * sample_confidence
        weight = clamp(weight, 0.65, 1.35)
        rows.append({
            "dimension": dimension,
            "weight_key": key,
            "weight": round(weight, 5),
            "samples": n,
            "wins": wins,
            "win_rate": round(wins / n, 6),
            "roi": round(roi, 6),
            "mean_clv": round(mean_clv, 6),
            "brier": round(brier, 6),
            "calibration_error": round(calibration_error, 6),
            "updated_at": UTC_NOW(),
        })
    return rows


def build_weight_rows(events: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    specs = [
        ("source", lambda x: x.get("source")),
        ("market", lambda x: x.get("market")),
        ("league", lambda x: x.get("league")),
        ("player", lambda x: x.get("player") or "unknown"),
        ("builder", lambda x: x.get("builder_type")),
        ("odds_bucket", lambda x: x.get("odds_bucket")),
        ("legs", lambda x: str(x.get("legs"))),
    ]
    output: List[Dict[str, Any]] = []
    for dimension, fn in specs:
        output.extend(_dimension_rows(events, dimension, fn))
    return output


def build_calibration_rows(events: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, str, str], List[Mapping[str, Any]]] = defaultdict(list)
    for event in events:
        p = to_float(event.get("probability"))
        bin_value = int(p * 20) / 20.0
        bin_key = f"{bin_value:.2f}"
        groups[("global", "all", bin_key)].append(event)
        groups[("market", norm(event.get("market")), bin_key)].append(event)
        groups[("league", norm(event.get("league")), bin_key)].append(event)
    rows: List[Dict[str, Any]] = []
    for (scope_type, scope_key, bin_key), group in groups.items():
        n = len(group)
        wins = sum(int(x["outcome"]) for x in group)
        predicted = statistics.fmean(to_float(x.get("probability")) for x in group)
        # Beta(5,5) shrinkage towards 0.5; blend towards predicted for small samples.
        actual = (wins + 5.0) / (n + 10.0)
        confidence = min(0.80, n / 100.0)
        calibrated = (1.0 - confidence) * predicted + confidence * actual
        rows.append({
            "scope_type": scope_type,
            "scope_key": scope_key or "unknown",
            "prob_bin": bin_key,
            "predicted_mean": round(predicted, 6),
            "actual_rate": round(actual, 6),
            "calibrated": round(clamp(calibrated, 0.01, 0.99), 6),
            "samples": n,
            "updated_at": UTC_NOW(),
        })
    return rows


def build_risk_state(events: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    ordered = sorted(events, key=lambda x: (str(x.get("tip_date") or ""), str(x.get("settled_at") or "")))
    bankroll = 100.0
    peak = bankroll
    max_drawdown = 0.0
    losing_streak = current_losing = 0
    for event in ordered:
        bankroll += to_float(event.get("profit_units"))
        peak = max(peak, bankroll)
        max_drawdown = max(max_drawdown, (peak - bankroll) / max(peak, 1.0))
        if int(event.get("outcome") or 0) == 0:
            current_losing += 1
            losing_streak = max(losing_streak, current_losing)
        else:
            current_losing = 0
    recent = ordered[-100:]
    recent_profit = sum(to_float(x.get("profit_units")) for x in recent)
    recent_brier = statistics.fmean(to_float(x.get("brier")) for x in recent) if recent else 0.25
    if max_drawdown >= 0.18 or current_losing >= 8 or recent_profit <= -12:
        mode = "protect"
        single_cap, builder_cap, lottery_cap, max_legs, kelly = 0.35, 0.12, 0.02, 4, 0.10
        max_singles, max_builders = 8, 3
    elif max_drawdown >= 0.10 or current_losing >= 5 or recent_profit <= -6:
        mode = "caution"
        single_cap, builder_cap, lottery_cap, max_legs, kelly = 0.60, 0.22, 0.03, 5, 0.18
        max_singles, max_builders = 12, 5
    elif len(events) >= 100 and recent_profit > 8 and recent_brier < 0.21:
        mode = "growth"
        single_cap, builder_cap, lottery_cap, max_legs, kelly = 1.25, 0.45, 0.06, 7, 0.30
        max_singles, max_builders = 24, 10
    else:
        mode = "normal"
        single_cap, builder_cap, lottery_cap, max_legs, kelly = 0.90, 0.35, 0.05, 6, 0.25
        max_singles, max_builders = 18, 8
    return {
        "state_id": "current",
        "mode": mode,
        "bankroll_units": round(bankroll, 4),
        "peak_bankroll_units": round(peak, 4),
        "drawdown_pct": round(max_drawdown * 100, 3),
        "current_losing_streak": current_losing,
        "max_losing_streak": losing_streak,
        "recent_profit_units": round(recent_profit, 4),
        "recent_brier": round(recent_brier, 6),
        "single_max_units": single_cap,
        "builder_max_units": builder_cap,
        "lottery_max_units": lottery_cap,
        "max_builder_legs": max_legs,
        "max_daily_singles": max_singles,
        "max_daily_builders": max_builders,
        "kelly_fraction": kelly,
        "updated_at": UTC_NOW(),
    }


def build_policy(
    weights: Sequence[Mapping[str, Any]],
    calibration: Sequence[Mapping[str, Any]],
    risk: Mapping[str, Any],
    source_candidates: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    weight_map: Dict[str, Dict[str, Any]] = defaultdict(dict)
    for row in weights:
        weight_map[str(row.get("dimension"))][norm(row.get("weight_key"))] = {
            "weight": to_float(row.get("weight"), 1.0),
            "samples": int(to_float(row.get("samples"))),
            "roi": to_float(row.get("roi")),
            "clv": to_float(row.get("mean_clv")),
            "brier": to_float(row.get("brier")),
        }
    calibration_map = {
        f"{row.get('scope_type')}|{norm(row.get('scope_key'))}|{row.get('prob_bin')}": {
            "calibrated": to_float(row.get("calibrated")),
            "samples": int(to_float(row.get("samples"))),
        }
        for row in calibration
    }
    active_sources = []
    fallback_sources = []
    for source in source_candidates:
        item = {
            "source_id": source.get("source_id"),
            "name": source.get("source_name"),
            "category": source.get("category"),
            "trust": to_float(source.get("trust_score")),
            "adapter": source.get("adapter"),
            "auto_ingest": bool(source.get("auto_ingest")),
        }
        if source.get("status") == "active":
            active_sources.append(item)
        elif source.get("status") == "fallback":
            fallback_sources.append(item)
    return {
        "version": f"V36-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "generated_at": UTC_NOW(),
        "weights": dict(weight_map),
        "calibration": calibration_map,
        "risk": {k: v for k, v in risk.items() if k not in {"state_id", "updated_at"}},
        "thresholds": {
            "min_edge": 0.05 if risk.get("mode") == "protect" else 0.04 if risk.get("mode") == "caution" else 0.03,
            "min_probability": 0.58 if risk.get("mode") == "protect" else 0.56 if risk.get("mode") == "caution" else 0.55,
            "min_source_weight": 0.75,
            "min_market_weight": 0.72,
        },
        "sources": {"active": active_sources, "fallback": fallback_sources},
    }



def settlement_as_tip(row: Mapping[str, Any]) -> Dict[str, Any]:
    payload = row.get("tip_payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    tip = dict(payload) if isinstance(payload, Mapping) else {}
    tip.update({
        "tip_id": row.get("tip_id") or tip.get("tip_id") or row.get("settlement_id"),
        "status": row.get("status") or tip.get("status"),
        "odds": row.get("odds") or tip.get("odds") or tip.get("oddsYes"),
        "stake": row.get("stake") or tip.get("stake") or tip.get("units"),
        "profit_units": row.get("profit") if row.get("profit") is not None else tip.get("profit_units"),
        "tip_date": row.get("tip_date") or tip.get("tip_date") or tip.get("date"),
        "settled_at": row.get("settled_at") or tip.get("settled_at"),
        "builder_total_legs": row.get("leg_count") or tip.get("builder_total_legs") or 1,
        "builder_style": row.get("builder_style") or tip.get("builder_style"),
        "market": tip.get("market") or row.get("market_group"),
        "legs_payload": row.get("legs_payload") or tip.get("legs_payload") or [],
    })
    return tip

def run_learning_cycle(db: Optional[SupabaseRest] = None) -> Dict[str, Any]:
    db = db or SupabaseRest()
    tips: List[Dict[str, Any]] = []
    for table in ("tips", "ml_tips", "prop_picks", "netrattler_builder_picks"):
        rows = db.get(table, limit_total=100000)
        tips.extend(rows)
    settlements = db.get("netrattler_settlements", limit_total=100000)
    tips.extend(settlement_as_tip(row) for row in settlements)
    clv_rows = db.get("netrattler_clv_events", limit_total=100000)
    events = build_learning_events(tips, clv_rows)
    # Dedupe across legacy/current tables.
    unique = {row["event_id"]: row for row in events}
    events = list(unique.values())
    weights = build_weight_rows(events)
    calibration = build_calibration_rows(events)
    risk = build_risk_state(events)
    candidates = db.get("netrattler_source_candidates", limit_total=5000)
    policy = build_policy(weights, calibration, risk, candidates)

    if db.enabled:
        db.upsert("netrattler_learning_events", events, "event_id")
        db.upsert("netrattler_learning_weights", weights, "dimension,weight_key")
        db.upsert("netrattler_calibration_bins", calibration, "scope_type,scope_key,prob_bin")
        db.upsert("netrattler_risk_state", [risk], "state_id")
        snapshot = {
            "policy_id": stable_hash(policy["version"])[:40],
            "version": policy["version"],
            "policy": policy,
            "is_active": False,
            "created_at": UTC_NOW(),
        }
        # Insert inactive first, then atomically-like flip active state. This avoids
        # violating the partial unique index when an older policy is active.
        db.upsert("netrattler_policy_snapshots", [snapshot], "policy_id")
        db.patch("netrattler_policy_snapshots", {"is_active": "eq.true"}, {"is_active": False})
        db.patch("netrattler_policy_snapshots", {"policy_id": f"eq.{snapshot['policy_id']}"}, {"is_active": True})

    POLICY_FILE.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Learning: {len(events)} settled picks | {len(weights)} weights | mode={risk['mode']}")
    return policy


if __name__ == "__main__":
    mode = os.getenv("NETRATTLER_LEARNING_MODE", "all").lower()
    db = SupabaseRest()
    if mode in {"all", "sources", "discovery"}:
        run_source_lab(max_repos=int(os.getenv("NETRATTLER_MAX_DISCOVERY_REPOS", "80")), db=db)
    if mode in {"all", "learning", "settlement"}:
        run_learning_cycle(db=db)
        # V36: learn empirical builder correlations and chronology-safe
        # champion calibration models after every settlement cycle.
        try:
            from netrattler_builder_learning_v36 import learn as _learn_builder_pairs
            _learn_builder_pairs(db=db)
        except Exception as exc:
            log(f"V36 builder learning skipped: {exc}", "WARN")
        try:
            from netrattler_autolearn_v36 import train_and_promote as _train_autolearn
            _train_autolearn(db=db)
        except Exception as exc:
            log(f"V36 AutoML skipped: {exc}", "WARN")
