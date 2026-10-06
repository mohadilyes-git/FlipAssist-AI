"""The three breaks the final recheck of 26 Sep found in the second fix round, each one that sends a wrong message."""

import pytest

from flip.checks import PAY_FIRST, check_message_manner
from flip.message_drafter import check_ai_manner, draft_message
from flip.style import for_kind, style_card
from flip.writer import with_reason

LISTING = {"id": "x", "title": "iPhone 13 128GB", "asking_price": "200", "marketplace": "facebook",
           "description": "iPhone 13 128gb unlocked, fully wkg, bh 88%. Collection Leeds."}
NOTHING = {"flaws": [], "pickup": "", "no_offers": "", "read_by": "gemma3:4b"}


def lower_with(closing):
    return style_card([{"my_message": f"Hi, would you take £{p}? {closing}", "asking_price": a, "marketplace": "facebook",
                        "listing_title": "iPhone 13"} for p, a in (("150", "180"), ("90", "110"), ("60", "80"))])


@pytest.mark.parametrize("closing", ["Hope a bit less is ok.", "Would a bit less be ok?", "Is a little less ok?",
                                     "Hope a little lower is alright.", "Bit lower than listed I know.",
                                     "A bit under list price I know.", "Bit under the advertised price, I know.",
                                     "It's a little less than listed but cash is ready."])
def test_at_or_over_asking_no_closing_says_the_offer_is_less(closing):
    card = lower_with(closing)
    for kind, offer in (("asking", 20000), ("more", 21000)):
        message = draft_message(LISTING, card, kind=kind, offer=offer, reading=NOTHING, writer="template")["answer"]["message"]
        assert closing not in message, (kind, message)
    # ...under asking it's yours, and stays
    lower = draft_message(LISTING, card, kind="lower", offer=17000, reading=NOTHING, writer="template")
    assert lower["answer"]["message"].endswith(closing)


def test_a_time_with_less_than_is_no_lower_offer():
    card = lower_with("Can collect in less than an hour.")
    assert for_kind(card, "asking")["phrases"]["closing"] == "Can collect in less than an hour."


def test_the_ai_is_refused_an_apology_at_or_over_asking():
    problem = check_ai_manner("Hi, I can pay £200. Hope a bit less is ok.", "asking", 20000, False)
    assert any("says the offer is less" in p for p in problem)
    assert not any("says the offer is less" in p for p in check_ai_manner("Hi, I can pay £200. Can collect today.",
                                                                           "asking", 20000, False))


@pytest.mark.parametrize("lead", ["allowing for", "to allow for", "accounting for", "to account for", "to make up for",
                                  "to compensate for", "making allowances for"])
def test_for_inside_a_lead_of_its_own_is_never_cut_off(lead):
    """'would you take £170 allowing?' (the "for" of "allowing for" was taken for the lead)."""
    mint = with_reason(f"would you take £[OFFER] {lead} the condition?", "lower", None)
    assert not mint.rstrip("?").endswith(lead.split()[-2]), mint
    assert "allowing?" not in mint and "allow?" not in mint
    # the control: a bare "for the condition" still takes the flaw
    point = {"about": "flaw", "says": ["Small crack on the back"]}
    assert with_reason("would you take £[OFFER] for the condition?", "lower", point) == \
        "would you take £[OFFER] given the small crack on the back?"


@pytest.mark.parametrize("message", ["Hi, I can pay £210 now upon confirmation if you can hold it for me.",
                                     "Hi, I can pay £210 straight away upon your reply.",
                                     "Hi, I can pay £210 asap after I hear back from you.",
                                     "Hi, I can pay £210 now after we agree, if you can hold it.",
                                     "Hi, I can pay £210 now by cash app.", "Hi, I can pay £210 now, cash or card."])
def test_paying_first_is_not_excused_by_words_that_arent_meeting(message):
    assert PAY_FIRST.search(message), message


@pytest.mark.parametrize("message", ["Hi, I can pay £200 now on collection.",
                                     "Hi, I can pay £200 straight away in cash when I collect.",
                                     "Hi, I can pay £200 now, cash on collection.", "Hi, I can pay £200 asap - cash in hand.",
                                     "Hi, I can pay £200 right away after I've had a look.",
                                     "Hi, I can pay £200 now when I pick it up."])
def test_paying_when_you_meet_still_passes(message):
    assert not PAY_FIRST.search(message), message
