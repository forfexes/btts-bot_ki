#!/usr/bin/env python3
"""
NETRATTLER Supabase Client
Wrapper für fbref_props_scraper, sofascore_scraper, flashscore_scraper
"""
import os, time, requests
from typing import Any, Dict, List

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")

class SupabaseRest:
    def __init__(self, url=None, key=None):
        self.url = (url or SUPABASE_URL).rstrip("/")
        self.key = key or SUPABASE_KEY
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def upsert(self, table: str, rows: List[Dict], on_conflict: str = "", batch_size: int = 400) -> int:
        if not rows: return 0
        h = dict(self.headers)
        h["Prefer"] = "resolution=merge-duplicates,return=minimal"
        url = f"{self.url}/rest/v1/{table}"
        if on_conflict: url += f"?on_conflict={on_conflict}"
        total = 0
        for i in range(0, len(rows), batch_size):
            chunk = rows[i:i+batch_size]
            try:
                r = requests.post(url, headers=h, json=chunk, timeout=60)
                if not r.ok:
                    print(f"⚠️ UPSERT {table} {r.status_code}: {r.text[:200]}")
                    continue
                total += len(chunk)
            except Exception as e:
                print(f"⚠️ UPSERT {table}: {e}")
            time.sleep(0.1)
        return total

    def select(self, table: str, params: Dict) -> List[Dict]:
        try:
            r = requests.get(f"{self.url}/rest/v1/{table}", headers=self.headers, params=params, timeout=60)
            return r.json() if r.ok else []
        except: return []

    def insert(self, table: str, row: Dict) -> Dict:
        h = dict(self.headers); h["Prefer"] = "return=representation"
        r = requests.post(f"{self.url}/rest/v1/{table}", headers=h, json=row, timeout=30)
        if not r.ok: raise RuntimeError(f"insert {table} {r.status_code}: {r.text[:200]}")
        data = r.json()
        return data[0] if isinstance(data, list) and data else {}
