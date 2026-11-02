"""Your own reason for any listing ("would you take £X given the condition?"),
as the 26 Sep red team found it: taken whole, wherever it sits in the
sentence, swapped for the listing's flaw or taken out when there's none to
give, and never followed by a second reason. No AI anywhere: the drafts are
code's own (writer="template"), through the drafter's checks."""

import pytest

from flip.message_drafter import draft_message
from flip.style import style_card
from flip.writer import with_reason

CRACK = {"about": "flaw", "says": ["Small crack on the back"]}
NO_CHARGE = {"about": "flaw", "says": ["Doesn't charge"]}
MARKS_AND_BATTERY = {"about": "flaw", "says": ["Battery health 79%", "Light marks on the frame"]}


def listing(title, description, asking="200"):
    return {"id": "x", "title": title, "description": description, "asking_price": asking, "marketplace": "facebook"}


CRACKED = listing("iPhone 13 128GB", "Small crack on the back, works perfectly")
DEAD_PORT = listing("iPhone 12 64GB", "Doesn't charge, needs a new port")
MINT = listing("iPhone 13 128GB", "Immaculate condition, boxed with charger")


def reading(*flaws):
    """The listing as the model read it (what the drafter is given)."""
    return {"flaws": list(flaws), "pickup": "", "no_offers": "", "read_by": "gemma3:4b"}


def habit(sentence, closing="Can collect today.", opener="Hi mate,"):
    """Three past Facebook messages, all under asking, with the same offer sentence (£X: the old price)."""
    return [{"my_message": " ".join(p for p in (opener, sentence.replace("£X", f"£{price}"), closing) if p),
             "asking_price": asking, "marketplace": "facebook", "listing_title": title}
            for price, asking, title in (("150", "200", "iPhone 12"), ("90", "120", "AirPods Pro"),
                                         ("300", "380", "iPhone 14 Pro"))]


def drafted(lst, messages, read, kind="lower", mention=True):
    """code's own message for the listing, and whether it passed the checks."""
    # Say the flaw: Yes, as you'd pick it on the message (14 Oct: whether you give it isn't learned from your style)
    result = draft_message(lst, style_card(messages), kind=kind, reading=read, writer="template", mention=mention)
    return result["status"], (result["answer"] or {}).get("message")


# ── order-leads-generic-removed-tail: no flaw to give, the whole of your reason goes ──

def test_your_reason_goes_whole_when_theres_no_flaw_to_give():
    """'given the state it's in' came out 'would you take £170 it's in?' on every lower offer: only 'given the state'
    was taken out. ('state' isn't learned as condition talk, so the cracked listing has nothing to give either.)"""
    state = habit("Would you take £X given the state it's in?", closing="Can collect today, cash ready.")
    for lst, read in ((CRACKED, reading("Small crack on the back")), (MINT, reading())):  # Say the flaw: No
        assert drafted(lst, state, read, mention=False) == \
            ("ready", "Hi mate, would you take £170? Can collect today, cash ready.")
    assert drafted(MINT, habit("would you take £X given the condition it's in?"), reading()) == \
        ("ready", "Hi mate, would you take £170? Can collect today.")


@pytest.mark.parametrize("sentence", [
    "Would you take £[OFFER] given the state it's in?", "Would you take £[OFFER] given the state it’s in?",
    "Would you take £[OFFER] given the condition it's in?", "Would you take £[OFFER] due to wear and tear?",
    "Would you take £[OFFER] considering the damage to it?", "Would you take £[OFFER] given the faults its got?",
    "Would you take £[OFFER] given the state of it?", "Would you take £[OFFER], given the condition?",
    "Would you take £[OFFER] considering it's state?", "Would you take £[OFFER] - given the conditon?",
])
def test_each_whole_reason_comes_out_with_nothing_left_behind(sentence):
    assert with_reason(sentence, "lower", None) == "Would you take £[OFFER]?"


def test_what_follows_your_reason_stays_when_it_goes():
    assert with_reason("Would you take £[OFFER] given the condition mate?", "lower", None) == "Would you take £[OFFER] mate?"
    assert with_reason("Would you take £[OFFER] given the condition, cash in hand?", "lower", None) == \
        "Would you take £[OFFER], cash in hand?"
    assert with_reason("would you take £[OFFER] given the condition x", "lower", None) == "would you take £[OFFER] x"


def test_a_reason_that_says_more_than_the_generic_words_gets_no_wording():
    """'given the condition and that I can collect today' isn't the generic reason alone: taking out 'given the
    condition' left '...£170 and that I can collect today?', and keeping it says 'given the condition' of a mint
    phone. The AI words it (and with a flaw, it never gets a second reason after it)."""
    sentence = "Would you take £[OFFER], given the condition and that I can collect today?"
    assert with_reason(sentence, "lower", None) is None
    assert with_reason(sentence, "lower", CRACK) is None
    status, message = drafted(MINT, habit("would you take £X, given the condition and that I can collect today?"),
                              reading())
    assert (status, message) == ("needs you", None)  # no wording, so the AI's turn: never a crash


# ── order-leads-generic-substituted-tail: the flaw takes the whole of your reason's place ──

def test_the_listings_flaw_takes_the_place_of_your_whole_reason():
    """The flaw landed in the middle: '...given the small crack on the back it's in?', '...because it doesn't charge
    and tear?', '...considering the small crack on the back to it?'."""
    assert drafted(CRACKED, habit("would you take £X given the condition it's in?"), reading("Small crack on the back")) == \
        ("ready", "Hi mate, would you take £170 given the small crack on the back? Can collect today.")
    assert drafted(DEAD_PORT, habit("would you do £X due to wear and tear?"), reading("Doesn't charge")) == \
        ("ready", "Hi mate, would you do £170 because it doesn't charge? Can collect today.")
    assert drafted(CRACKED, habit("would you accept £X considering the damage to it?"),
                   reading("Small crack on the back")) == \
        ("ready", "Hi mate, would you accept £170 considering the small crack on the back? Can collect today.")


def test_wear_and_tear_with_a_crack_is_said_and_not_refused():
    """The verifier's probe: 'due to wear and tear' on a cracked listing was refused ('tear' isn't the listing's)."""
    assert drafted(CRACKED, habit("would you do £X due to wear and tear?"), reading("Small crack on the back")) == \
        ("ready", "Hi mate, would you do £170 due to the small crack on the back? Can collect today.")


@pytest.mark.parametrize("sentence, said", [
    ("Would you take £[OFFER] given the faults its got?", "Would you take £[OFFER] given that it doesn't charge?"),
    ("Would you take £[OFFER] given it's got a few marks?", "Would you take £[OFFER] given that it doesn't charge?"),
    ("would you take £[OFFER] given the condition x", "would you take £[OFFER] given that it doesn't charge? x"),
    ("Would you take £[OFFER] given the condition or is that too cheeky?",
     "Would you take £[OFFER] given that it doesn't charge or is that too cheeky?"),
    ("Would you take £[OFFER] given the condition, cash in hand?",
     "Would you take £[OFFER] given that it doesn't charge, cash in hand?"),
])
def test_the_flaw_goes_where_your_reason_was_whatever_follows_it(sentence, said):
    assert with_reason(sentence, "lower", NO_CHARGE) == said


# ── order-leads-lead-unseen: your reason first in the sentence, "it's condition", "cos of" ──

def test_your_reason_said_first_takes_the_flaw_and_goes_on_a_mint_listing():
    """'Given the condition, would you take £170, given the small crack on the back?', and 'Given the condition'
    left on an immaculate listing."""
    first = habit("Given the condition, would you take £X?", opener="Hi mate, is this still available?")
    assert drafted(CRACKED, first, reading("Small crack on the back")) == \
        ("ready", "Hi mate, is this still available? Given the small crack on the back, would you take £170? "
                  "Can collect today.")
    assert drafted(MINT, first, reading()) == \
        ("ready", "Hi mate, is this still available? Would you take £170? Can collect today.")


def test_its_condition_typed_with_an_apostrophe_is_your_reason_too():
    assert drafted(DEAD_PORT, habit("Would you take £X given it's condition?"), reading("Doesn't charge")) == \
        ("ready", "Hi mate, would you take £170 given that it doesn't charge? Can collect today.")
    assert drafted(MINT, habit("Would you take £X given it's condition?"), reading()) == \
        ("ready", "Hi mate, would you take £170? Can collect today.")


def test_your_greeting_then_your_reason_first():
    """The verifier's 'Hi mate, given the condition would you take £X?': no comma of yours is added."""
    first = habit("given the condition would you take £X?")
    assert drafted(CRACKED, first, reading("Small crack on the back")) == \
        ("ready", "Hi mate, given the small crack on the back would you take £170? Can collect today.")
    assert drafted(MINT, first, reading()) == ("ready", "Hi mate, would you take £170? Can collect today.")


@pytest.mark.parametrize("sentence, crack, no_charge, none", [
    ("Would you take £[OFFER] cos of the condition?", "Would you take £[OFFER] cos of the small crack on the back?",
     "Would you take £[OFFER] cos it doesn't charge?", "Would you take £[OFFER]?"),
    ("would you take £[OFFER] coz of the scratches?", "would you take £[OFFER] coz of the small crack on the back?",
     "would you take £[OFFER] coz it doesn't charge?", "would you take £[OFFER]?"),
    ("Considering the state of it, any chance of £[OFFER]?",
     "Considering the small crack on the back, any chance of £[OFFER]?",
     "Considering that it doesn't charge, any chance of £[OFFER]?", "Any chance of £[OFFER]?"),
    ("Due to wear and tear, would you take £[OFFER]?", "Due to the small crack on the back, would you take £[OFFER]?",
     "Because it doesn't charge, would you take £[OFFER]?", "Would you take £[OFFER]?"),
])
def test_every_lead_keeps_reading_with_the_flaw_and_without_it(sentence, crack, no_charge, none):
    assert with_reason(sentence, "lower", CRACK) == crack
    assert with_reason(sentence, "lower", NO_CHARGE) == no_charge
    assert with_reason(sentence, "lower", None) == none


def test_a_reason_first_that_names_a_part_isnt_taken_for_the_generic_one():
    """'Given the condition of the screen, would you...' says which part: not swapped, not kept on a mint listing."""
    sentence = "Given the condition of the screen, would you take £[OFFER]?"
    assert with_reason(sentence, "lower", CRACK) is None
    assert with_reason(sentence, "lower", None) is None


# ── order-leads-asking-dont-mind-twice: at asking, your "don't mind the condition" takes the flaw ──

ASKER = [{"my_message": text, "asking_price": asking, "marketplace": "facebook", "listing_title": title}
         for text, asking, title in (
             ("Hi mate, is this still available? I can pay £200 cash, don't mind the condition. Can collect today.",
              "200", "iPhone 12"),
             ("Hi mate, is this still available? I can pay £120 cash, don't mind the condition. Can collect today.",
              "120", "AirPods Pro"),
             ("Hi mate, is this still available? Would you take £300 cash given the condition? Can collect today.",
              "380", "iPhone 14 Pro"),
             ("Hi mate, is this still available? Would you take £150 cash given the condition? Can collect today.",
              "200", "iPhone 13"))]


def test_your_dont_mind_at_asking_takes_the_flaw_not_a_second_sentence():
    """'...I can pay £200 cash, don't mind the condition. I don't mind the small crack on the back.'"""
    assert drafted(CRACKED, ASKER, reading("Small crack on the back"), kind="asking") == \
        ("ready", "Hi mate, is this still available? I can pay £200 cash, don't mind the small crack on the back. "
                  "Can collect today.")
    assert drafted(DEAD_PORT, ASKER, reading("Doesn't charge"), kind="asking") == \
        ("ready", "Hi mate, is this still available? I can pay £200 cash, don't mind that it doesn't charge. "
                  "Can collect today.")


def test_your_dont_mind_at_asking_goes_on_a_mint_listing():
    """As your 'given the condition' does under asking: not 'don't mind the condition' of an immaculate phone."""
    assert drafted(MINT, ASKER, reading(), kind="asking") == \
        ("ready", "Hi mate, is this still available? I can pay £200 cash. Can collect today.")


@pytest.mark.parametrize("sentence, crack, no_charge, none", [
    ("I'll pay full asking of £[OFFER], not fussed about the condition.",
     "I'll pay full asking of £[OFFER], not fussed about the small crack on the back.",
     "I'll pay full asking of £[OFFER], not fussed that it doesn't charge.", "I'll pay full asking of £[OFFER]."),
    ("I can pay £[OFFER] cash and I dont mind the marks.",
     "I can pay £[OFFER] cash and I dont mind the small crack on the back.",
     "I can pay £[OFFER] cash and I dont mind that it doesn't charge.", "I can pay £[OFFER] cash."),
    ("Don't mind the condition, I can pay £[OFFER] cash.", "Don't mind the small crack on the back, I can pay £[OFFER] cash.",
     "Don't mind that it doesn't charge, I can pay £[OFFER] cash.", "I can pay £[OFFER] cash."),
])
def test_each_dont_mind_takes_the_flaw_in_its_own_words(sentence, crack, no_charge, none):
    assert with_reason(sentence, "asking", CRACK) == crack
    assert with_reason(sentence, "asking", NO_CHARGE) == no_charge
    assert with_reason(sentence, "asking", None) == none


def test_a_dont_mind_about_something_else_gets_no_second_one():
    """'don't mind the scratches on the screen' isn't the generic words: no 'I don't mind ...' after it, and the
    AI words it; your 'don't mind collecting' isn't about the condition, so the flaw still goes after it."""
    assert with_reason("I can pay £[OFFER], don't mind the scratches on the screen.", "asking", CRACK) is None
    assert with_reason("I can pay £[OFFER], don't mind collecting.", "asking", CRACK) == \
        "I can pay £[OFFER], don't mind collecting. I don't mind the small crack on the back."


# ── v8-integration-5: your own flaw word ("given the scratches") is the generic reason too ──

SCRATCHED = listing("iPhone 13 128GB Midnight", "Few scratches on the screen. Works perfectly.")


def test_your_given_the_scratches_takes_the_listings_flaw_not_a_second_given():
    """'Hi, would you take £170 given the scratches, given a few scratches on the screen?'"""
    varied = [{"my_message": text, "asking_price": asking, "marketplace": "facebook", "listing_title": "iPhone 13 128GB"}
              for text, asking in (("Is this still available? Would you take £150 given the scratches?", "180"),
                                   ("Still for sale? Would you take £90 given the scratches?", "110"),
                                   ("Would you take £60 given the scratches?", "80"))]
    repeating = [{**m, "my_message": f"Hi, would you take £{p} given the scratches?"}
                 for m, p in zip(varied, ("150", "90", "60"))]
    expected = ("ready", "Hi, would you take £170 given a few scratches on the screen?")
    # varied never greets, so no "Hi," in front (round 2 red team, learning-ai-r4-6: this pinned the "Hi,")
    assert drafted(SCRATCHED, varied, reading("Few scratches on the screen")) == \
        ("ready", "Would you take £170 given a few scratches on the screen?")
    assert drafted(SCRATCHED, repeating, reading("Few scratches on the screen")) == expected
    assert drafted(SCRATCHED, repeating, None) == expected  # code reading the listing
    assert drafted(MINT, repeating, reading()) == ("ready", "Hi, would you take £170?")


@pytest.mark.parametrize("words", ["the scratches", "the light scratches", "a few marks", "the scratches and dents",
                                   "the dents", "the scuffs", "the chips", "the cracks", "the poor condition"])
def test_any_flaw_word_of_yours_takes_the_listings_flaw(words):
    sentence = f"Would you take £[OFFER] given {words}?"
    assert with_reason(sentence, "lower", CRACK) == "Would you take £[OFFER] given the small crack on the back?"
    assert with_reason(sentence, "lower", None) == "Would you take £[OFFER]?"


@pytest.mark.parametrize("sentence", ["Would you take £[OFFER] given the cracked screen?",
                                      "Would you take £[OFFER] given the scratches on the screen?"])
def test_a_reason_of_your_own_about_the_condition_never_gets_a_second_one(sentence):
    """The verifier: never ', given …' after an offer sentence that already gives a condition reason. These name the
    old listing's flaw in words code can't swap, so the AI words them, and they never stay on a mint listing."""
    assert with_reason(sentence, "lower", CRACK) is None
    assert with_reason(sentence, "lower", MARKS_AND_BATTERY) is None
    assert with_reason(sentence, "lower", None) is None


@pytest.mark.parametrize("sentence, crack, fact", [
    ("Would you take £[OFFER] as it's got a few marks?", "Would you take £[OFFER] given the small crack on the back?",
     "Would you take £[OFFER] as the back glass is cracked?"),
    ("Would you take £[OFFER] because it's damaged?", "Would you take £[OFFER] given the small crack on the back?",
     "Would you take £[OFFER] because the back glass is cracked?"),
    ("Would you take £[OFFER] since it's not in the best condition?",
     "Would you take £[OFFER] given the small crack on the back?",
     "Would you take £[OFFER] since the back glass is cracked?"),
    ("As there are a few scratches, would you take £[OFFER]?", "Given the small crack on the back, would you take £[OFFER]?",
     "As the back glass is cracked, would you take £[OFFER]?"),
])
def test_your_reason_said_as_a_clause_takes_the_listings_flaw_or_goes(sentence, crack, fact):
    """14 Oct hunt: "as it's got a few marks" was left to the AI, but since 14 Oct the template is the only writer, so
    that persona got no message on any listing. It's your reason for any listing, like "given the condition": the
    listing's flaw goes in its place (a fact after your own lead, a thing after "given"), and with none it goes."""
    assert with_reason(sentence, "lower", CRACK) == crack
    assert with_reason(sentence, "lower", {"about": "flaw", "says": ["Back glass cracked"],
                                           "clause": "the back glass is cracked"}) in (fact, crack)
    assert with_reason(sentence, "lower", None) == "Would you take £[OFFER]?"


def test_your_own_reason_on_a_mint_listing_is_left_to_the_ai_not_a_crash():
    status, message = drafted(MINT, habit("Would you take £X given the cracked screen?"), reading())
    assert (status, message) == ("needs you", None)


# ── controls: what already worked keeps working ──

@pytest.mark.parametrize("sentence, reasoned", [
    ("Would you take £[OFFER] cash?", "Would you take £[OFFER] cash, given the small crack on the back?"),
    # the reason goes with the price, before what's said after it (14 Oct hunt: "...can collect tonight, given...")
    ("Would you take £[OFFER] as I can collect today?",
     "Would you take £[OFFER], given the small crack on the back, as I can collect today?"),
    ("Would you take £[OFFER] with the box?", "Would you take £[OFFER] with the box, given the small crack on the back?"),
    ("Is £[OFFER] ok?", "Is £[OFFER] ok, given the small crack on the back?"),
    ("Would you take £[OFFER] given the condition? 😊", "Would you take £[OFFER] given the small crack on the back? 😊"),
])
def test_an_offer_with_no_reason_about_the_condition_still_gets_the_flaw(sentence, reasoned):
    assert with_reason(sentence, "lower", CRACK) == reasoned


@pytest.mark.parametrize("sentence", ["Would you take £[OFFER] cash?", "Would you take £[OFFER]...", "Would you take £[OFFER] x",
                                      "Would you take £[OFFER] as I can collect today?", "I can pay £[OFFER] cash."])
def test_with_no_flaw_a_sentence_without_your_reason_stays_as_typed(sentence):
    kind = "asking" if sentence.startswith("I can") else "lower"
    assert with_reason(sentence, kind, None) == sentence


def test_each_lead_still_reads_with_things_and_facts_together():
    """Pinned before (test_writer): never "because of that..." nor "with that..."."""
    assert with_reason("Would you take £[OFFER] because of the condition?", "lower", MARKS_AND_BATTERY) == \
        "Would you take £[OFFER] because of the light marks on the frame and because the battery health is 79%?"
    assert with_reason("Would you take £[OFFER] with the condition?", "lower", MARKS_AND_BATTERY) == \
        "Would you take £[OFFER] given the light marks on the frame and that the battery health is 79%?"
    assert with_reason("would you take £[OFFER] cos of the condition?", "lower", MARKS_AND_BATTERY) == \
        "would you take £[OFFER] cos of the light marks on the frame and cos the battery health is 79%?"
