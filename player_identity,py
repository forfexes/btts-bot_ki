import os
import time
import requests
from typing import Any, Dict, List, Optional

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

class SupabaseV4:
    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        self.url = (url or SUPABASE_URL).rstrip("/")
        self.key = key or SUPABASE_KEY
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL oder SUPABASE_KEY fehlt")
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def upsert(self, table: str, rows: List[Dict[str, Any]], on_conflict: str, batch_size: int = 500) -> int:
        if not rows:
            return 0
        total = 0
        headers = dict(self.headers)
        headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        url = f"{self.url}/rest/v1/{table}?on_conflict={on_conflict}"
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i+batch_size]
            r = requests.post(url, headers=headers, json=batch, timeout=60)
            if not r.ok:
                raise RuntimeError(f"Supabase upsert {table} failed {r.status_code}: {r.text[:500]}")
            try:
                data = r.json()
                total += len(data) if isinstance(data, list) else len(batch)
            except Exception:
                total += len(batch)
            time.sleep(0.15)
        return total

    def insert(self, table: str, row: Dict[str, Any]) -> Dict[str, Any]:
        headers = dict(self.headers)
        headers["Prefer"] = "return=representation"
        r = requests.post(f"{self.url}/rest/v1/{table}", headers=headers, json=row, timeout=30)
        if not r.ok:
            raise RuntimeError(f"Supabase insert {table} failed {r.status_code}: {r.text[:500]}")
        data = r.json()
        return data[0] if isinstance(data, list) and data else {}

    def select(self, table: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
        r = requests.get(f"{self.url}/rest/v1/{table}", headers=self.headers, params=params, timeout=60)
        if not r.ok:
            raise RuntimeError(f"Supabase select {table} failed {r.status_code}: {r.text[:500]}")
        return r.json()

    def rpc_or_empty(self, fn: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        r = requests.post(f"{self.url}/rest/v1/rpc/{fn}", headers=self.headers, json=payload, timeout=60)
        if not r.ok:
            return []
        try:
            return r.json()
        except Exception:
            return []
