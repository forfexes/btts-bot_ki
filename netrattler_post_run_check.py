#!/usr/bin/env python3
"""Post-run monitor: check actual GitHub conclusion, notify Telegram on failure.

Uses only GitHub's built-in workflow_run event and standard library.
Never executes downloaded artifacts or untrusted workflow code.
"""
import json
import os
import sys
import urllib.error
import urllib.request


def evaluate(run):
    name = run.get("name") or "unknown"
    status = run.get("status")
    conclusion = run.get("conclusion")
    url = run.get("html_url") or ""
    if status != "completed":
        return False, f"NETRATTLER | Run noch nicht abgeschlossen: {name}"
    if conclusion == "success":
        return True, f"NETRATTLER | OK: {name}\n{url}"
    return False, f"NETRATTLER | RUN-FEHLER: {name}\nStatus: {conclusion or 'unknown'}\n{url}"


def notify(message):
    token = os.getenv("TELEGRAM_TOKEN") or ""
    chat = os.getenv("TELEGRAM_GROUP_STATS") or os.getenv("TELEGRAM_CHAT_ID") or ""
    if not token or not chat:
        print("Telegram not configured; status visible in Actions", flush=True)
        return
    payload = json.dumps({"chat_id": chat, "text": message[:3900]}).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 200:
                print(f"Telegram HTTP {response.status}", flush=True)
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"Telegram notification failed: {type(exc).__name__}", flush=True)


def main():
    path = os.getenv("GITHUB_EVENT_PATH")
    if not path:
        raise SystemExit("GITHUB_EVENT_PATH missing")
    with open(path, encoding="utf-8") as handle:
        event = json.load(handle)
    run = event.get("workflow_run") or {}
    ok, message = evaluate(run)
    print(message, flush=True)
    # Send failures; successful runs are recorded in Actions without Telegram spam.
    if not ok:
        notify(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
