#!/usr/bin/env python3
"""NETRATTLER BetClone platform evidence report.

Distinguish operator listings, reachable homepages, labelled prices on a
homepage and a production *validated* odds integration. Never infer the latter
from HTTP 200, guessed domains or unlabelled 1xBet market codes.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, Mapping

# Integration evidence is a manually reviewed, fail-closed allowlist.
# 1xBet odds_history is currently a SHADOW source: raw numeric market IDs
# still lack corroborated market-period and selection semantics.
VERIFIED_BETCLONE_LIVE_FAMILIES: frozenset[str] = frozenset()
SHADOW_FAMILIES: frozenset[str] = frozenset({"1xbet"})

# These are verified sources in NETRATTLER, but are not represented by these
# ten BetClone platform-family pages. Never credit BetClone with their totals.
INDEPENDENT_VERIFIED_ODDS_COLLECTORS = ("bwin", "kambi", "pinnacle", "matchbook")


def summarize(audit: Mapping[str, Any]) -> Dict[str, Any]:
    catalogue = audit.get("catalogue") or {}
    sites = audit.get("sites") or []
    guesses = audit.get("unverified_candidate_probe_results") or []
    if not isinstance(catalogue, dict) or not isinstance(sites, list) or not isinstance(guesses, list):
        raise ValueError("Invalid BetClone audit structure")
    platforms: Dict[str, Any] = {}
    for family, entry in sorted(catalogue.items()):
        if not isinstance(entry, dict):
            raise ValueError("Invalid catalogue entry")
        site_rows = [r for r in sites if isinstance(r, dict) and r.get("platform") == family]
        guess_rows = [r for r in guesses if isinstance(r, dict) and r.get("platform") == family]
        sstates = Counter(str(x.get("state") or "unknown") for x in site_rows)
        gstates = Counter(str(x.get("state") or "unknown") for x in guess_rows)
        has_homepage_prices = sum(max(0, int(x.get("verified_odds") or 0)) for x in site_rows)
        # A candidate price-bearing JSON object is still not a validated feed.
        live = family in VERIFIED_BETCLONE_LIVE_FAMILIES
        shadow = family in SHADOW_FAMILIES and not live
        platforms[family] = {
            "listed_bookmakers": len(entry.get("bookmakers") or []),
            "curated_homepages_checked": len(site_rows),
            "unverified_candidate_domains_checked": len(guess_rows),
            "curated_homepage_states": dict(sstates),
            "unverified_candidate_states": dict(gstates),
            "structured_homepage_price_candidates": has_homepage_prices,
            "validated_production_odds_feed": live,
            "raw_shadow_feed": shadow,
            "integration_status": "production_verified" if live else
                                  "raw_shadow_unlabelled_markets" if shadow else
                                  "no_verified_production_feed",
        }
    catalogue_count = sum(p["listed_bookmakers"] for p in platforms.values())
    if catalogue_count != int(audit.get("catalogue_total_listed_entries") or 0):
        raise ValueError("Catalogue count does not match actual listed entries")

    # An inflated catalogue total is not proof that the per-brand audit
    # accounted for every operator. Validate the full family+brand matrix too.
    matrix = audit.get("catalogue_audit_matrix")
    matrix_complete = False
    if matrix is not None:
        if not isinstance(matrix, list):
            raise ValueError("Invalid bookmaker audit matrix")
        expected = {
            (family, brand.casefold())
            for family, row in catalogue.items()
            for brand in row.get("bookmakers") or []
        }
        actual = [
            (str(row.get("platform") or ""), str(row.get("brand") or "").casefold())
            for row in matrix if isinstance(row, dict)
        ]
        if len(actual) != len(matrix) or len(actual) != len(expected) or set(actual) != expected:
            raise ValueError("Incomplete or duplicated BetClone bookmaker audit matrix")
        matrix_complete = True

    return {
        "report": "netrattler_betclone_integration_status",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_audit_utc": audit.get("checked_at_utc"),
        "family_count": len(platforms),
        "catalogue_matrix_complete": matrix_complete,
        "listed_bookmaker_entries": catalogue_count,
        "curated_homepages_checked": sum(p["curated_homepages_checked"] for p in platforms.values()),
        "unverified_candidate_domains_checked": sum(p["unverified_candidate_domains_checked"] for p in platforms.values()),
        "families_with_verified_production_odds": sum(p["validated_production_odds_feed"] for p in platforms.values()),
        "families_with_shadow_feed": sum(p["raw_shadow_feed"] for p in platforms.values()),
        "separate_verified_collectors_not_attributed_to_betclone": list(INDEPENDENT_VERIFIED_ODDS_COLLECTORS),
        "warning": "HTTP 200, affiliated brand, guessed domain or JSON price does not prove a verified usable odds feed",
        "platforms": platforms,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--audit", default="netrattler_betclone_hardprobe.json")
    p.add_argument("--output", default="netrattler_betclone_integration_status.json")
    args = p.parse_args()
    audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    status = summarize(audit)
    Path(args.output).write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    print("BETCLONE_INTEGRATION family_count=", status["family_count"],
          "brands=", status["listed_bookmaker_entries"],
          "curated_checked=", status["curated_homepages_checked"],
          "guessed_checked=", status["unverified_candidate_domains_checked"],
          "validated_family_feeds=", status["families_with_verified_production_odds"],
          "shadow_family_feeds=", status["families_with_shadow_feed"],
          "brand_matrix_complete=", status["catalogue_matrix_complete"], flush=True)
    for family, info in status["platforms"].items():
        print("BETCLONE_INTEGRATION_FAMILY", family,
              "listed=", info["listed_bookmakers"],
              "status=", info["integration_status"],
              "homepage_states=", info["curated_homepage_states"], flush=True)


if __name__ == "__main__":
    main()
