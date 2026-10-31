"""Single-match prop builder photos; observed leg quotes, never a synthetic SGM price."""
import io
from PIL import Image,ImageDraw,ImageFont


def render_builder_card(pick):
    import netrattler_stats_match_cards as cards
    import netrattler_builder_engine as engine
    from netrattler_corner_cards import kickoff_label
    multi = len({leg.match for leg in pick.legs}) != 1
    tiers=getattr(pick,'tiers',None) or []
    height=420+160*len(pick.legs)+110+40*len(tiers)
    from netrattler_card_theme import midnight_arena
    im=midnight_arena(1200,height);draw=ImageDraw.Draw(im)
    def font(n):
        try:return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf',n)
        except OSError:
            try:return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',n)
            except OSError:return ImageFont.load_default(size=n)
    def fit(text,n,width):
        text=str(text)
        while text and draw.textlength(text,font=font(n))>width:
            text=text[:-2].rstrip()+'…'
        return text

    def center(text,x,y,n=25,color='#ffffff'):
        f=font(n);text=str(text);draw.text((x-draw.textlength(text,font=f)/2,y),text,font=f,fill=color)
    center('NETRATTLER',600,20,68)
    center('PROP BUILDER · '+str(pick.style),600,110,30,'#ffd84a')
    home,away=cards._teams(pick.legs[0].match) if not multi else ('Mehrere Spiele','Cross-Match')
    for team,x in ((home,150),(away,1050)):
        cards._TEAM_LEAGUE.setdefault(cards._norm(team),pick.legs[0].league)
        draw.ellipse((x-80,175,x+80,335),fill='#eaf1fa')
        if not multi: cards._paste_badge(im,draw,team,(x-80,175,x+80,335),font(35))
    center('VS',600,225,48)
    center(home[:26],300,350,28);center(away[:26],900,350,28)
    day,clock=kickoff_label({'_kickoff':pick.legs[0].kickoff},pick.match_date)
    center(day+' · '+clock,600,385,21)
    photos={}
    for i,leg in enumerate(pick.legs):
        y=430+i*160
        draw.rounded_rectangle((30,y,1170,y+145),radius=15,fill='#0A1B32',outline='#42cfe8',width=2)
        key=(leg.player,leg.team)
        if key not in photos:
            photos[key]=cards._player_photo(leg.player,leg.team) if len(photos)<6 else b''
        placed=False
        if photos[key]:
            try:
                image=Image.open(io.BytesIO(photos[key])).convert('RGBA');image.thumbnail((115,125))
                im.paste(image,(48,y+10),image);placed=True
            except (OSError,ValueError):pass
        if not placed:
            draw.ellipse((50,y+22,150,y+122),fill='#173858')
            center(''.join(w[0] for w in leg.player.split()[:2]).upper(),100,y+47,33)
        draw.text((185,y+12),fit(leg.player,28,750),font=font(28),fill='#ffffff')
        draw.text((185,y+52),fit(leg.market,23,760),font=font(23),fill='#d4ecff')
        series=getattr(leg,'series',None)
        history=(f'L{len(series)}: '+','.join(str(v) for v in series)+f' ({sum(v>=leg.line for v in series)}/{len(series)})') if series else engine.history_text(leg)
        if multi: history=leg.match+' · '+history
        draw.text((185,y+91),fit(history or 'Historie nicht verfügbar',18,955),font=font(18),fill='#a6c4dc')
        if leg.odds and leg.odds>1: center('@ '+f'{leg.odds:.2f}',1050,y+20,31,'#2EE6C5')
    y=430+160*len(pick.legs)
    for level,prob in tiers:
        label=('Basis' if level==0 else f'Alle Linien +{level}') if getattr(pick,'tier_shift',False) else f'{level}+ bei allen Beinen'
        center(f'{label} · Modell {prob*100:.1f}% · fair {1/prob:.2f}',600,y,21,'#a6c4dc')
        y+=40
    if getattr(pick,'model_only',False):
        center('MODELL · keine bestätigte Buchmacherquote',600,y,24,'#ffd84a')
        center(f'Modell: {pick.joint*100:.0f}% · faire Modellquote: {pick.fair:.2f}',600,y+40,22)
    else:
        center('Gesamtquote beim Buchmacher prüfen',600,y,25,'#ffd84a')
        center(str(pick.variant)+' · '+f'{pick.stake:g} Units',600,y+40,22)
    out=io.BytesIO();im.save(out,format='PNG',optimize=True);return out.getvalue()


def send_builder_card(token,chat,pick,log=print):
    import netrattler_stats_match_cards as cards
    if not token or not chat:return None
    try:
        payload=render_builder_card(pick)
        mid=cards._send_photo(token,chat,'',payload,log)
        return mid if isinstance(mid,int) and not isinstance(mid,bool) and mid>0 else None
    except Exception as exc:
        log('Builder-Foto nicht verfügbar: '+type(exc).__name__)
        return None


def send_model_builder_card(pick, match_date, text, log=print):
    """Adapt model picks without creating fictional leg prices or stakes."""
    import os
    from types import SimpleNamespace
    token=os.getenv('TELEGRAM_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')
    chat=(os.getenv('TELEGRAM_GROUP_BUILDER') or os.getenv('TELEGRAM_GROUP_PLAYER_PROPS')
          or os.getenv('TELEGRAM_GROUP_STATS') or os.getenv('TELEGRAM_CHAT_ID'))
    if not token or not chat:
        return None
    adapted=SimpleNamespace(legs=[SimpleNamespace(**leg) for leg in pick['legs']],
        style=pick.get('title','MODELL-BUILDER'),variant='',stake=0,match_date=match_date,
        model_only=True,joint=pick['joint'],fair=pick['fair'],
        tiers=pick.get('tiers'),tier_shift=pick.get('tier_shift',False))
    mid=send_builder_card(token,chat,adapted,log)
    return {'message_id':mid,'chat_id':chat,'text':text} if mid else None
