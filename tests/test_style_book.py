"""The messages your style is learned from: the style card and the message
search follow every message added or deleted, with no AI and nothing uploaded."""

import pytest

from flip.message_drafter import draft_message
from flip.retrieval import MessageIndex
from flip.style import StyleBook, check_not_removed, describe, learned, phrase_rows, scrubbed, style_card, traits, without
from flip.writer import write_offer
from tests.fakes import fake_embed

SENT = [{"id": "m1", "listing_title": "iPhone 13 128GB", "asking_price": "220", "marketplace": "facebook",
         "my_message": "Hi mate, would you take £185 cash? Can collect today."},
        {"id": "m2", "listing_title": "PS5 Slim disc", "asking_price": "300", "marketplace": "facebook",
         "my_message": "Hi mate, would you take £255 cash? Can collect today."}]


def book(tmp_path, index=True):
    return StyleBook(tmp_path / "style.sqlite3",
                     MessageIndex(tmp_path / "chroma", embed=fake_embed) if index else None)


def test_the_search_follows_every_message_added_and_deleted(tmp_path):
    found = book(tmp_path)
    found.add(SENT, "csv")
    assert [m["id"] for m in found.index.similar("iPhone 13 128GB facebook", n=1)] == ["m1"]
    found.remove("m1")
    assert [m["id"] for m in found.index.similar("iPhone 13 128GB facebook")] == ["m2"]
    assert found.remove("m1") is False


def test_learning_the_same_messages_twice_keeps_one_copy(tmp_path):
    found = book(tmp_path)
    found.add(SENT, "csv")
    found.add(SENT, "csv")
    assert len(found.messages()) == 2 and sorted(found.index.ids()) == ["m1", "m2"]


def test_the_search_catches_up_with_messages_it_missed(tmp_path):
    book(tmp_path, index=False).add(SENT, "csv")  # stored, but never searched
    MessageIndex(tmp_path / "chroma", embed=fake_embed).add([{**SENT[0], "id": "gone"}])  # searched, but gone
    assert sorted(book(tmp_path).index.ids()) == ["m1", "m2"]


def test_the_card_is_the_one_your_messages_give_and_changes_with_them(tmp_path):
    found = book(tmp_path, index=False)
    found.add(SENT, "csv")
    assert found.card() == style_card(SENT)
    found.remove("m2")
    assert found.card()["messages"] == 1


def test_the_card_in_words():
    card = style_card(SENT)
    assert traits(card) == [("Opens with", "'Hi mate'"), ("Length", "about 10 words"),
                            ("Mentions", "collecting, cash and today"), ("Says the flaw", "no")]
    # the greeting and the offer share a sentence, so there's no opener of its own
    assert phrase_rows(card) == [("Offer sentence", "Hi mate, would you take £… cash?"), ("Closing", "Can collect today.")]
    assert traits({}) == [] and phrase_rows({}) == []


# ── what it learned, each thing yours to remove ─────────────────────────────

def test_what_your_style_learned_is_listed_one_thing_a_row(tmp_path):
    found = book(tmp_path, index=False)
    found.add(SENT, "csv")
    assert [(r["what"], r["value"], r["used"]) for r in found.learned()] == [
        ("Opens with", "Hi mate", True), ("Mentions", "coming to collect", True), ("Mentions", "paying cash", True),
        ("Mentions", "today or asap", True), ("Offer sentence", "Hi mate, would you take £… cash?", True),
        ("Closing", "Can collect today.", True)]
    assert learned({}) == []


def test_what_you_remove_comes_off_the_card_and_the_ai_is_told_never_to_write_it(tmp_path):
    found = book(tmp_path, index=False)
    found.add(SENT, "csv")
    keys = {r["value"]: r["key"] for r in found.learned()}
    assert found.use(keys["paying cash"], False) and found.use(keys["Hi mate"], False)
    card = found.card()
    assert "cash" not in card["mentions"] and "cash" not in card["promises"] and "greeting" not in card
    assert card["removed"] == {"greetings": ["Hi mate"], "habits": ["cash"], "phrases": [], "asks": [], "emoji": False,
                               "flaw": False}
    assert [r["used"] for r in found.learned()] == [False, True, False, True, True, True]
    assert describe(card)[-2:] == ['Never opens with "Hi mate"', "Never mentions paying cash"]
    # put back, it's on the card again; what isn't removed, or was never learned, can't be
    assert found.use(keys["paying cash"], True) and "cash" in found.card()["promises"]
    assert found.use(keys["paying cash"], True) is False
    assert found.use("greeting:yo", False) is False
    # removing it changes what's used, never your messages
    assert len(found.messages()) == 2 and found.learned_card() == style_card(SENT)


def test_a_sentence_you_remove_is_no_habit_any_more(tmp_path):
    found = book(tmp_path, index=False)
    found.add(SENT, "csv")
    found.use(next(r["key"] for r in found.learned() if r["what"] == "Closing"), False)
    assert found.card()["phrases"]["closing"] is None
    assert describe(found.card())[-1] == 'Never writes "Can collect today."'


def test_a_draft_never_writes_what_you_removed(tmp_path):
    found = book(tmp_path, index=False)
    found.add(SENT, "csv")
    keys = {r["value"]: r["key"] for r in found.learned()}
    for value in ("Hi mate", "paying cash", "Can collect today."):
        found.use(keys[value], False)
    card = found.card()
    assert check_not_removed("Hi mate, would you take £185 cash? Can collect today.", card) == [
        'the message opens with "Hi mate", which you removed from your style',
        "the message mentions paying cash, which you removed from your style",
        'the message writes "Can collect today.", which you removed from your style']
    assert check_not_removed("Hi, would you take £185? I can collect tomorrow.", card) == []
    assert check_not_removed("Hi mate, would you take £185 cash?", style_card(SENT)) == []  # nothing removed


def test_a_question_you_ask_every_time_can_be_removed():
    card = style_card([{"my_message": "Hi, would you take £90? Does it come with a charger?"},
                       {"my_message": "Hello. Does it come with a charger? Would you take £120?"}])
    assert [(r["key"], r["value"]) for r in learned(card) if r["what"] == "Asks every time"] == \
        [("ask:does it come with a charger", "does it come with a charger?")]
    gone = without(card, {"ask:does it come with a charger"})
    assert "does it come with a charger" not in gone["asks"]
    assert check_not_removed("Hi, does it come with a charger? Would you take £100?", gone) == \
        ['the message asks "does it come with a charger?", which you removed from your style']
    assert describe(gone)[-1] == 'Never asks "does it come with a charger?"'


def test_a_question_in_one_of_your_sentences_is_listed_once():
    card = style_card([{"my_message": "Hi mate, still available? Would you take £90?"},
                       {"my_message": "Hi mate, still available? Would you take £120?"}])
    assert [(r["what"], r["value"]) for r in learned(card)] == [
        ("Opens with", "Hi mate"), ("Usual opener", "Hi mate, still available?"),
        ("Offer sentence", "Would you take £…?")]


# ── what test agents tried, to break removing things from your style (12 Sep 2026) ──

TODAY = [{"my_message": f"Hi mate, would you take £{p} cash? Can collect today."} for p in (185, 120, 60)]
THUMBS = style_card([{"my_message": f"Hi mate, would you take £{p}? 👍"} for p in (185, 120, 60)])
CHARGER = style_card([{"my_message": "Hi, would you take £90? Does it come with a charger?"},
                      {"my_message": "Hello. Does it come with a charger? Would you take £120?"},
                      {"my_message": "Hiya, does it come with a charger? Would you take £150?"}])
BOSE = {"id": "b", "title": "Bose QuietComfort 45 headphones", "description": "Good condition, works perfectly.",
        "asking_price": "150", "marketplace": "facebook"}


class Examples:
    """A search that finds the given past messages."""

    def __init__(self, messages):
        self.messages = messages

    def similar(self, query, leave_out=None, n=3):
        return [{**m, "id": f"m{i}", "listing_title": "Bose"} for i, m in enumerate(self.messages)]


def test_a_removed_habit_never_comes_back_through_your_examples():
    pick = [{"my_message": f"Hi mate, would you take £{p}? Happy to pick it up tonight."} for p in (185, 120, 60)]
    card = without(style_card(pick), {"mention:collecting"})
    assert draft_message(BOSE, card, Examples(pick), writer="template", offer=12500)["status"] == "needs you"


@pytest.mark.parametrize("habit, messages", [
    ("postage", ["Hi, would you take £85? Could you send it tracked?", "Hi, would you take £85? Happy to cover shipping.",
                 "Hi, would you take £85? Happy to pay for posting it."]),
    ("collecting", ["Hi, would you take £185 cash? I can pick it up today.",
                    "Hi, would you take £185 cash? Can come and grab it tonight.",
                    "Hi, would you take £185 cash? Can pop round tonight."]),
])
def test_a_removed_habit_is_caught_in_other_words(habit, messages):
    card = without(style_card(TODAY + [{"my_message": "Hi, would you take £85? Happy to pay postage."}] * 3),
                   {f"mention:{habit}"})
    assert all(check_not_removed(m, card) for m in messages)


@pytest.mark.parametrize("message", ["Hi mate would you take £185 for it?", "Hi mate - would you take £185 for it?",
                                     "Hi mate :) would you take £185 for it?", "Hi mate 👋 would you take £185 for it?",
                                     "Hi  mate, would you take £185?"])
def test_a_removed_greeting_is_caught_whatever_follows_it(message):
    assert check_not_removed(message, without(style_card(TODAY), {"greeting:hi mate"}))


def test_a_removed_question_is_caught_in_the_offers_own_sentence_and_never_asked_again():
    card = without(CHARGER, {"ask:does it come with a charger"})
    assert check_not_removed("Hi, would you take £90, does it come with a charger?", card)
    assert "charger" not in scrubbed("Hi, would you take £90, does it come with a charger?", card)
    longer = draft_message({"id": "i", "title": "iPhone 13 128GB Blue", "description": "Unlocked, good condition.",
                            "asking_price": "220", "marketplace": "facebook"}, card, writer="template", length="longer")
    assert "charger" not in (longer["answer"] or {}).get("message", "")


def test_a_removal_stands_after_you_add_messages(tmp_path):
    found = book(tmp_path, index=False)
    found.add(TODAY, "csv")
    found.use("greeting:hi mate", False)
    found.add([{"my_message": f"Hi, would you take £{p} cash? Can collect today."} for p in (100, 90, 80, 70)], "approved")
    assert check_not_removed("Hi mate, would you take £185 cash? Can collect today.", found.card())
    assert any(r["key"] == "greeting:hi mate" and not r["used"] for r in found.learned())


def test_the_template_still_writes_once_a_greeting_or_sentence_is_removed():
    no_greeting = draft_message(BOSE, without(style_card(TODAY), {"greeting:hi mate"}), writer="template", offer=12500)
    assert (no_greeting["status"], no_greeting["answer"]["message"]) == \
        ("ready", "Hi, would you take £125 cash? Can collect today.")
    no_offer = without(style_card(TODAY), {"phrase:offer:hi mate, would you take £[offer] cash?"})
    assert write_offer(no_offer, "lower", 12500).startswith("Hi mate, would you take £125 for it?")


def test_the_list_has_each_thing_once_and_nothing_it_never_puts_in():
    def keys(messages):
        return [r["key"] for r in learned(style_card([{"my_message": m} for m in messages]))]
    assert [r["what"] for r in learned(THUMBS)].count("Closing") == 0  # 👍 is the Emojis row
    assert "👍" not in write_offer(without(THUMBS, {"emoji"}), "lower", 12500)
    assert not any(k.startswith("phrase:opener") for k in keys([f"Hi mate! Would you take £{p} cash?" for p in (185, 120)]))
    assert "says-flaw" not in keys([f"Hi mate, what condition is it in? Would you take £{p}?" for p in (185, 120, 60)])
    assert "emoji" not in keys(["Hi, would you take £50? 😊"] + [f"Hi, would you take £{p}?" for p in (60, 70, 80, 90)])
    assert "mention:postage" not in keys([f"Hi, saw your post. Would you take £{p}?" for p in (100, 80, 60)])
    assert "mention:collecting" not in keys([f"Hi, is it collection only? Would you take £{p}?" for p in (100, 80, 60)])
    assert not any(k.startswith("ask:") for k in keys(["Alright mate? Would you take £150 cash?",
                                                       "Alright mate? Is it boxed? Would you take £90 cash?",
                                                       "Alright mate? Still for sale? Would you take £70 cash?"]))
    asks = learned(style_card([{"my_message": m} for m in ["Hi mate, still available? Would you take £90?"] * 2 +
                               ["Still available? Would you take £70?"] * 2]))
    assert [r["value"] for r in asks].count("still available?") <= 1
    cased = ["Hi mate, would you take £185 cash?", "hi mate, would you take £120 cash?", "HI MATE, would you take £60 cash?"]
    assert style_card([{"my_message": m} for m in cased * 2]).get("greeting") is not None


@pytest.mark.parametrize("card, removed, message, shown", [
    (style_card(TODAY), {"mention:cash"}, "Hi mate, would you take £185? Cash waiting.", "Hi mate, would you take £[OFFER]?"),
    (style_card(TODAY), {"mention:today"}, "Hi mate, would you take £185 cash? Can collect today or tomorrow.",
     "Hi mate, would you take £[OFFER] cash?"),
    (style_card(TODAY), {"mention:collecting"}, "Hi mate, would you take £185 cash? Happy to pick it up tonight.",
     "Hi mate, would you take £[OFFER] cash?"),
    (style_card(TODAY), {"phrase:closing:can collect today."}, "Hi mate, would you take £185 cash? can collect today",
     "Hi mate, would you take £[OFFER] cash?"),
    (style_card([{"my_message": f"Alright mate? Would you take £{p} cash?"} for p in (150, 90, 70)]),
     {"greeting:alright mate"}, "Alright mate? Would you take £150 cash?", "Would you take £[OFFER] cash?"),
    (THUMBS, {"emoji"}, "Hi mate, would you take £185? 👍 Can collect today.", "Hi mate, would you take £[OFFER]? Can collect today."),
])
def test_your_examples_are_shown_clean_without_what_you_removed(card, removed, message, shown):
    assert scrubbed(message, without(card, removed)) == shown


def test_cleaning_an_example_never_cuts_inside_a_word():
    kisses = style_card([{"my_message": f"Hi hun, would you take £{p}? x"} for p in (40, 30, 25)])
    assert "Xbox" in scrubbed("Hi hun, would you take £40 for the Xbox controller? Can collect next week x",
                              without(kisses, {"phrase:closing:x"}))


def test_a_question_in_a_removed_sentence_goes_with_it():
    opener = style_card([{"my_message": f"Hi mate, is this still available? Would you take £{p} cash?"} for p in (150, 90, 70)])
    card = without(opener, {"phrase:opener:hi mate, is this still available?"})
    assert check_not_removed("Hi, is this still available? Would you take £150 cash?", card)
