"""Pinned, independently scoped Last Minute Goal artwork release check."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
RELEASE=ROOT/".github/netrattler-last-minute-release.json"
PLATE=ROOT/"last_minute_owner_20261122/last_minute_clean_plate.png"
SOURCE=ROOT/"last_minute_owner_20261122/last_minute_user_original.png"
PLATE_BLOB="7386c75bbd32ba78ebeac3d4169a5104e2173741"
SOURCE_BLOB="5f5f0895b82b297684eb195f5e29928d6835670e"

def git_blob(path):
    raw=path.read_bytes()
    return hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()

def check_release():
    try:
        record=json.loads(RELEASE.read_text(encoding="utf-8"))
        return (record.get("owner_authorized") is True and
                record.get("scope")=="last_minute_goal" and
                record.get("source_git_blob")==SOURCE_BLOB and
                record.get("plate_git_blob")==PLATE_BLOB and
                git_blob(PLATE)==PLATE_BLOB and git_blob(SOURCE)==SOURCE_BLOB)
    except (OSError,ValueError,AttributeError):
        return False
