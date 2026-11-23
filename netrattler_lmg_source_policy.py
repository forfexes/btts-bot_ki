"""Goal Hunter's documented source *selection* policy (2026-11-23).

This module does not fetch, scrape, send or persist anything. It protects
source registration from the mistaken assumption that a live-score website
automatically grants permission to poll its internal APIs. All provider data
used for a published pick must additionally pass strict event matching.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceDecision:
    role: str
    automated_access: str
    goal_hunter: str
    note: str


DECISIONS = {
    "fotmob": SourceDecision(
        "football fixtures + observed match stats", "existing_guarded_adapter",
        "existing", "Keep existing fallback and identity checks; assess data-use rights"),
    "espn": SourceDecision(
        "football discovery and observed match stats", "existing_guarded_adapter",
        "existing", "Keep existing exact fixture-matching; not a licensed odds feed"),
    "sportscore": SourceDecision(
        "public football scores", "documented_public_widget",
        "shadow_only", "No automatic tip generation; attribution and licence review"),
    "sofascore": SourceDecision(
        "football results and deeper consumer statistics", "partner_only",
        "not_eligible", "Provider says sports data API endpoints are unavailable"),
    "flashscore": SourceDecision(
        "consumer live scores", "no_verified_public_api",
        "not_eligible", "Do not rely on undocumented feed/scraping"),
    "onefootball": SourceDecision(
        "consumer football scores and news", "no_verified_public_api",
        "not_eligible", "Provider-owned/licensed third-party data"),
    "sporteden": SourceDecision(
        "consumer live scores and statistics", "automated_extraction_prohibited",
        "not_eligible", "Terms prohibit scraping and extraction without permission"),
    "iscore_sports": SourceDecision(
        "user-entered local scorekeeping", "operator_controlled",
        "not_relevant", "Not a global live professional fixture feed"),
    "scoreholio": SourceDecision(
        "event and tournament scoring", "operator_controlled",
        "not_relevant", "Not a global live professional fixture feed"),
    "keepthescore": SourceDecision(
        "self-managed scoreboards and scores", "own_scoreboards_api",
        "not_relevant", "API controls own scoreboards, not external leagues"),
}


# Official/first-party provenance. These are POSSIBLE common upstream feeds,
# not proof that two apps used identical match events for every competition.
# This table never grants permission to access the app websites automatically.
UPSTREAM_EVIDENCE = {
    "flashscore": {
        "supplier": "opta",
        "scope": "primary football provider",
        "url": "https://www.flashscore.com/faq/data/",
    },
    "fotmob": {
        "supplier": "opta",
        "scope": "live match statistics in official partnership",
        "url": "https://www.socceraid.org.uk/news/fotmob-partnership/",
    },
    "onefootball": {
        "supplier": "opta",
        "scope": "selected match coverage / data products",
        "url": "https://www.statsperform.com/events/what-every-storyteller-and-creator-needs-to-know-about-world-cup-coverage-in-2026/",
    },
    "sofascore": {
        "supplier": "opta",
        "scope": "some historical and tournament analyses only; NOT all stats",
        "url": "https://www.statsperform.com/opta-euros-copa-america-2024/",
    },
}


def shared_upstream_risk(*providers: str) -> dict:
    """Audit possible common provenance; does NOT declare confirmed duplicates.

    Never count differently branded apps as independent corroboration without
    comparing actual metric provenance for that event and timestamp.
    """
    labels = []
    seen = set()
    for provider in providers:
        label = str(provider or "").strip().casefold().replace(" ", "_")
        decision(label)  # unregistered sources fail closed
        if label not in seen:
            seen.add(label)
            labels.append(label)
    by_supplier = {}
    for label in labels:
        evidence = UPSTREAM_EVIDENCE.get(label)
        if evidence:
            by_supplier.setdefault(evidence["supplier"], []).append(label)
    return {
        "possible_common_suppliers": {
            supplier: group for supplier, group in by_supplier.items()
            if len(group) >= 2
        },
        "unknown_lineage": [
            label for label in labels if label not in UPSTREAM_EVIDENCE
        ],
        "confirmed_independent_feeds": 0,
        "warning": "shared_supplier_possible_not_event_level_proof",
    }


def decision(provider: str) -> SourceDecision:
    """Fail closed for future unreviewed service names."""
    normalized = str(provider or "").strip().casefold().replace(" ", "_")
    if normalized not in DECISIONS:
        raise ValueError("goal_hunter_unreviewed_source")
    return DECISIONS[normalized]


def may_provide_live_tip_data(provider: str) -> bool:
    """No customer-facing source can enter tips merely from having a website."""
    return decision(provider).goal_hunter == "existing"


def may_provide_shadow_discovery(provider: str) -> bool:
    return decision(provider).goal_hunter in {"existing", "shadow_only"}
