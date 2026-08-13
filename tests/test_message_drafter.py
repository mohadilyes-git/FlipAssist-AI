"""The message drafter, tested with pretend models and a pretend embedder: the
offer comes from code, the examples come from your most similar listings
(with their old prices hidden), your style decides whether the listing's flaw
or good condition goes in, and the checks decide."""

from pathlib import Path

from flip.ai import Reply
from flip.message_drafter import draft_message
from flip.offers import point_for
from flip.prompts import message_prompt
from flip.retrieval import MessageIndex
from flip.style import describe, load_messages, style_card, without_prices
from tests.fakes import FakeModel, fake_embed

ROOT = Path(__file__).resolve().parent.parent
PAST = load_messages(ROOT / "testset" / "messages.example.csv")
LISTING = {"id": "l1", "title": "iPhone 13 128GB Blue unlocked", "description": "Good condition, boxed.",
           "asking_price": "200", "marketplace": "facebook"}
BROKEN = {**LISTING, "description": "Broken back but everything works."}
GOOD = {"message": "Hi mate, is this still available? Would you take £170 cash? Can collect today."}
WITH_FLAW = {"message": "Hi mate, would you take £170 as the back is broken? Can collect today."}
# a reseller whose messages usually mention the condition
TALKER = [{"my_message": "Hi mate, would you take £150 as the screen's cracked?"},
          {"my_message": "Hi mate, any scratches? Would you take £90?"}]


def index(tmp_path):
    found = MessageIndex(tmp_path / "chroma", embed=fake_embed)
    found.add(PAST)
    return found


# ── your style ──────────────────────────────────────────────────────────────

def test_your_style_card_is_worked_out_by_code():
    assert describe(style_card(PAST)) == ['Opens with "Hi mate"', "About 12 words", "Usually asks 2 questions",
                                          "No emojis", "Usually mentions: collecting, cash, today"]
    assert style_card([]) == {}


def test_mentioning_condition_is_your_style_when_you_usually_do():
    assert "condition" in style_card(TALKER)["mentions"]
    assert "condition" not in style_card(PAST)["mentions"]


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


def test_the_prompt_says_the_kind_of_offer_and_what_to_say_about_the_condition():
    point = point_for("lower", "Broken back")
    _, user = message_prompt(BROKEN, 17000, [], [], "lower", point)
    assert "Offer: £170, under their asking price" in user
    assert 'as the reason for the offer: "Broken back"' in user
    _, user = message_prompt(LISTING, 21000, [], [], "more")
    assert "never as a question" in user and "Condition: don't mention it" in user


# ── drafting ────────────────────────────────────────────────────────────────

def test_the_offer_comes_from_code_and_a_good_message_is_used(tmp_path):
    api = FakeModel("claude-haiku-5-5")
    result = draft_message(LISTING, style_card(PAST), index(tmp_path), FakeModel("gemma3:4b", GOOD), api)
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


# ── the kind of offer, and the listing's flaw or good condition ────────────

def test_the_flaw_goes_in_by_itself_when_your_messages_usually_mention_condition():
    local = FakeModel("gemma3:4b", WITH_FLAW)
    result = draft_message(BROKEN, style_card(TALKER), local=local)
    assert (result["status"], result["point"], result["mentioned"], result["ask"]) == \
        ("ready", ["Broken back"], True, None)
    assert 'as the reason for the offer: "Broken back"' in local.asked[0]["user"]


def test_otherwise_the_draft_leaves_it_out_and_asks_you():
    result = draft_message(BROKEN, style_card(PAST), local=FakeModel("gemma3:4b", GOOD))
    assert (result["status"], result["mentioned"]) == ("ready", False)
    assert result["ask"] == 'The listing says "Broken back". Mention it as the reason for your offer?'
    # you say yes: drafted again with it, and nothing more to ask
    again = draft_message(BROKEN, style_card(PAST), local=FakeModel("gemma3:4b", WITH_FLAW), mention=True)
    assert (again["status"], again["mentioned"], again["ask"]) == ("ready", True, None)
    # you said no: it stays out, and you aren't asked again
    assert draft_message(BROKEN, local=FakeModel("gemma3:4b", GOOD), mention=False)["ask"] is None


def test_a_draft_that_leaves_out_the_flaw_you_said_yes_to_fails():
    result = draft_message(BROKEN, local=FakeModel("gemma3:4b", GOOD), api=FakeModel("claude-haiku-5-5", WITH_FLAW),
                           mention=True)
    assert result["attempts"][0]["problems"] == ['the message leaves out what the listing says: "Broken back"']
    assert result["status"] == "ready"


def test_an_offer_at_the_asking_price_says_you_dont_mind_the_flaw():
    happy = {"message": "Hi mate, is this still available? I don't mind the broken back, happy to pay £200."}
    result = draft_message(BROKEN, local=FakeModel("gemma3:4b", happy), kind="asking", mention=True)
    assert (result["status"], result["offer"]) == ("ready", 20000)


def test_paying_more_gives_the_good_condition_and_is_said_never_asked():
    asked = {"message": "Hi mate, would you take £210 as it's in good condition?"}
    said = {"message": "Hi mate, is this still available? I can pay £210 as it's in good condition."}
    result = draft_message(LISTING, local=FakeModel("gemma3:4b", asked), api=FakeModel("claude-haiku-5-5", said),
                           kind="more", mention=True)
    assert (result["status"], result["offer"], result["point"]) == ("ready", 21000, ["Good condition"])
    assert result["attempts"][0]["problems"] == [
        "an offer over the asking price must be said, not asked: \"would you take\" reads like asking for a discount"]


def test_a_flawed_item_is_never_praised_for_paying_more():
    praise = {"message": "Hi mate, I can pay £210 as it's in good condition."}
    result = draft_message(BROKEN, local=FakeModel("gemma3:4b", praise), kind="more")
    assert result["point"] == [] and result["status"] == "needs you"
    assert result["attempts"][0]["problems"] == [
        "the message talks about the condition, but this draft leaves that out",
        "the message says things about the condition the listing doesn't: good"]
