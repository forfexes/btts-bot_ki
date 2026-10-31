"""NETRATTLER corner cards and explicit, timezone-aware kickoff presentation."""
from datetime import datetime
from zoneinfo import ZoneInfo
import re


def kickoff_label(tip, target_date):
    for key in ('_kickoff','kickoff','starts','commence_time','time_utc'):
        try:
            stamp=datetime.fromisoformat(str(tip.get(key) or '').replace('Z','+00:00'))
            if stamp.tzinfo is not None:
                local=stamp.astimezone(ZoneInfo('Europe/Zurich'))
                return local.strftime('%Y-%m-%d'),local.strftime('%H:%M')
        except (ValueError,TypeError):
            pass
    for key in ('time_local','time'):
        text=str(tip.get(key) or '').strip()
        if re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',text):
            return str(target_date)[:10],text
    return str(target_date)[:10],'Zeit nicht bestätigt'


def render_corner_card(tip,target_date,result=None):
    from PIL import Image,ImageDraw,ImageFont
    import netrattler_stats_match_cards as cards
    im=Image.new('RGB',(1200,900),'#071A3D'); draw=ImageDraw.Draw(im)
    def font(n,bold=True):
        path='/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed'+('-Bold' if bold else '')+'.ttf'
        try:return ImageFont.truetype(path,n)
        except OSError:
            try:return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if bold else '')+'.ttf',n)
            except OSError:return ImageFont.load_default(size=n)
    def center(text,x,y,n=25,color='#ffffff'):
        text=str(text); f=font(n); w=draw.textlength(text,font=f)
        draw.text((x-w/2,y),text,font=f,fill=color)
    def panel(box):
        draw.rounded_rectangle(box,radius=18,fill='#0A1B32',outline='#75e6ff',width=2)
    def value(v,suffix=''):
        return 'Nicht verfügbar' if v is None or v=='' else str(v)+suffix
    home,away=cards._teams(tip.get('match',''))
    for team in (home,away):
        cards._TEAM_LEAGUE.setdefault(cards._norm(team),str(tip.get('league') or ''))
    center('NETRATTLER',600,20,72)
    center('REAL ODDS. REAL CONTEXT.',600,103,20)
    center('CORNER SNIPER',600,145,38,'#ffd84a')
    draw.ellipse((95,185,275,365),fill='#eaf1fa')
    draw.ellipse((925,185,1105,365),fill='#eaf1fa')
    cards._paste_badge(im,draw,home,(90,180,280,370),font(40))
    cards._paste_badge(im,draw,away,(920,180,1110,370),font(40))
    center(home[:27],300,378,29);center(away[:27],900,378,29)
    center('VS',600,230,64)
    center(str(tip.get('league') or 'Fussball')[:46],600,315,20)
    day,clock=kickoff_label(tip,target_date)
    center(day+' · '+clock,600,350,23)
    panel((30,435,1170,600))
    center(tip.get('tip') or tip.get('selection') or 'Ecken',600,453,39)
    for x,label,v in [(180,'BUCHMACHERQUOTE',tip.get('odds') or tip.get('oddsYes')),
        (460,'MODELL',value(tip.get('probability'),'%')),
        (740,'ERWARTETE ECKEN',tip.get('expected_corners')),
        (1020,'FAIRE MODELLQUOTE',tip.get('fair_odds') or tip.get('fairOdds'))]:
        center(label,x,515,17);center(value(v),x,543,33,'#33f0c8')
    panel((30,620,585,805));panel((605,620,1170,805))
    center('TEAMHISTORIE · ECKEN ERZIELT',307,638,22)
    center(home[:19]+': '+value(tip.get('home_avg_corners'))+' für · '+value(tip.get('home_avg_corners_against'))+' gegen',307,685,21)
    center(away[:19]+': '+value(tip.get('away_avg_corners'))+' für · '+value(tip.get('away_avg_corners_against'))+' gegen',307,730,21)
    center('H2H · ABGESCHLOSSENE DUELLE',887,638,21)
    n=tip.get('h2h_matches')
    center(value(n,' Spiele') if n else 'Keine bestätigte Historie',887,680,24)
    if tip.get('h2h_avg_corners') is not None:
        center('Ø Ecken: '+value(tip['h2h_avg_corners']),887,725,24)
    elif tip.get('h2h_avg_goals') is not None:
        center('Ø Tore: '+value(tip['h2h_avg_goals']),887,725,24)
    else:center('Weitere H2H-Werte fehlen',887,725,20)
    footer='Echte Buchmacherquote · '+value(tip.get('units',1),' Units')
    if result:
        outcome=(result.get('marks') or {}).get('0') or result.get('status')
        label={'win':'GEWONNEN','loss':'VERLOREN','void':'VOID','pending':'OFFEN'}.get(outcome,'aktualisiert')
        footer='AUSWERTUNG · '+label
    center(footer,600,838,22)
    import io
    out=io.BytesIO();im.save(out,format='PNG',optimize=True);return out.getvalue()


def send_corner_card(token,chat,tip,target_date,log=print):
    import netrattler_stats_match_cards as cards
    if not token or not chat or not cards._valid(tip):return None
    try:
        cards._crest_cache_load()
        cards.attach_h2h_api({'corners':[tip]},log=log)
        payload=render_corner_card(tip,target_date)
        mid=cards._send_photo(token,chat,'',payload,log)
        if isinstance(mid,int) and not isinstance(mid,bool) and mid>0:
            cards.save_card(chat,mid,[('corners',tip)],target_date,log)
            return mid
    except Exception as exc:
        log('Corner-Card nicht verfügbar: '+type(exc).__name__)
    return None
