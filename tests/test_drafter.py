"""The drafter, tested with pretend models before any real AI runs: which model
is asked, when the API is (and isn't) used, and when a draft is ready."""

import http.client
import io
import json
import urllib.error
import urllib.request
from decimal import Decimal
from types import SimpleNamespace

import pytest

from flip.ai import ApiModel, LocalModel, Reply, parse_answer
from flip.audit import AuditLog
from flip.catalogue import fill_from_catalogue, load_catalogue, load_conditions
from flip.costs import cost_pence
from flip.drafter import draft_listing
from flip.prompts import SYSTEM, answer_schema, colour_schema, listing_prompt
from tests.fakes import FakeModel

CATALOGUE = load_catalogue()
CONDITIONS = load_conditions()
IPHONE_13 = next(m for m in CATALOGUE if m["id"] == "iphone-13")

ENTRY = {
    "id": "t1",
    "original_title": "iPhone 13 128GB unlocked",
    "original_description": "Selling my iPhone, works perfectly. Comes with box.",
    "my_notes": "boxed, battery 87%, light scratch on the back",
}
GOOD = {"colour": "Midnight", "condition_id": "3000",
        "condition_note": "Light scratch on the back. Battery health 87%.",
        "description": "Apple iPhone 13 128GB in Midnight, unlocked, boxed. Light scratch on the back, "
                       "battery health 87%."}
BAD = {**GOOD, "description": "Apple iPhone 13 128GB in Midnight, unlocked, boxed, with original charger."}


class FakeClient:
    """A pretend Anthropic client: keeps the request, returns a prepared response."""

    def __init__(self, response):
        self.response, self.sent, self.messages = response, None, self

    def create(self, **request):
        self.sent = request
        return self.response


PHOTO = "pretend-base64-photo"  # the fakes never look at it; with it, the AI's colour can count


def draft(entry=ENTRY, local=None, api=None, mode="auto", **options):
    return draft_listing(entry, CATALOGUE, CONDITIONS, local, api, mode, **{"photos": [PHOTO], **options})


def haiku_response(stop_reason="end_turn", text=json.dumps(GOOD)):
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)],
                           usage=SimpleNamespace(input_tokens=1200, output_tokens=250))


# ── when each model is used ─────────────────────────────────────────────────

def test_a_good_local_answer_is_used_and_the_api_is_never_asked():
    api = FakeModel("claude-haiku-5-5")
    result = draft(local=FakeModel("gemma3:4b", GOOD), api=api)
    assert result["status"] == "ready"
    assert result["title"] == "Apple iPhone 13 128GB Midnight Unlocked"
    assert api.asked == []
    assert result["attempts"][0]["cost_pence"] == 0  # the local model is free


def test_a_failed_check_gets_one_try_on_the_api():
    result = draft(local=FakeModel("gemma3:4b", BAD), api=FakeModel("claude-haiku-5-5", GOOD))
    assert result["status"] == "ready"
    assert [a["model"] for a in result["attempts"]] == ["gemma3:4b", "claude-haiku-5-5"]
    assert result["attempts"][0]["problems"] == ["description says things your inputs don't: charger"]
    assert result["attempts"][1]["cost_pence"] > 0


def test_both_wrong_means_needs_you():
    result = draft(local=FakeModel("gemma3:4b", BAD), api=FakeModel("claude-haiku-5-5", BAD))
    assert (result["status"], result["reasons"]) == ("needs you", ["no answer passed the checks", "fill in: colour"])
    assert result["title"] == "Apple iPhone 13 128GB Unlocked"  # code's part stands without the AI's


# the 2 Sep listing, with what Gemma and Haiku answered for it
PRO_MAX = {"id": "t2", "original_title": "iphone 14 pro max", "original_description": "I phone 14promax128gb",
           "my_notes": "battery 85% , unlocked , few scraches"}
GEMMA_PRO_MAX = {"colour": "Space Black", "condition_id": "3000",
                 "condition_note": "The phone has a few scratches on the screen and back.",
                 "description": "This is an Apple iPhone 14 Pro Max. The phone is unlocked and has an 85% battery health."}
HAIKU_PRO_MAX = {"colour": "Deep Purple", "condition_id": "3000",
                 "condition_note": "Battery health is 85%. There are a few scratches on the device.",
                 "description": "Apple iPhone 14 Pro Max with a 6.7 inch screen, A16 Bionic processor and 5G "
                                "connectivity. It is unlocked and runs iOS. The phone has a few scratches and the "
                                "battery health is 85%."}


def test_a_slip_in_your_notes_doesnt_fail_a_right_answer_but_a_made_up_place_does():
    result = draft(PRO_MAX, local=FakeModel("gemma3:4b", GEMMA_PRO_MAX), api=FakeModel("claude-haiku-5-5", HAIKU_PRO_MAX))
    assert [a["problems"] for a in result["attempts"]] == \
        [["condition_note says where marks are when your notes don't: back, screen"], []]
    assert (result["item"]["colour"], result["title"], result["reasons"]) == \
        ("Deep Purple", "Apple iPhone 14 Pro Max Deep Purple Unlocked", ["fill in: storage"])


def test_the_original_sellers_description_is_never_used():
    # 14 Oct (the owner: "only write it from the notes", as AlertFlip does): on eBay you're the seller, so a
    # description says only what you checked. An old entry's seller's text is ignored: not in the prompt, not a
    # source the AI may state, not a field's value or hint, not a "check it" reason
    entry = {"id": "t4", "original_title": "iphone 13 blue unlocked",
             "original_description": "128gb, comes with a 12 month warranty and the charger",
             "my_notes": "battery 78 , few scratches on screen"}
    answer = {"colour": "Blue", "condition_id": "3000",
              "condition_note": "The phone has a few scratches on the screen and the battery is at 78%.",
              "description": "Apple iPhone 13, unlocked. A few scratches on the screen, battery health 78%."}
    local = FakeModel("gemma3:4b", answer)
    result = draft(entry, local=local)
    assert "warranty" not in local.asked[0]["user"] and "Description:" not in local.asked[0]["user"]
    assert (result["attempts"][0]["problems"], result["reasons"]) == ([], ["fill in: storage"])
    storage = {s["name"]: s for s in result["ebay"]["specifics"]}["Storage Capacity"]
    assert (storage["value"], "hint" in storage) == (None, False)
    told = {**answer, "description": answer["description"] + " Comes with a 12 month warranty."}
    refused = draft(entry, local=FakeModel("gemma3:4b", told), mode="local")
    assert refused["attempts"][0]["problems"] == ["description has numbers that aren't in your inputs: 12",
                                                  "description says things your inputs don't: warranty"]


def test_a_battery_figure_on_its_own_in_your_notes_is_told_to_the_ai_and_backs_its_answer():
    # "78" with nothing next to it in a phone's notes is its battery health; "128" in the
    # title is a size the iPhone 13 comes in (flip.numbers)
    entry = {"id": "t5", "original_title": "iPhone 13 128 blue unlocked", "original_description": "",
             "my_notes": "78 , few scratches on screen"}
    answer = {"condition_id": "3000", "condition_note": "Battery health is 78%. A few scratches on the screen.",
              "description": "Apple iPhone 13 128GB in Blue, unlocked. A few scratches on the screen, battery "
                             "health 78%."}
    local = FakeModel("gemma3:4b", answer)
    result = draft(entry, local=local)
    assert "- Battery health: 78% (from the reseller's notes)" in local.asked[0]["user"]
    assert (result["attempts"][0]["problems"], result["status"]) == ([], "ready")
    assert (result["item"]["storage"], result["item"]["battery"], result["title"]) == \
        ("128GB", "78", "Apple iPhone 13 128GB Blue Unlocked")


def test_your_notes_typed_in_a_hurry_back_gemmas_answer():
    # the 2 Sep iPhone 13 mini: Gemma's answer was right, and failed only on "baterray" and "scraches"
    entry = {"id": "t3", "original_title": "iphone 13 mini 128gb unlocked to any sim",
             "my_notes": "baterray 88 , few scraches on back , crack on front"}
    gemma = {"colour": "unsure", "condition_id": "3000",
             "condition_note": "The phone has a crack on the front screen and a few scratches on the back. "
                               "Battery health is 88%.",
             "description": "This is an Apple iPhone 13 mini with 128GB of storage and is unlocked. The phone is used and "
                            "has a crack on the front screen and a few scratches on the back. It is sold with a battery "
                            "health of 88%."}
    api = FakeModel("claude-haiku-5-5", {"colour": "unsure"})
    result = draft(entry, local=FakeModel("gemma3:4b", gemma), api=api)
    assert (result["attempts"][0]["problems"], result["reasons"]) == ([], ["fill in: colour"])
    assert list(api.asked[0]["schema"]["properties"]) == ["colour"]  # Haiku looked at the colour only, nothing redrafted
    assert result["title"] == "Apple iPhone 13 mini 128GB Unlocked"


def test_a_broken_answer_counts_as_wrong():
    broken = Reply("gemma3:4b", error="the answer isn't valid JSON")
    result = draft(local=FakeModel("gemma3:4b", broken), api=FakeModel("claude-haiku-5-5", GOOD))
    assert result["attempts"][0]["problems"] == ["the answer isn't valid JSON"]
    assert result["status"] == "ready"


def test_nothing_goes_to_the_api_when_the_local_model_isnt_running():
    down = Reply("gemma3:4b", error="the local model isn't running (connection refused)", reachable=False)
    api = FakeModel("claude-haiku-5-5", GOOD)
    result = draft(local=FakeModel("gemma3:4b", down), api=api)
    assert api.asked == []
    assert result["status"] == "needs you"
    assert "nothing was sent to Claude Haiku 5.5 (paid) instead" in result["reasons"][0]  # named (14 Oct)
    assert draft(local=None, api=FakeModel("claude-haiku-5-5", GOOD))["attempts"] == []  # no local model at all


def test_each_mode_uses_only_its_models():
    api = FakeModel("claude-haiku-5-5", GOOD)
    assert draft(local=FakeModel("gemma3:4b", BAD), api=api, mode="local")["status"] == "needs you"
    assert api.asked == []
    local = FakeModel("gemma3:4b")
    assert draft(local=local, api=FakeModel("claude-haiku-5-5", GOOD), mode="api")["status"] == "ready"
    assert local.asked == []


# ── what "ready" means ──────────────────────────────────────────────────────

def test_an_unsure_colour_leaves_the_colour_for_you():
    unsure = {**GOOD, "colour": "unsure", "description": GOOD["description"].replace(" in Midnight", "")}
    result = draft(local=FakeModel("gemma3:4b", unsure))
    assert (result["status"], result["reasons"]) == ("needs you", ["fill in: colour"])
    assert result["title"] == "Apple iPhone 13 128GB Unlocked"


def test_missing_facts_mean_needs_you_even_when_the_ai_is_right():
    entry = {**ENTRY, "original_title": "iPhone 13 unlocked"}  # no storage anywhere
    right = {**GOOD, "description": GOOD["description"].replace(" 128GB", "")}
    result = draft(entry, local=FakeModel("gemma3:4b", right))
    assert (result["status"], result["reasons"]) == ("needs you", ["fill in: storage"])


def test_a_model_not_in_the_catalogue_asks_no_ai():
    local = FakeModel("gemma3:4b")
    result = draft({**ENTRY, "original_title": "Samsung Galaxy S24 Ultra 256GB"}, local=local)
    assert (result["status"], result["reasons"], local.asked) == \
        ("needs you", ["List on eBay is for iPhones only: say which iPhone it is in the title"], [])


@pytest.mark.parametrize("title", ["Samsung Galaxy S23 128GB", "PS5 Slim digital 1TB", "Nintendo Switch OLED",
                                   "AirPods Pro 2"])
def test_only_iphones_are_drafted(title):
    # 14 Oct (the owner's call): the catalogue still knows these (for messages), but List on eBay drafts iPhones only
    local = FakeModel("gemma3:4b", GOOD)
    result = draft({**ENTRY, "original_title": title}, local=local)
    assert (result["status"], result["reasons"], local.asked, result["ebay"]) == \
        ("needs you", ["List on eBay is for iPhones only"], [], None)


# ── what the AI is asked ────────────────────────────────────────────────────

def test_colour_is_asked_for_only_when_code_couldnt_fill_it():
    unknown = fill_from_catalogue("iPhone 13 128GB", "", CATALOGUE)
    known = fill_from_catalogue("iPhone 13 128GB Pink", "", CATALOGUE)
    schema = answer_schema(unknown, IPHONE_13, CONDITIONS["phones"])
    assert schema["properties"]["colour"]["enum"] == [*IPHONE_13["colours"], "unsure"]
    assert schema["properties"]["condition_id"]["enum"] == ["1000", "1500", "3000", "7000"]
    assert "colour" not in answer_schema(known, IPHONE_13, CONDITIONS["phones"])["properties"]


@pytest.mark.parametrize("notes, condition", [
    ("baterray 88 , few scraches on back , crack on front", "3000"),  # a crack is wear, not a fault
    ("battery 85%, face id not working", "7000"),
    ("brand new sealed", "1000"),
    ("never used, box opened to check", "1500"),
    ("", "3000"),
])
def test_code_sets_the_condition_and_the_ai_can_answer_no_other(notes, condition):
    local = FakeModel("gemma3:4b", {**GOOD, "condition_id": condition})
    draft({**ENTRY, "my_notes": notes}, local=local)
    asked = local.asked[0]
    assert asked["schema"]["properties"]["condition_id"]["enum"] == [condition]
    assert f"(condition_id {condition})" in asked["user"]


def test_the_prompt_gives_your_title_and_notes_never_the_sellers_description():
    item = fill_from_catalogue(ENTRY["original_title"], ENTRY["my_notes"], CATALOGUE)
    system, user = listing_prompt(item, IPHONE_13, ENTRY, 2)
    assert "boxed, battery 87%, light scratch on the back" in user
    assert "Reseller's title for it: iPhone 13 128GB unlocked" in user
    assert ENTRY["original_description"] not in user and "original seller" not in system
    assert "Pick from: Midnight, Starlight" in user
    assert "Photos attached: 2" in user


# ── the two real models, without spending anything ─────────────────────────

def test_the_api_request_holds_haiku_to_the_shape_at_low_effort():
    client = FakeClient(haiku_response())
    reply = ApiModel(client=client).ask("system", "user", ["QUJD"], {"type": "object"})
    assert (reply.answer, reply.tokens_in, reply.tokens_out) == (GOOD, 1200, 250)
    assert client.sent["model"] == "claude-haiku-5-5"
    assert client.sent["output_config"] == {"effort": "low",
                                            "format": {"type": "json_schema", "schema": {"type": "object"}}}
    assert "temperature" not in client.sent
    assert client.sent["messages"][0]["content"][0]["source"]["media_type"] == "image/jpeg"


def test_an_api_refusal_or_cut_off_answer_counts_as_wrong():
    for stop in ("refusal", "max_tokens"):
        reply = ApiModel(client=FakeClient(haiku_response(stop, ""))).ask("s", "u", [], {})
        assert reply.answer is None and stop in reply.error


def test_a_local_model_that_isnt_running_is_reported_as_unreachable():
    reply = LocalModel(url="http://127.0.0.1:9", timeout=2).ask("s", "u", [], {"type": "object"})
    assert (reply.answer, reply.reachable) == (None, False)
    assert "isn't running" in reply.error


class FakeOllamaResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_gemmas_curly_end_is_closed_instead_of_running_to_the_limit(monkeypatch):
    # Gemma's real answer from a live run: it ended with ”} and then wrote "✉️ ✉️ ✉️" for 32 seconds
    sent = {}

    def fake_urlopen(request, timeout):
        sent.update(json.loads(request.data))
        content = '{\n"message": "Hi mate, I’d like to offer £185. Does it come with a charger?'
        return FakeOllamaResponse(json.dumps({"message": {"content": content}, "done_reason": "stop"}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    reply = LocalModel(max_tokens=300).ask("s", "u", [], {"type": "object"})
    assert (reply.answer, reply.error) == ({"message": "Hi mate, I’d like to offer £185. Does it come with a charger?"}, "")
    assert sent["options"]["num_predict"] == 300 and "”}" in sent["options"]["stop"]


def test_gemmas_curly_quotes_in_a_row_stop_it_too(monkeypatch):
    # 2 Sep, live: '...on the back.”””  1000” 1500” 7000” 3000”...' for 64 seconds, to the token limit
    sent = {}

    def fake_urlopen(request, timeout):
        sent.update(json.loads(request.data))
        content = '{"colour": "unsure", "condition_id": "3000", "condition_note": "", "description": "Scratches on the back.'
        return FakeOllamaResponse(json.dumps({"message": {"content": content}, "done_reason": "stop"}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    reply = LocalModel().ask("s", "u", [], {"type": "object"})
    assert (reply.answer["description"], reply.error) == ("Scratches on the back.", "")
    assert "””" in sent["options"]["stop"]


def test_a_complete_local_answer_is_left_alone():
    from flip.ai import ollama_text
    finished = {"message": {"content": '{"message": "Hi mate"}'}, "done_reason": "stop"}
    assert ollama_text(finished) == '{"message": "Hi mate"}'
    assert ollama_text({"message": {"content": '{"message": "Hi'}, "done_reason": "length"}) == '{"message": "Hi'


def test_reading_the_models_answer():
    assert parse_answer('{"a": 1}') == ({"a": 1}, "")
    assert parse_answer("not json") == (None, "the answer isn't valid JSON")
    assert parse_answer("[1, 2]") == (None, "the answer isn't a JSON object")


# ── cost and the audit log ──────────────────────────────────────────────────

def test_the_api_costs_fractions_of_a_penny_and_the_local_model_nothing(monkeypatch):
    monkeypatch.setenv("USD_TO_GBP", "0.80")
    assert cost_pence("gemma3:4b", 1500, 300) == 0
    # 1,500 in at $0.10 per million + 300 out at $0.50 per million = $0.0003 = 0.024p
    assert cost_pence("claude-haiku-5-5", 1500, 300) == Decimal("0.024")
    # Sonnet 5.5, the reason's fixer (flip.wording, 3 Oct): 1,500 in at $2 + 300 out at $10 = $0.006 = 0.48p
    assert cost_pence("claude-sonnet-5-5", 1500, 300) == Decimal("0.48")
    # ...from the cache, the 1,500 in cost a tenth: $0.0003 + $0.003 = 0.264p
    assert cost_pence("claude-sonnet-5-5", 0, 300, tokens_cached=1500) == Decimal("0.264")
    # a paid model with no price here yet is never free: priced as the dearest one known (the explainer's, 14 Sep)
    assert cost_pence("claude-sonnet-9", 1500, 300) == cost_pence("claude-sonnet-5-5", 1500, 300) > 0


def test_every_attempt_and_outcome_goes_in_the_audit_log(tmp_path):
    log = AuditLog(tmp_path / "audit.sqlite3")
    draft(local=FakeModel("gemma3:4b", BAD), api=FakeModel("claude-haiku-5-5", GOOD), log=log)
    attempts = log.db.execute("select model, problems from attempts order by id").fetchall()
    assert [model for model, _ in attempts] == ["gemma3:4b", "claude-haiku-5-5"]
    assert "charger" in attempts[0][1]
    assert log.db.execute("select item_id, status from drafts").fetchall() == [("t1", "ready")]


UNSURE_GEMMA = {**GOOD, "colour": "unsure", "description": GOOD["description"].replace(" in Midnight", "")}


def test_gemma_unsure_of_the_colour_gets_haikus_look_at_the_colour_alone(tmp_path):
    log = AuditLog(tmp_path / "audit.sqlite3")
    local, api = FakeModel("gemma3:4b", UNSURE_GEMMA), FakeModel("claude-haiku-5-5", {"colour": "Midnight"})
    result = draft(local=local, api=api, log=log)
    assert (result["status"], result["item"]["colour"], result["colour_from"], result["colour_by"]) == \
        ("ready", "Midnight", "photos", "claude-haiku-5-5")
    assert result["answer"] == UNSURE_GEMMA  # Gemma's draft stands: Haiku only said the colour
    assert [(a["model"], a.get("colour_only", False)) for a in result["attempts"]] == \
        [("gemma3:4b", False), ("claude-haiku-5-5", True)]
    asked = api.asked[0]
    assert asked["schema"] == colour_schema(IPHONE_13) and asked["photos"] == [PHOTO]
    assert (asked["system"], asked["user"]) == (local.asked[0]["system"], local.asked[0]["user"])
    assert result["title"] == "Apple iPhone 13 128GB Midnight Unlocked"
    assert [m for (m,) in log.db.execute("select model from attempts order by id")] == ["gemma3:4b", "claude-haiku-5-5"]


def test_a_colour_look_is_paid_ai_but_doesnt_count_as_writing_the_draft(tmp_path):
    """The test agents' (14 Sep): a look at the colour alone isn't the paid model writing the draft; it's a paid
    output of its own, not one made on this device (Home's "done on this device", 14 Oct)."""
    log = AuditLog(tmp_path / "audit.sqlite3")
    for n, look in enumerate(({"colour": "Midnight"}, {"colour": "unsure"})):  # each draft its own item, as in the app
        draft({**ENTRY, "id": f"t{n}"}, local=FakeModel("gemma3:4b", UNSURE_GEMMA), api=FakeModel("claude-haiku-5-5", look),
              log=log)
    draft({**ENTRY, "id": "t2"}, local=FakeModel("gemma3:4b", GOOD), log=log)  # a colour the listing settles: no look
    stats = log.stats()
    assert (stats["outputs_here"], stats["outputs"]) == (3, 5)  # Gemma's 3 drafts here, and the 2 paid looks
    assert {m["model"]: m["job"] for m in stats["models"]}["gemma3:4b"] == "listing"  # Gemma wrote all three
    haiku = next(m for m in stats["models"] if m["model"] == "claude-haiku-5-5")
    assert (haiku["attempts"], haiku["cost_pence"] > 0) == (2, True)  # its looks are still counted, and paid for
    assert [job for (job,) in log.db.execute("select job from attempts order by id")] == \
        ["listing", "colour"] * 2 + ["listing"]  # an eBay listing's own job (14 Oct)


def test_haiku_unsure_too_or_failing_leaves_the_colour_for_you():
    for look in ({"colour": "unsure"}, {"colour": "Purple"}, Reply("claude-haiku-5-5", error="the API timed out")):
        result = draft(local=FakeModel("gemma3:4b", UNSURE_GEMMA), api=FakeModel("claude-haiku-5-5", look))
        assert (result["status"], result["reasons"], result["item"]["colour"]) == ("needs you", ["fill in: colour"], None)
        assert (result["colour_from"], result["colour_by"]) == (None, None)
        assert result["attempts"][-1]["colour_only"] and result["answer"] == UNSURE_GEMMA
    assert result["attempts"][-1]["problems"] == ["the API timed out"]


def test_no_second_look_at_the_colour_unless_gemma_drafted_from_photos_in_auto_mode():
    haiku = lambda: FakeModel("claude-haiku-5-5", {"colour": "Midnight"})
    api = haiku()
    assert draft(local=FakeModel("gemma3:4b", UNSURE_GEMMA), api=api, mode="local")["item"]["colour"] is None
    assert draft(local=FakeModel("gemma3:4b", UNSURE_GEMMA), api=api, photos=[])["item"]["colour"] is None
    assert api.asked == []  # local mode never asks the API; with no photos there's nothing to look at
    api = FakeModel("claude-haiku-5-5", UNSURE_GEMMA)
    result = draft(local=None, api=api, mode="api")
    assert (len(api.asked), result["item"]["colour"]) == (1, None)  # the API drafted it: its "unsure" stands
    api = FakeModel("claude-haiku-5-5", UNSURE_GEMMA)
    result = draft(local=FakeModel("gemma3:4b", BAD), api=api)
    assert (len(api.asked), result["item"]["colour"]) == (1, None)  # Gemma failed and Haiku drafted it: no third ask
    down = Reply("gemma3:4b", error="the local model isn't running (connection refused)", reachable=False)
    api = haiku()
    assert draft(local=FakeModel("gemma3:4b", down), api=api)["attempts"][-1]["model"] == "gemma3:4b"
    assert api.asked == []  # never the API in place of a local model that can't be reached
    known = {**ENTRY, "original_title": "iPhone 13 128GB unlocked Midnight"}
    api = haiku()
    assert draft(known, local=FakeModel("gemma3:4b", {k: v for k, v in GOOD.items() if k != "colour"}),
                 api=api)["colour_from"] == "listing"
    assert api.asked == []  # code read the colour from the title: nobody was asked for it


def test_with_no_photos_the_ais_colour_is_a_guess_and_stays_for_you():
    result = draft(local=FakeModel("gemma3:4b", GOOD), photos=[])
    assert (result["status"], result["item"]["colour"], result["colour_from"]) == ("needs you", None, None)
    assert result["reasons"] == ["fill in: colour"]
    with_photo = draft(local=FakeModel("gemma3:4b", GOOD))
    assert (with_photo["status"], with_photo["item"]["colour"], with_photo["colour_from"]) == ("ready", "Midnight", "photos")


# ── whatever answers on the local model's port, it never crashes a draft ────

def answering(monkeypatch, answer):
    """urlopen, pretend: it answers with these bytes, or raises this."""
    def urlopen(request, timeout):
        if isinstance(answer, BaseException):
            raise answer
        return io.BytesIO(answer)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


@pytest.mark.parametrize("answer", [
    b"{}", b"[1, 2]", b"<html>Bad gateway</html>", b'{"error": "model not found"}',
    b'{"message": {}}', b'{"message": {"content": 5}, "done_reason": "stop"}',
    b'{"message": {"content": null}, "done_reason": "stop"}', b'{"message": {"content": {"a": 1}}}',
    b"[" * 100000 + b"]" * 100000,
])
def test_a_reply_that_isnt_ollamas_is_as_good_as_no_model(monkeypatch, answer):
    answering(monkeypatch, answer)
    reply = LocalModel().ask("system", "user", [], {})
    assert (reply.answer, reply.reachable, reply.error) == (None, False, "Gemma 3 4B's answer couldn't be read")


@pytest.mark.parametrize("failure", [TimeoutError("timed out"), http.client.RemoteDisconnected("gone"),
                                     http.client.IncompleteRead(b"{"), ConnectionResetError("reset")])
def test_a_local_model_that_stops_answering_is_never_swapped_for_the_api(monkeypatch, failure):
    answering(monkeypatch, failure)
    result = draft(local=LocalModel(), api=FakeModel("claude-haiku-5-5"))  # asking it would fail: it has no answers
    assert result["status"] == "needs you" and [a["model"] for a in result["attempts"]] == ["gemma3:4b"]
    assert "nothing was sent to Claude Haiku 5.5 (paid) instead" in result["reasons"][0]


@pytest.mark.parametrize("page", [io.BytesIO("modèle introuvable".encode("latin-1")), None])
def test_an_error_page_is_read_whatever_its_encoding_or_skipped(monkeypatch, page):
    class HangsUp(io.RawIOBase):
        def read(self, *size):
            raise ConnectionResetError("reset")
    answering(monkeypatch, urllib.error.HTTPError("http://127.0.0.1:11434", 404, "Not Found", {}, page or HangsUp()))
    reply = LocalModel().ask("system", "user", [], {})
    assert reply.error.startswith("Ollama refused Gemma 3 4B (404)") and not reply.reachable


def test_token_counts_that_cant_be_are_counted_as_none(monkeypatch):
    answer = {"message": {"content": json.dumps(GOOD)}, "done_reason": "stop", "prompt_eval_count": "lots",
              "eval_count": 2**70}
    answering(monkeypatch, json.dumps(answer).encode())
    reply = LocalModel().ask("system", "user", [], {})
    assert (reply.answer, reply.tokens_in, reply.tokens_out) == (GOOD, 0, 0)


def test_half_a_character_in_an_answer_becomes_one_that_can_be_written(tmp_path):
    answer, error = parse_answer('{"description": "Light scratch \\ud800 on the back"}')
    assert (answer["description"], error) == ("Light scratch � on the back", "")
    AuditLog(tmp_path / "audit.sqlite3").attempt("item", Reply("gemma3:4b", answer=answer), [], 0)  # no crash


def test_the_prompt_is_for_an_iphone_written_as_its_seller_without_specs():
    # 14 Oct: Claude wrote "the reseller describes it as like new" and listed the chip and screen size
    assert "second-hand iPhone" in SYSTEM and "Write as the seller, about the phone" in SYSTEM
    assert "No specs such as screen size, processor, chip, iOS or 5G" in SYSTEM


def test_a_draft_that_talks_about_your_notes_is_refused():
    told = {**GOOD, "condition_note": "The reseller notes a light scratch on the back. Battery health 87%."}
    result = draft(local=FakeModel("gemma3:4b", told), mode="local")
    assert result["attempts"][0]["problems"] == ['condition_note talks about the notes, not the phone: "reseller"']


def test_the_writer_gets_no_specs_and_no_example_battery_figure():
    # 14 Oct, 40 real iPhones: Gemma 3 4B listed the chip and screen size whenever it was handed them, and wrote
    # "battery health 88%" (the prompt's example) for phones whose notes give no figure
    item = fill_from_catalogue("iPhone 13 128GB", "few scratches on the back", CATALOGUE)
    system, user = listing_prompt(item, IPHONE_13, {**ENTRY, "my_notes": "few scratches on the back"}, 0)
    assert "Screen Size" not in user and "Processor" not in user and "Bionic" not in user
    assert "88" not in system and "Battery health" not in user


def test_your_battery_figure_is_in_the_condition_note_whoever_wrote_it():
    # 14 Oct, judged blind: passing drafts left the battery figure out 1 time in 8 (Haiku) to 1 in 4 (Gemma)
    left_out = {**GOOD, "condition_note": "Light scratch on the back."}
    result = draft(local=FakeModel("gemma3:4b", left_out))
    assert (result["status"], result["answer"]["condition_note"]) == ("ready", "Light scratch on the back. Battery health 87%.")
    assert draft(local=FakeModel("gemma3:4b", GOOD))["answer"]["condition_note"] == GOOD["condition_note"]  # said once
    none = draft({**ENTRY, "my_notes": "boxed, light scratch on the back"},
                 local=FakeModel("gemma3:4b", {**left_out, "description": GOOD["description"].split(" Light")[0]}))
    assert none["answer"]["condition_note"] == "Light scratch on the back."  # no figure in your notes: nothing added
