"""The API AlertFlip calls, tested with pretend models and a throwaway audit
log: no AI runs, nothing is sent anywhere, and nothing costs anything."""

import base64
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from flip import api
from flip.ai import Reply
from flip.audit import AuditLog
from flip.style import StyleBook, load_messages
from tests.fakes import FakeModel

ROOT = Path(__file__).resolve().parent.parent
PAST = load_messages(ROOT / "testset" / "messages.example.csv")  # messages that repeat
KEY = "test-key-for-the-api-0123456789-abcdef"  # 32 characters or more, as a real key is
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
    """The API with the key set, and use(...) to give it pretend models and your past messages."""
    monkeypatch.setenv("FLIP_API_KEY", KEY)
    log = AuditLog(tmp_path / "audit.sqlite3")
    book = StyleBook(tmp_path / "style.sqlite3")  # no search: the examples come from the style card alone

    def use(local=None, api_model=None, messages=(), kinds=None, listing=None, listing_facts=False, reader=None):
        book.add(list(messages), "csv")
        api.app.dependency_overrides[api.setup] = lambda: api.Setup(local, api_model, log, kinds=kinds, listing=listing,
                                                                    listing_facts=listing_facts, reader=reader)
        api.app.dependency_overrides[api.audit] = lambda: log
        api.app.dependency_overrides[api.style] = lambda: book

    test = TestClient(api.app, headers={"X-API-Key": KEY})
    test.use, test.book = use, book
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


def test_health_says_which_paid_model_does_what_and_whether_the_prices_api_is_set(client, monkeypatch):
    """14 Oct: Claude Haiku 5.5 only checks each reason; Claude Sonnet 5.5 reads or writes when this device's models
    can't, and fixes a reason the check flags."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    for name in ("FLIP_BACKUP_MODEL", "FLIP_WORDING_CHECK", "FLIP_WORDING_FIX", "PRICES_URL", "PRICES_KEY",
                 "FLIP_PUBLIC_PRICES"):
        monkeypatch.delenv(name, raising=False)
    health = TestClient(api.app).get("/health").json()
    assert (health["api_model"], health["check_model"], health["fix_model"]) == \
        ("claude-sonnet-5-5", "claude-haiku-5-5", "claude-sonnet-5-5")
    # no key of your own: the free public UK prices, so the price tab (and the damage judge) can run
    assert (health["prices_api_set"], health["prices_mode"]) == (True, "public")
    monkeypatch.setenv("FLIP_PUBLIC_PRICES", "off")
    health = TestClient(api.app).get("/health").json()
    assert (health["prices_api_set"], health["prices_mode"]) == (False, "off")
    monkeypatch.setenv("PRICES_KEY", "k")  # a key with no address to send it to
    assert TestClient(api.app).get("/health").json()["prices_mode"] == "no url"
    monkeypatch.setenv("PRICES_URL", "https://example.test/prices")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    health = TestClient(api.app).get("/health").json()
    assert (health["prices_api_set"], health["prices_mode"]) == (True, "key")
    assert (health["check_model"], health["fix_model"]) == ("", "")


def test_health_names_each_model_by_its_job_and_says_which_isnt_installed(client, monkeypatch):
    """6 Oct review: Home said every model was running whenever Ollama answered."""
    import io
    import urllib.request

    class Tags(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    listed = {"models": [{"name": n} for n in ("flip-reader-5:latest", "flip-kinds-1:latest", "gemma3:4b")]}
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Tags(json.dumps(listed).encode()))
    for setting in ("FLIP_READER_MODEL", "FLIP_WORDING_MODEL", "FLIP_KINDS_MODEL", "FLIP_STYLE_AI"):
        monkeypatch.delenv(setting, raising=False)
    models = {m["job"]: (m["name"], m["installed"]) for m in TestClient(api.app).get("/health").json()["models"]}
    assert models == {"reads listings": ("flip-reader-5", True), "words the reason": ("flip-wording-4b", False),
                      "sorts price flaws": ("flip-kinds-1", True), "reads your style": ("flip-style-1b", False),
                      "writes messages": ("gemma3:4b", True)}
    monkeypatch.setenv("FLIP_STYLE_AI", "")  # turned off: not asked for, so not listed
    assert "reads your style" not in {m["job"] for m in TestClient(api.app).get("/health").json()["models"]}


@pytest.mark.parametrize("body", ['{"models": 3}', "[" * 100000, '["not", "ollama"]', "not json", None])
def test_health_answers_whatever_is_on_ollamas_port(client, monkeypatch, body):
    """15 Nov review: an answer that isn't Ollama's model list ({"models": 3}, deeply nested JSON, a broken status
    line) made /health a 500, so Home couldn't show the models. Something else on its port is no Ollama running, as
    the reader's own lookup (flip.reader.installed) already took it."""
    import http.client
    import io
    import urllib.request

    class Tags(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def opened(url, timeout):
        if body is None:
            raise http.client.BadStatusLine("x")
        return Tags(body.encode())

    monkeypatch.setattr(urllib.request, "urlopen", opened)
    answer = TestClient(api.app).get("/health")
    assert answer.status_code == 200
    assert (answer.json()["local_running"], answer.json()["models"]) == (False, [])


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
    client.use(local=local, messages=PAST)
    answer = client.post("/messages/draft", json={"listing": LISTING, "mention": True})
    assert answer.status_code == 200
    draft = answer.json()
    assert (draft["status"], draft["written_by"], draft["offer"], draft["offer_pence"]) == \
        ("ready", "template", "£185", 18500)
    assert draft["message"] == "Hi mate, is this still available? Would you take £185 cash, given the black dot on " \
                               "the screen? Can collect today."  # your messages never name a place (26 Sep)
    assert draft["note"] == 'The seller says: "Price is firm, no offers"'
    assert draft["reading"]["flaws"] == ["Black dot on the screen"] and draft["reading"]["read_by"] == "gemma3:4b"
    assert draft["kind"] == "lower" and isinstance(draft["draft_id"], int) and draft["cost_pence"] == 0
    assert len(local.asked) == 1  # the reading only


def test_the_docs_name_the_paid_backup_as_a_messages_paid_writer():
    """15 Nov review: /docs said a message is written by "template (no AI), gemma3:4b or claude-haiku-5-5"; since 14 Oct
    the paid writer is the backup, Claude Sonnet 5.5 unless FLIP_BACKUP_MODEL names another, and Haiku writes none."""
    said = api.app.openapi()["components"]["schemas"]["MessageDraft"]["properties"]["written_by"]["description"]
    assert "haiku" not in said and api.BACKUP_MODEL in said and "FLIP_BACKUP_MODEL" in said


def test_a_message_the_ai_writes(client):
    varied = [{"my_message": "Hiya, would £90 do? 😊"}, {"my_message": "Hey! Could you do £120?"}]
    local = FakeModel("gemma3:4b", READ, {"message": "Hiya, would you take £185, given the black dot on the screen? 😊"})
    client.use(local=local, messages=varied)
    draft = client.post("/messages/draft", json={"listing": LISTING, "mention": True, "writer": "ai"}).json()
    assert (draft["status"], draft["written_by"]) == ("ready", "gemma3:4b")
    assert [a["model"] for a in draft["attempts"]] == ["gemma3:4b"]


def test_with_no_model_running_code_reads_and_writes_alone(client):
    down = Reply("gemma3:4b", error="the local model isn't running (connection refused)", reachable=False)
    client.use(local=FakeModel("gemma3:4b", down), messages=PAST)
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
    # eBay's own fields, in its words: the colour the AI saw is eBay's plain one, with the exact name
    assert draft["ebay_category"] == {"id": "9355", "name": "Mobile & Smart Phones", "path": "Mobile Phones & Communication"}
    fields = {f["name"]: (f["value"], f["required"], f["source"]) for f in draft["item_specifics"]}
    assert fields["Model"] == ("Apple iPhone 13", True, "the catalogue")
    assert fields["Storage Capacity"] == ("128 GB", True, "your title or notes")
    assert fields["Colour"] == ("Black", True, "the photos: Midnight")


def test_list_on_ebay_is_written_by_the_listing_model_first_and_local_mode_stays_on_this_device(client):
    # 14 Oct: Claude Haiku 5.5 writes first in the app (blind-judged on 40 real iPhones), Claude Sonnet 5.5 if it fails
    gemma, haiku = FakeModel("gemma3:4b", LISTED), FakeModel("claude-haiku-5-5", LISTED)
    client.use(local=gemma, api_model=FakeModel("claude-sonnet-5-5", LISTED), listing=haiku)
    form = {"title": "iPhone 13 128GB Midnight unlocked", "notes": "boxed, battery 87%, light scratch on the back"}
    draft = client.post("/listings/draft", data=form).json()
    assert ([a["model"] for a in draft["attempts"]], draft["status"], gemma.asked) == (["claude-haiku-5-5"], "ready", [])
    local = client.post("/listings/draft", data={**form, "mode": "local"}).json()
    assert [a["model"] for a in local["attempts"]] == ["gemma3:4b"] and len(haiku.asked) == 1


def test_the_apps_listing_writer_is_claude_haiku_unless_set_back_to_gemma(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "pretend-anthropic-key")
    monkeypatch.delenv("FLIP_LISTING_WRITER", raising=False)
    assert (api.listing_writer_name(), api.listing_writer().name) == ("claude-haiku-5-5", "claude-haiku-5-5")
    monkeypatch.setenv("FLIP_LISTING_WRITER", "gemma")
    assert (api.listing_writer_name(), api.listing_writer()) == ("gemma3:4b", None)
    monkeypatch.delenv("FLIP_LISTING_WRITER")
    monkeypatch.delenv("ANTHROPIC_API_KEY")  # no key: this device's model writes
    assert (api.listing_writer_name(), api.listing_writer()) == ("gemma3:4b", None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "pretend-anthropic-key")
    assert TestClient(api.app).get("/health").json()["listing_model"] == "claude-haiku-5-5"


# 14 Oct (the owner: "what if we make gemma 4b make the ebay description"): flip-reader-5 reads your notes and Claude
# Haiku 5.5 phrases what it found (blind-judged on 40 real iPhones: 95% postable as is, against 90% reading the notes)
FORM = {"title": "iPhone 13 128GB Midnight unlocked", "notes": "boxed, battery 87%, light scratch on the back"}
READ_NOTES = {"flaws": ["light scratch on the back"], "pickup": "", "no_offers": ""}
PHRASED = {"condition_note": "Light scratch on the back. Battery health is 87%.",
           "description": "Apple iPhone 13, 128GB, in Midnight. There is a light scratch on the back. Battery health is "
                          "87%. Unlocked. Comes with the box."}


def test_list_on_ebays_writer_phrases_the_facts_flip_reader_5_found(client):
    haiku = FakeModel("claude-haiku-5-5", PHRASED)
    client.use(local=FakeModel("gemma3:4b"), api_model=FakeModel("claude-sonnet-5-5", LISTED), listing=haiku,
               listing_facts=True, reader=FakeModel("flip-reader-5", READ_NOTES))
    draft = client.post("/listings/draft", data=FORM).json()
    assert ([a["model"] for a in draft["attempts"]], draft["status"]) == (["claude-haiku-5-5"], "ready")
    assert haiku.asked[0]["user"] == ("Phone: Apple iPhone 13, 128GB, Midnight\neBay condition: Used\nFlaws: light "
                                      "scratch on the back\nBattery: Battery health is 87%\nNetwork: Unlocked\n"
                                      "Comes with: box")
    assert draft["description"] == PHRASED["description"]


def test_a_draft_that_leaves_a_fact_out_goes_to_the_paid_backup(client):
    left_out = {**PHRASED, "description": PHRASED["description"].replace(" Comes with the box.", "")}
    client.use(local=FakeModel("gemma3:4b"), api_model=FakeModel("claude-sonnet-5-5", LISTED),
               listing=FakeModel("claude-haiku-5-5", left_out), listing_facts=True,
               reader=FakeModel("flip-reader-5", READ_NOTES))
    draft = client.post("/listings/draft", data=FORM).json()
    assert [(a["model"], a["problems"]) for a in draft["attempts"]] == [
        ("claude-haiku-5-5", ["it left out what your notes say: box"]), ("claude-sonnet-5-5", [])]


def test_the_phraser_picks_the_colour_from_the_photos_in_the_same_call(client):
    # the photos are for the colour only, and only when the title and notes don't name it: Haiku looks as it phrases,
    # never a second look by Claude Sonnet 5.5 (20 times the price)
    no_colour = {**PHRASED, "colour": "Blue", "colour_seen_on": "back",
                 "description": PHRASED["description"].replace(", in Midnight", "")}
    haiku = FakeModel("claude-haiku-5-5", no_colour)
    client.use(local=FakeModel("gemma3:4b"), api_model=FakeModel("claude-sonnet-5-5", {"colour": "Red"}),
               listing=haiku, listing_facts=True, reader=FakeModel("flip-reader-5", READ_NOTES))
    draft = client.post("/listings/draft", data={**FORM, "title": "iPhone 13 128GB unlocked"},
                        files=[("photos", ("back.jpg", JPEG, "image/jpeg"))]).json()
    assert (draft["colour"], draft["colour_from"], draft["colour_by"]) == ("Blue", "photos", "claude-haiku-5-5")
    assert [a["model"] for a in draft["attempts"]] == ["claude-haiku-5-5"] and len(haiku.asked[0]["photos"]) == 1
    # the model's own colours, each with how it looks on it, where to look, and where it saw it (14 Oct)
    assert "Colour: not known. Pick the phone's own colour from the photos, one of this model's colours (how each looks " \
           "on an iPhone 13): Midnight (near-black back with a dark blue tint); Starlight (warm off-white back with a " \
           "champagne tint); Blue (mid sky-blue back and frame)" in haiku.asked[0]["user"]
    assert "colour_seen_on" in haiku.asked[0]["schema"]["properties"]


def test_a_colour_not_seen_on_the_phones_back_or_frame_is_unsure(client):
    # only the screen, or the phone in a case: the colour Haiku names doesn't count, and Sonnet looks once
    in_a_case = {**PHRASED, "colour": "Pink", "colour_seen_on": "not shown",
                 "description": PHRASED["description"].replace(", in Midnight", "")}
    sonnet = FakeModel("claude-sonnet-5-5", {"colour": "unsure", "seen_on": "not shown"})
    client.use(local=FakeModel("gemma3:4b"), api_model=sonnet, listing=FakeModel("claude-haiku-5-5", in_a_case),
               listing_facts=True, reader=FakeModel("flip-reader-5", READ_NOTES))
    draft = client.post("/listings/draft", data={**FORM, "title": "iPhone 13 128GB unlocked"},
                        files=[("photos", ("back.jpg", JPEG, "image/jpeg"))]).json()
    assert (draft["colour"], draft["colour_from"]) == (None, None) and "colour" in " ".join(draft["reasons"])
    assert [(a["model"], a["colour_only"]) for a in draft["attempts"]] == [("claude-haiku-5-5", False),
                                                                          ("claude-sonnet-5-5", True)]


# 14 Oct (the owner): My style On or Off on the AI message tab
def test_my_style_off_writes_the_default_way_and_approving_then_teaches_it_nothing(client):
    hi_there = [{"id": f"m{n}", "listing_title": "PS5", "asking_price": "300", "marketplace": "facebook",
                 "my_message": f"Hi there, hope you're well! Would you consider £{250 + n}? Many thanks! 😊"} for n in range(4)]
    client.use(local=FakeModel("gemma3:4b", READ, READ), messages=hi_there)
    on = client.post("/messages/draft", json={"listing": LISTING, "writer": "template", "mention": False}).json()
    client.use(local=FakeModel("gemma3:4b", READ))
    off = client.post("/messages/draft", json={"listing": LISTING, "writer": "template", "mention": False,
                                               "style": False}).json()
    assert on["message"].startswith("Hi there, hope you're well!") and "Many thanks! 😊" in on["message"]
    assert not off["message"].startswith("Hi there") and "Many thanks" not in off["message"]
    before = len(client.book.messages())
    done = client.post(f"/drafts/{off['draft_id']}/approve", json={"sent": off["message"], "learn": False}).json()
    assert done["saved_to_style"] is False and len(client.book.messages()) == before


def test_the_app_phrases_the_facts_unless_set_back(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "pretend-anthropic-key")
    monkeypatch.delenv("FLIP_LISTING_WRITER", raising=False)
    assert api.listing_from_facts() is True
    monkeypatch.setenv("FLIP_LISTING_WRITER", "notes")  # Claude Haiku 5.5 reads your notes itself
    assert (api.listing_from_facts(), api.listing_writer_name()) == (False, "claude-haiku-5-5")
    monkeypatch.setenv("FLIP_LISTING_WRITER", "gemma")
    assert (api.listing_from_facts(), api.listing_writer_name()) == (False, "gemma3:4b")
    monkeypatch.delenv("FLIP_LISTING_WRITER")
    monkeypatch.setattr(api, "reader_name", lambda: "flip-reader-5")
    monkeypatch.setattr(api, "ollama_models", lambda url: {"flip-reader-5:latest", "gemma3:4b"})
    assert TestClient(api.app).get("/health").json()["listing_reader"] == "flip-reader-5"


@pytest.mark.parametrize("listed, reads", [({"flip-reader-5:latest", "gemma3:4b"}, "flip-reader-5"),
                                           ({"gemma3:4b"}, "gemma3:4b"), (set(), "code"), (None, "code")])
def test_health_names_who_really_reads_list_on_ebays_notes(monkeypatch, listed, reads):
    """15 Nov review: listing_reader named flip-reader-5 whether or not this device's Ollama had it. Without it
    Gemma 3 4B reads your notes (flip.reader.reader_for), and with no model to read them (no Ollama), code."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "pretend-anthropic-key")
    for setting in ("FLIP_LISTING_WRITER", "FLIP_READER_MODEL"):
        monkeypatch.delenv(setting, raising=False)
    monkeypatch.setattr(api, "ollama_models", lambda url: listed)
    assert TestClient(api.app).get("/health").json()["listing_reader"] == reads
    monkeypatch.setenv("FLIP_READER_MODEL", "")  # FlipAssist's reader turned off in .env: Gemma reads, if it can
    assert TestClient(api.app).get("/health").json()["listing_reader"] == ("code" if reads == "code" else "gemma3:4b")
    monkeypatch.setenv("FLIP_LISTING_WRITER", "notes")  # Claude Haiku 5.5 reads your notes itself: nobody else does
    assert TestClient(api.app).get("/health").json()["listing_reader"] == ""


def test_a_colour_gemma_couldnt_see_comes_from_haikus_look_and_says_so(client):
    unsure = {**LISTED, "colour": "unsure", "description": LISTED["description"].replace(" in Midnight", "")}
    client.use(local=FakeModel("gemma3:4b", unsure),
               api_model=FakeModel("claude-haiku-5-5", {"colour": "Blue", "seen_on": "back and frame"}))
    draft = client.post("/listings/draft", data={"title": "iPhone 13 128GB unlocked",
                                                 "notes": "boxed, battery 87%, light scratch on the back"},
                        files=[("photos", ("back.jpg", JPEG, "image/jpeg"))]).json()
    assert (draft["colour"], draft["colour_from"], draft["colour_by"]) == ("Blue", "photos", "claude-haiku-5-5")
    assert [(a["model"], a["colour_only"]) for a in draft["attempts"]] == \
        [("gemma3:4b", False), ("claude-haiku-5-5", True)]
    assert draft["cost_pence"] == round(sum(a["cost_pence"] for a in draft["attempts"]), 4) > 0


def test_a_listing_that_isnt_an_iphone_is_turned_away(client):
    # 14 Oct (the owner's call): List on eBay drafts iPhones only
    local = FakeModel("gemma3:4b", {**LISTED, "colour": "White"})
    client.use(local=local)
    draft = client.post("/listings/draft", data={"title": "PS5 Slim digital 1TB", "notes": "boxed"}).json()
    assert (draft["status"], draft["reasons"], draft["ebay_category"], draft["item_specifics"]) == \
        ("needs you", ["List on eBay is for iPhones only"], None, [])
    assert local.asked == []


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
    assert (draft["status"], draft["reasons"]) == \
        ("needs you", ["List on eBay is for iPhones only: say which iPhone it is in the title"])
    assert local.asked == []


# ── approving, and the cost meter ───────────────────────────────────────────

def test_approving_records_what_you_sent_and_whether_you_edited_it(client):
    client.use(local=FakeModel("gemma3:4b", READ), messages=PAST)
    draft = client.post("/messages/draft", json={"listing": LISTING, "mention": True}).json()
    url = f"/drafts/{draft['draft_id']}/approve"
    assert client.post(url, json={"sent": draft["message"]}).json()["edited"] is False
    assert client.post(url, json={"sent": draft["message"] + " Cheers"}).json()["edited"] is True
    assert client.post("/drafts/9999/approve", json={"sent": "hi"}).status_code == 404
    assert client.post(url, json={"sent": ""}).status_code == 422


def test_an_approved_message_joins_your_style_once(client):
    client.use(local=FakeModel("gemma3:4b", READ), messages=PAST)
    draft = client.post("/messages/draft", json={"listing": LISTING, "mention": True}).json()
    url = f"/drafts/{draft['draft_id']}/approve"
    assert client.post(url, json={"sent": draft["message"]}).json()["saved_to_style"] is True
    client.post(url, json={"sent": "Hi mate, would you take £185? Cheers"})  # approved again, edited
    newest = client.get("/style/messages").json()[0]
    assert (newest["id"], newest["title"], newest["price"], newest["source"]) == \
        (f"draft-{draft['draft_id']}", LISTING["title"], "220", "approved")
    assert newest["text"] == "Hi mate, would you take £185? Cheers"
    assert client.get("/style").json()["count"] == len(PAST) + 1


def test_an_approved_listing_isnt_a_message_to_learn_from(client):
    client.use(local=FakeModel("gemma3:4b", READ, LISTED))
    form = {"title": "iPhone 13 128GB Midnight unlocked", "notes": "light scratch on the back, battery 87%"}
    draft = client.post("/listings/draft", data=form, files=[("photos", ("a.jpg", JPEG, "image/jpeg"))]).json()
    assert client.post(f"/drafts/{draft['draft_id']}/approve", json={"sent": "described"}).json()["saved_to_style"] \
        is False
    assert client.get("/style/messages").json() == []


def test_the_cost_meter_adds_it_all_up(client):
    client.use(local=FakeModel("gemma3:4b", READ, READ), api_model=FakeModel("claude-haiku-5-5"), messages=PAST)
    first = client.post("/messages/draft", json={"listing": LISTING, "mention": True}).json()
    client.post("/messages/draft", json={"listing": LISTING, "kind": "asking", "mention": True})
    client.post(f"/drafts/{first['draft_id']}/approve", json={"sent": first["message"]})
    stats = client.get("/stats").json()
    assert (stats["drafts"], stats["ready"], stats["needs_you"]) == (2, 2, 0)
    assert (stats["outputs_here"], stats["outputs"], stats["cost_pence"]) == (4, 4, 0)  # 2 readings, 2 messages
    assert {m["model"] for m in stats["models"]} == {"gemma3:4b", "template"}
    assert (stats["approved"], stats["edited_before_sending"]) == (1, 0)


def test_done_on_this_device_counts_the_successful_outputs_made_here(client):
    """14 Oct: Home's blue card counts the outputs that passed their checks made on this device (free), against all
    of them: the paid check runs on purpose, so it's counted as the paid model's output, not against a draft."""
    client.use(local=FakeModel("gemma3:4b", READ, READ, READ), messages=PAST)
    drafts = [client.post("/messages/draft", json={"listing": LISTING, "mention": True}).json() for _ in range(3)]
    log = api.app.dependency_overrides[api.audit]()
    stats = client.get("/stats").json()
    assert (stats["outputs_here"], stats["outputs"]) == (6, 6)  # 3 readings and 3 messages, all here
    log.attempt(log.item_of(drafts[0]["draft_id"]), Reply("claude-haiku-5-5", answer={"verdict": "ok"}), [], "0.01",
                job="reason")
    log.attempt(None, Reply("claude-sonnet-5-5", answer={}), ["no clause"], "0.1", job="reason")  # failed: not counted
    stats = client.get("/stats").json()
    assert (stats["outputs_here"], stats["outputs"]) == (6, 7)
    assert log.item_of(drafts[0]["draft_id"]).startswith("api-") and log.item_of(10**6) is None


def test_the_reasons_check_counts_for_its_draft(client, monkeypatch):
    client.use(local=FakeModel("gemma3:4b", READ), messages=PAST)
    draft = client.post("/messages/draft", json={"listing": LISTING, "mention": True}).json()
    log = api.app.dependency_overrides[api.audit]()
    setup = api.app.dependency_overrides[api.setup]()
    setup.wording = {"check": FakeModel("claude-haiku-5-5", {"verdict": "ok"})}
    api.app.dependency_overrides[api.setup] = lambda: setup
    checked = client.post("/messages/check-reason", json={
        "draft_id": draft["draft_id"], "listing": LISTING, "flaws": draft["reading"]["flaws"],
        "quotes": draft["reason_from"], "clause": "there's a black dot on the screen", "message": draft["message"],
        "offer_pence": draft["offer_pence"]})
    assert checked.status_code == 200 and checked.json()["reason"]["checked"] == "ok"
    items = [row[0] for row in log.db.execute("select item_id from attempts where model = 'claude-haiku-5-5'")]
    assert items == [log.item_of(draft["draft_id"])]


THREE = ["Back glass cracked in the top right corner.", "Face ID not working.", "Battery 79%."]
LISTING3 = {**LISTING, "description": " ".join(THREE) + " Collection only from Leeds LS6."}
READ3 = {"flaws": THREE, "pickup": "Collection only from Leeds LS6", "no_offers": ""}


@pytest.mark.parametrize("said, given, left", [
    (1, ["Face ID not working"], ["glass", "battery"]),
    (2, ["Back glass cracked in the top right corner", "Face ID not working"], ["battery"]),
    ("all", ["Back glass cracked in the top right corner", "Face ID not working", "Battery 79%"], []),
])
def test_you_pick_how_many_flaws_a_lower_offer_gives_the_worst_first(client, said, given, left):
    client.use(local=FakeModel("gemma3:4b", READ3), messages=PAST)
    draft = client.post("/messages/draft", json={"listing": LISTING3, "mention": True, "writer": "template",
                                                 "flaws_said": said}).json()
    assert draft["status"] == "ready" and draft["point"] == given
    assert draft["reason_from"] == (given if said != "all" else [t.rstrip(".") for t in THREE])
    assert "Face ID" in draft["message"] and not [w for w in left if w in draft["message"].lower()]


def test_a_flaw_count_that_isnt_one_is_refused(client):
    for wrong in (0, 4, "two"):
        assert client.post("/messages/draft", json={"listing": LISTING, "flaws_said": wrong}).status_code == 422


def test_the_price_you_picked_is_drafted_and_one_that_doesnt_fit_is_refused(client):
    client.use(local=FakeModel("gemma3:4b", READ, READ), messages=PAST)
    draft = client.post("/messages/draft", json={"listing": LISTING, "offer": "150", "mention": True}).json()
    assert (draft["offer"], draft["offer_pence"]) == ("£150", 15000) and "£150" in draft["message"]
    refused = client.post("/messages/draft", json={"listing": LISTING, "offer": "230"})
    assert refused.status_code == 422 and "isn't a lower offer" in refused.json()["detail"]
    assert client.post("/messages/draft", json={"listing": LISTING, "offer": "cheap"}).status_code == 422


# ── your style ──────────────────────────────────────────────────────────────

def test_your_style_learns_from_the_messages_you_add(client):
    assert client.get("/style").json() == {"count": 0, "traits": [], "phrases": [], "learned": []}
    sent = [{"title": "iPhone 12 64GB", "price": "£150", "text": "Hi mate, would you take £125 cash? Cheers"},
            {"title": "PS5 Slim", "price": "£1,200", "text": "Hi mate, would you take £270 cash? Cheers"},
            {"title": "", "price": "", "text": "Hi mate, would you take £90 cash? Cheers"}]
    added = client.post("/style/messages", json=sent)
    assert added.status_code == 201 and [m["price"] for m in added.json()] == ["150", "1200", ""]
    style = client.get("/style").json()
    assert style["count"] == 3
    assert {"k": "Opens with", "v": "'Hi mate'"} in style["traits"] and {"k": "Mentions", "v": "cash"} in style["traits"]
    assert {"k": "Offer sentence", "v": "Hi mate, would you take £… cash?"} in style["phrases"]
    assert {"k": "Closing", "v": "Cheers"} in style["phrases"]
    assert [m["text"] for m in client.get("/style/messages").json()][0] == sent[-1]["text"]  # newest first


def test_what_your_style_learned_is_yours_to_remove(client):
    local = FakeModel("gemma3:4b", READ, {"message": "Hi mate, is this still available? Would you take £185? Can "
                                                     "collect from Leeds LS6 today."})
    client.use(local=local, messages=PAST)
    cash = next(r for r in client.get("/style").json()["learned"] if r["value"] == "paying cash")
    assert cash == {"key": "mention:cash", "what": "Mentions", "value": "paying cash", "used": True}
    style = client.post("/style/learned", json={"key": "mention:cash", "used": False})
    assert style.status_code == 200
    assert next(r for r in style.json()["learned"] if r["key"] == "mention:cash")["used"] is False
    assert {"k": "Mentions", "v": "collecting and today"} in style.json()["traits"]
    # your own offer sentence says cash, so it's refused, and the AI is told never to say it
    draft = client.post("/messages/draft", json={"listing": LISTING, "mention": False}).json()  # Say the flaw: No
    assert (draft["status"], draft["written_by"]) == ("ready", "gemma3:4b") and "cash" not in draft["message"]
    assert "the message mentions paying cash, which you removed from your style" in draft["attempts"][0]["problems"]
    assert "Never mentions paying cash" in local.asked[-1]["user"]
    # put back, it's used again; putting back what isn't removed, or removing what it never learned, is a 404
    assert client.post("/style/learned", json={"key": "mention:cash", "used": True}).status_code == 200
    assert client.post("/style/learned", json={"key": "mention:cash", "used": True}).status_code == 404
    assert client.post("/style/learned", json={"key": "greeting:yo", "used": False}).status_code == 404


def test_doing_the_setup_again_takes_the_place_of_your_last_setup(client):
    """14 Oct: Redo setup starts your style afresh from your new answers; the drafts you approved and a CSV stay."""
    client.use(messages=PAST[:2])  # learned from a CSV
    first = client.put("/style/setup", json=[{"title": "PS5", "price": "300", "text": "Hi mate, would you take £255? Cheers"}])
    assert first.status_code == 200 and len(first.json()) == 1
    client.book.add([{"id": "draft-1", "listing_title": "iPhone", "asking_price": "200", "marketplace": "facebook",
                      "my_message": "Hi, £170?"}], "approved")
    removable = next(r["key"] for r in client.get("/style").json()["learned"])
    assert client.post("/style/learned", json={"key": removable, "used": False}).status_code == 200
    again = client.put("/style/setup", json=[{"title": "Dyson V11", "price": "£180", "text": "Hiya, I'll pay £190 if "
                                              "you hold it", "marketplace": "facebook"},
                                             {"title": "", "price": "", "text": "Hiya, would you do £100?"}])
    assert again.status_code == 200 and [m["price"] for m in again.json()] == ["180", ""]
    kept = {m["source"]: m["text"] for m in client.get("/style/messages").json()}
    texts = [m["text"] for m in client.get("/style/messages").json()]
    assert "Hi mate, would you take £255? Cheers" not in texts and "Hiya, would you do £100?" in texts
    assert kept["approved"] == "Hi, £170?" and "csv" in kept
    assert client.get("/style").json()["count"] == len(PAST[:2]) + 1 + 2
    assert client.book.removed() == set()  # what you removed is cleared: learned afresh
    for refused in ([], [{"text": "   "}], [{"text": "£90?", "price": "cheap"}]):
        assert client.put("/style/setup", json=refused).status_code == 422
    assert TestClient(api.app).put("/style/setup", json=[{"text": "hi"}]).status_code == 401


def test_a_message_you_add_needs_words_and_a_price_that_is_one(client):
    for refused in ([], [{"text": "   "}], [{"text": "Hi, £90?", "price": "cheap"}], [{"price": "£90"}]):
        assert client.post("/style/messages", json=refused).status_code == 422
    assert client.get("/style/messages").json() == []


def test_a_message_you_delete_is_no_longer_learned_from(client):
    added = client.post("/style/messages", json=[{"text": "Hi mate, would you take £90? Cheers"}]).json()
    assert client.delete(f"/style/messages/{added[0]['id']}").status_code == 204
    assert client.get("/style").json()["count"] == 0
    assert client.delete(f"/style/messages/{added[0]['id']}").status_code == 404


def test_your_style_needs_the_key(client):
    assert TestClient(api.app).get("/style").status_code == 401
    assert TestClient(api.app).post("/style/messages", json=[{"text": "hi"}]).status_code == 401


# ── what the review of the API found ────────────────────────────────────────

def served(path, headers, chunks):
    """Call the app as a server would, with the body in chunks: its answer's
    status, and the chunks it read."""
    import asyncio
    read, sent, chunks = [], [], list(chunks)

    async def receive():
        if not chunks:
            return {"type": "http.disconnect"}
        read.append(chunks.pop(0))
        return {"type": "http.request", "body": read[-1], "more_body": bool(chunks)}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": path, "raw_path": path.encode(), "query_string": b"",
             "root_path": "", "scheme": "http", "http_version": "1.1", "server": ("127.0.0.1", 8000),
             "client": ("127.0.0.1", 5000), "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]}
    asyncio.run(api.app(scope, receive, send))
    return next(m["status"] for m in sent if m["type"] == "http.response.start"), read


def test_a_caller_without_the_key_is_turned_away_before_a_byte_is_read(client):
    for path in ("/messages/draft", "/listings/draft", "/style/messages", "/drafts/1/approve", "/nowhere"):
        assert served(path, {"content-type": "application/json"}, [b"x" * 65536] * 80) == (401, [])


def test_a_body_bigger_than_the_endpoint_takes_is_turned_away(client):
    with_key = {"x-api-key": KEY, "content-type": "application/json"}
    assert served("/messages/draft", {**with_key, "content-length": str(api.MAX_JSON + 1)}, [b"{}"]) == (413, [])
    assert served("/messages/draft", {**with_key, "content-length": "lots"}, [b"{}"])[0] == 413
    status, read = served("/style/messages", with_key, [b" " * 65536] * 40)  # 2.5 MB in chunks, no length given
    assert status == 413 and sum(map(len, read)) <= api.MAX_JSON + 65536
    assert TestClient(api.app).get("/health").status_code == 200  # still open, as are the docs
    assert TestClient(api.app).get("/openapi.json").status_code == 200


@pytest.mark.parametrize("weak", ["your-key-here", "short", "x" * (api.MIN_KEY - 1)])
def test_the_placeholder_or_a_short_key_is_no_key(client, monkeypatch, weak):
    monkeypatch.setenv("FLIP_API_KEY", weak)
    refused = TestClient(api.app, headers={"X-API-Key": weak}).get("/stats")
    assert refused.status_code == 503 and "32 characters or more" in refused.json()["detail"]
    assert TestClient(api.app).get("/health").json()["flip_api_key_set"] is False


def test_a_photo_is_known_by_its_bytes_not_its_name(client):
    client.use(local=FakeModel("gemma3:4b", LISTED))
    form = {"title": "iPhone 13 128GB unlocked", "notes": "boxed, battery 87%, light scratch on the back"}
    from_a_blob = client.post("/listings/draft", data=form, files=[("photos", ("blob", JPEG, "image/jpeg"))])
    assert from_a_blob.status_code == 200 and from_a_blob.json()["photo_count"] == 1
    pdf = client.post("/listings/draft", data=form, files=[("photos", ("invoice.jpg", b"%PDF-1.4\n%x", "image/jpeg"))])
    assert pdf.status_code == 422 and pdf.json()["detail"] == "invoice.jpg: send photos as JPEG, PNG, HEIC or WebP"


def test_the_colour_is_the_checked_one_and_says_where_it_came_from(client):
    unsure = {**LISTED, "colour": "UNSURE"}
    client.use(local=FakeModel("gemma3:4b", unsure, LISTED, {k: v for k, v in LISTED.items() if k != "colour"}))
    form = {"notes": "boxed, battery 87%, light scratch on the back"}
    photo = [("photos", ("back.jpg", JPEG, "image/jpeg"))]
    guessed = client.post("/listings/draft", data={**form, "title": "iPhone 13 128GB unlocked"}, files=photo).json()
    assert (guessed["colour"], guessed["colour_from"], guessed["status"]) == (None, None, "needs you")
    seen = client.post("/listings/draft", data={**form, "title": "iPhone 13 128GB unlocked"}, files=photo).json()
    assert (seen["colour"], seen["colour_from"]) == ("Midnight", "photos")
    assert "colour" not in seen["filled_by_code"]  # the AI's, not code's
    read = client.post("/listings/draft", data={**form, "title": "iPhone 13 128GB Midnight unlocked"}, files=photo).json()
    assert (read["colour"], read["colour_from"], read["filled_by_code"]["colour"]) == ("Midnight", "listing", "Midnight")


def test_approving_a_draft_again_counts_it_once_as_last_approved(client):
    client.use(local=FakeModel("gemma3:4b", READ), messages=PAST)
    draft = client.post("/messages/draft", json={"listing": LISTING, "mention": True}).json()
    url = f"/drafts/{draft['draft_id']}/approve"
    for sent in (draft["message"], draft["message"] + " Thanks", draft["message"] + " Thanks"):
        client.post(url, json={"sent": sent})
    stats = client.get("/stats").json()
    assert (stats["drafts"], stats["approved"], stats["edited_before_sending"]) == (1, 1, 1)
    client.post(url, json={"sent": draft["message"]})
    assert client.get("/stats").json()["edited_before_sending"] == 0


@pytest.mark.parametrize("draft_id", ["0", "-1", str(2**63), "9" * 40])
def test_a_draft_id_out_of_range_is_refused_not_a_crash(client, draft_id):
    assert client.post(f"/drafts/{draft_id}/approve", json={"sent": "hi"}).status_code == 422


@pytest.mark.parametrize("change, words", [
    ({"listing": {**LISTING, "asking_price": "0"}}, "under £1"),
    ({"listing": {**LISTING, "asking_price": "0.50"}}, "under £1"),
    ({"offer": "230"}, "isn't a lower offer"),
    ({"previous": "Hi, would you take £185?"}, 'with "length": "longer"'),
    # 9 Nov: only iPhone, Samsung phone and MacBook listings
    ({"listing": {**LISTING, "title": "PS5 Disc edition"}}, "iPhone, Samsung phone and MacBook listings only"),
    ({"listing": {**LISTING, "title": "Mountain bike 26 inch"}}, "iPhone, Samsung phone and MacBook listings only"),
    ({"listing": {**LISTING, "title": "Google Pixel 8 Pro"}}, "iPhone, Samsung phone and MacBook listings only"),
    ({"listing": {**LISTING, "title": "iPad Air 5"}}, "iPhone, Samsung phone and MacBook listings only"),
    ({"listing": {**LISTING, "title": "iPhone 13 case"}}, "iPhone, Samsung phone and MacBook listings only"),
    ({"listing": {**LISTING, "title": "Samsung TV 55 inch"}}, "iPhone, Samsung phone and MacBook listings only"),
])
def test_what_cant_be_drafted_is_refused_before_anything_runs(client, change, words):
    local = FakeModel("gemma3:4b")
    client.use(local=local, messages=PAST)
    refused = client.post("/messages/draft", json={"listing": LISTING, **change})
    assert refused.status_code == 422 and words in refused.json()["detail"]
    assert local.asked == []  # not even the reading ran


def test_the_same_listing_again_isnt_read_again(client):
    """9 Nov, the owner: "get the flaws that the reader found straight from the previous request do not read it
    again": a draft sent with its listing's earlier reading uses it as it is."""
    local = FakeModel("gemma3:4b")
    client.use(local=local, messages=PAST)
    earlier = {"flaws": ["Black dot on the screen"], "quotes": ["Black dot on the screen."], "pickup": "Leeds LS6",
               "no_offers": "", "read_by": "flip-reader-5"}
    found = client.post("/messages/draft", json={"listing": LISTING, "kind": "asking", "mention": False,
                                                 "writer": "template", "reading": earlier})
    assert found.status_code == 200, found.text
    assert local.asked == []  # nothing read again
    read = found.json()["reading"]
    assert (read["flaws"], read["read_by"], read["attempts"]) == (earlier["flaws"], "flip-reader-5", [])


@pytest.mark.parametrize("sent", [{"flaws": ["Screen is smashed"]},
                                  {"flaws": ["Black dot on the screen"], "quotes": ["Face ID doesn't work."]},
                                  {"flaws": ["Black dot on the screen"], "pickup": "Manchester M1"},
                                  {"flaws": ["No scratches"]}])
def test_a_reading_that_isnt_this_listings_is_read_again(client, sent):
    """15 Nov review: a reading sent back was used as it was, never held to the listing, so a flaw the listing doesn't
    have went into a ready message ("...because the screen is smashed..."). One whose words aren't the listing's, or
    that gives as a flaw what the seller denies, is read again."""
    local = FakeModel("gemma3:4b", READ)
    client.use(local=local, messages=PAST)
    reading = {"quotes": [], "pickup": "", "no_offers": "", "read_by": "flip-reader-5", **sent}
    found = client.post("/messages/draft", json={"listing": {**LISTING, "description": f"{LISTING['description']} "
                                                             "No scratches."},
                                                 "mention": True, "writer": "template", "reading": reading})
    assert found.status_code == 200, found.text
    assert len(local.asked) == 1  # read again
    assert found.json()["reading"]["read_by"] == "gemma3:4b" and "black dot" in found.json()["message"].lower()
    assert not {"smashed", "face id", "manchester", "scratch"} & set(found.json()["message"].lower().split())


def test_a_local_model_that_hangs_up_falls_back_to_code(client, monkeypatch):
    import http.client
    import io
    from flip import ai

    def hangs_up(request, timeout):
        raise http.client.RemoteDisconnected("Remote end closed connection without response")
    monkeypatch.setattr(ai.urllib.request, "urlopen", hangs_up)
    client.use(local=ai.LocalModel(), messages=PAST)
    draft = client.post("/messages/draft", json={"listing": LISTING, "mention": True})
    assert draft.status_code == 200 and draft.json()["reading"]["read_by"] == "code"
    assert draft.json()["status"] == "ready"  # your own sentences, no AI needed
    monkeypatch.setattr(ai.urllib.request, "urlopen", lambda request, timeout: io.BytesIO(b"<html>Bad gateway</html>"))
    assert client.post("/messages/draft", json={"listing": LISTING, "mention": True}).status_code == 200


def test_a_fault_inside_is_a_500_not_the_callers_mistake(client, monkeypatch):
    client.use(local=FakeModel("gemma3:4b", READ), messages=PAST)

    def broken(*args, **kwargs):
        raise ValueError("a bug, not bad input")
    monkeypatch.setattr(api, "draft_message", broken)
    assert TestClient(api.app, headers={"X-API-Key": KEY}, raise_server_exceptions=False).post(
        "/messages/draft", json={"listing": LISTING}).status_code == 500


def test_half_a_character_from_a_caller_is_made_whole_not_a_crash(client):
    client.use(local=FakeModel("gemma3:4b", READ), messages=PAST)
    body = json.dumps({"listing": {**LISTING, "title": "iPhone 13 128GB Blue"}}).replace("Blue", "Blue \\ud800")
    draft = client.post("/messages/draft", content=body, headers={"Content-Type": "application/json"})
    assert draft.status_code == 200, draft.text
    added = client.post("/style/messages", content='[{"title": "Pixel \\udfff", "text": "Hi, would you take \\u00a3220?"}]',
                        headers={"Content-Type": "application/json"})
    assert added.status_code == 201 and added.json()[0]["title"] == "Pixel �"


def test_the_listing_is_read_by_the_reader_when_one_is_set():
    local, other = FakeModel("gemma3:4b"), FakeModel("flip-reader-5")
    assert api.Setup(local, None, None).reading_model() is local
    assert api.Setup(local, None, None, reader=lambda: other).reading_model() is other
    assert api.Setup(local, None, None, reader=lambda: None).reading_model() is local
    assert api.Setup(local, None, None, reader=other).reading_model() is other


# ── the AI UK price estimate tab (4 Oct) ───────────────────────────────────────

@pytest.fixture
def prices_api(monkeypatch):
    """A prices API set in .env (nothing is sent to it: estimate is pretend in these tests)."""
    monkeypatch.setenv("PRICES_URL", "https://example.test/functions/v1/prices")
    monkeypatch.setenv("PRICES_KEY", "k" * 64)


def test_the_price_tab_reads_the_flaws_then_cuts_the_price_for_them(client, monkeypatch, prices_api):
    asked = []

    def priced(title, flaws=(), description=None, **_):
        asked.append((title, list(flaws), description))
        return {"price": 170, "middle": 210, "currency": "GBP", "sales": 38, "kinds": ["fault"], "cuts": ["fault"],
                "rough": False, "exact": True}

    monkeypatch.setattr(api, "estimate", priced)
    client.use(local=FakeModel("gemma3:4b", READ))
    found = client.post("/prices/estimate", json={"title": LISTING["title"], "description": LISTING["description"]})
    dot = "Black dot on the screen"  # the reading, as a draft gets it
    assert asked == [("iPhone 13 128GB Blue", [dot], LISTING["description"])]
    assert (found.json()["price"], found.json()["flaws"], found.json()["read_by"]) == (170, [dot], "gemma3:4b")
    stats = client.get("/stats").json()
    assert stats["drafts"] == 0  # a price check is a reading, not a draft...
    assert [(m["model"], m["job"]) for m in stats["models"]] == [("gemma3:4b", "price")]  # ...kept as its own job


def test_a_price_checks_reading_isnt_counted_in_the_cost_per_draft(client, monkeypatch, prices_api):
    monkeypatch.setattr(api, "estimate", lambda title, flaws=(), **_: {"price": 150, "cuts": []})
    client.use(local=FakeModel("gemma3:4b", READ, READ), api_model=FakeModel("claude-haiku-5-5"), messages=PAST)
    client.post("/messages/draft", json={"listing": LISTING, "mention": True})
    before = client.get("/stats").json()["cost_per_100_drafts_pence"]
    log = api.app.dependency_overrides[api.audit]()
    log.attempt("price-1", Reply("claude-haiku-5-5", answer={}), [], "0.05", job="price")  # a paid price reading
    log.attempt(None, Reply("claude-sonnet-5-5", answer={"severity": "minor"}), [], "0.2", job="severity")  # its judge
    after = client.get("/stats").json()
    assert after["cost_per_100_drafts_pence"] == before and after["cost_pence"] >= 0.25


def test_flaws_already_read_are_used_as_they_are(client, monkeypatch, prices_api):
    monkeypatch.setattr(api, "estimate", lambda title, flaws=(), **_: {"price": 150, "cuts": list(flaws)})
    local = FakeModel("gemma3:4b", READ)
    client.use(local=local)
    found = client.post("/prices/estimate", json={"title": "iPhone 13", "description": "x", "flaws": ["battery 71%"]})
    assert (found.json()["cuts"], found.json()["read_by"], local.asked) == (["battery 71%"], None, [])
    # 9 Nov: flaws sent from AI message's Check the UK price come with who read them, shown as it is, nothing read again
    found = client.post("/prices/estimate", json={"title": "iPhone 13", "description": "x", "flaws": ["battery 71%"],
                                                  "read_by": "flip-reader-5"})
    assert (found.json()["cuts"], found.json()["read_by"], local.asked) == (["battery 71%"], "flip-reader-5", [])
    assert client.post("/prices/estimate", json={"title": "iPhone 13", "flaws": [], "read_by": "<script>"}).status_code == 422


def test_the_price_tab_sorts_the_flaws_with_flip_kinds_when_ollama_has_it(client, monkeypatch, prices_api):
    given = []

    def priced(title, flaws=(), description=None, sorter=None, **_):
        given.append(sorter)
        return {"price": 150, "cuts": ["fault"], "kinds": ["fault"], "sorted_by": sorter.name if sorter else "code"}

    class Sorter:
        name = "flip-kinds-1"

    monkeypatch.setattr(api, "estimate", priced)
    client.use(local=FakeModel("gemma3:4b", READ), kinds=lambda: Sorter())
    found = client.post("/prices/estimate", json={"title": LISTING["title"], "description": LISTING["description"]})
    assert isinstance(given[0], Sorter) and found.json()["sorted_by"] == "flip-kinds-1"
    client.use(local=FakeModel("gemma3:4b", READ), kinds=lambda: None)  # not in Ollama: code sorts
    found = client.post("/prices/estimate", json={"title": LISTING["title"], "description": LISTING["description"]})
    assert given[1] is None and found.json()["sorted_by"] == "code"


def test_no_flaws_means_flip_kinds_isnt_looked_for(client, monkeypatch, prices_api):
    looked = []
    monkeypatch.setattr(api, "estimate", lambda title, flaws=(), sorter=None, **_: {"price": 150, "cuts": []})
    client.use(local=FakeModel("gemma3:4b", READ), kinds=lambda: looked.append(1))
    client.post("/prices/estimate", json={"title": "iPhone 13", "description": "x", "flaws": []})
    assert looked == []


def test_the_app_looks_for_flip_kinds_in_the_ollama_that_reads(monkeypatch, tmp_path):
    seen = []
    log = AuditLog(tmp_path / "audit.sqlite3")  # never the real log
    monkeypatch.setattr(api, "kinds_sorter", lambda url, log=None: seen.append((url, log)) or "sorter")
    monkeypatch.setattr(api, "audit", lambda: log)
    api.setup.cache_clear()
    try:
        # its answers are kept in the audit log, so Home counts them (15 Nov review)
        assert api.setup().flaw_sorter() == "sorter" and seen == [("http://127.0.0.1:11434", log)]
    finally:
        api.setup.cache_clear()


def test_the_apps_style_reader_keeps_its_readings_in_the_audit_log(monkeypatch, tmp_path):
    """15 Nov review: flip-style-1b's readings went into no audit log, so Home's "who did the work" left it out."""
    made = {}
    log = AuditLog(tmp_path / "audit.sqlite3")  # never the real log, nor your real style
    monkeypatch.setattr(api, "StyleBook", lambda **settings: made.update(settings) or "book")
    monkeypatch.setattr(api, "MessageIndex", lambda: "index")
    monkeypatch.setattr(api, "audit", lambda: log)
    monkeypatch.delenv("FLIP_STYLE_AI", raising=False)
    api.style.cache_clear()
    try:
        assert api.style() == "book" and made.get("log") is log and made["ai"].name == "flip-style-1b"
    finally:
        api.style.cache_clear()


def test_the_price_tab_reads_nothing_but_iphones_samsungs_and_macbooks(client, prices_api):
    local = FakeModel("gemma3:4b", READ)
    client.use(local=local)
    for title in ("PS5 Slim 1TB", "iPhone 13 case", "MacBook Pro charger"):
        found = client.post("/prices/estimate", json={"title": title, "description": "Cracked case"}).json()
        assert found["skipped"] == "Estimates are for iPhones, Samsung phones and MacBooks only"
        assert found["flaws"] == []
    assert local.asked == []


def test_with_no_prices_to_ask_the_listing_isnt_read(client, monkeypatch):
    """No key and the free prices off, or a key with no address: nothing to price it with, so it isn't read."""
    monkeypatch.setenv("PRICES_URL", "")
    monkeypatch.setenv("PRICES_KEY", "")
    monkeypatch.setenv("FLIP_PUBLIC_PRICES", "off")
    local = FakeModel("gemma3:4b", READ)
    client.use(local=local)
    found = client.post("/prices/estimate", json={"title": "iPhone 13 128GB", "description": "Cracked back"}).json()
    assert found["skipped"].startswith("The free UK prices are off") and local.asked == []
    monkeypatch.setenv("PRICES_KEY", "k" * 64)
    found = client.post("/prices/estimate", json={"title": "iPhone 13 128GB", "description": "Cracked back"}).json()
    assert found["skipped"].startswith("The AlertFlip API isn't set") and local.asked == []


def test_with_no_key_the_price_tab_reads_the_listing_and_asks_the_free_prices(client, monkeypatch):
    """No PRICES_KEY: the listing is read as before and priced by the free public UK prices, asked with no key at the
    prices API's own address; the screen gets how fresh its sales are."""
    import io
    import urllib.error

    from flip import prices
    for name in ("PRICES_URL", "PRICES_KEY", "FLIP_PUBLIC_PRICES"):
        monkeypatch.delenv(name, raising=False)
    asked = []

    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(request, timeout):
        asked.append((request.full_url, dict(request.header_items()), json.loads(request.data)))
        if json.loads(request.data)["title"].startswith("iPhone 12"):
            raise urllib.error.HTTPError(request.full_url, 429, "x", {}, io.BytesIO(json.dumps(
                {"error": {"code": "PUBLIC_BUSY", "message": "Too many", "retry_after_s": 900}}).encode()))
        return Answer(json.dumps({"price": 170, "middle": 210, "low": 190, "high": 230, "sales": 40, "used": [],
                                  "model": "iphone 13", "storage_gb": 128, "mode": "catalogue", "public": True,
                                  "checked_at": "2026-10-20T07:00:00Z", "stale": True}).encode())
    monkeypatch.setattr(prices.urllib.request, "urlopen", urlopen)
    prices._seen.clear()
    local = FakeModel("gemma3:4b", READ)
    client.use(local=local)
    found = client.post("/prices/estimate", json={"title": LISTING["title"], "description": LISTING["description"]})
    url, headers, body = asked[-1]
    assert url == prices.PUBLIC_PRICES_URL and headers == {"Content-type": "application/json"}
    assert (body["action"], body["country"], body["title"]) == ("price", "uk", LISTING["title"])
    assert len(local.asked) == 1 and found.json()["flaws"] == ["Black dot on the screen"]  # read as before
    assert {k: found.json()[k] for k in ("public", "checked_at", "stale")} == \
        {"public": True, "checked_at": "2026-10-20T07:00:00Z", "stale": True}
    busy = client.post("/prices/estimate", json={"title": "iPhone 12 64GB", "flaws": []}).json()
    assert busy["error"] == "The free UK prices are busy: try again in about 15 minutes" and busy["public"] is False


def test_the_damage_judge_needs_your_claude_key_on_the_free_prices_too(client, monkeypatch):
    for name in ("PRICES_URL", "PRICES_KEY", "FLIP_PUBLIC_PRICES"):
        monkeypatch.delenv(name, raising=False)
    judges = []
    monkeypatch.setattr(api, "estimate", lambda title, flaws=(), judge=None, **_: judges.append(judge) or
                        {"price": 150, "cuts": [], "public": True})
    log = api.app.dependency_overrides[api.audit]()
    api.app.dependency_overrides[api.setup] = lambda: api.Setup(FakeModel("gemma3:4b"), None, log, judge="settings")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client.post("/prices/estimate", json={"title": "iPhone 13 128GB", "flaws": ["Cracked back"]})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    client.post("/prices/estimate", json={"title": "iPhone 13 128GB", "flaws": ["Cracked back"]})
    assert judges[0] is None and callable(judges[1])  # no Claude key: code judges alone, as with your own prices


def test_the_price_tab_asks_for_the_kinds_and_the_size_the_listing_gives(client, monkeypatch, prices_api):
    """The tab end to end with the real flip.prices (6 Oct recheck), against a pretend prices API: a fault said as the
    one thing not working, a title selling it for repairs, a size written "128 gig"."""
    from flip import prices
    asked = []

    class Answer:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"price": 150, "middle": 170, "used": []}).encode()

    def urlopen(request, timeout):
        asked.append(json.loads(request.data))
        return Answer()
    monkeypatch.setattr(prices.urllib.request, "urlopen", urlopen)
    prices._seen.clear()
    found = client.post("/prices/estimate", json={"title": "iPhone 13 128GB", "flaws": ["Everything works except face id"],
                                                  "description": "Everything works except face id. Collection Leeds."})
    # 4 Nov: an iPhone's fault is FlipAssist's own measured cut, so the API is asked for the clean price
    assert (asked[-1]["kinds"], found.json()["kinds"]) == ([], ["fault"])
    assert found.json()["own_cuts"]["fault"]["n"] == 204
    client.post("/prices/estimate", json={"title": "iPhone 12 Pro repairs", "description": "Collection only.", "flaws": []})
    assert (asked[-1]["kinds"], asked[-1]["bucket"]) == (["parts"], "good")
    found = client.post("/prices/estimate", json={"title": "iPhone 13 Blue", "description": "128 gig, battery 90%",
                                                  "flaws": []})
    assert (asked[-1]["storage_gb"], found.json()["asked_storage_gb"]) == (128, 128)


def test_the_price_tab_says_the_monthly_cap_and_skips_a_charger(client, monkeypatch, prices_api):
    """The tab with the real flip.prices (6 Oct second check), against a pretend prices API: its monthly cap, an
    UNAVAILABLE whose message says "next month", is said as that, not as a moment's wait; a charger with its own cable
    is never read or asked about."""
    import io
    import urllib.error

    from flip import prices
    asked = []

    def urlopen(request, timeout):
        asked.append(json.loads(request.data))
        raise urllib.error.HTTPError(request.full_url, 503, "x", {}, io.BytesIO(json.dumps(
            {"error": {"code": "UNAVAILABLE", "message": "New price checks are paused until next month."}}).encode()))
    monkeypatch.setattr(prices.urllib.request, "urlopen", urlopen)
    prices._seen.clear()
    found = client.post("/prices/estimate", json={"title": "iPhone 13 mini 512GB", "flaws": [],
                                                  "description": "Works perfectly."}).json()
    assert found["error"] == "New price checks are paused until next month: models checked before can still be priced"
    local = FakeModel("gemma3:4b", READ)
    client.use(local=local)
    found = client.post("/prices/estimate", json={"title": "MacBook Pro charger and cable included",
                                                  "description": "Genuine Apple 61W, works."}).json()
    assert found["skipped"] == "Estimates are for iPhones, Samsung phones and MacBooks only"
    assert (len(asked), local.asked) == (1, [])


@pytest.mark.parametrize("kind, said, given", [
    ("asking", 1, ["Face ID not working"]),
    ("more", "all", ["Back glass cracked in the top right corner", "Face ID not working", "Battery 79%"]),
])
def test_at_or_over_asking_you_can_say_you_dont_mind_the_flaws_you_pick(client, kind, said, given):
    """14 Oct: Pay asking and Offer more can say the flaws you don't mind, the worst first, as many as you pick; Offer
    more still says why it pays more (it's if they take the listing down)."""
    client.use(local=FakeModel("gemma3:4b", READ3, READ3), messages=PAST)
    draft = client.post("/messages/draft", json={"listing": LISTING3, "kind": kind, "mention": True, "writer": "template",
                                                 "flaws_said": said}).json()
    assert draft["status"] == "ready" and draft["point"] == given and draft["mentioned"] is True
    message = draft["message"]
    assert "don't mind" in message.lower() and "Face ID" in message
    assert ("glass" in message.lower()) is (said == "all")
    if kind == "more":
        assert "listing down" in message or "hold it" in message
    plain = client.post("/messages/draft", json={"listing": LISTING3, "kind": kind, "mention": None if kind == "more"
                                                 else False, "writer": "template"}).json()
    assert "mind" not in plain["message"].lower() and "Face ID" not in plain["message"]
