#!/usr/bin/env python3
"""
NETRATTLER GitHub Watch V1
==========================
Lightweight repository watcher for football/odds/model projects.

- Tracks latest commit SHA and latest release/tag per repository.
- Persists immutable snapshots in existing Supabase table
  `netrattler_source_discovery` (kind=github_watch), so no SQL migration is needed.
- Writes raw snapshots to `netrattler_data_lake_raw` when available.
- On a changed commit, fetches changed files and calculates a relevance score for
  NETRATTLER (odds, props, corners, settlement, models, scrapers, APIs, etc.).
- Sends Telegram only for meaningful changes when Telegram secrets are present.
- Does not clone repositories and does not install Playwright.

ENV:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY
  GITHUB_TOKEN                  recommended (Actions GITHUB_TOKEN is enough)
  TELEGRAM_TOKEN                optional
  TELEGRAM_GROUP_STATS          optional, preferred destination
  TELEGRAM_CHAT_ID              optional fallback
  GITHUB_WATCH_NOTIFY_MIN_SCORE default 3
  GITHUB_WATCH_ALWAYS_NOTIFY    true/false, default false
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or ""
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or ""
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_GROUP_STATS") or os.getenv("TELEGRAM_CHAT_ID") or ""
NOTIFY_MIN_SCORE = int(os.getenv("GITHUB_WATCH_NOTIFY_MIN_SCORE", "3") or 3)
ALWAYS_NOTIFY = str(os.getenv("GITHUB_WATCH_ALWAYS_NOTIFY", "false")).lower() in {"1", "true", "yes", "on"}

NOW = datetime.now(timezone.utc).isoformat()
UA = "NETRATTLER-GitHub-Watch/1.0"
TIMEOUT = 12

# Targeted watchlist: user-requested projects + the most useful NETRATTLER upstreams.
WATCH_REPOS: List[Dict[str, Any]] = [
    {"repo": "ACHBIDHAN/Pinnacle_Football_Odds_Scraper", "priority": 100, "role": "pinnacle_odds_props"},
    {"repo": "gregorizeidler/footyforecast-soccer-bets-predictor", "priority": 84, "role": "betting_platform"},
    {"repo": "ajibolagenius/football-predictive-model", "priority": 94, "role": "ml_features_xg"},
    {"repo": "RaiLeonbr/evollution-soccer-pro", "priority": 62, "role": "poisson_kelly_reference"},
    {"repo": "Hicruben/theopenmodel", "priority": 96, "role": "dixon_coles_elo_calibration"},
    {"repo": "ghurault/football-prediction", "priority": 78, "role": "bayesian_dixon_coles_validation"},
    {"repo": "probberechts/soccerdata", "priority": 98, "role": "multi_source_scrapers"},
    {"repo": "statsbomb/open-data", "priority": 98, "role": "player_event_data"},
    {"repo": "jordantete/OddsHarvester", "priority": 88, "role": "odds_scraping"},
    {"repo": "withqwerty/reep", "priority": 86, "role": "entity_identity_mapping"},
    {"repo": "openfootball/football.json", "priority": 82, "role": "results_fixtures"},
    {"repo": "oseymour/ScraperFC", "priority": 90, "role": "player_stats_scrapers"},
    {"repo": "JaseZiv/worldfootballR", "priority": 70, "role": "player_stats_fbref"},
]

RELEVANCE_RULES: List[Tuple[re.Pattern[str], int, str]] = [
    (re.compile(r"player[ _-]?props?|prop[s _-]?market|bet[ _-]?builder|same[ _-]?game|sgp", re.I), 6, "player_props/builder"),
    (re.compile(r"pinnacle|kambi|bet365|bookmaker|odds|market[s]?|price[s]?", re.I), 5, "odds/markets"),
    (re.compile(r"corner|booking|card|foul|tackle|shot|sot|goalscorer|scorer", re.I), 5, "special/player markets"),
    (re.compile(r"settle|settlement|result|grade|grading|score|fixture", re.I), 5, "settlement/results"),
    (re.compile(r"dixon.?coles|poisson|xgboost|random.?forest|elo|monte.?carlo|calibrat|brier", re.I), 4, "model/calibration"),
    (re.compile(r"xg\b|ppda|deep.?completion|rolling|feature|understat|statsbomb", re.I), 4, "advanced features"),
    (re.compile(r"scrap|playwright|selenium|api|endpoint|arcadia|request|curl", re.I), 3, "scraper/api"),
    (re.compile(r"rate.?limit|403|429|cloudflare|anti.?bot|fallback|proxy", re.I), 4, "reliability/fallback"),
    (re.compile(r"readme|docs?|changelog|requirements|dependency|workflow", re.I), 1, "maintenance"),
]


def log(message: str, level: str = "INFO") -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"{ts} {level:<7} {message}", flush=True)


def stable_hash(*parts: Any) -> str:
    raw = "||".join(json.dumps(p, ensure_ascii=False, sort_keys=True, default=str) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def gh_headers() -> Dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": UA, "X-GitHub-Api-Version": "2022-11-28"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def gh_get(path: str, *, allow_404: bool = False) -> Optional[Any]:
    url = path if path.startswith("http") else f"https://api.github.com{path}"
    r = requests.get(url, headers=gh_headers(), timeout=TIMEOUT)
    if allow_404 and r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def sb_headers(prefer: str = "return=minimal") -> Dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def sb_latest_watch(repo: str) -> Optional[Dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/netrattler_source_discovery",
            headers=sb_headers(),
            params={
                "select": "source_name,payload,collected_at",
                "source_name": f"eq.{repo}",
                "kind": "eq.github_watch",
                "order": "collected_at.desc",
                "limit": "1",
            },
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            log(f"Supabase latest {repo}: HTTP {r.status_code} {r.text[:140]}", "WARN")
            return None
        rows = r.json() or []
        return rows[0] if rows else None
    except Exception as exc:
        log(f"Supabase latest {repo}: {str(exc)[:140]}", "WARN")
        return None


def sb_insert(table: str, row: Dict[str, Any], on_conflict: str = "data_hash") -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=sb_headers("resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": on_conflict},
            data=json.dumps([row], ensure_ascii=False),
            timeout=TIMEOUT,
        )
        if r.status_code in (200, 201, 204):
            return True
        log(f"Supabase {table}: HTTP {r.status_code} {r.text[:180]}", "WARN")
    except Exception as exc:
        log(f"Supabase {table}: {str(exc)[:140]}", "WARN")
    return False


def latest_release(repo: str) -> Optional[Dict[str, Any]]:
    rel = gh_get(f"/repos/{repo}/releases/latest", allow_404=True)
    if not rel:
        return None
    return {
        "tag": rel.get("tag_name"),
        "name": rel.get("name"),
        "published_at": rel.get("published_at"),
        "url": rel.get("html_url"),
    }


def changed_files(repo: str, old_sha: str, new_sha: str) -> Tuple[List[Dict[str, Any]], int]:
    if old_sha and old_sha != new_sha:
        try:
            comp = gh_get(f"/repos/{repo}/compare/{old_sha}...{new_sha}") or {}
            files = comp.get("files") or []
            return files[:100], int(comp.get("ahead_by") or len(comp.get("commits") or []))
        except Exception as exc:
            log(f"{repo}: compare fallback ({str(exc)[:100]})", "WARN")
    try:
        commit = gh_get(f"/repos/{repo}/commits/{new_sha}") or {}
        return (commit.get("files") or [])[:100], 1
    except Exception:
        return [], 0


def relevance(commit_message: str, files: Iterable[Dict[str, Any]]) -> Tuple[int, List[str]]:
    text_parts = [commit_message]
    for f in files:
        text_parts.extend([str(f.get("filename") or ""), str(f.get("patch") or "")[:6000]])
    text = "\n".join(text_parts)
    score = 0
    reasons: List[str] = []
    for pattern, weight, reason in RELEVANCE_RULES:
        if pattern.search(text):
            score += weight
            reasons.append(reason)
    return score, sorted(set(reasons))


def telegram_send(message: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "disable_web_page_preview": True},
            timeout=TIMEOUT,
        )
        return r.status_code == 200
    except Exception as exc:
        log(f"Telegram: {str(exc)[:120]}", "WARN")
        return False


def inspect_repo(cfg: Dict[str, Any]) -> Dict[str, Any]:
    repo = cfg["repo"]
    meta = gh_get(f"/repos/{repo}") or {}
    branch = meta.get("default_branch") or "main"
    latest = gh_get(f"/repos/{repo}/commits/{branch}") or {}
    sha = latest.get("sha") or ""
    commit = latest.get("commit") or {}
    message = (commit.get("message") or "").splitlines()[0][:300]
    commit_date = ((commit.get("committer") or {}).get("date") or (commit.get("author") or {}).get("date"))
    release = latest_release(repo)

    previous_row = sb_latest_watch(repo)
    previous_payload = (previous_row or {}).get("payload") or {}
    old_sha = str(previous_payload.get("sha") or "")
    old_release = ((previous_payload.get("release") or {}).get("tag") or "")
    release_tag = (release or {}).get("tag") or ""
    baseline = not bool(old_sha)
    changed = bool(old_sha and sha and old_sha != sha)
    release_changed = bool(old_sha and release_tag and release_tag != old_release)

    files: List[Dict[str, Any]] = []
    ahead_by = 0
    if changed:
        files, ahead_by = changed_files(repo, old_sha, sha)
    elif baseline:
        files, ahead_by = changed_files(repo, "", sha)

    rel_score, reasons = relevance(message, files)
    filenames = [f.get("filename") for f in files if f.get("filename")]
    payload = {
        "repo": repo,
        "role": cfg.get("role"),
        "priority": cfg.get("priority"),
        "url": meta.get("html_url") or f"https://github.com/{repo}",
        "description": meta.get("description"),
        "default_branch": branch,
        "sha": sha,
        "commit_url": latest.get("html_url"),
        "commit_message": message,
        "commit_date": commit_date,
        "pushed_at": meta.get("pushed_at"),
        "stars": meta.get("stargazers_count"),
        "forks": meta.get("forks_count"),
        "open_issues": meta.get("open_issues_count"),
        "archived": bool(meta.get("archived")),
        "release": release,
        "baseline": baseline,
        "changed": changed,
        "release_changed": release_changed,
        "ahead_by": ahead_by,
        "changed_files": filenames[:100],
        "relevance_score": rel_score,
        "relevance_reasons": reasons,
        "checked_at": NOW,
    }

    # Immutable snapshot: only a new commit/release produces a new logical row.
    row = {
        "source_name": repo,
        "url": payload["url"],
        "kind": "github_watch",
        "tags": ["github-watch", str(cfg.get("role") or "repo"), *reasons][:30],
        "score": min(9999, int(cfg.get("priority") or 0) + rel_score),
        "payload": payload,
        "data_hash": stable_hash("github_watch", repo, sha, release_tag),
        "collected_at": NOW,
    }
    saved = sb_insert("netrattler_source_discovery", row)

    lake = {
        "source": "GitHubWatch",
        "source_type": "github",
        "url": payload["url"],
        "league": "",
        "season": "",
        "match_date": None,
        "entity_type": "repository_snapshot",
        "entity_name": repo,
        "market": "",
        "category": str(cfg.get("role") or "repo"),
        "payload": payload,
        "data_hash": stable_hash("GitHubWatch", repo, sha, release_tag),
        "collected_at": NOW,
    }
    sb_insert("netrattler_data_lake_raw", lake)

    state = "BASELINE" if baseline else "CHANGED" if (changed or release_changed) else "UNCHANGED"
    log(f"{repo}: {state} sha={sha[:8]} score={rel_score} files={len(filenames)} saved={saved}")

    should_notify = not baseline and (changed or release_changed) and (ALWAYS_NOTIFY or rel_score >= NOTIFY_MIN_SCORE)
    if should_notify:
        reason_text = ", ".join(reasons[:5]) if reasons else "allgemeines Update"
        file_text = ", ".join(filenames[:5]) if filenames else "keine Dateiliste"
        msg = (
            "🔎 NETRATTLER GitHub Watch\n"
            f"{repo}\n"
            f"Commit: {message or sha[:8]}\n"
            f"Relevanz: {rel_score} · {reason_text}\n"
            f"Geändert: {file_text}\n"
            f"{payload['commit_url'] or payload['url']}"
        )
        payload["telegram_sent"] = telegram_send(msg)
    else:
        payload["telegram_sent"] = False

    return payload


# ---------------------------------------------------------------- Hugging Face datasets
HF_TERMS = [t.strip() for t in os.getenv(
    "HF_WATCH_TERMS",
    "football,soccer,premier league,bundesliga,la liga,serie a,betting odds,football odds,player stats,expected goals",
).split(",") if t.strip()]
HF_MIN_SCORE = int(os.getenv("HF_WATCH_MIN_SCORE", "5") or 5)
HF_MAX_AGE_DAYS = int(os.getenv("HF_WATCH_MAX_AGE_DAYS", "120") or 120)
_HF_NOISE = re.compile(r"american.?football|\bnfl\b|fantasy.?premier|image|vision|video|audio|speech|tweet|sentiment|commentary", re.I)


def hf_seen() -> Dict[str, str]:
    """dataset id -> last stored lastModified (keyless HF datasets already recorded)."""
    out: Dict[str, str] = {}
    if not SUPABASE_URL or not SUPABASE_KEY:
        return out
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/netrattler_source_discovery", headers=sb_headers(), timeout=TIMEOUT,
                         params={"select": "source_name,payload->>last_modified", "kind": "eq.hf_dataset", "limit": "5000"})
        for row in (r.json() if r.ok else []) or []:
            out[row.get("source_name")] = row.get("last_modified") or ""
    except Exception as exc:
        log(f"HF seen: {str(exc)[:120]}", "WARN")
    return out


def inspect_huggingface() -> Dict[str, Any]:
    seen = hf_seen()
    first_run = not seen
    found: Dict[str, Dict[str, Any]] = {}
    for term in HF_TERMS:
        try:
            r = requests.get("https://huggingface.co/api/datasets", timeout=TIMEOUT, headers={"User-Agent": UA},
                             params={"search": term, "sort": "lastModified", "direction": "-1", "limit": "50", "full": "true"})
            items = r.json() if r.ok else []
        except Exception as exc:
            log(f"HF {term}: {str(exc)[:120]}", "WARN")
            continue
        for it in items if isinstance(items, list) else []:
            did = str(it.get("id") or "")
            if not did or did in found:
                continue
            text = " ".join([did, str(it.get("description") or "")[:600], " ".join(map(str, it.get("tags") or []))])
            if _HF_NOISE.search(text) and not re.search(r"odds|bet", text, re.I):
                continue
            mod = str(it.get("lastModified") or "")
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(mod.replace("Z", "+00:00"))).days
            except Exception:
                age = 9999
            if age > HF_MAX_AGE_DAYS:
                continue
            score, reasons = 0, []
            for pattern, pts, label in RELEVANCE_RULES:
                if pattern.search(text):
                    score += pts
                    reasons.append(label)
            if re.search(r"football|soccer", text, re.I):
                score += 2
            found[did] = {"id": did, "last_modified": mod, "age_days": age, "downloads": it.get("downloads"),
                          "likes": it.get("likes"), "gated": bool(it.get("gated")), "score": score, "reasons": reasons,
                          "url": f"https://huggingface.co/datasets/{did}"}
    new_or_updated = []
    for d in found.values():
        prev = seen.get(d["id"])
        if prev is None or (prev and prev != d["last_modified"]):
            d["state"] = "NEW" if prev is None else "UPDATED"
            new_or_updated.append(d)
            sb_insert("netrattler_source_discovery", {
                "source_name": d["id"], "url": d["url"], "kind": "hf_dataset",
                "tags": ["hf-dataset", *d["reasons"]][:30], "score": d["score"], "payload": d,
                "data_hash": stable_hash("hf_dataset", d["id"], d["last_modified"]), "collected_at": NOW,
            })
    relevant = sorted([d for d in new_or_updated if d["score"] >= HF_MIN_SCORE and not d["gated"]],
                      key=lambda x: (x["score"], x.get("downloads") or 0), reverse=True)
    log(f"HF datasets: found={len(found)} new/updated={len(new_or_updated)} relevant={len(relevant)} first_run={first_run}")
    if relevant:
        lines = ["🤗 NETRATTLER Hugging Face Watch" + (" (Erstlauf)" if first_run else "")]
        for d in relevant[:8]:
            lines.append(f"• {d['id']} · {d['state']} · Relevanz {d['score']} · {', '.join(d['reasons'][:3]) or 'football'}\n  {d['url']}")
        if len(relevant) > 8:
            lines.append(f"+{len(relevant) - 8} weitere")
        telegram_send("\n".join(lines))
    return {"found": len(found), "new_or_updated": len(new_or_updated), "relevant": [d["id"] for d in relevant[:20]]}


DISCOVERY_QUERIES = (
    "football odds scraper",
    "soccer player stats scraper",
    "football betting odds api",
    "soccer player props",
)


DISCOVERY_LOG: List[Dict[str, Any]] = []


def discover_new_repos() -> List[Dict[str, Any]]:
    """Monthly GitHub search for new, active football odds/stats repos that are not on the watchlist yet.
    Report only; nothing is installed or run automatically."""
    known = {c["repo"].lower() for c in WATCH_REPOS}
    seen: Dict[str, Dict[str, Any]] = {}
    headers = {"Accept": "application/vnd.github+json"}
    tok = os.getenv("GITHUB_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    for q in DISCOVERY_QUERIES:
        try:
            r = requests.get("https://api.github.com/search/repositories", headers=headers, timeout=25,
                             params={"q": f"{q} pushed:>{(datetime.now(timezone.utc) - timedelta(days=120)).date()} stars:>5",
                                     "sort": "stars", "order": "desc", "per_page": 8})
            DISCOVERY_LOG.append({"q": q, "http": r.status_code, "n": len(r.json().get("items", [])) if r.ok else 0})
            if not r.ok:
                continue
            for it in r.json().get("items", []):
                name = it.get("full_name", "")
                if name.lower() in known or it.get("archived") or name in seen:
                    continue
                seen[name] = {"repo": name, "stars": it.get("stargazers_count"), "pushed_at": it.get("pushed_at"),
                              "description": (it.get("description") or "")[:140], "license": (it.get("license") or {}).get("spdx_id")}
        except Exception as exc:
            log(f"discovery '{q}': {str(exc)[:100]}", "WARN")
    return sorted(seen.values(), key=lambda x: -(x.get("stars") or 0))[:15]


def main() -> int:
    log("=" * 68)
    log("NETRATTLER GitHub Watch V1 startet")
    log(f"Watchlist={len(WATCH_REPOS)} · notify_min_score={NOTIFY_MIN_SCORE}")
    log("=" * 68)

    results: List[Dict[str, Any]] = []
    failures = 0
    for cfg in WATCH_REPOS:
        try:
            results.append(inspect_repo(cfg))
        except Exception as exc:
            failures += 1
            log(f"{cfg['repo']}: FAIL {str(exc)[:180]}", "WARN")

    changed = [r for r in results if r.get("changed") or r.get("release_changed")]
    relevant = [r for r in changed if int(r.get("relevance_score") or 0) >= NOTIFY_MIN_SCORE]
    summary = {
        "checked_at": NOW,
        "watch_count": len(WATCH_REPOS),
        "ok": len(results),
        "failures": failures,
        "changed": len(changed),
        "relevant_changes": len(relevant),
        "repos": results,
    }
    if str(os.getenv("HF_WATCH", "true")).lower() not in {"0", "false", "no", "off"}:
        try:
            summary["huggingface"] = inspect_huggingface()
        except Exception as exc:
            log(f"HF watch: FAIL {str(exc)[:160]}", "WARN")
    try:
        summary["discovered"] = discover_new_repos()
        sb_insert("netrattler_source_discovery", {
            "source_name": "github_discovery_run", "url": "https://github.com", "kind": "github_discovery_run",
            "tags": ["github-discovery"], "score": len(summary["discovered"]), "payload": {"log": DISCOVERY_LOG},
            "data_hash": stable_hash("github_discovery_run", str(NOW)), "collected_at": NOW})
        for d in summary["discovered"]:
            sb_insert("netrattler_source_discovery", {
                "source_name": d["repo"], "url": f"https://github.com/{d['repo']}", "kind": "github_discovery",
                "tags": ["github-discovery"], "score": int(d.get("stars") or 0), "payload": d,
                "data_hash": stable_hash("github_discovery", d["repo"], str(NOW)[:7]), "collected_at": NOW})
    except Exception as exc:
        log(f"discovery: FAIL {str(exc)[:160]}", "WARN")
    with open("netrattler_github_watch_summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    log(f"Fertig: ok={len(results)} fail={failures} changed={len(changed)} relevant={len(relevant)}")
    return 0 if results or summary.get("huggingface") else 2


if __name__ == "__main__":
    raise SystemExit(main())
