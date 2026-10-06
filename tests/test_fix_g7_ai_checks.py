"""The checks written for the AI's slips, after the 26 Sep red team (v8-integration-6, -7, -9 and -10): how a lower
offer is made (check_ai_manner), the AI's own words apart from yours (META_TALK, ROLE_MIX), and your own numbers
(check_no_invented_numbers), each with the finding's own input. No model runs: the AI is tests/fakes.FakeModel."""

import pytest

from flip.checks import check_no_invented_numbers, clock_times
from flip.message_drafter import check_ai_manner, draft_message, your_sentences
from flip.style import asks_lower, describe, style_card
from tests.fakes import FakeModel

PLAIN = {"id": "x", "title": "iPhone 13 128GB Midnight", "description": "Good condition, unlocked, comes with box.",
         "asking_price": "200", "marketplace": "facebook"}


def past(*rows):
    """Past Facebook messages: (message, the listing's asking price in pounds)."""
    return [{"id": f"m{n}", "my_message": text, "asking_price": str(asking), "marketplace": "facebook",
             "listing_title": "iPhone 12"} for n, (text, asking) in enumerate(rows)]


def draft(messages, ai=None, listing=PLAIN, **kwargs):
    """A lower offer of £170 on the £200 listing; the AI, if any, hands back the same reply every time it's asked."""
    replies = [{"message": ai}] * 4 if ai else []
    local = FakeModel("gemma3:4b", *replies) if ai else None
    api = FakeModel("claude-haiku-5-5", *replies) if ai else None
    result = draft_message(listing, style_card(messages) if messages else None, None, local, api, kind="lower",
                           **kwargs)
    return result


def message(result):
    return (result.get("answer") or {}).get("message")


def problems(result):
    return [problem for attempt in result["attempts"] for problem in attempt["problems"]]


# someone whose lower offers are asked, the same way each time
ASKER = past(("Hi mate, would you take £150 cash? Can collect today.", 180),
             ("Hi mate, would you take £90 cash? Can collect tonight.", 110),
             ("Hi mate, would you take £250 cash? Can collect today.", 300))
# a chatty writer: 5 messages, no sentence repeats, 4 of the 5 lower offers asked
CHATTY = [{"id": f"c{n}", "marketplace": "facebook", **m} for n, m in enumerate([
    {"my_message": "Hiya! Lovely phone this, my daughter's been after one for ages. Would you consider £150? I can come "
                   "over this evening if that suits 😊", "asking_price": "180", "listing_title": "iPhone 12"},
    {"my_message": "Hello there, hope you're well. I've been looking for one of these for a while now and yours looks "
                   "great. Would £320 be any good? Happy to come to you.", "asking_price": "380", "listing_title": "iPad Air"},
    {"my_message": "Hey, is the switch still going? I'd happily do £200 cash, I'm only 10 mins away and could grab it "
                   "after work.", "asking_price": "240", "listing_title": "Nintendo Switch OLED"},
    {"my_message": "Morning! Any chance you'd let it go for £90? It's for my lad's birthday so would need it by Saturday "
                   "ideally. Thanks so much", "asking_price": "120", "listing_title": "AirPods Pro"},
    {"my_message": "Hi, really interested in this. I know it's a bit under but could you do £400? Cash ready and I can "
                   "be there whenever.", "asking_price": "470", "listing_title": "MacBook Air M1"}])]


# ── v8-integration-6: what check_ai_manner is for ───────────────────────────

def test_a_chatty_writer_with_no_offer_habit_still_has_lower_offers_asked():
    """asks_lower came from the offer habit alone, and this writer has none: "the full £170" on a £200 listing went."""
    card = style_card(CHATTY)
    assert (card["phrases"]["offer"], card["phrases"]["offer_lower"], card["asks_lower"]) == (None, None, True)
    full = draft(CHATTY, "Hi, I'll pay the full £170 cash. Can come over this evening.", writer="ai")
    assert full["status"] == "needs you"
    assert 'a lower offer is said, not asked: "Hi, I\'ll pay the full £170 cash." (under asking it\'s a question)' in \
        problems(full)
    assert 'a lower offer is called the full price: "the full £170" (it\'s under what they ask)' in problems(full)
    # said, then a question that isn't about the offer (the hold itself is the hold rule's)
    hold = draft(CHATTY, "Hi, I can do £170 cash. Could you hold it for me till Saturday?", writer="ai")
    assert hold["status"] == "needs you"
    assert 'a lower offer is said, not asked: "Hi, I can do £170 cash." (under asking it\'s a question)' in problems(hold)


def test_the_offer_is_found_however_the_price_is_written():
    """Only the string "£170" was looked for, so "170 quid" was never read as the offer."""
    quid = draft(ASKER, "Hi mate, I'll give you 170 quid cash for it. Can collect today.", writer="ai")
    assert quid["status"] == "needs you"
    assert 'a lower offer is said, not asked: "Hi mate, I\'ll give you 170 quid cash for it." (under asking it\'s a ' \
           'question)' in problems(quid)
    # the control the verifier ran: the same said with "£170" was already refused
    pounds = draft(ASKER, "Hi mate, I'll give you £170 cash for it. Can collect today.", writer="ai")
    assert pounds["status"] == "needs you"
    assert check_ai_manner("Hi mate, I can do £170.00 cash. Can collect today.", "lower", 17000, False) == \
        ['a lower offer is said, not asked: "Hi mate, I can do £170.00 cash." (under asking it\'s a question)']
    # "£1700" isn't "£170"
    assert check_ai_manner("Hi mate, I can do £1700 cash.", "lower", 17000, False) == []


def test_the_seller_is_never_asked_to_pick_it_up_however_its_worded():
    be_able = draft(ASKER, "Hi mate, would you take £170 cash? Would you be able to pick it up?", writer="ai")
    assert be_able["status"] == "needs you"
    assert 'the message mixes up who does what: "Would you be able to pick it up" (you collect and you pay)' in \
        problems(be_able)
    for wording in ("Could you possibly collect?", "Can you collect?", "cud u collect?", "Are you able to pick it up?"):
        assert any("mixes up who does what" in p for p in
                   check_ai_manner(f"Hi mate, would you take £170 cash? {wording}", "lower", 17000, False)), wording
    # asking to come yourself is fine
    for fine in ("Would you be happy for me to collect today?", "Would you be able to hold it till Saturday?",
                 "Can I collect today?"):
        assert not any("mixes up" in p for p in
                       check_ai_manner(f"Hi mate, would you take £170 cash? {fine}", "lower", 17000, False)), fine


def test_a_lower_offer_called_the_full_price_is_refused():
    assert check_ai_manner("Hi, would you take the full £170?", "lower", 17000, False) == \
        ['a lower offer is called the full price: "the full £170" (it\'s under what they ask)']
    assert check_ai_manner("Hi, would you take the asking price of 170 quid?", "lower", 17000, False) == \
        ['a lower offer is called the full price: "the asking price of 170" (it\'s under what they ask)']
    # not what "full" means elsewhere, nor the asking price said back, nor at the asking price itself
    for fine in ("Hi, would you take £170 in full?", "I know you're asking £200 but would you take £170?",
                 "Hi, would you take £170, paid in full on collection?"):
        assert check_ai_manner(fine, "lower", 17000, False) == [], fine
    assert check_ai_manner("Hi, I'll pay the full £200.", "asking", 20000, False) == []


def test_whether_you_ask_your_lower_offers_is_read_from_your_messages_under_asking():
    """Asked in half or more of them; with fewer than 2, asked (AlertFlip's way); never from paying asking."""
    assert asks_lower(ASKER) is True
    sayer = past(("Hi, I can do £150 cash. Can collect today.", 180), ("Hi, I can do £90 cash for it. Can collect.", 110),
                 ("Hi, I can offer £250. Can collect tonight.", 300))
    assert asks_lower(sayer) is False
    # someone who writes "I can do £170 cash" may say it
    said = draft(sayer, "Hi, I can do £170 cash. Can collect today.", writer="ai")
    assert (said["status"], message(said)) == ("ready", "Hi, I can do £170 cash. Can collect today.")
    # 3 messages paying asking say nothing of how you ask for less: a lower offer is asked
    payer = past(("Hi, I'll pay £180 cash.", 180), ("Hi, I'll pay £110 cash.", 110), ("Hi, I'll pay £300 cash.", 300))
    assert asks_lower(payer) is None and style_card(payer)["phrases"]["offer"] == "Hi, I'll pay £[OFFER] cash."
    assert draft(payer, "Hi, I'll pay £170 cash. Can collect today.", writer="ai")["status"] == "needs you"
    assert asks_lower(past(("Hi, I can do £150 cash.", 180))) is None  # one message is no habit
    # wud u, with no question mark, asks
    assert asks_lower(past(("hi wud u take £150 cash", 180), ("hi wud u do £90", 110))) is True


# ── v8-integration-7: a lower offer said, then asked about ──────────────────

@pytest.mark.parametrize("text", [
    "Hi mate, I can do £170 cash. Would you be happy with that? Can collect today.",
    "Hi mate, I can do £170 cash. Would you accept that? Can collect today.",
    "Hi mate, I could do £170 cash. Is that something you'd consider? Can collect today.",
    "Hi mate, I can do £170 cash, let me know if that works. Can collect today.",
    "Hi mate, I can do £170 cash. I can collect today. Would that work for you?",
    # the controls that passed already
    "Hi mate, I can do £170 cash. Would that work? Can collect today.",
    "Hi mate, I could do £170 cash if that works? Can collect today.",
])
def test_a_lower_offer_said_and_then_asked_about_passes(text):
    result = draft(ASKER, text, writer="ai")
    assert (result["status"], result["writer"], message(result)) == ("ready", "gemma3:4b", text)


@pytest.mark.parametrize("text", [
    "Hi mate, I can do £170 cash. What do you think? Can collect today.",
    "Hi mate, I can do £170 cash. Are you happy with that? Can collect today.",
    "Hi mate, I can do £170 cash. Let me know if you're interested.",
    "Hi mate, I can do £170 cash if you're happy with that. Can collect today.",
    "hi mate, i can do £170 cash, lmk if thats ok",
    "Hi mate, I can do £170 cash. Is that something you’d consider?",
])
def test_other_ways_of_asking_about_it_pass_too(text):
    assert check_ai_manner(text, "lower", 17000, False) == []


@pytest.mark.parametrize("text", [
    "Hi mate, I can do £170 cash. Can collect today.",
    "Hi mate, I can do £170 cash. Is it still available?",
    "Hi mate, I can do £170 cash. Does it come with a charger?",
    "Hi mate, I can do £170 cash. Is it ok if I collect tomorrow?",
    "Hi mate, I can do £170 cash. Hope that's ok.",
    "Hi mate, I can do £170 cash. Let me know if it's still available.",
    "Hi mate, I can do £170 cash. Is the battery any good?",
    "Hi mate, I can do £170 cash. Does it work with EE?",
    "Hi mate, I can do £170 cash. Would it be possible to collect today?",
])
def test_a_question_about_something_else_doesnt_ask_the_offer(text):
    assert check_ai_manner(text, "lower", 17000, False) == \
        ['a lower offer is said, not asked: "Hi mate, I can do £170 cash." (under asking it\'s a question)']


# ── v8-integration-9: your own sentences aren't the AI's slips ──────────────

DESCRIBED = past(("Hi, would you take £150? Is it all as described in the ad?", 180),
                 ("Hi, would you take £90? Is it all as described in the ad?", 110),
                 ("Hi, would you take £250? Is it all as described in the ad?", 300))
CASH_IN_HAND = past(("hi wud u take £150? can collect cash in hand", 180), ("hi wud u take £90? can collect cash in hand", 110),
                    ("hi wud u take £250? can collect cash in hand", 300))


def test_your_own_question_and_closing_are_written_as_you_write_them():
    described = draft(DESCRIBED)
    assert (described["status"], described["writer"], message(described)) == \
        ("ready", "template", "Hi, would you take £170? Is it all as described in the ad?")
    cash = draft(CASH_IN_HAND)
    assert (cash["status"], cash["writer"], message(cash)) == \
        ("ready", "template", "hi wud u take £170? can collect cash in hand")
    # the AI copying your question is yours too (it was refused 4 times)
    copied = draft(DESCRIBED, "Hi, would you take £170? Is it all as described in the ad?", writer="ai")
    assert (copied["status"], copied["writer"]) == ("ready", "gemma3:4b")
    assert "Is it all as described in the ad?" in your_sentences(style_card(DESCRIBED), 17000)


def test_the_ais_own_slips_are_still_refused():
    for text, said in (("Hi mate, would you take £170 cash? As noted in the listing, can collect today.",
                        '"As noted in the listing"'),
                       ("Hi mate, would you take £170 cash? Cash and collecting is arranged separately.",
                        '"is arranged separately"')):
        result = draft(ASKER, text, writer="ai")
        assert f"the message talks about the listing or itself, not to the seller: {said}" in problems(result)
    collect_cash = draft(ASKER, "Hi mate, would you take £170 cash? I'll collect cash.", writer="ai")
    assert 'the message mixes up who does what: "collect cash" (you collect and you pay)' in problems(collect_cash)
    # with no past messages nothing is yours: the checks read every word
    assert any("talks about the listing" in p for p in problems(
        draft(None, "Hi, would you take £170 for it? As noted in the listing.", writer="ai")))


def test_asking_the_seller_whether_its_as_described_is_to_them():
    """The AI's own question passes as yours does; saying it about the listing doesn't."""
    asks = draft(ASKER, "Hi mate, would you take £170 cash? Is everything as described in the advert?", writer="ai")
    assert asks["status"] == "ready"
    says = draft(ASKER, "Hi mate, would you take £170 cash? It's as described in the listing so can collect today.",
                 writer="ai")
    assert any("talks about the listing" in p for p in problems(says))
    # cash in hand is how you pay: the AI writing it is fine too, with or without the comma
    for text in ("Hi mate, would you take £170 cash? Can collect cash in hand today.",
                 "Hi mate, would you take £170 cash? Can collect, cash in hand."):
        assert draft(ASKER, text, writer="ai")["status"] == "ready", text


# ── v8-integration-10: a clock time in your own closing ─────────────────────

TIMED = past(("Hi, would you take £150? Can collect after 6pm.", 180), ("Hi, would you take £90? Can collect after 6pm.", 110),
             ("Hi, would you take £250? Can collect after 6pm.", 300))


def test_your_closing_with_a_clock_time_is_sent():
    result = draft(TIMED)
    assert (result["status"], result["writer"], message(result)) == \
        ("ready", "template", "Hi, would you take £170? Can collect after 6pm.")
    for closing in ("Can collect any time after 6.", "Can collect before 9 tomorrow.", "Can collect at 7:30 tonight.",
                    "Only 10 mins away."):
        mine = past(*[(f"Hi, would you take £{p}? {closing}", a) for p, a in ((150, 180), (90, 110), (250, 300))])
        assert message(draft(mine)) == f"Hi, would you take £170? {closing}", closing
    # the template puts the listing's place in: no longer word for word, but the time is still yours
    placer = TIMED + past(("Hi, would you take £60? Can collect from Leeds.", 80),
                          ("Hi, would you take £70? Can collect from Bradford.", 90))
    placed = draft(placer, listing={**PLAIN, "description": "Collection from Wakefield. Good condition."},
                   reading={"flaws": [], "pickup": "Wakefield", "no_offers": "", "read_by": "gemma3:4b"})
    assert message(placed) == "Hi, would you take £170? Can collect from Wakefield after 6pm."


def test_the_ai_may_give_your_time_but_never_make_one_up():
    for text in ("Hi, would you take £170? Can collect after 6pm.", "Hi, would you take £170? I can collect after 6pm today.",
                 "Hi, would you take £170? Can pick it up after 6 tonight."):
        result = draft(TIMED, text, writer="ai")
        assert (result["status"], message(result)) == ("ready", text)
    for text, number in (("Hi, would you take £170? Can collect after 7pm.", "7"),  # not your time
                         ("Hi, would you take £170? I finish work at 6pm.", "6"),  # not about collecting
                         ("Hi, would you take £170? Can collect, I have 6 cases for it.", "6")):  # a count, not a time
        assert f"message has numbers that aren't in your inputs: {number}" in problems(draft(TIMED, text, writer="ai"))
    # someone who never gives a time
    nobody = draft(ASKER, "Hi mate, would you take £170 cash? Can collect after 6pm.", writer="ai")
    assert "message has numbers that aren't in your inputs: 6" in problems(nobody)


def test_your_own_numbers_count_only_in_your_own_sentences():
    own = ["Can collect after 6pm.", "Only 10 mins away."]
    assert check_no_invented_numbers("message", "Would you take £170? Only 10 mins away.", "£170", own) == []
    assert check_no_invented_numbers("message", "Would you take £170? I'm 10 minutes away.", "£170", own) == \
        ["message has numbers that aren't in your inputs: 10"]
    # no sentences of yours: as before
    assert check_no_invented_numbers("message", "Would you take £170? Can collect after 6pm.", "£170") == \
        ["message has numbers that aren't in your inputs: 6"]
    assert [clock for _, clock in clock_times("after 6pm, half 6, at 7:30, 6.30pm, 5-7pm, between 5 and 7")] == \
        [(6, 0), (6, 30), (7, 30), (6, 30), (5, 0), (7, 0), (5, 0), (7, 0)]
    assert clock_times("in 10 mins, 2 days, 6 cases") == []
    # cut into sentences as your phrasebook is: "£170?😊 Only 10 mins away." is two
    assert check_no_invented_numbers("message", "Would you take £170?😊 Only 10 mins away.", "£170",
                                     ["Would you take £170?😊", "Only 10 mins away."]) == []


def test_every_sentence_of_your_phrasebook_is_yours():
    """A closing learned for one kind of offer too, whatever its slot is called; not the emoji."""
    card = {"phrases": {"opener": "", "offer": "Hi, would you take £[OFFER]?", "closing_lower": "Can collect after 6pm.",
                        "closing": None, "emoji": "😊"}}
    assert your_sentences(card, 17000) == ["Hi, would you take £170?", "Can collect after 6pm."]
    assert your_sentences(None, 17000) == [] and your_sentences({}, 17000) == []


def test_the_ai_isnt_told_to_end_with_what_the_checks_refuse():
    assert 'Usually ends with "Can collect after 6pm."' in describe(style_card(TIMED))
    for closing in ("I'm only 5 mins away.", "It's for my son.", "Text me on 07700900123.", "Can collect at 6 or 7.",
                    "As you’ve said, can collect today."):
        card = style_card(past(*[(f"Hi, would you take £{p}? {closing}", a) for p, a in ((150, 180), (90, 110), (250, 300))]))
        assert card["phrases"]["closing"] == closing
        assert not any(line.startswith("Usually ends with") for line in describe(card)), closing
    # ...and only the sentence the checks refuse goes
    card = style_card(past(*[(f"Hi, would you take £{p}? Can collect today. It's for my son.", a)
                             for p, a in ((150, 180), (90, 110), (250, 300))]))
    assert 'Usually ends with "Can collect today."' in describe(card)
