"""Numbers read by what the product's answers can be (flip.numbers). The ways of
writing them come from real UK phone listings (2,091 titles, 2 Sep 2026); the
examples here are made up."""

import pytest

from flip.catalogue import fill_from_catalogue, load_catalogue
from flip.numbers import battery_worded, read_numbers

CATALOGUE = load_catalogue()
MODELS = {m["id"]: m for m in CATALOGUE}
NAMES = [alias for m in CATALOGUE for alias in m["aliases"]]


def read(text, model="iphone-13", alone=False):
    return read_numbers(text, MODELS[model], NAMES, alone)


@pytest.mark.parametrize("text, size", [
    ("iPhone 13 128", "128GB"), ("iPhone 13 128g", "128GB"), ("iPhone 13 128G Purple", "128GB"),
    ("iphone 13 256 gig, midnight", "256GB"), ("iPhone 13 512bg like new", "512GB"), ("iPhone 13 256gh", "256GB"),
    ("iPhone 13 128 go", "128GB"), ("iPhone 13 256gGB unlocked", "256GB"), ("iPhone 13 256￼GB", "256GB"),
    ("iPhone 13 midnight 128", "128GB"), ("iPhone 13 128 in good working condition", "128GB"),
    ("iPhone 13 128 £300", "128GB"),  # the £ is the next number's
    ("storage 128.", "128GB"), ("iPhone 13 128GB", "128GB"),
    # found in real listings: the number right after a model name, dots, an ellipsis or a new line
    ("NO OFFERS iPhone 13 256GB", "256GB"), ("IPHONE 13....128GB...UNLOCKED", "128GB"),
    ("Apple iPhone 13\u2026128gb, black", "128GB"), ("Single owner phone. Blue\n128 GB. iOS 26", "128GB"),
    ("factory reset\n512gb\nmidnight", "512GB"),
])
def test_a_size_the_model_comes_in_is_its_storage_gb_or_not(text, size):
    assert read(text)["storage"] == {size}


def test_ram_and_storage_written_together():
    assert read("Galaxy S23 8/256", "galaxy-s23")["storage"] == {"256GB"}
    assert read("Galaxy S23 8GB RAM 256GB", "galaxy-s23") == {"storage": {"256GB"}, "stated": {"8GB", "256GB"},
                                                             "battery": set()}


@pytest.mark.parametrize("text", [
    "iPhone 13 £128", "iPhone 13 128 ono", "iPhone 13 128 quid", "paid 256 for it", "selling for 256",
    "had it 128 days", "128.5 hours", "collect from 128 High Street", "call 07700 900128", "unit 128 on the estate",
    "iPhone 13 64",  # the iPhone 13 doesn't come in 64 GB
    "iPhone 13 32",  # nor 32: under 64, a number on its own could be anything
    "iPhone 13 5g",  # the network, not 5 GB
    "iPhone 13 offers over 256", "iPhone 13 128.50",
])
def test_a_number_that_belongs_to_something_else_is_not_storage(text):
    assert read(text)["storage"] == set()


def test_numbers_in_a_models_name_are_names_not_sizes():
    phone = {"id": "made-up", "category": "phones", "aliases": ["nokia 64"], "storage": ["64GB", "128GB"]}
    assert read_numbers("Nokia 64 128", phone)["storage"] == {"128GB"}
    assert read_numbers("Nokia 64, 64", phone)["storage"] == {"64GB"}


@pytest.mark.parametrize("notes, figure", [
    ("battery 84", "84"), ("batt 84", "84"), ("batt84 few marks", "84"), ("baterray 88", "88"), ("bh 88", "88"),
    ("bh: 91", "91"), ("battery health is 86%", "86"), ("84 battery health", "84"), ("83 battery life", "83"),
    ("battery %83", "83"), ("%84 battery health", "84"), ("87🔋 great", "87"), ("88percent battery health", "88"),
    ("85% maximum capacity", "85"), ("87%", "87"), ("battery 100%", "100"), ("battery 84.5%", "84.5"),
    ("78 , few scratches on screen", "78"),  # on its own, in your notes
])
def test_battery_health_however_your_notes_put_it(notes, figure):
    assert read(notes, alone=True)["battery"] == {figure}


@pytest.mark.parametrize("notes", [
    "collection from BH21", "100% working", "100", "great condition 84%", "95% mint", "charged to 80%",
    "77 High Street", "paid 80", "80 quid", "had it 90 days", "comes with a 65w charger", "condition 9/10",
    "99% sure it's unlocked", "6.1 inch screen",
])
def test_figures_about_something_else_are_not_the_battery(notes):
    assert read(notes, alone=True)["battery"] == set()


def test_a_number_on_its_own_counts_only_in_your_notes():
    assert read("78 , few scratches", alone=True)["battery"] == {"78"}
    # in a seller's text it stays unread: in real listings those were shop addresses
    assert read("78 , few scratches")["battery"] == set()


def test_a_number_that_could_be_either_is_neither():
    # the iPhone 11 comes in 64 GB, so "64" on its own could be that or the battery
    assert read("64", "iphone-11", alone=True) == {"storage": set(), "stated": set(), "battery": set()}
    assert read("64", alone=True)["battery"] == {"64"}  # the iPhone 13 doesn't come in 64 GB
    # a word settles it
    assert read("storage 64, battery 85", "iphone-11", alone=True) == \
        {"storage": {"64GB"}, "stated": set(), "battery": {"85"}}


def test_only_phones_have_a_battery_health():
    assert read("battery 85", "ps5", alone=True)["battery"] == set()


def test_battery_words_on_either_side_for_the_checks():
    for text in ("battery 84", "84 battery health", "battery %84", "84🔋", "Battery health is 84%.", "bh 84"):
        assert battery_worded(text) == {"84"}
    assert battery_worded("battery lasts 12 hours, 128gb, collection BH21") == set()


# ── cases two test agents wrote to break it (2 Sep 2026), kept as they wrote them ──

def fill(title, notes=""):
    item = fill_from_catalogue(title, notes, CATALOGUE)
    return item.get("storage"), item.get("battery")


@pytest.mark.parametrize("title, notes, storage, battery", [
    # a battery word belongs to one figure, so the size next to it stays the storage
    ("iPhone 13 128 Battery 87%", "", "128GB", None),
    ("iPhone 13 | 128 | Battery 89% | Unlocked", "", "128GB", None),
    ("iPhone 13 Battery 100% 128 Unlocked Midnight", "", "128GB", None),
    ("iPhone 13 100% Battery 128 Unlocked", "", "128GB", None),
    ("iPhone 13 Battery Health Good 256", "", "256GB", None),
    ("iPhone 13", "midnight\n128\nbattery 87%\nunlocked", "128GB", "87"),
    ("iPhone 14", "bh 90%\n256\nsmall scratch top", "256GB", "90"),
    ("iPhone 11", "64 battery 81%", "64GB", "81"),
    ("iPhone 13", "128 bh 87", "128GB", "87"),
    ("iPhone 13", "128 / 100% bh", "128GB", "100"),
    ("iPhone 13", "128 storage 89% battery", "128GB", "89"),
    ("iPhone 13", "capacity 256, 88%", "256GB", "88"),
    ("iPhone 13", "bh 87,128gb,unlocked", "128GB", "87"),
    ("iPhone 13", "iOS 18 bh 89", None, "89"),
    ("iPhone 13", "bought 14/09/26 bh 94", None, "94"),
    ("iPhone 13", "bh 87/100", None, "87"),
    ("iPhone 11", "64 battery replaced, screen mint", "64GB", None),
    # prices in your own notes
    ("iPhone 12", "bought 128, sell 180, bh 86", None, "86"),
    ("iPhone 8 64gb", "cex 95 cash", "64GB", None),
    ("iPhone 8 64gb", "list at 95", "64GB", None),
    ("iPhone 14", "repair quote 79", None, None),
    ("iPhone XR 64GB", "won it for 68 on ebay, bh 84", "64GB", "84"),
    ("iPhone 8 64gb", "paid 45 sell 85, batt 79%", "64GB", "79"),
    ("iPhone 11 64GB unlocked 128 posted", "", "64GB", None),
    ("iPhone 13", "price: 128", None, None),
    ("iPhone 13", "battery replaced for 85", None, None),
    # charge cycles, addresses, the end of an IMEI, cloud storage, warranties, distances, dates
    ("iPhone 15", "bh 97%, 256 cycles, mint", None, "97"),
    ("iPhone 15", "cycles 87", None, None),
    ("iPhone 15", "battery cycle count 87", None, None),
    ("iPhone 15", "battery 100% 87 cycles", None, "100"),
    ("iPhone 15", "only 64 battery cycles and 100% battery health", None, "100"),
    ("iPhone 13", "collected from 128 Elm Close, bh 88", None, "88"),
    ("iPhone 13", "collect from 72 Oak Drive", None, None),
    ("iPhone 13", "imei ends 0512, bh 88", None, "88"),
    ("iPhone 17 Pro Max", "signed out of 2tb icloud, bh 100", None, "100"),
    ("iPhone 13", "90-day warranty", None, None),
    ("iPhone 14", "only 75 miles away", None, None),
    ("iPhone 13", "bought 01-10-2025 86% bh", None, "86"),
    # battery written every which way
    ("iPhone 13", "B/H 100%", None, "100"),
    ("iPhone 13", "Battery Health:- 100%", None, "100"),
    ("iPhone 13", "battery health is still at 100%", None, "100"),
    ("iPhone 13", "batt. 100%", None, "100"),
    ("iPhone 13", "bettery 100%", None, "100"),
    ("iPhone 13", "87% original battery", None, "87"),
    ("iPhone 13", "bh87 few marks", None, "87"),
    ("iPhone 13", "bh 88 g/c", None, "88"),
    ("iPhone 13", "batt 88 go for 300", None, "88"),
    ("iPhone 13 Pro Max", "Max cap 100%", None, "100"),
    ("iPhone 13", "86% max cap", None, "86"),  # "max" here isn't a Pro Max
    # figures about something else
    ("iPhone 13", "battery charged to 80%", None, None),
    ("iPhone 15", "charging limit 80%", None, None),
    ("iPhone 15", "80% limit on, bh 100%", None, "100"),
    ("iPhone 13", "screen 95%, bh 88", None, "88"),
    ("iPhone 13", "battery dies at 30%", None, None),
    ("iPhone XS", "64gb space grey 76%", "64GB", "76"),
    # model names
    ("Samsung Galaxy S23 8GB+256GB Phantom Black", "", "256GB", None),
    ("iPhone 13", "comes with box plus 2 cases, bh 88", None, "88"),
])
def test_what_the_test_agents_tried(title, notes, storage, battery):
    assert fill(title, notes) == (storage, battery)


def test_a_size_right_after_another_models_name_is_that_models():
    from flip.catalogue import model_names
    said = "Upgraded to the iPhone 15 Pro 256GB so selling my old phone"
    assert read_numbers(said, MODELS["iphone-13"], model_names())["storage"] == set()
