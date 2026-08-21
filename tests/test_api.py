"""The API AlertFlip calls, tested with pretend models and a throwaway audit
log: no AI runs, nothing is sent anywhere, and nothing costs anything."""

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from flip import api
from flip.ai import Reply
from flip.audit import AuditLog
from flip.style import load_messages, style_card
from tests.fakes import FakeModel

ROOT = Path(__file__).resolve().parent.parent
PAST = style_card(load_messages(ROOT / "testset" / "messages.example.csv"))  # messages that repeat
KEY = "test-key"
LISTING = {"title": "iPhone 13 128GB Blue", "asking_price": "220", "marketplace": "facebook",
           "description": "Black dot on the screen, doesn't affect use. Collection only from Leeds LS6. "
                          "Price is firm, no offers."}
READ = {"flaws": ["Black dot on the screen, doesn't affect use"], "pickup": "Collection only from Leeds LS6",
        "no_offers": "Price is firm, no offers"}
LISTED = {"colour": "Midnight", "condition_id": "3000", "condition_note": "Light scratch on the back. Battery health 87%.",
          "description": "Apple iPhone 13 128GB in Midnight, unlocked, boxed. Light scratch on the back, "
                         "battery health 87%."}
# a real 2x2 JPEG, so a photo goes through the same conversion the app uses
JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAASABIAAD/4QBMRXhpZgAATU0AKgAAAAgAAYdpAAQAAAABAAAAGgAAAAAAA6ABAAMAAAABAAEAAKACAAQA"
    "AAABAAAAAqADAAQAAAABAAAAAgAAAAD/7QA4UGhvdG9zaG9wIDMuMAA4QklNBAQAAAAAAAA4QklNBCUAAAAAABDUHYzZjwCyBOmA"
    "CZjs+EJ+/8AAEQgAAgACAwEiAAIRAQMRAf/EAB8AAAEFAQEBAQEBAAAAAAAAAAABAgMEBQYHCAkKC//EALUQAAIBAwMCBAMFBQQE"
    "AAABfQECAwAEEQUSITFBBhNRYQcicRQygZGhCCNCscEVUtHwJDNicoIJChYXGBkaJSYnKCkqNDU2Nzg5OkNERUZHSElKU1RVVldY"
    "WVpjZGVmZ2hpanN0dXZ3eHl6g4SFhoeIiYqSk5SVlpeYmZqio6Slpqeoqaqys7S1tre4ubrCw8TFxsfIycrS09TV1tfY2drh4uPk"
    "5ebn6Onq8fLz9PX29/j5+v/EAB8BAAMBAQEBAQEBAQEAAAAAAAABAgMEBQYHCAkKC//EALURAAIBAgQEAwQHBQQEAAECdwABAgMR"
    "BAUhMQYSQVEHYXETIjKBCBRCkaGxwQkjM1LwFWJy0QoWJDThJfEXGBkaJicoKSo1Njc4OTpDREVGR0hJSlNUVVZXWFlaY2RlZmdo"
    "aWpzdHV2d3h5eoKDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uLj5OXm5+jp6vLz"
    "9PX29/j5+v/bAEMAAgICAgICAwICAwUDAwMFBgUFBQUGCAYGBgYGCAoICAgICAgKCgoKCgoKCgwMDAwMDA4ODg4ODw8PDw8PDw8P"
    "D//bAEMBAgICBAQEBwQEBxALCQsQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEP/dAAQA"
    "Af/aAAwDAQACEQMRAD8A/Heiiiv0Q8M//9k="
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """The API with the key set, and use(...) to give it pretend models and a style card."""
    monkeypatch.setenv("FLIP_API_KEY", KEY)
    log = AuditLog(tmp_path / "audit.sqlite3")

    def use(local=None, api_model=None, card=None):
        api.app.dependency_overrides[api.setup] = lambda: api.Setup(local, api_model, log, card)
        api.app.dependency_overrides[api.audit] = lambda: log

    test = TestClient(api.app, headers={"X-API-Key": KEY})
    test.use = use
    use()
    yield test
    api.app.dependency_overrides.clear()


# ── the key ─────────────────────────────────────────────────────────────────

def test_health_needs_no_key_and_shows_none(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "pretend-anthropic-key")
    answer = TestClient(api.app).get("/health")
    assert answer.status_code == 200
    assert answer.json()["api_key_set"] is True and answer.json()["flip_api_key_set"] is True
    assert "pretend-anthropic-key" not in answer.text and KEY not in answer.text


@pytest.mark.parametrize("headers, status", [({}, 401), ({"X-API-Key": "wrong"}, 401)])
def test_everything_else_needs_the_key(client, headers, status):
    for answer in (TestClient(api.app, headers=headers).get("/stats"),
                   TestClient(api.app, headers=headers).post("/messages/draft", json={"listing": LISTING})):
        assert answer.status_code == status


def test_with_no_key_set_nobody_can_call_it(client, monkeypatch):
    monkeypatch.delenv("FLIP_API_KEY")
    assert client.get("/stats").status_code == 503


# ── messages ────────────────────────────────────────────────────────────────

def test_a_message_from_your_own_sentences_with_the_reading_and_the_note(client):
    local = FakeModel("gemma3:4b", READ)  # reads the listing; the message is written without AI
    client.use(local=local, card=PAST)
    answer = client.post("/messages/draft", json={"listing": LISTING, "mention": True})
    assert answer.status_code == 200
    draft = answer.json()
    assert (draft["status"], draft["written_by"], draft["offer"], draft["offer_pence"]) == \
        ("ready", "template", "£185", 18500)
    assert draft["message"] == "Hi mate, is this still available? Would you take £185 cash, given the black dot on " \
                               "the screen? Can collect from Leeds LS6 today."
    assert draft["note"] == 'The seller says: "Price is firm, no offers"'
    assert draft["reading"]["flaws"] == ["Black dot on the screen"] and draft["reading"]["read_by"] == "gemma3:4b"
    assert draft["kind"] == "lower" and isinstance(draft["draft_id"], int) and draft["cost_pence"] == 0
    assert len(local.asked) == 1  # the reading only


def test_a_message_the_ai_writes(client):
    varied = style_card([{"my_message": "Hiya, would £90 do? 😊"}, {"my_message": "Hey! Could you do £120?"}])
    local = FakeModel("gemma3:4b", READ, {"message": "Hiya, would you take £185, given the black dot on the screen? 😊"})
    client.use(local=local, card=varied)
    draft = client.post("/messages/draft", json={"listing": LISTING, "mention": True}).json()
    assert (draft["status"], draft["written_by"]) == ("ready", "gemma3:4b")
    assert [a["model"] for a in draft["attempts"]] == ["gemma3:4b"]


def test_with_no_model_running_code_reads_and_writes_alone(client):
    down = Reply("gemma3:4b", error="the local model isn't running (connection refused)", reachable=False)
    client.use(local=FakeModel("gemma3:4b", down), card=PAST)
    draft = client.post("/messages/draft", json={"listing": LISTING}).json()
    assert (draft["status"], draft["written_by"], draft["reading"]["read_by"]) == ("ready", "template", "code")
    assert draft["note"] == 'The seller says: "Price is firm"'


@pytest.mark.parametrize("change", [{"kind": "cheeky"}, {"length": "essay"}, {"writer": "poet"},
                                    {"listing": {**LISTING, "asking_price": "two hundred"}},
                                    {"listing": {**LISTING, "title": ""}}])
def test_a_request_in_the_wrong_shape_is_refused_before_anything_runs(client, change):
    local = FakeModel("gemma3:4b")
    client.use(local=local)
    assert client.post("/messages/draft", json={"listing": LISTING, **change}).status_code == 422
    assert local.asked == []


# ── listings ────────────────────────────────────────────────────────────────

def test_a_listing_drafted_from_the_form_and_photos(client):
    local = FakeModel("gemma3:4b", LISTED)
    client.use(local=local)
    answer = client.post("/listings/draft", data={"title": "iPhone 13 128GB unlocked",
                                                  "notes": "boxed, battery 87%, light scratch on the back"},
                         files=[("photos", ("back.jpg", JPEG, "image/jpeg"))])
    assert answer.status_code == 200, answer.text
    draft = answer.json()
    assert (draft["status"], draft["ebay_title"], draft["photo_count"]) == \
        ("ready", "Apple iPhone 13 128GB Midnight Unlocked", 1)
    assert draft["filled_by_code"]["model"] == "iPhone 13" and draft["condition_id"] == "3000"
    assert len(local.asked[0]["photos"]) == 1


def test_a_listing_needs_photos_that_are_photos(client):
    client.use(local=FakeModel("gemma3:4b"))
    too_many = [("photos", (f"{n}.jpg", JPEG, "image/jpeg")) for n in range(api.MAX_PHOTOS + 1)]
    assert client.post("/listings/draft", data={"title": "iPhone 13"}, files=too_many).status_code == 422
    text = [("photos", ("notes.txt", b"hello", "text/plain"))]
    assert client.post("/listings/draft", data={"title": "iPhone 13"}, files=text).status_code == 422
    broken = [("photos", ("photo.jpg", b"not a photo", "image/jpeg"))]
    assert client.post("/listings/draft", data={"title": "iPhone 13"}, files=broken).status_code == 422


def test_a_listing_the_catalogue_doesnt_know_needs_you_and_asks_no_ai(client):
    local = FakeModel("gemma3:4b")
    client.use(local=local)
    draft = client.post("/listings/draft", data={"title": "Dyson V11 cordless vacuum"}).json()
    assert (draft["status"], draft["reasons"]) == ("needs you", ["the model isn't in the catalogue"])
    assert local.asked == []


# ── approving, and the cost meter ───────────────────────────────────────────

def test_approving_records_what_you_sent_and_whether_you_edited_it(client):
    client.use(local=FakeModel("gemma3:4b", READ), card=PAST)
    draft = client.post("/messages/draft", json={"listing": LISTING, "mention": True}).json()
    url = f"/drafts/{draft['draft_id']}/approve"
    assert client.post(url, json={"sent": draft["message"]}).json()["edited"] is False
    assert client.post(url, json={"sent": draft["message"] + " Cheers"}).json()["edited"] is True
    assert client.post("/drafts/9999/approve", json={"sent": "hi"}).status_code == 404
    assert client.post(url, json={"sent": ""}).status_code == 422


def test_the_cost_meter_adds_it_all_up(client):
    client.use(local=FakeModel("gemma3:4b", READ, READ), api_model=FakeModel("claude-haiku-5-5"), card=PAST)
    first = client.post("/messages/draft", json={"listing": LISTING, "mention": True}).json()
    client.post("/messages/draft", json={"listing": LISTING, "kind": "asking", "mention": True})
    client.post(f"/drafts/{first['draft_id']}/approve", json={"sent": first["message"]})
    stats = client.get("/stats").json()
    assert (stats["drafts"], stats["ready"], stats["needs_you"]) == (2, 2, 0)
    assert stats["done_on_this_mac"] == 1.0 and stats["cost_pence"] == 0
    assert {m["model"] for m in stats["models"]} == {"gemma3:4b", "template"}
    assert (stats["approved"], stats["edited_before_sending"]) == (1, 0)


def test_the_price_you_picked_is_drafted_and_one_that_doesnt_fit_is_refused(client):
    client.use(local=FakeModel("gemma3:4b", READ, READ), card=PAST)
    draft = client.post("/messages/draft", json={"listing": LISTING, "offer": "150", "mention": True}).json()
    assert (draft["offer"], draft["offer_pence"]) == ("£150", 15000) and "£150" in draft["message"]
    refused = client.post("/messages/draft", json={"listing": LISTING, "offer": "230"})
    assert refused.status_code == 422 and "isn't a lower offer" in refused.json()["detail"]
    assert client.post("/messages/draft", json={"listing": LISTING, "offer": "cheap"}).status_code == 422
