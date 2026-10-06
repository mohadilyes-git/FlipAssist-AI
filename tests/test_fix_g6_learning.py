"""What your style learns, fixed after the 26 Sep red team (v8-integration 1, 2, 3, 11 and 12): a time taken out of a
habit only where it ends the sentence, the closing learned for each kind of offer, no apology or laughing emoji on an
offer of the asking price or more, no hold on a lower offer (in the writer and the AI's check alike), and no "Hi," for
someone who never greets. No AI runs: the AI, where there is one, is tests.fakes.FakeModel."""

import pytest

from flip.checks import HOLD, LOWBALL
from flip.message_drafter import check_ai_manner, draft_message
from flip.style import Habits, StyleBook, describe, for_kind, for_market, learned, phrasebook, style_card
from flip.writer import HELD, write_offer
from tests.fakes import FakeModel

PLAIN = {"id": "x", "title": "iPhone 13 128GB Midnight", "description": "Good condition, unlocked, comes with box.",
         "asking_price": "200", "marketplace": "facebook"}


def past(*rows, market="facebook"):
    """Past messages: (text, asking pounds)."""
    return [{"id": f"m{n}", "my_message": text, "asking_price": str(asking), "marketplace": market,
             "listing_title": "iPhone 12"} for n, (text, asking) in enumerate(rows)]


def drafted(messages, kind="lower", ai=None, **kwargs):
    """The drafter's message for PLAIN, as the red team ran it: your own sentences first, the AI (a FakeModel giving
    the replies in ai, again and again) only if they can't say it."""
    local = FakeModel("gemma3:4b", *[{"message": m} for m in ai] * 3) if ai else None
    api = FakeModel("claude-haiku-5-5", *[{"message": m} for m in ai] * 3) if ai else None
    result = draft_message(PLAIN, style_card(messages), None, local, api, kind=kind, **kwargs)
    return result["status"], result["writer"], (result["answer"] or {}).get("message")


# ── v8-integration-1: a time taken out of a list left "Can collect or Saturday." ─────────────────────────────────

@pytest.mark.parametrize("closings, message", [
    (("Can collect today or Saturday.", "Can collect tomorrow or Saturday."),
     "Hi mate, would you take £170? Can collect tomorrow or Saturday."),
    (("Can collect today or tomorrow if that's easier.", "Can collect tonight or tomorrow if that's easier."),
     "Hi mate, would you take £170? Can collect tonight or tomorrow if that's easier."),
    (("Free from today till Sunday to collect.", "Free from tomorrow till Sunday to collect."),
     "Hi mate, would you take £170? Free from tomorrow till Sunday to collect."),
])
def test_a_time_inside_your_closing_stays_as_you_wrote_it(closings, message):
    """The red team's input: the newest way as you wrote it, never "Can collect or Saturday." nor "Free from till"."""
    messages = past((f"Hi mate, would you take £150? {closings[0]}", 180),
                    (f"Hi mate, would you take £90? {closings[1]}", 110))
    assert drafted(messages) == ("ready", "template", message)


def test_a_time_inside_your_offer_sentence_stays_as_you_wrote_it():
    messages = past(("Hi, would you take £150 if I collect today or tomorrow morning?", 180),
                    ("Hi, would you take £90 if I collect tonight or tomorrow morning?", 110))
    assert drafted(messages) == \
        ("ready", "template", "Hi, would you take £170 if I collect tonight or tomorrow morning?")


@pytest.mark.parametrize("closings, broken", [
    (("can collect today or sat", "can collect tomorrow or sat", "can collect tonight or sat"), "collect or sat"),
    (("Can collect today or tomorrow, whatever suits.", "Can collect tonight or tomorrow, whatever suits."), "or,"),
    (("Free today or tomorrow to collect.", "Free tonight or tomorrow to collect."), "Free or to"),
    (("I can come today or tomorrow evening.", "I can come tonight or tomorrow evening."), "come or evening"),
])
def test_the_verifiers_other_lists_never_leave_a_word_hanging(closings, broken):
    messages = past(*[(f"hi would you take £{p}? {c}", p + 30) for p, c in zip((150, 90, 60), closings)])
    status, _, message = drafted(messages)
    assert status == "ready" and broken not in message and message.split("? ", 1)[1].lower() in \
        {c.lower() for c in closings}


def test_a_time_that_ends_your_sentence_still_goes():
    """The verifier's control: no one time is your habit, so it's said without one."""
    messages = past(("Hi mate, would you take £150? Can collect today.", 180),
                    ("Hi mate, would you take £90? Can collect tomorrow.", 110))
    assert drafted(messages) == ("ready", "template", "Hi mate, would you take £170? Can collect.")


@pytest.mark.parametrize("ways, habit", [
    (("Could you hold it for me till tonight?", "Could you hold it for me till tomorrow?"), "Could you hold it for me?"),
    (("Can collect today 👍", "Can collect tomorrow 👍"), "Can collect 👍"),  # its sign-off kept
    (("Can collect today or tomorrow.", "Can collect tonight or tomorrow."), "Can collect."),  # a list of times at the end
    (("Can collect today. x", "Can collect tonight. x"), "Can collect. x"),
    (("Today if possible.", "Tonight if possible."), "Tonight if possible."),  # not "If possible.": the time is the point
    (("Free from today.", "Free from tomorrow."), "Free from tomorrow."),  # not "Free from."
    (("Can collect today or Saturday.", "Can collect tomorrow or Saturday."), "Can collect tomorrow or Saturday."),
])
def test_a_habit_that_differs_in_when_is_said_without_it_only_where_that_reads(ways, habit):
    counted = Habits()
    for way in ways:
        counted.add(way)
    assert counted.habit() == habit


def test_the_style_list_and_the_ais_description_show_the_closing_as_you_wrote_it():
    card = style_card(past(("Hi mate, would you take £150? Can collect today or Saturday.", 180),
                           ("Hi mate, would you take £90? Can collect tomorrow or Saturday.", 110)))
    assert ("Closing", "Can collect tomorrow or Saturday.") in [(r["what"], r["value"]) for r in learned(card)]
    assert 'Usually ends with "Can collect tomorrow or Saturday."' in describe(card)


# ── v8-integration-2: a lowballer's apology went on offers of the asking price and over it ─────────────────────

LOWBALLER = [(f"{greeting}, would you take £{offer}? {{closing}}", asking)
             for greeting, offer, asking in (("Hi", 150, 180), ("Hiya", 90, 110), ("Hello", 250, 300))]


def lowballer(closing):
    return past(*[(text.format(closing=closing), asking) for text, asking in LOWBALLER])


@pytest.mark.parametrize("closing", ["I know it's a bit less than you're after.",
                                     "I appreciate it's lower than you wanted.",
                                     "I know it's not quite what you're asking."])
def test_an_apology_for_a_low_offer_is_never_said_at_or_over_asking(closing):
    assert drafted(lowballer(closing), "asking") == ("ready", "template", "Hi, I can pay £200 for it.")
    assert drafted(lowballer(closing), "more") == \
        ("ready", "template", "Hi, I can pay £210 if you can hold it for me.")


def test_the_apology_stays_yours_under_asking():
    """The verifier's control: the lower offer is fine."""
    assert drafted(lowballer("I know it's a bit less than you're after."), "lower") == \
        ("ready", "template", "Hi, would you take £170 for it? I know it's a bit less than you're after.")


def test_an_apology_is_left_out_whatever_greeting_you_use():
    """MAIN's own template sent this with one repeated greeting (verified f2_asking_same_greeting)."""
    messages = past(*[(f"Hi, would you take £{p}? I know it's a bit less than you're after.", p + 30)
                      for p in (150, 90, 250)])
    assert drafted(messages, "asking") == ("ready", "template", "Hi, I can pay £200.")


@pytest.mark.parametrize("said", [
    "I know it's a bit less than you're after.", "I appreciate it's lower than you wanted.",
    "I know it's not quite what you're asking.", "i know its a bit less than ur after",
    "It's a bit under what you want", "below what you're asking i know", "I know it's not much",
    "I know it's not the full asking price", "I know it's low",
    "a little lower than you listed it for", "I know it's a bit cheeky.", "I know it's less than you're asking.",
])
def test_lowball_reads_the_ways_an_offer_is_called_low(said):
    assert LOWBALL.search(said)


@pytest.mark.parametrize("said", ["Can collect today.", "I'm less than 10 minutes from you.",
                                  "Can collect in less than an hour.", "Not asking you to post, I'll collect.",
                                  "No worries if not.", "I'll pay the full asking price.", "Could you hold it for me?",
                                  "Cash waiting."])
def test_lowball_leaves_other_sentences_alone(said):
    assert not LOWBALL.search(said)


# ── the closing for each kind of offer (v8-integration-2 and 3) ─────────────────────────────────────────────

HOLDER = past(("Hi, I'll pay the full £200. Could you hold it for me till tonight?", 200),
              ("Hi, would you take £150? Can collect today.", 180),
              ("Hi, I'll pay the full £120. Could you hold it for me till tomorrow?", 120),
              ("Hi, would you take £60?", 80))


def test_the_closing_is_learned_for_each_kind_of_offer():
    """The hold is how you end an offer of the asking price, not one under it: your closing for any kind is one
    you wrote with every kind of offer you make."""
    phrases = style_card(HOLDER)["phrases"]
    assert (phrases["closing"], phrases["closing_lower"], phrases["closing_asking"], phrases["closing_more"]) == \
        (None, None, "Could you hold it for me?", None)
    only_lower = phrasebook(past(("Hi mate, would you take £150? Can collect today.", 180),
                                 ("Hi mate, would you take £90? Can collect today.", 110)))
    assert (only_lower["closing"], only_lower["closing_lower"]) == ("Can collect today.", "Can collect today.")
    # every kind you make: under and at asking both end "Can collect today.", so over asking does too
    both = style_card(past(("Hi mate, would you take £150? Can collect today.", 180),
                           ("Hi mate, I can pay £90. Can collect today.", 90),
                           ("Hi mate, would you take £60? Can collect today.", 80),
                           ("Hi mate, I can pay £70. Can collect today.", 70)))
    assert both["phrases"]["closing"] == "Can collect today."
    assert write_offer(both, "more", 21000) == "Hi mate, I can pay £210 if you can hold it for me. Can collect today."


def test_a_kind_with_no_closing_of_its_own_gets_yours_only_if_it_came_with_that_kind():
    """The sweep of 26 Sep: one asking-price message ending "Cash waiting." took "Can collect tonight." from every
    kind. Now a kind with messages gets your closing if one of them ended that way, a kind with none if every kind
    you have HABIT messages of did."""
    one_asking = past(("Hi mate, I'll pay £290 if you can hold it for me. Can collect tonight.", 280),
                      ("Hi mate, I can pay £200 cash. Cash waiting.", 200),
                      ("Hi mate, would you take £120? Can collect tonight.", 150),
                      ("Hi mate, would you take £90? Can collect tonight.", 120),
                      ("Hi mate, would you take £120? Can collect tonight.", 160))
    assert drafted(one_asking, "more") == \
        ("ready", "template", "Hi mate, I can pay £210 if you can hold it for me. Can collect tonight.")
    assert drafted(one_asking, "asking") == ("ready", "template", "Hi mate, I can pay £200.")  # yours ended otherwise
    ten = past(*[(f"Hi mate, would you take £{p} cash? Can collect today.", p + 30) for p in (150, 90, 60, 120, 140)],
               ("Hi mate, I'll pay the full £200. Could you hold it for me?", 200))
    assert drafted(ten, "more") == \
        ("ready", "template", "Hi mate, I can pay £210 cash if you can hold it for me. Can collect today.")


def test_each_kinds_closing_is_listed_once_and_yours_to_remove(tmp_path):
    rows = [(r["what"], r["value"]) for r in learned(style_card(HOLDER))]
    assert ("Closing at asking", "Could you hold it for me?") in rows and not any(w == "Closing" for w, _ in rows)
    found = StyleBook(tmp_path / "style.sqlite3")
    found.add(HOLDER, "csv")
    key = next(r["key"] for r in found.learned() if r["what"] == "Closing at asking")
    assert found.use(key, False)
    assert write_offer(found.card(), "asking", 20000) == "Hi, I'll pay the full £200."
    assert found.use(key, True)
    assert write_offer(found.card(), "asking", 20000) == "Hi, I'll pay the full £200. Could you hold it for me?"
    # your closing, the same under asking, is listed once as that
    same = style_card(past(("Hi mate, would you take £150? Can collect today.", 180),
                           ("Hi mate, would you take £90? Can collect today.", 110)))
    assert [r["what"] for r in learned(same)].count("Closing") == 1 and \
        not any(r["what"].startswith("Closing ") for r in learned(same))


def test_your_closing_where_you_buy_comes_before_how_all_your_messages_end_that_kind():
    """eBay's "Happy to pay straight away." isn't put aside for the "Can collect today." of your Facebook offers."""
    facebook = past(("Hi mate, would you take £150 cash? Can collect today.", 180),
                    ("Hi mate, would you take £90 cash? Can collect today.", 110))
    ebay = past(("Hi, would you accept £115? Happy to pay straight away.", 140),
                ("Hi, would you accept £70? Happy to pay straight away.", 90), market="ebay")
    messages = facebook + [{**m, "id": f"e{n}"} for n, m in enumerate(ebay)]
    card = style_card(messages)
    assert for_kind(for_market(card, "ebay"), "lower")["phrases"]["closing"] == "Happy to pay straight away."
    assert for_kind(for_market(card, "facebook"), "lower")["phrases"]["closing"] == "Can collect today."


# ── v8-integration-3: the hold of asking-price messages ended a lower offer ──────────────────────────────────

def test_a_lower_offer_never_ends_with_the_hold_you_ask_for_at_asking():
    assert drafted(HOLDER) == ("ready", "template", "Hi, would you take £170?")
    same = [{**m, "my_message": m["my_message"].replace(" till tonight", "").replace(" till tomorrow", "")}
            for m in HOLDER]
    assert drafted(same) == ("ready", "template", "Hi, would you take £170?")
    # at the asking price it's still yours
    assert drafted(HOLDER, "asking") == ("ready", "template", "Hi, I'll pay the full £200. Could you hold it for me?")


def test_a_hold_sentence_goes_from_a_lower_offers_closing_and_the_rest_stays():
    messages = past(("Hi, would you take £150? Can collect today. Could you hold it for me?", 180),
                    ("Hi, would you take £90? Can collect today. Could you hold it for me?", 110))
    assert drafted(messages) == ("ready", "template", "Hi, would you take £170? Can collect today.")


def test_the_ai_is_told_the_closing_for_the_kind_it_writes():
    for kind, offer, told in (("lower", 17000, False), ("asking", 20000, True), ("more", 21000, False)):
        fake = FakeModel("gemma3:4b", *[{"message": "x"}] * 4)
        draft_message(PLAIN, style_card(HOLDER), None, fake, None, kind=kind, writer="ai", offer=offer)
        asked = fake.asked[0]["system"] + fake.asked[0]["user"]
        assert ('Usually ends with "Could you hold it for me?"' in asked) is told, kind


ASKER = past(("Hi mate, would you take £150 cash? Can collect today.", 180),
             ("Hi mate, would you take £90 cash? Can collect tonight.", 110),
             ("Hi mate, would you take £250 cash? Can collect today.", 300))
HOLD_PROBLEM = "a lower offer asks them to hold it: holding it is the deal for paying more"


def test_the_ai_is_refused_a_hold_in_any_sentence_of_a_lower_offer():
    held = "Hi mate, would you take £170 cash? If so could you hold it for me till Saturday? Can collect then."
    assert HOLD_PROBLEM in check_ai_manner(held, "lower", 17000, False)
    assert drafted(ASKER, writer="ai", ai=[held])[0] == "needs you"
    # the verifier's control: in the price sentence it was refused already, and still is
    assert HOLD_PROBLEM in check_ai_manner("Hi mate, would you take £170 cash if you could hold it for me till Saturday?",
                                           "lower", 17000, False)
    # a battery that holds its charge isn't a hold
    battery = "Hi mate, would you take £170 cash? Does the battery hold its charge? Can collect today."
    assert drafted(ASKER, writer="ai", ai=[battery]) == ("ready", "gemma3:4b", battery)


@pytest.mark.parametrize("said", ["if you can keep it till Saturday", "if you can keep it back for me",
                                  "could you save me it?", "could you hang onto it for me",
                                  "Would you mind holding it for me?", "hold on to it for me", "Could you hold it for me?",
                                  "if you take the listing down"])
def test_a_hold_is_read_the_same_by_the_writer_and_the_checks(said):
    assert HELD is HOLD and HOLD.search(said)


@pytest.mark.parametrize("said", ["Does the battery hold its charge?", "How's the battery holding up?",
                                  "Hold on, is it unlocked?", "Happy to keep in touch", "That would save me a trip"])
def test_a_hold_isnt_read_in_other_sentences(said):
    assert not HOLD.search(said)


@pytest.mark.parametrize("hold", ["keep it back for me", "save me it", "hang onto it for me"])
def test_your_own_over_asking_hold_says_why_in_your_words(hold):
    """The side claim: "I'll do £210 if you can keep it back for me." failed 'an offer over asking says why'."""
    messages = past(*[(f"Hi, I'll do £{p} if you can {hold}.", p - 10) for p in (210, 130, 90)])
    assert drafted(messages, "more") == ("ready", "template", f"Hi, I'll do £210 if you can {hold}.")


# ── v8-integration-11: one cheeky message's 😂 went on every offer ─────────────────────────────────────────────

LAUGH = past(("Hi mate, would you take £150? Cheeky I know 😂", 200))


def test_one_messages_emoji_isnt_a_habit_yet():
    assert drafted(LAUGH, "asking") == ("ready", "template", "Hi mate, I can pay £200 for it.")
    assert drafted(LAUGH, "more") == ("ready", "template", "Hi mate, I can pay £210 if you can hold it for me.")
    two = past(("Hi mate, would you take £150? Cheeky I know 😂", 200),
               ("Hi mate, would you take £90? Can collect today.", 110))
    assert drafted(two, "asking") == ("ready", "template", "Hi mate, I can pay £200.")
    assert style_card(LAUGH)["phrases"]["emoji"] is None  # an emoji, but not a habit yet ("" is none at all)


def test_an_emoji_that_only_came_with_a_cheeky_word_isnt_added_at_or_over_asking():
    cheeky = past(*[(f"Hi mate, would you take £{p}? Cheeky I know 😂", p + 40) for p in (150, 90, 60)])
    assert drafted(cheeky, "asking") == ("ready", "template", "Hi mate, I can pay £200.")
    # still yours under asking
    assert drafted(cheeky, "lower") == ("ready", "template", "Hi mate, would you take £170? Cheeky I know 😂")
    varied = past(("Hi mate, would you take £150? Cheeky I know 😂", 190),
                  ("Hi mate, would you take £90? Bit cheeky sorry 😂", 130),
                  ("Hi mate, would you take £60? Can collect today", 100))
    assert "😂" not in drafted(varied, "asking")[2]


def test_an_emoji_in_two_of_your_messages_is_yours():
    """The control: the same emoji every time is a habit, at the asking price too; three different ones aren't."""
    thumbs = past(*[(f"Hi mate, would you take £{p}? 👍", p + 40) for p in (150, 90, 60)])
    assert drafted(thumbs, "asking") == ("ready", "template", "Hi mate, I can pay £200. 👍")
    varied = past(("Hi, would you take £150? 😊", 180), ("Hi, would you take £90? 👍", 110),
                  ("Hi, would you take £60? 🙏", 80))
    assert drafted(varied, "asking") == ("ready", "template", "Hi, I can pay £200.")


def test_where_you_buy_an_emoji_thats_no_habit_there_yet_leaves_yours_for_all_your_messages():
    """😊 in 2 of your messages, one on Facebook and one on eBay: your emoji on Facebook is still 😊 (the sweep of
    26 Sep: one market's single emoji had read as "no emoji" there)."""
    messages = past(("Hi mate, would you take £150? Can collect today 😊", 180), ("Hi mate, would you take £90? Cheers", 110),
                    ("Hi mate, would you take £60? Can collect today.", 80)) + \
        [{**m, "id": f"e{n}"} for n, m in enumerate(past(("Hi mate, would you take £75? 😊", 90),
                                                         ("Hi mate, would you take £50?", 60), market="ebay"))]
    card = style_card(messages)
    assert card["by_market"]["in_person"]["emoji"] is None and card["phrases"]["emoji"] == "😊"
    assert for_market(card, "facebook")["phrases"]["emoji"] == "😊"
    assert phrasebook(past(("Hi, would you take £150?", 180), ("Hi, would you take £90?", 110)))["emoji"] == ""


# ── v8-integration-12: "Hi," for someone who never greets ────────────────────────────────────────────────────

NOGREET = past(("£150 cash? Can collect today.", 180), ("Would you do £90 for it? I'm local.", 110),
               ("Any chance of £250? Cash waiting.", 300))


def test_someone_who_never_greets_gets_no_greeting():
    assert drafted(NOGREET) == ("ready", "template", "Would you take £170 for it?")
    assert drafted(NOGREET, "asking") == ("ready", "template", "I can pay £200 for it.")
    lower_case = past(("£150 cash? can collect", 180), ("wud u do £90? im local", 110),
                      ("any chance of £60? cash ready", 80))
    assert drafted(lower_case) == ("ready", "template", "would you take £170 for it?")


def test_someone_who_greets_in_other_words_each_time_still_gets_hi():
    """Hi, Hiya, Hello: no one greeting is a habit, but they greet, so "Hi," as before (v8-integration-2 expects
    it)."""
    messages = past(("Hi, would you take £150?", 180), ("Hiya, would you take £90?", 110),
                    ("Hello, would you take £60?", 80))
    assert drafted(messages) == ("ready", "template", "Hi, would you take £170 for it?")
    assert not style_card(messages).get("no_greeting") and style_card(NOGREET)["no_greeting"]
