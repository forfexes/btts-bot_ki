#!/usr/bin/env python3
"""Read-only official SportScore fixture discovery audit.

This process is deliberately incapable of Telegram dispatch or SQLite writes.
It never treats an unverified match clock as a signal.
SportScore's free developer API requires visible attribution on published pages:
https://sportscore.com/developers/ .
"""
from __future__ import annotations

import json
import requests

from netrattler_lmg_external_sources import (
    parse_sportscore, sportscore_discovery_report, SOURCE_URLS
)


def probe(*, get=requests.get):
    response=get(
        SOURCE_URLS["sportscore"],
        params={"sport":"football","limit":50,"src":"netrattler-readonly-qa"},
        headers={"Accept":"application/json","User-Agent":"NETRATTLER-ReadOnly-SourceAudit/1.0"},
        timeout=12,
    )
    response.raise_for_status()
    payload=response.json()
    report=sportscore_discovery_report(payload)
    # Do NOT turn unmatched widget results into generated betting picks.
    # Output only aggregate metadata and the provider's required attribution.
    report["candidate_identities_verified"]=len(parse_sportscore(payload))
    print("LMG_SPORTSCORE_READ_ONLY",json.dumps(report,sort_keys=True),flush=True)
    return report


if __name__=="__main__":
    probe()
