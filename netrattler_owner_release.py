"""Owner release record and explicit main-branch push request. No network/send."""
import json
import os
from pathlib import Path
import re
import subprocess

RECORD = ".github/netrattler-card-release.json"
SCOPE = "netrattler-verified-original-cards"
SEND_MARKER = "[netrattler-owner-send]"

def approved(record):
    return (isinstance(record, dict) and record.get("approved") is True
            and record.get("scope") == SCOPE
            and isinstance(record.get("request_id"), str)
            and bool(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9-]+", record["request_id"])))

def explicit_send(record, *, event_name, ref, message, changed):
    return (approved(record) and event_name == "push"
            and ref == "refs/heads/main" and SEND_MARKER in message.split()
            and RECORD in changed)

def changed_files(before, after):
    if not all(isinstance(x, str) and re.fullmatch(r"[0-9a-f]{40}", x)
               and x != "0" * 40 for x in (before, after)):
        return []
    try:
        return subprocess.check_output(
            ["git", "diff", "--name-only", before, after, "--", RECORD],
            text=True, stderr=subprocess.DEVNULL, timeout=10).splitlines()
    except (subprocess.SubprocessError, OSError):
        return []

def main():
    try:
        record = json.loads(Path(RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = {}
    event = {}
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    except (KeyError, OSError, ValueError):
        pass
    event_name = os.getenv("GITHUB_EVENT_NAME", "")
    ref = os.getenv("GITHUB_REF", "")
    message = str((event.get("head_commit") or {}).get("message") or "")
    changes = changed_files(event.get("before"), event.get("after")) if event_name == "push" else []
    release = approved(record)
    request = explicit_send(record, event_name=event_name, ref=ref,
                            message=message, changed=changes)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        out.write(f"approved={str(release).lower()}\nexplicit_send={str(request).lower()}\n")
    print(f"Owner repository approval={release}, explicit push request={request}")
if __name__ == "__main__":
    main()
