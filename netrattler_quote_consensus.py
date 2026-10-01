"""NETRATTLER quote provenance + consensus guard. No synthetic prices."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

TRUSTED_SINGLE={"oddspapi","pinnacle","bet365","5dollar","fieldfunded","sockodds"}

@dataclass
class Quote:
    event:str; market:str; selection:str; line:Optional[float]; odds:float
    source:str; bookmaker:str=""; observed_at:str=""; provider_event_id:str=""
    def row(self)->Dict[str,Any]: return asdict(self)

def _n(v:Any)->str: return " ".join(str(v or "").lower().replace("_"," ").split())
def _line(v:Any):
    try:return round(float(v),3)
    except:return None
def normalize_quote(row:Dict[str,Any])->Optional[Quote]:
    try:o=float(row.get("odds") or row.get("decimal_odds") or 0)
    except:return None
    if not 1.01 <= o <= 100:return None
    event=str(row.get("event") or row.get("match") or "").strip()
    market=_n(row.get("market") or row.get("market_id"))
    selection=_n(row.get("selection") or row.get("outcome"))
    if not event or not market or not selection:return None
    return Quote(event,market,selection,_line(row.get("line")),o,
        _n(row.get("source") or "unknown"),str(row.get("bookmaker") or ""),
        str(row.get("observed_at") or datetime.now(timezone.utc).isoformat()),
        str(row.get("provider_event_id") or row.get("event_id") or ""))

def consensus(rows:Iterable[Dict[str,Any]], max_price_delta:float=.18, allow_trusted_single:bool=True)->Dict[str,Any]:
    qs=[q for q in (normalize_quote(x) for x in rows) if q]
    if not qs:return {"ok":False,"reason":"no_valid_quote","quotes":[]}
    base=qs[0]
    same=[q for q in qs if q.market==base.market and q.selection==base.selection and q.line==base.line]
    independent={q.source for q in same}
    spread=(max(q.odds for q in same)-min(q.odds for q in same))/max(.01,min(q.odds for q in same))
    trusted=base.source in TRUSTED_SINGLE or _n(base.bookmaker) in TRUSTED_SINGLE
    ok=(len(independent)>=2 and spread<=max_price_delta) or (allow_trusted_single and len(same)==1 and trusted)
    return {"ok":ok,"reason":"confirmed" if ok else ("price_divergence" if spread>max_price_delta else "single_weak_source"),
            "sources":sorted(independent),"spread":round(spread,4),"quotes":[q.row() for q in same]}
