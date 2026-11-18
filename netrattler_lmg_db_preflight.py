#!/usr/bin/env python3
"""Fail-closed check before live Goal Hunter scans when Supabase is restricted.

Do not waste source requests, send untracked Telegram tips, or try to route
around provider quota restrictions. Automatically resumes if REST is available.
"""
import os
import sys
from urllib.parse import urlparse

import requests


EXPECTED_HOST = "sugycqnjncgfheueqaee.supabase.co"


def preflight(get=requests.get):
    base=(os.getenv("SUPABASE_URL") or "").rstrip("/")
    key=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if not base or not key or urlparse(base).scheme != "https":
        return "missing_credentials"
    if urlparse(base).hostname != EXPECTED_HOST:
        return "wrong_supabase_project"
    try:
        resp=get(base+"/rest/v1/netrattler_lmg_alerts",
                 headers={"apikey":key,"Authorization":"Bearer "+key},
                 params={"select":"alert_key","limit":"1"},timeout=15)
    except requests.RequestException:
        return "network_unavailable"
    if resp.status_code == 200:
        return "ready"
    if resp.status_code == 402:
        try:
            message=str((resp.json() or {}).get("message") or "").lower()
        except (ValueError,TypeError,AttributeError):
            message=""
        return "blocked_egress_quota" if "egress" in message else "blocked_api_quota"
    if resp.status_code in (401,403):
        return "credentials_rejected"
    return "rest_http_"+str(resp.status_code)


def main():
    status=preflight()
    print("LMG_STORAGE_PREFLIGHT",status,flush=True)
    if status != "ready":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
