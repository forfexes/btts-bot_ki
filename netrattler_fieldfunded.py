"""FieldFunded shadow adapter. Requires FIELDFUNDED_API_KEY; endpoint paths are configurable."""
from __future__ import annotations
import os, requests
BASE=os.getenv("FIELDFUNDED_BASE_URL","https://api.fieldfunded.com").rstrip("/")
def _get(path,params=None):
    key=os.getenv("FIELDFUNDED_API_KEY","").strip()
    if not key:return None
    headers={"Authorization":f"Bearer {key}","x-api-key":key}
    r=requests.get(BASE+path,params=params or {},headers=headers,timeout=15); r.raise_for_status(); return r.json()
def settlements(params=None): return _get("/v1/settlements",params)
def probe(path="/v1/events",params=None): return _get(path,params)
