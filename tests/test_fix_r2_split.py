"""The fourth red team (26 Sep), the split area's second round: what the first round's split and battery fixes broke,
and what they only partly fixed. A battery fitted "due to" something is a replaced one; "due" alone, "need" and "will
need" are said in the seller's words with "it" agreeing; the iPhone apostrophe (’) is read as '; two flaws sharing a
plural verb are one subject; "light on the back" is the flash; a part's state then "wont turn on" is two; praise after
"front and back" is never the reason; a reader's quote cut off mid-clause gets no wording; and two real seller lines the
first round newly worded wrong get none again. Each test is a finding's own listing with the message it should get; no
model is called (local=None, api=None) but where a FakeModel stands in for the AI writer."""
import re

import pytest

from fakes import FakeModel
from flip import reader
from flip.checks import BATTERY_REPLACED, clauses
from flip.message_drafter import draft_message
from flip.offers import check_condition_talk, check_reasons, condition_said
from flip.style import style_card
from flip.writer import flaw_phrase, flaw_words, reason_sentence

# "Hello, would you accept £X given the condition? Thanks", three times (the findings' "given the condition" style)
GIVEN = style_card([{"my_message": f"Hello, would you accept £{price} given the condition? Thanks", "asking_price": asking,
                     "marketplace": "facebook", "listing_title": title}
                    for price, asking, title in (("150", "200", "iPhone 12"), ("90", "120", "AirPods Pro"),
                                                 ("300", "380", "iPhone 14 Pro"))])
# AlertFlip's lower offer on Facebook, with no past messages: £170 on £200
SAYS = "Hi, would you take £170 cash for it? I'm offering that because {}. I can come and collect."


def drafted(description, title="iPhone 12 64GB", quotes=None, card=None, ai_says=None):
    """The draft for a Facebook listing at £200: code's own reading, or a reader's quotes as production takes them
    (reader.reading_from); ai_says is what a FakeModel AI writer gives as the reason."""
    text = f"{title}. {description}"
    reading = reader.reading_from({"flaws": quotes, "pickup": "", "no_offers": ""}, text, "flip-reader-5") if quotes \
        else reader.code_reading(text)
    listing = {"id": "x", "title": title, "description": description, "asking_price": "200", "marketplace": "facebook"}
    if ai_says:
        said = {"message": SAYS.format(ai_says)}
        return draft_message(listing, card=card, local=FakeModel("gemma3:4b", *[said] * 6),
                             api=FakeModel("claude-haiku-5-5", *[said] * 6), kind="lower", reading=reading, writer="ai")
    return draft_message(listing, card=card, local=None, api=None, kind="lower", reading=reading, writer="auto")


def sent(description, title="iPhone 12 64GB", quotes=None, card=None, ai_says=None):
    """The message that goes out (a ready draft's), failing with the draft's problems if none does."""
    result = drafted(description, title, quotes, card, ai_says)
    assert result["status"] == "ready", result["attempts"]
    return result["answer"]["message"]


# ── split-r4-battery-due-to: "due to" says why a battery was fitted; a need, then one fitted, is a replaced one ───────

@pytest.mark.parametrize("description, quotes, reason", [
    ("Had a new battery due to the old one swelling. Small scratch on the screen", None,
     "of the small scratch on the screen and because the battery has been replaced"),
    ("Had a new battery due to the old one swelling. Small scratch on the screen",
     ["Had a new battery due to the old one swelling", "Small scratch on the screen"],
     "of the small scratch on the screen and because the battery has been replaced"),
    ("Brand new battery due to old one degrading, unlocked", ["Brand new battery due to old one degrading"],
     "the battery has been replaced"),
    ("Was due a new battery so had one fitted at Apple last month. Unlocked, works perfectly", None,
     "the battery has been replaced"),
    ("Needed new battery so got it done in a shop. Works perfect", None, "the battery has been replaced"),
    ("New battery fitted due to low health. Works perfect", None, "the battery has been replaced"),  # control
    ("new battery due to old one at 79%. few marks on frame", None,  # the verifier's
     "of a few marks on the frame and because the battery has been replaced"),
])
def test_a_battery_fitted_due_to_something_is_replaced(description, quotes, reason):
    assert sent(description, quotes=quotes) == SAYS.format(reason)


def test_a_battery_fitted_due_to_something_in_your_style_and_by_the_ai():
    assert sent("Had a new battery due to the old one swelling. Small scratch on the screen", card=GIVEN) == \
        "Hello, would you accept £170 given the small scratch on the screen and that the battery has been replaced? Thanks"
    said = "the battery has been replaced and there's a small scratch on the screen"
    assert sent("Had a battery replacement due to low battery health. Small scratch on the screen. Unlocked",
                ai_says=said) == SAYS.format(said)  # a correct AI message passes the checks again


@pytest.mark.parametrize("words", [
    "Had a new battery due to the old one swelling", "Brand new battery due to old one degrading",
    "Was due a new battery so had one fitted", "Needed new battery so got it done in a shop",
    "a battery replacement due to low battery health", "New battery fitted due to low health",
    "Battery was dying so had it replaced"])
def test_the_checks_read_a_battery_fitted_as_replaced(words):
    assert "issue: battery replaced" in condition_said(words, typos=True)
    assert flaw_phrase(words) == "that the battery has been replaced"


def test_what_isnt_a_battery_fitted_is_still_not_one():
    replaced = re.compile(rf"\b(?:{BATTERY_REPLACED})\b", re.IGNORECASE)
    for words in ("Due a new battery", "Battery replacement due", "Due for a new battery soon", "Needs a new battery",
                  "Never had a replacement battery", "battery is at 78% so got it cheap", "Was due a new battery"):
        assert not replaced.search(words), words


# ── split-r4-due-wording-refused: a "due" that isn't "due to" doesn't start a clause of the checks' ───────────────────

@pytest.mark.parametrize("description, reason", [
    ("Due a new battery. Otherwise works fine, unlocked", "it's due a new battery"),
    ("Battery replacement due. Otherwise works fine, unlocked", "a battery replacement is due"),
    ("Due for a new battery soon, works fine", "it's due for a new battery soon"),
    ("Needs a new battery. Otherwise works fine, unlocked", "it needs a new battery"),  # control
])
def test_a_battery_that_is_due_is_said(description, reason):
    assert sent(description, "iPhone 11 64GB") == SAYS.format(reason)


def test_an_ai_saying_a_battery_is_due_passes_and_due_to_still_starts_a_reason():
    assert sent("Due a new battery. Otherwise works fine, unlocked", "iPhone 11 64GB", ai_says="it's due a new battery") \
        == SAYS.format("it's due a new battery")
    assert [c for c, _ in clauses("I'm offering that because it's due a new battery.")] == \
        ["I'm offering that ", " it's due a new battery."]
    assert [c for c, _ in clauses("Would you take £170 due to the crack?")] == ["Would you take £170 ", " to the crack?"]


# ── split-r4-need-wording, cause-done-split-8: a battery it needs, said with "it" agreeing, never as replaced ─────────

@pytest.mark.parametrize("description, reason", [
    ("Works perfect, it'll need a new battery soon though. Unlocked", "it'll need a new battery soon"),
    ("Good condition, need new battery. Collection only", "it needs new battery"),  # the seller's words, "it" agreeing
    ("Works great. Will need a battery replacement soon", "it will need a battery replacement soon"),
    ("May need a battery replacement soon. No cracks", "it may need a battery replacement soon"),
    ("Would need a battery change at some point", "it would need a battery change at some point"),
    ("Need a new battery. Works fine", "it needs a new battery"),  # "needs" is the listing's "need" (check_reasons)
    ("Battery health is 75%, so it may need a battery replacement",  # the verifier's real lines
     "the battery health is 75% and it may need a battery replacement"),
    ("It powers on, resets, and functions normally, but will eventually need a battery replacement.",
     "it will eventually need a battery replacement"),
    ("Requires battery replacement - Sold as Spares/Repair",
     "it requires battery replacement and it's sold as spares/repair"),
    ("- please take note that it will definitely need a battery replacement",  # the reader's quote cuts "it will"
     "it definitely needs a battery replacement"),
])
def test_a_battery_it_needs_is_said_as_needed(description, reason):
    assert sent(description, "iPhone 11 64GB") == SAYS.format(reason)


def test_a_battery_it_needs_in_your_style():
    assert sent("Fully working. Will probably need a new battery soon", "iPhone XR 128GB", card=GIVEN) == \
        "Hello, would you accept £170 given that it will probably need a new battery soon? Thanks"


@pytest.mark.parametrize("quote, words", [
    ("need new battery", "that it needs new battery"),
    ("it'll need a new battery soon", "that it'll need a new battery soon"),
    ("itll need a new battery soon", "that it'll need a new battery soon"),
    ("Will probably need a new battery soon", "that it will probably need a new battery soon"),
    ("will soon need a new battery", "that it will soon need a new battery"),
    ("will likely need a replacement battery", "that it will likely need a replacement battery"),
    ("will most likely need a battery replacement at some point",
     "that it will most likely need a battery replacement at some point"),
    ("so it may need a battery replacement", "that it may need a battery replacement"),
    ("Could need a new battery", "that it could need a new battery"),
    ("Requires battery replacement", "that it requires battery replacement"),
    ("Only need screen replacement and battery replacement", "that it needs screen replacement and battery replacement"),
    ("Have a few scratches due to use", "that it has a few scratches"),
    # what the first round got right stays right
    ("Needs a new battery", "that it needs a new battery"),
    ("Could do with a new battery", "that it could do with a new battery"),
    ("In need of a new battery", "that it's in need of a new battery"), ("Due a new battery", "that it's due a new battery"),
    ("Battery replacement needed", "that a battery replacement is needed"),
    ("New battery needed", "that a new battery is needed"),
    ("Battery needs replacing", "that the battery needs replacing"),
    ("Battery changed 4 months ago", "that the battery has been replaced"),
])
def test_a_battery_need_is_said_in_the_sellers_words(quote, words):
    assert flaw_words([quote]) == words


@pytest.mark.parametrize("quote", [
    "Just needs screen or battery replaced as when put on charge it just flashes the apple symbol and dosent turn on",
    "iphone 6 but it needs reparing and a battery replacement and it's not unlocked",
    "Only need screen replacement and battery replacement",
    "a battery replacement may be worth considering",
    "Please note: Battery health is 73%, so battery life may be reduced and a battery replacement may be worth considering.",
    "A battery replacement would bring it back to full capacity",
    "so a future battery replacement may be desired",
])
def test_a_battery_still_needed_is_never_said_replaced(quote):
    """cause-done-split-8's verifier: a need before the battery's words, or a "may" after them, isn't one fitted."""
    assert "has been replaced" not in (reason_sentence({"about": "flaw", "says": [quote]}) or "")


def test_the_writer_never_says_the_will():
    for quote in ("Will need a battery replacement soon", "May need a battery replacement soon", "will need replacing",
                  "Smashed screen but will need replacing", "may have slight scratches", "There may be some minor signs "
                  "of use", "sim don't work and motherboard needs to be", "so a future battery replacement may be desired"):
        said = flaw_words([quote]) or ""
        assert not re.search(r"\bthe (?:will|would|may|might|could|should|so|there|don't)\b", said), quote


def test_the_checks_read_need_and_needs_as_one_word():
    assert check_reasons("Hi, would you take £170? I'm offering that because it needs a new battery.",
                         "iPhone 11. Need a new battery. Works fine") == []
    assert check_reasons("Hi, would you take £170? I'm offering that because the hinge is stiff.",
                         "iPhone 11. Need a new battery. Works fine") != []  # words it doesn't use still aren't


# ── split-r4-curly-apostrophe: the iPhone keyboard's ’ is read as ' ───────────────────────────────────────────────────

@pytest.mark.parametrize("title, description, quotes, reason", [
    ("iPhone 12", "Camera doesn’t work and has slight crack on back. Spares or repairs", None,
     "the camera doesn't work and has slight crack on the back and it's sold as spares or repairs"),
    ("iPhone 11", "Face ID doesn’t work and back is cracked. Battery 81%", None,
     "the Face ID doesn't work and the back is cracked and the battery health is 81%"),
    ("iPhone 12 Pro 128gb spares", "won’t turn on screen cracked, sold as seen", None,
     "it's sold as spares and it won't turn on and the screen is cracked"),
    ("iPhone XR", "Water damaged and doesn’t turn on. Spares or repairs", ["Water damaged and doesn’t turn on"],
     "it's water damaged and doesn't turn on and it's sold as spares or repairs"),
])
def test_the_iphone_apostrophe_reads_as_the_straight_one(title, description, quotes, reason):
    assert sent(description, title, quotes) == SAYS.format(reason)
    assert sent(description.replace("’", "'"), title, quotes and [q.replace("’", "'") for q in quotes]) == \
        SAYS.format(reason)  # the same words typed with ' (the finding's control)


@pytest.mark.parametrize("quote, words", [
    ("It’s got a small crack on the back", "that it's got a small crack on the back"),
    ("Doesn’t charge", "that it doesn't charge"),
    ("selfie/front camera doesn’t work and has slight crack on back glass",
     "that the selfie/front camera doesn't work and has slight crack on the back glass"),
])
def test_a_quote_with_the_iphone_apostrophe_is_worded(quote, words):
    assert flaw_phrase(quote) == words if " and " not in quote else flaw_words([quote]) == words


# ── split-r4-compound-subject: two flaws sharing a plural verb are one subject ────────────────────────────────────────

@pytest.mark.parametrize("title, description, quotes, reason", [
    ("iPhone 12 64GB", "Small scratch and dent are on the back. Unlocked, works perfect", None,
     "the small scratch and dent are on the back"),
    ("iPhone 13 128GB", "Crack and scratches are on the back, screen is perfect. Battery 89%", None,
     "the crack and scratches are on the back"),
    ("iPhone 13", "Scratches on the screen and back are light, unlocked", ["Scratches on the screen and back are light"],
     "the scratches on the screen and back are light"),
    ("iPhone 14", "Scuffs on the corners and edges are minor, 128gb", ["Scuffs on the corners and edges are minor"],
     "the scuffs on the corners and edges are minor"),
])
def test_two_flaws_with_one_verb_are_one_subject(title, description, quotes, reason):
    assert sent(description, title, quotes) == SAYS.format(reason)


def test_two_flaws_with_one_verb_in_your_style():
    assert sent("Dent and scuff are on the corner, otherwise mint", "Samsung Galaxy S22",
                ["Dent and scuff are on the corner"], card=GIVEN) == \
        "Hello, would you accept £170 given that the dent and scuff are on the corner? Thanks"


@pytest.mark.parametrize("quote, words", [
    ("Crack and chip are both on the back glass", "that the crack and chip are both on the back glass"),
    ("a few scratches and a dent are on the frame", "that a few scratches and a dent are on the frame"),
    ("Small chip and scratch are visible on the screen", "that the small chip and scratch are visible on the screen"),
    ("Only marks and scratches are on the edges and corners", "that the marks and scratches are on the edges and corners"),
    # a clause of its own after the "and" is still two (the verifier's controls)
    ("Back cracked and both cameras are scratched", "that the back is cracked and that both cameras are scratched"),
    ("Small crack on the screen and both lenses are scratched",
     "the small crack on the screen and that both lenses are scratched"),
    ("Scratches on the frame and the screen has a chip", "the scratches on the frame and that the screen has a chip"),
    ("Back cracked and cameras are scratched", "that the back is cracked and that the cameras are scratched"),
    ("small dent at the bottom and there are some small scratches around the camera",
     "the small dent at the bottom and that there are some small scratches around the camera"),
    ("Screen and back are cracked", "that the screen and back are cracked"),
])
def test_one_subject_or_two_clauses(quote, words):
    assert flaw_words([quote]) == words


# ── split-r4-part-verb: a part never ends on its own verb ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("title, description, quotes, reason", [
    ("iPhone 13 Pro", "Back cracked and both cameras are scratched. Unlocked", None,
     "the back is cracked and both cameras are scratched"),
    ("iPhone 14 Pro", "Small crack on the screen and both lenses are scratched",
     ["Small crack on the screen and both lenses are scratched"],
     "of the small crack on the screen and because both lenses are scratched"),
    ("iPhone 12 spares", "Won't turn on battery might be dead. Spares or repairs", ["Won't turn on battery might be dead"],
     "it won't turn on and the battery might be dead and it's sold as spares"),
])
def test_a_part_and_its_verb_are_said_once(title, description, quotes, reason):
    assert sent(description, title, quotes) == SAYS.format(reason)


@pytest.mark.parametrize("quote, words", [
    ("Both cameras are scratched", "that both cameras are scratched"),
    ("all the buttons are stiff", "that all the buttons are stiff"),
    ("mic might be faulty", "that the mic might be faulty"),
    ("screen cracked and battery might be faulty", "that the screen is cracked and that the battery might be faulty"),
    ("doesnt charge and charging port may be broken", "that it doesnt charge and that the charging port may be broken"),
    ("both lenses scratched", "that both lenses are scratched"),  # no verb: "are" as before
    ("Island cracked", "that the island is cracked"),  # "is" inside a word isn't one
])
def test_a_part_never_ends_on_a_verb(quote, words):
    assert flaw_words([quote]) == words


# ── split-r4-light-on: "light on the back" is the flash, not "turns on" ───────────────────────────────────────────────

@pytest.mark.parametrize("title, description, quotes, card, said", [
    ("iPhone 12", "The light on the back camera doesn't work. Everything else fine", None, None,
     SAYS.format("the light on the back camera doesn't work")),
    ("iPhone 11 64GB", "flash light on back not working, rest is fine", ["flash light on back not working"], GIVEN,
     "Hello, would you accept £170 given that the flash light on the back is not working? Thanks"),
    ("iPhone XR", "Torch light on the back doesn't turn on. Battery 84%", None, None,
     SAYS.format("the torch light on the back doesn't turn on and the battery health is 84%")),
])
def test_a_light_on_the_back_is_a_part(title, description, quotes, card, said):
    assert sent(description, title, quotes, card) == said


def test_a_light_on_the_back_and_the_run_ons_after_turn_on():
    assert flaw_phrase("flash light on back doesn't work") == "that the flash light on the back doesn't work"
    for quote, words in (("wont turn on screen cracked", "that it wont turn on and that the screen is cracked"),
                         ("Turns on battery drains fast", "that the battery drains fast")):
        assert flaw_words([quote]) == words, quote


# ── split-r4-reverse-run-on, the-word-6: a part's state, then what it won't do, is two ────────────────────────────────

@pytest.mark.parametrize("title, description, quotes, card, said", [
    ("iPhone 12 Pro 128gb spares", "Screen cracked wont turn on, sold as seen", ["Screen cracked wont turn on"], None,
     SAYS.format("the screen is cracked and it wont turn on and it's sold as spares")),
    ("iPhone XR for parts", "Back glass smashed won't switch on", None, GIVEN,
     "Hello, would you accept £170 given that it's sold for parts and that the back glass is smashed and that it won't "
     "switch on? Thanks"),
    ("iPhone 11 spares or repairs", "screen smashed doesnt turn on. no returns", None, None,
     SAYS.format("it's sold as spares or repairs and the screen is smashed and it doesnt turn on")),
])
def test_a_state_then_what_it_wont_do_is_two(title, description, quotes, card, said):
    assert sent(description, title, quotes, card) == said


@pytest.mark.parametrize("quote, words", [
    ("screen cracked wont charge", "that the screen is cracked and that it wont charge"),
    ("Screen cracked not working", "that the screen is cracked and that it's not working"),
    ("screen cracked and wont turn on", "that the screen is cracked and that it wont turn on"),  # as before
    ("Screen cracked but works fine", "that the screen is cracked"),
    ("Screen cracked doesn't affect use", "that the screen is cracked"),
])
def test_a_state_then_a_fault_or_not(quote, words):
    assert flaw_words([quote]) == words


# ── split-r4-front-back-praise: praise after "front and back" is never the reason ─────────────────────────────────────

def test_praise_after_front_and_back_is_left_out():
    assert sent("Small crack on the front and back is fine. Battery 88%", "iPhone 13 128GB",
                ["Small crack on the front and back is fine"]) == SAYS.format("of the small crack on the front")
    assert sent("Few scratches on the front and back is perfect", "iPhone 12 64GB",
                ["Few scratches on the front and back is perfect"], GIVEN) == \
        "Hello, would you accept £170 given a few scratches on the front? Thanks"
    assert flaw_words(["small scratches on the side front and back is flawless"]) == "the small scratches on the side front"
    assert flaw_words(["Crack on the screen and back is mint"]) == "the crack on the screen"  # the fixed control


@pytest.mark.parametrize("quote, words", [  # both sides damaged stay one (the verifier's caution)
    ("Front and back is cracked", "that the front and back is cracked"),
    ("Scratches front and back", "the scratches front and back"),
    ("screen front and back is broken", "that the screen front and back is broken"),
    ("Small crack on the back and front camera flickers", "the small crack on the back and that the front camera flickers"),
])
def test_both_sides_damaged_stay_one(quote, words):
    assert flaw_words([quote]) == words


def test_a_quote_cut_off_in_a_second_clause_gets_no_wording():
    """Code's reading cuts "...front and back is fine" to "...front and back is": what the back is isn't known, so the AI
    words it (as for "Cracked the back glass and the lens is"), never "because of the small crack on the front and back"."""
    result = drafted("Small crack on the front and back is fine. Battery 88%", "iPhone 13 128GB")
    assert result["point"] == ["Small crack on the front and back is"]
    assert result["status"] == "needs you" and "front and back" not in str(result["answer"])
    for quote in ("speakers are a bit quiet and screen is", "small dent at the bottom and there are",
                  "Cracked the back glass and the lens is"):
        assert flaw_words([quote]) is None, quote
    # ...but one cut where the same thing goes on is said without it
    for quote, words in (("Has minor scuffs and scratches and is", "that it has minor scuffs and scratches"),
                         ("small crack on the back glass and has", "the small crack on the back glass"),
                         ("battery has been changed recently and it is", "that the battery has been replaced")):
        assert flaw_words([quote]) == words, quote


# ── two real seller lines the first round newly worded wrong (labelled flaw lines f019, f127) ─────────────────────────

def test_real_lines_the_first_round_broke_get_no_wording():
    # f019: the misspelt model as the subject, the frame and the battery dropped
    assert reason_sentence({"about": "flaw", "says": [
        "Ipjone 15 pro grade c has some scratches on the screen and on the frame 93% battery health, grab a "
        "bargain."]}) is None
    # f127: praise kept, shouting, garbled
    assert reason_sentence({"about": "flaw", "says": [
        ">Works perfectly”EXCEPT FOR FACE ID ISSUE & SMALL SCREEN BLACK DOT,housing have minor scratches as shown on "
        "photos"]}) is None
    assert flaw_words(["Cracked back and battery 88%"]) == "the cracked back"  # a good battery on its own is no reason
    assert flaw_words(['an "Unknown Part" message in Settings']) == 'an "Unknown Part" message in Settings'  # quotes read


def test_praise_or_a_verb_is_never_the_thing_said():
    for quote in ("Phone is in good condition but has a scratch on top middle.",
                  "The screen is in good condition but has a deep mark on it and some scratches.",
                  "It's got a cracked back and presents quite a few scratches on the screen and frame, with a small dent "
                  "at the top of the frame.", "shows some light scratches", "a new battery would help"):
        assert flaw_words([quote]) is None, quote


# ── "spares and repairs" is one thing ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("quote, words", [
    ("Spares and repairs as it won't turn on", "that it's sold as spares and repairs"),
    ("spares & repairs as it doesn't charge", "that it's sold as spares & repairs"),
    ("Sold for spares and repairs and the screen is cracked",
     "that it's sold as spares and repairs and that the screen is cracked"),
])
def test_spares_and_repairs_is_one_thing(quote, words):
    assert flaw_words([quote]) == words


def test_a_message_naming_a_battery_needed_passes_the_checks():
    point = {"about": "flaw", "says": ["Would need a battery change at some point"]}
    assert check_condition_talk("Hi, would you take £170? I'm offering that because it would need a battery change at "
                                "some point.", "iPhone 11. Would need a battery change at some point", point, True) == []
