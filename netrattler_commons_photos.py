"""License-safe Wikimedia Commons photos for selected, identity-checked footballers.

Only Public Domain / CC0 images are used automatically: other Commons licenses
may require author credits, license links and share-alike attribution on cards.
Never treat a Commons category as evidence that any arbitrary file shows its subject.
"""
import re
import unicodedata
from urllib.parse import urlparse
import requests

CATEGORIES = {
    "lionel messi": "Lionel Messi",
    "cristiano ronaldo": "Cristiano Ronaldo",
    "kylian mbappe": "Kylian Mbappe",
    "erling haaland": "Erling Haaland",
    "jude bellingham": "Jude Bellingham",
    "mohamed salah": "Mohamed Salah",
    "harry kane": "Harry Kane",
    "vinicius junior": "Vinicius Junior",
    "rodri": "Rodri (footballer, born 1996)",
    "lamine yamal": "Lamine Yamal",
}
CACHE = {}
MAX_REQUESTS = 10
_REQUESTS = 0


def normalize(text):
    value = unicodedata.normalize("NFKD", str(text or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(
        c for c in value if not unicodedata.combining(c))).strip()


def is_usable(title, info, player):
    """Require explicit player name in filename and a license without attribution duty."""
    name = normalize(title.removeprefix("File:"))
    wanted = normalize(player)
    if not wanted or not re.search(r"(?<![a-z0-9])" + re.escape(wanted) + r"(?![a-z0-9])", name):
        return False
    metadata = info.get("extmetadata") or {}
    lic = str((metadata.get("LicenseShortName") or {}).get("value") or "").strip().lower()
    if lic not in {"cc0", "cc0 1.0", "public domain", "pd"}:
        return False
    url = info.get("thumburl") or info.get("url") or ""
    parsed = urlparse(url)
    return (parsed.scheme == "https" and parsed.hostname == "upload.wikimedia.org"
            and parsed.path.lower().split(".")[-1] in {"jpg", "jpeg", "png", "webp"})


def commons_photo(name):
    """Return exactly one Commons image URL, or empty on uncertainty/errors."""
    global _REQUESTS
    key = normalize(name)
    if key not in CATEGORIES:
        return ""
    if key in CACHE:
        return CACHE[key]
    if _REQUESTS >= MAX_REQUESTS:
        return ""
    _REQUESTS += 1
    try:
        response = requests.get("https://commons.wikimedia.org/w/api.php",
            params={"action": "query", "generator": "categorymembers",
                    "gcmtitle": "Category:" + CATEGORIES[key], "gcmtype": "file",
                    "gcmlimit": "100", "prop": "imageinfo", "iiprop": "url|extmetadata",
                    "iiurlwidth": "450", "format": "json", "formatversion": "2"},
            headers={"User-Agent": "NETRATTLER/1.0 (licensed-image lookup)"},
            timeout=9)
        if not response.ok:
            return ""
        pages = (response.json().get("query") or {}).get("pages") or []
        matches = []
        for page in pages:
            for info in page.get("imageinfo") or []:
                if is_usable(str(page.get("title") or ""), info, name):
                    matches.append(info.get("thumburl") or info.get("url"))
        # Only cache a unique match: multiple distinct files need manual curation.
        result = matches[0] if len(set(matches)) == 1 else ""
        CACHE[key] = result
        return result
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return ""
