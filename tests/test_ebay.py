"""eBay's fields, filled from the catalogue in eBay's own words: every phone,
size, colour and chip checked against what eBay's API said (data/ebay_fields.json)."""

import json
import urllib.request

import pytest

from flip import ebay
from flip.catalogue import fill_from_catalogue, load_catalogue

CATALOGUE = load_catalogue()
PHONES = [m for m in CATALOGUE if m["category"] == "phones"]
FIELDS = ebay.load_fields()
EMAP = ebay.load_map()
PHONE_FIELDS = {f["name"]: f for f in FIELDS["categories"]["phones"]["fields"]}


def specifics(title, notes="", colour_from=None):
    item = fill_from_catalogue(title, notes, CATALOGUE)
    model = next(m for m in CATALOGUE if m["id"] == item["model_id"])
    return ebay.item_specifics(item, model, colour_from)


def test_what_ebay_needs_in_each_category():
    needed = {kind: [f["name"] for f in c["fields"] if f["required"]] for kind, c in FIELDS["categories"].items()}
    assert needed == {"phones": ["Brand", "Model", "Storage Capacity", "Colour"], "consoles": ["Brand", "Model"],
                      "headphones": ["Brand", "Connectivity", "Model", "Colour", "Type"]}


@pytest.mark.parametrize("phone", PHONES, ids=lambda m: m["id"])
def test_every_phone_is_named_and_sized_as_ebay_lists_it(phone):
    item = {"model_id": phone["id"], "brand": phone["brand"], "model": phone["model"]}
    assert ebay.model_value(item, PHONE_FIELDS["Model"]["values"], EMAP["models"]) in PHONE_FIELDS["Model"]["values"]
    for size in phone["storage"]:  # eBay has no 2 TB phone yet: a typed value it takes
        assert ebay.ebay_size(size) in PHONE_FIELDS["Storage Capacity"]["values"] or size == "2TB"
    assert PHONE_FIELDS["Storage Capacity"]["typed"]


def test_every_phone_colour_is_one_of_ebays_16():
    colours = {colour for phone in PHONES for colour in phone["colours"]}
    assert colours <= set(EMAP["colours"])
    assert set(EMAP["colours"].values()) <= set(PHONE_FIELDS["Colour"]["values"])
    assert (EMAP["colours"]["Midnight"], EMAP["colours"]["Rose Gold"], EMAP["colours"]["Natural Titanium"]) == \
        ("Black", "Pink", "Silver")  # what UK sellers pick, not the first word


@pytest.mark.parametrize("chip, named", [
    ("A15 Bionic", "Apple A15 Bionic"), ("A9", "Apple A9"), ("A17 Pro", "Apple A17 Pro"),
    ("A19 Pro", "Apple A19 Pro"),  # not on eBay's list yet: typed
])
def test_chips_are_named_as_ebay_does(chip, named):
    assert ebay.chipset_value("Apple", chip, PHONE_FIELDS["Chipset Model"]["values"]) == named
    assert ebay.chipset_value("Samsung", "Snapdragon 8 Gen 2", PHONE_FIELDS["Chipset Model"]["values"]) == \
        "Qualcomm Snapdragon 8 Gen 2"


def test_a_phone_gets_ebays_category_and_fields_in_its_words():
    # the 2 Sep iPhone 13 mini: no colour yet (the photo showed boxes)
    found = specifics("iphone 13 mini 128gb unlocked to any sim", "baterray 88 , few scraches on back , crack on front")
    assert found["category"] == {"id": "9355", "name": "Mobile & Smart Phones", "path": "Mobile Phones & Communication"}
    assert [(s["name"], s["value"], s["required"], s["source"]) for s in found["specifics"]] == [
        ("Brand", "Apple", True, "the catalogue"),
        ("Model", "Apple iPhone 13 mini", True, "the catalogue"),
        ("Storage Capacity", "128 GB", True, "your title or notes"),
        ("Colour", None, True, None),  # eBay needs it: for you
        ("Network", "Unlocked", False, "your title or notes"),
        ("Connectivity", "5G", False, "the catalogue"),
        ("Operating System", "iOS", False, "the catalogue"),
        ("Screen Size", "5.4 in", False, "the catalogue"),
        ("Chipset Model", "Apple A15 Bionic", False, "the catalogue"),
    ]
    options = {s["name"]: s["options"] for s in found["specifics"]}
    assert options["Storage Capacity"] == ["128 GB", "256 GB", "512 GB"]
    assert "Apple iPhone 13 mini" in options["Model"] and all(m.startswith("Apple ") for m in options["Model"])
    assert options["Network"][0] == "Unlocked" and len(options["Colour"]) == 16


def test_the_colour_says_its_exact_name_and_where_it_came_from():
    colour = {s["name"]: s for s in specifics("iPhone 13 128GB starlight")["specifics"]}["Colour"]
    assert (colour["value"], colour["source"]) == ("White", "your title or notes: Starlight")
    item = {**fill_from_catalogue("iPhone 13 mini 128GB", "", CATALOGUE), "colour": "(PRODUCT)RED"}
    found = ebay.item_specifics(item, next(m for m in CATALOGUE if m["id"] == "iphone-13-mini"), "photos")
    assert {s["name"]: s["source"] for s in found["specifics"]}["Colour"] == "the photos: (PRODUCT)RED"


def test_a_colour_eBay_spells_the_same_way_doesnt_repeat_it():
    item = {**fill_from_catalogue("iPhone 13 128GB", "", CATALOGUE), "colour": "Blue"}
    found = ebay.item_specifics(item, next(m for m in CATALOGUE if m["id"] == "iphone-13"), "photos")
    assert {s["name"]: s["source"] for s in found["specifics"]}["Colour"] == "the photos"


def test_an_empty_storage_field_is_yours_to_fill_from_the_models_sizes():
    # 14 Oct: no hint from the original seller's words any more (List on eBay is written from your title and notes)
    phone = next(m for m in CATALOGUE if m["id"] == "iphone-13")
    found = ebay.item_specifics(fill_from_catalogue("iPhone 13", "", CATALOGUE), phone)
    storage = {s["name"]: s for s in found["specifics"]}["Storage Capacity"]
    assert (storage["value"], "hint" in storage) == (None, False)
    assert storage["options"] == [ebay.ebay_size(size) for size in phone["storage"]]


def test_other_categories_and_unknown_models_get_no_fields_yet():
    ps5 = fill_from_catalogue("PS5 Slim digital", "", CATALOGUE)
    assert ebay.item_specifics(ps5, next(m for m in CATALOGUE if m["id"] == ps5["model_id"])) is None
    assert ebay.item_specifics(fill_from_catalogue("Nokia 3310", "", CATALOGUE)) is None


def test_asking_ebay_again_keeps_what_each_field_is(monkeypatch, tmp_path):
    answers = {
        "get_default_category_tree_id": {"categoryTreeId": "3"},
        "get_item_aspects_for_category": {"aspects": [
            {"localizedAspectName": "Brand", "aspectConstraint": {"aspectRequired": True, "aspectUsage": "RECOMMENDED",
                                                                  "aspectMode": "FREE_TEXT"},
             "aspectValues": [{"localizedValue": "Apple"}]},
            {"localizedAspectName": "Charger Included", "aspectConstraint": {"aspectUsage": "RECOMMENDED",
                                                                             "aspectMode": "SELECTION_ONLY"},
             "aspectValues": [{"localizedValue": "Yes"}, {"localizedValue": "No"}]}]},
        "get_category_subtree": {"categorySubtreeNode": {"category": {"categoryName": "Mobile & Smart Phones"}}},
        "get_category_suggestions": {"categorySuggestions": [{"category": {"categoryId": "9355"},
                                                              "categoryTreeNodeAncestors": [{"categoryName": "Mobile Phones & Communication"}]}]},
    }

    class Answer:
        def __init__(self, data):
            self.data = json.dumps(data).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, *args):
            return self.data

    def fake_urlopen(request, timeout):
        url = request.full_url
        if "oauth2/token" in url:
            return Answer({"access_token": "pretend"})
        return Answer(next(answer for name, answer in answers.items() if name in url))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(ebay, "CATEGORIES", {"phones": "9355"})
    monkeypatch.setenv("EBAY_CLIENT_ID", "id")
    monkeypatch.setenv("EBAY_CLIENT_SECRET", "secret")
    saved = ebay.refresh(tmp_path / "fields.json")
    phones = saved["categories"]["phones"]
    assert (phones["name"], phones["path"]) == ("Mobile & Smart Phones", "Mobile Phones & Communication")
    assert phones["fields"] == [
        {"name": "Brand", "required": True, "usage": "recommended", "typed": True, "multiple": False, "values": ["Apple"]},
        {"name": "Charger Included", "required": False, "usage": "recommended", "typed": False, "multiple": False,
         "values": ["Yes", "No"]}]
    assert json.loads((tmp_path / "fields.json").read_text()) == saved


def test_asking_ebay_again_needs_its_keys(monkeypatch):
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    with pytest.raises(SystemExit, match="EBAY_CLIENT_ID"):
        ebay.app_token()
