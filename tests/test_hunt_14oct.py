"""14 Oct hunt: bugs in how a message is written in your style, found by five hunters after the owner's "...on the
spot. 😊 Many thanks! 😊" (each test names its bug). Messages are the style setup's six listings, in order."""
import pytest

from flip.checks import check_no_invented_numbers
from flip.message_drafter import draft_message, in_your_case
from flip.style import own_tail, signed_part, signed_with, style_card, unsigned
from flip.writer import after_price, point_in_closing, split_end, with_reason

SETUP = [("iPhone 13 128GB, cracked back", "220", "facebook"), ("PS5 Disc Edition + 2 pads", "300", "facebook"),
         ("AirPods Pro 2", "120", "ebay"), ("iPhone 12 64GB, scratches", "140", "gumtree"),
         ("MacBook Air M1 8GB", "450", "facebook"), ("Dyson V11 Absolute", "180", "facebook")]
CRACK = {"about": "flaw", "says": ["Small crack on the back"]}
LISTING = {"title": "iPhone 14 128GB", "description": "Small crack on the back glass. Works perfectly. Collection from "
           "Leeds LS6.", "asking_price": "300", "marketplace": "facebook"}
MINT = {"title": "PS5 Slim Disc", "description": "Like new, boxed with one controller. Collect from Bradford BD1.",
        "asking_price": "350", "marketplace": "facebook"}


def card_of(texts):
    return style_card([{"listing_title": t, "asking_price": p, "marketplace": m, "my_message": x}
                       for (t, p, m), x in zip(SETUP, texts)])


def reading(flaws=(), pickup=""):
    return {"flaws": list(flaws), "quotes": list(flaws), "pickup": pickup, "no_offers": "", "read_by": "code",
            "attempts": [], "reasons": []}


def drafted(listing, card, kind="lower", mention=None, flaws=(), pickup=""):
    offer = {"lower": int(int(listing["asking_price"]) * 0.85) * 100, "asking": int(listing["asking_price"]) * 100,
             "more": int(listing["asking_price"]) * 100 + 2000}[kind]
    result = draft_message(listing, card, None, None, None, "local", None, kind=kind, mention=mention,
                           writer="template", offer=offer, reading=reading(flaws, pickup))
    return (result["answer"] or {}).get("message")


# ── 1, 2: a sign-off is said once, whatever emoji it comes with, and another sign-off of yours gives way to it ──

@pytest.mark.parametrize("text, sign_off, signed", [
    ("...on the spot. Many thanks! 🙏", "Many thanks! 😊", "...on the spot. Many thanks! 😊"),
    ("Hi, would you take £340? 😊 Cheers, Sam", "Cheers, Sam", "Hi, would you take £340? 😊 Cheers, Sam"),
    ("Hi, would you take £340? 🙏 Thanks 😊", "Thanks 😊", "Hi, would you take £340? 🙏 Thanks 😊"),
    ("Can collect today. Thanks a lot", "Cheers, Sam", "Can collect today. Cheers, Sam"),
    ("Can collect today. Many thanks", "Thanks, Dan", "Can collect today. Thanks, Dan"),
    ("Can collect today. Kind regards", "Thanks, Dan", "Can collect today. Thanks, Dan"),
    ("Can collect today, cheers mate", "Thanks, Dan", "Can collect today. Thanks, Dan"),
    ("Would you take £100? Best offer.", "Thanks, Dan", "Would you take £100? Best offer. Thanks, Dan"),  # no sign-off
])
def test_the_sign_off_is_said_once(text, sign_off, signed):
    assert signed_with(text, sign_off) == signed


def test_the_signature_is_counted_by_its_words():
    card = card_of(["Hi, would you take £185 given the cracked back? I can collect this evening. Many thanks! 😊",
                    "Hi, would you take £255? I can collect this evening. Many thanks! 🙏",
                    "Hi, would you take £100? Many thanks! 😊",
                    "Hi, would you take £115? I can collect this evening. Many thanks! 🙏",
                    "Hi, I'll pay the full £450. I can collect this evening. Many thanks! 😊",
                    "Hi, I'll pay £190 if you hold it. I can collect this evening. Many thanks! 😊"])
    assert card["signature"] == "Many thanks! 😊" and card["phrases"]["closing_lower"] == "I can collect this evening."
    assert drafted(LISTING, card, mention=False).endswith("I can collect this evening. Many thanks! 😊")
    assert unsigned("I can collect this evening. Many thanks! 🙏", "Many thanks! 😊") == "I can collect this evening."


def test_signed_part_is_only_a_last_part_that_signs_off():
    assert signed_part("Can collect today, thanks a lot") == len("Can collect today, ")
    assert signed_part("Can collect today. Cheers mate, Sam") == len("Can collect today. ")
    assert signed_part("Thanks for your time") is None and signed_part("Would you take £100? Best offer.") is None
    assert own_tail("Would you take £300 for the iPhone X?", "sam :), cheers") is None


# ── 7: a sign-off typed in your offer sentence comes once, after the reason; a question keeps its "?" ──

@pytest.mark.parametrize("texts, lower, plain", [
    (["Hi, would you take £185 given the cracked back, cheers Dan", "Hi, would you take £255, cheers Dan",
      "Hi, would you take £100, cheers Dan", "Hi, would you take £115 given the scratches, cheers Dan",
      "Hi, I can pay £450, cheers Dan", "Hi, I can pay £190 if you hold it for me, cheers Dan"],
     "Hi, would you take £255, given the small crack on the back glass? cheers Dan", "Hi, would you take £297? cheers Dan"),
    (["Hi, would you take £185 given the cracked back… Thanks, Dan", "Hi, would you take £255… Thanks, Dan",
      "Hi, would you take £100… Thanks, Dan", "Hi, would you take £115 given the scratches… Thanks, Dan",
      "Hi, I can pay £450… Thanks, Dan", "Hi, I can pay £190 if you hold it for me… Thanks, Dan"],
     "Hi, would you take £255, given the small crack on the back glass… Thanks, Dan", "Hi, would you take £297… Thanks, Dan"),
])
def test_a_sign_off_in_the_offer_sentence_comes_once(texts, lower, plain):
    card = card_of(texts)
    assert drafted(LISTING, card, mention=True, flaws=["Small crack on the back glass"]) == lower
    assert drafted(MINT, card) == plain


# ── 14: your sign-off as you typed it: never shortened, and your name keeps its capital ──

def test_your_sign_off_is_never_shortened_nor_lowered():
    shortcut = {"phrases": {}, "shortcuts": {"you": "u"}}
    assert in_your_case({"message": "Hi, would you take £295? Thank you."}, shortcut)["message"] == \
        "Hi, would u take £295? Thank you."
    lower = {"phrases": {}, "lowercase": True, "signature": "cheers, Dan"}
    assert in_your_case({"message": "Hi, would you take £295? Can collect today."}, lower, kind="lower")["message"] == \
        "hi, would you take £295? can collect today. cheers, Dan"


# ── 5, 26: a closing made of your parts says each thing once, and never splits your sign-off ──

def test_a_closing_of_parts_says_collecting_once():
    card = card_of(["Hi, would you take £185? I can collect this evening. Thanks", "Hi, would you take £255? Can pick up "
                    "today. Cheers", "Hi, would you take £100? I can collect this evening. Ta",
                    "Hi, would you take £115? Can pick up today. Thank you", "Hi, I'll pay £450. Cheers mate",
                    "Hi, I'll pay £190 if you hold it. Many thanks"])
    assert card["phrases"]["closing_lower"] in ("I can collect this evening.", "Can pick up today.")


@pytest.mark.parametrize("sign_off", ["Cheers mate, Sam", "Thanks, Jess x"])
def test_offer_more_keeps_the_sign_off_whole(sign_off):
    card = card_of([f"Hi, would you take £185? Can collect tonight. {sign_off}",
                    f"Hi, would you take £255? Can collect tonight. {sign_off}", f"Hi, would you take £100? {sign_off}",
                    f"Hi, would you take £115? Can collect tonight. {sign_off}",
                    f"Hi, I'll pay £450. Can collect tonight. {sign_off}",
                    f"Hi, I can pay £190 if you hold it for me. {sign_off}"])
    assert drafted(LISTING, card, kind="more").endswith(sign_off)


# ── 9, 10, 12, 32: where the reason goes, and the marks around it ──

@pytest.mark.parametrize("sentence, said", [
    ("Would you take £[OFFER]??", "Would you take £[OFFER], given the small crack on the back??"),
    ("Would you take £[OFFER]?!", "Would you take £[OFFER], given the small crack on the back?!"),
    ("Would you take £[OFFER] ?", "Would you take £[OFFER], given the small crack on the back?"),
    ("Would you take £[OFFER]... 😊", "Would you take £[OFFER], given the small crack on the back... 😊"),
    ("Would you take £[OFFER] cash, can collect tonight?",
     "Would you take £[OFFER] cash, given the small crack on the back, can collect tonight?"),
    ("Would you take £[OFFER] or is that too cheeky?",
     "Would you take £[OFFER], given the small crack on the back, or is that too cheeky?"),
])
def test_the_reason_goes_after_the_price_with_your_marks_at_the_end(sentence, said):
    assert with_reason(sentence, "lower", CRACK) == said


def test_split_end_and_after_price():
    assert split_end("Would you take £[OFFER]?? 😊") == ("Would you take £[OFFER]", "??", "😊")
    assert split_end("I can pay £[OFFER]…") == ("I can pay £[OFFER]", "…", "")
    assert after_price("Would you take £[OFFER] if I collect", ", given X") == "Would you take £[OFFER], given X, if I collect"


def test_trailing_dots_end_a_statement_too():
    card = card_of(["Hi mate, would you take £185... Can collect today", "Hi mate, would you take £255... Can collect today",
                    "Hi mate, would you take £100... Can collect today", "Hi mate, would you take £115... Can collect today",
                    "Hi mate, I can pay £450... Can collect today", "Hi mate, I can pay £190 if you hold it... Can collect today"])
    for kind in ("asking", "more"):
        message = drafted(MINT, card, kind=kind)
        assert ". ..." not in message and "? ..." not in message, message


# ── 19, 31, 33: your own reason takes the listing's flaw, once ──

def test_offer_more_says_the_flaw_once():
    closing, point = point_in_closing("Don't mind the condition.", "more", CRACK)
    assert (closing, point) == ("Don't mind the small crack on the back.", None)


@pytest.mark.parametrize("closing, flawed", [
    ("I'm offering that because of the condition. Can collect today.",
     "I'm offering that because of the small crack on the back. Can collect today."),
    ("It's just because of the condition. Can collect today.",
     "It's just because of the small crack on the back. Can collect today."),
])
def test_your_reason_in_a_closing_sentence_takes_the_flaw_or_goes(closing, flawed):
    assert point_in_closing(closing, "lower", CRACK) == (flawed, None)
    assert point_in_closing(closing, "lower", None) == ("Can collect today.", None)


# ── 34: a number of yours stays yours once the reason goes in ──

def test_your_own_number_is_yours_in_a_sentence_the_reason_went_into():
    own = ["Hi, would you take £185, can be there in 20 mins?"]
    text = "Hi, would you take £255, given the small crack on the back, can be there in 20 mins?"
    assert check_no_invented_numbers("message", text, "£255", own) == []
    assert check_no_invented_numbers("message", "I finish work at 6pm.", "£255", ["Can collect after 6pm."])


# ── 3, 8, 25: saying you like the item, or naming a kind of item, is never a habit for every listing ──

@pytest.mark.parametrize("liked", ["I like the phone.", "Love the phone!", "I like your phone."])
def test_liking_the_phone_isnt_learned_for_a_ps5(liked):
    card = card_of([f"Hi, would you take £{p}? {liked} Can collect today." for p in (185, 255, 100, 115, 450, 190)])
    assert "phone" not in drafted(MINT, card)
    assert "phone" not in drafted(MINT, {**card, "likes": None})  # removing your likes removes them all


def test_for_ur_phone_is_the_item_named():
    card = card_of([f"would u take £{p} for ur phone? Can collect tonight." for p in (185, 255, 100, 115, 450, 190)])
    assert card["phrases"]["offer"] == "would u take £[OFFER]?"


# ── 23: the item's name is a word that names it ──

@pytest.mark.parametrize("title, name", [("Space Grey MacBook Pro 14", "MacBook"), ("White AirPods Pro 2", "AirPods"),
                                         ("Grade A iPad Air 5", "iPad"), ("Brand new sealed PS5", "PS5"),
                                         ("Kids Nintendo Switch Lite", "Switch"), ("Large Dyson V15 Detect", "Dyson")])
def test_i_like_the_item_names_the_item(title, name):
    from flip.message_drafter import liked_name
    assert liked_name({"item_naming": {"all": "family"}}, None, title) == name


def test_buds_and_tabs_arent_phones():
    from flip.style import item_kind
    assert item_kind("Samsung Galaxy Buds2 Pro") == "headphones" and item_kind("Galaxy Tab S9 128GB") == "tablet"
    assert item_kind("Samsung Galaxy S23") == "phone"


# ── 16, 28, 29, 30: a style the checks would refuse on every listing still gets a message ──

@pytest.mark.parametrize("closing", ["Can collect and pay straight away.", "I'm local so can collect today.",
                                     "Can collect at 6 or 7.", "Battery health?", "Is it unlocked?",
                                     "What's the battery health? Is it unlocked?"])
def test_your_usual_closing_never_stops_the_message(closing):
    card = card_of([f"Hi mate, would you take £{p}? {closing}" for p in (185, 255, 100, 115)] +
                   [f"Hi mate, I'll pay £{p}. {closing}" for p in (450, 190)])
    listing = {**LISTING, "description": "Unlocked, boxed. Battery health 88%. Small crack on the back glass. "
                                         "Collection from Leeds LS6."}
    for kind in ("lower", "asking", "more"):
        message = drafted(listing, card, kind=kind)
        assert message, (closing, kind)
        assert "unlocked" not in message.lower() and "pay straight away" not in message and "battery" not in message.lower()
