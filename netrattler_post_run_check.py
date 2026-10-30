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
import re
import urllib.parse


def coverage_warnings(log_text):
    """Distinguish missing builder candidates from legitimate deduplication.

    Green runs with N generated builders and N previously delivered builder IDs
    should not raise a false zero-builder alarm. Partial sends still warn.
    """
    issues = []
    generated = [int(n) for n in re.findall(r'MASTER BUILDER[^\n]*generated=(\d+)', log_text)]
    count_generated = max(generated, default=0)
    duplicate_ids = set(re.findall(
        r'MASTER BUILDER duplicate skipped: ([a-zA-Z0-9_-]+)', log_text
    ))
    all_already_delivered = count_generated > 0 and len(duplicate_ids) >= count_generated
    # Model builders are an explicitly supported style in the same group.
    # Count only deliveries with a confirmed Telegram receipt, never attempts.
    model_delivered = any(int(n) > 0 for n in re.findall(
        r'Modell-Builder: (\d+) gesendet und mit Telegram-Receipt bestaetigt', log_text
    ))

    for line in log_text.splitlines():
        if 'Coverage:' in line and 'no_candidates' in line:
            missing = re.findall(r'([a-z0-9_]+)=no_candidates', line)
            if all_already_delivered or model_delivered:
                missing = [item for item in missing if item != 'builder']
            if missing:
                issues.append('No candidates: ' + ', '.join(missing))
        if 'Builder Engine: 0 Builder' in line and not all_already_delivered and not model_delivered:
            issues.append('Builder Engine sent zero builders')
    return list(dict.fromkeys(issues))


class LogRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Signed log downloads must not receive the GitHub API bearer token."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urllib.parse.urlsplit(req.full_url).netloc != urllib.parse.urlsplit(newurl).netloc:
            redirected.remove_header('Authorization')
        return redirected


def fetch_job_logs(run):
    token = os.getenv('GITHUB_TOKEN') or ''
    repo = os.getenv('GITHUB_REPOSITORY') or ''
    run_id = run.get('id')
    if not (token and repo and run_id):
        raise ValueError('GitHub log configuration missing')
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json'}
    url = f'https://api.github.com/repos/{repo}/actions/runs/{int(run_id)}/jobs?per_page=30'
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as response:
        jobs = json.load(response).get('jobs', [])
    chunks = []
    if not jobs or len(jobs) > 5:
        raise ValueError('Incomplete job log coverage')
    opener = urllib.request.build_opener(LogRedirectHandler())
    for job in jobs:
        jid = int(job['id'])
        url = f'https://api.github.com/repos/{repo}/actions/jobs/{jid}/logs'
        with opener.open(urllib.request.Request(url, headers=headers), timeout=30) as response:
            chunk = response.read(4000001)
            if len(chunk) > 4000000:
                raise ValueError('Job log exceeds inspection limit')
            chunks.append(chunk.decode('utf-8', 'replace'))
    logs = '\n'.join(chunks)
    if not logs.strip():
        raise ValueError('Empty job logs')
    return logs


def evaluate(run):
    name = run.get("name") or "unknown"
    status = run.get("status")
    conclusion = run.get("conclusion")
    url = run.get("html_url") or ""
    if status != "completed":
        return False, f"NETRATTLER | Run noch nicht abgeschlossen: {name}"
    if conclusion == "success":
        return True, f"NETRATTLER | OK: {name}\n{url}"
    if conclusion == "cancelled" and run.get("event") == "push":
        # A newer push replaces this verification run via Actions concurrency.
        # Cancellation is still visible in Actions, but not a production failure.
        return True, f"NETRATTLER | PUSH-TEST ABGEBROCHEN: {name}\n{url}"
    return False, f"NETRATTLER | RUN-FEHLER: {name}\nStatus: {conclusion or 'unknown'}\n{url}"


def notify(message):
    # Run status is visible in Actions only; no Telegram run alerts (user request).
    if os.getenv("NETRATTLER_RUN_ALERTS", "0") != "1":
        print(message, flush=True)
        return
    token = os.getenv("TELEGRAM_TOKEN") or ""
    chat = os.getenv("TELEGRAM_GROUP_ALERTS") or os.getenv("TELEGRAM_GROUP_STATS") or os.getenv("TELEGRAM_CHAT_ID") or ""
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
    if ok and run.get('conclusion') == 'success' and run.get('name') == 'NETRATTLER AI Tipp Bot':
        try:
            warnings = coverage_warnings(fetch_job_logs(run))
            if warnings:
                ok = False
                message = 'NETRATTLER | TIP COVERAGE WARNING\n' + '\n'.join(warnings) + '\n' + (run.get('html_url') or '')
                print(message, flush=True)
                notify(message)
        except (urllib.error.URLError, ValueError, KeyError, TimeoutError) as exc:
            ok = False
            message = 'NETRATTLER | Coverage log inspection unavailable: ' + type(exc).__name__
            print(message, flush=True)
    # Send failures; successful runs are recorded in Actions without Telegram spam.
    if not ok:
        notify(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
