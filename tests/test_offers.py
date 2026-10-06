"""What the listing gives each kind of offer to say, read by plain code from
the seller's own words, and the check that holds a message to them."""

import pytest

from flip.offers import check_condition_talk, check_reasons, condition_said, point_for, read_listing, says_point

BROKEN = "iPhone 13 128GB. Broken back but everything works, battery 86%."
EXCELLENT = "iPhone 13 128GB. Excellent condition, boxed."
LEFT_OUT = "the message talks about the condition, but this draft leaves that out"


# ── reading the listing ─────────────────────────────────────────────────────

def test_the_listing_is_read_in_the_sellers_own_words():
    assert read_listing(BROKEN) == {"flaws": ["Broken back"], "good": []}
    assert read_listing(EXCELLENT) == {"flaws": [], "good": ["Excellent condition"]}
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


def test_a_flaw_the_seller_priced_in_is_still_the_reason():
    """Decided 3 Oct 2026: every flaw is a lower offer's reason, even one the seller says the price allows for
    (before, any such words left every flaw out)."""
    for text in ("Cracked screen hence the price.", "The back glass is cracked, which is reflected in the price",
                 "Small scratch on the screen. Battery 74%, priced accordingly. Priced to sell!"):
        assert point_for("lower", text)["about"] in ("flaw", "battery"), text
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
     ["the message says what's wrong with it in words the listing doesn't: stiff"]),
    ("Would you take £170 given the black dot and the screen burn?",
     ["the message says what's wrong with it in words the listing doesn't: burn"]),
    ("Hi, would you take £170 with the stiff hinge?",
     ["the message says what's wrong with it in words the listing doesn't: stiff"]),
    ("Hi, would you take £170 cash? Shame about the stiff hinge.",
     ["the message says what's wrong with it in words the listing doesn't: stiff"]),
    ("Hi mate, would you take £170 as it's cash?", []),  # a reason about the sale
    ("Hi, would you take £170 because it's a bit over my budget?", []),
    ("Hi mate, I can pay £220, the black dot is no problem.", []),
    ("Would you take £170 as I can collect today?", []),  # a reason about you, not the item
    ("I can pay £220. I don't mind the black dot on the screen as long as everything works.", []),
])
def test_a_reason_about_the_item_uses_the_listings_words(message, problems):
    assert check_reasons(message, "iPhone 13. Black dot on the screen, doesn't affect use. Battery 88%.") == problems


def test_a_message_never_copies_the_sellers_own_story():
    assert check_reasons("Hi mate, would you take £185 given I dropped it and cracked the back?",
                         "iPhone. I dropped it and cracked the back.") == \
        ['the message copies the seller\'s own story: "i dropped it and"']


CRACKED_BACK = "iPhone 12 64GB. Works perfectly, no scratches on the screen, back glass is cracked."


@pytest.mark.parametrize("message, kind, said", [
    ("Hi, would you take £170 for it? I know you dropped it and cracked the back.", "dropped or knocked", "dropped"),
    ("Hi, would you take £170 for it? I see it's been dropped, so the back glass is cracked.", "dropped or knocked",
     "it's been dropped"),
    ("Hi, would you take £170 as it fell off a table?", "dropped or knocked", "fell"),
    ("Hi, would you take £170, given it had a fall?", "dropped or knocked", "had a fall"),
    ("Hi, would you take £170 for it? It looks like it has never been dropped.", "dropped or knocked", "been dropped"),
    ("Hi, would you take £170 for it? Looks like it got water damage as well as the cracked back.", "water",
     "water damage"),
    # the test agents' (14 Sep): natural wordings that got through
    ("Hi, would you take £170 for it, as the back glass cracked after being dropped?", "dropped or knocked",
     "being dropped"),
    ("Hi, would you take £170 for it, as the back glass is cracked? I'm guessing it fell.", "dropped or knocked", "fell"),
    ("Hi, would you take £170 for it, as the back glass is cracked? Clearly dropped at some point.",
     "dropped or knocked", "dropped"),
    ("Hi, would you take £170 for it, as the back glass is cracked? It's had a few knocks by the look of it.",
     "dropped or knocked", "had a few knocks"),
    ("Hi, would you take £170 for it, as the back glass is cracked? Looks like it's been bashed about a bit.",
     "dropped or knocked", "it's been bashed"),
    ("Hi, would you take £170 for it, as the back glass is cracked? It's taken a hit by the look of it.",
     "dropped or knocked", "taken a hit"),
    ("Hi, would you take £170 for it, as the back glass is cracked? Looks like moisture damage too.", "water",
     "moisture damage"),
    ("Hi, would you take £170 for it, as the back glass is cracked? Looks like it's been through the wash.", "water",
     "through the wash"),
    ("Hi, would you take £170 for it, as the back glass is cracked? It's probably been rained on.", "water",
     "It's probably been rained on"),
])
def test_a_message_never_says_how_the_damage_happened_when_the_listing_doesnt(message, kind, said):
    """The explainer's sentences (12 Sep): every check passed them."""
    assert check_reasons(message, CRACKED_BACK) == \
        [f"the message says how it happened ({kind}), which the listing doesn't: \"{said}\""]


@pytest.mark.parametrize("message, listing", [
    ("Hi, would you take £170 for it, as the back glass is cracked?", CRACKED_BACK),
    ("Hi, would you take £170 for it? I can come and collect, just drop me a line.", CRACKED_BACK),
    ("Hi, I see you dropped the price, would you take £170 for it?", CRACKED_BACK),
    ("Hi, would you take £170 for it? Happy to drop round tonight.", CRACKED_BACK),
    ("Hi, would you take £170 for it? Was it ever dropped?", CRACKED_BACK),  # asked, not said
    ("Hi, would you take £170 for it? Is it water resistant still?", CRACKED_BACK),
    ("Hi, would you take £170 for it? I see it has been dropped and the back glass is cracked.",
     "iPhone 12 64GB. Dropped once, back glass is cracked."),
    ("Hi, would you take £150 for it as it got wet and the screen flickers?",
     "iPhone 12 64GB. Got wet in the rain, screen flickers."),
    # the test agents' (14 Sep): the price, an extra, collecting, the weather, asking, and listings in other words
    ("Hi, I see it's been dropped in price. Would you take £190 for it?", CRACKED_BACK),
    ("Hi, I see you've dropped your asking price. Would you take £190 for it?", CRACKED_BACK),
    ("Hi, I see you've knocked off a bit already. Would you take £190 for it?", CRACKED_BACK),
    ("Hi, would you take £190 with the carry case thrown in?", CRACKED_BACK),
    ("Hi, would you take £300 cash for it? I can run over tonight to collect it.", CRACKED_BACK),
    ("Hi, would you take £300 cash for it? I'm in Bath on Saturday so can collect then.", CRACKED_BACK),
    ("Hi, would you take £300 cash for it? Happy to collect today, even in the rain.", CRACKED_BACK),
    ("Hi, would you take £300 cash for it? I can collect tonight, will bring a bag in case it's wet.", CRACKED_BACK),
    ("Hi, would you take £300 cash for it? I can come and collect, or get it dropped off to me if easier.",
     CRACKED_BACK),
    ("Hi, I see it's been sat on here a while. Would you take £190 for it?", CRACKED_BACK),
    ("Hi, would you take £170 for it, as the back glass is cracked? Did it crack because it was dropped?",
     CRACKED_BACK),
    ("Hi, would you take £250 for it, as the back glass cracked after a tumble down the stairs?",
     "iPhone 13 128GB. Back glass cracked after a tumble down the stairs. Works perfectly."),
    ("Hi, would you take £210 for it, as the screen cracked when it was hit by a football?",
     "Galaxy S22 128GB. Screen cracked when it was hit by a football. Works perfectly otherwise."),
    ("Hi, would you take £150 for it, as it went in the sea and the screen flickers?",
     "iPhone 12 64GB. Went in the sea on holiday, screen now flickers."),
    ("Hi, would you take £150 for it, as it got wet and the screen flickers?",
     "iPhone 12 64GB. Got rained on, screen flickers now."),
    ("Hi, would you take £60 for it, as the screen flickers from the water damage?",
     "iPhone 11 64GB. Seawater damage, screen flickers."),
    ("Hi, would you take £170 for it, given it was knocked off the side and has a small dent?",
     "iPhone 12 64GB. Knoked off the side, small dent on the corner."),
])
def test_how_it_happened_is_fine_when_the_listing_says_it_and_everyday_drops_arent_damage(message, listing):
    assert check_reasons(message, listing) == []


def test_what_follows_if_in_a_statement_is_a_condition_not_a_claim():
    """A real longer message (18 Aug) was refused for "good" here."""
    listing = "iPhone 14 for sale. Few scratches on screen but does not effect. Works perfectly fine! No offers"
    message = ("Hi, I can pay £400 for it. I don't mind the few scratches on screen. Still available? "
               "I'm happy to take it as listed if it's still available and the battery is in good shape.")
    point = point_for("asking", listing, ["Few scratches on screen"])
    assert check_condition_talk(message, listing, point, True, "asking", 40000) == []
    claimed = message.replace("if it's still available and the battery", "and the battery")  # now it's a claim
    assert check_condition_talk(claimed, listing, point, True, "asking", 40000) == \
        ["the message says things about the condition the listing doesn't: good"]


@pytest.mark.parametrize("said", ["The few scratches on screen don't bother me.", "The scratches aren't a problem.",
                                  "I can live with the few scratches on screen.", "The scratches won't put me off.",
                                  "The few scratches on screen are fine by me."])
def test_not_minding_the_flaw_can_be_said_in_other_words(said):
    """A real rewrite (18 Aug) was refused for "don't bother me"."""
    listing = "iPhone 14 for sale. Few scratches on screen but does not effect. No offers"
    point = point_for("asking", listing, ["Few scratches on screen"])
    assert check_condition_talk(f"Hi, I can pay £400 for it. {said} Is it still available?", listing, point, True,
                                "asking", 40000) == []


def test_a_low_battery_is_the_reason_for_a_lower_offer_when_there_is_no_flaw():
    assert point_for("lower", "iPhone 14 Pro, great condition", [], battery="80") == \
        {"about": "battery", "says": ["battery health 80%"], "battery": "80"}
    assert point_for("lower", "iPhone 14 Pro, great condition", [], battery="85")["about"] == "battery"
    assert point_for("lower", "iPhone 14 Pro, great condition", [], battery="86") is None  # not a low one
    assert point_for("lower", "Cracked back", battery="80")["about"] == "flaw"  # a flaw comes first
    assert point_for("asking", "iPhone 14 Pro", [], battery="80") is None  # only a lower offer gives it
    assert point_for("lower", "Battery 80%, priced accordingly", [], battery="80")["about"] == "battery"  # said anyway


def test_a_long_part_is_cut_to_the_flaw_without_the_word_that_joins_it():
    """A real draft (12 Sep): "I dropped it last week and cracked the back glass" was quoted from "and"."""
    assert read_listing("I dropped it last week and cracked the back glass, screen is fine")["flaws"] == \
        ["cracked the back glass"]
    assert read_listing("Selling as upgraded, has a small crack on the back camera lens")["flaws"] == \
        ["small crack on the back camera lens"]


def test_a_low_battery_is_a_flaw_like_the_others():
    """The line set on 23 Sep: 85% or under is a flaw. With another flaw both are the reason, the title's figure
    and the description's are one flaw, and the battery alone is said as AlertFlip says it."""
    text = "iPhone 12 64GB 79% BH. Cracked back. Battery health 79%."
    assert read_listing(text)["flaws"] == ["79% BH", "Cracked back", "Battery health 79%"]
    assert point_for("lower", text) == {"about": "flaw", "says": ["Battery health 79%", "Cracked back"]}
    assert point_for("lower", "iPhone 12 64GB. Battery health 79%.") == \
        {"about": "battery", "says": ["battery health 79%"], "battery": "79"}
    # "81% BH" is said by the same figure in a message's own words
    assert says_point("Would you take £150 as the battery health is 81%?", {"about": "flaw", "says": ["81% BH"]})
    assert not says_point("Would you take £150 as the battery health is 91%?", {"about": "flaw", "says": ["81% BH"]})


def test_a_reasons_own_words_back_the_message():
    # "no cracks a couple scratches": the reader keeps the scratches (29 Sep), and the reason says them
    text = "iPhone 13 128GB. Good condition, no cracks a couple scratches on the back."
    point = {"about": "flaw", "says": ["a couple scratches on the back"]}
    message = "Hi, would you take £255 for it? I'm offering that because of a couple scratches on the back."
    assert check_condition_talk(message, text, point, True) == []
    assert check_condition_talk("Hi, would you take £255 for it? It has a cracked screen.", text, point, True) != []
