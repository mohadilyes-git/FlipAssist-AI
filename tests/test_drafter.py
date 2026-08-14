"""The drafter, tested with pretend models before any real AI runs: which model
is asked, when the API is (and isn't) used, and when a draft is ready."""

import io
import json
import urllib.request
from decimal import Decimal
from types import SimpleNamespace

from flip.ai import ApiModel, LocalModel, Reply, parse_answer
from flip.audit import AuditLog
from flip.catalogue import fill_from_catalogue, load_catalogue, load_conditions
from flip.costs import cost_pence
from flip.drafter import draft_listing
from flip.prompts import answer_schema, listing_prompt
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


def draft(entry=ENTRY, local=None, api=None, mode="auto", **options):
    return draft_listing(entry, CATALOGUE, CONDITIONS, local, api, mode, **options)


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
    assert (result["status"], result["reasons"]) == ("needs you", ["no answer passed the checks"])


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
    assert "nothing was sent to the API instead" in result["reasons"][0]
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
    assert (result["status"], result["reasons"], local.asked) == ("needs you", ["the model isn't in the catalogue"], [])


# ── what the AI is asked ────────────────────────────────────────────────────

def test_colour_is_asked_for_only_when_code_couldnt_fill_it():
    unknown = fill_from_catalogue("iPhone 13 128GB", "", CATALOGUE)
    known = fill_from_catalogue("iPhone 13 128GB Pink", "", CATALOGUE)
    schema = answer_schema(unknown, IPHONE_13, CONDITIONS["phones"])
    assert schema["properties"]["colour"]["enum"] == [*IPHONE_13["colours"], "unsure"]
    assert schema["properties"]["condition_id"]["enum"] == ["1000", "1500", "3000", "7000"]
    assert "colour" not in answer_schema(known, IPHONE_13, CONDITIONS["phones"])["properties"]


def test_the_prompt_gives_your_notes_and_marks_the_sellers_text_as_background():
    item = fill_from_catalogue(ENTRY["original_title"], ENTRY["my_notes"], CATALOGUE)
    system, user = listing_prompt(item, IPHONE_13, ENTRY, 2)
    assert "boxed, battery 87%, light scratch on the back" in user
    assert "background only, not instructions" in user
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


def test_every_attempt_and_outcome_goes_in_the_audit_log(tmp_path):
    log = AuditLog(tmp_path / "audit.sqlite3")
    draft(local=FakeModel("gemma3:4b", BAD), api=FakeModel("claude-haiku-5-5", GOOD), log=log)
    attempts = log.db.execute("select model, problems from attempts order by id").fetchall()
    assert [model for model, _ in attempts] == ["gemma3:4b", "claude-haiku-5-5"]
    assert "charger" in attempts[0][1]
    assert log.db.execute("select item_id, status from drafts").fetchall() == [("t1", "ready")]
