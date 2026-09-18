"""Writing an offer with no AI: your own sentences, the seller's words, and
nothing anyone made up."""

from pathlib import Path

import pytest

from flip.style import load_messages, phrasebook, style_card
from flip.writer import as_statement, collecting_from, flaw_phrase, flaw_words, good_words, make_longer, merge_questions, repeats, \
    with_reason, write_offer

ROOT = Path(__file__).resolve().parent.parent
PAST = style_card(load_messages(ROOT / "testset" / "messages.example.csv"))  # messages that repeat
FLAW = {"about": "flaw", "says": ["Black dot on the screen"]}
CHATTY = style_card([{"my_message": "Hiya! Is the iPhone still up for grabs? Could you do £255? 😊"},
                     {"my_message": "Hey, lovely looking PS5! Would you consider £240? Can come over this evening"},
                     {"my_message": "Hi! Still available? I could do £170 if that's any good 👍"}])


# ── your phrasebook ─────────────────────────────────────────────────────────

def test_your_phrasebook_is_the_sentences_you_use_again_and_again():
    # every one of these offered under asking, so that's the only kind with a sentence of its own
    assert PAST["phrases"] == {"opener": "Hi mate, is this still available?", "offer": "Would you take £[OFFER] cash?",
                               "offer_lower": "Would you take £[OFFER] cash?", "offer_asking": None,
                               "offer_more": None, "closing": "Can collect today.", "emoji": ""}
    assert phrasebook([{"my_message": "Hiya, £100?"}, {"my_message": "Hey! Would £90 do?"}]) == \
        {"opener": None, "offer": None, "offer_lower": None, "offer_asking": None, "offer_more": None,
         "closing": "", "emoji": ""}


def test_messages_that_repeat_are_written_without_ai_and_ones_that_vary_by_ai():
    assert repeats(PAST) and not repeats(CHATTY) and not repeats({}) and not repeats(None)


# ── the message ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kind, offer, point, message", [
    ("lower", 18500, FLAW, "Hi mate, is this still available? Would you take £185 cash, given the black dot on the "
                           "screen? Can collect today."),
    ("asking", 22000, FLAW, "Hi mate, is this still available? I can pay £220 cash. I don't mind the black dot on the "
                            "screen. Can collect today."),
    ("more", 42000, {"about": "condition", "says": ["Excellent condition"]},
     "Hi mate, is this still available? I can pay £420 cash, as it's in excellent condition. Can collect today."),
    ("lower", 18500, None, "Hi mate, is this still available? Would you take £185 cash? Can collect today."),
])
def test_your_own_sentences_with_the_new_price_and_the_sellers_words(kind, offer, point, message):
    assert write_offer(PAST, kind, offer, point, item="iPhone 13") == message


def test_with_no_past_messages_it_writes_alertflips_messages():
    # on Facebook and Gumtree: cash, and you come and collect
    assert write_offer(None, "lower", 18500, FLAW, item="iPhone 13", in_person=True) == \
        "Hi, would you take £185 cash for it? I'm offering that because of the black dot on the screen. " \
        "I can come and collect."
    assert write_offer({}, "asking", 22000, item="iPhone 13", in_person=True) == \
        "Hi, is this still available? I'll pay the full £220 cash and can come and collect. Could you hold it for me?"
    assert write_offer({}, "more", 42000, item="iPhone 13", in_person=True) == \
        "Hi, I'll pay £420 cash if you take the listing down and sell it to me. I can come and collect."
    # on eBay and Vinted it's paid through the site and posted: neither
    assert write_offer(None, "lower", 18500, FLAW, item="iPhone 13") == \
        "Hi, would you take £185 for it? I'm offering that because of the black dot on the screen."
    assert write_offer({}, "asking", 22000, item="iPhone 13") == \
        "Hi, is this still available? I'm happy to pay the full £220. Could you hold it for me?"
    assert write_offer({}, "more", 42000, item="iPhone 13") == \
        "Hi, I'll pay £420 if you take the listing down and sell it to me."


def test_a_low_battery_is_the_reason_for_a_lower_offer():
    battery = {"about": "battery", "says": ["battery health 80%"], "battery": "80"}
    assert write_offer({}, "lower", 23500, battery, in_person=True) == \
        "Hi, would you take £235 cash for it? I'm offering that because the battery health is 80%. I can come and collect."
    # in your own sentences it goes after the offer, like a flaw
    assert write_offer(PAST, "lower", 23500, battery) == "Hi mate, is this still available? Would you take £235 " \
                                                          "cash, given that the battery health is 80%? Can collect today."


def test_the_reason_sentence_says_each_flaw_the_way_it_reads():
    two = {"about": "flaw", "says": ["Broken back", "doesn't charge"]}
    assert write_offer({}, "lower", 9000, two) == \
        "Hi, would you take £90 for it? I'm offering that because of the broken back and because it doesn't charge."
    assert write_offer({}, "lower", 9000, {"about": "flaw", "says": ["Not charging"]}) == \
        "Hi, would you take £90 for it? I'm offering that because it's not charging."
    # the seller's own story has no sentence here: the AI writes instead
    assert write_offer({}, "lower", 9000, {"about": "flaw", "says": ["I dropped it and cracked the back"]}) is None


def test_the_pickup_place_goes_in_only_where_you_say_youll_collect():
    assert write_offer(PAST, "lower", 18500, item="iPhone 13", pickup="Leeds LS6").endswith(
        "Can collect from Leeds LS6 today.")
    assert write_offer(None, "lower", 18500, item="iPhone 13", pickup="Leeds LS6", in_person=True).endswith(
        "I can come and collect from Leeds LS6.")
    assert "Leeds" not in write_offer(None, "lower", 18500, item="iPhone 13", pickup="Leeds LS6")
    assert "Leeds" not in write_offer(CHATTY, "lower", 18500, item="iPhone 13", pickup="Leeds LS6")


@pytest.mark.parametrize("says, words", [
    (["Broken back"], "the broken back"),
    (["Doesn't charge with a cable"], "that it doesn't charge with a cable"),
    (["Has a few scratches on the screen"], "that it has a few scratches on the screen"),
    (["A few scuffs on the frame"], "a few scuffs on the frame"),
    (["Left joycon drifts"], "that the left joycon drifts"),
    (["Hinge is stiff"], "that the hinge is stiff"),
    (["One AirPod has a faulty mic"], "that one AirPod has a faulty mic"),
    (["Battery drains quite fast"], "that the battery drains quite fast"),
    (["Scratches on the screen"], "the scratches on the screen"),
    (["Faulty HDMI port", "Spares or repairs"], "the faulty HDMI port and that it's sold as spares or repairs"),
])
def test_the_sellers_flaw_reads_as_part_of_the_sentence(says, words):
    assert flaw_words(says) == words


def test_good_condition_reads_as_part_of_the_sentence():
    assert good_words(["Excellent condition"]) == "it's in excellent condition"
    assert good_words(["barely used"]) == "it's barely used"


def test_questions_about_what_comes_with_it_are_asked_together():
    assert merge_questions(["What's the battery health?", "Does it come with a charger?",
                            "Does it come with the box?"]) == \
        ["What's the battery health?", "Does it come with a charger and the box?"]


def test_an_emoji_habit_ends_the_message_and_a_reason_goes_before_it():
    card = style_card([{"my_message": "Hi! Still available? Would you take £170? 👍"},
                       {"my_message": "Hi! Still available? Would you take £90? 👍"}])
    assert write_offer(card, "lower", 18500, FLAW, item="iPhone 13") == \
        "Hi! Still available? Would you take £185, given the black dot on the screen? 👍"


# ── longer ─────────────────────────────────────────────────────────────────

def test_a_longer_message_adds_the_open_questions_then_only_safe_lines():
    asks = ["Does it come with a charger?", "Does it come with the box?"]
    assert write_offer(None, "lower", 18500, FLAW, asks, at_least=23, item="iPhone 13") == \
        "Hi, would you take £185 for it? I'm offering that because of the black dot on the screen. Does it come " \
        "with a charger and the box?"
    assert write_offer(None, "lower", 34000, None, [], at_least=23, item="PlayStation 5 Slim") == \
        "Hi, I'm interested in your PlayStation 5 Slim. Would you take £340 for it? Let me know what you think."
    assert write_offer(None, "lower", 34000, None, [], at_least=23, item="PlayStation 5 Slim", in_person=True) == \
        "Hi, I'm interested in your PlayStation 5 Slim. Would you take £340 cash for it? Let me know what you think. " \
        "I can come and collect."


def test_the_draft_on_screen_keeps_every_word():
    on_screen = "Hi mate, is this still available? Would you take £185 cash? Can collect today."
    longer = make_longer(on_screen, ["Does it come with a charger?"], 23, "iPhone 13")
    assert longer == "Hi mate, I'm interested in your iPhone 13. Is this still available? Would you take £185 cash? " \
                     "Does it come with a charger? Can collect today."
    assert make_longer("Hi mate, would you take £185?", ["Does it come with a charger?"], 0, "iPhone 13") == \
        "Hi mate, would you take £185? Does it come with a charger?"


@pytest.mark.parametrize("part, phrase", [
    ("It's cracked", "that it's cracked"),
    ("It has a few scratches on the back", "that it has a few scratches on the back"),
    ("There's a crack on the back", "that there's a crack on the back"),
    ("Not charging", "that it's not charging"),
    ("Cracked", "that it's cracked"),
    ("No picture", "that there's no picture"),
    # the seller's own story, or a denied fault, has no sentence here: the AI writes instead
    ("I dropped it and cracked the back", None),
    ("My son cracked the screen", None),
    ("Not spares or repairs", None),
])
def test_the_sellers_words_fit_a_sentence_or_are_left_to_the_ai(part, phrase):
    assert flaw_phrase(part) == phrase


@pytest.mark.parametrize("says, words", [
    (["Phone is in excellent condition"], "it's in excellent condition"),
    (["condition Excellent"], "it's in excellent condition"),  # "Condition: Excellent", as read_listing has it
    (["Condition is good"], "it's in good condition"),
    (["Hardly used"], "it's hardly used"),
    (["Works perfectly"], None),
])
def test_good_condition_in_a_shape_it_can_say(says, words):
    assert good_words(says) == words


@pytest.mark.parametrize("habit, said", [
    ("Would you take £[OFFER] cash?", "I can pay £[OFFER] cash."),
    ("Hi mate, would you take £[OFFER]?😊", "Hi mate, I can pay £[OFFER]. 😊"),
    ("Would you take £[OFFER] x", "I can pay £[OFFER]. x"),
    ("Is £[OFFER] ok?", "I can pay £[OFFER]."),
    ("Would you take [OFFER] quid?", "I can pay £[OFFER]."),
    ("Would you take £[OFFER] at all?", "I can pay £[OFFER]."),
    ("Would you take £[OFFER] or is that too cheeky?", "I can pay £[OFFER]."),
])
def test_an_offer_at_or_over_asking_is_said_in_plain_words(habit, said):
    assert as_statement(habit) == said


def test_the_reason_goes_before_a_sign_off():
    flaw = {"about": "flaw", "says": ["Broken back"]}
    assert with_reason("Would you take £[OFFER]...", "lower", flaw) == "Would you take £[OFFER], given the broken back? ..."
    assert with_reason("Would you take £[OFFER] x", "lower", flaw) == "Would you take £[OFFER], given the broken back? x"


def test_an_offer_at_or_over_asking_is_never_called_low():
    cheeky = style_card([{"my_message": "Hi mate, would you take £170? I know it's a bit cheeky."},
                         {"my_message": "Hi mate, would you take £90? I know it's a bit cheeky."}])
    assert "cheeky" in write_offer(cheeky, "lower", 17000, item="PS5")
    assert write_offer(cheeky, "more", 21000, item="PS5") == "Hi mate, I can pay £210 if you can hold it for me."


def test_a_greeting_inside_the_offer_stays_first_in_a_longer_message():
    card = style_card([{"my_message": "Hi mate, would you take £185? Can collect today."},
                       {"my_message": "Hi mate, would you take £150? Can collect today."}])
    assert write_offer(card, "lower", 17000, questions=["Does it come with a charger?"], at_least=23,
                       item="iPhone 13").startswith("Hi mate, I'm interested in your iPhone 13. Would you take £170?")


def test_making_a_draft_longer_never_breaks_the_greeting_or_asks_twice():
    shout = make_longer("Hi mate! Is this still available? Would you take £170 cash? Can collect today.",
                        ["What's the battery health?"], 0, "iPhone 13")
    assert shout.startswith("Hi mate! Is this still available?")
    once = "Hi mate, is this still available? Would you take £170 cash? What's the battery health? Does it come " \
           "with a charger and the box? Can collect today."
    again = make_longer(once, ["What's the battery health?", "Does it come with a charger?",
                               "Does it come with the box?"], 0, "iPhone 13")
    assert again == once


@pytest.mark.parametrize("part, phrase", [
    ("Face ID not working", "that the Face ID is not working"),  # "ID" isn't "I"
    ("Faulty", "that it's faulty"),
    ("Slightly scratched", "that it's slightly scratched"),
    ("Cracked and scratched", "that it's cracked and scratched"),
    ("iPhone 13 128GB cracked screen", "the cracked screen"),  # a flaw from the title, without the title
    ("Selling for parts", "that it's sold for parts"),
    ("Sold as spares", "that it's sold as spares"),
    ("cracked the back", None),  # a deed: the AI words it
])
def test_more_of_the_sellers_wordings(part, phrase):
    assert flaw_phrase(part) == phrase


def test_the_place_goes_after_collect_it():
    assert collecting_from("Can collect it today.", "Leeds LS6") == "Can collect it from Leeds LS6 today."


def test_a_question_the_draft_already_asks_isnt_asked_again_in_a_merged_one():
    longer = make_longer("Hi, would you take £170? Does it come with a charger? Thanks.",
                         ["What's the battery health?", "Does it come with a charger?", "Does it come with the box?"],
                         0, "iPhone 13")
    assert longer.count("charger") == 1 and "Does it come with the box?" in longer


def test_less_than_youre_asking_isnt_said_with_an_offer_over_asking():
    card = style_card([{"my_message": "Hi mate, would you take £170? I know it's less than you're asking."},
                       {"my_message": "Hi mate, would you take £90? I know it's less than you're asking."}])
    assert write_offer(card, "more", 21000, item="PS5") == "Hi mate, I can pay £210 if you can hold it for me."


def test_a_sellers_run_on_flaw_reads_as_a_sentence():
    """A real listing (2 Sep): "one issue with the screen it turns on and off sometimes"."""
    point = {"about": "flaw", "says": ["one issue with the screen it turns on and off"]}
    assert write_offer({}, "lower", 9000, point) == \
        "Hi, would you take £90 for it? I'm offering that because of the issue with the screen – it turns on and off."
    assert write_offer({}, "asking", 11000, point) == \
        "Hi, is this still available? I'm happy to pay the full £110. I don't mind the issue with the screen – it " \
        "turns on and off. Could you hold it for me?"
