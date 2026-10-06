"""When and where, after the second red team (26 Sep): paying first however it's
worded, paying cash when you meet, a time said once without leaving words
behind, your own numbers still yours once a time is out, when you'd pay
before "mate", and the listing's place said back. Each with the finding's
own input and the verifiers' controls. No model runs: the AI is
tests/fakes.FakeModel, and writer="template" never asks one."""

import pytest

from flip import reader
from flip.checks import check_message_manner
from flip.message_drafter import draft_message, said_place, your_sentences
from flip.style import names_places, style_card
from flip.writer import collecting_from, paid_at, said_once, time_once
from tests.fakes import FakeModel

FACEBOOK = {"id": "x", "title": "iPhone 13 128GB", "asking_price": "200", "marketplace": "facebook",
            "description": "iPhone 13 128gb unlocked, fully wkg, bh 88%. Collection Leeds."}
EBAY = {**FACEBOOK, "marketplace": "ebay", "description": "iPhone 13 128gb unlocked, fully wkg, bh 88%."}
NOTHING_READ = {"flaws": [], "pickup": "", "no_offers": "", "read_by": "gemma3:4b"}
LOWER = (("150", "180"), ("90", "110"), ("60", "80"))  # (your offer, the asking price) under asking
OVER = (("300", "280"), ("130", "120"))  # ...and over it
AT_ASKING = (("200", "200"), ("150", "150"), ("90", "90"))


def card(*messages, market="facebook"):
    """Your style card from past messages, each (what you wrote, the listing's asking price)."""
    return style_card([{"my_message": text, "asking_price": asking, "marketplace": market, "listing_title": "iPhone 13"}
                       for text, asking in messages])


def drafted(listing, yours, kind, offer=None, reading=NOTHING_READ, ai=None, writer="template"):
    """(status, writer, message, every problem the checks found): the AI, if any, says the same each time it's asked."""
    local = FakeModel("gemma3:4b", *[{"message": ai}] * 4) if ai else None
    result = draft_message(listing, yours, local=local, kind=kind, offer=offer, reading=reading, writer=writer)
    return (result["status"], result["writer"], (result["answer"] or {}).get("message"),
            [p for attempt in result["attempts"] for p in attempt["problems"]])


def refused(found):
    return [f'the message offers to pay before collecting: "{found}"']


# ── tp4-pay-first-transfer-bypass: sending it, with the price said, is paying first too ──────────────

@pytest.mark.parametrize("message, found", [
    ("Hi, I can transfer £200 now.", "transfer £200 now"),
    ("Hi, I can send £200 over now.", "send £200 over now"),
    ("Hi, I'll transfer the £200 now.", "transfer the £200 now"),
    ("Hi, I can pay £200 immediately.", "pay £200 immediately"),
    ("Hi, I can pay immediately.", "pay immediately"),
    # the verifier's own probes
    ("Hi mate, I'll send you £200 now if you hold it.", "send you £200 now"),
    ("Hi, I can paypal you £200 now.", "paypal you £200 now"),
    ("hi can bank transfer £200 now if u hold it for me", "transfer £200 now"),
    ("Hi, can transfer 200 quid tonight", "transfer 200 quid tonight"),
    ("Hi, I can send the £200 straight away.", "send the £200 straight away"),
    ("Hi, happy to transfer £200 today to hold it.", "transfer £200 today"),
    ("Hi, I can ping £200 over now.", "ping £200 over now"),
    # ...and the controls, refused before and now
    ("Hi, I can transfer it now.", "transfer it now"), ("Hi, I can send the money now.", "send the money now"),
    ("Hi, I can pay £200 now.", "pay £200 now"),
])
def test_sending_or_paying_first_is_caught_with_the_price_said(message, found):
    assert check_message_manner(message, greeting=True) == refused(found)


@pytest.mark.parametrize("ai, found", [
    ("Hi, I can transfer £210 now if you can hold it for me.", "transfer £210 now"),
    ("Hi, I can send £210 over now if you can hold it for me.", "send £210 over now"),
    ("Hi, I can pay £210 immediately if you can hold it for me.", "pay £210 immediately"),
])
def test_the_ais_pay_first_draft_is_refused(ai, found):
    """It went out with code's "I can pay cash and come and collect it." after it, which says the opposite."""
    assert drafted(FACEBOOK, None, "more", 21000, ai=ai, writer="ai") == ("needs you", None, None, refused(found) * 2)


def test_your_own_transfer_now_habit_isnt_sent_on_facebook():
    yours = card(*((f"Hi mate, I can transfer £{p} now if you can hold it for me.", a) for p, a in (*OVER, ("90", "80"))))
    assert drafted(FACEBOOK, yours, "more", 21000) == ("needs you", None, None, refused("transfer £210 now"))


def test_on_ebay_paying_immediately_is_how_you_buy_but_sending_money_isnt():
    ebay = {"greeting": True, "pay_first": False, "cash": False}
    assert check_message_manner("Hi, I can pay £200 immediately.", **ebay) == []
    assert check_message_manner("Hi, I can pay immediately.", **ebay) == []
    assert check_message_manner("Hi, I can transfer £200 now.", **ebay) == refused("transfer £200 now")


# ── tp4-pay-first-cash-refused: paying cash when you meet isn't paying first ────────────────────────

@pytest.mark.parametrize("message", [
    "Hi, I can pay £200 straight away in cash when I collect.", "Hi, I'll pay £200 asap in cash when I pick it up.",
    "Hi, I can pay you £200 right away in cash when we meet.", "Hi, I can pay £200 straight away cash in hand.",
    "Hi, I'll pay £200 now, cash on collection.", "Hi, can pay £200 straight away, cash in hand.",
    "hi can pay 200 quid now cash", "Hi, I'll pay £200 asap - cash on collection.",
    "Hi, I can pay £200 right away after I've had a look.",
    # the verifier's: with the price, and without it (refused on main too, for the same one-word reading)
    "Hi, can pay £200 straight away in cash", "hi can pay £200 asap cash on collection",
    "Hi, I can pay £200 now, cash when I pick it up.", "Hi, I can pay straight away in cash.",
    "Hi, I can pay straight away in cash when I collect.", "Hi, I can pay now, cash on collection.",
    "Hi, can pay straight away cash in hand",
    # ...and what passed before and still does
    "Hi, I can pay £200 cash straight away.", "Hi, I can pay £200 straight away on collection.",
    "Hi, I'll pay you £200 right away when I see it.", "Hi, I can pay £200 straight away once I've seen it.",
])
def test_paying_now_in_cash_when_you_meet_isnt_paying_first(message):
    assert check_message_manner(message, greeting=True) == []


@pytest.mark.parametrize("message, found", [
    ("Hi, I'll pay £200 now and collect tonight.", "pay £200 now"),  # bare "collect" doesn't tie it to meeting
    ("Hi, I can pay £200 now so you can hold it.", "pay £200 now"),
    ("Hi, I can pay £200 now only if you hold it.", "pay £200 now"),  # "only" isn't "on"
    ("Hi, I can pay £200 now, or cash on collection.", "pay £200 now"),  # paying now is still offered
    ("Hi, I can pay £200 now, cash or PayPal.", "pay £200 now"),  # ...and with another way to pay after it
    ("Hi, I can pay £200 straight away in cash or by bank transfer.", "pay £200 straight away"),
])
def test_paying_first_is_still_refused_when_the_words_after_it_dont_tie_it_to_meeting(message, found):
    assert refused(found)[0] in check_message_manner(message, greeting=True)


@pytest.mark.parametrize("sentence", ["Hi, I can pay £{p} straight away in cash.",
                                      "Hi mate, can pay £{p} straight away cash in hand."])
def test_your_own_cash_straight_away_habit_is_sent(sentence):
    """Needs you since the first fixes; BASE and main sent it."""
    yours = card(*((sentence.format(p=p), a) for p, a in AT_ASKING))
    assert drafted(FACEBOOK, yours, "asking", 20000) == ("ready", "template", sentence.format(p="200"), [])


def test_the_ais_cash_when_you_collect_draft_is_sent():
    ai = "Hi, I can pay £200 straight away in cash when I collect."
    assert drafted(FACEBOOK, None, "asking", 20000, ai=ai, writer="ai") == ("ready", "gemma3:4b", ai, [])


# ── tp4-time-once-strands-words: a time comes out only with nothing left hanging ─────────────────────

def holds_with(hold, closing):
    """Lower offers that end with the closing, and over-asking ones that ask them to hold it till a time and end with
    it too (style.for_kind learns the closing for each kind of offer)."""
    return card(*((f"Hi mate, would you take £{p}? {closing}", a) for p, a in LOWER),
                *((f"Hi mate, I'll pay £{p} if you can hold it {hold}. {closing}", a) for p, a in OVER))


@pytest.mark.parametrize("hold, closing", [
    ("till tonight", "Can collect tonight latest."), ("till tomorrow", "Can pick up tmrw at the latest."),
    ("till the weekend", "Can collect over the weekend."), ("till the weekend", "Can collect anytime over the weekend."),
    ("till tomorrow", "Can collect as early as tomorrow."), ("till tonight", "Can collect up until tonight."),
    ("till later", "Can collect, speak later."), ("till tonight", "Can collect tonight too."),
    ("till tomorrow", "Can collect tomorrow at the latest."), ("till tonight", "Could collect tonight even."),
    ("till tonight", "Can collect tonight ideally."), ("till tonight", "Can collect tonight probably."),
])
def test_a_time_with_a_word_that_only_went_with_it_stays_as_you_wrote_it(hold, closing):
    """Never "Can collect over.", "Can collect latest.", "Can collect as early as.", "Can collect up.", "Can collect,
    speak.": the sentence as you wrote it (BASE dropped these whole or kept them)."""
    assert drafted(FACEBOOK, holds_with(hold, closing), "more", 21000) == \
        ("ready", "template", f"Hi mate, I'll pay £210 if you can hold it {hold}. {closing}", [])


@pytest.mark.parametrize("when, closing", [("tonight", "Can collect tonight latest."),
                                           ("this weekend", "Can collect over the weekend."),
                                           ("this weekend", "can collect anytime over the weekend"),
                                           ("tonight", "can pick up by tonight latest"),
                                           ("today", "Can collect today at the earliest.")])
def test_after_an_offer_that_pays_then_too(when, closing):
    yours = card(*((f"Hi mate, would you take £{p} cash {when}? {closing}", a) for p, a in LOWER))
    assert drafted(FACEBOOK, yours, "lower") == \
        ("ready", "template", f"Hi mate, would you take £170 cash {when}? {closing[0].upper()}{closing[1:]}", [])


@pytest.mark.parametrize("closing, come, said", [
    # the time still comes out where nothing hangs on it (the verifier's controls)
    ("Can collect today if poss.", "today", "Can collect if poss."),
    ("Can collect tonight, 10 mins away.", "tonight", "Can collect, 10 mins away."),
    ("Can pick up tonight after work.", "tonight", "Can pick up after work."),  # "pick up" is no "up until"
    ("Can pick up by tonight and pay cash.", "tonight", "Can pick up and pay cash."),
    ("Can collect tonight, speak soon.", "tonight", "Can collect, speak soon."),
    ("Can collect up until tonight.", "tonight", "Can collect up until tonight."),
    ("Can collect over the weekend.", "the weekend", "Can collect over the weekend."),
])
def test_time_once_on_its_own(closing, come, said):
    assert time_once(closing, {come}, set()) == said


# ── tp4-time-once-loses-own-sentence-exemption: your figures stay yours once the time is out ─────────

@pytest.mark.parametrize("closing, said", [
    ("Can collect tonight, 10 mins away.", "Can collect, 10 mins away."),
    ("Can collect tonight 100%.", "Can collect 100%."),
    ("Can collect tonight, 15 mins from you.", "Can collect, 15 mins from you."),
])
def test_your_closing_with_a_figure_is_sent_once_its_time_is_out(closing, said):
    """Needs you: "message has numbers that aren't in your inputs: 10", over asking and under it."""
    assert drafted(FACEBOOK, holds_with("till tonight", closing), "more", 21000) == \
        ("ready", "template", f"Hi mate, I'll pay £210 if you can hold it till tonight. {said}", [])
    lower = card(*((f"Hi mate, would you take £{p} cash tonight? {closing}", a) for p, a in LOWER))
    assert drafted(FACEBOOK, lower, "lower") == ("ready", "template", f"Hi mate, would you take £170 cash tonight? {said}", [])
    # the control: with no time in the offer your closing is sent word for word, as before
    plain = card(*((f"Hi mate, would you take £{p}? {closing}", a) for p, a in LOWER))
    assert drafted(FACEBOOK, plain, "lower") == ("ready", "template", f"Hi mate, would you take £170? {closing}", [])


def test_in_auto_no_ai_is_asked_for_it():
    """The verifier: auto asked the AI, whose copy said "tonight" twice."""
    lower = card(*((f"Hi mate, would you take £{p} cash tonight? Can collect tonight, 10 mins away.", a) for p, a in LOWER))
    model = FakeModel("gemma3:4b")
    result = draft_message(FACEBOOK, lower, local=model, kind="lower", reading=NOTHING_READ)
    assert (result["status"], result["writer"], model.asked) == ("ready", "template", [])


def test_your_sentences_include_them_as_the_writer_says_them():
    closing = "Can collect tonight, 10 mins away."
    assert said_once(closing) == ["Can collect, 10 mins away."]
    assert said_once("Can collect tonight latest.") == []  # never said without its time
    assert said_once("Can collect after 6pm.") == []  # no time to take out
    yours = card(*((f"Hi mate, would you take £{p}? {closing}", a) for p, a in LOWER))
    assert {"Can collect tonight, 10 mins away.", "Can collect, 10 mins away."} <= set(your_sentences(yours, 17000))
    # ...and with the listing's place put in, when your messages name places
    assert {"Can collect from Leeds LS6 tonight, 10 mins away.", "Can collect from Leeds LS6, 10 mins away."} <= \
        set(your_sentences(yours, 17000, "Leeds LS6"))


def test_a_figure_you_never_give_is_still_made_up():
    lower = card(*((f"Hi mate, would you take £{p} cash tonight? Can collect tonight, 10 mins away.", a) for p, a in LOWER))
    status, _, _, found = drafted(FACEBOOK, lower, "lower", ai="Hi mate, would you take £170 cash tonight? Can collect, "
                                                               "15 mins away.", writer="ai")
    assert status == "needs you" and "message has numbers that aren't in your inputs: 15" in found


def test_your_figure_is_yours_with_the_listings_place_in_too():
    """The same loss with the place put in (old: BASE and main refused it too)."""
    leeds = {**FACEBOOK, "description": "iPhone 13 128gb unlocked, fully wkg, bh 88%. Collection from Leeds LS6."}
    yours = card(*((f"Hi mate, would you take £{p}? Can collect tonight, 10 mins away.", a) for p, a in LOWER),
                 ("Hi mate, would you take £240? Can collect from Wakefield tonight.", "280"),
                 ("Hi mate, would you take £100? Can collect from Halifax tonight.", "130"))
    assert drafted(leeds, yours, "lower", reading={**NOTHING_READ, "pickup": "Leeds LS6"}) == \
        ("ready", "template", "Hi mate, would you take £170? Can collect from Leeds LS6 tonight, 10 mins away.", [])


# ── tp4-paid-at-after-tag: when you'd pay goes before "mate", "please" and "no problem" ─────────────

@pytest.mark.parametrize("offer, facebook, ebay", [
    ("Hi mate, I'll pay £{p} for it mate.", "Hi mate, I'll pay £200 for it today mate.",
     "Hi mate, I'll pay £200 for it straight away mate."),
    ("Hi, I can pay £{p} no problem.", "Hi, I can pay £200 today no problem.", "Hi, I can pay £200 straight away no problem."),
    ("Hi, I can pay the full £{p} no worries.", "Hi, I can pay the full £200 today no worries.",
     "Hi, I can pay the full £200 straight away no worries."),
    ("Hi, I'll pay £{p} for it please.", "Hi, I'll pay £200 for it today please.",
     "Hi, I'll pay £200 for it straight away please."),
])
def test_when_you_pay_goes_before_the_word_that_rounds_off_the_offer(offer, facebook, ebay):
    on_facebook = card(*((f"{offer.format(p=p)} Can pay today.", a) for p, a in AT_ASKING))
    assert drafted(FACEBOOK, on_facebook, "asking", 20000) == ("ready", "template", facebook, [])
    on_ebay = card(*((f"{offer.format(p=p)} Can pay straight away.", a) for p, a in AT_ASKING), market="ebay")
    assert drafted(EBAY, on_ebay, "asking", 20000) == ("ready", "template", ebay, [])


@pytest.mark.parametrize("sentence, said", [
    ("I'll pay £[OFFER] for it mate.", "I'll pay £[OFFER] for it today mate."),
    ("hi can pay £[OFFER] no probs", "hi can pay £[OFFER] today no probs"),
    ("I'll pay £[OFFER] mate if you can hold it for me.", "I'll pay £[OFFER] today mate if you can hold it for me."),
    ("I'll pay £[OFFER] for it ta x", "I'll pay £[OFFER] for it today ta x"),
    ("Could I pay £[OFFER] please?", "Could I pay £[OFFER] today please?"),
    # someone the offer is for isn't a word that rounds it off
    ("I'll pay £[OFFER] for my mate.", "I'll pay £[OFFER] for my mate today."),
    ("I'll pay £[OFFER] for a mate.", "I'll pay £[OFFER] for a mate today."),
    # ...and the first fixes' own cases
    ("I'll pay £[OFFER] for it, mate.", "I'll pay £[OFFER] for it today, mate."),
    ("I'll pay £[OFFER] cash if you can hold it for me.", "I'll pay £[OFFER] cash today if you can hold it for me."),
])
def test_paid_at_reads_the_word_that_rounds_off_the_offer(sentence, said):
    assert paid_at(sentence, "today") == said


# ── tp4-clause-end-shadowed and time-place-02: a closing that already says where stays ──────────────

@pytest.mark.parametrize("closing, said", [
    ("Can collect tonight… at yours?", "Can collect tonight… at yours?"),
    ("Can collect tonight - at yours if ok?", "Can collect tonight - at yours if ok?"),
    ("Can collect tonight: at yours or a meeting point?", "Can collect tonight: at yours or a meeting point?"),
    ("can collect 2nite - at urs if ok?", "can collect 2nite - at urs if ok?"),
    ("Can collect tomorrow… near you?", "Can collect tomorrow… near you?"),
    # where comes in another clause: the place goes in, as in g5's own copy
    ("Can collect later then meet at the station.", "Can collect from Leeds LS6 later then meet at the station."),
])
def test_collecting_from_reads_where_after_a_dash_dots_or_colon(closing, said):
    assert collecting_from(closing, "Leeds LS6") == said


BRADFORD = {**FACEBOOK, "description": "iPhone 13 128gb unlocked, fully wkg, bh 88%. Collection from Bradford BD7."}
NAMES_TOWNS = (("Hi mate, would you take £240? Can collect from Wakefield tonight.", "280"),
               ("Hi mate, would you take £100? Can collect from Halifax tonight.", "130"))


def test_a_closing_that_says_where_after_dots_is_sent_as_you_wrote_it():
    yours = card(*((f"Hi mate, would you take £{p}? Can collect tonight… at yours?", a) for p, a in LOWER), *NAMES_TOWNS)
    assert drafted(BRADFORD, yours, "lower", reading={**NOTHING_READ, "pickup": "Bradford BD7"}) == \
        ("ready", "template", "Hi mate, would you take £170? Can collect tonight… at yours?", [])


@pytest.mark.parametrize("closing", ["Can collect tonight - in Leeds if ok?", "Can collect today: in Leeds or Bradford?"])
def test_a_town_after_a_dash_is_refused_as_one_without_it_is(closing):
    """The verifier: sent as "...Can collect tonight - in Leeds if ok?" on a Bradford BD7 listing, a second place the
    listing doesn't give, where "Can collect in Leeds today." is refused (time-place-02)."""
    yours = card(*((f"Hi mate, would you take £{p}? {closing}", a) for p, a in LOWER), *NAMES_TOWNS)
    assert drafted(BRADFORD, yours, "lower", reading={**NOTHING_READ, "pickup": "Bradford BD7"}) == \
        ("needs you", None, None, ["the message says it'll collect from a place the listing doesn't: Leeds"])


@pytest.mark.parametrize("closing, names", [
    ("Can collect tonight - in Leeds if ok?", True), ("Can collect Saturday, at the Trafford Centre.", True),
    ("Can collect tonight… at yours?", False), ("can collect 2nite - at urs if ok?", False),
    ("Can collect today, in person.", False), ("Can collect today - in an hour", False), ("Can collect today, at lunch", False),
])
def test_a_place_after_a_dash_counts_as_naming_one_and_everyday_words_still_dont(closing, names):
    assert names_places([closing, closing]) is names


# ── tp4-places-dropped: the listing's place said back, never the seller's door ──────────────────────

@pytest.mark.parametrize("line, said", [
    ("Collection from Liverpool Street station.", "from Liverpool Street station"),
    ("Collection Old Street, London.", "from Old Street"),
    ("Pick up from Brick Lane E1.", "from Brick Lane E1"),
    ("Collection from Kew Gardens.", "from Kew Gardens"),
    ("Collection near Turnpike Lane station.", "from Turnpike Lane station"),
    ("Collection Gloucester Road, Bristol.", "from Gloucester Road"),
    ("Collection from Ladbroke Grove.", "from Ladbroke Grove"),
    ("Collection Example Lane IG1.", "from Example Lane IG1"),
    # a door, or a street with its full postcode, still isn't said back (time-place-03)
    ("Collection from Example Lane IG1 2AC.", "from IG1"),
    ("Collection from 78, Example Lane, Ilford.", ""),
    ("Collection from 14 Baker Street", ""),
])
def test_alertflips_message_says_the_listings_place_back(line, said):
    description = f"iPhone 13 128gb unlocked, fully wkg, bh 88%. {line}"
    pickup = reader.place(line)
    assert pickup and reader.in_listing(pickup, description)
    result = drafted({**FACEBOOK, "description": description}, None, "lower", reading={**NOTHING_READ, "pickup": pickup})
    assert result == ("ready", "template", f"Hi, would you take £170 cash for it? I can come and collect{' ' * bool(said)}"
                                           f"{said}.", [])


@pytest.mark.parametrize("pickup, said", [
    ("Edgware Road Station", "Edgware Road Station"), ("Ecclesall Road Sheffield S11", "Ecclesall Road Sheffield S11"),
    ("Baker Street", "Baker Street"), ("Baker Street NW1 6XE", "NW1"), ("78 Example Lane", ""), ("Flat 2", ""),
])
def test_said_place_leaves_out_only_the_door(pickup, said):
    assert said_place(pickup) == said


@pytest.mark.parametrize("quote, found", [
    ("collection from seven sisters", "Seven Sisters"), ("pick up from nine elms", "Nine Elms"),
    ("collection from four oaks", "Four Oaks"), ("collection from three bridges", "Three Bridges"),
    ("collection from three bridges crawley", "Three Bridges Crawley"),
    # a number word alone, or with a time, is when: never a place
    ("collection from six", ""), ("collection from six thirty", ""), ("collection from six onwards", ""),
    ("collection from ten til six", ""), ("collection from six ish", ""),
    # ...and the first fixes' own cases
    ("collection in public", ""), ("collection from here", ""), ("collection at earliest convenience", ""),
    ("collection from rotherham", "Rotherham"), ("Collection from Seven Sisters", "Seven Sisters"),
])
def test_a_lower_case_place_may_start_with_a_number_word(quote, found):
    assert reader.place(quote) == found


def test_a_lower_case_number_word_place_is_said_back():
    description = "iphone 13 128gb unlocked fully wkg bh 88%. collection from seven sisters"
    pickup = reader.reading_from({"flaws": [], "pickup": "collection from seven sisters", "no_offers": ""}, description,
                                 "gemma3:4b")["pickup"]
    assert drafted({**FACEBOOK, "description": description}, None, "lower", reading={**NOTHING_READ, "pickup": pickup}) == \
        ("ready", "template", "Hi, would you take £170 cash for it? I can come and collect from Seven Sisters.", [])
