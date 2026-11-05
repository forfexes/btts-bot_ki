"""Conservative club identity for presentation assets; no fuzzy city-name matches."""
import re
import unicodedata

ALIASES = {
    'psg':'paris saint germain', 'bayern':'bayern munich', 'bayern munchen':'bayern munich',
    'rennes':'stade rennais', 'swansea':'swansea city', 'blackburn':'blackburn rovers',
    'derby':'derby county', 'inter':'inter milan', 'internazionale':'inter milan',
    'atletico madrid':'atletico de madrid', 'athletic bilbao':'athletic club',
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
