"""Schreibt pro Lauf und Quelle einen Gesundheitseintrag nach Supabase source_health.

So lässt sich per SQL sehen, ob ein "grüner" Workflow wirklich Daten geliefert hat.
Non-fatal: jeder Fehler wird ignoriert.
"""
from __future__ import annotations

import os
from typing import Optional

import requests


def record(workflow: str, source: str, rows_found: int, rows_saved: Optional[int] = None,
           note: str = "", ok: Optional[bool] = None) -> None:
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if not url or not key:
        return
    try:
        requests.post(
            f"{url}/rest/v1/source_health",
            headers={"apikey": key, "Authorization": f"Bearer {key}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            json=[{
                "workflow": workflow, "source": source,
                "rows_found": int(rows_found or 0),
                "rows_saved": None if rows_saved is None else int(rows_saved),
                "ok": bool(rows_found) if ok is None else bool(ok),
                "note": str(note or "")[:400],
            }],
            timeout=15,
        )
    except Exception:
        pass
