"""List on eBay written by flip-reader-5 and code (flip.listing_code, 14 Oct 2026, the owner: "make it flip-reader 5 just
read it and then we will make the ebay description using that and code ... cos we will only do phones for this"):
short sentences in your own words, nothing your notes don't say. Pretend reader: nothing runs."""

import pytest

from flip.catalogue import load_catalogue, load_conditions
from flip.drafter import draft_listing
from flip.listing_code import NAME, ReaderCodeWriter, written
from tests.fakes import FakeModel

ITEM = {"model_id": "iphone-14", "category": "phones", "brand": "Apple", "model": "iPhone 14", "storage": "128GB",
        "colour": "Midnight", "network": "Unlocked", "battery": "75", "missing": []}


def write(notes, flaws=(), condition="3000", **item):
    return written({**ITEM, **item}, {"colours": ["Midnight", "Starlight", "Blue"]}, condition, list(flaws), notes)


def test_the_flaws_the_battery_and_the_rest_are_short_sentences_in_your_own_words():
    said = write("cracked back, battery 75%, face id works, unlocked, comes with box and charger", ["Cracked back"])
    assert said == {"condition_id": "3000", "condition_note": "Cracked back. Battery health is 75%.",
                    "description": "Apple iPhone 14, 128GB, in Midnight. It's used: cracked back. Battery health is "
                                   "75%. Face ID works. Unlocked. Comes with box and charger."}


def test_two_flaws_go_in_one_sentence():
    said = write("cracked back and the balck dot in the front screen", ["Cracked back", "The balck dot in the front screen"],
                 battery=None)
    assert said["description"] == ("Apple iPhone 14, 128GB, in Midnight. It's used: cracked back and the balck dot in "
                                   "the front screen. Unlocked.")
    assert said["condition_note"] == "Cracked back. The balck dot in the front screen."


def test_flaws_that_would_put_a_mark_somewhere_else_joined_are_a_sentence_each():
    # "...rear camera lens and cracks are on screen protector": read joined, a crack on the camera
    notes = "small blemish on one rear camera lens, cracks are on screen protector not glass"
    said = write(notes, ["Small blemish on one rear camera lens", "Cracks are on screen protector not glass"],
                 battery=None)
    assert "It's used. Small blemish on one rear camera lens. Cracks are on screen protector not glass." in \
        said["description"]


@pytest.mark.parametrize("notes, said, left_out", [
    # a "no" over a list is a no to each: never "Comes with charger or cable"
    ("works, no box, charger or cable", "No box, charger or cable.", "Comes with"),
    # the battery as your notes give it
    ("battery health under 80%", "Battery health is under 80%.", "is 80%"),
    ("battery 90% 264 cycles", "Battery health is 90%, 264 cycles.", ". 264 cycles"),  # not a sentence of its own
    # what's about the listing, the specs and "used" are left out
    ("iphone 14 midnight 128gb, no network info, used", "It's used.", "info"),
    # a thing that comes with it that no claim names
    ("comes with covers", "Comes with covers.", "Covers."),
    # "mint green" is a colour, not its condition
    ("mint green iphone 14", "It's used.", "Mint"),
])
def test_your_notes_are_said_as_they_say_it(notes, said, left_out):
    description = write(notes, battery=None)["description"]
    assert said in description and left_out not in description


def test_a_flaw_the_reader_didnt_quote_is_still_a_flaw():
    said = write("one small chip on right side, fully working", battery=None)
    assert "It's used: one small chip on right side." in said["description"]
    assert said["condition_note"] == "One small chip on right side."


def test_a_new_phone_has_no_condition_note():
    said = write("brand new, sealed in box", condition="1000", battery=None)
    assert (said["condition_note"], said["description"].split(". ")[1]) == ("", "It's new")


def test_a_phone_with_a_fault_is_for_parts_with_its_fault_first():
    said = write("face id not working, battery 81%", ["Face ID not working"], condition="7000", battery="81")
    assert "It's for parts or not working: Face ID not working. Battery health is 81%." in said["description"]


def test_the_drafter_gives_it_the_facts_and_its_draft_passes_the_checks():
    reader = FakeModel("flip-reader-5", {"flaws": ["cracked back and the battery is 75%"], "pickup": "",
                                         "no_offers": ""})
    entry = {"id": "x", "original_title": "iPhone 14 128GB Midnight",
             "my_notes": "cracked back and the battery is 75%, unlocked, boxed"}
    result = draft_listing(entry, load_catalogue(), load_conditions(), ReaderCodeWriter(reader), None, "local", (), None)
    assert result["answer"] is not None and result["attempts"][0]["model"] == NAME
    assert result["answer"]["description"] == ("Apple iPhone 14, 128GB, in Midnight. It's used: cracked back. Battery "
                                               "health is 75%. Unlocked. Comes with box.")
    assert result["attempts"][0]["cost_pence"] == 0  # all on this device


# ── 14 Oct: a model only phrases the facts (the owner: "what if we make gemma 4b make the ebay description") ─────────

from flip.listing_code import PhrasingWriter, facts_missing, facts_of, facts_text  # noqa: E402

PINK = {**ITEM, "model": "iPhone 13", "colour": "Pink", "battery": "88"}


def test_the_facts_keep_every_note_about_the_phone_and_leave_out_the_sale():
    notes = ("iphone 13 pink 128gb, unlocked, battery 88%, face id working, new screen fitted january, charges "
             "wirelessly, second phone, no box, charger or cable")
    facts = facts_of(PINK, {"colours": ["Pink"]}, "3000", [], notes)
    assert facts_text(facts) == ("Phone: Apple iPhone 13, 128GB, Pink\neBay condition: Used\nBattery: Battery health is "
                                 "88%\nOther facts: Unlocked; Face ID working; New screen fitted january; Charges "
                                 "wirelessly; No box, charger or cable")


def test_a_draft_that_leaves_a_fact_out_is_found():
    facts = facts_of({**PINK, "network": None}, {"colours": ["Pink"]}, "3000", ["Cracked back"],
                     "cracked back, battery 88%, comes with box")
    assert facts_missing({"condition_note": "The back glass is cracked.", "description": "Battery health is 88%."},
                         facts) == ["box"]
    assert facts_missing({"condition_note": "The back glass is cracked. Battery health is 88%.",
                          "description": "Comes with the box."}, facts) == []


def test_a_phraser_is_told_the_facts_and_its_draft_goes_through_the_checks():
    reader = FakeModel("flip-reader-5", {"flaws": ["cracked back"], "pickup": "", "no_offers": ""})
    phraser = FakeModel("gemma3:4b", {"condition_note": "The back is cracked. Battery health is 88%.",
                                      "description": "Apple iPhone 13 in Pink. The back is cracked. Battery health is "
                                                     "88%. Comes with the box."})
    writer = PhrasingWriter(phraser, reader)
    entry = {"id": "x", "original_title": "iPhone 13 128GB Pink", "my_notes": "cracked back, battery 88%, boxed"}
    result = draft_listing(entry, load_catalogue(), load_conditions(), writer, None, "local", (), None)
    assert phraser.asked[0]["user"] == ("Phone: Apple iPhone 13, 128GB, Pink\neBay condition: Used\nFlaws: cracked back"
                                        "\nBattery: Battery health is 88%\nComes with: box")
    assert result["answer"] is not None and writer.last_missing == []
