"""The message drafter, tested with pretend models and a pretend embedder: the
offer comes from code, the examples come from your most similar listings
(with their old prices hidden), your style decides whether the listing's flaw
or good condition goes in, and the checks decide."""

from pathlib import Path

from flip.ai import Reply
import pytest

from flip.message_drafter import draft_message, item_name, longer_words
from flip.offers import point_for
from flip.prompts import message_prompt
from flip.retrieval import MessageIndex
from flip.style import describe, load_messages, style_card, without, without_prices
from tests.fakes import FakeModel, fake_embed

ROOT = Path(__file__).resolve().parent.parent
PAST = load_messages(ROOT / "testset" / "messages.example.csv")
LISTING = {"id": "l1", "title": "iPhone 13 128GB Blue unlocked", "description": "Good condition, boxed.",
           "asking_price": "200", "marketplace": "facebook"}
BROKEN = {**LISTING, "description": "Broken back but everything works."}
GOOD = {"message": "Hi mate, is this still available? Would you take £170 cash? Can collect today."}
WITH_FLAW = {"message": "Hi mate, would you take £170 as the back is broken? Can collect today."}
LONG = {"message": "Hi mate, is this still available? Would you do £170 cash? Can collect today or whenever suits you. "
                   "What's the battery health? And does it come with a charger? Cheers"}
LONG_WITH_FLAW = {"message": "Hi mate, is this still available? Would you take £170 as the back is broken? Can "
                             "collect today or whenever suits you. Does it come with a charger and the box? Cheers"}
# a reseller whose messages usually mention the condition, and vary
TALKER = [{"my_message": "Hi mate, would you take £150 as the screen's cracked? Can collect today."},
          {"my_message": "Hi mate, any scratches? Would you take £90? Can collect tonight."}]


def ai_draft(*args, **kwargs):
    """The AI writer, whatever your past messages: these tests are about what it's asked and how it's checked."""
    return draft_message(*args, writer="ai", **kwargs)


def index(tmp_path):
    found = MessageIndex(tmp_path / "chroma", embed=fake_embed)
    found.add(PAST)
    return found


# ── your style ──────────────────────────────────────────────────────────────

def test_your_style_card_is_worked_out_by_code():
    assert describe(style_card(PAST)) == ['Opens with "Hi mate"', "About 12 words", "Usually asks 2 questions",
                                          "No emojis", "Usually mentions: collecting, cash, today",
                                          'Usually starts with "Hi mate, is this still available?"',
                                          'Usually ends with "Can collect today."']
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
    result = ai_draft(LISTING, style_card(PAST), index(tmp_path), FakeModel("gemma3:4b", GOOD), api)
    assert (result["status"], result["offer"], result["answer"]) == ("ready", 17000, GOOD)
    assert api.asked == []
    assert result["examples"][0] == "m1"


def test_a_wrong_price_gets_one_try_on_the_api():
    wrong = {"message": "Hi mate, would you take £160?"}
    result = ai_draft(LISTING, style_card(PAST), local=FakeModel("gemma3:4b", wrong, wrong),
                      api=FakeModel("claude-haiku-5-5", GOOD))
    assert result["status"] == "ready"
    assert "the message must offer exactly £170.00 and no other price" in result["attempts"][0]["problems"]


def test_contact_details_or_paying_off_the_platform_fail():
    phone = {"message": "Hi mate, would you take £170? Text me on 07700 900123."}
    transfer = {"message": "Hi mate, would you take £170? I can pay by bank transfer."}
    result = ai_draft(LISTING, local=FakeModel("gemma3:4b", phone, phone), api=FakeModel("claude-haiku-5-5", transfer))
    assert (result["status"], result["reasons"]) == ("needs you", ["no answer passed the checks"])


def test_nothing_goes_to_the_api_when_the_local_model_isnt_running():
    down = Reply("gemma3:4b", error="the local model isn't running (connection refused)", reachable=False)
    api = FakeModel("claude-haiku-5-5", GOOD)
    result = ai_draft(LISTING, local=FakeModel("gemma3:4b", down), api=api)
    assert api.asked == [] and result["status"] == "needs you"


# ── the kind of offer, and the listing's flaw or good condition ────────────

def test_the_flaw_goes_in_by_itself_when_your_messages_usually_mention_condition():
    local = FakeModel("gemma3:4b", WITH_FLAW)
    result = ai_draft(BROKEN, style_card(TALKER), local=local)
    assert (result["status"], result["point"], result["mentioned"], result["ask"]) == \
        ("ready", ["Broken back"], True, None)
    assert 'as the reason for the offer: "Broken back"' in local.asked[0]["user"]


def test_otherwise_the_draft_leaves_it_out_and_asks_you():
    result = ai_draft(BROKEN, style_card(PAST), local=FakeModel("gemma3:4b", GOOD))
    assert (result["status"], result["mentioned"]) == ("ready", False)
    assert result["ask"] == 'The listing says "Broken back". Mention it as the reason for your offer?'
    # you say yes: drafted again with it, and nothing more to ask
    again = ai_draft(BROKEN, style_card(PAST), local=FakeModel("gemma3:4b", WITH_FLAW), mention=True)
    assert (again["status"], again["mentioned"], again["ask"]) == ("ready", True, None)
    # you said no: it stays out, and you aren't asked again
    assert ai_draft(BROKEN, local=FakeModel("gemma3:4b", GOOD), mention=False)["ask"] is None


def test_a_draft_that_leaves_out_the_flaw_you_said_yes_to_fails():
    result = ai_draft(BROKEN, style_card(PAST), local=FakeModel("gemma3:4b", GOOD, GOOD),
                      api=FakeModel("claude-haiku-5-5", WITH_FLAW), mention=True)
    assert result["attempts"][0]["problems"] == ['the message leaves out what the listing says: "Broken back"']
    assert result["status"] == "ready"


def test_an_offer_at_the_asking_price_says_you_dont_mind_the_flaw():
    happy = {"message": "Hi, is this still available? I don't mind the broken back, happy to pay £200 cash and I can "
                        "come and collect."}
    result = ai_draft(BROKEN, local=FakeModel("gemma3:4b", happy), kind="asking", mention=True)
    assert (result["status"], result["offer"]) == ("ready", 20000)


def test_paying_more_gives_the_good_condition_and_is_said_never_asked():
    asked = {"message": "Hi mate, would you take £210 cash as it's in good condition? I can come and collect."}
    said = {"message": "Hi, is this still available? I can pay £210 cash as it's in good condition, and I can come "
                       "and collect."}
    result = ai_draft(LISTING, local=FakeModel("gemma3:4b", asked, asked), api=FakeModel("claude-haiku-5-5", said),
                      kind="more", mention=True)
    assert (result["status"], result["offer"], result["point"]) == ("ready", 21000, ["Good condition"])
    assert result["attempts"][0]["problems"] == [
        "an offer over the asking price must be said, not asked: \"would you take\" reads like asking for a discount"]


def test_a_flawed_item_is_never_praised_for_paying_more():
    praise = {"message": "Hi mate, I can pay £210 cash as it's in good condition. I can come and collect."}
    result = ai_draft(BROKEN, local=FakeModel("gemma3:4b", praise, praise), kind="more")
    assert result["point"] == [] and result["status"] == "needs you"
    assert result["attempts"][0]["problems"] == [
        "the message talks about the condition, but this draft leaves that out",
        "the message says things about the condition the listing doesn't: good",
        "an offer over asking says why: that it's if they'll hold it for you"]


# ── a longer message ────────────────────────────────────────────────────────

def test_longer_is_about_twice_the_usual_at_least_30_words_and_at_most_70():
    assert [longer_words(words) for words in (5, 12, 20, 35, 50)] == [30, 30, 40, 70, 70]


def test_a_longer_draft_says_more_with_the_questions_the_listing_doesnt_answer():
    local = FakeModel("gemma3:4b", LONG)
    result = ai_draft(BROKEN, style_card(PAST), local=local, length="longer")
    assert (result["status"], result["length"], result["words"]) == ("ready", "longer", 30)  # usual 12 -> 30
    assert result["questions"] == ["What's the battery health?", "Does it come with a charger?",
                                   "Does it come with the box?"]
    user = local.asked[0]["user"]
    assert "Length: about 30 words, longer than usual" in user
    assert "What's the battery health? Does it come with a charger? Does it come with the box?" in user
    assert "About 30 words" in user and "About 12 words" not in user  # the usual length gives way


def test_a_longer_draft_that_isnt_longer_gets_one_try_on_the_api():
    result = ai_draft(LISTING, style_card(PAST), local=FakeModel("gemma3:4b", GOOD, GOOD),
                      api=FakeModel("claude-haiku-5-5", LONG), length="longer")
    assert result["attempts"][0]["problems"] == ["the message is 14 words, but a longer one needs at least 20"]
    assert result["status"] == "ready"


def test_a_longer_draft_can_start_from_the_one_on_screen():
    on_screen = "Hi mate, is this still available? Would you take £170 cash? Can collect today or tomorrow, whenever."
    local = FakeModel("gemma3:4b", {"message": LONG["message"] + " Could collect tomorrow evening too if easier."})
    result = ai_draft(LISTING, style_card(PAST), local=local, length="longer", previous=on_screen)
    assert result["words"] == 34  # its 17 words, not the style's 12: twice that
    assert result["status"] == "ready"
    assert "Their previous draft, to make longer (keep its wording and everything it says): " + on_screen \
        in local.asked[0]["user"]


def test_longer_means_longer_than_the_draft_on_screen():
    on_screen = " ".join(["word"] * 60)  # 60 words: aim 70, and fewer than 61 isn't longer
    result = ai_draft(LISTING, style_card(PAST), local=FakeModel("gemma3:4b", LONG, LONG), length="longer",
                      previous=on_screen)
    assert result["attempts"][0]["problems"][0] == "the message is 30 words, but a longer one needs at least 61"
    # a draft already at the longest asks no AI at all
    longest = ai_draft(LISTING, local=FakeModel("gemma3:4b"), length="longer", previous=" ".join(["word"] * 70))
    assert (longest["status"], longest["reasons"], longest["attempts"]) == \
        ("needs you", ["the draft is already as long as a message goes (70 words)"], [])


def test_a_blank_draft_on_screen_counts_as_none():
    local = FakeModel("gemma3:4b", LONG)
    result = ai_draft(LISTING, style_card(PAST), local=local, length="longer", previous="   ")
    assert result["words"] == 30 and "previous draft" not in local.asked[0]["user"]


def test_a_longer_draft_for_a_listing_the_catalogue_doesnt_know_asks_the_general_questions():
    for title in ("PS5 console", "Samsung fridge freezer", ""):
        listing = {**LISTING, "title": title, "description": "Selling as upgraded."}
        result = ai_draft(listing, style_card(PAST), local=FakeModel("gemma3:4b", LONG), length="longer")
        assert result["questions"] == ["Any marks or scratches?", "Does it come with the box?"], title


def test_a_longer_draft_mustnt_ask_what_the_listing_already_says():
    asks_again = {"message": "Hi mate, is this still available? Would you do £170 cash? Can collect today or whenever "
                             "suits you. Is it unlocked? Does it come with the box? Cheers"}
    result = ai_draft(LISTING, style_card(PAST), local=FakeModel("gemma3:4b", asks_again, asks_again),
                      api=FakeModel("claude-haiku-5-5", LONG), length="longer")
    assert result["attempts"][0]["problems"] == ["the message asks what the listing already says: box, unlocked"]
    assert result["status"] == "ready"


def test_the_draft_on_screen_settles_the_flaw_the_way_it_was_drafted():
    kept = ai_draft(BROKEN, style_card(PAST), local=FakeModel("gemma3:4b", LONG_WITH_FLAW),
                    length="longer", previous=WITH_FLAW["message"])
    assert (kept["status"], kept["mentioned"], kept["ask"]) == ("ready", True, None)
    left = ai_draft(BROKEN, style_card(PAST), local=FakeModel("gemma3:4b", LONG),
                    length="longer", previous=GOOD["message"])
    assert (left["status"], left["mentioned"]) == ("ready", False)
    assert left["ask"] == 'The listing says "Broken back". Mention it as the reason for your offer?'


def test_a_usual_draft_ignores_a_previous_one_and_asks_nothing_extra():
    local = FakeModel("gemma3:4b", GOOD)
    result = ai_draft(LISTING, style_card(PAST), local=local, previous="anything")
    assert (result["words"], result["questions"]) == (None, [])
    assert "Length:" not in local.asked[0]["user"] and "previous draft" not in local.asked[0]["user"]


def test_an_unknown_length_or_writer_is_refused():
    with pytest.raises(ValueError):
        draft_message(LISTING, length="essay")
    with pytest.raises(ValueError):
        draft_message(LISTING, writer="poet")


# ── who writes ──────────────────────────────────────────────────────────────

# a reseller whose messages vary, and never collect or say cash
QUIET = style_card([{"my_message": "Hiya, would £90 do? 😊"}, {"my_message": "Hey! Could you do £120?"}])


def test_messages_that_repeat_are_written_without_ai():
    local = FakeModel("gemma3:4b")
    result = draft_message(LISTING, style_card(PAST), local=local)
    assert (result["status"], result["writer"], local.asked) == ("ready", "template", [])
    assert result["answer"]["message"] == "Hi mate, is this still available? Would you take £170 cash? Can collect today."
    assert [(a["model"], a["problems"], a["cost_pence"]) for a in result["attempts"]] == [("template", [], 0)]


def test_with_no_past_messages_alertflips_message_is_used():
    result = draft_message(LISTING, local=FakeModel("gemma3:4b"))
    assert (result["writer"], result["answer"]["message"]) == \
        ("template", "Hi, would you take £170 cash for it? I can come and collect.")
    posted = draft_message({**LISTING, "marketplace": "ebay"}, local=FakeModel("gemma3:4b"))
    assert posted["answer"]["message"] == "Hi, would you take £170 for it?"


def test_with_no_past_messages_a_lower_offer_gives_the_low_battery_as_its_reason():
    """Like the iPhone 14 Pro AlertFlip wrote for (12 Sep), whose listing gives "Battery Health: 80%" (made up here)."""
    listing = {"id": "b80", "title": "iPhone 14 Pro – 128GB – Silver", "asking_price": "250", "marketplace": "facebook",
               "description": "Great condition | Box & cable included\nLooked after, no scratches, scuffs or visible "
                              "damage.\n✅ Battery Health: 80%\n✅ Unlocked"}
    drafts = {kind: draft_message(listing, kind=kind, offer=offer)["answer"]["message"]
              for kind, offer in (("lower", 23500), ("asking", 25000), ("more", 26500))}
    assert drafts == {
        "lower": "Hi, would you take £235 cash for it? I'm offering that because the battery health is 80%. "
                 "I can come and collect.",
        "asking": "Hi, is this still available? I'll pay the full £250 cash and can come and collect. "
                  "Could you hold it for me?",
        "more": "Hi, I'll pay £265 cash if you take the listing down and sell it to me. I can come and collect."}
    # 86% and up isn't a reason, and nor is the battery of a phone your style doesn't mention condition for
    high = {**listing, "description": listing["description"].replace("80%", "90%")}
    assert draft_message(high, kind="lower", offer=23500)["point"] == []
    assert draft_message(listing, style_card(PAST), kind="lower", offer=23500)["mentioned"] is False


def test_a_replaced_battery_is_the_reason_whoever_replaced_it():
    """The rule of 23 Sep: a battery that's been replaced is always a flaw, even by Apple. Made up here."""
    listing = {"id": "r1", "title": "iPhone 12 64GB Black", "asking_price": "200", "marketplace": "facebook",
               "description": "Battery replaced by Apple last year, works perfectly."}
    assert draft_message(listing, kind="lower", offer=18000)["answer"]["message"] == \
        "Hi, would you take £180 cash for it? I'm offering that because the battery has been replaced. " \
        "I can come and collect."


def test_a_lower_offer_gives_the_flaw_and_the_low_battery_together():
    """A low battery is a flaw like the others (the line set on 23 Sep: 85% or under), made up here."""
    listing = {"id": "c79", "title": "iPhone 13 128GB Midnight", "asking_price": "250", "marketplace": "facebook",
               "description": "Cracked back, works fine.\nBattery health 79%"}
    assert draft_message(listing, kind="lower", offer=23500)["answer"]["message"] == \
        "Hi, would you take £235 cash for it? I'm offering that because of the cracked back and because the " \
        "battery health is 79%. I can come and collect."


def test_messages_that_vary_are_written_by_your_own_sentences_first():
    """26 Sep: your sentences first for every style, not only styles that repeat (94 of 98 fresh drafts sendable in
    the blind review, against 86); the AI writes when you choose it, or when they can't say this one."""
    local = FakeModel("gemma3:4b", WITH_FLAW)
    result = draft_message(BROKEN, style_card(TALKER), local=local)
    assert (result["writer"], len(local.asked)) == ("template", 0)
    assert result["answer"]["message"] == "Hi mate, would you take £170 for it, given the broken back? Can collect."
    chosen = draft_message(BROKEN, style_card(TALKER), local=FakeModel("gemma3:4b", WITH_FLAW), writer="ai")
    assert chosen["writer"] == "gemma3:4b"


def test_when_the_message_without_ai_fails_a_check_the_ai_gets_its_turn(monkeypatch):
    monkeypatch.setattr("flip.message_drafter.write_offer", lambda *args, **kwargs: "Hi mate, would you take £160?")
    result = draft_message(LISTING, style_card(PAST), local=FakeModel("gemma3:4b", GOOD))
    assert [a["model"] for a in result["attempts"]] == ["template", "gemma3:4b"]
    assert "the message must offer exactly £170.00 and no other price" in result["attempts"][0]["problems"]
    assert (result["status"], result["writer"], result["reasons"]) == ("ready", "gemma3:4b", [])
    # told to write without AI, it asks no AI: the draft is yours to look at
    only = draft_message(LISTING, style_card(PAST), local=FakeModel("gemma3:4b"), writer="template")
    assert (only["status"], only["reasons"]) == ("needs you", ["No AI writing's message didn't pass the checks"])


def test_a_message_never_promises_collecting_or_cash_your_messages_dont(tmp_path):
    promise = {"message": "Hiya, would you take £170? I can arrange collection quickly."}
    result = ai_draft(LISTING, QUIET, local=FakeModel("gemma3:4b", promise, promise),
                      api=FakeModel("claude-haiku-5-5", {"message": "Hiya, would you take £170? 😊"}))
    assert result["attempts"][0]["problems"] == ["the message promises collecting, which your own messages don't"]
    assert result["status"] == "ready"
    # an example message of yours that collects makes it yours to say
    shown = ai_draft(LISTING, QUIET, index(tmp_path), local=FakeModel("gemma3:4b", promise, promise))
    assert shown["status"] == "ready"


# ── what the listing's reading adds ─────────────────────────────────────────

READ = {"flaws": ["Black dot on the screen"], "pickup": "Leeds LS6", "no_offers": "Price is firm, no offers",
        "read_by": "gemma3:4b"}
DOTTED = {**LISTING, "description": "Black dot on the screen, doesn't affect use. Collection only from Leeds LS6. "
                                    "Price is firm, no offers."}


def test_a_flaw_only_ai_read_goes_in_and_no_offers_is_a_note_not_a_new_offer():
    result = draft_message(DOTTED, style_card(PAST), mention=True, reading=READ)
    # your messages never say where you collect from, so neither does this one (26 Sep review)
    assert result["answer"]["message"] == "Hi mate, is this still available? Would you take £170 cash, given the " \
                                          "black dot on the screen? Can collect today."
    assert result["note"] == 'The seller says: "Price is firm, no offers"'
    assert (result["kind"], result["offer"], result["point"]) == ("lower", 17000, ["Black dot on the screen"])
    assert result["reading"] == READ
    # code alone has no word for the dot, and reads no place
    alone = draft_message(DOTTED, style_card(PAST), mention=True)
    assert alone["point"] == [] and "Leeds" not in alone["answer"]["message"]
    assert alone["note"] == 'The seller says: "Price is firm"'


def test_the_pickup_place_is_only_for_messages_that_collect():
    # with no past messages, AlertFlip's message collects on Facebook, from the listing's place...
    plain = draft_message(DOTTED, mention=True, reading=READ)
    assert plain["writer"] == "template" and plain["answer"]["message"].endswith("I can come and collect from Leeds LS6.")
    # ...and on eBay it's posted
    posted = draft_message({**DOTTED, "marketplace": "ebay"}, mention=True, reading=READ)
    assert posted["writer"] == "template" and "Leeds" not in posted["answer"]["message"]
    local = FakeModel("gemma3:4b", {"message": "Hiya, would you take £170, given the black dot on the screen? 😊"})
    ai_draft(DOTTED, QUIET, local=local, mention=True, reading=READ)
    assert "Pickup:" not in local.asked[0]["user"]
    # ...and with your messages, only if they say where you collect from (26 Sep review: "Can collect from SE1 9CK
    # today" from someone who never names a place read like a form)
    local = FakeModel("gemma3:4b", {"message": "Hi mate, would you take £170 given the black dot? Can collect today."})
    ai_draft(DOTTED, style_card(TALKER), local=local, mention=True, reading=READ)
    assert "Pickup:" not in local.asked[0]["user"]
    placer = style_card([{"my_message": "Hi mate, would you take £150? Can collect today."},
                         {"my_message": "Hi mate, would you take £90? Can collect today."},
                         {"my_message": "Hi mate, would you take £120? Can collect from Bradford tonight."},
                         {"my_message": "Hi mate, would you take £95? Can collect from Leeds today."}])
    local = FakeModel("gemma3:4b", {"message": "Hi mate, would you take £170 given the black dot? Can collect today."})
    ai_draft(DOTTED, placer, local=local, mention=True, reading=READ)
    assert "Pickup: Leeds LS6, where the listing says to collect" in local.asked[0]["user"]
    assert draft_message(DOTTED, placer, mention=True, reading=READ)["answer"]["message"] == \
        "Hi mate, would you take £170, given the black dot on the screen? Can collect from Leeds LS6 today."
    # a house number and street is the seller's door: never said back, whoever writes
    street = {**READ, "pickup": "78 Example Lane"}
    assert draft_message(DOTTED, mention=True, reading=street)["answer"]["message"].endswith("I can come and collect.")


def test_the_item_is_called_by_its_catalogue_name():
    assert item_name("airpods-pro-2", "AirPods Pro 2 USB-C") == "AirPods Pro"
    assert item_name("ps5-slim", "PS5 Slim Disc Edition") == "PlayStation 5 Slim"
    assert item_name(None, "Dyson V11 cordless vacuum") == "Dyson V11 cordless vacuum"



# ── after the 18 Aug review ─────────────────────────────────────────────────

def test_a_phrasebook_habit_never_names_an_item_or_carries_a_second_price():
    iphones = [{"my_message": "Hi mate, is the iPhone still available? Would you take £185?", "listing_title": "iPhone 13"},
               {"my_message": "Hi mate, is the iPhone still available? Would you take £150?", "listing_title": "iPhone 12"}]
    assert style_card(iphones)["phrases"]["opener"] is None
    asking = [{"my_message": "Hi mate, I know you're asking £220 but would you take £185 cash?"},
              {"my_message": "Hi mate, I know you're asking £200 but would you take £170 cash?"}]
    assert style_card(asking)["phrases"]["offer"] is None
    assert without_prices("Would you take £185, cash on collection?") == "Would you take £[OFFER], cash on collection?"


def test_your_own_promises_are_yours_to_make():
    picker = style_card([{"my_message": "Hi mate, would you take £185? Can pick it up today."},
                         {"my_message": "Hi mate, would you take £150? Can pick it up today."}])
    assert picker["promises"] == ["collecting"]
    result = draft_message(LISTING, picker)
    assert (result["status"], result["writer"]) == ("ready", "template")


def test_words_the_writer_cant_say_go_to_the_ai():
    told = {**LISTING, "description": "Cracked the back glass and the lens is chipped too and the frame has a dent"}
    local = FakeModel("gemma3:4b", {"message": "Hi mate, would you take £170 given the damage? Can collect today."})
    result = draft_message(told, style_card(PAST), local=local, mention=True)
    assert result["point"] == ["Cracked the back glass and the lens is"]  # code's reading cuts it there
    assert result["attempts"][0]["problems"] == \
        ["there's no plain wording for what the listing says: Cracked the back glass and the lens is"]
    assert (result["status"], result["writer"]) == ("ready", "gemma3:4b")


def test_a_part_said_with_what_was_done_to_it_is_said_of_the_part():
    """26 Sep: "it has bent the frame at the top" went to the AI, which pasted it back as if the buyer had bent it."""
    told = {**LISTING, "description": "I dropped it and cracked the back."}
    result = draft_message(told, style_card(PAST), local=FakeModel("gemma3:4b"), mention=True)
    assert result["point"] == ["cracked the back"]  # the seller's story, cut to the flaw
    assert (result["writer"], result["answer"]["message"]) == \
        ("template", "Hi mate, is this still available? Would you take £170 cash, given that the back is cracked? "
                     "Can collect today.")


def test_a_message_never_names_another_model():
    local = FakeModel("gemma3:4b", {"message": "Hi mate, would you take £170 for the iPhone 14? Can collect today."}, {"message": "Hi mate, would you take £170 for the iPhone 14? Can collect today."})
    result = ai_draft(LISTING, style_card(PAST), local=local)
    assert "the message names a different item from the listing's" in result["attempts"][0]["problems"]


def test_not_for_parts_is_never_said_to_be_for_parts():
    working = {**LISTING, "description": "Fully working, not spares or repairs."}
    result = draft_message(working, style_card(PAST), mention=True)
    assert result["point"] == [] and "spares" not in result["answer"]["message"]


def test_an_unknown_item_is_named_without_the_sellers_selling_words():
    assert item_name(None, "Bose QC45 headphones *BARGAIN*") == "Bose QC45 headphones"
    assert item_name(None, "Nintendo Switch Lite turquoise FREE DELIVERY") == "Nintendo Switch Lite turquoise"
    assert item_name(None, "Dyson V11 Absolute excellent condition boxed") == "Dyson V11 Absolute"



def test_the_price_you_picked_is_the_price_drafted_and_must_fit_its_kind():
    result = draft_message(LISTING, local=FakeModel("gemma3:4b"), offer=15000)
    assert (result["offer"], result["answer"]["message"]) == \
        (15000, "Hi, would you take £150 cash for it? I can come and collect.")
    for kind, offer in [("lower", 21000), ("more", 19000), ("asking", 19000)]:
        with pytest.raises(ValueError):
            draft_message(LISTING, kind=kind, offer=offer)


def test_a_message_never_collects_from_a_place_the_listing_doesnt_give():
    local = FakeModel("gemma3:4b", {"message": "Hi mate, would you take £170 cash? Can collect from Bradford today."}, {"message": "Hi mate, would you take £170 cash? Can collect from Bradford today."})
    result = ai_draft(LISTING, style_card(PAST), local=local)
    assert "the message says it'll collect from a place the listing doesn't: Bradford" in result["attempts"][0]["problems"]


def test_another_models_name_is_read_one_sentence_at_a_time():
    ok = FakeModel("gemma3:4b", {"message": "Hi mate, would you take £170 cash for the iPhone 13? Plus I can collect today."})
    assert ai_draft(LISTING, style_card(PAST), local=ok)["status"] == "ready"


def test_the_asking_price_said_back_is_never_a_habit():
    said_back = [{"my_message": "Hi mate, is this still available at £220? Any room on price?"},
                 {"my_message": "Hi mate, is this still available at £150? What's your lowest?"}]
    assert style_card(said_back)["phrases"]["offer"] is None


# ── a title and description that name different models ─────────────────────

def test_a_title_and_description_naming_different_models_is_a_warning():
    odd = {**LISTING, "title": "iphone 15 pro max", "description": "iPhone 14 for sale. Few scratches on screen"}
    result = draft_message(odd, style_card(PAST))
    assert result["warnings"] == ["The title says iPhone 15 Pro Max but the description says iPhone 14: "
                                  "check which it is"]
    for fine in ({**odd, "title": "iphone 14"}, {**odd, "description": "Few scratches, fits iPhone 13 cases"},
                 {**odd, "description": "Works perfectly"}):
        assert draft_message(fine, style_card(PAST))["warnings"] == []


# ── Rewrite: the same things in other words ─────────────────────────────────

ON_SCREEN = "Hi mate, is this still available? Would you take £170 cash? Can collect today."
REWORDED = {"message": "Hi mate, would £170 cash work for you? I can collect today."}


def test_a_rewrite_asks_for_other_words_and_refuses_the_same_message():
    local, api = FakeModel("gemma3:4b", {"message": ON_SCREEN}, {"message": ON_SCREEN}), FakeModel("claude-haiku-5-5", REWORDED)
    result = ai_draft(LISTING, style_card(PAST), None, local, api, rewrite_of=ON_SCREEN)
    assert result["attempts"][0]["problems"] == ["it's the message on screen again: a rewrite says it in other words"]
    assert (result["status"], result["answer"], result["writer"]) == ("ready", REWORDED, "claude-haiku-5-5")
    assert local.asked[0]["vary"] is True
    assert local.asked[0]["user"].endswith(f'wants another version of it: "{ON_SCREEN}"\nSay the same things, but word '
                                           f'every sentence differently, the way the reseller might have written it another day.')


def test_a_first_draft_is_the_same_every_time():
    local = FakeModel("gemma3:4b", GOOD)
    ai_draft(LISTING, style_card(PAST), None, local)
    assert local.asked[0]["vary"] is False and "rewrite" not in local.asked[0]["user"]


def test_your_own_sentences_say_it_one_way_so_the_ai_rewords_a_rewrite():
    yours = draft_message(LISTING, style_card(PAST))["answer"]["message"]  # the template's
    local = FakeModel("gemma3:4b", REWORDED)
    result = draft_message(LISTING, style_card(PAST), None, local, rewrite_of=yours)
    assert (result["writer"], result["answer"]) == ("gemma3:4b", REWORDED)


def test_with_no_ai_a_rewrite_gives_your_message_back_and_says_why():
    yours = draft_message(LISTING, style_card(PAST))["answer"]["message"]
    result = draft_message(LISTING, style_card(PAST), writer="template", rewrite_of=yours)
    assert (result["status"], result["answer"]["message"]) == ("ready", yours)
    assert result["warnings"] == ["No AI writing says this one way only: pick the AI writer (Gemma 3 4B) for other words"]


def test_when_no_other_wording_passes_your_own_message_stays():
    yours = draft_message(LISTING, style_card(PAST))["answer"]["message"]
    local, api = FakeModel("gemma3:4b", {"message": yours}, {"message": yours}), FakeModel("claude-haiku-5-5", {"message": yours})
    result = draft_message(LISTING, style_card(PAST), None, local, api, rewrite_of=yours)
    assert (result["status"], result["writer"], result["answer"]["message"], result["reasons"]) == \
        ("ready", "template", yours, [])
    assert result["warnings"] == ["No other wording passed the checks: this is your usual message"]



# ── a question you asked about one listing isn't asked about another ────────

WORKS_FINE = [{"id": "s1", "listing_title": "iphone 15 pro max", "my_message": "Hi, I can pay £400 for it. Does it still "
               "work perfectly fine?"},
              {"id": "s2", "listing_title": "iphone 14 pro", "my_message": "Hi, I can pay £280 for it. Is it still available?"}]
BLUE = {"id": "b", "title": "iphone 13 Blue", "asking_price": "110", "marketplace": "facebook",
        "description": "iPhone 13 blue\n128gb\nUpgraded my phone hence the sale\nOriginal screen\nBattery 91% health"}


class Past:
    """A search that finds the given past messages, nearest first."""
    def __init__(self, messages):
        self.messages = messages

    def similar(self, text, n=3, leave_out=None, deal=None):
        return self.messages[:n]


def test_a_question_asked_about_another_listing_is_never_shown_to_the_ai_or_copied():
    """A real draft (2 Sep): "Does it still work perfectly fine?" from a message about another phone."""
    copied = {"message": "Hi, I can pay £110 for it. Does it still work perfectly fine?"}
    plain = {"message": "Hi, I can pay £110 for it. Is it still available?"}
    local, api = FakeModel("gemma3:4b", copied, copied), FakeModel("claude-haiku-5-5", plain)
    result = ai_draft(BLUE, style_card(WORKS_FINE), Past(WORKS_FINE), local, api, kind="asking")
    assert "perfectly fine" not in local.asked[0]["user"] and "Is it still available?" in local.asked[0]["user"]
    assert result["attempts"][0]["problems"] == [
        'the message asks what you asked about another listing: "does it still work"']
    assert (result["status"], result["answer"]) == ("ready", plain)


def test_a_question_this_listing_or_code_would_ask_is_never_counted_as_copied():
    asked = [{"id": "s1", "listing_title": "PS5", "my_message": "Hi, would you take £300? Does it come with a charger?"}]
    local = FakeModel("gemma3:4b", {"message": "Hi, I can pay £110 for it. Does it come with a charger?"})
    result = ai_draft(BLUE, style_card(asked), Past(asked), local, kind="asking")
    assert result["status"] == "ready"


def test_an_offer_over_asking_says_why():
    over = {"message": "Hi, I can pay £120 cash for it. I can come and collect."}
    held = {"message": "Hi, I can pay £120 cash if you can hold it for me. I can come and collect."}
    result = ai_draft(BLUE, {}, None, FakeModel("gemma3:4b", over, held), kind="more", offer=12000)
    assert result["attempts"][0]["problems"] == ["an offer over asking says why: that it's if they'll hold it for you"]
    assert draft_message(BLUE, {}, kind="more")["answer"]["message"].endswith(
        "if you take the listing down and sell it to me. I can come and collect.")


def test_your_offer_sentence_is_your_style_not_a_question_about_another_listing():
    """A real draft (2 Sep): your own sentences were refused for "for it given the"."""
    mine = [{"id": "s1", "listing_title": "iPhone 13 128GB Blue", "my_message":
             "Hi, would you take £185 for it, given the black dot on the screen? Thanks. Cheers"}]
    faulty = {**BLUE, "description": BLUE["description"].replace("Original screen", "Original screen one issue with "
                                                                  "the screen it turns on and off sometimes")}
    result = draft_message(faulty, {}, Past(mine), kind="lower", mention=True, writer="template")
    assert result["status"] == "ready", result["attempts"]


# ── AlertFlip's rules for the AI ────────────────────────────────────────────

def test_with_no_past_messages_the_ai_is_given_alertflips_rules():
    local = FakeModel("gemma3:4b", {"message": "Hi, would you take £170 cash? I can come and collect."})
    ai_draft(LISTING, local=local)
    user, system = local.asked[0]["user"], local.asked[0]["system"]
    # a lower offer on Facebook: code adds the cash-and-collect sentence, so the AI is told to leave it out
    assert "Buying: don't mention cash, collecting or postage\n" in user  # not why: Gemma copied that (14 Oct)
    assert '- Opens with "Hi"' in user and "- One or two short sentences, under 220 characters" in user
    assert "- At most two questions" in user and "- No emojis and no sign-off" in user
    assert '(none yet). The shape of a good one, not their words: "Hi, would you take £[OFFER] for it?"' in user
    assert user.endswith("- Ask nothing about the item itself.\n- Be one or two short sentences: the greeting and the "
                         "offer.")
    assert "added after" not in user and "added at the end" not in user
    assert "Your message must:\n- Start with \"Hi\".\n- Ask if they'd take £170, under their asking price: " \
           "\"would you take £170 for it?\"" in user
    assert "iCloud" not in system and "I'll pay ... I'll pay" not in system  # not named unless the listing does
    asking = FakeModel("gemma3:4b", {"message": "Hi, is this still available? I can pay £200 cash and come and "
                                                "collect it. Could you hold it for me?"})
    assert ai_draft(LISTING, local=asking, kind="asking")["status"] == "ready"
    assert 'say both in one sentence with the offer, like "I can pay £200 cash and come and collect it"' in \
        asking.asked[0]["user"]
    ebay = FakeModel("gemma3:4b", {"message": "Hi, would you take £170?"})
    assert ai_draft({**LISTING, "marketplace": "ebay"}, local=ebay)["status"] == "ready"
    assert "Buying: don't mention cash, collecting or postage" in ebay.asked[0]["user"]
    assert "- Be two or three short sentences, under 250 characters." in ebay.asked[0]["user"]
    locked = FakeModel("gemma3:4b", {"message": "Hi, would you take £170 cash? I can come and collect."})
    ai_draft({**LISTING, "description": "Good condition, boxed. Signed out of iCloud."}, local=locked)
    assert "Don't ask about iCloud, Find My or locks; you may say what the listing says about them." in \
        locked.asked[0]["system"]


def test_with_your_style_the_ai_buys_the_way_your_messages_do():
    local = FakeModel("gemma3:4b", GOOD)
    ai_draft(LISTING, style_card(PAST), local=local)
    user = local.asked[0]["user"]
    assert "Buying: say it only the way their own messages do: cash, collecting" in user
    assert "Opens with \"Hi\"" not in user and '- Opens with "Hi mate"' in user


def test_gemmas_short_draft_of_31_oct_no_longer_passes():
    """Gemma wrote "I can pay £235" for a lower offer on an iPhone 14 Pro, and the old checks let it through."""
    listing = {**LISTING, "title": "iPhone 14 Pro – 128GB – Silver", "asking_price": "250",
               "description": "Excellent condition, with no scratches, scuffs or visible damage! Battery Health: 80%"}
    short = {"message": "I can pay £235"}
    result = ai_draft(listing, local=FakeModel("gemma3:4b", short, short), offer=23500)
    assert result["status"] == "needs you"
    # since 14 Sep code adds the reason and the cash-and-collect sentence; it still doesn't open with "Hi", and
    # since 26 Sep a lower offer is asked
    assert [a["problems"] for a in result["attempts"]] == [['the message doesn\'t open with "Hi"',
                                                            'a lower offer is said, not asked: "I can pay £235." '
                                                            "(under asking it's a question)"]] * 2
    # and the seller's "no scratches, scuffs or visible damage" is no flaw; the 80% battery is (23 Sep: 85% or under)
    assert result["reading"]["flaws"] == ["Battery Health: 80%"] and result["point"] == ["battery health 80%"]


def test_what_you_removed_from_your_style_is_never_shown_to_the_ai():
    """Gemma copied "cash" from your own examples after you'd removed it (12 Sep): the examples go without it."""
    card = without(style_card(PAST), {"mention:cash"})
    local = FakeModel("gemma3:4b", {"message": "Hi mate, is this still available? Would you take £170? Can collect today."})
    result = draft_message(LISTING, card, Past(PAST[:3]), local)
    assert "the message mentions paying cash, which you removed from your style" in result["attempts"][0]["problems"]
    shown = local.asked[0]["user"].split("Their messages for similar listings:")[1]
    assert "cash" not in shown.lower() and "Would you take £[OFFER]?" in shown
    assert "- Never mentions paying cash" in local.asked[0]["user"]
    assert (result["status"], result["writer"]) == ("ready", "gemma3:4b")


def test_paying_more_says_why_only_when_you_said_yes_to_the_reason():
    quiet = FakeModel("gemma3:4b", {"message": "Hi, I'll pay £210 cash if you take the listing down and sell it to "
                                               "me. I can come and collect."})
    ai_draft(LISTING, local=quiet, kind="more")
    assert "- Doesn't say why they'll pay more" in quiet.asked[0]["user"]
    said = FakeModel("gemma3:4b", {"message": "Hi, I'll pay £210 cash as it's in good condition, if you take the "
                                              "listing down. I can come and collect."})
    ai_draft(LISTING, local=said, kind="more", mention=True)
    assert "Doesn't say why" not in said.asked[0]["user"] and "Condition: give this from the listing" in said.asked[0]["user"]


# ── with no past messages: code's sentences and one free retry (14 Sep 2026) ──

CRACKED = {**LISTING, "title": "iPhone 12 64GB", "description": "Back glass is cracked. Works perfectly. Collection only."}


def test_code_adds_the_reason_and_cash_and_collecting_after_a_lower_offer():
    """The explainer's read of 42 drafts: the AI pasted the seller's words in ("because Faulty HDMI port, no
    picture") and merged cash and collecting into the offer ("£320 cash and come and collect it")."""
    local = FakeModel("gemma3:4b", {"message": "Hi, would you take £170 for it?"})
    result = ai_draft(CRACKED, local=local, offer=17000, mode="local")
    assert (result["status"], result["answer"]["message"]) == (
        "ready", "Hi, would you take £170 for it? I'm offering that because the back glass is cracked. "
                 "I can pay cash and come and collect it.")
    assert "Condition: don't mention it" in local.asked[0]["user"]  # code says it, the AI doesn't
    ebay = ai_draft({**CRACKED, "marketplace": "ebay"}, local=FakeModel("gemma3:4b", {"message": "Hi, would you take "
                                                                                                  "£170 for it?"}),
                    offer=17000, mode="local")
    assert ebay["answer"]["message"] == "Hi, would you take £170 for it? I'm offering that because the back glass is cracked."


def test_a_listing_that_says_no_cash_gets_no_cash_offered():
    """Decided 14 Sep: "mention cash unless the listing description says no cash"."""
    no_cash = {**CRACKED, "description": "Back glass is cracked. Works perfectly. No cash, bank transfer only."}
    local = FakeModel("gemma3:4b", {"message": "Hi, would you take £170 for it?"})
    result = ai_draft(no_cash, local=local, offer=17000, mode="local")
    assert result["answer"]["message"].endswith("I can come and collect it.") and "cash" not in \
        result["answer"]["message"].split("bank")[0].lower()
    assert "the listing says no cash" in local.asked[0]["user"]
    template = draft_message(no_cash, offer=17000, writer="template")
    assert template["answer"]["message"] == ("Hi, would you take £170 for it? I'm offering that because the back glass "
                                             "is cracked. I can come and collect.")
    cash = FakeModel("gemma3:4b", {"message": "Hi, would you take £170 cash? I can come and collect."},
                     {"message": "Hi, would you take £170 cash? I can come and collect."})
    assert "the message offers cash, but the listing says no cash" in \
        ai_draft(no_cash, local=cash, offer=17000, mode="local")["attempts"][0]["problems"]
    yours = draft_message(no_cash, style_card(PAST), offer=17000, writer="template")
    assert "cash" not in yours["answer"]["message"].lower()  # your own "...cash?" comes without it here


def test_code_never_adds_collecting_to_a_message_that_wont_collect():
    drop = {"message": "Hi, would you take £170 for it? Happy for you to drop round with it tonight."}
    result = ai_draft(CRACKED, local=FakeModel("gemma3:4b", drop, drop), offer=17000, mode="local")
    assert "the message doesn't say you'll come and collect: on Facebook and Gumtree it does" in \
        result["attempts"][0]["problems"]


def test_one_free_retry_on_this_mac_before_haiku_told_what_was_turned_down():
    wrong = {"message": "Hi, would you take £160 for it?"}
    local, api = FakeModel("gemma3:4b", wrong, {"message": "Hi, would you take £170 for it?"}), \
        FakeModel("claude-haiku-5-5")
    result = ai_draft(CRACKED, local=local, api=api, offer=17000)
    assert (result["status"], api.asked) == ("ready", [])  # the retry passed: Haiku never asked
    assert [a["model"] for a in result["attempts"]] == ["gemma3:4b", "gemma3:4b"]
    retry = local.asked[1]["user"]
    assert 'Your last try was: "Hi, would you take £160 for it?"' in retry  # its own words, not code's
    assert "It was turned down: the message must offer exactly £170.00 and no other price" in retry
    assert retry.endswith("changing only what was turned down.") and "Code adds" not in retry
    down = Reply("gemma3:4b", error="the local model isn't running (connection refused)", reachable=False)
    local = FakeModel("gemma3:4b", down)
    assert ai_draft(CRACKED, local=local, api=FakeModel("claude-haiku-5-5"), offer=17000)["status"] == "needs you"
    assert len(local.asked) == 1  # nothing to retry when Gemma isn't running


def test_code_sentences_go_right_after_the_offer():
    padded = {"message": "Hi, would you take £170 for it? Just checking that's agreeable. Let me know."}
    result = ai_draft(CRACKED, local=FakeModel("gemma3:4b", padded), offer=17000, mode="local")
    assert result["answer"]["message"] == ("Hi, would you take £170 for it? I'm offering that because the back glass is "
                                           "cracked. I can pay cash and come and collect it. Just checking that's "
                                           "agreeable. Let me know.")
