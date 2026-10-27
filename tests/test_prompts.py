

def test_every_catalogue_iphone_colour_says_how_it_looks():
    # 14 Oct: the AI picking the colour from the photos is told how each of the model's own colours looks on it
    from flip.catalogue import load_catalogue
    from flip.prompts import COLOUR_LOOKS
    for model in load_catalogue():
        if model["category"] == "phones" and model["brand"] == "Apple":
            assert sorted(COLOUR_LOOKS[model["id"]]) == sorted(model["colours"]), model["id"]


def test_a_colour_counts_only_when_seen_on_the_phones_back_or_frame():
    from flip.prompts import colour_seen
    assert [colour_seen(a) for a in ({"colour": "Blue", "seen_on": "back"}, {"colour": "Blue", "seen_on": "frame"},
                                     {"colour": "Blue", "colour_seen_on": "back and frame"},
                                     {"colour": "Blue", "seen_on": "not shown"}, {"colour": "Blue"},
                                     {"colour": "unsure", "seen_on": "back"})] == \
        ["Blue", "Blue", "Blue", "unsure", "unsure", "unsure"]
