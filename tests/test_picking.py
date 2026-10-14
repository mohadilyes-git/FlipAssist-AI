"""How many flaws a lower offer gives when you pick (flip.picking, 14 Oct 2026): the worst first, by how much each cuts
the price, said in the seller's words and order; one sentence cut into its flaws only where each side stands alone."""

from flip.picking import left_out_said, pick_flaws, pieces_of

RUN_ON = ("iphone 11 back dot in the front screen with the some dust marks at the back , and it has also a thin crack "
          "across the screen from top left to top bottom and battery is under 80")
THREE = ["Back glass cracked in the top right corner.", "Face ID not working.", "Battery 79%."]
THREE_TEXT = "iPhone 13. " + " ".join(THREE)


def test_a_run_on_sentence_is_cut_into_its_flaws():
    assert pieces_of(RUN_ON, RUN_ON) == ["iphone 11 back dot in the front screen", "the some dust marks at the back",
                                         "it has also a thin crack across the screen from top left to top bottom",
                                         "battery is under 80"]


def test_and_joins_two_flaws_only_when_each_side_names_its_own_part():
    text = "Light scratches on the screen and a small dent on the corner"
    assert pieces_of(text, text) == ["Light scratches on the screen", "a small dent on the corner"]
    for whole in ("screen cracked and scratched", "Light scratches and scuffs on the screen",
                  "some damage to the screen and sides of the phone"):
        assert pieces_of(whole, whole) == [whole]


def test_the_worst_go_first_and_are_said_in_the_sellers_order():
    assert pick_flaws(THREE, THREE_TEXT, 1) == (["Face ID not working"],
                                                ["Back glass cracked in the top right corner", "Battery 79%"])
    assert pick_flaws(THREE, THREE_TEXT, 2) == (["Back glass cracked in the top right corner", "Face ID not working"],
                                                ["Battery 79%"])
    picked, left_out = pick_flaws([RUN_ON], RUN_ON, 1)
    assert picked == ["it has also a thin crack across the screen from top left to top bottom"] and len(left_out) == 3
    # a lock cuts the price most, so it's the one flaw
    assert pick_flaws(["small scratch on the back", "It's iCloud locked"], "iPhone 14. small scratch on the back. "
                      "It's iCloud locked", 1) == (["It's iCloud locked"], ["small scratch on the back"])


def test_no_more_flaws_than_you_picked_keeps_the_sentences_as_they_are():
    assert pick_flaws(THREE, THREE_TEXT, 3) == (THREE, [])
    assert pick_flaws(["screen cracked and scratched"], "iPhone 12. screen cracked and scratched", 1) == \
        (["screen cracked and scratched"], [])
    for not_a_number in ("all", None, 0, 4):
        assert pick_flaws(THREE, THREE_TEXT, not_a_number) == (THREE, [])


def test_a_sentence_code_sees_no_flaw_in_still_counts_whole():
    lines = ["iPhone is fully operational, just some damage to the screen and sides of the phone.", "sound is a little muffle"]
    text = "iphone 11. " + " ".join(lines)
    assert pick_flaws(lines, text, 1) == (["some damage to the screen and sides of the phone"], ["sound is a little muffle"])
    assert pick_flaws(lines, text, 2) == (lines, [])


def test_the_same_flaw_in_the_title_and_the_description_is_one():
    lines = ["iPhone 13 cracked back", "Cracked back", "Battery 79%"]
    assert pick_flaws(lines, "iPhone 13 cracked back. Cracked back. Battery 79%", 2) == (lines, [])


def test_a_left_out_flaw_said_anyway_is_named_but_a_question_isnt():
    picked, left_out = ["Back glass cracked in the top right corner"], ["Face ID not working", "Battery 79%"]
    said = "Hi, would you take £100? I'm offering that because the back glass is cracked and the battery health is 79%."
    assert left_out_said(said, picked, left_out, 10000) == ["battery"]
    asked = "Hi, would you take £100? I'm offering that because the back glass is cracked. What's the battery health?"
    assert left_out_said(asked, picked, left_out, 10000) == []
    assert left_out_said("Would you take £100 given the scratches on the screen?", ["a small dent on the corner"],
                         ["Light scratches on the screen"], 10000) == ["scratch"]
    assert left_out_said(said, picked, [], 10000) == []
