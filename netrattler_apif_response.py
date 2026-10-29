"""Validate API-Football envelopes without logging credentials or response bodies."""
def checked_response(response):
    if not response.ok:
        raise RuntimeError(f"API-Football HTTP {response.status_code}")
    try:
        body = response.json()
    except ValueError:
        raise RuntimeError("API-Football invalid JSON") from None
    if not isinstance(body, dict) or body.get("errors"):
        raise RuntimeError("API-Football provider error (account, quota or request); check provider dashboard")
    rows = body.get("response")
    if not isinstance(rows, list):
        raise RuntimeError("API-Football response list missing")
    return rows
