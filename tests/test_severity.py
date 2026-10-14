"""How bad a listing's damage is (flip.severity, fix 1, 14 Oct 2026), and the cut that takes off a clean one's price by
its price tier. Made-up sentences only: no real seller's words."""

import pytest

from flip.severity import damage_cut, severity, table, tier


@pytest.mark.parametrize("flaws, expected", [
    (["Screen is smashed"], "severe"),
    (["Back glass shattered"], "severe"),
    (["Spider web crack across the screen"], "severe"),
    (["Badly cracked screen"], "severe"),
    (["Screen needs replacing"], "severe"),
    (["Big dent on the lid"], "severe"),
    (["Frame is bent"], "severe"),
    (["Cracked screen"], "moderate"),
    (["The back glass is cracked"], "moderate"),
    (["A dent on the back"], "moderate"),
    (["A few small cracks on the screen"], "moderate"),
    (["Small crack on the front and a small crack on the back"], "moderate"),
    (["Small crack on the screen"], "minor"),
    (["Hairline crack in the corner of the screen"], "minor"),
    (["Tiny chip on the frame"], "minor"),
    (["Small dent on the corner"], "minor"),
    (["Camera lens is cracked"], "minor"),
    (["Slightly cracked back"], "minor"),
])
def test_how_bad_the_damage_is(flaws, expected):
    assert severity(flaws) == expected


def test_no_damage_said_is_none_and_a_denial_isnt_damage():
    assert severity(["Battery health 79%"]) is None
    assert severity(["No cracks or chips, light scratches"]) is None
    assert severity([]) is None


def test_the_worst_damage_said_counts():
    assert severity(["Tiny chip on the corner", "Screen is smashed"]) == "severe"
    assert severity(["Small chip on the frame", "Cracked back"]) == "moderate"


def test_a_modifier_belongs_to_its_own_word():
    # "minor" is the scuffs', not the crack's; "light" is the chips', not the smashed glass's
    assert severity(["Minor scuffs and the back is cracked"]) == "moderate"
    assert severity(["Smashed back glass, has a few light chips on the edges"]) == "severe"
    assert severity(["Nothing major, a couple of dents"]) == "moderate"


def test_the_title_counts_only_when_the_flaws_dont_say_it():
    assert severity(["The back is slightly cracked"], title="iPhone 13 Cracked Back") == "minor"
    assert severity([], title="iPhone 13 Smashed Screen") == "severe"


def test_typos_of_the_damage_words():
    assert severity(["craked screen"]) == "moderate"
    assert severity(["screen smahed"]) == "severe"


def test_the_tier_comes_from_a_clean_ones_price():
    low, high = table()["tables"]["iphone/uk"]["edges"]
    assert tier("iphone", "uk", low - 1) == "bottom"
    assert tier("iphone", "uk", low) == "middle"
    assert tier("iphone", "uk", high) == "top"
    assert tier("iphone", "fr", 300) is None and tier("tablet", "uk", 300) is None


def test_a_cheap_phone_loses_a_bigger_share_and_worse_damage_more():
    low, high = table()["tables"]["iphone/uk"]["edges"]
    cheap, dear = low - 20, high + 200
    for price in (cheap, dear):
        cuts = [damage_cut("iphone", "uk", price, level)["cut"] for level in ("minor", "moderate", "severe")]
        assert cuts == sorted(cuts, reverse=True) and all(c < 0 for c in cuts)  # severe cuts most
    assert damage_cut("iphone", "uk", cheap, "moderate")["cut"] < damage_cut("iphone", "uk", dear, "moderate")["cut"]
    found = damage_cut("iphone", "uk", dear, "moderate")
    assert (found["tier"], found["rough"]) == ("top", False) and found["n"] >= 10


def test_a_borrowed_cell_says_where_from_and_is_rough():
    # UK Samsung: none in the listings, every cell is the US Samsung's
    found = damage_cut("samsung", "uk", 500, "minor")
    assert found["rough"] is True and found["from"].startswith("the US")
    assert table()["tables"]["samsung/uk"]["rough_edges"] is True
    # UK MacBook: 32 listings, so a thin cell is the US one's
    assert any(cell["rough"] and cell["from"].startswith("the US")
               for row in table()["tables"]["macbook/uk"]["cuts"].values() for cell in row.values())


def test_no_table_or_no_level_is_none():
    assert damage_cut("tablet", "uk", 300, "minor") is None
    assert damage_cut("iphone", "uk", 300, None) is None
    assert damage_cut("iphone", "uk", None, "minor") is None
