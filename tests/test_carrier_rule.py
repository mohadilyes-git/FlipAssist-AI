"""The owner's carrier rule (6 Oct 2026, buyer-safe): a carrier or network named for the phone is a network lock
unless the listing says it's unlocked or works on any network (flip.prices: network_lock, network_named,
says_unlocked, lock_said). Code's rules sort the title and any flaw flip-kinds-1 can't answer; the model already sorts
this way. Made-up listings only: carrier_cases.py holds the adversarial review's 193."""
import json

import pytest

from flip import prices
from tests.carrier_cases import CASES


def kinds(flaw, rest=""):
    return prices.kinds_of([flaw], f"iPhone 13 128GB. {flaw} {rest}".strip())


def title_kinds(title, description):
    return prices.kinds_of([title], f"{title}. {description}", title=True)


@pytest.mark.parametrize("locked, where, title, description, flaw, why", CASES, ids=[c[5] for c in CASES])
def test_the_adversarial_reviews_cases(locked, where, title, description, flaw, why):
    found = title_kinds(title, description) if where == "title" else prices.kinds_of([flaw], f"{title}. {description}")
    assert ("network lock" in found) is locked, (title, flaw, description, found)


@pytest.mark.parametrize("flaw", [
    "Carrier: AT&T", "Carrier AT&amp;T", "CarrierT-Mobile", "Network: O2", "Samsung Galaxy S21 Phantom Grey EE",
    "for Straight Talk", "Works on Verizon", "Ready to use on Cricket", "Provider is Metro by T-Mobile",
    "AT&T or Cricket", "Boost Mobile phone", "It's a Tracfone", "On 02", "On Three", "Comes from Vodafone",
    "Total Wireless prepaid", "Bought from Rogers", "Telstra network", "for metro or tmobile", "Verzion iPhone",
    "I only use EE", "We are with EE", "VZW", "TMO", "Network: Three", "Carrier: Bell", "Network - Virgin",
])
def test_a_carrier_named_for_the_phone_is_a_network_lock(flaw):
    assert "network lock" in kinds(flaw)


@pytest.mark.parametrize("flaw, rest", [
    ("Carrier: AT&T", "Unlocked to all networks."),
    ("Carrier: AT&T", "Factory unlocked."),
    ("Network: O2", "SIM free."),
    ("Works on Verizon", "Works on any network."),
    ("Works on Verizon", "Compatible with all carriers."),
    ("Works on Verizon", "Works with all GSM & CDMA carriers."),
    ("Bought from EE", "Not network locked."),
    ("Bought from EE", "It isn't locked."),
    ("Network: EE", "Network locked: No."),
    ("Network: EE", "SIM lock: none."),
    ("Was on EE but has been unlocked", ""),
    ("Previously O2 locked, now unlocked", ""),
    ("Unlocked EE", ""),
    ("Never been locked to EE", ""),
    ("No EE lock", ""),
])
def test_unless_the_listing_says_it_works_on_any_network(flaw, rest):
    assert "network lock" not in kinds(flaw, rest)


@pytest.mark.parametrize("flaw, rest", [
    ("Works on Verizon", "Not unlocked."),
    ("Works on Verizon", "Can be unlocked once it's paid off."),
    ("Works on Verizon", "I think it's unlocked."),  # a doubt: buyer-safe, it isn't said
    ("Carrier: EE", "I think it's not network locked."),
    ("Carrier: EE", "Will work on any network once unlocked."),
    ("Network: O2", "iCloud unlocked."),  # not the network
    ("Network: O2", "Won't work on any other network."),
    ("On EE, not sure if it's been unlocked", ""),
    ("On Vodafone, I don't think it has been unlocked", ""),
])
def test_a_doubt_a_promise_or_another_lock_is_no_unlock(flaw, rest):
    assert "network lock" in kinds(flaw, rest)


@pytest.mark.parametrize("flaw", [
    "Never been unlocked", "It hasn't been unlocked yet", "It hasnt been unlocked", "It has not yet been unlocked",
    "Not unlocked", "Can be unlocked for £10", "Can be easily unlocked", "Needs to be network unlocked", "Unlock pending",
    "Eligible for unlock in March", "Won't work on any other network", "Won't take other networks' SIMs",
    "Doesn't work with other sims", "No issues and can't be used on other networks", "EE locked, hasnt been unlocked",
    "Network lock: Yes",
])
def test_a_lock_said_in_other_words(flaw):
    assert "network lock" in kinds(flaw)


@pytest.mark.parametrize("flaw", [
    "Untested on the EE network", "Not tested with O2", "Switching to Vodafone so selling this",
    "Not tested on EE or O2, small scratch", "Switching to EE or O2 so selling", "Comes with three cases",
    "Visible scratches on the back", "Mint condition", "Battery boost mode works", "On 02/03/2025 the screen cracked",
    "With 3 small scratches", "Orange case included", "Not iCloud locked", "Not EE locked", "Not network locked",
    "Was EE locked, got it unlocked", "Was EE locked, had it unlocked", "Not a Verizon phone, bought from Apple",
    "Face ID not working, can only be unlocked with the passcode", "Not unlocked from iCloud yet",
    "Small scratch, will be unlocked from my iCloud before sale", "Activation locked, needs unlocking by previous owner",
])
def test_no_network_lock(flaw):
    assert "network lock" not in kinds(flaw)


def test_a_macbook_has_no_network_lock():
    found = prices.kinds_of(["Wifi doesn't work with other networks"],
                            "MacBook Pro 13 2019. Wifi doesn't work with other networks")
    assert "network lock" not in found and "fault" in found


@pytest.mark.parametrize("title, description, locked", [
    ("iPhone 13 128GB AT&T", "Great phone, small scratch.", True),
    ("Apple iPhone 16 Pro 128GB T-Mobile", "Like new.", True),
    ("Samsung Galaxy S21 5G Phantom Grey EE", "Good condition.", True),
    ("Samsung Galaxy S20 FE 128GB (Three)", "Good condition.", True),
    ("Samsung Galaxy A54 5G Metro", "Brand new, good with metropcs.", True),  # the blind title check's two misses
    ("Samsung galaxy j3 I used 02 sim In it", "Micro sim, 8gb, no charger.", True),
    ("iPhone 13 128GB Ultra Mobile", "Like new.", True),
    ("iPhone 13 128GB AT&T Unlocked", "Great phone.", False),
    ("iPhone 13 128GB Verizon", "Unlocked to any carrier.", False),
    ("iPhone 13 Pro 128GB O2", "Carrier Lock: No SIM restrictions.", False),
    ("iPhone 13 128GB EE", "Never dropped and fully unlocked.", False),
    ("iPhone 13 128GB EE", "Not a mark on it and unlocked to any network.", False),
    ("iPhone 13 128GB Space Grey", "Great phone.", False),
    ("iPhone 13 Mint Condition 128GB", "Barely visible scratches.", False),
    ("Samsung Galaxy S23 Ultra Mobile Phone 256GB", "Good condition.", False),
    ("iPhone 17 Pro 256GB Cosmic Orange Mobile Phone", "Like new.", False),
])
def test_the_title_is_sorted_by_the_same_rule(title, description, locked):
    assert ("network lock" in title_kinds(title, description)) is locked


def test_a_network_lock_reaches_the_prices_api_from_the_title(monkeypatch):
    """The title's carrier goes into what's sent: the cut happens (a pretend API, no real call)."""
    from tests.test_prices import ANSWER, Response
    monkeypatch.setenv("PRICES_URL", "https://example.test/functions/v1/prices")
    monkeypatch.setenv("PRICES_KEY", "k" * 64)
    prices._seen.clear()
    sent = []

    def opener(request, timeout):
        sent.append(json.loads(request.data))
        return Response(json.dumps(ANSWER).encode())

    prices.estimate("iPhone 13 128GB AT&T", [], opener=opener, description="Great phone.")
    prices.estimate("iPhone 13 128GB AT&T Unlocked", [], opener=opener, description="Great phone.")
    assert "network lock" in sent[0]["kinds"] and "network lock" not in sent[1]["kinds"]


@pytest.mark.parametrize("description, locked", [
    ("I pretty sure it's unlocked, worked with a T-Mobile sim.", True),  # a hedge: buyer-safe, it isn't said
    ("I'm fairly sure it's unlocked.", True),
    ("100% unlocked for sure.", False),
    ("Make sure you check the photos. Unlocked to all networks.", False),
])
def test_a_hedge_is_no_unlock(description, locked):
    assert ("network lock" in title_kinds("Samsung Galaxy Note 20 5G (T mobile)", description)) is locked


@pytest.mark.parametrize("title, description", [  # the second blind title check's misses: one seller's template
    ("Att/cricket Apple IPhone 11 64gb", "Excellent condition for att net10 h20 aio air voice cricket or can be unlocked "
                                         "for any Sim card worldwide"),
    ("Pink att/cricket Samsung Galaxy s23 Ultra 512gb", "Excellent condition, can be unlocked for any Sim card worldwide "
                                                        "after using it"),
])
def test_a_promise_of_any_network_is_no_unlock(title, description):
    assert "network lock" in title_kinds(title, description)
    assert "network lock" not in title_kinds(title, "Unlocked for any Sim card worldwide.")
