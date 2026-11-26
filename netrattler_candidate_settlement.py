"""Verified settlement presentation contract for original-layout card snapshots.

No source lookups, odds recomputation, P&L inference, or network calls.
The caller must provide the saved original selection and independently
verified final grades keyed by the exact fixture and quote identifiers.
"""
from collections.abc import Mapping

LABELS={"won":"GEWONNEN","lost":"VERLOREN","void":"VOID","push":"PUSH"}
COLORS={"won":"#40F58A","lost":"#FF7373","void":"#D4E4EE","push":"#D4E4EE"}

def grades(record, settlement):
    if settlement is None:
        return None
    if not isinstance(settlement, Mapping) or settlement.get("verified") is not True:
        raise ValueError("Explicit verified settlement evidence required")
    rows=record.get("legs") or [record]
    actual=settlement.get("legs")
    if not isinstance(actual,list) or len(actual)!=len(rows):
        raise ValueError("Settlement must cover every original selection")
    def key(row):
        if not isinstance(row,Mapping):
            raise ValueError("Invalid settlement selection")
        values=tuple(str(row.get(k) or "").strip() for k in ("fixture_id","quote_id"))
        if not all(values):
            raise ValueError("Missing exact fixture/quote identity")
        return values
    expected=[key(row) for row in rows]
    if len(set(expected))!=len(expected):
        raise ValueError("Original selection identities are ambiguous")
    by_key={}
    for row in actual:
        k=key(row)
        status=row.get("status")
        if k in by_key or k not in expected or status not in LABELS or not str(row.get("source") or "").strip():
            raise ValueError("Wrong, duplicate or unverified settlement selection")
        by_key[k]=status
    if set(by_key)!=set(expected):
        raise ValueError("Incomplete settlement")
    return [by_key[k] for k in expected]

def footer(record, settlement):
    states=grades(record,settlement)
    if states is None:
        return "SANDBOX · KEIN TIPP"
    if len(states)==1:
        label=LABELS[states[0]]
    else:
        label=" · ".join(str(states.count(s))+" "+LABELS[s] for s in LABELS if s in states)
    # Do not infer a combined bet's cash settlement from theoretical odds.
    return "SANDBOX · "+label
