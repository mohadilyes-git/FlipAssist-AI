"""The closing's time and paying, each said once and where you'd say it (the
third red team, 26 Sep: time-place-01, 04, 05, 06 and 11, v8-integration-4).
Your own sentences only: writer="template" never asks a model."""

import re

import pytest

from flip.checks import check_message_manner
from flip.message_drafter import draft_message
from flip.style import TIMES, style_card
from flip.writer import paid_at, time_of, times_in, write_offer
from tests.fakes import FakeModel

FACEBOOK = {"id": "x", "title": "iPhone 13 128GB", "asking_price": "200", "marketplace": "facebook",
            "description": "iPhone 13 128gb unlocked, fully wkg, bh 88%. Collection Leeds."}
EBAY = {**FACEBOOK, "marketplace": "ebay", "description": "iPhone 13 128gb unlocked, fully wkg, bh 88%."}
NOTHING_READ = {"flaws": [], "pickup": "", "no_offers": "", "read_by": "gemma3:4b"}
LOWER = (("150", "180"), ("90", "110"), ("60", "80"))  # (your offer, the asking price) under asking


def card(*messages, market="facebook"):
    """Your style card from past messages, each (what you wrote, the listing's asking price[, where])."""
    return style_card([{"my_message": m[0], "asking_price": m[1], "marketplace": m[2] if len(m) > 2 else market,
                        "listing_title": "iPhone 13"} for m in messages])


def drafted(listing, yours, kind, offer=None, reading=NOTHING_READ, **kwargs):
    """The message your own sentences write, and every problem the checks found in it."""
    result = draft_message(listing, yours, kind=kind, offer=offer, reading=reading, writer="template", **kwargs)
    return (result["answer"] or {}).get("message"), [p for a in result["attempts"] for p in a["problems"]]


def holds_with(hold, closing):
    """Lower offers that end with the closing, and over-asking ones that ask them to hold it till a time and end with
    it too: the closing is learned for each kind of offer (style.for_kind), so an over-asking draft ends the way your
    over-asking messages do."""
    return card(*((f"Hi, would you take £{p}? {closing}", a) for p, a in LOWER),
                *((f"Hi, I'll pay £{p} if you can hold it {hold}. {closing}", a)
                  for p, a in (("300", "280"), ("130", "120"))))


# ── time-place-01: when you'd pay goes in the offer, after "cash", and never paying first in person ─────

def test_a_time_to_pay_goes_at_the_end_of_the_offers_main_clause():
    """It went straight after the price: "I'll pay £210 today cash if you can hold it for me."."""
    yours = card(("Hi mate, I'll pay £300 cash if you can hold it for me. Can pay today.", "280"),
                 ("Hi mate, I'll pay £130 cash if you can hold it for me. Can pay today.", "120"),
                 ("Hi mate, would you take £150 cash? Can pay today.", "180"))
    assert drafted(FACEBOOK, yours, "more", 21000) == \
        ("Hi mate, I'll pay £210 cash today if you can hold it for me.", [])


def test_a_time_paying_puts_in_the_offer_is_said_once():
    """"Hi mate, I can pay £200 today cash. Can collect today.": the closing's collecting stays, its time goes."""
    yours = card(*((f"Hi mate, I can pay £{p} cash. Can pay today. Can collect today.", p)
                   for p in ("200", "150", "90")))
    assert drafted(FACEBOOK, yours, "asking", 20000) == ("Hi mate, I can pay £200 cash today. Can collect.", [])


@pytest.mark.parametrize("offer, closing, message", [
    ("I'll pay £{p} for it.", "Can pay now.", "Hi mate, I'll pay £200 for it."),
    ("I can pay £{p} cash.", "Can pay straight away.", "Hi mate, I can pay £200 cash."),  # the verifier's probe
])
def test_paying_first_never_goes_into_the_offer_where_you_meet_the_seller(offer, closing, message):
    """On Facebook "Can pay now." became "I'll pay £200 now for it.", which got past the pay-first check. Paying first
    is never said where you meet the seller: it was kept for the check to refuse, but since 14 Oct the template is the
    only writer, so that was no message at all (14 Oct hunt). Now it's left out, and the rest is sent."""
    yours = card(*((f"Hi mate, {offer.format(p=p)} {closing}", p) for p in ("200", "150", "90")))
    assert drafted(FACEBOOK, yours, "asking", 20000) == (message, [])


def test_a_lower_offer_never_pays_first_where_you_meet_the_seller():
    """The verifier's control: no "I'll pay" in the offer, so nothing was ever moved; the pay-first sentence is left
    out (it was refused, so no message, until the 14 Oct hunt)."""
    yours = card(*((f"Hi mate, would you take £{p}? Can pay now.", a) for p, a in LOWER))
    assert drafted(FACEBOOK, yours, "lower") == ("Hi mate, would you take £170?", [])


@pytest.mark.parametrize("closing, message", [
    ("Can pay straight away.", "Hi mate, I'll pay £200 for it straight away."),
    ("Can pay now.", "Hi mate, I'll pay £200 for it now."),
])
def test_on_ebay_paying_straight_away_still_goes_in_the_offer(closing, message):
    """There it's how you buy (pay_first=False), so it's said once, at the end of the offer's main clause."""
    yours = card(*((f"Hi mate, I'll pay £{p} for it. {closing}", p) for p in ("200", "150", "90")), market="ebay")
    assert drafted(EBAY, yours, "asking", 20000) == (message, [])


@pytest.mark.parametrize("closing, message", [
    ("Can pay tonight.", "Hi mate, I'll pay £200 for it tonight."),  # every time style.TIMES knows, not only today
    ("I'll pay today.", "Hi mate, I'll pay £200 for it today."),
    ("Happy to pay today.", "Hi mate, I'll pay £200 for it today."),
    ("can pay 2day", "Hi mate, I'll pay £200 for it 2day."),
    ("Can pay today x", "Hi mate, I'll pay £200 for it today. x"),  # its own sign-off stays, a kiss in lower case
    ("Can pay today 👍", "Hi mate, I'll pay £200 for it today. 👍"),
    ("Can collect today. Can pay today.", "Hi mate, I'll pay £200 for it today. Can collect."),
])
def test_when_you_pay_is_moved_into_the_offer_however_you_say_it(closing, message):
    yours = card(*((f"Hi mate, I'll pay £{p} for it. {closing}", p) for p in ("200", "150", "90")))
    assert drafted(FACEBOOK, yours, "asking", 20000) == (message, [])


@pytest.mark.parametrize("sentence, said", [
    ("I'll pay £[OFFER] cash if you can hold it for me.", "I'll pay £[OFFER] cash today if you can hold it for me."),
    ("I can pay £[OFFER] cash.", "I can pay £[OFFER] cash today."),
    ("I'll pay £[OFFER] for it 😊", "I'll pay £[OFFER] for it today 😊"),
    ("I can pay £[OFFER] cash, as it's in excellent condition.",
     "I can pay £[OFFER] cash today, as it's in excellent condition."),
    ("I'll pay the full [OFFER] quid and can come and collect.",
     "I'll pay the full [OFFER] quid today and can come and collect."),
    ("No price here.", "No price here."),
])
def test_when_you_pay_goes_before_the_offers_condition_or_full_stop(sentence, said):
    assert paid_at(sentence, "today") == said


@pytest.mark.parametrize("message, found", [
    ("Hi, I can pay £200 now.", "pay £200 now"),  # the verifier: an AI's, which passed on main too
    ("Hi, I can pay £200 now if you can hold it.", "pay £200 now"),
    ("Hi mate, I'll pay £200 now for it.", "pay £200 now"),  # the template's, before this fix
    ("Hi mate, I can pay £200 straight away for it.", "pay £200 straight away"),
    ("Hi, I'll pay you the full £200 for it right away.", "pay you the full £200 for it right away"),
    ("Hi, I can pay £1,200.00 asap.", "pay £1,200.00 asap"),
    ("Hi, I can pay 200 quid now.", "pay 200 quid now"),
    ("Hi, I can pay right now.", "pay right now"),
])
def test_paying_first_is_caught_with_the_price_said_in_between(message, found):
    assert check_message_manner(message, greeting=True) == [f'the message offers to pay before collecting: "{found}"']


@pytest.mark.parametrize("message", [
    "Hi, I can pay £200 cash now.",  # cash is paid when you meet
    "Hi, I can pay £200 now on collection.", "Hi, I can pay £200 when I collect.",
    "Hi, I'll pay £200 first thing tomorrow.", "Hi, I can pay £200. Now, when could I collect?",
    "Hi, I can pay £200 cash today.", "Hi, would you take £200 now?",
])
def test_paying_when_you_meet_is_no_paying_first(message):
    assert check_message_manner(message, greeting=True) == []


def test_your_ebay_pay_now_offer_isnt_used_on_facebook():
    """style.for_market leaves out a habit PAY_FIRST reads, where you meet the seller: with "pay £[OFFER] now" missed,
    your eBay "I'll pay £[OFFER] now." went out on Facebook as "Hi mate, I'll pay £200 now."."""
    yours = card(*((f"Hi mate, I'll pay £{p} now.", p, "ebay") for p in ("200", "150", "90")),
                 ("Hi mate, I can do £200 cash for it.", "200"), ("Hi mate, happy to give £150 for it.", "150"))
    assert drafted(FACEBOOK, yours, "asking", 20000) == ("Hi mate, I can pay £200 for it.", [])


def test_on_ebay_paying_straight_away_with_the_price_is_fine_but_never_off_the_site():
    ebay = {"greeting": True, "pay_first": False, "cash": False}
    assert check_message_manner("Hi, I'll pay the full £400 straight away.", **ebay) == []
    assert check_message_manner("Hi, I can pay £200 straight away, send me your bank details.", **ebay) == [
        'the message offers to pay before collecting: "pay £200 straight away"']


# ── time-place-04: a closing that holds is never dropped ───────────────────────────────────────────

def holder(closing):
    return card(*((f"Hi, I can pay £{p} cash tonight. {closing}", a)
                  for p, a in (("300", "280"), ("130", "120"), ("150", "150"), ("90", "90"))))


@pytest.mark.parametrize("kind, offer, message", [
    ("more", 21000, "Hi, I can pay £210 cash tonight. Could you hold it for me and I'll collect?"),
    ("asking", 20000, "Hi, I can pay £200 cash tonight. Could you hold it for me and I'll collect?"),
])
def test_a_closing_that_holds_keeps_the_hold_and_loses_only_the_time(kind, offer, message):
    """It went whole for saying "tonight" again: over asking was refused ("says why"), at asking the hold was lost."""
    assert drafted(FACEBOOK, holder("Could you hold it for me and I'll collect tonight?"), kind, offer) == (message, [])


def test_in_auto_your_own_sentences_now_pass_so_no_ai_is_asked():
    """The verifier: auto ended as "needs you" (the AI's draft refused too), where V8PRE sent your own message."""
    result = draft_message(FACEBOOK, holder("Could you hold it for me and I'll collect tonight?"),
                           local=FakeModel("gemma3:4b"), kind="more", offer=21000, reading=NOTHING_READ)
    assert (result["status"], result["writer"]) == ("ready", "template")


def test_a_hold_in_its_own_sentence_stays_and_the_collecting_says_no_time_twice():
    """The verifier's control. "cash tonight" says when you'd pay, not that you'd come (v8-integration-4), so "I'll
    collect." stays, without its "tonight"."""
    assert drafted(FACEBOOK, holder("Could you hold it for me? I'll collect tonight."), "more", 21000) == \
        ("Hi, I can pay £210 cash tonight. Could you hold it for me? I'll collect.", [])


# ── time-place-05: a sentence that says more than collecting keeps it all but the time ────────────

@pytest.mark.parametrize("time", ["tonight", "today"])  # "today": the verifier's
def test_collecting_and_cash_in_one_sentence_keep_the_cash(time):
    yours = card(*((f"Hi mate, would you take £{p}? Can collect {time} and pay cash.", a) for p, a in LOWER),
                 *((f"Hi mate, I'll pay £{p} if you can hold it till {time}. Can collect {time} and pay cash.", a)
                   for p, a in (("300", "280"), ("130", "120"))))
    assert drafted(FACEBOOK, yours, "more", 21000) == \
        (f"Hi mate, I'll pay £210 if you can hold it till {time}. Can collect and pay cash.", [])


def test_the_thanks_typed_in_a_dropped_sentence_stays():
    """"can pick up later ta x" went whole, its "ta x" with it (N5 kept "Ta" only as a sentence of its own)."""
    yours = card(*((f"hiya would u do £{p}? can pick up later ta x", a) for p, a in LOWER),
                 *((f"hiya ill give u £{p} if u hold it till later. can pick up later ta x", a)
                   for p, a in (("300", "280"), ("130", "120"))))
    assert drafted(FACEBOOK, yours, "more", 21000) == ("hiya ill give u £210 if u hold it till later. ta x", [])


# ── time-place-06: the seller's time in a flaw isn't yours ─────────────────────────────────────────

@pytest.mark.parametrize("flaw, closing", [("Screen started flickering today", "Can collect today."),
                                           ("Back glass cracked this morning", "Can collect this morning.")])
def test_the_time_in_the_listings_flaw_doesnt_drop_your_collecting(flaw, closing):
    listing = {**FACEBOOK, "description": f"iphone 13 128gb unlocked. {flaw}, otherwise fully wkg. bh 88%"}
    yours = card(*((f"Hi mate, would you take £{p} given the condition? {closing}", a)
                   for p, a in (("150", "180"), ("90", "110"), ("240", "280"))))
    assert drafted(listing, yours, "lower", reading={**NOTHING_READ, "flaws": [flaw]}, mention=True) == \
        (f"Hi mate, would you take £170 given the {flaw[0].lower()}{flaw[1:]}? {closing}", [])


# ── time-place-11: the same time in another spelling, or another way of coming ─────────────────────

@pytest.mark.parametrize("hold, closing", [
    ("till tmr", "Can collect tmr."), ("till tonight", "Can collect 2nite."), ("till later", "Can pop round later."),
    # ...and the verifier's controls, dropped before and now
    ("till later", "Can pick up later."), ("till tomorrow", "Can collect tomorrow."),
    ("till tmrw", "Can collect tmrw."), ("till tonight", "Can come tonight."),
    # ...and more of the ways the style knows
    ("till tonight", "Can come over this evening."), ("till tomorrow", "Can collect tommorow."),
    ("till tonight", "can collect 2nite"), ("till tonight", "Can be there tonight."),
    ("till the weekend", "Can collect at the weekend."), ("till tonight", "Tonight I can collect."),
    ("till tonight", "CAN COLLECT TONIGHT"), ("till tonight", "Can collect tonight..."),  # not a lone "..." left
])
def test_the_same_time_said_another_way_is_said_once(hold, closing):
    assert drafted(FACEBOOK, holds_with(hold, closing), "more", 21000) == \
        (f"Hi, I'll pay £210 if you can hold it {hold}.", [])


@pytest.mark.parametrize("hold, closing, ends", [
    # a list: never "Can collect or tomorrow."
    ("till tonight", "Can collect tonight or tomorrow.", "Can collect tonight or tomorrow."),
    ("till tonight", "Can collect tonight and tomorrow.", "Can collect tonight and tomorrow."),
    ("till tonight", "Can collect tonight/tomorrow.", "Can collect tonight/tomorrow."),
    ("till tomorrow", "Can collect tomorrow morning.", "Can collect tomorrow morning."),  # more of when
    ("till tonight", "Can collect tonight-ish.", "Can collect tonight-ish."),
    ("till today", "Free from today till Sunday to collect.", "Free from today till Sunday to collect."),  # a range
    ("until tonight", "Can collect no later than tonight.", "Can collect no later than tonight."),
    ("till tonight", "Can collect from yours tonight.", "Can collect from yours."),  # says where: only the time goes
    ("till tonight", "Can collect tonight if that's ok?", "Can collect if that's ok?"),
    ("till tonight", "Can collect tonight, cheers", "Cheers"),  # nothing but collecting: its thanks stays
    ("till tomorrow", "Can grab it tmrw x", "x"),
    # ...and when is the point, or what it's about: never "Can't collect." or "Is ok to collect?"
    ("till tonight", "Can't collect till tonight.", "Can't collect till tonight."),
    ("till tonight", "Can only collect tonight.", "Can only collect tonight."),
    ("till tonight", "Is tonight ok to collect?", "Is tonight ok to collect?"),
    ("till tonight", "Can collect tonight if not tomorrow.", "Can collect tonight if not tomorrow."),
    ("till tonight", "Can collect tonight, otherwise tomorrow.", "Can collect tonight, otherwise tomorrow."),
    ("till later", "Can collect a bit later.", "Can collect a bit later."),  # never "Can collect a bit."
    ("till tonight", "Can collect late tonight.", "Can collect late tonight."),
    ("till tomorrow", "Can collect first thing tomorrow.", "Can collect first thing tomorrow."),
    ("till tonight", "No rush, can collect tonight.", "No rush, can collect."),
])
def test_a_time_comes_out_only_where_the_sentence_still_reads(hold, closing, ends):
    assert drafted(FACEBOOK, holds_with(hold, closing), "more", 21000) == \
        (f"Hi, I'll pay £210 if you can hold it {hold}. {ends}", [])


# ── v8-integration-4: a time to pay doesn't say you'd come ─────────────────────────────────────────

@pytest.mark.parametrize("message, ends", [
    ("Hi mate, would you take £{p} cash today? Can collect today.",
     "Hi mate, would you take £170 cash today? Can collect."),
    ("hi would you take £{p}, can pay today? can pick up today after work",
     "hi would you take £170, can pay today? can pick up after work"),
])
def test_a_time_to_pay_never_drops_your_collecting(message, ends):
    """"Can collect today." went after "cash today": the promise to collect (and "after work") was lost. The time is
    said once and the collecting stays, as the finding allows."""
    listing = {**FACEBOOK, "title": "iPhone 13 128GB Midnight",
               "description": "Good condition, unlocked, comes with box."}
    yours = card(*((message.format(p=p), a) for p, a in (("150", "180"), ("90", "110"), ("250", "300"))))
    assert drafted(listing, yours, "lower") == (ends, [])


@pytest.mark.parametrize("offer, closing, ends", [
    ("would you take £{p} if I collect today?", "Can collect today.", ""),  # the offer says you'd come: once
    ("would you take £{p} cash today?", "Can collect tonight.", " Can collect tonight."),  # another time: stays
    ("would you take £{p} cash today?", "Can collect today or tomorrow.", " Can collect today or tomorrow."),
])
def test_your_collecting_goes_only_when_the_offer_says_youd_come_then(offer, closing, ends):
    yours = card(*((f"Hi mate, {offer.format(p=p)} {closing}", a) for p, a in LOWER))
    assert drafted(FACEBOOK, yours, "lower") == (f"Hi mate, {offer.format(p='170')}{ends}", [])


@pytest.mark.parametrize("sentence, coming", [
    ("I'll pay £[OFFER] if you can hold it till later.", True), ("would you take £[OFFER] if I collect today?", True),
    ("would you take £[OFFER] if I pop round tonight?", True), ("would you take £[OFFER] for collection today?", True),
    ("would you take £[OFFER] cash today?", False), ("hi would you take £[OFFER], can pay today?", False),
    ("Hi, I can pay £[OFFER] cash tonight.", False),
    ("If you could keep it for me I can pay £[OFFER] cash tonight", False),
    # a price's words aren't coming
    ("Would you come down to £[OFFER] today?", False), ("Could you meet me halfway at £[OFFER] today?", False),
    ("would you take £[OFFER] if you pop it in the post today?", False),
])
def test_a_time_is_when_youd_come_only_with_a_word_of_coming_before_it(sentence, coming):
    assert {come for _, come in times_in(sentence)} == {coming}


def test_one_offer_can_say_when_youd_pay_and_when_youd_come():
    assert times_in("I'll pay £[OFFER] cash today if you can hold it till 2nite") == \
        {("today", False), ("tonight", True)}


@pytest.mark.parametrize("said, time", [
    ("today", "today"), ("2day", "today"), ("tonight", "tonight"), ("2nite", "tonight"), ("tonite", "tonight"),
    ("this evening", "tonight"), ("This Eve", "tonight"), ("tomorrow", "tomorrow"), ("tmrw", "tomorrow"),
    ("Tmr", "tomorrow"), ("tomoz", "tomorrow"), ("2moro", "tomorrow"), ("tommorow", "tomorrow"),
    ("later on", "later"), ("at the weekend", "the weekend"), ("this weekend", "the weekend"),
])
def test_a_time_is_read_as_one_whatever_its_spelling(said, time):
    assert times_in(f"Can collect {said}.") == {(time, True)}


def test_every_spelling_of_a_time_the_style_card_knows_is_read_by_the_time_once_rule():
    """style.TIMES is how your habits merge their times; the writer reads each of them as a time it knows, so the two
    never drift apart (a new spelling there needs its time in writer.SPELLED)."""
    nested = re.search(r"this \(\?:([^)]*)\)", TIMES)
    spellings = [s for s in TIMES[3:nested.start()].split("|") if s] + [f"this {w}" for w in nested.group(1).split("|")]
    assert "tmr" in spellings and "this evening" in spellings
    for said in spellings:
        assert {time for time, _ in times_in(f"Can collect {said}.")} == {time_of(said)}
        assert time_of(said) in {"today", "tonight", "tomorrow", "this afternoon", "this morning"}


def test_a_kiss_closing_stays_a_kiss():
    """A kiss isn't a sentence: "Would you take £170? X" (before this fix too, for a closing of just "x")."""
    yours = card(*((f"Hi, would you take £{p}? x", a) for p, a in LOWER))
    assert write_offer(yours, "lower", 17000, in_person=True) == "Hi, would you take £170? x"
