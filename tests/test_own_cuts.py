"""A Samsung's and a MacBook's own cuts (4 Nov 2026, the owner: "MacBook cuts are rough: the flaw percentages were
measured on phones. yh do them for sumsungs and macbook please"). Every kind but damage and battery was the prices
API's UK table, measured on iPhones; now each category has its own (data/kind_cuts.json), measured on 3,375 UK Samsung
and 3,044 UK MacBook listings against the flawless used ones of the same model, as the damage table is. The API is
asked for the clean price and FlipAssist takes them off it, the cut any flaw takes (wear's) counted once. An iPhone is
cut as before. Pretend API: nothing is sent anywhere."""

import io
import json

import pytest

from flip import prices


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Sorter:
    """flip-kinds as these tests need it: its kinds for the words it's told, None for the rest (code sorts those)."""
    name = "flip-kinds-1"

    def __init__(self, said):
        self.said = said

    def __call__(self, words, title, description):
        return self.said.get(words)


@pytest.fixture(autouse=True)
def backend(monkeypatch):
    monkeypatch.setenv("PRICES_URL", "https://example.test/functions/v1/prices")
    monkeypatch.setenv("PRICES_KEY", "k" * 64)
    prices._seen.clear()


def api(middle=240.0, parts_sales=True):
    """A pretend prices API that cuts as the real one does for the kinds it's sent (applyCuts, base "clean"), with the
    for-parts price (£70) for a locked or for-parts one, or its rough cut when there are too few for-parts sales; and
    what it was sent."""
    sent = []

    def opener(request, timeout):
        kinds = json.loads(request.data)["kinds"]
        sent.append(kinds)
        table = prices.API_CUTS_UK
        whole = next((k for k in ("lock", "parts") if k in kinds), None)
        if whole and parts_sales:
            price, used, factor = 70, ["for-parts price"], 70 / middle
        elif whole:
            factor = table[whole] / table["clean"]
            price, used = round(middle * factor), [whole]
        else:
            factor = 1 / table["clean"] if kinds else 1.0
            for k in kinds:
                factor *= table.get(k, 1)
            price, used = round(middle * factor), kinds or ["no flaw"]
        return Response(json.dumps({"mode": "catalogue", "model": "galaxy s21", "storage_gb": 128, "currency": "GBP",
                                    "sales": 40, "middle": middle, "low": 200, "high": 280, "price": price,
                                    "factor": round(factor, 3), "used": used, "rough": bool(whole and not parts_sales),
                                    "exact_match": True}).encode())
    return opener, sent


def rows(found):
    return [(r["words"], r["kinds"], r["by"], None if r["cut"] is None else round(r["cut"], 3))
            for r in found["breakdown"]]


def made_by_rows(found):
    price = found["middle"]
    for row in found["breakdown"]:
        price *= 1 + (row["cut"] or 0)
    return price


def test_the_tables_are_measured_and_say_how_many_listings():
    samsung, macbook, iphone = prices.kind_table("samsung"), prices.kind_table("macbook"), prices.kind_table("iphone")
    # iPhones too since 4 Nov evening (the owner: "yh please go"), measured the same way on 7,548 UK iPhone listings
    assert {k: (c["cut"], c["n"]) for k, c in iphone["kinds"].items()} == {
        "wear": (-0.071, 895), "fault": (-0.259, 204), "network lock": (-0.119, 109), "not genuine": (-0.108, 100),
        "lock": (-0.5, 71), "parts": (-0.582, 106)}
    assert not any(c["rough"] for c in iphone["kinds"].values())
    assert prices.kind_table("iphone", "us") is None  # a market with none: the prices API's table
    assert {k: (c["cut"], c["n"]) for k, c in samsung["kinds"].items()} == {
        "wear": (-0.125, 598), "fault": (-0.333, 168), "network lock": (-0.16, 139), "not genuine": (-0.188, 43),
        "lock": (-0.516, 25), "parts": (-0.536, 62)}
    assert (macbook["kinds"]["wear"]["cut"], macbook["kinds"]["fault"]["cut"]) == (-0.048, -0.251)
    # too few MacBooks with parts that aren't genuine (8): the iPhone's, measured the same way, and rough
    assert macbook["kinds"]["not genuine"]["from"] == "the iPhone" and macbook["kinds"]["not genuine"]["rough"]
    assert samsung["kinds"]["lock"]["rough"] and not samsung["kinds"]["fault"]["rough"]  # 25 listings: rough


def test_a_samsungs_fault_is_its_own_cut_off_the_clean_price():
    opener, sent = api()
    words = "The fingerprint sensor doesn't work"
    found = prices.estimate("Samsung Galaxy S21 128GB", [words], opener=opener, description=words,
                            sorter=Sorter({words: ["fault"]}))
    assert sent == [[]]  # the API is asked for the clean price
    assert found["price"] == 160  # £240 less 33.3%, not the phones' 17.1% (£199)
    assert rows(found) == [([words], ["fault"], "own", -0.333)]
    assert found["own_cuts"] == {"fault": {"cut": -0.333, "n": 168, "rough": False, "from": None}}
    assert found["cuts"] == ["fault"] and found["kinds"] == ["fault"]


def test_the_any_flaw_cut_is_taken_once():
    """The worst kind has its whole cut, another kind only its part on top of the cut any flaw takes (a network lock's
    -16% over wear's -12.5%: -4%), and wear beside them nothing more, right after the cut it's counted in."""
    opener, sent = api()
    fault, lock, wear = "Fingerprint sensor doesn't work", "Locked to EE", "Scratches on the screen"
    found = prices.estimate("Samsung Galaxy S21 128GB", [fault, lock, wear], opener=opener,
                            description=f"{fault}. {lock}. {wear}.",
                            sorter=Sorter({fault: ["fault"], lock: ["network lock"], wear: ["wear"]}))
    assert sent == [[]]
    assert rows(found) == [([fault], ["fault"], "own", -0.333), ([wear], ["wear"], "own none", None),
                           ([lock], ["network lock"], "own", -0.04)]
    assert found["price"] == 154 and abs(made_by_rows(found) - found["price"]) < 1


def test_wear_alone_is_the_any_flaw_cut():
    opener, _ = api()
    words = "Light scratches on the back"
    found = prices.estimate("Samsung Galaxy S21 128GB", [words], opener=opener, description=words,
                            sorter=Sorter({words: ["wear"]}))
    assert rows(found) == [([words], ["wear"], "own", -0.125)] and found["price"] == 210


def test_a_damaged_samsungs_wear_is_in_its_damage_cut():
    """The damage table is measured against flawless ones, so its cut already has what any flaw takes in it: wear beside
    damage takes nothing more (before, the phones' wear cut came off on top of it)."""
    opener, sent = api()
    damage, wear = "Cracked screen", "scratches on the back"
    found = prices.estimate("Samsung Galaxy S21 128GB", [damage, wear], opener=opener,
                            description=f"{damage}, {wear}.", sorter=Sorter({damage: ["damage"], wear: ["wear"]}))
    assert sent == [[]]
    # a clean one £240: a pricier UK Samsung (over £147.50), moderate damage -37.5%, from 65 UK listings
    assert found["damage"]["cut"] == -0.375 and found["damage"]["n"] == 65 and not found["damage"]["rough"]
    assert rows(found) == [([damage], ["damage"], "damage", -0.375), (["Scratches on the back"], ["wear"], "own none", None)]
    assert found["price"] == 150


def test_a_macbooks_cuts_are_its_own_and_one_it_has_too_few_of_is_the_iphones():
    opener, sent = api()
    wear, fake = "Small scratch on the lid", "The screen is not genuine"
    found = prices.estimate("MacBook Air M1 2020 256GB", [wear, fake], opener=opener, description=f"{wear}. {fake}.",
                            sorter=Sorter({wear: ["wear"], fake: ["not genuine"]}))
    assert sent == [[]]
    assert found["own_cuts"]["wear"] == {"cut": -0.048, "n": 532, "rough": False, "from": None}
    assert found["own_cuts"]["not genuine"]["from"] == "the iPhone" and found["own_cuts"]["not genuine"]["rough"]
    # not genuine -10.8% (the iPhone's: 8 MacBooks), wear beside it nothing more
    assert rows(found) == [([fake], ["not genuine"], "own", -0.108), ([wear], ["wear"], "own none", None)]
    assert found["price"] == 214


def test_a_locked_samsung_with_too_few_for_parts_sales_takes_its_own_measured_cut():
    words = "Google account locked"
    opener, sent = api(parts_sales=False)
    found = prices.estimate("Samsung Galaxy S21 128GB", [words], opener=opener, description=words,
                            sorter=Sorter({words: ["lock"]}))
    assert sent == [["lock"]]  # locked: the API prices it as that alone, as before
    # the API's rough cut was -38% (£149); UK sellers ask 51.6% less for a locked Samsung (25 listings: still rough)
    assert found["price"] == 116 and found["rough"] is True
    assert found["own_whole"] == {"kind": "lock", "cut": -0.516, "n": 25, "rough": True, "from": "few listings"}
    assert rows(found) == [([words], ["lock"], "own lock", -0.516)]
    # with for-parts sales to go on, it's what for-parts ones sell for, as before
    prices._seen.clear()
    opener, _ = api(parts_sales=True)
    found = prices.estimate("Samsung Galaxy S21 128GB", [words], opener=opener, description=words,
                            sorter=Sorter({words: ["lock"]}))
    assert found["price"] == 70 and "own_whole" not in found and rows(found)[0][2] == "parts price"


def test_an_iphone_is_cut_by_its_own_measure_too():
    opener, sent = api()
    words = "Face ID doesn't work"
    found = prices.estimate("iPhone 13 128GB", [words], opener=opener, description=words,
                            sorter=Sorter({words: ["fault"]}))
    # 4 Nov evening: UK sellers ask 25.9% less for an iPhone with a fault (204 listings), not the API table's 17.1%
    assert sent == [[]] and found["price"] == 178 and found["own_cuts"]["fault"]["n"] == 204
    assert rows(found) == [([words], ["fault"], "own", -0.259)]


def test_a_category_with_no_own_table_is_cut_by_the_prices_apis_table(monkeypatch):
    monkeypatch.setattr(prices, "kind_table", lambda category, market="uk": None)
    opener, sent = api()
    words = "Face ID doesn't work"
    found = prices.estimate("iPhone 13 128GB", [words], opener=opener, description=words,
                            sorter=Sorter({words: ["fault"]}))
    assert sent == [["fault"]] and found["price"] == 199 and "own_cuts" not in found
    assert rows(found) == [([words], ["fault"], "api", -0.171)]
