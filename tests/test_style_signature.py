"""3 Oct: three habits the style card missed, in made-up messages: a sign-off with the writer's name and a smiley
before the thanks ("sam :), cheers"), saying you like the item ("I like the ps5"), and whether you give the flaw counted
on the listings that had one."""

import pytest

from flip.message_drafter import draft_message
from flip.style import learned, signature, signed_with, style_card, without

ROWS = [
    ("iPhone 11 64GB, cracked back", "160", "facebook",
     "hiya, would you take £130 given the cracked back . i like the phone a lot . I could pick up tonight . sam :), cheers"),
    ("PS5 Digital Edition", "280", "facebook", "Hey, would £240 be ok, I like the ps5 a lot. Happy to bring the money. sam :), cheers."),
    ("Galaxy Buds2 Pro", "90", "ebay", "HEY wOULD £70 BE OK i CAN SEND IT TODAY. i really like it. sam:). cheers"),
    ("Samsung Galaxy S21 128GB, scratches", "150", "gumtree", "Hey, would £120 do. I like the phone . I could come by today. sam:). cheers"),
    ("MacBook Pro M1 13in", "520", "facebook", "Hey, I'll pay the full £520 since I like the macbook. sam:),cheers"),
    ("Dyson V8 Animal", "110", "facebook", "Hey, I can do £120 for it, i really like the dyson . I could come right now. sam :), thanks."),
]
MESSAGES = [{"listing_title": t, "asking_price": p, "marketplace": m, "my_message": text} for t, p, m, text in ROWS]
LISTING = {"title": "iPhone 14 128gb", "description": "Small crack on the back. Collection from Leeds.",
           "asking_price": "200", "marketplace": "facebook"}


def test_the_sign_off_with_your_name_and_a_smiley_is_learned_as_you_write_it_most():
    assert signature(MESSAGES) == "sam :), cheers"


def test_what_isnt_a_sign_off_isnt_learned():
    def card_of(*texts):
        return style_card([{"listing_title": "iPhone 13", "asking_price": "200", "marketplace": "facebook",
                            "my_message": text} for text in texts])
    for texts in (("Would you take £150? Can collect tmr.", "Would you take £140? Can collect tmr."),  # "tmr" is no name
                  ("Would you take £150 given the condition? Thanks", "£140 given the condition? Thanks"),
                  ("Would you take £150? Can collect tonight-ish.", "£140? Can collect tonight-ish."),
                  ("Would you take £150? 👍", "Would you take £140? 👍")):  # a lone emoji is the phrasebook's
        assert "signature" not in card_of(*texts), texts
    assert card_of("Would you take £150? Thanks, Dan", "£140? Can collect. Thanks, Dan")["signature"] == "Thanks, Dan"


def test_saying_you_like_the_item_is_learned_with_the_items_name_left_out():
    card = style_card(MESSAGES)
    assert card["likes"] == "I like the {item}"  # "really" in 2 of 6: not the usual way
    assert style_card(MESSAGES[:1] + [{**MESSAGES[1], "my_message": "Hi, would you take £255?"}]).get("likes") is None


def test_whether_you_give_the_flaw_is_never_learned():
    # 1 of the 2 listings with a flaw (cracked back, scratches) gives it, which once made "Says the flaw" a habit: now
    # it's picked on each message (14 Oct, the owner), and never listed on My style
    card = style_card(MESSAGES)
    assert "condition" not in card["mentions"] and all(r["key"] != "says-flaw" for r in learned(card))


def test_learned_lists_them_and_each_can_be_removed():
    card = style_card(MESSAGES)
    rows = {r["key"]: (r["what"], r["value"]) for r in learned(card)}
    assert rows["likes"] == ("Says you like the item", "I like the [item]")
    assert rows["signature"] == ("Signs off with", "sam :), cheers")
    gone = without(card, {"likes", "signature"})
    assert "likes" not in gone and "signature" not in gone


def test_a_draft_says_you_like_the_item_and_ends_with_your_sign_off():
    card = style_card(MESSAGES)
    result = draft_message(LISTING, card, kind="lower", mention=True, writer="template")
    message = result["answer"]["message"]
    # named as they name a phone: "the phone" (3 Oct), with their sign-off after
    assert result["status"] == "ready" and message.endswith("I like the phone. sam :), cheers"), message
    plain = draft_message(LISTING, without(card, {"likes", "signature"}), kind="lower", mention=True, writer="template")
    assert "sam" not in plain["answer"]["message"] and "I like" not in plain["answer"]["message"]


def test_signed_with_swaps_the_sign_off_a_draft_ends_with_for_yours():
    assert signed_with("Hi, would you take £170? Cheers", "sam :), cheers") == "Hi, would you take £170? sam :), cheers"
    assert signed_with("Hi, would you take £170? I can come and collect", "sam :), cheers") == \
        "Hi, would you take £170? I can come and collect. sam :), cheers"
    assert signed_with("Would you take £300 for the iPhone X?", "sam :), cheers") == \
        "Would you take £300 for the iPhone X? sam :), cheers"  # the item's X stays
    assert signed_with("Hi, £170? sam :), cheers", "sam :), cheers") == "Hi, £170? sam :), cheers"  # once


def test_the_item_is_named_the_way_you_name_that_kind():
    """"the phone" for phones, the title's short name for the rest ("the ps5", "the macbook"), as these messages do."""
    from flip.style import item_naming
    assert item_naming(MESSAGES) == {"all": "family", "phone": "generic"}
    card = style_card(MESSAGES)
    for title, said in (("iPhone 14 128gb", "the phone"), ("PS5 Slim Disc", "the PS5"), ("Sony PlayStation 5", "the PlayStation"),
                        ("MacBook Air M2", "the MacBook"), ("Dyson V15 Detect", "the Dyson")):
        message = draft_message({**LISTING, "title": title}, card, kind="lower", mention=True, writer="template")
        assert f"I like {said}." in message["answer"]["message"], (title, message["answer"]["message"])


@pytest.mark.parametrize("text, sign_off, signed", [
    # 14 Oct, the owner's style test: "...on the spot. 😊 Many thanks! 😊", the habit's 😊 and the sign-off's
    ("I can collect this evening and pay cash on the spot. 😊", "Many thanks! 😊",
     "I can collect this evening and pay cash on the spot. Many thanks! 😊"),
    ("Would you take £100? 😊😊", "Cheers 😊", "Would you take £100? Cheers 😊"),
    ("Can collect today 👍", "Thanks 😊", "Can collect today 👍 Thanks 😊"),  # another emoji is yours: kept
])
def test_a_sign_off_with_an_emoji_brings_it_once(text, sign_off, signed):
    from flip.style import signed_with
    assert signed_with(text, sign_off) == signed
