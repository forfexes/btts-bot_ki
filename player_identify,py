import re
import unicodedata
from typing import Optional

TEAM_WORDS = {
    "yes", "no", "over", "under", "both", "either", "team", "first", "second",
    "to", "score", "scored", "goal", "goals", "match", "half", "total",
    "home", "away", "draw", "none", "other"
}

def strip_accents(text: str) -> str:
    text = text or ""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )

def norm_name(name: str) -> str:
    n = strip_accents(name or "").lower()
    n = re.sub(r"[^a-z0-9\s\-\']", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n

def looks_like_player(name: str) -> bool:
    n = norm_name(name)
    if not n:
        return False
    if n in TEAM_WORDS:
        return False
    parts = [p for p in n.replace("-", " ").split() if p]
    if len(parts) >= 2:
        return True
    # Einzelname erlaubt, aber nicht generische Wörter.
    if len(parts) == 1 and len(parts[0]) >= 4 and parts[0] not in TEAM_WORDS:
        return True
    return False

def extract_player_from_description(desc: str) -> Optional[str]:
    """
    Beispiele:
    - James Rodriguez To Score -> James Rodriguez
    - Luka Modric Anytime Goalscorer -> Luka Modric
    - Virgil van Dijk To Be Booked -> Virgil van Dijk
    """
    if not desc:
        return None
    d = re.sub(r"\s+", " ", desc).strip()

    patterns = [
        r"^(.*?)\s+(?:anytime\s+)?(?:to\s+score|goalscorer|goal scorer)\b",
        r"^(.*?)\s+(?:to\s+be\s+booked|player\s+to\s+be\s+booked|card|yellow card)\b",
        r"^(.*?)\s+(?:to\s+assist|anytime assist|assist)\b",
        r"^(.*?)\s+(?:\d+\+?\s+)?(?:shots? on target|sot|shots?|tackles?|fouls?|offsides?)\b",
    ]
    for pat in patterns:
        m = re.search(pat, d, flags=re.I)
        if m:
            cand = m.group(1).strip(" -:|")
            return cand if looks_like_player(cand) else None
    return None

def same_player(a: str, b: str) -> bool:
    return norm_name(a) == norm_name(b)
