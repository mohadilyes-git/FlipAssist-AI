"""The third red team (26 Sep), one quote with more than one thing in it: a half that isn't a fault (praise, a denial,
a selling point, the seller's story) is never said as a reason; the "and"s are tried from the last one back and never
inside "wear and tear"; a story or deed opener, a pronoun subject and a run-on after "turn on" each get the wording
they need; and a battery the phone needs is never said as one it's had. Each test is a finding's own listing, with the
message it should get; no model is called (local=None, api=None), so a "ready" draft is the template's own."""
import re

import pytest

from flip.checks import BATTERY_REPLACED
from flip.message_drafter import draft_message
from flip.offers import check_condition_talk, condition_said
from flip.style import style_card
from flip.writer import flaw_phrase, flaw_words, reason_sentence, split_phrases

# "Hi mate, would you take £X given the condition? Can collect today.", three times (the findings' "given" style)
GIVEN = style_card([{"my_message": f"Hi mate, would you take £{price} given the condition? Can collect today.",
                     "asking_price": asking, "marketplace": "facebook", "listing_title": title}
                    for price, asking, title in (("150", "200", "iPhone 12"), ("90", "120", "AirPods Pro"),
                                                 ("300", "380", "iPhone 14 Pro"))])
# "Hello, would you accept £X given the condition? Thanks" (the-word-6's "given" style)
HELLO = style_card([{"my_message": f"Hello, would you accept £{price} given the condition? Thanks",
                     "asking_price": asking} for price, asking in (("150", "200"), ("90", "120"), ("300", "380"))])
# AlertFlip's lower offer on Facebook, with no past messages: £170 on £200
SAYS = "Hi, would you take £170 cash for it? I'm offering that because {}. I can come and collect."


def draft(description, title="iPhone 13", flaws=None, card=None, kind="lower", asking="200"):
    """The message the template sends for a Facebook listing: code's own reading when flaws is None."""
    listing = {"id": "x", "title": title, "description": description, "asking_price": asking, "marketplace": "facebook"}
    reading = None if flaws is None else {"flaws": flaws, "pickup": "", "no_offers": "", "read_by": "flip-reader-5"}
    result = draft_message(listing, card=card, local=None, api=None, kind=kind, reading=reading)
    assert (result["status"], result["writer"]) == ("ready", "template"), result["attempts"]
    return result["answer"]["message"]


# ── cause-done-split-1: a half that denies or praises is never the reason ──────────────────────────────────────────

@pytest.mark.parametrize("title, description, reason", [
    ("iPhone 14 128GB", "Cracked the back and no scratches on the screen. Battery 88%", "the back is cracked"),
    ("iPhone 12 64GB", "Dented the corner and no other damage. Always had a case", "the corner is dented"),
    ("iPhone 12", "Dented the frame and not iCloud locked, all working", "the frame is dented"),
])
def test_a_denied_half_is_left_out(title, description, reason):
    assert draft(description, title) == SAYS.format(reason)


def test_a_denied_half_is_left_out_at_asking_and_from_a_readers_quote():
    assert draft("Cracked the back and no scratches on the screen. Battery 88%", "iPhone 14 128GB", card=GIVEN,
                 kind="asking") == "Hi mate, I can pay £200. I don't mind that the back is cracked. Can collect today."
    quote = "Few light scratches on the back glass and the screen is perfect with no marks"
    assert draft(f"{quote} as always had a protector", "iPhone 13 Pro", flaws=[quote]) == \
        SAYS.format("of a few light scratches on the back glass")


@pytest.mark.parametrize("quote, words", [
    ("Cracked the back and no scratches on the screen", "that the back is cracked"),
    ("Dented the frame and not iCloud locked", "that the frame is dented"),
    ("Scratched the screen and no other marks", "that the screen is scratched"),
    ("Cracked the back and zero scratches on screen", "that the back is cracked"),  # "zero" reads as scratches
    ("Small scratch on the back and never had a replacement battery", "the small scratch on the back"),
    ("Cracked the back glass and no issues with face id", "that the back glass is cracked"),
])
def test_a_denial_is_never_said(quote, words):
    assert flaw_words([quote]) == words


@pytest.mark.parametrize("half, phrase", [  # the halves that are flaws still are (the finder's own list)
    ("The back is cracked", "that the back is cracked"),
    ("it has bent the frame at the top", "that the frame is bent at the top"),
    ("eSIM only", "that it's eSIM only"), ("Untested", "that it's untested"),
    ("Battery replaced", "that the battery has been replaced"),
])
def test_a_half_that_is_a_flaw_is_still_said(half, phrase):
    assert split_phrases(f"{half} and no scratches on the screen") == [phrase]


# ── cause-done-split-2, -8 and order-leads-split-needs-battery: a battery it needs, not one it's had ──────────────

def test_a_needed_battery_is_said_as_needed():
    assert draft("Needs a new battery. Otherwise works fine, unlocked", "iPhone 11 64GB") == \
        SAYS.format("it needs a new battery")
    assert draft("Will need a new battery soon", "iPhone XR", card=GIVEN) == \
        "Hi mate, would you take £170 given that it will need a new battery soon? Can collect today."
    assert draft("Battery replacement needed and small crack on screen. Collection only", "iPhone 11 128GB") == \
        SAYS.format("of the small crack on the screen and because a battery replacement is needed")
    # the reader's quotes kept apart: both said (code alone cuts its quote before the crack, and says the need)
    assert draft("Needs a new battery and has a small crack on the back. Unlocked, fully wkg", "iPhone 12 64GB",
                 flaws=["Needs a new battery", "has a small crack on the back"]) == \
        SAYS.format("it needs a new battery and it has a small crack on the back")
    assert draft("Needs a new battery and has a small crack on the back. Unlocked, fully wkg", "iPhone 12 64GB") == \
        SAYS.format("it needs a new battery")


def test_a_needed_battery_next_to_another_flaw_is_said_as_needed():
    assert draft("Back cracked and needs a new battery. Still works fine", "iPhone 12 64GB") == \
        SAYS.format("the back is cracked and it needs a new battery")
    quote = "Needs a new battery and the screen has a small crack"
    assert draft(f"{quote}. Otherwise works fine", "iPhone 11 64GB", flaws=[quote], card=GIVEN) == \
        "Hi mate, would you take £170 given that it needs a new battery and that the screen has a small crack? " \
        "Can collect today."
    assert draft("Needs a new battery, otherwise works fine", "iPhone 11 64GB", flaws=["Needs a new battery"]) == \
        SAYS.format("it needs a new battery")


@pytest.mark.parametrize("quote, phrase", [
    ("Needs a new battery", "that it needs a new battery"),
    ("Will need a new battery soon", "that it will need a new battery soon"),
    ("Could do with a new battery", "that it could do with a new battery"),
    ("In need of a new battery", "that it's in need of a new battery"),
    ("Battery replacement needed", "that a battery replacement is needed"),
    ("Battery needs replacing", "that the battery needs replacing"),  # worded right before: unchanged
    ("Battery changed 4 months ago", "that the battery has been replaced"),  # and a replaced one still is
])
def test_a_battery_is_said_as_the_seller_says_it(quote, phrase):
    assert flaw_phrase(quote) == phrase


def test_a_needed_battery_reads_as_weak_not_replaced():
    replaced = re.compile(rf"\b(?:{BATTERY_REPLACED})\b", re.IGNORECASE)
    for needed in ("Needs a new battery", "needs new battery", "Could do with a new battery", "Due a new battery",
                   "Battery replacement needed", "New battery needed", "needs a battery replacement",
                   "Never had a replacement battery"):
        assert not replaced.search(needed), needed
        assert "issue: battery replaced" not in condition_said(needed, typos=True), needed
    for needed in ("Needs a new battery", "Battery replacement needed", "Due a new battery", "Requires a new battery"):
        assert "issue: battery weak" in condition_said(needed, typos=True), needed  # still a flaw, of the right kind
    for had in ("Battery changed 4 months ago", "New battery", "Replacement battery from Apple", "Battery is brand new",
                "just had a new battery fitted", "replaced with a new battery", "battery recently replaced"):
        assert replaced.search(had) and "issue: battery replaced" in condition_said(had, typos=True), had


def test_a_message_that_calls_a_needed_battery_replaced_is_caught():
    """The checks read the listing as the writer does now, so an AI that says "replaced" is stopped (finding 8)."""
    point = {"about": "flaw", "says": ["Needs a new battery"]}
    listing = "iPhone 11 64GB. Needs a new battery. Otherwise works fine, unlocked"
    assert any("issue: battery replaced" in p for p in check_condition_talk(
        "Hi, would you take £170? I'm offering that because the battery has been replaced.", listing, point, True))
    assert check_condition_talk("Hi, would you take £170? I'm offering that because it needs a new battery.", listing,
                                point, True) == []
    could = {"about": "flaw", "says": ["Could do with a new battery"]}  # "do with" doesn't start a clause of its own
    assert check_condition_talk("Hi, would you take £170? I'm offering that because it could do with a new battery.",
                                "iPhone XR. Could do with a new battery", could, True) == []


# ── cause-done-split-5: a half that starts with "it" ──────────────────────────────────────────────────────────────

def test_a_half_that_starts_with_it_is_said_with_it():
    quote = "Crack across the top of the screen and it flickers when you scroll fast"
    assert draft(f"iPhone 13 Pro 256GB. {quote}. Otherwise fine", "iPhone 13 Pro", flaws=[quote]) == \
        SAYS.format("of the crack across the top of the screen and because it flickers when you scroll fast")
    quote = "Small crack in the corner of the screen and it sometimes freezes on the lock screen"
    assert draft(quote, flaws=[quote], card=GIVEN) == "Hi mate, would you take £170 given the small crack in the " \
        "corner of the screen and that it sometimes freezes on the lock screen? Can collect today."


@pytest.mark.parametrize("quote, phrase", [
    ("it flickers when you scroll fast", "that it flickers when you scroll fast"),
    ("it keeps restarting", "that it keeps restarting"),
    ("they crackle at high volume", "that they crackle at high volume"),
])
def test_a_pronoun_keeps_its_verb(quote, phrase):
    assert flaw_phrase(quote) == phrase


def test_a_wording_never_puts_the_before_a_pronoun_or_a_deed():
    for quote in ("Crack on the screen and it keeps restarting", "Dent on the bottom corner of the frame and it doesn't "
                  "always charge first time", "it glitches", "dropped it and cracked the back", "Bent the frame and no "
                  "dead pixels", "Fell and cracked the back", "Back cracked and been repaired"):
        said = flaw_words([quote]) or ""
        assert not re.search(r"\bthe (?:it|they|this|which|dropped it|bent the|fell|been)\b", said), quote


# ── cause-done-split-6, order-leads-split-list, -wear-and-tear: from the last "and", never inside a pair ─────────

def test_the_last_and_is_tried_first():
    quote = "Scratches and scuffs all around the frame and the screen has a small chip"
    assert draft(quote, flaws=[quote], card=GIVEN) == "Hi mate, would you take £170 given the scratches and scuffs all " \
        "around the frame and that the screen has a small chip? Can collect today."
    quote = "Light scratches on screen and frame and back glass has a hairline crack"
    assert draft(f"{quote}. Fully working", "iPhone 14 Pro 128GB", flaws=[quote]) == SAYS.format(
        "of the light scratches on the screen and frame and because the back glass has a hairline crack")
    quote = "Some scratches on the back and sides and the screen has a small chip"
    assert draft(quote, "iPhone 12 128GB", flaws=[quote], card=GIVEN) == "Hi mate, would you take £170 given some " \
        "scratches on the back and sides and that the screen has a small chip? Can collect today."
    assert flaw_words(["Few marks on the screen and frame and the back camera lens is cracked"]) == \
        "a few marks on the screen and frame and that the back camera lens is cracked"
    assert flaw_words(["Scuffs and light scratches on the back glass and the camera lens is cracked"]) == \
        "the scuffs and light scratches on the back glass and that the camera lens is cracked"


def test_wear_and_tear_is_never_split():
    quote = "Signs of wear and tear on the frame and a hairline crack on the back glass"
    assert draft(f"{quote}. 128GB", "iPhone 12", flaws=[quote]) == \
        SAYS.format("of the signs of wear and tear on the frame and a hairline crack on the back glass")
    quote = "Some wear and tear on the frame and a small crack on the back"
    assert draft(f"{quote}. Unlocked", "Samsung Galaxy S22 Ultra", flaws=[quote]) == \
        SAYS.format("of some wear and tear on the frame and a small crack on the back")
    quote = "Lots of wear and tear on the case and the hinge is a bit loose now"
    assert draft(quote, "MacBook Pro 13 2019", flaws=[quote]) == \
        SAYS.format("of lots of wear and tear on the case and because the hinge is a bit loose now")
    assert flaw_words(["Wear and tear on the corners and a crack on the camera lens"]) == \
        "the wear and tear on the corners and a crack on the camera lens"
    assert flaw_words(["Some wear & tear on the frame and a small crack on the back"]) == \
        "some wear & tear on the frame and a small crack on the back"


@pytest.mark.parametrize("quote, words", [  # two sides are one thing, unless the second names its own part
    ("Small crack on the back and front camera flickers",
     "the small crack on the back and that the front camera flickers"),
    ("Small crack on the top and bottom speaker crackles",
     "the small crack on the top and that the bottom speaker crackles"),
    ("Scratches on the top and bottom", "the scratches on the top and bottom"),
    ("Front and back cracked", "that the front and back are cracked"),
    # a fault word only the writer knows is still a fault, and still denied after a "not" ("front" isn't "n't")
    ("it doesnt charge and front camera is blurry", "that it doesnt charge and that the front camera is blurry"),
    ("Dent on the corner and screen no good", "the dent on the corner and that the screen is no good"),
    ("Small crack and not slow at all", "the small crack"),
])
def test_a_pair_or_a_fault_word_is_read_as_meant(quote, words):
    assert flaw_words([quote]) == words


@pytest.mark.parametrize("quote, words", [  # what was right stays right
    ("Cracked and scratched", "that it's cracked and scratched"),
    ("Scratches and scuffs on the frame", "the scratches and scuffs on the frame"),
    ("Light scratches on screen and frame", "the light scratches on the screen and frame"),
    ("General wear and tear and a small crack on the back", "the general wear and tear and a small crack on the back"),
    ("Scratches on the screen and a dent on the corner", "the scratches on the screen and a dent on the corner"),
    ("Doesn't charge and won't turn on", "that it doesn't charge and won't turn on"),
    ("Screen and back are cracked", "that the screen and back are cracked"),
    ("Screen and back cracked", "that the screen and back are cracked"),  # two parts: "are" (was "is")
    ("Volume and power buttons stiff", "that the volume and power buttons are stiff"),
    ("Turns on and off by itself", "that it turns on and off by itself"),
    ("Black and white lines on the screen", "the black and white lines on the screen"),
    ("Scratches on front and back", "the scratches on the front and back"),
    ("The back is cracked and it has bent the frame at the top",
     "that the back is cracked and that the frame is bent at the top"),
    ("Battery replaced and back cracked", "that the battery has been replaced and that the back is cracked"),
    ("I dropped it and cracked the back", None),  # the seller's own story: the AI words it
    ("Cracked the back glass and the lens is", None),
])
def test_what_one_wording_said_well_still_is(quote, words):
    assert flaw_words([quote]) == words


# ── cause-done-split-7, order-leads-whole-two-clauses: a story or deed with more after it ────────────────────────

@pytest.mark.parametrize("title, description, reason", [
    ("iPhone 13 mini", "dropped it and cracked the back but screen fine", "the back is cracked"),
    ("iPhone XR", "Bent the frame and no dead pixels", "the frame is bent"),
    ("iPhone 12", "Fell and cracked the back. Unlocked", "the back is cracked"),
    ("iPhone 12 64GB", "Dropped it and cracked the back. Everything else fine", "the back is cracked"),
    ("iPhone 13 128GB", "Works perfectly and the back glass is cracked", "the back glass is cracked"),
    ("iPhone 13", "Dropped it and smashed the screen", "the screen is smashed"),
    ("iPhone 13", "Smashed the back and screen is mint", "the back is smashed"),
])
def test_a_story_or_deed_says_only_the_flaw(title, description, reason):
    assert draft(description, title) == SAYS.format(reason)


def test_a_deed_with_praise_after_it_in_your_style():
    assert draft("Cracked the back and the screen is perfect", card=GIVEN) == \
        "Hi mate, would you take £170 given that the back is cracked? Can collect today."


def test_water_damage_and_what_it_does_reads_as_one():
    assert draft("Water damaged and doesn't turn on. Spares or repairs", "iPhone XR",
                 flaws=["Water damaged and doesn't turn on"]) == SAYS.format("it's water damaged and doesn't turn on")
    assert draft("Water damaged and doesn't turn on. Spares or repairs", "iPhone XR") == \
        SAYS.format("it's water damaged and doesn't turn on and it's sold as spares or repairs")
    assert flaw_phrase("Cracked and doesn't charge") == "that it's cracked and doesn't charge"


# ── order-leads-split-unlocked, -praise: a selling point or praise is never the reason ───────────────────────────

def test_a_selling_point_is_never_the_reason():
    assert draft("Unlocked and back glass cracked. Any questions just ask", "iPhone 12 64GB") == \
        SAYS.format("the back glass is cracked")
    assert draft("Network unlocked and back glass cracked, collection only", "iPhone 12 Pro 128GB", card=GIVEN) == \
        "Hi mate, would you take £170 given that the back glass is cracked? Can collect today."
    assert flaw_phrase("Unlocked") is None and flaw_phrase("Network unlocked") is None
    for quote in ("Boxed and small crack on the back", "Comes with charger and small crack on the back",
                  "iCloud free and small crack on the back"):
        assert flaw_words([quote]) == "the small crack on the back", quote


def test_praise_is_never_the_reason():
    quote = "Very good condition and small crack on the back"
    assert draft(f"{quote}. Works perfectly", flaws=[quote]) == SAYS.format("of the small crack on the back")
    quote = "The screen is in perfect condition and there is a small crack on the back glass"
    assert draft(f"{quote}.", "iPhone 13 Pro 256GB", flaws=[quote], card=GIVEN) == \
        "Hi mate, would you take £170 given that there's a small crack on the back glass? Can collect today."
    assert flaw_words(["Good condition and a small chip on the corner"]) == "a small chip on the corner"
    assert flaw_words(["Screen is perfect and the back has a small crack and a dent"]) == \
        "that the back has a small crack and a dent"
    assert flaw_words(["Cracked back and battery 88%"]) == "the cracked back"  # a good battery is no reason either


def test_a_half_that_is_neither_gives_no_wording():
    """Not a fault, nor clearly not one ("has a small" from a cut quote): the AI words it."""
    assert flaw_words(["Scuffs on frame and back has a small"]) is None
    assert reason_sentence({"about": "flaw", "says": ["Unlocked and very good condition"]}) is None


# ── the-word-6: a run-on after "turn on" is two faults ───────────────────────────────────────────────────────────

def test_a_run_on_after_turn_on_is_two_faults():
    assert draft("wont turn on screen cracked, sold as seen no returns", "iPhone 12 Pro 128gb spares or repairs",
                 flaws=["wont turn on screen cracked"], asking="120") == \
        "Hi, would you take £100 cash for it? I'm offering that because it wont turn on and the screen is cracked. " \
        "I can come and collect."
    assert draft("wont turn on screen cracked, sold as seen no returns", "iPhone 12 Pro 128gb spares or repairs",
                 flaws=["wont turn on screen cracked"], asking="120", card=HELLO) == \
        "Hello, would you accept £100 given that it wont turn on and that the screen is cracked? Thanks"
    assert draft("doesnt turn on screen is smashed. collection only", "Samsung S21 for spares",
                 flaws=["doesnt turn on screen is smashed"], asking="60") == \
        "Hi, would you take £50 cash for it? I'm offering that because it doesnt turn on and the screen is smashed. " \
        "I can come and collect."
    # it does come on: what's wrong is the flicker
    assert draft("phone comes on screen flickers sometimes. Battery 82%", "iPhone XR 64GB",
                 flaws=["phone comes on screen flickers"], asking="80") == \
        "Hi, would you take £65 cash for it? I'm offering that because the screen flickers. I can come and collect."
    assert flaw_phrase("won't turn on the screen") == "that it won't turn on the screen"  # no second fault: one


def test_a_run_on_listing_says_its_crack():
    """The checks read "wont turn on screen cracked" as a crack, not "won't... cracked" (else no message could
    say it)."""
    assert "crack" in condition_said("wont turn on screen cracked")
    assert "crack" in condition_said("won't turn on screen cracked")
    assert "scratch" not in condition_said("doesnt turn on no scratches")  # a denial after it still is one
    assert "crack" not in condition_said("not working and not cracked")
