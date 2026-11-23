"""Owner-style LAST MINUTE GOAL / GOAL HUNTER static-plate renderer.

Takes a pre-cleaned plate rather than the sample-filled original photograph.
All volatile fields and authentic crests are independent draw layers.
Never downloads imagery, estimates odds, posts Telegram or edits Supabase.
"""
from __future__ import annotations
from pathlib import Path
from io import BytesIO
import math
from PIL import Image,ImageDraw,ImageFont,ImageOps

HERE=Path(__file__).resolve().parent
CLEAN=HERE/'last_minute_clean_plate.png'
ORIGINAL=HERE/'last_minute_user_original.png'
FONTS=(
 '/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf',
 '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
)
WHITE=(250,250,251)
YELLOW=(254,224,76)
CYAN=(50,235,245)
ORANGE=(255,166,58)

def _font(size):
    for path in FONTS:
        if Path(path).is_file():return ImageFont.truetype(path,max(8,int(size)))
    raise RuntimeError('Production font unavailable')

def _text(draw,label,x,y,size,*,max_width=None,color=WHITE,anchor='mm',stroke=0):
    label=str(label)
    font=_font(size)
    if max_width is not None:
        while draw.textbbox((0,0),label,font=font,stroke_width=stroke)[2] > max_width and size>8:
            size-=1; font=_font(size)
        if draw.textbbox((0,0),label,font=font,stroke_width=stroke)[2] > max_width:
            raise ValueError('Verified text does not fit original card slot')
    draw.text((x,y),label,fill=color,font=font,anchor=anchor,
              stroke_width=stroke,stroke_fill=(0,0,0))

def _n(value, name, *, maximum=None, integer=False):
    if value is None:return None
    if isinstance(value,bool):raise ValueError(name+' must be a real number')
    try:n=float(value)
    except (TypeError,ValueError,OverflowError):raise ValueError(name+' invalid') from None
    if not math.isfinite(n) or n<0 or (maximum is not None and n>maximum):
        raise ValueError(name+' outside credible bounds')
    if integer and int(n)!=n:raise ValueError(name+' must be an integer')
    return int(n) if integer else n

def _logo(im,contents,*,x,y):
    if not isinstance(contents,(bytes,bytearray)) or len(contents)<90:
        raise ValueError('Verified authentic crest bytes required')
    try:
        with Image.open(BytesIO(contents)) as src:
            src.load()
            if min(src.size)<40 or src.size[0]>4096 or src.size[1]>4096:
                raise ValueError('Invalid authentic team crest')
            logo=src.convert('RGBA')
    except (OSError,ValueError) as e:
        raise ValueError('Verified authentic team crest unreadable') from e
    # Crop the provider's TRANSPARENT outside padding before fitting.
    # Otherwise genuine crests appear too small/misaligned in the owner's
    # existing shield fields. Do not draw a replacement circle or sticker.
    visible=logo.getchannel('A').point(
        lambda alpha: 255 if alpha>=24 else 0).getbbox()
    if visible is None:
        raise ValueError('Authentic crest has no visible pixels')
    logo=logo.crop(visible)
    if min(logo.size)<12:
        raise ValueError('Authentic crest artwork too small')
    logo.thumbnail((70,65),Image.Resampling.LANCZOS)
    im.paste(logo,(round(x-logo.width/2),round(y-logo.height/2)),
             logo.getchannel('A'))

def _fmt(v,places=0):
    return '–' if v is None else (f'{v:.{places}f}' if places else str(int(v)))

def _bar(draw,value,other,*,x,y,direction,color):
    if value is None or other is None:return
    denom=max(value,other,1)
    length=int(round(82*value/denom))
    if length<1:return
    if direction=='left':box=(x,y-4,x+length,y+4)
    else:box=(x+82-length,y-4,x+82,y+4)
    draw.rounded_rectangle(box,radius=4,fill=color)
    draw.line((box[0]+3,box[1]+1,box[2]-3,box[1]+1),fill=(178,247,248) if direction=='left' else (255,217,132),width=1)

def render_card(data,*,home_crest:bytes|None=None,away_crest:bytes|None=None,
                preview_only=False,plate=CLEAN,scale=2):
    """Render from data-free master; never write to or repaint the original.

    Required: league, home, away, minute, hg, ag, real logo bytes. Optional:
    xg_prev_home/away, xg_home/away, stats (shots,sot,possession,corners,
    attacks each 2-value list), league_winrate, xg_winrate, over_probability,
    next_probability, next_goal_team, status.
    """
    if not isinstance(data,dict):raise ValueError('Explicit verified data required')
    if not Path(plate).is_file():raise RuntimeError('No cleaned original master - card blocked')
    if Path(plate).resolve()==ORIGINAL.resolve():
        raise ValueError('Cannot render over sample-filled owner original')
    with Image.open(plate) as src:
        if src.size!=(512,512):raise RuntimeError('Clean plate source size changed')
        image=src.convert('RGBA')
    d=ImageDraw.Draw(image)
    home=str(data.get('home') or '').strip();away=str(data.get('away') or '').strip()
    league=str(data.get('league') or '').strip()
    if not all((home,away,league)) or home.casefold()==away.casefold():
        raise ValueError('Verified teams and league required')
    if len(home)>45 or len(away)>45 or len(league)>75:
        raise ValueError('Unverified or too long identity')
    minute=_n(data.get('minute'),'minute',maximum=130,integer=True)
    hg=_n(data.get('hg'),'hg',maximum=30,integer=True)
    ag=_n(data.get('ag'),'ag',maximum=30,integer=True)
    if minute is None or hg is None or ag is None:raise ValueError('Confirmed live minute/score required')
    # Identity and match state
    _text(d,league,266,87,12,max_width=222)
    _logo(image,home_crest,x=96,y=132)
    _logo(image,away_crest,x=419,y=132)
    _text(d,home.upper(),122,182,17,max_width=118)
    _text(d,away.upper(),397,182,17,max_width=129)
    status=str(data.get('status') or 'offen').lower()
    if status not in ('offen','gewonnen','verloren','void'):
        raise ValueError('Unsupported settlement state')
    final=data.get('final_score')
    if final is not None:
        if status=='offen':raise ValueError('Final score cannot remain OFFEN')
        if isinstance(final,str):
            sides=final.replace(' ','').split(':')
        elif isinstance(final,(list,tuple)) and len(final)==2:
            sides=list(final)
        else:raise ValueError('Invalid final score')
        if len(sides)!=2:raise ValueError('Invalid final score')
        fh=_n(sides[0],'final home',maximum=30,integer=True)
        fa=_n(sides[1],'final away',maximum=30,integer=True)
        if fh<hg or fa<ag:raise ValueError('Final score below tip snapshot')
    elif status!='offen':
        raise ValueError('Settlement requires verified final score')
    else:fh,fa=hg,ag
    _text(d,'FT' if final is not None else 'LIVE',259,112,14,max_width=40)
    _text(d,'FT' if final is not None else f"{minute}′",256,135,23,max_width=43)
    _text(d,f'{fh} - {fa}',257,173,33,max_width=76,color=YELLOW,stroke=1)
    # Actual xG history; blank means unknown, not made up.
    hp=_n(data.get('xg_prev_home'),'xg_prev_home',maximum=15)
    ap=_n(data.get('xg_prev_away'),'xg_prev_away',maximum=15)
    hn=_n(data.get('xg_home'),'xg_home',maximum=15)
    an=_n(data.get('xg_away'),'xg_away',maximum=15)
    xg_left=f'{_fmt(hp,2)} → {_fmt(hn,2)}'
    xg_right=f'{_fmt(ap,2)} → {_fmt(an,2)}'
    _text(d,xg_left,101,230,14,max_width=99)
    _text(d,f'{_fmt(hn,2)} - {_fmt(an,2)}',257,229,13,max_width=89,color=YELLOW)
    _text(d,xg_right,413,230,14,max_width=99)
    # Real comparative statistics. No fabricated bar if a side is unknown.
    rows=[('shots',253,120),('sot',270,120),('possession',286,100),
          ('corners',303,50),('attacks',320,200)]
    stats=data.get('stats') or {}
    if not isinstance(stats,dict):raise ValueError('stats must be a mapping')
    for key,y,maximum in rows:
        pair=stats.get(key)
        if pair is None:left=right=None
        elif not isinstance(pair,(list,tuple)) or len(pair)!=2:
            raise ValueError('Bad stat pair for '+key)
        else:
            left=_n(pair[0],key+'_home',maximum=maximum,integer=True)
            right=_n(pair[1],key+'_away',maximum=maximum,integer=True)
        _text(d,_fmt(left)+( '%' if key=='possession' and left is not None else ''),36,y,13,max_width=30)
        _text(d,_fmt(right)+( '%' if key=='possession' and right is not None else ''),477,y,13,max_width=30)
        _bar(d,left,right,x=65,y=y,direction='left',color=CYAN)
        _bar(d,right,left,x=364,y=y,direction='right',color=ORANGE)
    for key,x,maxw in (('league_winrate',187,70),('xg_winrate',455,81)):
        val=data.get(key)
        if val is not None and not isinstance(val,str):raise ValueError(key+' must use observed n/N (%) text')
        _text(d,val or '–',x,346,10,max_width=maxw)
    # Model probabilities, not bookmaker prices.
    p1=_n(data.get('over_probability'),'over_probability',maximum=100)
    p2=_n(data.get('next_probability'),'next_probability',maximum=100)
    _text(d,_fmt(p1,1)+'%' if p1 is not None else '–',432,418,21,max_width=73,color=(201,255,79))
    next_team=data.get('next_goal_team')
    if next_team is not None and next_team not in (home,away):
        raise ValueError('Next-goal team must match an authenticated side')
    if next_team is None and p2 is not None:raise ValueError('Unattributed next-goal probability')
    _text(d,(next_team or 'KEIN SIGNAL'),270,451,18,max_width=130,color=YELLOW)
    _text(d,_fmt(p2,1)+'%' if p2 is not None else '–',432,458,21,max_width=74,color=(201,255,79))
    # The outcome belongs on the original card, not a separate Telegram post.
    # The line is small so it stays between the prediction frame and footer.
    next_grade=data.get('next_goal_result')
    grade_names={'won':'RICHTIG','lost':'FALSCH','void':'KEIN TOR',
                 'unverified':'NICHT VERIFIZIERT'}
    if next_grade is not None and next_grade not in grade_names:
        raise ValueError('Unknown next-goal settlement')
    if next_grade is not None and not next_team:
        raise ValueError('Next-goal result without original selected team')
    status_line='AUSWERTUNG '+status.upper()
    if next_grade is not None:
        status_line+=' · NÄCHSTES TOR '+grade_names[next_grade]
    # Settlement and next-goal result are both inside this SAME image, not
    # standalone Telegram messages. Fit the full line into the clear footer.
    _text(d,status_line,265,485,9,max_width=330,
          color=WHITE if status=='offen' else ((118,255,121) if status=='gewonnen' else (255,119,110)))
    if preview_only:
        # Never let fixture data or a QA crest be mistaken for real betting tips.
        d.rounded_rectangle((142,473,367,488),fill=(5,17,25),outline=YELLOW,width=1)
        _text(d,'SANDBOX · KEIN TIPP',254,480,10,color=YELLOW,max_width=213)
    if scale not in (1,2,3):raise ValueError('Allowed pixel scales: 1,2,3')
    image=image.convert('RGB').resize((512*scale,512*scale),Image.Resampling.LANCZOS)
    # Blank Telegram clock/edited margin BELOW the original artwork.
    out=Image.new('RGB',(512*scale,512*scale+27*scale),(2,11,17))
    out.paste(image,(0,0))
    buf=BytesIO();out.save(buf,'PNG',optimize=True)
    return buf.getvalue()

if __name__=='__main__':
    # Non-betting demonstration; QA-only fictitious crests are never live.
    dct={'league':'TESTLIGA / SANDBOX','home':'TEST HEIM','away':'TEST GAST',
         'minute':75,'hg':1,'ag':1,'xg_prev_home':0.52,'xg_home':0.81,
         'xg_prev_away':0.72,'xg_away':1.06,
         'stats':{'shots':[10,14],'sot':[4,6],'possession':[47,53],
                  'corners':[4,6],'attacks':[39,47]},
         'league_winrate':'10/22 (45%)','xg_winrate':'16/29 (55%)',
         'over_probability':68.2,'next_probability':62.1,
         'next_goal_team':'TEST HEIM','status':'offen'}
    def qa_crest(initial,color):
        logo=Image.new('RGBA',(140,140),(0,0,0,0));dr=ImageDraw.Draw(logo)
        dr.ellipse((6,6,134,134),fill=color,outline=(255,212,70),width=5)
        _text(dr,initial,70,70,44,max_width=120)
        b=BytesIO();logo.save(b,'PNG');return b.getvalue()
    preview=render_card(dct,home_crest=qa_crest('QA',(26,115,174)),
                        away_crest=qa_crest('QA',(173,81,37)),preview_only=True)
    (HERE/'last_minute_render_test.png').write_bytes(preview)
    print('Sandbox preview:',HERE/'last_minute_render_test.png')