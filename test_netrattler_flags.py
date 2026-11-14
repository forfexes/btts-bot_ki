from netrattler_flags import flag_url
def test_flags():
    assert flag_url("Italy").endswith("/it.png")
    assert flag_url("Congo Republic").endswith("/cg.png")
    assert flag_url("Italy U21") == "" and flag_url("Girona") == ""
