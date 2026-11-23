"""Conservative club identity for presentation assets; no fuzzy city-name matches."""
import re
import unicodedata

ALIASES = {
    'psg':'paris saint germain', 'bayern':'bayern munich', 'bayern munchen':'bayern munich',
    'rennes':'stade rennais', 'swansea':'swansea city', 'blackburn':'blackburn rovers',
    'derby':'derby county', 'inter':'inter milan', 'internazionale':'inter milan',
    'mechelen':'kv mechelen', 'sint truidense':'sint truidense vv', 'twente 65':'twente enschede',
    'atletico madrid':'atletico de madrid', 'athletic bilbao':'athletic club',
    # Verified exact aliases for club names in the pinned football-logos index.
    'atalanta':'atalanta bc', 'bayer leverkusen':'bayer 04 leverkusen',
    'lens':'rc lens', 'psv':'psv eindhoven',
    'lyon':'olympique lyon', 'nice':'ogc nice', 'sassuolo':'us sassuolo',
    'juventus':'juventus fc', 'frosinone':'frosinone calcio',
    'atletico mg':'atletico mineiro', 'atletico mineiro mg':'atletico mineiro',
    'deportivo la coruna':'deportivo a coruna',
    'rc deportivo la coruna':'deportivo a coruna',
    'rc deportivo a coruna':'deportivo a coruna',
}
STOP = {'fc','cf','afc','sc','fk','football','club','futbol','futebol','clube'}


def identity(name):
    text=unicodedata.normalize('NFKD',str(name or '')).encode('ascii','ignore').decode().lower()
    text=' '.join(re.findall(r'[a-z0-9]+',text))
    text=' '.join(t for t in text.split() if t not in STOP)
    return ALIASES.get(text,text)


def same_club(a,b):
    a,b=identity(a),identity(b)
    return bool(a and b and a==b)


def named_crest_url_matches_club(team, url):
    """True/False when a provider filename names the club; None when opaque.

    Reject known wrong-club CDN filenames without guessing opaque API asset IDs.
    """
    from urllib.parse import unquote, urlparse

    if not team or not url or not str(url).startswith("https://"):
        return None
    address = urlparse(url)
    path = unquote(address.path or "")
    basename = path.rsplit("/", 1)[-1]
    if address.hostname == "assets.football-logos.cc" and "/logos/" in path:
        candidate = basename.split(".")[0].replace("-", " ")
    elif address.hostname == "raw.githubusercontent.com" and "/logos/" in path:
        candidate = basename.rsplit(".", 1)[0]
    else:
        return None
    if not candidate:
        return None
    return same_club(team, candidate)
