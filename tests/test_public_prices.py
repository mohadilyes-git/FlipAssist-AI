"""The free public UK prices (flip.prices.mode): with no PRICES_KEY, FlipAssist asks the AlertFlip prices API with no
key at all, for the UK only and only iPhones, Samsung phones and MacBooks, at PRICES_URL if it's set, else the API's
own address; FLIP_PUBLIC_PRICES=off turns that off, and your own PRICES_URL and PRICES_KEY are asked as before. Every
refusal is said in FlipAssist's words, a busy one with when to try again. Pretend API: nothing is sent anywhere (and
tests/conftest.py stops any test that tries)."""

import io
import json
import urllib.error

import pytest

from flip import prices

OWN_URL = "https://example.test/functions/v1/prices"
ANSWER = {"mode": "catalogue", "model": "iphone 13", "storage_gb": 128, "ram_gb": None, "currency": "GBP",
          "sales": 38, "middle": 210, "low": 180, "high": 240, "price": 210, "factor": 1.0, "used": ["no flaw"],
          "rough": False, "exact_match": True,
          "plan": {"kind": "iphone", "model": "iphone 13", "storage_gb": 128, "ram_gb": None, "condition": "good"}}
# what the free prices add: when the model's sales were last checked
FREE = {**ANSWER, "public": True, "checked_at": "2026-11-02T09:30:00.000Z"}


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def nothing_set(monkeypatch):
    """No prices settings at all, as on a fresh download: each test sets what it needs."""
    for name in ("PRICES_URL", "PRICES_KEY", "FLIP_PUBLIC_PRICES"):
        monkeypatch.delenv(name, raising=False)
    prices._seen.clear()


def asking(answer=FREE):
    """A pretend prices API that answers with answer and keeps what it was sent: (url, headers, body)."""
    sent = []

    def opener(request, timeout):
        sent.append((request.full_url, dict(request.header_items()), json.loads(request.data)))
        return Response(json.dumps(answer).encode())
    return opener, sent


def refusing(status, error=None, top=None, headers=None):
    """A pretend prices API that refuses: {"error": error, **top} with this HTTP status and headers."""
    sent = []

    def opener(request, timeout):
        sent.append(request.full_url)
        body = {**({"error": error} if error is not None else {}), **(top or {})}
        raise urllib.error.HTTPError(request.full_url, status, "refused", headers or {},
                                     io.BytesIO(json.dumps(body).encode()))
    return opener, sent


# ── which prices are asked ───────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("settings, mode", [
    ({}, "public"),  # a fresh download: the free prices
    ({"PRICES_URL": OWN_URL}, "public"),  # an address with no key: asked the free way
    ({"PRICES_URL": OWN_URL, "PRICES_KEY": "k" * 64}, "key"),  # your own, as before
    ({"PRICES_KEY": "k" * 64}, "no url"),  # a key with nowhere to send it: never sent to the free address
    ({"FLIP_PUBLIC_PRICES": "off"}, "off"),
    ({"FLIP_PUBLIC_PRICES": " OFF "}, "off"),
    ({"FLIP_PUBLIC_PRICES": "off", "PRICES_URL": OWN_URL}, "off"),
    ({"FLIP_PUBLIC_PRICES": "off", "PRICES_URL": OWN_URL, "PRICES_KEY": "k" * 64}, "key"),  # off: your own still work
    ({"FLIP_PUBLIC_PRICES": ""}, "public"),  # empty, as .env.example leaves it
    ({"FLIP_PUBLIC_PRICES": "on"}, "public"),
    ({"PRICES_URL": "  ", "PRICES_KEY": " "}, "public"),  # spaces are nothing
])
def test_the_settings_choose_your_own_prices_the_free_ones_or_none(monkeypatch, settings, mode):
    for name, value in settings.items():
        monkeypatch.setenv(name, value)
    assert prices.mode() == mode
    assert prices.available() is (mode in ("key", "public"))


def test_with_no_key_the_free_prices_are_asked_at_the_apis_own_address_with_no_key_sent():
    opener, sent = asking()
    found = prices.estimate("iPhone 13 128GB Blue", [], opener=opener, description="Lovely phone.")
    url, headers, body = sent[0]
    assert url == prices.PUBLIC_PRICES_URL == "https://kgwykdmpcmvtyjnmlnqk.supabase.co/functions/v1/prices-"
    assert headers == {"Content-type": "application/json"}  # no x-prices-key, no Authorization: nothing else at all
    assert body == {"action": "price", "country": "uk", "title": "iPhone 13 128GB Blue", "kinds": [], "strict": True}
    assert (found["price"], found["public"], found["checked_at"], found["stale"]) == \
        (210, True, "2026-11-02T09:30:00.000Z", False)


def test_prices_url_with_no_key_is_asked_the_free_way(monkeypatch):
    monkeypatch.setenv("PRICES_URL", OWN_URL)
    opener, sent = asking()
    found = prices.estimate("Samsung Galaxy S23 256GB", [], opener=opener, description="")
    assert (sent[0][0], sent[0][1], found["public"]) == (OWN_URL, {"Content-type": "application/json"}, True)


def test_the_free_prices_get_the_same_request_your_own_key_does_and_your_own_is_asked_as_before(monkeypatch):
    """The keyed path unchanged: the same body, your key in x-prices-key, its answer as before (no public, checked_at
    or stale); the free path sends that same body with no key."""
    listing = ("MacBook Pro 15 inch", ["Small crack on the back", "Battery 76%"],
               "Apple MacBook Pro 15 (2018) Core i7, 16GB RAM. Small crack on the back. Battery 76%.")
    answer = {**ANSWER, "model": "macbook pro 15 2018", "kind": "macbook", "storage_gb": 512, "ram_gb": 16}
    free_opener, free_sent = asking({**answer, "public": True, "checked_at": None})
    free = prices.estimate(listing[0], listing[1], opener=free_opener, description=listing[2])
    monkeypatch.setenv("PRICES_URL", OWN_URL)
    monkeypatch.setenv("PRICES_KEY", "k" * 64)
    own_opener, own_sent = asking(answer)
    own = prices.estimate(listing[0], listing[1], opener=own_opener, description=listing[2])
    assert own_sent[0][2] == free_sent[0][2]  # the description's model details, the RAM, the kinds: all the same
    assert own_sent[0][0] == OWN_URL
    assert own_sent[0][1] == {"Content-type": "application/json", "X-prices-key": "k" * 64}
    assert not {"public", "checked_at", "stale"} & set(own)
    assert {k: v for k, v in free.items() if k not in ("public", "checked_at", "stale")} == own
    assert (free["public"], free["checked_at"], free["stale"]) == (True, None, False)


def test_the_off_switch_asks_nothing_but_your_own_key_still_works(monkeypatch):
    monkeypatch.setenv("FLIP_PUBLIC_PRICES", "off")
    opener, sent = asking()
    found = prices.estimate("iPhone 13 128GB", [], opener=opener)
    assert found == {"skipped": "The free UK prices are off (FLIP_PUBLIC_PRICES=off in .env): take that line out, "
                                "or add your own PRICES_URL and PRICES_KEY"}
    assert sent == []
    monkeypatch.setenv("PRICES_URL", OWN_URL)
    monkeypatch.setenv("PRICES_KEY", "k" * 64)
    assert prices.estimate("iPhone 13 128GB", [], opener=opener)["price"] == 210
    assert sent[0][1]["X-prices-key"] == "k" * 64


def test_a_key_with_no_address_is_never_sent_anywhere(monkeypatch):
    monkeypatch.setenv("PRICES_KEY", "k" * 64)
    opener, sent = asking()
    assert prices.estimate("iPhone 13 128GB", [], opener=opener) == {
        "skipped": "The AlertFlip API isn't set: add PRICES_URL to .env with your PRICES_KEY, or take PRICES_KEY out "
                   "for the free UK prices"}
    assert sent == []


def test_the_free_prices_are_for_the_uk_and_iphones_samsungs_and_macbooks_only(monkeypatch):
    opener, sent = asking()
    assert prices.estimate("iPhone 13 128GB", [], country="us", opener=opener) == {"skipped": prices.PUBLIC_UK_ONLY}
    for title in ("PS5 Slim 1TB", "iPhone 13 case", "Samsung Galaxy Tab S9", "MacBook Pro charger 61W"):
        assert prices.estimate(title, [], opener=opener) == {"skipped": prices.SKIPPED}, title
    assert sent == []
    monkeypatch.setenv("PRICES_URL", OWN_URL)
    monkeypatch.setenv("PRICES_KEY", "k" * 64)
    prices.estimate("iPhone 13 128GB", [], country="us", opener=opener)  # your own key: asked as before
    assert sent[0][2]["country"] == "us"


def test_a_free_answer_is_kept_in_memory_and_a_refusal_isnt():
    opener, sent = asking()
    for _ in range(2):
        prices.estimate("iPhone 13 128GB", ["Small scratch on the back"], opener=opener,
                        description="Small scratch on the back.")
    assert len(sent) == 1
    busy, tried = refusing(429, {"code": "PUBLIC_BUSY", "message": "Too many price checks", "retry_after_s": 600})
    for _ in range(2):
        prices.estimate("iPhone 12 64GB", [], opener=busy)
    assert len(tried) == 2  # busy is asked again: it may not be by then


def test_old_sales_are_said_to_be_old():
    opener, _ = asking({**FREE, "checked_at": "2026-09-12T08:00:00Z", "stale": True})
    found = prices.estimate("iPhone 13 128GB", [], opener=opener)
    assert (found["checked_at"], found["stale"]) == ("2026-09-12T08:00:00Z", True)
    prices._seen.clear()
    opener, _ = asking({**FREE, "checked_at": 1731000000, "stale": "yes"})  # not a time, not true: neither is said
    found = prices.estimate("iPhone 13 128GB", [], opener=opener)
    assert (found["checked_at"], found["stale"]) == (None, False)


def test_the_damage_judge_is_still_asked_on_the_free_prices():
    asked = []

    def judge(flaws, title, description, kind):
        asked.append(flaws)
        return "minor", "code and Claude Haiku 5.5"
    opener, _ = asking()
    found = prices.estimate("iPhone 13 128GB", ["Small crack on the back"], opener=opener,
                            description="Small crack on the back.", judge=judge)
    assert asked == [["Small crack on the back"]]
    assert (found["damage"]["level"], found["damage"]["by"], found["public"]) == \
        ("minor", "code and Claude Haiku 5.5", True)


# ── its refusals, in FlipAssist's words ──────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status, error, top, headers, said", [
    (429, {"code": "PUBLIC_BUSY", "message": "Too many price checks from here", "retry_after_s": 1200}, None, None,
     "The free UK prices are busy: try again in about 20 minutes"),
    (429, {"code": "PUBLIC_BUSY", "message": "x"}, {"retry_after_s": 30}, None,
     "The free UK prices are busy: try again in a minute"),  # retry_after_s beside the error
    (429, {"code": "PUBLIC_BUSY", "message": "x"}, None, {"Retry-After": "7200"},
     "The free UK prices are busy: try again in about 2 hours"),  # or the HTTP header
    (429, {"code": "PUBLIC_BUSY", "message": "x"}, None, None, "The free UK prices are busy: try again later"),
    (503, {"code": "PUBLIC_OFF", "message": "Free prices are off"}, None, None,
     "The free UK prices are switched off for now: try again later, or add your own PRICES_URL and PRICES_KEY to .env"),
    (403, {"code": "PUBLIC_NOT_ALLOWED", "message": "Only iPhones, Samsung phones and MacBooks on ebay.co.uk"}, None,
     None,
     "The free UK prices are only for the iPhone, Samsung phone and MacBook models the AlertFlip prices API knows, and "
     "it couldn't match this title to one: put the model in the title (like iPhone 13 128GB)"),
    # too few saved sales, whether this month's free checks are used up or a check found too few
    (404, {"code": "PUBLIC_NO_DATA", "message": "No saved sales, and this month's checks are used up"}, None, None,
     "Not enough recent UK sales of this model are saved to price it: the free prices check each model about once a "
     "month, so try again next month"),
    (404, {"code": "PUBLIC_NO_DATA", "message": "Not enough recent UK sales of this model (iphone 13) to price it."},
     None, None, "Not enough recent UK sales of this model are saved to price it: the free prices check each model "
     "about once a month, so try again next month"),
    # a prices API that wants a key (one without the free prices yet), or Supabase asking for a sign-in itself
    (401, {"code": "UNAUTHORIZED", "message": "Sign in to AlertFlip first."}, None, None,
     "The AlertFlip prices API asked for a key, so it has no free UK prices to give: add your own PRICES_URL and "
     "PRICES_KEY to .env"),
    (401, None, {"code": 401, "message": "Missing authorization header"}, None,
     "The AlertFlip prices API asked for a key, so it has no free UK prices to give: add your own PRICES_URL and "
     "PRICES_KEY to .env"),
    # the API's other refusals as before
    (404, {"code": "NO_SALES", "message": "No good sales of iphone 13 on ebay.co.uk"}, None, None,
     prices.REFUSED["NO_SALES"]),
    (503, {"code": "UNAVAILABLE", "message": "New price checks are paused until next month."}, None, None,
     prices.MONTHLY_CAP),
    (500, {"code": "SOMETHING_NEW", "message": "ebay.co.uk said no"}, None, None,
     "The AlertFlip API couldn't price it (SOMETHING_NEW)"),
    (502, {"code": ["PUBLIC_BUSY"], "message": {"no": "words"}}, None, None, "The AlertFlip API answered 502"),
])
def test_each_refusal_of_the_free_prices_is_said_plainly(status, error, top, headers, said):
    opener, sent = refusing(status, error, top, headers)
    found = prices.estimate("iPhone 13 128GB", [], opener=opener)
    assert found == {"error": said} and sent == [prices.PUBLIC_PRICES_URL]
    assert "ebay" not in said.lower()


def test_a_slow_answer_says_to_try_again_and_no_network_says_so(monkeypatch):
    """A model whose sales are a month old is checked again while its first ask waits: past TIMEOUT that ask says to
    try again, not that the API couldn't be reached. Your own key's words for it are as before."""
    def raising(error):
        def opener(request, timeout):
            raise error
        return opener
    for slow in (TimeoutError("timed out"), urllib.error.URLError(TimeoutError("timed out"))):
        assert prices.estimate("iPhone 13 128GB", [], opener=raising(slow)) == {"error": prices.PUBLIC_SLOW}
    assert prices.estimate("iPhone 13 128GB", [], opener=raising(urllib.error.URLError("no network"))) == \
        {"error": "Couldn't reach the AlertFlip API (URLError)"}
    monkeypatch.setenv("PRICES_URL", OWN_URL)
    monkeypatch.setenv("PRICES_KEY", "k" * 64)
    assert prices.estimate("iPhone 13 128GB", [], opener=raising(TimeoutError("timed out"))) == \
        {"error": "Couldn't reach the AlertFlip API (TimeoutError)"}


def test_a_refusal_with_a_price_missing_is_said_the_same_way():
    opener, _ = asking({"error": {"code": "PUBLIC_NO_DATA", "message": "No saved sales"}})
    assert prices.estimate("iPhone 13 128GB", [], opener=opener)["error"] == prices.PUBLIC_REFUSED["PUBLIC_NO_DATA"]


def test_your_own_key_keeps_its_own_words_for_a_refused_key(monkeypatch):
    monkeypatch.setenv("PRICES_URL", OWN_URL)
    monkeypatch.setenv("PRICES_KEY", "k" * 64)
    opener, _ = refusing(401, {"code": "UNAUTHORIZED", "message": "Sign in to AlertFlip first."})
    assert prices.estimate("iPhone 13 128GB", [], opener=opener) == {"error": prices.REFUSED["UNAUTHORIZED"]}


@pytest.mark.parametrize("seconds, said", [
    (0, "try again in a minute"), (45, "try again in a minute"), (60, "try again in a minute"),
    (61, "try again in about 2 minutes"), (1200, "try again in about 20 minutes"),
    ("900", "try again in about 15 minutes"),
    (3540, "try again in about 59 minutes"), (3599, "try again in about an hour"), (3600, "try again in about an hour"),
    (5400, "try again in about 2 hours"), (40000, "try again in about 11 hours"), (200000, "try again in about 2 days"),
    (None, "try again later"), (-5, "try again later"), (True, "try again later"), ("soon", "try again later"),
    (float("nan"), "try again later"), (float("inf"), "try again later"), ([60], "try again later"),
])
def test_when_to_try_again_is_said_in_minutes_hours_or_days(seconds, said):
    assert prices.try_again(seconds) == said


def test_a_price_asked_with_no_pretend_api_is_stopped_before_anything_is_sent(monkeypatch):
    """The real request (urllib's own opener) is never made from a test: tests/conftest.py refuses the address before
    it's looked up. An address that doesn't exist stands in for the real one here."""
    monkeypatch.setenv("PRICES_URL", "https://prices.invalid/functions/v1/prices-")
    with pytest.raises(RuntimeError, match="a test tried to look up prices.invalid"):
        prices.estimate("iPhone 13 128GB")
