"""Nationalmannschaften: Flagge statt Vereinswappen (flagcdn.com, ISO-3166)."""
import re

_ISO = {
 "albania":"al","algeria":"dz","andorra":"ad","angola":"ao","argentina":"ar","armenia":"am","australia":"au","austria":"at",
 "azerbaijan":"az","belarus":"by","belgium":"be","benin":"bj","bolivia":"bo","bosnia and herzegovina":"ba","bosnia":"ba",
 "botswana":"bw","brazil":"br","bulgaria":"bg","burkina faso":"bf","burundi":"bi","cameroon":"cm","canada":"ca",
 "central african republic":"cf","chad":"td","chile":"cl","china":"cn","colombia":"co","comoros":"km","congo":"cg",
 "congo republic":"cg","dr congo":"cd","costa rica":"cr","croatia":"hr","cuba":"cu","curacao":"cw","cyprus":"cy",
 "czech republic":"cz","czechia":"cz","denmark":"dk","ecuador":"ec","egypt":"eg","el salvador":"sv",
 "equatorial guinea":"gq","estonia":"ee","eswatini":"sz","ethiopia":"et","faroe islands":"fo","finland":"fi",
 "france":"fr","gabon":"ga","gambia":"gm","georgia":"ge","germany":"de","ghana":"gh","gibraltar":"gi","greece":"gr",
 "guatemala":"gt","guinea":"gn","guinea-bissau":"gw","haiti":"ht","honduras":"hn","hungary":"hu","iceland":"is",
 "india":"in","indonesia":"id","iran":"ir","iraq":"iq","ireland":"ie","republic of ireland":"ie","israel":"il",
 "italy":"it","ivory coast":"ci","jamaica":"jm","japan":"jp","jordan":"jo","kazakhstan":"kz","kenya":"ke",
 "kosovo":"xk","kuwait":"kw","latvia":"lv","lebanon":"lb","liberia":"lr","libya":"ly","liechtenstein":"li",
 "lithuania":"lt","luxembourg":"lu","madagascar":"mg","malawi":"mw","mali":"ml","malta":"mt","mauritania":"mr",
 "mexico":"mx","moldova":"md","montenegro":"me","morocco":"ma","mozambique":"mz","namibia":"na","netherlands":"nl",
 "new zealand":"nz","nicaragua":"ni","niger":"ne","nigeria":"ng","north macedonia":"mk","northern ireland":"gb-nir",
 "norway":"no","oman":"om","panama":"pa","paraguay":"py","peru":"pe","philippines":"ph","poland":"pl","portugal":"pt",
 "qatar":"qa","romania":"ro","russia":"ru","rwanda":"rw","saudi arabia":"sa","scotland":"gb-sct","senegal":"sn",
 "serbia":"rs","sierra leone":"sl","singapore":"sg","slovakia":"sk","slovenia":"si","south africa":"za",
 "south korea":"kr","korea republic":"kr","spain":"es","sudan":"sd","suriname":"sr","sweden":"se","switzerland":"ch",
 "syria":"sy","tanzania":"tz","thailand":"th","togo":"tg","trinidad and tobago":"tt","tunisia":"tn","turkey":"tr",
 "turkiye":"tr","uganda":"ug","ukraine":"ua","united arab emirates":"ae","uae":"ae","united states":"us","usa":"us",
 "uruguay":"uy","uzbekistan":"uz","venezuela":"ve","vietnam":"vn","wales":"gb-wls","england":"gb-eng","zambia":"zm",
 "zimbabwe":"zw","cape verde":"cv","bahrain":"bh","barbados":"bb","guadeloupe":"gp","suriname ":"sr","san marino":"sm",
}


def flag_url(team):
    """Flaggen-URL nur fuer exakte Laendernamen (keine U21/Frauen/Vereine)."""
    k = re.sub(r"\s+", " ", str(team or "").strip().lower())
    iso = _ISO.get(k)
    return f"https://flagcdn.com/w160/{iso}.png" if iso else ""
