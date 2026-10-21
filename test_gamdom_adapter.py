import netrattler_keyless_odds as k

def _ev(**kw):
    ev = {"Deporte": "Soccer", "Estado": "N", "EsOutright": "N", "IdPartido": 7, "FechaPlanInicioPartido": "2026-10-22 16:00:00",
          "EquipoLocalCod": "a", "EquipoVisitanteCod": "b", "Pais": "ESP",
          "Info": {"Competidores": [{"Id": "a", "Nombre": "Real Madrid"}, {"Id": "b", "Nombre": "RB Leipzig"}]},
          "Modalidades": [
            {"Estado": "A", "Modalidad": "1x2", "Especificador": "{}", "Ofertas": [
              {"Estado": "A", "Localia": 1, "OfertaEvento": "Real Madrid", "CotizacionWeb": "1.23"},
              {"Estado": "A", "Localia": None, "OfertaEvento": "Draw", "CotizacionWeb": "6.8"},
              {"Estado": "A", "Localia": 2, "OfertaEvento": "RB Leipzig", "CotizacionWeb": "9.5"}]},
            {"Estado": "A", "Modalidad": "Total", "Especificador": "{total=2.5}", "Ofertas": [
              {"Estado": "A", "OfertaEvento": "Over 2.5", "CotizacionWeb": "1.6"},
              {"Estado": "A", "OfertaEvento": "Under 2.5", "CotizacionWeb": "2.3"}]},
            {"Estado": "A", "Modalidad": "Total", "Especificador": "{total=5.25}", "Ofertas": [
              {"Estado": "A", "OfertaEvento": "Over 5.25", "CotizacionWeb": "3"},
              {"Estado": "A", "OfertaEvento": "Under 5.25", "CotizacionWeb": "1.3"}]},
            {"Estado": "A", "Modalidad": "Both Teams To Score", "Especificador": "{}", "Ofertas": [
              {"Estado": "A", "OfertaEvento": "Yes", "CotizacionWeb": "1.5"}]}]}
    ev.update(kw)
    return ev

def test_complete_markets_only():
    rows = k._gamdom_rows([_ev()])
    got = {(r["market"], r["selection"]): r["odds"] for r in rows}
    assert got[("1x2", "home")] == 1.23 and got[("1x2", "away")] == 9.5
    assert got[("totals_2_5", "over_2_5")] == 1.6
    assert not any(m == "btts" for m, _ in got)      # incomplete -> dropped
    assert not any("5_25" in m for m, _ in got)      # other lines ignored
    assert {r["home_team"] for r in rows} == {"Real Madrid"}

def test_skips_live_and_non_football():
    assert k._gamdom_rows([_ev(Estado="J")]) == []
    assert k._gamdom_rows([_ev(Deporte="Tennis")]) == []
    assert k._gamdom_rows([_ev(Info={"Competidores": []})]) == []

def test_start_date_mapped_and_required():
    rows = k._gamdom_rows([_ev()])
    assert rows and all(r["match_date"] == "2026-10-22" for r in rows)
    e = _ev(); e.pop("FechaPlanInicioPartido")
    assert k._gamdom_rows([e]) == []
