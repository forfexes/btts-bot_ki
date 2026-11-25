"""Remaining owner-stadium layouts. Pure rendering; no Telegram or settlement writes.
The exact pinned original PNG is loaded for every page; no legacy screenshot
or synthetic artwork is substituted. Provider inputs must be identity verified.
"""
from io import BytesIO
import math
from PIL import Image, ImageDraw, ImageChops
from netrattler_stadium_portrait import load_master, _label, _crest, _verified_time, GOLD, WHITE, CYAN
from netrattler_premium_live_bridge import _book_price, _split_match, _market_category, _raw_asset
from netrattler_btts_owner_original import _percent
from premium_joint_formula import estimate_combo

def _output(canvas,original):
    if ImageChops.difference(original.crop((0,0,1122,265)),canvas.crop((0,0,1122,265))).getbbox():
        raise AssertionError("Master masthead modified")
    out=BytesIO()
    canvas.save(out,format="PNG",optimize=True)
    return out.getvalue()

def _pair(home,away,provider):
    a,b=(_raw_asset(provider(team),team) for team in (home,away))
    def fingerprint(im):
        box=im.getchannel("A").getbbox()
        return im.crop(box).resize((96,96),Image.Resampling.LANCZOS).tobytes()
    if fingerprint(a)==fingerprint(b):
        raise ValueError("Identical club crests")
    return a,b

def _number(value,label):
    try: n=float(value)
    except (ValueError,TypeError,OverflowError): raise ValueError("Missing "+label) from None
    if not math.isfinite(n) or n<0: raise ValueError("Invalid "+label)
    return n

def _status(result):
    mark=str(((result or {}).get("marks") or {}).get("0") or "").lower()
    return {"win":"GEWONNEN","won":"GEWONNEN","loss":"VERLOREN","lost":"VERLOREN","void":"VOID","push":"PUSH"}.get(mark,"OFFEN")

def _time(tip):
    for key in ("_kickoff","commence_time","kickoff_utc","kickoff","starts","time_utc"):
        label=_verified_time({"commence_time":tip.get(key)})
        if label:return label
    raise ValueError("No verified offset-aware kickoff")

def render_corner(tip, *, crest_provider, result=None):
    from netrattler_corner_template import first
    home,away=_split_match(tip.get("match"))
    price,_=_book_price(tip)
    clock=_time(tip)
    selection=str(tip.get("selection") or tip.get("tip") or "").strip()
    if not selection: raise ValueError("Missing actual corner market")
    probability=_percent(tip.get("probability"),strict=True)
    stats=[]
    for side in ("home","away"):
        for window in (10,15):
            names=(f"{side}_corners_l{window}",f"{side}_l{window}_corners",f"{side}_avg_corners_l{window}",f"{side}_corners_l{window}_avg")
            stats.append(_number(first(tip,*names),f"{side} L{window}"))
    expected=_number(tip.get("expected_corners"),"expected corners")
    hits=[str(tip.get(f"corner_hits_l{n}") or "").strip() for n in (10,15)]
    if not all(hits):raise ValueError("Missing observed corner hit history")
    original=load_master();canvas=original.copy()
    for x,badge in zip((310,812),_pair(home,away,crest_provider)):
        _crest(canvas,badge,(x,485))
    d=ImageDraw.Draw(canvas)
    _label(d,(561,305),"CORNER HUNTER",950,54,GOLD)
    _label(d,(310,625),home,470,34)
    _label(d,(812,625),away,470,34)
    _label(d,(561,690),clock,980,32)
    _label(d,(561,760),selection,1000,44,GOLD)
    _label(d,(300,827),f"QUOTE @{price:.2f}",500,38,GOLD)
    _label(d,(822,827),"MODELL "+probability,500,38)
    for x,vals in ((310,stats[:2]),(812,stats[2:])):
        _label(d,(x,913),f"L10: {vals[0]:.1f}",470,34)
        _label(d,(x,967),f"L15: {vals[1]:.1f}",470,34)
    _label(d,(561,1040),f"ERWARTETE ECKEN {expected:.1f}",980,38,GOLD)
    _label(d,(561,1100),f"TREFFER L10 {hits[0]} · L15 {hits[1]}",1000,30)
    _label(d,(561,1215),"AUSWERTUNG: "+_status(result),980,38,GOLD)
    _label(d,(561,1260),str((result or {}).get("ft") or ""),980,28)
    return _output(canvas,original)

TICKET_TITLES={"builder":"BUILDER","combo":"COMBO","cross_mix":"CROSS","lottery":"LOTTERY"}
def render_ticket(kind,legs,*,crest_provider,player_provider=None,ticket_id,status="OFFEN"):
    if kind not in TICKET_TITLES or not 2<=len(legs)<=12 or not str(ticket_id).strip():
        raise ValueError("Invalid ticket kind, identity or size")
    if status not in {"OFFEN","GEWONNEN","VERLOREN","VOID","PUSH"}:raise ValueError("Invalid result")
    validated=[];formula=[]
    seen=set()
    for leg in legs:
        home,away=_split_match(leg.get("match"))
        _,market=_market_category(leg,kind)
        price,_=_book_price(leg)
        clock=_time(leg)
        player=str(leg.get("player") or "").strip()
        team=str(leg.get("team") or "").strip()
        if player and (team.casefold() not in {home.casefold(),away.casefold()} or not callable(player_provider)):
            raise ValueError("Missing verified player identity")
        key=(home.casefold(),away.casefold(),market.casefold(),player.casefold())
        if key in seen:raise ValueError("Duplicate ticket leg")
        seen.add(key)
        formula.append({"match":leg["match"],"event_id":leg.get("event_id"),"odds":price,"odds_observed":True,"probability":leg.get("probability")})
        validated.append((home,away,market,price,clock,player,team))
    data=estimate_combo(formula,conditional_probabilities=legs[0].get("conditional_probabilities"),joint_observations=legs[0].get("joint_observations"))
    product=data["indicative_leg_product"]
    if product is None or not data["individual_prices_observed"]:raise ValueError("Missing verified leg quotes")
    # Every output page retains the full original artwork. Four distinct
    # title types share row geometry, with player cutouts only when applicable.
    per_page=3
    pages=[]
    n_pages=math.ceil(len(legs)/per_page)
    for start in range(0,len(legs),per_page):
        original=load_master();canvas=original.copy()
        d=ImageDraw.Draw(canvas)
        _label(d,(561,305),TICKET_TITLES[kind],850,56,GOLD)
        _label(d,(561,364),f"{len(legs)} TIPPS · SEITE {start//per_page+1}/{n_pages}",960,29)
        for index,(home,away,market,price,clock,player,team) in enumerate(validated[start:start+per_page]):
            y=485+index*225
            first,second=_pair(home,away,crest_provider)
            for x,im in ((110,first),(1012,second)):
                im.thumbnail((100,100),Image.Resampling.LANCZOS)
                canvas.paste(im,(x-im.width//2,y-im.height//2),im)
            _label(d,(561,y-48),home+" vs "+away,730,30)
            _label(d,(561,y-4),market+"  @"+f"{price:.2f}",730,34,GOLD)
            _label(d,(561,y+37),clock,730,25)
            if player:
                pic=_raw_asset(player_provider(player,team),player,80)
                pic.thumbnail((88,88),Image.Resampling.LANCZOS)
                canvas.paste(pic,(170,y+42),pic)
                _label(d,(595,y+84),player,650,29)
        _label(d,(561,1160),f"FORMELQUOTE {product:.2f}",1000,44,GOLD)
        _label(d,(561,1210),"BERECHNET – KEINE BUCHMACHERQUOTE",1050,28)
        _label(d,(561,1265),status,980,32)
        pages.append(_output(canvas,original))
    return pages,data

LIVE_TITLES={"last_minute_goal":"LAST MINUTE GOAL","late_goals":"LATE GOALS","live_halftime":"HALBZEIT LIVE"}
def render_live(kind,fixture,*,crest_provider,metrics):
    if kind not in LIVE_TITLES or fixture.get("fixture_verified") is not True:
        raise ValueError("Verified live fixture required")
    home=str(fixture.get("home") or "").strip()
    away=str(fixture.get("away") or "").strip()
    if not home or not away or home.casefold()==away.casefold():raise ValueError("Invalid fixture")
    clock=_number(fixture.get("minute"),"live minute")
    hg=_number(fixture.get("hg"),"home goals");ag=_number(fixture.get("ag"),"away goals")
    if not all(v.is_integer() for v in (clock,hg,ag)) or not 0<=clock<=150 or max(hg,ag)>30:
        raise ValueError("Invalid observed live score")
    if kind=="live_halftime" and not 0<=clock<=60:raise ValueError("Outside halftime window")
    if kind in {"last_minute_goal","late_goals"} and clock<60:raise ValueError("Outside late goal window")
    observed=[]
    for k,label in (("shots","SCHÜSSE"),("sot","AUFS TOR"),("corners","ECKEN"),("xg","xG")):
        raw=metrics.get(k)
        if raw is not None:
            if not isinstance(raw,(tuple,list)) or len(raw)!=2:raise ValueError("Invalid live statistic")
            a,b=(_number(x,k) for x in raw)
            observed.append((label,f"{a:g} : {b:g}"))
    if not observed:raise ValueError("Missing live observations")
    original=load_master();canvas=original.copy()
    for x,badge in zip((310,812),_pair(home,away,crest_provider)):_crest(canvas,badge,(x,500))
    d=ImageDraw.Draw(canvas)
    _label(d,(561,305),LIVE_TITLES[kind],1000,53,GOLD)
    _label(d,(561,500),f"{int(hg)} : {int(ag)}",250,57,GOLD)
    _label(d,(310,645),home,470,34)
    _label(d,(812,645),away,470,34)
    _label(d,(561,722),f"{int(clock)}. MINUTE · LIVE",980,42,GOLD)
    for i,(label,value) in enumerate(observed):
        _label(d,(310,830+85*i),label,470,33)
        _label(d,(812,830+85*i),value,470,39,GOLD)
    _label(d,(561,1260),"LIVE-BEOBACHTUNG",980,35)
    return _output(canvas,original)
