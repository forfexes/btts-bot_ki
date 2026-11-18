"""Read-only Wikimedia Commons attribution inventory for NETRATTLER.

Source roster: existing data/player_season_2026_2027.csv (no new paid datasets).
Writes a local CSV of candidate images; NEVER posts pictures or marks a source
image as licensed for Telegram without review. Does not persist to Supabase.
Usage: python netrattler_commons_inventory.py --limit 50 --output /tmp/commons.csv
"""
import argparse
import csv
import html
import re
import time
from pathlib import Path
from urllib.parse import quote
import requests

from netrattler_commons_photos import normalize

API = "https://commons.wikimedia.org/w/api.php"
FIELDS = ["Spieler", "Verein", "Bild_URL", "Lizenz", "Fotograf",
          "Commons_Seite", "Lizenz_URL", "Pruefstatus"]
HEADERS = {"User-Agent": "NETRATTLER-photo-inventory/1.0 (metadata research)"}


def clean_html(text):
    return re.sub(r"<[^>]+>", "", html.unescape(str(text or ""))).strip()


def metadata_value(info, field):
    return clean_html(((info.get("extmetadata") or {}).get(field) or {}).get("value"))


def candidate_row(player, club, page):
    title = str(page.get("title") or "")
    if not title.startswith("File:"):
        return None
    # A Commons search hit isn't proof of identity. Only exact full-name
    # filename matches become candidates; all stay pending review.
    if not re.search(r"(?<![a-z0-9])" + re.escape(normalize(player)) + r"(?![a-z0-9])",
                     normalize(title[5:])):
        return None
    info = (page.get("imageinfo") or [{}])[0]
    url = info.get("thumburl") or info.get("url") or ""
    if not str(url).startswith("https://upload.wikimedia.org/"):
        return None
    license_name = metadata_value(info, "LicenseShortName")
    credit = metadata_value(info, "Artist")
    license_url = ((info.get("extmetadata") or {}).get("LicenseUrl") or {}).get("value") or ""
    return {
        "Spieler": player, "Verein": club, "Bild_URL": url,
        "Lizenz": license_name, "Fotograf": credit,
        "Commons_Seite": "https://commons.wikimedia.org/wiki/" + quote(title.replace(" ", "_"), safe=":()_,"),
        "Lizenz_URL": str(license_url),
        "Pruefstatus": "manuell_pruefen" if license_name and credit else "metadaten_unvollstaendig",
    }


def search_commons(session, name, club):
    response = session.get(API, params={
        "action": "query", "generator": "search",
        "gsrsearch": 'filetype:bitmap "' + name + '"',
        "gsrnamespace": 6, "gsrlimit": 15,
        "prop": "imageinfo", "iiprop": "url|extmetadata",
        "iiurlwidth": 450, "format": "json", "formatversion": 2,
    }, headers=HEADERS, timeout=20)
    response.raise_for_status()
    pages = (response.json().get("query") or {}).get("pages") or []
    candidates = [candidate_row(name, club, page) for page in pages]
    return [r for r in candidates if r]


def roster(path, limit):
    seen = set()
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            name, club = (row.get("Player") or "").strip(), (row.get("Squad") or "").strip()
            if not name or not club or (normalize(name), normalize(club)) in seen:
                continue
            seen.add((normalize(name), normalize(club)))
            yield name, club
            if len(seen) >= limit:
                return


def build(source, output, limit=50, pause=1.0, session=None):
    if limit < 1 or limit > 500:
        raise ValueError("limit must be 1..500")
    session = session or requests.Session()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for name, club in roster(source, limit):
            try:
                rows = search_commons(session, name, club)
                if rows:
                    for row in rows:
                        writer.writerow(row)
                        count += 1
                else:
                    writer.writerow({"Spieler": name, "Verein": club,
                                     "Pruefstatus": "kein_eindeutiger_kandidat"})
            except (requests.RequestException, ValueError):
                writer.writerow({"Spieler": name, "Verein": club,
                                 "Pruefstatus": "api_fehler"})
            if pause:
                time.sleep(max(0, pause))
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="data/player_season_2026_2027.csv")
    parser.add_argument("--output", default="/tmp/netrattler_commons_inventory.csv")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--pause", type=float, default=1.0)
    args = parser.parse_args()
    print("Commons candidates written:", build(args.source, args.output, args.limit, args.pause))
