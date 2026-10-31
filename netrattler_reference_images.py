"""Bounded, identity-checked SoccerWiki and German/English Wikipedia image fallbacks."""
from html.parser import HTMLParser
from urllib.parse import urlparse
import re
import requests
from netrattler_season_profiles import norm

_CALLS = 0
MAX_CALLS = 12
_CACHE = {}
HEADERS = {'User-Agent':'NETRATTLER-source-check/1.0'}


class SoccerRows(HTMLParser):
    def __init__(self):
        super().__init__();self.rows=[];self.row=None;self.anchor=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='tr': self.row={'players':[],'clubs':[],'images':[]}
        if self.row is None:return
        if tag=='a':self.anchor=[attrs.get('href',''),'']
        if tag=='img':self.row['images'].append(attrs.get('data-src') or attrs.get('src') or '')
    def handle_data(self,data):
        if self.anchor is not None:self.anchor[1]+=data
    def handle_endtag(self,tag):
        if tag=='a' and self.anchor is not None:
            href,text=self.anchor
            if self.row is not None:
                if re.fullmatch(r'/player.php\?pid=\d+',href) and text.strip():self.row['players'].append((href,text.strip()))
                if re.fullmatch(r'/squad.php\?clubid=\d+',href) and text.strip():self.row['clubs'].append(text.strip())
            self.anchor=None
        if tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None


def soccerwiki_url(document,player,team):
    if not player or not team:return ''
    parser=SoccerRows();parser.feed(document)
    urls=set()
    for row in parser.rows:
        matches=[href for href,name in row['players'] if norm(name)==norm(player)]
        if len(set(matches))!=1 or not any(norm(club)==norm(team) for club in row['clubs']):continue
        pid=matches[0].split('=')[-1]
        target=f'https://cdn.soccerwiki.org/images/player/{pid}.png'
        if target in row['images']:urls.add(target)
    return next(iter(urls)) if len(urls)==1 else ''


def _get(url,**kwargs):
    global _CALLS
    if _CALLS>=MAX_CALLS:return None
    _CALLS+=1
    try:
        r=requests.get(url,headers=HEADERS,timeout=5,**kwargs)
        return r if r.ok and len(r.content)<=1_000_000 else None
    except requests.RequestException:return None


def player_urls(player,team):
    key=(norm(player),norm(team))
    if not all(key):return []
    if key in _CACHE:return _CACHE[key]
    urls=[]
    response=_get('https://de.soccerwiki.org/search.php',params={'q':player})
    if response is not None:
        url=soccerwiki_url(response.text,player,team)
        if url:urls.append(url)
    # MediaWiki is an additional fallback; no first-name-only identity matching.
    if not urls:
        for language,word in [('de','Fußballspieler'),('en','footballer')]:
            r=_get(f'https://{language}.wikipedia.org/w/api.php',params={
                'action':'query','generator':'search','gsrsearch':f'"{player}" {word}',
                'gsrlimit':3,'prop':'pageimages|extracts','piprop':'thumbnail','pithumbsize':400,
                'exintro':1,'explaintext':1,'format':'json','formatversion':2})
            if r is None:continue
            try:pages=r.json().get('query',{}).get('pages',[])
            except (ValueError,AttributeError):continue
            candidates=[]
            for page in pages:
                title=re.sub(r'\s*\([^)]*\)\s*$','',str(page.get('title','')))
                extract=str(page.get('extract',''))
                url=str((page.get('thumbnail') or {}).get('source',''))
                if (norm(title)==key[0] and key[1] in norm(extract)
                    and re.search(r'football|fußball|fussball',extract,re.I)
                    and urlparse(url).hostname=='upload.wikimedia.org'):
                    candidates.append(url)
            if len(set(candidates))==1:urls.append(candidates[0]);break
    _CACHE[key]=urls
    return urls
