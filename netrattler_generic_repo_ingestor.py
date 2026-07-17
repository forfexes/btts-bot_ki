#!/usr/bin/env python3
"""Safely ingest recognised CSV/JSON datasets from promoted GitHub sources.

Unknown repository code is never imported or executed.  Only data files that
passed the V35 source lab are downloaded, schema-inferred and normalised.
"""
from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import requests

from netrattler_learning_engine import (
    GITHUB_TOKEN, HTTP_TIMEOUT, SupabaseRest, dedupe_rows_for_conflict,
    infer_schema, is_production_football_data_path, log, norm,
    source_role_override, stable_hash, to_float,
)
from netrattler_source_router_v36 import load_last_good, save_last_good

MAX_FILES = int(os.getenv("NETRATTLER_GENERIC_MAX_FILES", "30"))
MAX_ROWS_PER_FILE = int(os.getenv("NETRATTLER_GENERIC_MAX_ROWS_PER_FILE", "5000"))


GENERIC_DATA_REPO_ALLOWLIST = {
    "martj42/international_results",
    "martj42/womens-international-results",
    "datasets/football-datasets",
    "anishkhetani/premier-league-data",
    "salimt/football-datasets",
}


def _repo_allows_generic_ingest(repo: str, candidate: Mapping[str, Any]) -> bool:
    key = str(repo or "").lower()
    if source_role_override(key):
        return False
    adapter = str(candidate.get("adapter") or "").lower()
    category = str(candidate.get("category") or "").lower()
    if key in GENERIC_DATA_REPO_ALLOWLIST:
        return True
    return adapter == "generic_data" and category in {"match_results", "player_stats", "odds"}


def _path_is_allowed(repo: str, path: str) -> bool:
    if not is_production_football_data_path(path):
        return False
    lower = str(path or "").replace("\\", "/").lower()
    # Odds/code repositories often contain multi-sport test payloads. Generic
    # ingestion is forbidden even when a file accidentally resembles results.
    if source_role_override(repo):
        return False
    return True


def _headers() -> Dict[str, str]:
    headers = {"User-Agent": "NETRATTLER-GenericRepoIngestor/36C", "Accept": "*/*"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def _first(row: Mapping[str, Any], mapping: Mapping[str, str], key: str, default: Any = None) -> Any:
    source_key = mapping.get(key)
    return row.get(source_key, default) if source_key else default


def _date(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    for sep in ("T", " "):
        if sep in text and len(text.split(sep)[0]) >= 8:
            text = text.split(sep)[0]
            break
    # ISO or common dd/mm/yyyy forms.
    if len(text) >= 10 and text[4:5] == "-":
        return text[:10]
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text[:10], fmt).date().isoformat()
        except ValueError:
            pass
    return text[:10] if len(text) >= 8 else None


def _iter_rows(content: bytes, path: str) -> Iterable[Dict[str, Any]]:
    lower = path.lower()
    if lower.endswith((".csv", ".tsv")):
        text = content.decode("utf-8-sig", errors="replace")
        try:
            dialect = csv.excel_tab if lower.endswith(".tsv") else csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        yield from csv.DictReader(io.StringIO(text), dialect=dialect)
        return
    if lower.endswith(".json"):
        data = json.loads(content.decode("utf-8-sig", errors="replace"))
        if isinstance(data, dict):
            for key in ("matches", "games", "results", "data", "events", "players", "odds"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
        if isinstance(data, list):
            for row in data:
                if isinstance(row, dict):
                    yield row
        elif isinstance(data, dict):
            yield data


def _result_row(source: str, raw: Mapping[str, Any], mapping: Mapping[str, str]) -> Optional[Dict[str, Any]]:
    home = str(_first(raw, mapping, "home_team", "") or "").strip()
    away = str(_first(raw, mapping, "away_team", "") or "").strip()
    match_date = _date(_first(raw, mapping, "date"))
    if not home or not away or not match_date:
        return None
    hg = int(to_float(_first(raw, mapping, "home_score"), -999))
    ag = int(to_float(_first(raw, mapping, "away_score"), -999))
    if hg == -999 or ag == -999:
        return None
    total = hg + ag
    return {
        "source": source,
        "match_id": stable_hash(source, match_date, home, away)[:64],
        "match_date": match_date,
        "season": str(raw.get("season") or ""),
        "country": str(raw.get("country") or ""),
        "league": str(raw.get("league") or raw.get("competition") or raw.get("tournament") or "Unknown"),
        "division": str(raw.get("division") or ""),
        "home_team": home,
        "away_team": away,
        "home_goals": hg,
        "away_goals": ag,
        "result": "H" if hg > ag else "A" if ag > hg else "D",
        "total_goals": total,
        "btts": bool(hg > 0 and ag > 0),
        "over_25_hit": bool(total > 2.5),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _player_row(source: str, raw: Mapping[str, Any], mapping: Mapping[str, str]) -> Optional[Dict[str, Any]]:
    player = str(_first(raw, mapping, "player", "") or "").strip()
    if not player:
        return None
    team = str(_first(raw, mapping, "team", "") or "").strip()
    match_date = _date(_first(raw, mapping, "date"))
    match_id = str(raw.get("match_id") or raw.get("event_id") or stable_hash(source, match_date, team, player)[:48])
    row = {
        "source": source,
        "event_id": match_id,
        "player_id": str(raw.get("player_id") or stable_hash(source, player)[:32]),
        "player_name": player,
        "player": player,
        "team": team,
        "league": str(raw.get("league") or raw.get("competition") or ""),
        "match_date": match_date,
        "date": match_date,
        "minutes": to_float(_first(raw, mapping, "minutes")),
        "shots": to_float(_first(raw, mapping, "shots")),
        "sot": to_float(_first(raw, mapping, "sot")),
        "shots_on_target": to_float(_first(raw, mapping, "sot")),
        "tackles": to_float(_first(raw, mapping, "tackles")),
        "fouls_committed": to_float(_first(raw, mapping, "fouls")),
        "passes": to_float(_first(raw, mapping, "passes")),
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
    row["data_hash"] = stable_hash(source, match_id, player, row["shots"], row["sot"], row["tackles"], row["passes"])
    return row


def _odds_row(source: str, raw: Mapping[str, Any], mapping: Mapping[str, str]) -> Optional[Dict[str, Any]]:
    home = str(_first(raw, mapping, "home_team", "") or "").strip()
    away = str(_first(raw, mapping, "away_team", "") or "").strip()
    odds = to_float(_first(raw, mapping, "odds"))
    if not home or not away or odds <= 1:
        return None
    market = str(_first(raw, mapping, "market", "1x2") or "1x2")
    bookmaker = str(_first(raw, mapping, "bookmaker", source) or source)
    match_date = _date(_first(raw, mapping, "date"))
    selection = str(raw.get("selection") or raw.get("outcome") or "unknown")
    event_key = stable_hash(match_date, home, away)[:40]
    return {
        "snapshot_id": stable_hash(source, event_key, market, selection, bookmaker, odds)[:48],
        "event_key": event_key,
        "match_date": match_date,
        "home_team": home,
        "away_team": away,
        "market": market,
        "selection": selection,
        "bookmaker": bookmaker,
        "odds": odds,
        "snapshot_type": "historical_sample",
        "source": source,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": None,
    }


def ingest_source(candidate: Mapping[str, Any], db: SupabaseRest) -> Dict[str, int]:
    repo = str(candidate.get("repo_full_name") or candidate.get("source_name") or "")
    if not _repo_allows_generic_ingest(repo, candidate):
        log(f"GENERIC SKIP {repo}: dedicated adapter or unapproved generic source")
        return {"match_results": 0, "player_stats": 0, "odds": 0, "identity": 0, "failed": 0, "cached": 0, "skipped": 1, "deduped": 0}
    metadata = candidate.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    branch = str(metadata.get("default_branch") or "main")
    paths = list(metadata.get("data_files") or [])[:MAX_FILES]
    source = f"github:{repo}"
    totals = {"match_results": 0, "player_stats": 0, "odds": 0, "identity": 0, "failed": 0, "cached": 0, "skipped": 0, "deduped": 0}
    cache_items: List[Dict[str, Any]] = []
    live_rows = 0
    for path in paths:
        if not _path_is_allowed(repo, str(path)):
            totals["skipped"] += 1
            continue
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
        try:
            response = requests.get(url, headers=_headers(), timeout=HTTP_TIMEOUT)
            if not response.ok or len(response.content) > 8_000_000:
                totals["failed"] += 1
                continue
            iterator = _iter_rows(response.content, str(path))
            sample = []
            for index, row in enumerate(iterator):
                if index >= MAX_ROWS_PER_FILE:
                    break
                sample.append(row)
            if not sample:
                continue
            schema, score, mapping = infer_schema(sample[0].keys())
            if score < 0.55:
                continue
            table = conflict = ""
            if schema == "match_results":
                rows = [x for x in (_result_row(source, row, mapping) for row in sample) if x]
                table, conflict = "football_historical_matches", "source,match_id"
            elif schema == "player_stats":
                rows = [x for x in (_player_row(source, row, mapping) for row in sample) if x]
                table, conflict = "player_match_stats", "data_hash"
            elif schema == "odds":
                rows = [x for x in (_odds_row(source, row, mapping) for row in sample) if x]
                table, conflict = "netrattler_odds_snapshots", "snapshot_id"
            else:
                rows = []
            candidate_category = str(candidate.get("category") or "").lower()
            if candidate_category in {"match_results", "player_stats", "odds"} and schema != candidate_category:
                totals["skipped"] += 1
                log(
                    f"GENERIC SKIP {repo}:{path}: inferred={schema} expected={candidate_category}",
                    "WARN",
                )
                continue

            original_count = len(rows)
            rows = dedupe_rows_for_conflict(rows, conflict) if table and rows else []
            totals["deduped"] += original_count - len(rows)
            ok, failed = db.upsert(table, rows, conflict) if table and rows else (0, 0)
            totals["failed"] += failed
            totals[schema] = totals.get(schema, 0) + ok
            live_rows += ok

            # Cache only data that was actually accepted by Supabase.
            if ok and not failed:
                for row in rows[:ok]:
                    cache_items.append({"table": table, "conflict": conflict, "schema": schema, "row": row})
            log(
                f"GENERIC {repo}:{path} schema={schema} "
                f"parsed={original_count} deduped={len(rows)} written={ok} failed={failed}"
            )
        except Exception as exc:
            totals["failed"] += 1
            log(f"GENERIC {repo}:{path}: {exc}", "WARN")

    if cache_items:
        save_last_good(source, cache_items)
    elif live_rows == 0:
        cached = load_last_good(source, float(os.getenv("NETRATTLER_GENERIC_CACHE_HOURS", "168")))
        grouped: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
        for item in cached:
            if not isinstance(item, Mapping) or not isinstance(item.get("row"), Mapping):
                continue
            key = (str(item.get("table") or ""), str(item.get("conflict") or ""), str(item.get("schema") or "unknown"))
            grouped.setdefault(key, []).append(dict(item["row"]))
        for (table, conflict, schema), rows in grouped.items():
            if not table or not conflict:
                continue
            ok, _ = db.upsert(table, rows, conflict)
            totals[schema] = totals.get(schema, 0) + ok
            totals["cached"] += ok
        if totals["cached"]:
            log(f"GENERIC {repo}: last-good cache fallback rows={totals['cached']}")
    return totals


def main() -> None:
    db = SupabaseRest()
    candidates = db.get(
        "netrattler_source_candidates",
        filters={"status": "in.(active,fallback)", "auto_ingest": "eq.true", "cost": "eq.free"},
        order="trust_score.desc", limit_total=500,
    )
    grand: Dict[str, int] = {
        "match_results": 0, "player_stats": 0, "odds": 0,
        "identity": 0, "failed": 0, "cached": 0, "skipped": 0, "deduped": 0,
    }
    for candidate in candidates:
        totals = ingest_source(candidate, db)
        for key, value in totals.items():
            grand[key] = grand.get(key, 0) + value
    log(f"GENERIC INGEST DONE {grand}")


if __name__ == "__main__":
    main()
