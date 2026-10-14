"""The listing's UK price from the AlertFlip app's prices API (flip.prices, 4 Oct 2026): iPhones, Samsungs and
MacBooks only (never a case or a charger), the flaws sorted into kinds here (a "no" or "not" undoes one, every kind in
a sentence counts), the size from the description when the title has none, the key in a header, and every failure an
answer in FlipAssist's words, never an error. Pretend API: nothing is sent anywhere.

The flaw sentences below are the 4 Oct review's, each one a price the API's own sorter got wrong, then the 6 Oct
recheck's (from "6 Oct recheck" on): each one a price or a size FlipAssist's own sorting still got wrong, then its
second check's (from "6 Oct second check" on): what the recheck's fixes broke or left, and every input that check
tried, each with its right answer."""

import io
import json
import urllib.error

import pytest

from flip import prices

ANSWER = {"mode": "catalogue", "model": "iphone 13", "storage_gb": 128, "ram_gb": None, "currency": "GBP",
          "sales": 38, "middle": 210, "low": 180, "high": 240, "price": 170, "factor": 0.81, "used": ["damage"],
          "rough": False, "exact_match": True,
          "plan": {"kind": "iphone", "model": "iphone 13", "storage_gb": 128, "ram_gb": None, "condition": "good"}}


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def backend(monkeypatch):
    monkeypatch.setenv("PRICES_URL", "https://example.test/functions/v1/prices")
    monkeypatch.setenv("PRICES_KEY", "k" * 64)
    prices._seen.clear()


def asking(answer=None):
    """A pretend API that answers with answer (ANSWER) and keeps what it was sent."""
    sent = []

    def opener(request, timeout):
        sent.append((request.full_url, request.headers, json.loads(request.data)))
        return Response(json.dumps(answer or ANSWER).encode())
    return opener, sent


def test_an_iphone_is_priced_with_its_flaws_sorted_into_kinds():
    opener, sent = asking()
    found = prices.estimate("iPhone 13 128GB Blue", ["Small crack on the back", " "], opener=opener,
                            description="Small crack on the back. Collection Leeds.")
    # fix 1 (14 Oct): the damage is FlipAssist's own cut, by how bad (a small crack: minor) and the model's price tier
    # (a clean one £210: middle), measured on 153 such UK iPhone listings; the API is asked for its other cuts only
    assert found == {"price": 138, "middle": 210, "low": 180, "high": 240, "currency": "GBP", "sales": 38,
                     "model": "iphone 13", "item": None, "storage_gb": 128, "ram_gb": None, "asked_storage_gb": 128,
                     "asked_ram_gb": None, "kind": "iphone", "kinds": ["damage"], "cuts": ["damage"],
                     "parts_price": False, "rough": False, "exact": True, "mode": "catalogue", "sorted_by": "code",
                     "damage": {"level": "minor", "tier": "middle", "cut": -0.188, "rough": False, "from": None,
                                "n": 153}}
    url, headers, body = sent[0]
    assert body == {"action": "price", "country": "uk", "title": "iPhone 13 128GB Blue", "kinds": [],
                    "strict": True}  # the API's own sorter isn't used, and a title naming no model is refused
    assert headers["X-prices-key"] == "k" * 64
    prices.estimate("iPhone 13 128GB Blue", ["Small crack on the back"], opener=opener,
                    description="Small crack on the back. Collection Leeds.")
    assert len(sent) == 1  # the same listing again: asked once


@pytest.mark.parametrize("flaws, kinds", [
    (["Small scratch on the back, no repairs, never opened"], ["wear"]),  # the API: for parts, £90
    (["Not iCloud locked, has a small scratch on the screen"], ["wear"]),  # the API: locked
    (["Find My iPhone is off, small dent on the corner"], ["damage"]),  # the API: locked
    # the owner's carrier rule (6 Oct): a network named for the phone, with no "unlocked", is a lock (buyer-safe)
    (["Only tested with EE, not tested on other networks, small scratch"], ["wear", "network lock"]),  # API: for parts
    (["Fully working, no faults, small scratch on the screen"], ["wear"]),  # the API: a fault
    (["no cracks a couple scratches on the back"], ["wear"]),  # the API: damage
    (["Cracked screen and Face ID not working"], ["damage", "fault"]),  # the API: damage only
    (["Cracked back", "Small crack on the screen"], ["damage"]),  # one kind, cut once
    (["Rear camera is broken"], ["fault"]),  # the API: wear
    (["Green line on the screen"], ["fault"]),
    (["Keyboard has a sticky key"], ["fault"]),
    (["Speaker crackles a bit at full volume"], ["fault"]),  # the API: damage ("crack")
    (["Unlocked to all networks, slight scratch on the screen"], ["wear"]),  # the API: network lock
    (["Scratched and no cracks"], ["wear"]),
    (["No cracks or chips but light scratches"], ["wear"]),
    (["not very obvious scratches on the back"], ["wear"]),  # a "not" that only says how much
    (["Battery health 81%."], []),  # 80% or more is no flaw, as the sales were sorted
    (["Battery health 75%"], ["battery"]),
    (["Original box, slightly damaged"], []),  # the box's
    (["Charger missing"], []),
    (["Scratch free screen"], []),
    (["iCloud locked to previous owner"], ["lock"]),
    (["Locked to EE"], ["network lock"]),
    (["Screen is not genuine"], ["not genuine"]),
    (["Sold as seen"], ["wear"]),  # a warning with no flaw named, cut as the API cuts it
])
def test_each_flaw_is_sorted_as_the_price_should_be_cut(flaws, kinds):
    assert prices.kinds_of(flaws, "iPhone 13 128GB. " + " ".join(flaws)) == kinds


def test_only_iphones_samsungs_and_macbooks_are_asked_about_never_what_goes_with_them():
    opener, sent = asking()
    for title in ("PS5 Disc Edition", "Dyson V11", "iMac 24 M1", "Mac mini M2", "iPad Air 5", "Audi S8 2015",
                  "iPhone 13 case", "iPhone 13 screen protector", "iPhone 13/14 case", "Charger for MacBook",
                  "MacBook sleeve 13 inch", "MacBook Pro charger 61W", "iPhone 14 Pro Max box only",
                  "Samsung 55 inch TV", "Samsung Galaxy Tab S9", "Galaxy Watch 6", "Galaxy Buds 2 Pro",
                  "Samsung Galaxy Book3"):
        assert prices.estimate(title, opener=opener) == {"skipped": prices.SKIPPED}, title
    assert not sent
    titles = {"Samsung Galaxy S22 128GB": "samsung", "iPhone 12": "iphone", "Apple MacBook Air M1 8GB 256GB": "macbook",
              "macbook pro 14 m3": "macbook", "Mac Book Air 2020": "macbook", "iPhone13 128GB": "iphone",
              "iPhoneX 64GB": "iphone", "iphone12pro": "iphone", "MacBookAir M2 2022": "macbook",
              "MacBookPro16,1": "macbook", "MBP 16 M1 Pro": "macbook", "GalaxyS23 Ultra": "samsung",
              "S23 Ultra 256GB": "samsung", "iPhone 13 128GB with case": "iphone",
              "MacBook Air M1 2020, charger included": "macbook", "iPhone 12 swap for iPhone 13": "iphone",
              "Samsung Galaxy Z Fold 5 with Galaxy Watch": "samsung"}
    assert {t: prices.kind_of(t) for t in titles} == titles


@pytest.mark.parametrize("text, kind, sizes", [
    ("Storage 128GB, 6GB RAM", "iphone", (128, None)),  # a phone's RAM isn't its storage
    ("1TB, battery 89%", "iphone", (1024, None)),
    ("comes with 50GB iCloud plan, 256GB", "iphone", (256, None)),
    ("128GB SD card included, phone is 64GB", "iphone", (64, None)),
    ("64GB or 128GB", "iphone", (None, None)),  # two sizes: neither
    ("half price 1/2 off", "iphone", (None, None)),
    ("M1 8GB 256GB", "macbook", (256, 8)),
    ("16GB RAM 1TB SSD", "macbook", (1024, 16)),
    ("8/256", "macbook", (256, 8)),
    ("16GB/1TB", "macbook", (1024, 16)),
])
def test_the_size_is_read_from_the_words_that_give_it(text, kind, sizes):
    assert prices.sizes_in(text, kind) == sizes


def test_a_size_only_the_description_gives_is_sent_and_the_size_asked_comes_back():
    answer = {**ANSWER, "storage_gb": 1024, "plan": {**ANSWER["plan"], "storage_gb": None}}
    opener, sent = asking(answer)
    found = prices.estimate("iPhone 14 Pro Max Deep Purple", [], opener=opener, description="1TB, battery 89%")
    assert sent[0][2]["storage_gb"] == 1024 and found["asked_storage_gb"] == 1024
    opener, sent = asking({**ANSWER, "plan": {**ANSWER["plan"], "storage_gb": None}})
    found = prices.estimate("iPhone 13 Blue", [], opener=opener, description="Lovely phone")
    assert "storage_gb" not in sent[0][2] and found["asked_storage_gb"] is None  # no size anywhere: the screen says so
    opener, sent = asking({**ANSWER, "model": "macbook air 13 m1", "storage_gb": 256, "ram_gb": 8,
                           "plan": {"kind": "macbook", "storage_gb": 256, "ram_gb": None}})
    found = prices.estimate("MacBook Air M1 256GB", [], opener=opener, description="16GB RAM, perfect")
    assert sent[0][2]["ram_gb"] == 16 and "storage_gb" not in sent[0][2]  # the title's size is the API's to read
    assert (found["asked_storage_gb"], found["asked_ram_gb"], found["ram_gb"]) == (256, 16, 8)


def test_a_locked_or_for_parts_listing_is_asked_as_good_with_the_parts_cut():
    opener, sent = asking({**ANSWER, "used": ["for-parts price"], "price": 90})
    found = prices.estimate("iPhone 13 128GB for parts", ["Won't turn on"], opener=opener, description="Won't turn on")
    assert (sent[0][2]["bucket"], sent[0][2]["kinds"]) == ("good", ["parts"])
    assert (found["parts_price"], found["cuts"]) == (True, [])
    opener, sent = asking()
    prices.estimate("Faulty iPhone 12 64GB", [], opener=opener, description="")
    assert (sent[0][2]["bucket"], sent[0][2]["kinds"]) == ("good", ["fault"])  # the title's own flaw counts
    opener, sent = asking()
    prices.estimate("iPhone 13 128GB", ["Small scratch"], opener=opener, description="Small scratch")
    assert "bucket" not in sent[0][2]  # a sealed one is still the API's to read as new


def test_a_macbook_comes_back_with_its_ram():
    answer = {**ANSWER, "model": "macbook air 13 m1", "storage_gb": 256, "ram_gb": 8, "used": ["no flaw"],
              "plan": {"kind": "macbook", "storage_gb": 256, "ram_gb": 8}}
    found = prices.estimate("MacBook Air M1 8GB 256GB", opener=asking(answer)[0])
    assert (found["model"], found["storage_gb"], found["ram_gb"], found["cuts"], found["kind"]) == \
        ("macbook air 13 m1", 256, 8, [], "macbook")


def test_every_failure_is_an_answer_in_its_own_words_never_ebays():
    def refusing(code, status):
        def opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, status, "x", {}, io.BytesIO(json.dumps(
                {"error": {"code": code, "message": f"No good sales of iphone 13 on ebay.co.uk ({code})"}}).encode()))
        return opener
    for code, status in (("TOO_VAGUE", 422), ("NO_SALES", 404), ("UNAVAILABLE", 503), ("DAILY_LIMIT", 429),
                         ("SOMETHING_NEW", 500)):
        said = prices.estimate("iPhone 13", opener=refusing(code, status))["error"]
        assert "ebay" not in said.lower() and said, code
    assert prices.estimate("iPhone 13", opener=refusing("TOO_VAGUE", 422))["error"] == prices.REFUSED["TOO_VAGUE"]

    def down(request, timeout):
        raise urllib.error.URLError("no network")
    assert "Couldn't reach" in prices.estimate("Galaxy S23", opener=down)["error"]


def test_with_no_api_set_nothing_is_asked(monkeypatch):
    monkeypatch.setenv("PRICES_KEY", "")
    assert "skipped" in prices.estimate("iPhone 14")


# ── 6 Oct recheck ──────────────────────────────────────────────────────────────────────────────────────────────────

def kinds(sentence):
    """The kinds one flaw sentence gives, read in a listing that's the title and that sentence."""
    return prices.kinds_of([sentence], "iPhone 13 128GB. " + sentence)


def sent(title, flaws=(), description=""):
    """What estimate asks the pretend API, without what every request has, and with the kinds it counted: since fix 1
    (14 Oct) damage is FlipAssist's own cut, so the API is asked without it (test_damage_is_cut_once_by_how_bad)."""
    opener, asked = asking()
    found = prices.estimate(title, list(flaws), opener=opener, description=description)
    return {**{k: v for k, v in asked[0][2].items() if k not in ("action", "country", "title", "strict")},
            "kinds": found["kinds"]}


@pytest.mark.parametrize("flaws, level, tier, price", [
    (["Screen smashed"], "severe", "middle", 104),  # 170 x (1 - 0.391)
    (["Screen cracked"], "moderate", "middle", 118),  # 170 x (1 - 0.304)
    (["Tiny chip on the corner"], "minor", "middle", 138),  # 170 x (1 - 0.188)
])
def test_damage_is_cut_once_by_how_bad_and_the_models_price_tier(flaws, level, tier, price):
    opener, asked = asking()
    found = prices.estimate("iPhone 13 128GB Blue", flaws, opener=opener, description=". ".join(flaws))
    assert "damage" not in asked[0][2]["kinds"]  # not cut twice: the API's own damage cut isn't asked for
    assert (found["damage"]["level"], found["damage"]["tier"], found["price"], found["cuts"]) == \
        (level, tier, price, ["damage"])


def test_a_locked_or_for_parts_one_keeps_the_apis_price_with_no_damage_cut_of_ours():
    opener, asked = asking()
    found = prices.estimate("iPhone 13 128GB Blue", ["Screen smashed", "iCloud locked"], opener=opener,
                            description="Screen smashed. iCloud locked.")
    assert "damage" in asked[0][2]["kinds"] and "damage" not in found  # priced as locked by the API alone


@pytest.mark.parametrize("sentence, expected", [
    # a repair done and gone, "dead" as slang for very: no phone for parts (the price was the for-parts one)
    ("it went to apple for repair last year", []),
    ("its been in for repairs before under warranty", []),
    ("sent off for repair once, new screen fitted", []),
    ("phone is dead mint", []),
    ("it is dead good", []),
    ("phone is dead easy to use", []),
    # one thing untested is a warning (the API's "sold as seen", cut as wear), not a phone for parts: the same as "not
    # tested on other networks" already was
    ("face id untested", ["wear"]),
    ("esim untested", ["wear"]),
    ("unlocked but untested on other networks", ["wear"]),
    # ...while what's sold for parts still is
    ("FOR REPAIR OR PARTS", ["parts"]),
    ("Sold as faulty/for repair", ["parts"]),
    ("spares or repairs", ["parts"]),
    ("Only for repairs", ["parts"]),
    ("Untested", ["parts"]),
    ("No warranty sold for repairs", ["parts"]),
])
def test_a_past_repair_one_untested_part_or_dead_mint_is_no_phone_for_parts(sentence, expected):
    assert kinds(sentence) == expected


@pytest.mark.parametrize("sentence, expected", [
    ("i cloud locked", ["lock"]),
    ("locked to previous owner", ["lock"]),
    ("its dead", ["parts"]),
    ("it's dead", ["parts"]),
    ("phones dead", ["parts"]),
    ("it wont come on", ["parts"]),
    ("doesnt come on", ["parts"]),
    ("Its just dead you need to replace battery", ["parts"]),
    ("Like new, tiny scratches on one side..Will not come on its original box.", ["wear"]),  # "comes in", typed
    ("Not locked to the previous owner", []),
])
def test_a_lock_or_a_dead_phone_in_common_uk_wording_is_caught(sentence, expected):
    assert kinds(sentence) == expected


@pytest.mark.parametrize("sentence", [
    "rear camera is blurry", "back camera blurry", "touch screen unresponsive in places", "screen is unresponsive",
    "speaker blown", "boot loop", "shuts down randomly", "random shutdowns", "wifi greyed out",
    "people cant hear me on calls", "face id dosent work", "face id dosnt work", "black screen",
    "everything works except face id", "all works apart from face id and true tone",
    "fully working other than the speaker", "face id ❌", "Face ID doesn’t work",
])
def test_a_fault_the_readers_judge_has_no_word_for_still_counts(sentence):
    assert kinds(sentence) == ["fault"]


@pytest.mark.parametrize("sentence, expected", [
    ("camera is not blurry", []),  # a "no" still undoes it
    ("my old phone camera was blurry, this one is perfect", []),  # another phone's
    ("the box is a bit scraped", []),  # the box's
    ("grade c face id not set up", ["wear"]),  # Face ID not set up is no fault
    ("Scratches ❌", []),  # a mark crossed out is "no scratches"
    ("Everything works apart from the speaker grille which is scratched", ["wear"]),  # the grille's scratch
])
def test_what_the_judge_has_no_word_for_is_still_judged(sentence, expected):
    assert kinds(sentence) == expected


def test_a_fault_said_as_the_one_thing_not_working_is_cut_for():
    assert sent("iPhone 13 128GB", ["Everything works except face id"],
                "Everything works except face id. Collection Leeds.") == {"kinds": ["fault"]}


@pytest.mark.parametrize("sentence, expected", [
    ("phone is in good condition has a small crack on the top left corner of the screen", ["damage"]),
    ("selling my iphone 13 in good condition there is a small crack on the back glass from when i dropped it",
     ["damage"]),
    ("the phone works perfect only issue is the face id doesnt work after it was dropped last year", ["fault"]),
    ("upgraded so selling my old phone has some scratches on the screen and the back from general use", ["wear"]),
    # ...but a long one whose every word for a flaw has a "no" is still none
    ("the phone has never had any issues or problems at all since I bought it new in 2021 honestly", []),
])
def test_a_run_on_clause_over_fifteen_words_keeps_its_kinds(sentence, expected):
    assert kinds(sentence) == expected


@pytest.mark.parametrize("sentence, expected", [
    ("screen cracked no box", ["damage"]),
    ("back glass smashed no charger", ["damage"]),
    ("no box no charger face id doesnt work", ["fault"]),
    ("small crack on back always kept in a case no box", ["damage"]),
    ("dropped it without a case and cracked the back", ["damage"]),
    ("used without a case so has a few scratches", ["wear"]),
    ("no case so there are some light scratches on the back", ["wear"]),
    ("missing charger screen has a hairline crack", ["damage"]),
    ("screen cracked no offers", ["damage"]),
    ("back glass smashed no swaps", ["damage"]),
    ("small crack no low ballers please", ["damage"]),
    ("Screen cracked, no box", ["damage"]),
    ("Cracks: no", []),  # a label's answer still denies
])
def test_a_missing_box_or_a_no_offers_beside_a_flaw_leaves_the_flaw(sentence, expected):
    assert kinds(sentence) == expected


def test_a_flaw_with_no_swaps_after_it_is_cut_as_damage():
    assert sent("iPhone 13 128GB", ["Back glass smashed no swaps"], "Back glass smashed no swaps") == \
        {"kinds": ["damage"]}


@pytest.mark.parametrize("sentence, expected", [
    ("screen cracked and broken", ["damage"]),
    ("screen is smashed and broken", ["damage"]),
    ("back glass is cracked and broken", ["damage"]),
    ("broken and cracked screen", ["damage"]),
    ("Volume button is broken", ["fault"]),  # a part that's broken is still a fault
    ("Cracked screen and the volume button is broken", ["damage", "fault"]),
])
def test_one_broken_screen_is_cut_once_as_damage(sentence, expected):
    assert kinds(sentence) == expected


def test_a_cracked_and_broken_screen_is_asked_as_damage_only():
    assert sent("iPhone 13 128GB", ["Screen is cracked and broken but still works"],
                "Screen is cracked and broken but still works") == {"kinds": ["damage"]}


@pytest.mark.parametrize("sentence", [
    "few light scratches on the back no cracks and dents", "few scratches on the back no cracks or visible dents",
    "light scratches no dents or major cracks",
])
def test_a_denied_list_after_a_real_flaw_denies_all_of_it(sentence):
    assert kinds(sentence) == ["wear"]


@pytest.mark.parametrize("sentence", [
    "craked screen", "screen is craked", "chiped corner", "shatterd back glass", "smashd screen", "screen is broke",
    "back glass broke",
])
def test_damage_typed_with_a_slip_or_broke_is_damage(sentence):
    assert kinds(sentence) == ["damage"]


@pytest.mark.parametrize("sentence", [
    "volume button is stuck", "power button doesnt click", "charging port is a bit loose", "only charges wirelessly",
    "screen has a thin line", "screen goes black randomly", "stuck on the apple logo",
])
def test_a_fault_in_other_words_is_a_fault_not_wear(sentence):
    assert kinds(sentence) == ["fault"]


def test_charging_one_way_by_choice_is_no_fault():
    assert kinds("I only charge it wirelessly to protect the port") == []


@pytest.mark.parametrize("sentence, expected", [
    ("battery says service", ["battery"]),
    ("battery shows service", ["battery"]),
    ("Battery health: Service", ["battery"]),
    ("Battery condition: Service Recommended", ["battery"]),
    ("Battery health shows Service Recommended", ["battery"]),
    ("battery health is on service", ["battery"]),
    ("The battery needs servicing.", ["battery"]),
    ("battery dies quickly", ["battery"]),
    # 80% or more is no flaw however soon it may need one, and one that won't hold a charge or has swollen is a fault
    ("battery is 81% and needs replacing soon", []),
    ("doesnt hold charge", ["fault"]),
    ("swollen battery", ["fault"]),
])
def test_a_battery_that_needs_a_service_is_a_battery_flaw(sentence, expected):
    assert kinds(sentence) == expected


@pytest.mark.parametrize("sentence, expected", [
    ("o2 locked", ["network lock"]),
    ("EE locked", ["network lock"]),
    ("vodafone locked", ["network lock"]),
    ("locked EE", ["network lock"]),
    ("will only take EE sims", ["network lock"]),
    ("Not EE locked", []),
])
def test_a_network_named_before_locked_is_a_network_lock(sentence, expected):
    assert kinds(sentence) == expected


@pytest.mark.parametrize("sentence", [
    "grade C", "fair condition", "C grade", "condition fair", "small scrape on the corner", "a few dings on the frame",
    "grade d", "average condition", "scrapes on the corner", "small ding", "nicks",
])
def test_wear_the_judge_has_no_word_for_still_counts(sentence):
    assert kinds(sentence) == ["wear"]


@pytest.mark.parametrize("sentence, expected", [
    ("no face id issues", []), ("no face id problems", []), ("no touch id issues", []), ("no signal issues", []),
    ("no sound issues", []), ("no wifi issues", []), ("no bluetooth problems", []), ("no display issues", []),
    ("no service issues at all", []), ("no signal problems on any network", []),
    ("iPhone 12 Pro 128GB No Face ID", ["fault"]),  # no Face ID at all is still a fault
    ("iPhone 11 no signal", ["fault"]),
    ("No charger screen has issues", ["wear"]),  # the screen's issues aren't denied
])
def test_no_issues_with_a_part_is_a_denial_not_wear(sentence, expected):
    assert kinds(sentence) == expected


@pytest.mark.parametrize("title", [
    "iPhone 12 Pro repairs", "iPhone 12 Pro Max - Repairs", "iPhone XR repair job", "iPhone 8 needs screen repair",
    "iPhone 13 Pro screen repair needed", "MacBook Pro 2019 repair", "Samsung S21 Ultra repairs",
])
def test_a_title_selling_it_for_repairs_is_asked_as_good_with_the_parts_cut(title):
    assert sent(title) == {"kinds": ["parts"], "bucket": "good"}


def test_a_title_with_a_repair_done_or_none_needed_isnt_for_parts():
    assert sent("iPhone 13 Pro, screen repair done") == {"kinds": [], "bucket": "good"}
    assert sent("iPhone 13 Pro, never needed repairs") == {"kinds": [], "bucket": "good"}


@pytest.mark.parametrize("title, kind", [
    ("MacBook Pro 2015 firmware password locked", "lock"), ("MacBook Pro 2018 EFI password", "lock"),
    ("iPhone 12 locked to owner", "lock"), ("Samsung Galaxy A52 KG locked", "lock"), ("iPhone 12 barred", "lock"),
    ("iPhone 11 passcode locked", "lock"), ("iPhone 12 dead", "parts"), ("Dead iPhone 12", "parts"),
    ("iPhone 12 Pro Max - dead", "parts"),
])
def test_a_locked_or_dead_title_in_uk_wording_gets_the_lock_or_parts_price(title, kind):
    assert sent(title) == {"kinds": [kind], "bucket": "good"}


def test_a_title_with_a_dead_pixel_is_still_a_fault():
    assert sent("iPhone 12 dead pixels on screen") == {"kinds": ["fault"]}


@pytest.mark.parametrize("title, expected", [
    ("iPhone 12 not working", ["parts"]), ("MacBook Air not working", ["parts"]),
    ("iPhone 13 128GB not working", ["parts"]), ("iPhone 11 (not working)", ["parts"]),
    ("iPhone 12 Face ID not working", ["fault"]),  # one part not working is a fault
])
def test_a_title_saying_the_whole_device_isnt_working_is_for_parts(title, expected):
    assert sent(title) == {"kinds": expected, "bucket": "good"}


def test_a_real_phone_or_macbook_isnt_refused_for_how_its_case_or_frame_is_named():
    titles = {"iPhone 11 in Otterbox case": "iphone", "iPhone 15 Pro Max always in a case": "iphone",
              "iPhone 12 Pro Max kept in case, mint": "iphone", "iPhone 13 Pro wallet case included": "iphone",
              "iPhone 12 charger and case included": "iphone", "MacBook Air M1 2020 sleeve included": "macbook",
              "MacBook Air M3 keyboard cover included": "macbook",
              "iPhone 14 Pro screen protector fitted since new": "iphone",
              "Samsung Galaxy S21 Ultra cracked frame": "samsung", "Samsung S20 FE bent frame": "samsung",
              "I-phone 13": "iphone", "I-phone 11 64GB": "iphone",
              "iPhone XS Space Grey – Fully Working – Case & Screen Protector Included": "iphone",
              "MacBook Pro 15 inch. Power cable & disc included.": "macbook",
              "iPhone 15 excellent condition included case": "iphone"}
    assert {t: prices.kind_of(t) for t in titles} == titles
    for title in ("iPhone 13 case in black", "iPhone 12 wallet case", "MacBook Pro keyboard cover",
                  "Samsung The Frame 55", "Samsung Galaxy S20 FE fitted case"):
        assert prices.kind_of(title) is None, title  # still the case, the cover, the TV


@pytest.mark.parametrize("text, kind, sizes", [
    ("Storage: 128GB\nRAM: 6GB", "iphone", (128, None)),
    ("Storage 128GB RAM 6GB", "samsung", (128, None)),
    ("Capacity: 256GB\nRAM: 8GB\nColour: Black", "samsung", (256, None)),
    ("Memory: 16GB\nStorage: 512GB", "macbook", (512, 16)),
    ("Processor: M1\nMemory: 8GB\nStorage: 256GB\nBattery cycles: 120", "macbook", (256, 8)),
    ("SSD 512GB RAM 16GB", "macbook", (512, 16)),
    ("Memory 8GB Storage 128GB", "macbook", (128, 8)),
    ("Storage: 128GB\nRAM: 8", "macbook", (128, 8)),
    ("- 8GB\nRAM - 128GB SSD", "macbook", (128, 8)),  # its own word after it beats the label before
    ("8GB RAM 256GB SSD", "macbook", (256, 8)),
    ("12GB RAM 256GB", "samsung", (256, None)),
])
def test_a_spec_lists_next_label_is_the_next_sizes(text, kind, sizes):
    assert prices.sizes_in(text, kind) == sizes


def test_a_spec_lists_sizes_are_sent():
    assert sent("iPhone 13 Blue", description="Storage: 128GB\nRAM: 4GB") == {"kinds": [], "storage_gb": 128}
    assert sent("MacBook Air M1", description="Memory: 8GB\nStorage: 256GB") == \
        {"kinds": [], "storage_gb": 256, "ram_gb": 8}


@pytest.mark.parametrize("text, kind, sizes", [
    ("128 gig", "iphone", (128, None)), ("128gig, battery 90%", "iphone", (128, None)),
    ("64 gig storage", "iphone", (64, None)), ("256 gigs", "iphone", (256, None)),
    ("64 gigabytes", "iphone", (64, None)), ("storage 512", "iphone", (512, None)),
    ("512 storage", "iphone", (512, None)), ("128GB memory", "iphone", (128, None)),
    ("64gb memory, battery 85%", "iphone", (64, None)), ("256GB of memory", "iphone", (256, None)),
    ("8gb ram 256 ssd", "macbook", (256, 8)), ("8 ram 256 ssd", "macbook", (256, 8)),
    ("8gb/256ssd", "macbook", (256, 8)),
    ("iPhone 16 storage 128GB", "iphone", (128, None)),  # the model's number isn't a size
    ("Battery capacity 64%", "iphone", (None, None)),
])
def test_a_size_written_the_uk_way_is_read(text, kind, sizes):
    assert prices.sizes_in(text, kind) == sizes


def test_a_size_written_the_uk_way_is_sent():
    assert sent("iPhone 13 Blue", description="128 gig, battery 90%") == {"kinds": [], "storage_gb": 128}
    assert sent("MacBook Air M1", description="8gb ram 256 ssd") == {"kinds": [], "storage_gb": 256, "ram_gb": 8}


@pytest.mark.parametrize("text, kind, sizes", [
    ("Comes with a 256GB microSD card", "samsung", (None, None)),
    ("Includes 64GB SanDisk card", "samsung", (None, None)),
    ("iCloud storage 2TB", "iphone", (None, None)),
    ("2TB Google Drive", "samsung", (None, None)),
    ("Open to swaps for an iPhone 14 Pro 256GB", "iphone", (None, None)),
    ("Upgraded to the 15 Pro 256GB so selling this one", "iphone", (None, None)),
    ("Would swap for S24 Ultra 512GB", "samsung", (None, None)),
    ("Samsung A52 128GB, comes with 64GB microSD card", "samsung", (128, None)),
    ("No swaps 256GB", "iphone", (256, None)),  # no swap, so it's this one's
    ("Upgraded to 16GB RAM", "macbook", (None, 16)),  # a MacBook's own upgrade
])
def test_another_things_size_isnt_this_listings(text, kind, sizes):
    assert prices.sizes_in(text, kind) == sizes


def test_another_things_size_isnt_sent():
    assert sent("iPhone 13 Pro Graphite", description="Battery 88%. Open to swaps for an iPhone 14 Pro 256GB.") == \
        {"kinds": []}
    assert sent("Samsung Galaxy A52", description="Comes with a 256GB microSD card") == {"kinds": []}


@pytest.mark.parametrize("text, sizes", [
    ("i7 16GB RAM 512GB SSD AMD Radeon Pro 5300M 4GB", (512, 16)),
    ("16GB RAM, 1TB SSD, Radeon Pro 5500M 8GB GDDR6", (1024, 16)),
    ("Radeon Pro 560X 4GB, 16GB RAM, 512GB SSD", (512, 16)),
    ("AMD 5500 4gb Graphics", (None, None)),  # the graphics card's is never the RAM
    ("Core i9 / 32GB / 500GB / Radeon Pro 555X 4GB", (None, 32)),
])
def test_a_macbooks_graphics_memory_isnt_its_ram(text, sizes):
    assert prices.sizes_in(text, "macbook") == sizes


def test_a_macbooks_ram_is_sent_with_its_graphics_memory_named():
    assert sent("MacBook Pro 16 2019", description="i7, 16GB RAM, 512GB SSD, Radeon Pro 5300M 4GB") == \
        {"kinds": [], "storage_gb": 512, "ram_gb": 16}


@pytest.mark.parametrize("text, kind, sizes", [
    ("64/128GB", "iphone", (None, None)),  # two sizes on offer
    ("128/256GB", "iphone", (None, None)),
    ("Either 128/256 GB (can't remember)", "iphone", (None, None)),
    ("16/32GB All Colours", "iphone", (None, None)),
    ("8/128", "samsung", (128, None)),  # its RAM and its storage
    ("12/256", "samsung", (256, None)),
    ("16/512", "samsung", (512, None)),
    ("iPhone 16/128GB", "iphone", (128, None)),
    ("M3 Max 128GB 2TB", "macbook", (2048, 128)),
    ("M1 Max 64GB 2TB", "macbook", (2048, 64)),
    ("MacBook Air 2012 64GB SSD 4GB RAM", "macbook", (64, 4)),
])
def test_two_sizes_on_offer_are_neither_and_a_big_macbooks_ram_is_its_ram(text, kind, sizes):
    assert prices.sizes_in(text, kind) == sizes


@pytest.mark.parametrize("sentence, expected", [
    ("battery health 78% no scratches or cracks", ["battery"]),  # the "no" starts a denial of its own
    ("Screen cracked no other issues", ["damage"]),  # ...or says nothing else is wrong
    ("screen cracked no box no charger", ["damage"]),  # ...or is about what comes with it
    ("Cracks: no", []),  # a label's answer
    ("Back glass slightly damaged from when it was previously looked at for repair", ["damage"]),  # a repair gone by
    ("Everything works fine but not face id", ["fault"]),
])
def test_a_no_after_a_flaw_denies_it_only_as_a_labels_answer(sentence, expected):
    assert kinds(sentence) == expected


# ── 6 Oct second check ─────────────────────────────────────────────────────────────────────────────────────────────
# The first fix round's checker found what its fixes broke and what they left (each test below says which). Every
# input of its scripts (check_findings.py, probe_breakage.py) and every case its report quotes is a test here too, each
# with its right answer (the tables at the end), so neither the first round's fixes nor what they broke can come back.

def mac_kinds(sentence, title="MacBook Air M1"):
    """The kinds one flaw sentence gives, read in a MacBook's listing."""
    return prices.kinds_of([sentence], f"{title}. " + sentence)


@pytest.mark.parametrize("sentence", [
    "untested for parts", "Untested for parts", "UNTESTED FOR PARTS OR REPAIR", "untested for repair",
    "untested for repairs", "Sold untested for parts only", "Sold untested for parts or repair", "Untested, for parts",
    # the phone itself untested, whatever follows the word
    "Phone untested by me as I have no sim", "Untested on charge", "Untested with a sim", "untested in the UK",
    "Phone is untested as I have no charger",
])
def test_untested_for_parts_or_the_phone_itself_untested_is_for_parts(sentence):
    assert kinds(sentence) == ["parts"]  # was wear: "untested for" was read as one part untested


def test_untested_with_a_warning_beside_it_is_for_parts_and_the_warning():
    assert kinds("Untested by me, bought as is") == ["parts", "wear"]


@pytest.mark.parametrize("title", ["iPhone 11 Pro untested for parts", "MacBook Pro 2017 untested for parts",
                                   "iPhone 13 Pro Max untested for parts", "iPhone 11 untested"])
def test_a_title_untested_for_parts_is_asked_as_good_with_the_parts_cut(title):
    assert sent(title) == {"kinds": ["parts"], "bucket": "good"}


@pytest.mark.parametrize("sentence", [
    "untested on other networks", "untested on EE", "untested with other sims", "Untested abroad", "Network untested",
])
def test_one_thing_untested_is_still_a_warning_not_a_phone_for_parts(sentence):
    assert kinds(sentence) == ["wear"]  # the first round's choice (finding #0), kept


@pytest.mark.parametrize("sentence, expected", [
    ("Taken to a shop for repair but they couldnt fix it", ["parts"]),
    ("Taken to a repair shop for repair but they couldn't fix it", ["parts"]),
    ("Sent off for repair, Apple said it is not worth fixing", ["parts"]),
    ("Sent for repair but they said the logic board is dead", ["parts", "wear"]),
    ("Booked in for repair but changed my mind", ["parts"]),
    ("Went in for repair and came back worse, now selling for parts", ["parts"]),
    ("Went in for repair but the repair failed", ["parts"]),
    ("Was sent for repair but too expensive to fix", ["parts"]),
    ("It was taken for repair but they said not worth it", ["parts"]),
    ("Taken in for a repair and now it's still not working", ["parts", "fault"]),
    # ...while one part that couldn't be fixed is that part's fault, and a repair that worked is none
    ("Taken in for repair, they couldn't fix the Face ID", ["fault"]),
    ("Sent for repair, they couldn't fix the speaker", ["fault"]),
    ("Sent for repair, Face ID can't be fixed", ["fault"]),
    ("Taken to Apple for repair last year, works perfectly", []),
    ("Went in for repair, fixed under warranty", []),
    ("Sent off for repair, came back perfect", []),
])
def test_a_repair_that_failed_or_didnt_happen_is_one_for_repairs(sentence, expected):
    assert kinds(sentence) == expected  # the failed ones were priced as clean


def test_a_quote_cut_before_the_repair_failed_is_read_with_the_rest_of_its_sentence():
    assert prices.kinds_of(["Taken to a shop for repair"],
                           "iPhone 13 128GB. Taken to a shop for repair but they couldnt fix it.") == ["parts"]


@pytest.mark.parametrize("title", [
    "iPhone 12 Pro Max (had screen repair)", "iPhone 13 - professional screen repair",
    "iPhone 11 128GB new screen repair", "iPhone XR after battery repair", "iPhone 13 Pro 256GB, Apple repair",
    "iPhone 12 - genuine Apple screen repair", "iPhone 12 Pro, had screen repair",
    "iPhone 12 Pro 256GB after screen repair", "iPhone 12 with screen repair",
])
def test_a_title_naming_a_repair_it_has_had_isnt_for_parts(title):
    # was the for-parts price. "good": the API, left to read "repair" from the title, finds no sales
    assert sent(title) == {"kinds": [], "bucket": "good"}


@pytest.mark.parametrize("title, expected", [
    ("iPhone 13 128GB screen repaired", {"kinds": []}), ("iPhone 12 repaired by Apple", {"kinds": []}),
    ("iPhone 13 Pro, needs genuine Apple screen repair", {"kinds": ["parts"], "bucket": "good"}),  # one it needs
    ("iPhone 12 for new screen repair", {"kinds": ["parts"], "bucket": "good"}),
    ("iPhone 12 with screen repair needed", {"kinds": ["parts"], "bucket": "good"}),
])
def test_a_title_with_a_repair_done_or_needed_is_asked_as_it_says(title, expected):
    assert sent(title) == expected


@pytest.mark.parametrize("sentence", [
    "Torch won't come on", "The flash wont come on", "Backlight doesnt come on",
    "Flash doesn't come on when taking photos", "Wifi won't turn on", "Bluetooth won't switch on",
    "Camera won't turn on",
])
def test_a_part_that_wont_come_on_is_that_parts_fault_not_a_dead_phone(sentence):
    assert kinds(sentence) == ["fault"]  # was for parts


@pytest.mark.parametrize("sentence", ["Keyboard backlight doesn't come on", "Charging light doesn't come on"])
def test_a_macbooks_light_that_wont_come_on_is_a_fault(sentence):
    assert mac_kinds(sentence) == ["fault"]


def test_a_phone_or_its_screen_that_wont_come_on_is_still_for_parts():
    for sentence in ("it won't come on", "Phone won't come on", "Screen won't come on", "Won't turn on"):
        assert kinds(sentence) == ["parts"], sentence
    assert sent("iPhone 12 torch wont come on") == {"kinds": ["fault"]}  # its title: the torch's fault


@pytest.mark.parametrize("sentence, expected", [
    ("Cracks: no Scratches: yes", ["wear"]), ("Cracks no Scratches minor", ["wear"]),
    ("Dents: no Scuffs: few", ["wear"]), ("Screen cracks no back scratches yes", ["wear"]),
    ("Cracks: no\nScratches: minor", ["wear"]), ("Cracks no, scratches light", ["wear"]),
    ("Cracks no scratches yes", ["wear"]), ("Cracks no dents no scratches minor", ["wear"]),
    ("Cracks: no Scratches: minor", ["wear"]), ("Scratches: light Cracks: no", ["wear"]),
    ("Dents no scratches a few", ["wear"]), ("Cracks - no, Scratches - light", ["wear"]),
    ("Cracks - no Scratches - light", ["wear"]), ("Scratches: yes Cracks: no", ["wear"]),
    ("Cracks no Scratches yes Dents no", ["wear"]), ("Cracks: No Scratches: No Dents: Yes", ["damage"]),
    ("Dents: no Cracks - minor", ["damage"]), ("Face ID: working Camera: blurry", ["fault"]),
    # ...every answer a "no": none (they gave wear, as the judge called the line a flaw)
    ("Cracks no Scratches no", []), ("Cracks no scratches no dents no", []),
    ("Cracks: No Scratches: No Dents: No", []), ("Scratches no", []), ("Damage: no cracks", []),
    # ...while a "no" that starts a denial of its own still leaves the flaw before it, and what's another thing's is
    # still no flaw
    ("light scratches no dents", ["wear"]), ("Scratches no cracks no dents", ["wear"]),
    ("small dent no scratches no", ["damage"]), ("battery health 78% no scratches or cracks", ["battery"]),
    ("Box: damaged Phone: mint", []), ("Screen protector: cracked Screen: perfect", []),
    ("Cracks - no Dents no", []),
    ("Scratches - no cracks, Battery: 85%", ["wear"]),  # a lone " - no cracks" is a denial of its own
])
def test_a_line_of_labels_counts_each_label_by_its_own_answer(sentence, expected):
    assert kinds(sentence) == expected  # mixed answers gave damage, not wear


@pytest.mark.parametrize("title", [
    "MacBook Pro charger and cable included", "iPhone 13 charger cable included",
    "Genuine Apple MacBook charger, cable included", "Samsung Galaxy S23 charger and plug included",
    "MacBook charger and cable included", "MacBook Pro 61W charger and cable included", "MacBook Air 13 in case",
    "MacBook Pro 16 in sleeve",
])
def test_a_charger_with_its_own_cable_or_a_13_inch_case_isnt_asked_about(title):
    opener, asked = asking()
    assert prices.estimate(title, opener=opener) == {"skipped": prices.SKIPPED}
    assert not asked  # no call spent pricing a charger as the device


def test_a_device_with_its_charger_or_case_still_is():
    titles = {"MacBook Air M1 2020, charger included": "macbook", "iPhone 13 charger included": "iphone",
              "iPhone 13, charger and cable included": "iphone", "iPhone 13 with charger and cable included": "iphone",
              "Samsung Galaxy S23 Ultra 256GB charger and cable included": "samsung",
              "iPhone 12 charger and case included": "iphone", "MacBook Pro 13 in Space Grey": "macbook",
              "MacBook Pro 2019 in case": "macbook", "iPhone 11 in Otterbox case": "iphone"}
    assert {t: prices.kind_of(t) for t in titles} == titles


@pytest.mark.parametrize("text, sizes", [
    ("M1 8-core CPU 7-core GPU 8GB RAM 256GB SSD", (256, 8)), ("M2 Pro 10-core CPU 16-core GPU 16GB 512GB", (512, 16)),
    ("Intel UHD Graphics 617 8GB RAM 128GB SSD", (128, 8)), ("Intel Iris Plus Graphics 645 8GB 256GB", (256, 8)),
    ("M1 Pro 14-core GPU 16GB 512GB", (512, 16)), ("Radeon Pro 560X 16GB RAM 512GB SSD", (512, 16)),
    ("NVIDIA GeForce GT 750M 2GB 16GB RAM 512GB", (512, 16)), ("AMD Radeon Pro 5500M 8GB 16GB 1TB", (1024, 16)),
])
def test_a_macbooks_sizes_after_its_chips_own_graphics_are_read(text, sizes):
    assert prices.sizes_in(text, "macbook") == sizes  # were (None, None): read as graphics memory


@pytest.mark.parametrize("sentence, expected", [
    ("Midnight black screen and back perfect", []),  # the colour, not a fault
    ("Everything works apart from the camera, which has a scratch on the lens", ["wear"]),  # its scratch, no fault
    ("Box ✅ Charger ❌ Sim card ❌", []),  # what comes with it, not a SIM fault
    ("Box ✅ Charger ✅ Sim ❌", []), ("Box ✅ Charger ❌ Face ID ❌", ["fault"]),
    ("Previously EE locked, now unlocked", []), ("Was EE locked but has been unlocked", []),
    ("Previously locked to O2", []), ("EE locked, now unlocked", []),
    ("Locked to Three but can be unlocked", ["network lock"]),  # still locked
    # the seller's own network, the phone's as far as a buyer knows: a lock under the owner's carrier rule (6 Oct)
    ("I only use EE so can't test other sims", ["wear", "network lock"]), ("I only use EE", ["network lock"]),
    ("Phone dead clean IMEI", ["parts"]),  # dead, with a clean IMEI: not "dead clean"
    ("Battery goes dead quick", ["battery"]),  # not "dead quick" as UK slang
])
def test_the_first_rounds_smaller_misreads_are_put_back(sentence, expected):
    assert kinds(sentence) == expected


def test_a_dead_title_with_a_clean_imei_is_for_parts_and_a_part_exchanges_size_is_its_own():
    assert sent("iPhone 11 dead clean imei") == {"kinds": ["parts"], "bucket": "good"}
    assert prices.sizes_in("Will consider part exchange 128GB", "iphone") == (128, None)  # no other model named
    assert prices.sizes_in("Swaps considered 256GB", "iphone") == (256, None)
    assert prices.sizes_in("Swap for iPhone 15 128GB considered", "iphone") == (None, None)


def test_the_monthly_cap_is_said_as_that_not_as_a_moments_wait():
    def refusing(message):
        def opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 503, "x", {}, io.BytesIO(json.dumps(
                {"error": {"code": "UNAVAILABLE", "message": message}}).encode()))
        return opener
    said = prices.estimate("iPhone 13 mini 512GB", [], opener=refusing("New price checks are paused until next month."),
                           description="Works perfectly.")
    assert said == {"error": "New price checks are paused until next month: models checked before can still be priced"}
    assert prices.estimate("iPhone 13 mini 512GB", opener=refusing("Busy, try again"))["error"] == \
        prices.REFUSED["UNAVAILABLE"]  # a moment's wait is still one
    assert prices.refused("UNAVAILABLE", 503) == {"error": prices.REFUSED["UNAVAILABLE"]}

    def answering(request, timeout):  # the same refusal said with no error status
        return Response(json.dumps({"error": {"code": "UNAVAILABLE", "message": "Paused until next month"}}).encode())
    assert prices.estimate("iPhone 13 mini 256GB", opener=answering)["error"] == prices.MONTHLY_CAP


@pytest.mark.parametrize("sentence", ["Minuscule nick", "nick on the corner", "Small nick on the corner",
                                      "A nick on the frame"])
def test_a_single_nick_is_wear(sentence):
    assert kinds(sentence) == ["wear"]  # was none: the judge has no word for it


@pytest.mark.parametrize("text, kind, sizes", [
    ("Capacity 256", "iphone", (256, None)), ("Capacity: 256", "iphone", (256, None)),
    ("Storage capacity 128", "iphone", (128, None)), ("Internal capacity 512", "samsung", (512, None)),
    ("Battery capacity 88", "iphone", (None, None)), ("battery capacity 64", "iphone", (None, None)),
    ("iPhone 6 16GB memory", "iphone", (16, None)),  # no iPhone has 16GB of RAM
    ("Galaxy S21 Ultra 16GB memory 512GB", "samsung", (512, None)),  # ...a Samsung can
])
def test_a_size_labelled_capacity_is_read_but_a_batterys_isnt(text, kind, sizes):
    assert prices.sizes_in(text, kind) == sizes


@pytest.mark.parametrize("sentence, expected", [
    ('Battery health: "Service"', ["battery"]), ('Battery says "service"', ["battery"]),
    ("battery health - service", ["battery"]), ("Battery health shows 'Service'", ["battery"]),
    ("Battery service done", []), ("Battery service at Apple last month", []),  # a service done is none
])
def test_a_battery_service_in_quotes_or_after_a_dash_is_a_battery_flaw(sentence, expected):
    assert kinds(sentence) == expected


@pytest.mark.parametrize("sentence, expected", [
    ("Dead battery, needs replacing", ["battery"]), ("Dead battery", ["battery"]),
    ("Cracked screen, needs replacing", ["damage"]),  # what the flaw before it needs is no flaw of its own
    ("No signal at all, maybe needs a new antenna", ["fault"]), ("Battery health 75%, needs replacing", ["battery"]),
    ("Needs new screen", ["damage"]), ("Needs a new back glass", ["damage"]), ("Needs a new screen protector", []),
    ("Cracking condition, no marks", []), ("In cracking condition", []),
    ("Had it in for repairs, couldn't fault it since", []),  # UK praise
    ("Dosent have any scratches", []), ("Phone dosnt have any dents", []),  # "doesn't" typed with a slip
    ("Selling as repairs", ["parts"]), ("Screen goes black when on a call", ["fault"]),
])
def test_what_a_flaw_sentence_says_in_uk_wording(sentence, expected):
    assert kinds(sentence) == expected


@pytest.mark.parametrize("title, expected", [
    ("iPhone 12 dead battery", {"kinds": ["battery"]}),  # the battery's, as "Dead battery" in a description
    ("MacBook Air M1 not working properly", {"kinds": ["fault"], "bucket": "good"}),  # working badly: a fault
    ("iPhone 12 not working properly", {"kinds": ["fault"], "bucket": "good"}),
    ("iPhone 12 previously EE locked now unlocked", {"kinds": []}),
    ("iPhone 12 wifi won't turn on", {"kinds": ["fault"]}),
    ("MacBook Air M1 needs new screen", {"kinds": ["damage"]}),
])
def test_a_titles_own_words_in_uk_wording(title, expected):
    assert sent(title) == expected


# every input of the second check (its check_findings.py and probe_breakage.py), each with its right answer
RECHECK_KINDS = [  # the findings' sentences: (sentence, kinds), read in "iPhone 13 128GB. <sentence>"
    # #0 a past repair, one part untested, "dead mint"
    ("it went to apple for repair last year", []),
    ("its been in for repairs before under warranty", []),
    ("sent off for repair once, new screen fitted", []),
    ("phone is dead mint", []),
    ("it is dead good", []),
    ("phone is dead easy to use", []),
    ("face id untested", ["wear"]),
    ("esim untested", ["wear"]),
    ("unlocked but untested on other networks", ["wear"]),
    ("Casing: The side casing is a little bit damaged from when it was previously looked at for repair (it was never "
     "fully fixed by the repair shop).",
     ["damage"]),
    ("Network untested", ["wear"]),
    ("AppleCare+ until 2027 for peace of mind for repairs and support", []),
    ("FOR REPAIR OR PARTS", ["parts"]),
    ("Sold as faulty/for repair", ["parts"]),
    ("spares or repairs", ["parts"]),
    ("Only for repairs", ["parts"]),
    ("Untested", ["parts"]),
    ("No warranty sold for repairs", ["parts"]),
    # #1 a lock or a dead phone in UK wording
    ("i cloud locked", ["lock"]),
    ("locked to previous owner", ["lock"]),
    ("its dead", ["parts"]),
    ("it's dead", ["parts"]),
    ("phones dead", ["parts"]),
    ("it wont come on", ["parts"]),
    ("doesnt come on", ["parts"]),
    ("iPhone is dead", ["parts"]),
    ("It's completely dead", ["parts"]),
    ("Phone won't come on", ["parts"]),
    ("Its just dead you need to replace battery", ["parts"]),
    ("Locked to the previous owner", ["lock"]),
    ("doesnt come on and i advise using for parss", ["parts"]),
    ("Like new, tiny scratches on one side..Will not come on its original box.", ["wear"]),
    ("it's dead at the moment, needs charging", ["wear"]),
    # #2 a fault the judge has no word for
    ("rear camera is blurry", ["fault"]),
    ("back camera blurry", ["fault"]),
    ("touch screen unresponsive in places", ["fault"]),
    ("screen is unresponsive", ["fault"]),
    ("speaker blown", ["fault"]),
    ("boot loop", ["fault"]),
    ("shuts down randomly", ["fault"]),
    ("random shutdowns", ["fault"]),
    ("wifi greyed out", ["fault"]),
    ("people cant hear me on calls", ["fault"]),
    ("face id dosent work", ["fault"]),
    ("face id dosnt work", ["fault"]),
    ("black screen", ["fault"]),
    ("everything works except face id", ["fault"]),
    ("all works apart from face id and true tone", ["fault"]),
    ("fully working other than the speaker", ["fault"]),
    ("face id ❌", ["fault"]),
    ("camera is blurry", ["fault"]),
    ("camera blurry", ["fault"]),
    ("blurry camera", ["fault"]),
    ("camera is shaky", ["fault"]),
    ("shaky camera", ["fault"]),
    ("unresponsive", ["fault"]),
    ("bootloop", ["fault"]),
    ("randomly shuts down", ["fault"]),
    ("patches on the screen", ["fault"]),
    ("shadows on the screen", ["fault"]),
    ("blotches on the screen", ["fault"]),
    ("no backlight", ["fault"]),
    ("fully functional apart from Face ID", ["fault"]),
    ("Everything on phone works fine but not face id scan.", ["fault"]),
    ("burnin on the screen", ["damage"]),
    ("liquid spill", ["damage"]),
    ("Please be aware that Face ID is not working and the LiDAR camera has an issue.", ["fault"]),
    ("Original box, slightly damaged", []),
    ("Front camera is blurry", ["fault"]),
    # #3 a run-on clause over 15 words
    ("phone is in good condition has a small crack on the top left corner of the screen", ["damage"]),
    ("selling my iphone 13 in good condition there is a small crack on the back glass from when i dropped it",
     ["damage"]),
    ("the phone works perfect only issue is the face id doesnt work after it was dropped last year", ["fault"]),
    ("upgraded so selling my old phone has some scratches on the screen and the back from general use", ["wear"]),
    ("Perfect condition other than a v small crack on the back of the device and a small black dot on the screen and "
     "the sound is a bit low .",
     ["damage", "fault"]),
    ("Small scratch on the screen as seen in the photos and small pixel broken in the bottom left corner.",
     ["wear", "fault"]),
    ("Overall good condition Just have small crack on the side as you can see in the pictures", ["damage"]),
    # #4 a missing box or a "no offers" beside a flaw
    ("screen cracked no box", ["damage"]),
    ("back glass smashed no charger", ["damage"]),
    ("no box no charger face id doesnt work", ["fault"]),
    ("small crack on back always kept in a case no box", ["damage"]),
    ("dropped it without a case and cracked the back", ["damage"]),
    ("used without a case so has a few scratches", ["wear"]),
    ("no case so there are some light scratches on the back", ["wear"]),
    ("missing charger screen has a hairline crack", ["damage"]),
    ("screen cracked no offers", ["damage"]),
    ("back glass smashed no swaps", ["damage"]),
    ("small crack no low ballers please", ["damage"]),
    ("In mint condition without box screens cracked and sim tray is missing.", ["damage"]),
    ("Cracked edges as pictured and missing s pen", ["damage"]),
    ("Screen cracked no other issue", ["damage"]),
    ("smashed screen untested no charger", ["damage", "parts"]),
    ("Excellent condition,battery health 79% no scratches or cracks.", ["battery"]),
    ("No charger- locked to EE", ["network lock"]),
    ("Charger missing", []),
    ("Cracks: no", []),
    # #5 one broken screen, cut once
    ("screen cracked and broken", ["damage"]),
    ("screen is smashed and broken", ["damage"]),
    ("back glass is cracked and broken", ["damage"]),
    ("broken and cracked screen", ["damage"]),
    ("Volume button is broken", ["fault"]),
    ("Cracked screen and the volume button is broken", ["damage", "fault"]),
    ("Back Glass: Cracked/broken on the back (cameras are intact and working).", ["damage"]),
    ("The front screen/LCD is severely cracked and broken, touch still works", ["damage"]),
    ("Heavily broken and shattered back glass, cameras fine", ["damage"]),
    # #6 a denied list after a real flaw
    ("few light scratches on the back no cracks and dents", ["wear"]),
    ("few scratches on the back no cracks or visible dents", ["wear"]),
    ("light scratches no dents or major cracks", ["wear"]),
    ("The phone has been well looked after, with only light signs of use and no cracks or major damage.", ["wear"]),
    # #7 damage typed with a slip
    ("craked screen", ["damage"]),
    ("screen is craked", ["damage"]),
    ("chiped corner", ["damage"]),
    ("shatterd back glass", ["damage"]),
    ("smashd screen", ["damage"]),
    ("screen is broke", ["damage"]),
    ("back glass broke", ["damage"]),
    ("great phone back is broke but doesnt affect the use of this phone at all", ["damage"]),
    ("Screen broke top right of screen", ["damage"]),
    ("Small crqck top left screen, doesn't affect in anyway", ["damage"]),
    ("Good condition but just craks on the back camera is good", ["damage"]),
    # #8 a fault in other words
    ("volume button is stuck", ["fault"]),
    ("power button doesnt click", ["fault"]),
    ("charging port is a bit loose", ["fault"]),
    ("only charges wirelessly", ["fault"]),
    ("screen has a thin line", ["fault"]),
    ("screen goes black randomly", ["fault"]),
    ("stuck on the apple logo", ["fault"]),
    ("The charging port is a bit loose.", ["fault"]),
    ("Can only charge with wireless charger", ["fault"]),
    ("Does only charge wirelessly", ["fault"]),
    ("Home button is a little loose.", ["fault"]),
    ("Black screen/display issue", ["fault"]),
    ("Repair because it gets stuck on the Apple logo and does not fully boot.", ["fault"]),
    ("Charging port is slightly loose", ["fault"]),
    ("Volume button stuck", ["fault"]),
    ("Power button is stuck", ["fault"]),
    ("Screen goes black", ["fault"]),
    ("Stuck on Apple logo", ["fault"]),
    ("Only charges on MagSafe", ["fault"]),
    ("Scratch on the back, volume button is stuck", ["wear", "fault"]),
    ("Phone won’t turn on", ["parts"]),
    ("Face ID doesn’t work", ["fault"]),
    # #9 a battery that needs a service
    ("battery says service", ["battery"]),
    ("battery shows service", ["battery"]),
    ("battery dies quickly", ["battery"]),
    ("Battery health: Service", ["battery"]),
    ("Battery condition: Service Recommended", ["battery"]),
    ("Battery health shows Service Recommended", ["battery"]),
    ("battery health is on service", ["battery"]),
    ("The battery needs servicing.", ["battery"]),
    ("battery is 81% and needs replacing soon", []),
    ("battery 82% will need replacing soon", []),
    ("doesnt hold charge", ["fault"]),
    ("battery doesnt hold charge", ["fault"]),
    ("swollen battery", ["fault"]),
    # #10 a network named before "locked"
    ("o2 locked", ["network lock"]),
    ("EE locked", ["network lock"]),
    ("vodafone locked", ["network lock"]),
    ("locked EE", ["network lock"]),
    ("will only take EE sims", ["network lock"]),
    ("Phone is EE locked.", ["network lock"]),
    ("Vodafone locked", ["network lock"]),
    ("O2 locked sim.", ["network lock"]),
    ("Will only work with an O2 SIM card unless unlocked.", ["network lock"]),
    ("It is Vodafone locked, small scratch on the back", ["network lock", "wear"]),
    ("Not EE locked", []),
    ("Unlocked EE", []),
    # #11 wear the judge has no word for
    ("grade C", ["wear"]),
    ("fair condition", ["wear"]),
    ("C grade", ["wear"]),
    ("condition fair", ["wear"]),
    ("small scrape on the corner", ["wear"]),
    ("a few dings on the frame", ["wear"]),
    ("grade d", ["wear"]),
    ("average condition", ["wear"]),
    ("scrapes on the corner", ["wear"]),
    ("small ding", ["wear"]),
    ("nicks", ["wear"]),
    ("Minuscule nick", ["wear"]),
    # #12 "no face id issues"
    ("no face id issues", []),
    ("no face id problems", []),
    ("no touch id issues", []),
    ("no signal issues", []),
    ("no sound issues", []),
    ("no wifi issues", []),
    ("no bluetooth problems", []),
    ("no display issues", []),
    ("no service issues at all", []),
    ("no signal problems on any network", []),
    ("Screen works perfectly with no display issues", []),
    ("Fully operational with no display faults", []),
    ("iPhone 12 Pro 128GB No Face ID", ["fault"]),
    ("iPhone 11 no signal", ["fault"]),
    # the probe's own
    ("Spares/repairs", ["parts"]),
    ("Selling for spares or repair", ["parts"]),
    ("For parts only", ["parts"]),
    ("Needs repair", ["parts"]),
    ("Won't turn on", ["parts"]),
    ("Does not power on", ["parts"]),
    ("Not turning on, for repair", ["parts"]),
    ("Sold as not working", ["parts"]),
    ("Phone is untested as I have no charger", ["parts"]),
    ("untested for parts", ["parts"]),
    ("Sold untested for parts or repair", ["parts"]),
    ("Untested, for parts", ["parts"]),
    ("untested for repair", ["parts"]),
    ("Phone untested by me as I have no sim", ["parts"]),
    ("Taken to a repair shop for repair but they couldn't fix it", ["parts"]),
    ("iCloud locked, for parts", ["lock", "parts"]),
    ("Activation locked, sold for parts", ["lock", "parts"]),
    ("no repairs", []),
    ("Never had any repairs", []),
    ("not iCloud locked", []),
    ("Find My is off", []),
    ("Find My iPhone turned off", []),
    ("Not activation locked", []),
    ("No cracks or scratches", []),
    ("No dents, no scratches", []),
    ("Never been repaired", []),
    ("No faults whatsoever", []),
    ("Battery health 100%", []),
    ("unlocked to all networks", []),
    ("Not network locked", []),
    ("IMEI clean, not barred", []),
    ("Not blacklisted", []),
    ("No firmware password", []),
    ("No iCloud lock", []),
    ("Fully working no issues", []),
    ("Screen perfect, no dead pixels", []),
    ("No Face ID issues", []),
    ("Cracks no Scratches no", []),
    ("Cracks: No Scratches: No Dents: No", []),
    ("Never been dropped or cracked", []),
    ("No knox guard", []),
    ("Not passcode locked", []),
    ("Not dead, just needs charging", []),
    ("Cracks no scratches yes", ["wear"]),
    ("Cracks no dents no scratches minor", ["wear"]),
    ("Cracks: no Scratches: minor", ["wear"]),
    ("Scratches: light Cracks: no", ["wear"]),
    ("Dents no scratches a few", ["wear"]),
    ("Cracks - no, Scratches - light", ["wear"]),
    ("Screen was replaced by Apple last year so it's genuine", []),
    ("Back glass is cracked but doesn't affect use", ["damage"]),
    ("Few marks on the frame from my case", ["wear"]),
    ("Locked to Three but can be unlocked", ["network lock"]),
    ("Was on EE but has been unlocked", []),
    ("Previously EE locked, now unlocked", []),
    ("I only use EE so can't test other sims", ["wear", "network lock"]),  # the owner's carrier rule (6 Oct)
    ("Face ID stopped working after a drop", ["fault"]),
    ("Screen has a small chip in the corner", ["damage"]),
    ("Battery health 76% so will need a new one soon", ["battery"]),
    ("Charging port is loose and only charges at an angle", ["fault"]),
    ("Torch won't come on", ["fault"]),
    ("Flash doesn't come on when taking photos", ["fault"]),
    ("Battery goes dead quick", ["battery"]),
    ("Phone dead clean IMEI", ["parts"]),
    ("Cracking condition, no marks", []),
    ("In cracking condition", []),
    ("Speaker crackled once on a call", ["fault"]),
    ("Midnight black screen and back perfect", []),
    ("Everything works apart from the camera, which has a scratch on the lens", ["wear"]),
    ("Box ✅ Charger ❌ Sim card ❌", []),
    ("AppleCare+ covers repairs until 2027", []),
    ("Selling as repairs", ["parts"]),
    ("Needs new screen", ["damage"]),
    ("Dead battery, needs replacing", ["battery"]),
    ("Screen goes black when on a call", ["fault"]),
    ("The screen protector is cracked but the screen underneath is perfect", []),
    ("Minor scuff on the corner, otherwise mint", ["wear"]),
    ("Small dent on the bottom near the charging port", ["damage"]),
    ("Dosent have any scratches", []),
    ("Has had a third party screen fitted", ["not genuine"]),
    ("Unknown part message for the battery", ["not genuine"]),
    ("Battery health shows 'Service'", ["battery"]),
    ("Bent slightly but works fine", ["damage"]),
    ("No signal at all, maybe needs a new antenna", ["fault"]),
    ("Water damaged, selling as spares", ["damage", "parts"]),
]

RECHECK_MAC_KINDS = [  # (sentence, title, kinds): read in "<title>. <sentence>"
    ("The laptop works fine apart from the screen being cracked and broken.", "MacBook Air M1", ["damage"]),
    ("Keyboard backlight doesn't come on", "MacBook Air M1", ["fault"]),
    ("Hinge is a bit stiff", "MacBook Air M1", ["fault"]),
]

RECHECK_SIZES = [  # (text, kind, (storage_gb, ram_gb))
    # #17 a spec list's labels
    ("Storage: 128GB\nRAM: 6GB", "iphone", (128, None)),
    ("Storage 128GB RAM 6GB", "samsung", (128, None)),
    ("Capacity: 256GB\nRAM: 8GB\nColour: Black", "samsung", (256, None)),
    ("Memory: 16GB\nStorage: 512GB", "macbook", (512, 16)),
    ("Processor: M1\nMemory: 8GB\nStorage: 256GB\nBattery cycles: 120", "macbook", (256, 8)),
    ("SSD 512GB RAM 16GB", "macbook", (512, 16)),
    ("Memory 8GB Storage 128GB", "macbook", (128, 8)),
    ("Storage: 256GB\nRAM: 8GB", "samsung", (256, None)),
    ("ROM 512GB\nRAM 12GB", "samsung", (512, None)),
    ("MacBook Air M1\nStorage: 512GB\nMemory: 16GB", "macbook", (512, 16)),
    ("Storage: 128GB\nRAM: 8", "macbook", (128, 8)),
    ("Storage: 256GB, RAM: 8GB", "samsung", (256, None)),
    ("RAM: 8GB\nStorage: 256GB", "samsung", (256, None)),
    ("Storage: 128GB\nBattery health: 88%", "iphone", (128, None)),
    ("8GB RAM\n256GB SSD", "macbook", (256, 8)),
    ("- 8GB\nRAM - 128GB SSD", "macbook", (128, 8)),
    ("Memory: 32 GB\nStorage: 1TB", "macbook", (1024, 32)),
    ("Storage: 1TB\nMemory: 16 GB", "macbook", (1024, 16)),
    ("Storage 256GB\nRAM 8GB", "samsung", (256, None)),
    ("RAM 32 GB\nSSD 512 GB", "macbook", (512, 32)),
    ("RAM 32 GB\nSSD 512 GB\nRadeon 555X 4GB", "macbook", (512, 32)),
    # #18 a size written the UK way
    ("128 gig", "iphone", (128, None)),
    ("128gig, battery 90%", "iphone", (128, None)),
    ("64 gig storage", "iphone", (64, None)),
    ("256 gigs", "iphone", (256, None)),
    ("64 gigabytes", "iphone", (64, None)),
    ("storage 512", "iphone", (512, None)),
    ("512 storage", "iphone", (512, None)),
    ("128GB memory", "iphone", (128, None)),
    ("64gb memory, battery 85%", "iphone", (64, None)),
    ("256GB of memory", "iphone", (256, None)),
    ("8gb ram 256 ssd", "macbook", (256, 8)),
    ("8 ram 256 ssd", "macbook", (256, 8)),
    ("8gb/256ssd", "macbook", (256, 8)),
    ("storage is 128", "iphone", (128, None)),
    ("Capacity 256", "iphone", (256, None)),
    ("512 ssd", "macbook", (512, None)),
    ("512GB memory", "iphone", (512, None)),
    ("1tb storage", "iphone", (1024, None)),
    ("64gb (54gb free)", "iphone", (64, None)),
    ("with 2TB iCloud", "iphone", (None, None)),
    ("16/512", "macbook", (512, 16)),
    ("unified memory 24GB", "macbook", (None, 24)),
    ("12GB RAM 256GB", "samsung", (256, None)),
    # #19 another thing's size
    ("Comes with a 256GB microSD card", "samsung", (None, None)),
    ("Includes 64GB SanDisk card", "samsung", (None, None)),
    ("iCloud storage 2TB", "iphone", (None, None)),
    ("2TB Google Drive", "samsung", (None, None)),
    ("Open to swaps for an iPhone 14 Pro 256GB", "iphone", (None, None)),
    ("Upgraded to the 15 Pro 256GB so selling this one", "iphone", (None, None)),
    ("Would swap for S24 Ultra 512GB", "samsung", (None, None)),
    ("Samsung A52 128GB, comes with 64GB microSD card", "samsung", (128, None)),
    ("Comes with 128GB MicroSD", "samsung", (None, None)),
    ("with 64GB SanDisk SD card", "samsung", (None, None)),
    ("Swap for iPhone 15 128GB considered", "iphone", (None, None)),
    # #20 a MacBook's graphics memory
    ("i7 16GB RAM 512GB SSD AMD Radeon Pro 5300M 4GB", "macbook", (512, 16)),
    ("16GB RAM, 1TB SSD, Radeon Pro 5500M 8GB GDDR6", "macbook", (1024, 16)),
    ("Radeon Pro 560X 4GB, 16GB RAM, 512GB SSD", "macbook", (512, 16)),
    ("i7 16GB RAM 512GB SSD", "macbook", (512, 16)),
    ("AMD 5500 4gb Graphics", "macbook", (None, None)),
    ("Core i9 / 32GB / 500GB / Radeon Pro 555X 4GB", "macbook", (None, 32)),
    # #21 two sizes on offer
    ("64/128GB", "iphone", (None, None)),
    ("128/256GB", "iphone", (None, None)),
    ("M3 Max 128GB 2TB", "macbook", (2048, 128)),
    ("MacBook Air 2012 64GB SSD 4GB RAM", "macbook", (64, 4)),
    ("Apple iPhone 13  Green  Either 128/256 GB (can’t remember) Not sure if sim is locked", "iphone", (None, None)),
    ("Storage: 32/64/128GB Im not sure", "samsung", (None, None)),
    ("16/32GB All Colours", "iphone", (None, None)),
    ("8/128", "samsung", (128, None)),
    ("12/256", "samsung", (256, None)),
    ("16/512", "samsung", (512, None)),
    ("iPhone 16/128GB", "iphone", (128, None)),
    ("Iphone 16/512GB", "iphone", (512, None)),
    ("M1 Max 64GB 2TB", "macbook", (2048, 64)),
    ("64GB/128GB", "iphone", (None, None)),
    ("64GB or 128GB", "iphone", (None, None)),
    # #22 "128gig"
    ("128gig, unlocked, works perfectly", "iphone", (128, None)),
    ("128 gig storage", "iphone", (128, None)),
    ("It has 128 gigs of storage", "iphone", (128, None)),
    ("256g model", "iphone", (256, None)),
    ("8gig 256gig", "macbook", (256, 8)),
    ("128g", "iphone", (128, None)),
    ("128 GIG", "iphone", (128, None)),
    ("128gigs", "iphone", (128, None)),
    ("256gig", "samsung", (256, None)),
    ("Mem 256gig", "iphone", (256, None)),
    ("256 gig", "iphone", (256, None)),
    ("256 gigs of storage", "iphone", (256, None)),
    ("128 gigabytes", "iphone", (128, None)),
    ("64g", "iphone", (64, None)),
    # the probe's own
    ("Upgraded to the 15 Pro so selling my 13 Pro 256GB", "iphone", (256, None)),
    ("M1 8-core CPU 7-core GPU 8GB RAM 256GB SSD", "macbook", (256, 8)),
    ("Intel UHD Graphics 617 8GB RAM 128GB SSD", "macbook", (128, 8)),
    ("M2 Pro 10-core CPU 16-core GPU 16GB 512GB", "macbook", (512, 16)),
    ("Storage 64GB with a 128GB SD card", "samsung", (64, None)),
    ("128GB, battery capacity 86%", "iphone", (128, None)),
    ("5G phone, 128GB", "samsung", (128, None)),
    ("Weighs 174g, 256GB", "iphone", (256, None)),
    ("iPhone 6 16GB memory", "iphone", (16, None)),
    ("Has 6GB RAM and 128 GB internal storage", "samsung", (128, None)),
    ("16GB unified memory, 512GB SSD, 10-core GPU", "macbook", (512, 16)),
    ("Apple M1 chip with 8-core CPU, 7-core GPU, 8GB unified memory, 256GB SSD storage", "macbook", (256, 8)),
    ("Selling because I switched to a Pixel, this is the 128GB", "iphone", (128, None)),
    ("Swapped the screen for a genuine one, 256GB", "iphone", (256, None)),
    ("Swap for PS5 considered. 256GB", "iphone", (256, None)),
    ("Will consider part exchange 128GB", "iphone", (128, None)),
    ("256gb storage, 2 years old, 8 months warranty left", "iphone", (256, None)),
    ("RAM 16 SSD 512", "macbook", (512, 16)),
]

RECHECK_DEVICES = [  # (title, what kind_of says it is)
    # #16 a case or a frame in a real device's title
    ("iPhone 11 in Otterbox case", "iphone"),
    ("iPhone 15 Pro Max always in a case", "iphone"),
    ("iPhone 12 Pro Max kept in case, mint", "iphone"),
    ("iPhone 13 Pro wallet case included", "iphone"),
    ("iPhone 12 charger and case included", "iphone"),
    ("MacBook Air M1 2020 sleeve included", "macbook"),
    ("MacBook Air M3 keyboard cover included", "macbook"),
    ("iPhone 14 Pro screen protector fitted since new", "iphone"),
    ("Samsung Galaxy S21 Ultra cracked frame", "samsung"),
    ("Samsung S20 FE bent frame", "samsung"),
    ("I-phone 13", "iphone"),
    ("I-Phone 13", "iphone"),
    ("I-phone 11 64GB", "iphone"),
    ("Immaculate I-Phone 12 Pro Max", "iphone"),
    ("iPhone XS Space Grey – Fully Working – Case & Screen Protector Included", "iphone"),
    ("Samsung S24 Ultra great condition factory unlocked Case and screen protectors included", "samsung"),
    ("MacBook Pro 15 inch. Power cable & disc included.", "macbook"),
    ("iPhone 15 excellent condition included case", "iphone"),
    ("Frame Damage Galaxy S25", "samsung"),
    ("Samsung Galaxy S21 Ultra 256GB cracked frame", "samsung"),
    ("Samsung Galaxy S20 FE fitted case", None),
    ("iPhone 13 case in black", None),
    ("iPhone 12 wallet case", None),
    ("MacBook Pro keyboard cover", None),
    ("Samsung The Frame 55", None),
    ("iPhone 13 case", None),
    ("iPhone 13 screen protector", None),
    ("MacBook sleeve 13 inch", None),
    # the probe's own
    ("MacBook charger and cable included", None),
    ("iPhone 13 charger cable included", None),
    ("iPhone 14 case and screen protector", None),
    ("MacBook Air 13 in case", None),
    ("Samsung Galaxy S23 in Otterbox Defender case", "samsung"),
    ("Leather case for iPhone 13 in brown", None),
    ("iPhone 15 Pro Max case in excellent condition", None),
    ("Samsung Frame TV 2023", None),
    ("iPhone 13 Pro Max, box and charger included", "iphone"),
]

RECHECK_ASKED = [  # (title, flaws, description, what estimate asks, without what every request has)
    # #2 a fault the judge has no word for
    ("iPhone 13 128GB",
     ["Everything works except face id"],
     "Everything works except face id. Collection Leeds.",
     {"kinds": ["fault"]}),
    ("iPhone 13 128GB", ["Rear camera is blurry"], "Rear camera is blurry.", {"kinds": ["fault"]}),
    ("iPhone 13 128GB", ["Speaker blown"], "Speaker blown.", {"kinds": ["fault"]}),
    ("iPhone 13 128GB",
     ["Screen is unresponsive in places"],
     "Screen is unresponsive in places.",
     {"kinds": ["fault"]}),
    ("iPhone 13 128GB", ["Shuts down randomly"], "Shuts down randomly.", {"kinds": ["fault"]}),
    # #3 a run-on clause over 15 words
    ("iPhone 13 128GB",
     ["selling my iphone 13 in good condition there is a small crack on the back glass from when i dropped it"],
     "selling my iphone 13 in good condition there is a small crack on the back glass from when i dropped it",
     {"kinds": ["damage"]}),
    # #4 a missing box or a "no offers" beside a flaw
    ("iPhone 13 128GB", ["Back glass smashed no swaps"], "Back glass smashed no swaps", {"kinds": ["damage"]}),
    ("iPhone 13 128GB", ["Screen cracked and no box"], "Screen cracked and no box", {"kinds": ["damage"]}),
    ("iPhone 13 128GB",
     ["Face ID doesn't work and no charger"],
     "Face ID doesn't work and no charger",
     {"kinds": ["fault"]}),
    # #5 one broken screen, cut once
    ("iPhone 13 128GB",
     ["Screen is cracked and broken but still works"],
     "Screen is cracked and broken but still works",
     {"kinds": ["damage"]}),
    # #9 a battery that needs a service
    ("iPhone 13 128GB", ["Battery shows service"], "Battery shows service", {"kinds": ["battery"]}),
    ("MacBook Air M1 8GB 256GB",
     ["Battery condition: Service Recommended"],
     "Battery condition: Service Recommended",
     {"kinds": ["battery"]}),
    # #10 a network named before "locked"
    ("Apple iPhone 7 Plus rose gold 256GB", ["Vodafone locked"], "Vodafone locked", {"kinds": ["network lock"]}),
    # #11 wear the judge has no word for
    ("iPhone 13 128GB Blue",
     ["Two scrapes on the front screen."],
     "Two scrapes on the front screen.",
     {"kinds": ["wear"]}),
    ("iPhone 13 128GB Blue",
     ["A few dings but still works well."],
     "A few dings but still works well.",
     {"kinds": ["wear"]}),
    ("MacBook Air M2 8GB 256GB",
     ["Apart from a very small ding on lid (as shown) in good overall condition."],
     "Apart from a very small ding on lid (as shown) in good overall condition.",
     {"kinds": ["wear"]}),
    ("iPhone 13 128GB Blue", ["Grade C"], "Grade C", {"kinds": ["wear"]}),
    # #12 "no face id issues"
    ("iPhone 13 128GB - No Face ID issues", [], "", {"kinds": []}),
    ("iPhone 13 128GB", ["Great condition, no face id issues."], "Great condition, no face id issues.", {"kinds": []}),
    ("iPhone 13 128GB", ["No Face ID problems at all."], "Mint condition. No Face ID problems at all.", {"kinds": []}),
    # #13 a title selling it for repairs
    ("iPhone 12 Pro repairs", [], "", {"kinds": ["parts"], "bucket": "good"}),
    ("iPhone 12 Pro Max - Repairs", [], "", {"kinds": ["parts"], "bucket": "good"}),
    ("iPhone XR repair job", [], "", {"kinds": ["parts"], "bucket": "good"}),
    ("iPhone 8 needs screen repair", [], "", {"kinds": ["parts"], "bucket": "good"}),
    ("iPhone 13 Pro screen repair needed", [], "", {"kinds": ["parts"], "bucket": "good"}),
    ("MacBook Pro 2019 repair", [], "", {"kinds": ["parts"], "bucket": "good"}),
    ("Samsung S21 Ultra repairs", [], "", {"kinds": ["parts"], "bucket": "good"}),
    # #14 a locked or dead title
    ("MacBook Pro 2015 firmware password locked", [], "", {"kinds": ["lock"], "bucket": "good"}),
    ("MacBook Pro 2018 EFI password", [], "", {"kinds": ["lock"], "bucket": "good"}),
    ("iPhone 12 locked to owner", [], "", {"kinds": ["lock"], "bucket": "good"}),
    ("Samsung Galaxy A52 KG locked", [], "", {"kinds": ["lock"], "bucket": "good"}),
    ("iPhone 12 barred", [], "", {"kinds": ["lock"], "bucket": "good"}),
    ("iPhone 11 passcode locked", [], "", {"kinds": ["lock"], "bucket": "good"}),
    ("iPhone 12 dead", [], "", {"kinds": ["parts"], "bucket": "good"}),
    ("Dead iPhone 12", [], "", {"kinds": ["parts"], "bucket": "good"}),
    ("iPhone 12 Pro Max - dead", [], "", {"kinds": ["parts"], "bucket": "good"}),
    ("iPhone x", ["Locked to owner"], "Locked to owner", {"kinds": ["lock"], "bucket": "good"}),
    ("MacBook Air 15in 2023 (Passcode locked)", [], "", {"kinds": ["lock"], "bucket": "good"}),
    ("iPhone 12 dead pixels on screen", [], "", {"kinds": ["fault"]}),
    # #15 a "not working" title
    ("iPhone 12 not working", [], "", {"kinds": ["parts"], "bucket": "good"}),
    ("MacBook Air not working", [], "", {"kinds": ["parts"], "bucket": "good"}),
    ("iPhone 13 128GB not working", [], "", {"kinds": ["parts"], "bucket": "good"}),
    ("iPhone 11 (not working)", [], "", {"kinds": ["parts"], "bucket": "good"}),
    ("iPhone 12 completely dead", [], "", {"kinds": ["parts"], "bucket": "good"}),
    ("iPhone XR dead", [], "", {"kinds": ["parts"], "bucket": "good"}),
    ("Faulty iPhone 12 64GB", [], "", {"kinds": ["fault"], "bucket": "good"}),
    ("MacBook Pro 2019 faulty", [], "", {"kinds": ["fault"], "bucket": "good"}),
    ("iPhone 12 Face ID not working", [], "", {"kinds": ["fault"], "bucket": "good"}),
    # #17 a spec list's labels
    ("iPhone 13 Blue", [], "Storage: 128GB\nRAM: 4GB", {"kinds": [], "storage_gb": 128}),
    ("MacBook Air M1", [], "Memory: 8GB\nStorage: 256GB", {"kinds": [], "storage_gb": 256, "ram_gb": 8}),
    # #18 a size written the UK way
    ("iPhone 13 Blue", [], "128 gig, battery 90%", {"kinds": [], "storage_gb": 128}),
    ("MacBook Air M1", [], "8gb ram 256 ssd", {"kinds": [], "storage_gb": 256, "ram_gb": 8}),
    # #19 another thing's size
    ("iPhone 13 Pro Graphite", [], "Battery 88%. Open to swaps for an iPhone 14 Pro 256GB.", {"kinds": []}),
    ("Samsung Galaxy A52", [], "Comes with a 256GB microSD card", {"kinds": []}),
    ("Samsung Galaxy A54 5G", [], "Great condition, comes with case and 256GB microSD card", {"kinds": []}),
    ("iPhone 13 Pro", [], "Upgraded to the 15 Pro 256GB so selling this one. Battery 86%.", {"kinds": []}),
    # #20 a MacBook's graphics memory
    ("MacBook Pro 16 2019",
     [],
     "i7, 16GB RAM, 512GB SSD, Radeon Pro 5300M 4GB",
     {"kinds": [], "storage_gb": 512, "ram_gb": 16}),
    ("MacBook Pro 2019 intel I9", [], "AMD 5500 4gb Graphics", {"kinds": []}),
    # #21 two sizes on offer
    ("Apple IPhone 13",
     [],
     "Apple iPhone 13  Green  Either 128/256 GB (can’t remember) Not sure if sim is locked",
     {"kinds": []}),
    # #22 "128gig"
    ("iPhone 13 Blue", [], "128gig, unlocked, works perfectly.", {"kinds": [], "storage_gb": 128}),
    # the probe's own
    ("iPhone 13 Pro Max untested for parts", [], "", {"kinds": ["parts"], "bucket": "good"}),
    ("iPhone 11 untested", [], "", {"kinds": ["parts"], "bucket": "good"}),
    ("iPhone 12 Pro, had screen repair", [], "", {"kinds": [], "bucket": "good"}),
    ("iPhone 12 Pro 256GB after screen repair", [], "", {"kinds": [], "bucket": "good"}),
    ("iPhone 12 - genuine Apple screen repair", [], "", {"kinds": [], "bucket": "good"}),
    ("iPhone 13 128GB screen repaired", [], "", {"kinds": []}),
    ("iPhone 12 dead battery", [], "", {"kinds": ["battery"]}),
    ("iPhone 12 Pro Max dead mint condition", [], "", {"kinds": []}),
    ("iPhone 12 EE locked", [], "", {"kinds": ["network lock"]}),
    ("iPhone 13 Pro unlocked (was EE)", [], "", {"kinds": []}),
    ("MacBook Air M1 not working properly", [], "", {"kinds": ["fault"], "bucket": "good"}),
    ("Samsung Galaxy S22 for spares or repairs", [], "", {"kinds": ["parts"], "bucket": "good"}),
    ("iPhone 14 Pro 128GB iCloud locked", [], "", {"kinds": ["lock"], "bucket": "good"}),
]

RECHECK_ASKED_KINDS = [  # (title, flaws, description, the kinds estimate asks for)
    # #10 a network named before "locked"
    ("iPhone 12 EE locked", [], "", ["network lock"]),
    ("Apple iPhone 6s 16GB – EE Locked", [], "", ["network lock"]),
    ("Apple IPhone X 64GB 82% BH Black EE Locked", [], "", ["network lock"]),
    # #13 a title selling it for repairs
    ("iPhone 13 Pro, screen repair done", [], "", []),
    ("iPhone 13 Pro, never needed repairs", [], "", []),
    ("iPhone 12 Pro", ["Repair job, no offers."], "Repair job, no offers.", ["parts"]),
    ("iPhone 12 Pro",
     ["Selling as repairs.", "Needs new screen."],
     "Selling as repairs. Needs new screen.",
     ["parts", "damage"]),
    # #14 a locked or dead title
    ("DEAD Iphone 6s rose gold check desc", [], "", ["parts"]),
]


@pytest.mark.parametrize("sentence, expected", RECHECK_KINDS)
def test_every_sentence_of_the_second_check_gives_its_kinds(sentence, expected):
    assert kinds(sentence) == expected


@pytest.mark.parametrize("sentence, title, expected", RECHECK_MAC_KINDS)
def test_every_macbook_sentence_of_the_second_check_gives_its_kinds(sentence, title, expected):
    assert mac_kinds(sentence, title) == expected


@pytest.mark.parametrize("text, kind, sizes", RECHECK_SIZES)
def test_every_size_of_the_second_check_is_read_as_it_should_be(text, kind, sizes):
    assert prices.sizes_in(text, kind) == sizes


@pytest.mark.parametrize("title, kind", RECHECK_DEVICES)
def test_every_title_of_the_second_check_is_the_device_it_should_be(title, kind):
    assert prices.kind_of(title) == kind


@pytest.mark.parametrize("title, flaws, description, expected", RECHECK_ASKED)
def test_every_listing_of_the_second_check_is_asked_as_it_should_be(title, flaws, description, expected):
    assert sent(title, flaws, description) == expected


@pytest.mark.parametrize("title, flaws, description, expected", RECHECK_ASKED_KINDS)
def test_every_listing_of_the_second_check_is_asked_for_its_kinds(title, flaws, description, expected):
    assert sent(title, flaws, description)["kinds"] == expected


@pytest.mark.parametrize("sentence, kinds", [
    ("Untested on a different network", ["wear"]),  # one feature untested: a warning, not a phone sold for parts
    ("Untested on the EE network", ["wear"]),
    ("Untested on the other networks", ["wear"]),
    ("Untested for parts", ["parts"]),  # the phone itself untested still is
    ("Cracks or chips: none", []),  # one label over two flaws, answered once (6 Oct round-2 check)
    ("Cracks & chips: none", []),
    ("Any cracks or chips: no", []),
    ("Screen cracks or chips: none", []),
    ("Cracks or chips: a few on the corner", ["damage"]),  # an answer that isn't a denial still counts
])
def test_the_round_two_regressions_stay_fixed(sentence, kinds):
    assert prices.kinds_of([sentence], "iPhone 13 128GB. " + sentence) == kinds
