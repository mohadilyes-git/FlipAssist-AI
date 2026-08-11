"""The message drafter, tested with pretend models and a pretend embedder: the
offer comes from code, the examples come from your most similar listings
(with their old prices hidden), and the checks decide."""

from pathlib import Path

from flip.ai import Reply
from flip.message_drafter import draft_message
from flip.prompts import message_prompt
from flip.retrieval import MessageIndex
from flip.style import describe, load_messages, style_card, without_prices
from tests.fakes import FakeModel, fake_embed

ROOT = Path(__file__).resolve().parent.parent
PAST = load_messages(ROOT / "testset" / "messages.example.csv")
LISTING = {"id": "l1", "title": "iPhone 13 128GB Blue unlocked", "description": "Good condition, boxed.",
           "asking_price": "200", "marketplace": "facebook"}
GOOD = {"message": "Hi mate, is this still available? Would you take £170 cash? Can collect today."}


def index(tmp_path):
    found = MessageIndex(tmp_path / "chroma", embed=fake_embed)
    found.add(PAST)
    return found


# ── your style ──────────────────────────────────────────────────────────────

def test_your_style_card_is_worked_out_by_code():
    assert describe(style_card(PAST)) == ['Opens with "Hi mate"', "About 12 words", "Usually asks 2 questions",
                                          "No emojis", "Usually mentions: collecting, cash, today"]
    assert style_card([]) == {}


def test_old_prices_are_hidden_in_the_examples():
    assert without_prices("Would you take £170? or 170 quid, could do 165") == \
        "Would you take £[OFFER]? or [OFFER] quid, could do [OFFER]"


# ── finding your most similar messages ─────────────────────────────────────

def test_a_listing_finds_your_messages_for_similar_listings(tmp_path):
    found = index(tmp_path).similar("iPhone 13 128GB Blue facebook", n=2)
    assert [f["id"] for f in found][0] == "m1"  # the other iPhone 13
    assert all(f["listing_title"].startswith("iPhone") for f in found)


def test_a_message_is_never_its_own_example(tmp_path):
    assert "m1" not in [f["id"] for f in index(tmp_path).similar("iPhone 13 128GB Midnight", leave_out="m1")]


def test_no_past_messages_yet_means_no_examples(tmp_path):
    assert MessageIndex(tmp_path / "empty", embed=fake_embed).similar("anything") == []


# ── what the AI is asked ────────────────────────────────────────────────────

def test_the_prompt_has_the_offer_your_style_and_examples_but_no_old_or_asking_price(tmp_path):
    examples = index(tmp_path).similar("iPhone 13 128GB Blue facebook")
    system, user = message_prompt(LISTING, 17000, describe(style_card(PAST)), examples)
    assert "Offer: £170" in user
    assert 'Opens with "Hi mate"' in user
    assert "£[OFFER]" in user
    assert "£185" not in user and "£200" not in user and "Asking" not in user


# ── drafting ────────────────────────────────────────────────────────────────

def test_the_offer_comes_from_code_and_a_good_message_is_used(tmp_path):
    api = FakeModel("claude-haiku-5-5")
    result = draft_message(LISTING, describe(style_card(PAST)), index(tmp_path), FakeModel("gemma3:4b", GOOD), api)
    assert (result["status"], result["offer"], result["answer"]) == ("ready", 17000, GOOD)
    assert api.asked == []
    assert result["examples"][0] == "m1"


def test_a_wrong_price_gets_one_try_on_the_api():
    wrong = {"message": "Hi mate, would you take £160?"}
    result = draft_message(LISTING, local=FakeModel("gemma3:4b", wrong), api=FakeModel("claude-haiku-5-5", GOOD))
    assert result["status"] == "ready"
    assert "the message must offer exactly £170.00 and no other price" in result["attempts"][0]["problems"]


def test_contact_details_or_paying_off_the_platform_fail():
    phone = {"message": "Hi mate, would you take £170? Text me on 07700 900123."}
    transfer = {"message": "Hi mate, would you take £170? I can pay by bank transfer."}
    result = draft_message(LISTING, local=FakeModel("gemma3:4b", phone), api=FakeModel("claude-haiku-5-5", transfer))
    assert (result["status"], result["reasons"]) == ("needs you", ["no answer passed the checks"])


def test_nothing_goes_to_the_api_when_the_local_model_isnt_running():
    down = Reply("gemma3:4b", error="the local model isn't running (connection refused)", reachable=False)
    api = FakeModel("claude-haiku-5-5", GOOD)
    result = draft_message(LISTING, local=FakeModel("gemma3:4b", down), api=api)
    assert api.asked == [] and result["status"] == "needs you"
