import netrattler_builder_engine as e
def test_legset_same_across_styles():
    a=[{"player":"Pedri","match":"A vs B","category":"shots","line":1.0,"odds":1.4}]
    b=[{"player":"pedri","match":"A vs B","category":"shots","line":1.0,"odds":1.5}]
    assert e.legset_from_legs(a)==e.legset_from_legs(b)
    assert e.legset_from_legs(a)!=e.legset_from_legs([{**a[0],"line":2.0}])
