"""What the listing gives each kind of offer to say, read by plain code from
the seller's own words, and the check that holds a message to them."""

import pytest

from flip.offers import check_condition_talk, check_reasons, condition_said, point_for, read_listing, says_point

BROKEN = "iPhone 13 128GB. Broken back but everything works, battery 86%."
EXCELLENT = "iPhone 13 128GB. Excellent condition, boxed."
LEFT_OUT = "the message talks about the condition, but this draft leaves that out"


# ── reading the listing ─────────────────────────────────────────────────────

def test_the_listing_is_read_in_the_sellers_own_words():
    assert read_listing(BROKEN) == {"flaws": ["Broken back"], "good": [], "priced_in": False}
    assert read_listing(EXCELLENT) == {"flaws": [], "good": ["Excellent condition"], "priced_in": False}
    assert read_listing("Minor cosmetic damage on the corner, works perfectly")["flaws"] == \
        ["Minor cosmetic damage on the corner"]
    assert read_listing("Condition: good. Light scratch on the screen")["flaws"] == ["Light scratch on the screen"]


def test_what_isnt_a_flaw_isnt_read_as_one():
    for text in ("No scratches, no dents, fully working", "Red Dead Redemption 2 included", "Comes with a case"):
        assert read_listing(text)["flaws"] == [], text


def test_a_long_run_on_listing_is_quoted_around_the_flaw():
    text = ("iphone 13 pro max 256gb unlocked to all networks battery health 86% small crack on the back camera "
            "lens otherwise perfect working order")
    assert read_listing(text)["flaws"] == ["small crack on the back camera lens"]


def test_each_kind_of_offer_gets_its_own_point():
    assert point_for("lower", BROKEN) == {"about": "flaw", "says": ["Broken back"]}
    assert point_for("asking", BROKEN) == {"about": "flaw", "says": ["Broken back"]}
    assert point_for("more", BROKEN) is None  # a flawed item is never praised
    assert point_for("more", EXCELLENT) == {"about": "condition", "says": ["Excellent condition"]}
    assert point_for("lower", EXCELLENT) is None and point_for("asking", EXCELLENT) is None


def test_a_flaw_the_seller_priced_in_is_no_reason_to_offer_less():
    for text in ("Cracked screen hence the price.", "The back glass is cracked, which is reflected in the price"):
        assert read_listing(text)["priced_in"], text
        assert point_for("lower", text) is None
        assert point_for("asking", text)["about"] == "flaw"  # you can still say you don't mind it


def test_a_no_in_one_sentence_doesnt_hide_a_flaw_in_the_next():
    assert read_listing("No box. Smashed screen.")["flaws"] == ["Smashed screen"]


def test_dont_mind_isnt_read_as_no_flaw():
    assert condition_said("I don't mind the scratches") == {"scratch"}
    assert condition_said("not fussed about the broken back") == {"fault"}
    assert condition_said("No scratches or dents") == set()
    assert condition_said("It isn't in good condition") == set()


# ── checking a message ──────────────────────────────────────────────────────

def test_the_message_says_the_flaw_only_as_the_listing_does():
    point = point_for("lower", BROKEN)
    assert check_condition_talk("Hi mate, would you take £170 as the back is broken?", BROKEN, point, True) == []
    assert check_condition_talk("Hi mate, the back is broken and the screen is scratched, would you take £170?",
                                BROKEN, point, True) == \
        ["the message says things about the condition the listing doesn't: scratch"]
    assert check_condition_talk("Hi mate, would you take £170?", BROKEN, point, True) == \
        ['the message leaves out what the listing says: "Broken back"']
    # Gemma's real draft: it asks about the flaw the listing already states
    assert check_condition_talk("Hi mate, I'm interested in buying this iPhone 13. Can I pay £185? Does this have a "
                                "broken back?", BROKEN, point, True) == \
        ['the message asks about "Broken back" instead of saying it']


def test_at_the_asking_price_the_message_says_you_dont_mind_the_flaw():
    point = point_for("asking", BROKEN)
    for fine in ("Hi mate, I don't mind the broken back, happy to pay £220.",
                 "Hi mate, I can pay £220, the broken back is no problem."):
        assert check_condition_talk(fine, BROKEN, point, True, "asking") == [], fine
    assert check_condition_talk("I can pay £220 for it. Broken back.", BROKEN, point, True, "asking") == \
        ["the message names \"Broken back\" but doesn't say you don't mind it"]


@pytest.mark.parametrize("message", [
    "Hi mate, would you take £170 to allow for the broken back?",
    "Hi mate, would you take £170 to account for the broken back?",
    "Hi mate, would you take £170 in light of the broken back?",
    "Hi mate, would you take £170 for it so I can fix the broken back?",
    "Hi mate, would you take £170 for the phone that has the broken back?",
    "Hi mate, would you take £170 as the back's broken?",
])
def test_the_flaw_given_inside_the_offer_question_counts_as_said(message):
    assert check_condition_talk(message, BROKEN, point_for("lower", BROKEN), True, offer=17000) == [], message


@pytest.mark.parametrize("message", [
    "Hi mate, would you take £170 for it even though the screen is cracked?",
    "Hi mate, would you take £170 for the scratched one?",
    "Hi mate, would you take £170 now that the battery is faulty?",
])
def test_a_made_up_flaw_inside_the_offer_question_fails(message):
    problems = check_condition_talk(message, EXCELLENT, None, False, offer=17000)
    assert any(p.startswith("the message says things about the condition the listing doesn't") for p in problems), \
        message


@pytest.mark.parametrize("listing, message, claim", [
    ("Faulty, won't turn on. Spares or repairs.", "Hi mate, would you take £170? Good to see it's in full working order.",
     "working"),
    ("Selling as I've upgraded.", "Hi mate, would you take £170? I see it's brand new and still sealed.", "new"),
    ("Selling as I've upgraded.", "Hi mate, would you take £170? It looks in great nick and well looked after.",
     "good"),
])
def test_a_paraphrased_condition_claim_is_held_to_the_listing(listing, message, claim):
    assert f"the message says things about the condition the listing doesn't: {claim}" in \
        check_condition_talk(message, listing, None, False, offer=17000)


def test_praise_in_other_words_still_counts_as_praise():
    assert point_for("more", "PS5 Slim. Great nick, boxed.") == {"about": "condition", "says": ["Great nick"]}
    assert check_condition_talk("Hi mate, I can pay £400 as it looks in great nick.", BROKEN, None, False,
                                "more", 40000)[0] == LEFT_OUT  # never praise a flawed item


def test_a_time_that_works_for_you_isnt_a_claim_the_item_works():
    assert check_condition_talk("Hi mate, would you take £170? Let me know a time that works for you.",
                                "Faulty, won't turn on.", None, False, offer=17000) == []


@pytest.mark.parametrize("message", [
    "Hi mate, would you take £170? Just wondering if there are any marks or scratches?",
    "Hi mate, would you take £170? I was wondering if it has any marks or scratches?",
    "Hi mate, would you take £170? Let me know if there are any marks or scratches.",
])
def test_asking_in_a_roundabout_way_is_still_asking(message):
    assert check_condition_talk(message, "Selling as I've upgraded.", None, False, offer=17000) == []


def test_a_draft_meant_to_leave_the_flaw_out_mustnt_slip_it_in():
    point = point_for("lower", BROKEN)
    assert check_condition_talk("Hi mate, would you take £170 given the broken back?", BROKEN, point, False) == \
        [LEFT_OUT]
    # asking about something else isn't saying it
    assert check_condition_talk("Hi mate, any other marks? Would you take £170?", BROKEN, point, False) == []


def test_asking_about_the_condition_is_always_fine():
    assert check_condition_talk("Hi mate, any scratches? Would you take £170?", EXCELLENT, None, False) == []
    assert check_condition_talk("Perfect, I can collect today.", EXCELLENT, None, False) == []


def test_praise_is_held_to_the_listings_level():
    point = point_for("more", EXCELLENT)
    assert check_condition_talk("Hi mate, I can pay £210 as it's in excellent condition.", EXCELLENT, point, True) == []
    assert check_condition_talk("Hi mate, I can pay £210 as it's in great condition.", EXCELLENT, point, True) == []
    assert check_condition_talk("Hi mate, I can pay £210 as it's mint.", EXCELLENT, point, True) == [
        'the message leaves out what the listing says: "Excellent condition"',
        "the message says things about the condition the listing doesn't: flawless"]


def test_the_flaws_flip_reader_found_take_the_place_of_codes_own():
    text = "iPhone 13. Black dot on the screen, doesn't affect use."
    assert point_for("lower", text) is None  # code has no word for a dot
    assert point_for("lower", text, ["Black dot on the screen"]) == {"about": "flaw", "says": ["Black dot on the screen"]}
    assert point_for("more", "iPhone 13. Great condition. Black dot on the screen.", ["Black dot on the screen"]) is None


@pytest.mark.parametrize("message, said", [
    ("Would you take £185, given the black dot on the screen?", True),
    ("Would you take £185 given the black dot?", True),  # most of its words
    ("Would you take £185 given the dot?", False),  # one word of three isn't saying it
    ("Would you take £185?", False),
    ("Would you take £185 given the black screen?", False),  # its words in another order say something else
    ("Would you take £185 as the screen is black?", False),
])
def test_a_flaw_code_has_no_word_for_is_said_with_most_of_its_words(message, said):
    assert says_point(message, {"about": "flaw", "says": ["Black dot on the screen"]}) is said


def test_the_condition_check_holds_a_message_to_a_flaw_only_ai_found():
    text = "iPhone 13. Black dot on the screen, doesn't affect use."
    point = point_for("lower", text, ["Black dot on the screen"])
    assert check_condition_talk("Would you take £185, given the black dot on the screen?", text, point, True) == []
    assert check_condition_talk("Would you take £185?", text, point, True) == \
        ['the message leaves out what the listing says: "Black dot on the screen"']
    assert check_condition_talk("Does it have a black dot on the screen? Would you take £185?", text, point, True,
                                offer=18500) == ['the message asks about "Black dot on the screen" instead of saying it']


@pytest.mark.parametrize("message, problems", [
    ("Hi mate, would you take £170 given the black dot on the screen? Can collect today.", []),
    ("Hi mate, would you take £170 given the black dot on the screen and the stiff hinge?",
     ["the message gives a reason the listing doesn't: stiff, hinge"]),
    ("Would you take £170 given the black dot and the screen burn?",
     ["the message gives a reason the listing doesn't: burn"]),
    ("Would you take £170 as I can collect today?", []),  # a reason about you, not the item
    ("I can pay £220. I don't mind the black dot on the screen as long as everything works.", []),
])
def test_a_reason_about_the_item_uses_the_listings_words(message, problems):
    assert check_reasons(message, "iPhone 13. Black dot on the screen, doesn't affect use. Battery 88%.") == problems
