"""The questions a longer message may ask: only what the listing doesn't
already answer, its category's first."""

import pytest

from flip.questions import MAX_QUESTIONS, answered, check_no_answered_questions, load_questions, open_questions

BROKEN = "iPhone 13 128GB Blue unlocked. Broken back but everything works, battery 86%. Comes with case."


def test_only_what_the_listing_doesnt_answer_is_asked():
    assert open_questions(BROKEN, "phones") == ["Does it come with a charger?", "Does it come with the box?"]
    assert open_questions("iPhone 13 locked to EE, boxed with charger", "phones") == \
        ["What's the battery health?", "Any marks or scratches?"]


def test_a_no_answers_the_question_too():
    assert "box" in answered("AirPods Pro 2, no box")
    assert "Does it come with the box?" not in open_questions("AirPods Pro 2, no box", "headphones")


def test_each_category_asks_its_own_and_unknown_items_only_the_general_ones():
    assert open_questions("PS5 Slim disc edition", "consoles")[0] == "Does it come with a controller?"
    assert open_questions("Samsung fridge freezer") == ["Any marks or scratches?", "Does it come with the box?"]


@pytest.mark.parametrize("text, category, asked", [
    ("iPhone 13 128GB Blue. Mint condition, BH 91%, open to all networks, phone only.", "phones", []),
    ("PS5 Slim disc. Excellent condition. Console only.", "consoles", []),
    ("PS5 Slim disc. Excellent condition. Comes with 2 pads and all wires, boxed.", "consoles", []),
    ("iPhone 13 128GB Blue unlocked. No scratches or dents, battery 90%, boxed with charger.", "phones", []),
    ("iPhone 13 128GB Blue. Brand new and sealed, unlocked, boxed with charger.", "phones",
     ["What's the battery health?"]),
    ("iPhone 13 128GB Blue unlocked. No box. Smashed screen.", "phones",
     ["What's the battery health?", "Does it come with a charger?"]),
    ("iPhone 13 128GB, collection from BH21, cash only", "phones",
     ["What's the battery health?", "Is it unlocked?", "Does it come with a charger?"]),
])
def test_other_ways_a_listing_answers_are_read(text, category, asked):
    assert open_questions(text, category) == asked


def test_never_more_than_a_few():
    assert len(open_questions("iPhone 13 128GB", "phones")) == MAX_QUESTIONS


def test_no_icloud_question_in_a_first_message():
    asks = [q["ask"].lower() for questions in load_questions().values() for q in questions]
    assert not any("icloud" in ask for ask in asks)


def test_a_message_doesnt_ask_what_the_listing_already_says():
    listing = "iPhone 13 128GB Blue unlocked. Good condition, boxed. Battery 88%."
    assert check_no_answered_questions("Would you take £170? Is it unlocked? Does it come with the box?", listing) == \
        ["the message asks what the listing already says: box, unlocked"]
    # what's open, a reason, and a fair follow-up about condition are all fine
    assert check_no_answered_questions("Would you take £170 as it's boxed? Does it come with a charger? Any other "
                                       "marks?", listing) == []


def test_all_accessories_answers_what_comes_with_it():
    assert open_questions("Nintendo Switch OLED. Mint condition, boxed with all accessories.", "consoles") == []


def test_a_flaw_only_ai_found_answers_the_marks_question():
    text = "iPhone 13 128GB Blue unlocked. Black dot on the screen. Battery 88%. Boxed with charger."
    assert open_questions(text, "phones") == ["Any marks or scratches?"]
    assert open_questions(text, "phones", flaws=["Black dot on the screen"]) == []


def test_not_all_the_accessories_answers_nothing():
    assert "Does it come with a charger?" in open_questions(
        "iPhone 13 128GB. Good condition. Doesn't come with all the accessories.", "phones")
