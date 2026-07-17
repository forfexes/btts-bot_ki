#!/usr/bin/env python3
"""Daily football exposure limits for builders.

The manager loads today's existing ledger from Supabase, caps proposed stakes by
match/player/league/market/daily exposure and records only picks actually sent.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import requests


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().strip().split())


def _hash(*parts: Any) -> str:
    return hashlib.sha256("||".join(map(str, parts)).encode("utf-8")).hexdigest()[:48]


class ExposureManager:
    def __init__(self, supabase_url: str = "", supabase_key: str = "") -> None:
        self.url = (supabase_url or os.getenv("SUPABASE_URL") or "").rstrip("/")
        self.key = supabase_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
        self.today = date.today().isoformat()
        self.daily_cap = float(os.getenv("NETRATTLER_DAILY_EXPOSURE_CAP", "5.0"))
        self.match_cap = float(os.getenv("NETRATTLER_MATCH_EXPOSURE_CAP", "1.25"))
        self.player_cap = float(os.getenv("NETRATTLER_PLAYER_EXPOSURE_CAP", "0.75"))
        self.league_cap = float(os.getenv("NETRATTLER_LEAGUE_EXPOSURE_CAP", "2.0"))
        self.market_cap = float(os.getenv("NETRATTLER_MARKET_EXPOSURE_CAP", "2.0"))
        self.used: Dict[str, Dict[str, float]] = {
            "daily": defaultdict(float), "match": defaultdict(float), "player": defaultdict(float),
            "league": defaultdict(float), "market": defaultdict(float),
        }
        self._load()

    def _headers(self, prefer: str = "return=minimal") -> Dict[str, str]:
        return {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Content-Type": "application/json", "Prefer": prefer}

    def _load(self) -> None:
        if not self.url or not self.key:
            return
        try:
            response = requests.get(
                f"{self.url}/rest/v1/netrattler_exposure_ledger",
                headers=self._headers(),
                params={"select": "*", "exposure_date": f"eq.{self.today}", "status": "eq.active", "limit": "5000"},
                timeout=12,
            )
            if not response.ok:
                return
            for row in response.json() or []:
                stake = float(row.get("stake") or 0.0)
                self.used["daily"]["all"] += stake
                for dim, column in (("match", "match_keys"), ("player", "player_keys"), ("league", "league_keys"), ("market", "market_keys")):
                    values = row.get(column) or []
                    if isinstance(values, str):
                        try: values = json.loads(values)
                        except json.JSONDecodeError: values = []
                    for value in values if isinstance(values, list) else []:
                        self.used[dim][_norm(value)] += stake
        except Exception:
            return

    def _keys(self, pick: Any) -> Dict[str, List[str]]:
        legs = list(getattr(pick, "legs", []) or [])
        return {
            "match": sorted({_norm(getattr(leg, "match", "")) for leg in legs if _norm(getattr(leg, "match", ""))}),
            "player": sorted({_norm(getattr(leg, "player", "")) for leg in legs if _norm(getattr(leg, "player", ""))}),
            "league": sorted({_norm(getattr(leg, "league", "")) for leg in legs if _norm(getattr(leg, "league", ""))}),
            "market": sorted({_norm(getattr(leg, "category", "") or getattr(leg, "market", "")) for leg in legs if _norm(getattr(leg, "category", "") or getattr(leg, "market", ""))}),
        }

    def adjust_builder(self, pick: Any, proposed: float) -> float:
        if proposed <= 0:
            return 0.0
        keys = self._keys(pick)
        remaining = [self.daily_cap - self.used["daily"]["all"]]
        caps = {"match": self.match_cap, "player": self.player_cap, "league": self.league_cap, "market": self.market_cap}
        for dim, values in keys.items():
            for value in values:
                remaining.append(caps[dim] - self.used[dim][value])
        allowed = max(0.0, min([proposed] + remaining))
        return round(allowed, 2) if allowed >= 0.02 else 0.0

    def record_builder(self, pick: Any, stake: float) -> None:
        if stake <= 0:
            return
        keys = self._keys(pick)
        self.used["daily"]["all"] += stake
        for dim, values in keys.items():
            for value in values:
                self.used[dim][value] += stake
        if not self.url or not self.key:
            return
        row = {
            "exposure_id": _hash(self.today, getattr(pick, "builder_id", "")),
            "exposure_date": self.today,
            "pick_id": getattr(pick, "builder_id", ""),
            "pick_type": "builder",
            "stake": stake,
            "match_keys": keys["match"], "player_keys": keys["player"],
            "league_keys": keys["league"], "market_keys": keys["market"],
            "status": "active", "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            requests.post(
                f"{self.url}/rest/v1/netrattler_exposure_ledger",
                headers=self._headers("resolution=merge-duplicates,return=minimal"),
                params={"on_conflict": "exposure_id"}, json=row, timeout=12,
            )
        except Exception:
            pass
