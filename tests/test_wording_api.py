"""The reason checked after the draft is on screen (3 Oct 2026): /messages/draft with check_later gives
flip-wording's reason straight away ("pending"), and /messages/check-reason runs Haiku's check and Sonnet's fix,
puts a fixed reason in the message and keeps the audit log in step. Plus the speed settings: flip-wording's small
working memory and Haiku's check without thinking. Pretend models only."""

import io
import json
import urllib.request
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from flip import api
from flip.ai import ApiModel, LocalModel
from flip.audit import AuditLog
from flip.style import StyleBook
from flip.wording import worded_reason
from tests.fakes import FakeModel

KEY = "test-key-for-the-api-0123456789-abcdef"
LISTING = {"title": "iPhone 13 128GB Blue", "asking_price": "220", "marketplace": "facebook",
           "description": "Small chip on the bottom left corner. Batt 81. Otherwise great."}
READ = {"flaws": ["Small chip on the bottom left corner", "Batt 81"], "pickup": "", "no_offers": ""}
CLAUSE = "there's a chip on the corner and the battery health is 81%"
BETTER = "there's a small chip on the bottom left corner and the battery health is 81%"


def models(wording=CLAUSE, check="ok", fix=None):
    return {"wording": FakeModel("flip-wording-3", {"reason": wording}),
            "check": FakeModel("claude-haiku-5-5", {"verdict": check}),
            "fix": FakeModel("claude-sonnet-5-5", *([{"verdict": fix[0], "clause": fix[1]}] if fix else []))}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIP_API_KEY", KEY)
    monkeypatch.delenv("FLIP_WORDING_MODEL", raising=False)  # whatever .env says, the tests' own models
    log = AuditLog(tmp_path / "audit.sqlite3")
    book = StyleBook(tmp_path / "style.sqlite3")

    def use(wording, reading=READ):
        local = FakeModel("gemma3:4b", reading)
        api.app.dependency_overrides[api.setup] = lambda: api.Setup(local, None, log, wording=wording)
        api.app.dependency_overrides[api.audit] = lambda: log
        api.app.dependency_overrides[api.style] = lambda: book

    test = TestClient(api.app, headers={"X-API-Key": KEY})
    test.use, test.log = use, log
    yield test
    api.app.dependency_overrides.clear()


def drafted(client, used, check_later=True):
    client.use(used)
    answer = client.post("/messages/draft", json={"listing": LISTING, "kind": "lower", "mention": True,
                                                   "writer": "template", "check_later": check_later})
    assert answer.status_code == 200, answer.text
    return answer.json()


def checked(client, draft, used):
    client.use(used)
    answer = client.post("/messages/check-reason", json={
        "draft_id": draft["draft_id"], "listing": LISTING, "flaws": draft["reading"]["flaws"],
        "clause": draft["reason"]["clause"], "message": draft["message"], "kind": draft["kind"],
        "offer_pence": draft["offer_pence"], "by": draft["reason"]["by"]})  # as the app sends it
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_the_draft_comes_back_before_the_check_and_haiku_is_not_asked_yet(client):
    used = models()
    draft = drafted(client, used)
    assert draft["reason"] == {"clause": CLAUSE, "by": "flip-wording-3", "checked": "pending"}
    assert CLAUSE in draft["message"] and not used["check"].asked
    assert [a["job"] for a in draft["attempts"]][:1] == ["reason"]
    assert draft["reading"]["quotes"] == draft["reading"]["flaws"]  # Gemma's reading has no story cut to undo


def test_without_check_later_the_draft_is_checked_in_the_same_call(client):
    draft = drafted(client, models(), check_later=False)
    assert draft["reason"]["checked"] == "ok"


def test_a_fixed_reason_goes_into_the_message_and_approving_it_counts_as_unedited(client):
    draft = drafted(client, models())
    done = checked(client, draft, models(check="fix", fix=("fix", BETTER)))
    assert done["reason"] == {"clause": BETTER, "by": "claude-sonnet-5-5", "checked": "fixed"}
    assert done["changed"] and done["message"] == draft["message"].replace(CLAUSE, BETTER)
    assert [a["model"] for a in done["attempts"]] == ["claude-haiku-5-5", "claude-sonnet-5-5"]
    approved = client.post(f"/drafts/{draft['draft_id']}/approve", json={"sent": done["message"]}).json()
    assert approved["edited"] is False  # the audit log has the fixed message as the draft


def test_a_reason_haiku_passes_leaves_the_message_as_it_is(client):
    draft = drafted(client, models())
    done = checked(client, draft, models(check="ok"))
    # credited to the model that worded it, as the draft said (6 Oct review)
    assert done["reason"] == {"clause": CLAUSE, "by": "flip-wording-3", "checked": "ok"}
    assert not done["changed"] and done["message"] == draft["message"]


def test_a_fix_that_cant_go_in_leaves_the_message_and_says_why(client):
    draft = drafted(client, models())
    reworded = {**draft, "message": "Hi, would you take £185? There's a little chip and the battery is at 81%."}
    done = checked(client, reworded, models(check="fix", fix=("fix", BETTER)))
    assert not done["changed"] and done["problems"] == \
        ["the message words the reason its own way, so Claude Sonnet 5.5's fix wasn't put in"]  # named (14 Oct)
    # the reason says what the message gives: flip-wording's, flagged and kept, not Sonnet's (3 Oct review)
    assert done["reason"] == {"clause": CLAUSE, "by": "flip-wording-3", "checked": "flagged, kept"}
    none = checked(client, draft, models(check="fix", fix=("fix", "none")))
    assert not none["changed"] and none["problems"][0].startswith("Claude Sonnet 5.5 says nothing here is a flaw")
    assert none["reason"]["checked"] == "flagged, kept"


@pytest.mark.parametrize("fix, why", [
    (f"{BETTER}, text me on 07700 900123", "contains a link, email, phone number"),
    (f"{BETTER} and I've seen it for £150 elsewhere", "must offer exactly £185.00 and no other price"),
    ("there's a small chip on the bottom left corner and the battery health is 71%",
     "numbers that aren't in your inputs: 71"),
    (f"{BETTER} and the screen is cracked", "condition the listing doesn't: crack"),
])
def test_a_fix_is_held_to_the_listing_like_any_message(client, fix, why):
    """15 Nov review: a fix went into the message after only the condition checks, which read the fix itself as the
    listing's words, so a phone number, another price, a battery figure the listing doesn't give and a made-up crack
    went in. The listing is "Small chip on the bottom left corner. Batt 81. Otherwise great."."""
    draft = drafted(client, models())
    done = checked(client, draft, models(check="fix", fix=("fix", fix)))
    assert not done["changed"] and done["message"] == draft["message"]
    assert done["reason"] == {"clause": CLAUSE, "by": "flip-wording-3", "checked": "flagged, kept"}
    assert done["problems"] and all(p.startswith("Claude Sonnet 5.5's fix wasn't put in: with it, ")
                                    for p in done["problems"])
    assert any(why in p for p in done["problems"]), done["problems"]
    approved = client.post(f"/drafts/{draft['draft_id']}/approve", json={"sent": draft["message"]}).json()
    assert approved["edited"] is False  # the audit log still has the message as drafted


def test_with_the_step_off_nothing_is_checked(client):
    draft = drafted(client, models())
    client.use(None)
    answer = client.post("/messages/check-reason", json={
        "draft_id": draft["draft_id"], "listing": LISTING, "flaws": draft["reading"]["flaws"], "clause": CLAUSE,
        "message": draft["message"], "kind": "lower", "offer_pence": draft["offer_pence"]}).json()
    assert answer["reason"]["checked"] == "not checked" and not answer["changed"]


class FakeOllamaResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_flip_wording_asks_ollama_for_a_small_working_memory(monkeypatch):
    sent = []

    def fake_urlopen(request, timeout):
        sent.append(json.loads(request.data))
        return FakeOllamaResponse(json.dumps({"message": {"content": json.dumps({"reason": CLAUSE})},
                                              "done_reason": "stop"}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("FLIP_WORDING_MODEL", "flip-wording-3")
    worded_reason("iPhone 13", ["Batt 81"], mode="local")
    assert sent[0]["model"] == "flip-wording-3" and sent[0]["options"]["num_ctx"] == 2048
    LocalModel().ask("s", "u", [], {"type": "object"})
    assert sent[1]["options"]["num_ctx"] == 8192  # the reader and the writer keep room for photos


def test_haikus_check_asks_for_no_thinking():
    class Client:
        def __init__(self):
            self.messages, self.sent = self, None

        def create(self, **request):
            self.sent = request
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text='{"verdict": "ok"}')],
                                   usage=SimpleNamespace(input_tokens=150, output_tokens=12, cache_read_input_tokens=3700,
                                                         cache_creation_input_tokens=0))

    client = Client()
    reply = ApiModel("claude-haiku-5-5", client=client, thinking={"type": "disabled"}).ask("s", "u", [], {"type": "object"})
    assert client.sent["thinking"] == {"type": "disabled"} and reply.answer == {"verdict": "ok"}
    assert (reply.tokens_cached, reply.tokens_cache_write) == (3700, 0)
    plain = Client()
    ApiModel("claude-haiku-5-5", client=plain).ask("s", "u", [], {"type": "object"})
    assert "thinking" not in plain.sent  # everything else asks as before


def test_haiku_checks_the_quotes_and_code_checks_the_flaws(client):
    draft = drafted(client, models())
    used = models(check="fix", fix=("fix", BETTER))
    client.use(used)
    whole = ["Small chip on the bottom left corner", "Batt 81. Otherwise great."]
    answer = client.post("/messages/check-reason", json={
        "draft_id": draft["draft_id"], "listing": LISTING, "flaws": draft["reading"]["flaws"], "quotes": whole,
        "clause": draft["reason"]["clause"], "message": draft["message"], "kind": draft["kind"],
        "offer_pence": draft["offer_pence"]})
    assert answer.status_code == 200, answer.text
    assert "- Batt 81. Otherwise great." in used["check"].asked[0]["user"]  # the same lines flip-wording words from
    assert answer.json()["changed"]


def test_make_it_longer_keeps_the_fixed_reason_and_asks_nobody(client):
    draft = drafted(client, models())
    done = checked(client, draft, models(check="fix", fix=("fix", BETTER)))
    used = models()
    client.use(used)
    longer = client.post("/messages/draft", json={"listing": LISTING, "kind": "lower", "mention": True,
                                                  "writer": "template", "check_later": True, "length": "longer",
                                                  "previous": done["message"],
                                                  "reason": {**done["reason"], "quotes": draft["reading"]["quotes"]}})
    assert longer.status_code == 200, longer.text
    assert longer.json()["reason"] == done["reason"] and not used["wording"].asked and not used["check"].asked
