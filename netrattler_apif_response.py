"""Validate API-Football envelopes without logging credentials or response bodies."""
def checked_response(response):
    if not response.ok:
        raise RuntimeError(f"API-Football HTTP {response.status_code}")
    try:
        body = response.json()
    except ValueError:
        raise RuntimeError("API-Football invalid JSON") from None
    if not isinstance(body, dict) or body.get("errors"):
        errs = body["errors"]
        keys = ",".join(sorted(str(k) for k in errs))[:60] if isinstance(errs, dict) else "list"
        suspended = isinstance(errs, dict) and "suspended" in str(errs.get("access", "")).lower()
        hint = "account suspended" if suspended else "account, quota or request"
        raise RuntimeError(f"API-Football provider error ({hint}; fields: {keys}); check provider dashboard")
    rows = body.get("response")
    if not isinstance(rows, list):
        raise RuntimeError("API-Football response list missing")
    return rows

def number(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        n = float(v)
        return int(n) if n >= 0 and n.is_integer() else None
    except (ValueError, TypeError, OverflowError):
        return None
