from netrattler_apif_profile_photo import pick
def row(f, l, photo): return {"player": {"name": f[0] + ". " + l, "firstname": f, "lastname": l, "photo": photo}}
def test_pick():
    rows = [row("Jonathan", "David", "u1"), row("Jonas", "David", "u2")]
    assert pick(rows, "Jonathan David") == "u1"
    assert pick(rows, "J. David") == ""  # mehrdeutig
    assert pick([row("Alphadjo", "Cissé", "u3")], "Alphadjo Cissè") == "u3"
