"""The safety net, tested before any AI exists: hand-written "AI answers",
one good and many bad, each bad one failing for the right reason."""

import pytest

from flip.catalogue import fill_from_catalogue, load_catalogue, load_conditions
from flip.checks import (check_listing_answer, check_message, check_no_unasked_promises, has_fault, numbers_in,
                         offer_asked, promised_in, promises_in, sources_text)

CATALOGUE = load_catalogue()
CONDITIONS = load_conditions()

TITLE = "iPhone 13 128GB unlocked"
DESCRIPTION = "Selling my iPhone, works perfectly, screen protector on since day one. Perfect for gaming."
NOTES = "boxed, battery 87%, light scratch on the back"
ITEM = fill_from_catalogue(TITLE, NOTES, CATALOGUE)
SOURCES = sources_text(TITLE, DESCRIPTION, NOTES, ITEM)

GOOD = {
    "colour": "Midnight",
    "condition_id": "3000",
    "condition_note": "Light scratch on the back. Battery health 87%.",
    "description": "Apple iPhone 13 128GB in Midnight, unlocked, boxed. 5G. Screen has had a protector on "
                   "since day one. Battery health 87%. Perfect for a new owner.",
}


def problems(notes=NOTES, sources=SOURCES, **changes):
    return check_listing_answer({**GOOD, **changes}, ITEM, CATALOGUE, CONDITIONS["phones"], sources, notes)


def test_a_good_answer_passes():
    assert problems() == []


def test_wrong_shape_fails():
    for answer in ({"colour": "Midnight"}, "Midnight, used", {**GOOD, "price": "£300"}):
        assert check_listing_answer(answer, ITEM, CATALOGUE, CONDITIONS["phones"], SOURCES, NOTES) == \
            ["the answer isn't in the agreed shape"]


def test_small_slips_in_spelling_are_fine():
    assert problems(colour="midnight", condition_id=3000) == []


def test_colour_must_be_real_for_the_model():
    assert problems(colour="Black", description="iPhone 13") == ["colour 'Black' isn't one of the allowed values"]


def test_colour_must_agree_with_the_listing_text():
    item = fill_from_catalogue("iPhone 13 128GB Pink unlocked", NOTES, CATALOGUE)
    result = check_listing_answer({**GOOD, "description": "iPhone 13"}, item, CATALOGUE, CONDITIONS["phones"], SOURCES, NOTES)
    assert result == ["colour 'Midnight' disagrees with the listing text ('Pink')"]


def test_condition_must_be_on_ebays_list():
    assert problems(condition_id="2010") == ["condition '2010' isn't one of the allowed values"]  # refurbished


def test_new_condition_needs_your_notes_to_say_new():
    assert problems(condition_id="1000", condition_note="") == \
        ["condition is New, but your notes don't say it's brand new and unopened"]


def test_new_item_has_no_condition_note():
    notes = "brand new sealed, unopened, boxed"
    assert problems(notes=notes, condition_id="1000", condition_note="", description="Boxed iPhone 13, sealed.") == []
    assert problems(notes=notes, condition_id="1000", condition_note="Sealed.", description="Boxed iPhone 13.") == \
        ["condition_note must be empty on a new item: eBay ignores it"]


def test_invented_number_fails():
    assert problems(description="iPhone 13, battery health 90%.") == \
        ["description has numbers that aren't in your inputs: 90"]


def test_numbers_written_as_words_count():
    assert problems(description="iPhone 13 with two cases.") == [
        "description has numbers that aren't in your inputs: 2",
        "description says things your inputs don't: case"]


def test_invented_accessory_fails():
    assert problems(description="iPhone 13 with original charger.") == \
        ["description says things your inputs don't: charger"]


def test_other_words_for_the_same_accessory_count():
    assert problems(description="iPhone 13 with charging cord and chargers.") == \
        ["description says things your inputs don't: cable, charger"]


def test_saying_no_charger_is_still_a_claim():
    assert problems(description="iPhone 13, no charger included.") == \
        ["description says things your inputs don't: no charger"]


def test_your_no_beats_the_drafts_yes():
    # your notes say no box, so a draft saying "boxed" is wrong
    notes = "no box, battery 87%, light scratch on the back"
    assert problems(notes=notes, sources=SOURCES.replace("boxed", "no box"), description="Boxed iPhone 13.") == \
        ["description says things your inputs don't: box"]


def test_doesnt_come_with_is_a_no():
    assert promises_in("doesn't come with a charger") == {"charger": {"no"}}
    assert promises_in("no scratches, comes with box") == {"scratch": {"no"}, "box": {"yes"}}
    assert promises_in("no scratches and comes with box") == {"scratch": {"no"}, "box": {"yes"}}
    assert promises_in("scratch free") == {"scratch": {"no"}}


def test_condition_claims_need_your_notes_not_the_sellers_words():
    # the seller's description says "works perfectly": that doesn't make it flawless
    assert problems(condition_note="Mint condition.") == \
        ["condition_note says things about the condition your notes don't: flawless"]
    assert problems(description="Like new iPhone 13.") == \
        ["description says things about the condition your notes don't: flawless"]


def test_no_scratches_when_your_notes_say_scratch_fails():
    assert problems(condition_note="No scratches.") == \
        ["condition_note says things about the condition your notes don't: no scratch"]


def test_harmless_phrases_are_not_claims():
    assert problems(description="iPhone 13, perfect for gaming, ready for its new owner.") == []


def test_claims_your_notes_make_pass():
    assert problems(description="Boxed iPhone 13, unlocked, light scratch on the back.") == []


@pytest.mark.parametrize("text", [
    "Message me on 07700 900123",
    "call 07700-900-123",
    "ring +44 (0) 7700 900123",
    "landline 020 7946 0958",
    "see www.example.com",
    "ebay dot com",
    "email me@example.com",
    "whatsapp me",
    "insta @example_seller",
    "IMEI 123456789012345",
    "call O7700 900123",                                     # a letter O for the zero
    "Snap: example_seller",
    "find me on IG",
])
def test_contact_details_fail(text):
    assert "description contains a link, email, phone number, handle or long ID number" in problems(description=text)


def test_empty_or_too_long_description_fails():
    assert problems(description="  ") == ["description is empty"]
    assert problems(description="a" * 1501) == ["description is 1501 characters, over the 1500 limit"]


def test_empty_condition_note_is_allowed():
    assert problems(condition_note="") == []


def test_numbers_written_differently_are_the_same():
    assert numbers_in("£1,200.00 and 6.10 inch, two cables") == {"1200", "6.1", "2"}


# ── found by the second check: your notes beat the seller's words ──────────

def test_your_notes_beat_the_sellers_words():
    # the seller's text says boxed (it's in SOURCES), your notes say no box
    notes = "no box, battery 87%, light scratch on the back"
    assert problems(notes=notes, description="Boxed iPhone 13.") == \
        ["description says things your inputs don't: box"]


def test_a_percentage_must_come_from_your_notes():
    sources = SOURCES + " battery health 90%"  # the seller said 90%, you measured 87%
    assert problems(sources=sources, description="iPhone 13, battery health 90%.") == \
        ["description has a percentage your notes don't: 90%"]


def test_a_new_part_doesnt_make_the_item_new():
    notes = "new battery fitted, light scratch on the back"
    assert problems(notes=notes, condition_id="1000", condition_note="", description="iPhone 13.") == \
        ["condition is New, but your notes don't say it's brand new and unopened"]
    assert problems(notes="opened but never used", condition_id="1500", condition_note="",
                    description="iPhone 13.") == []


@pytest.mark.parametrize("text, expected", [
    ("Box: no, charger - none", {"box": {"no"}, "charger": {"no"}}),
    ("charger not included", {"charger": {"no"}}),
    ("charger isn't included", {"charger": {"no"}}),
    ("original box missing", {"box": {"no"}}),
    ("can't find the box", {"box": {"no"}}),
    ("dent-free", {"dent": {"no"}}),
    ("free from scratches", {"scratch": {"no"}}),
    ("fully working, no faults", {"working": {"yes"}}),
    ("faulty speaker", {"working": {"no"}}),
    ("comes with dock and Joy-Cons", {"dock": {"yes"}, "controller": {"yes"}}),
    ("all accessories included", {"accessories": {"yes"}}),
    ("games console", {}),
    ("excellent noise cancelling", {}),
    ("screen perfect", {"flawless screen": {"yes"}}),
    ("new battery fitted", {"battery": {"yes"}}),
])
def test_reading_claims(text, expected):
    assert promises_in(text) == expected


def test_working_claims_need_your_notes():
    # a draft saying Face ID works, when your notes never said so
    assert problems(description="iPhone 13, Face ID works.") == \
        ["description says things about the condition your notes don't: working"]
    assert problems(notes=NOTES + ", fully working", description="iPhone 13, Face ID works.") == []


def test_nothing_is_flawless_when_your_notes_mention_a_mark():
    notes = "screen perfect, light scratch on the back, battery 87%"
    assert problems(notes=notes, description="Flawless iPhone 13.") == \
        ["description says things about the condition your notes don't: flawless"]
    assert problems(notes=notes, description="iPhone 13, screen perfect.") == []


# ── found by the second check: drafts that contradict the item ─────────────

@pytest.mark.parametrize("description, problem", [
    ("Apple iPhone 13 Pro 128GB, unlocked, boxed.", "description names a different model from the iPhone 13"),
    ("Apple iPhone 13 mini 128GB, unlocked, boxed.", "description names a different model from the iPhone 13"),
    ("Apple iPhone 13 128GB in Blue, unlocked, boxed.", "description names a colour that isn't the item's: Blue"),
    ("Apple iPhone 13 128GB in black, unlocked, boxed.", "description names a colour that isn't the item's: black"),
    ("Apple iPhone 13 256GB, unlocked, boxed.", "description names a storage size that isn't the item's: 256GB"),
])
def test_a_draft_that_contradicts_the_item_fails(description, problem):
    assert problem in problems(description=description)


def test_the_reviewers_iphone_13_pro_draft_fails():
    result = problems(description="Apple iPhone 13 Pro 128GB in Midnight, unlocked, boxed. Face ID works.")
    assert "description names a different model from the iPhone 13" in result
    assert "description says things about the condition your notes don't: working" in result


def test_plus_a_case_is_not_the_plus_model():
    assert problems(description="Apple iPhone 13 128GB, unlocked, boxed, plus a case.") == \
        ["description says things your inputs don't: case"]


def test_a_draft_naming_the_other_edition_fails():
    title = "PS5 Slim disc edition 1TB white"
    item = fill_from_catalogue(title, "", CATALOGUE)
    answer = {"condition_id": "3000", "condition_note": "",
              "description": "Sony PlayStation 5 Slim Digital Edition 1TB in White."}
    assert check_listing_answer(answer, item, CATALOGUE, CONDITIONS["consoles"],
                                sources_text(title, "", "", item), "") == \
        ["description says Digital Edition, but the item's edition is Disc Edition"]


def test_short_colour_names_and_unsure_are_allowed():
    plain = "Apple iPhone 13 128GB, unlocked, boxed."
    assert problems(colour="Red", description=plain) == []      # (PRODUCT)RED
    assert problems(colour="unsure", description=plain) == []   # the colour is left for you
    assert problems(colour="unsure", description="Apple iPhone 13 128GB in Midnight.") == \
        ["description names a colour that isn't the item's: Midnight"]


def test_no_colour_needed_when_code_already_knows_it():
    item = fill_from_catalogue("iPhone 13 128GB Midnight unlocked", NOTES, CATALOGUE)
    answer = {key: value for key, value in GOOD.items() if key != "colour"}
    assert check_listing_answer(answer, item, CATALOGUE, CONDITIONS["phones"], SOURCES, NOTES) == []


def test_a_listing_never_states_a_price():
    assert "description mentions a price" in problems(description="Apple iPhone 13 128GB, bought for £220.")


# ── found by the attack agents: claims ─────────────────────────────────────

def answer_for(title, notes, description, condition_id="3000", condition_note="", seller=""):
    """Check one hand-written answer for any catalogue item."""
    item = fill_from_catalogue(title, notes, CATALOGUE, seller)
    answer = {"condition_id": condition_id, "condition_note": condition_note, "description": description}
    if not item.get("colour"):
        answer["colour"] = "unsure"
    return check_listing_answer(answer, item, CATALOGUE, CONDITIONS[item["category"]],
                                sources_text(title, seller, notes, item), notes)


@pytest.mark.parametrize("notes", [
    "used but in brand new condition, no marks",
    "bought brand new from samsung in 2023, used daily since",
    "box opened, console never used",
])
def test_used_or_opened_is_never_new(notes):
    assert "condition is New, but your notes don't say it's brand new and unopened" in \
        answer_for("Galaxy S23 256GB Lavender unlocked", notes, "Samsung Galaxy S23 256GB in Lavender, unlocked.", "1000")


def test_opened_but_never_used_can_be_opened_never_used():
    assert answer_for("PS5 Slim digital 1TB white", "box opened, console never used",
                      "PlayStation 5 Slim Digital Edition 1TB in White.", "1500") == []


@pytest.mark.parametrize("notes", [
    "face id stopped working, screen fine",
    "fully working apart from left joycon drift",
    "screen works, face id broken",
])
def test_a_fault_in_your_notes_blocks_fully_working(notes):
    result = answer_for("iPhone 15 128GB Black unlocked", notes,
                        "Apple iPhone 15 128GB in Black, unlocked. Fully working.", "7000")
    assert "description says things about the condition your notes don't: working" in result


def test_a_fault_means_for_parts_and_for_parts_needs_a_fault():
    assert "your notes mention a fault, so the condition must be For parts or not working" in \
        answer_for("iPhone 13 128GB Blue unlocked", "won't turn on, for parts", "Apple iPhone 13 128GB in Blue, unlocked.")
    assert "condition is For parts or not working, but your notes don't mention a fault" in \
        answer_for("iPhone 13 128GB Blue unlocked", "light scratch on the back",
                   "Apple iPhone 13 128GB in Blue, unlocked.", "7000")


def test_each_kind_of_mark_is_its_own_claim():
    notes = "small scratch on the screen, no dents or cracks"
    title = "Galaxy S23 128GB Cream unlocked"
    assert "description says things about the condition your notes don't: no scratch" in \
        answer_for(title, notes, "Samsung Galaxy S23 128GB in Cream, unlocked. Screen is scratch free.")
    assert answer_for(title, notes, "Samsung Galaxy S23 128GB in Cream, unlocked. Small scratch on the screen, no dents.") == []
    assert answer_for(title, "no marks", "Samsung Galaxy S23 in Cream. No scratches.") == []


def test_your_own_excellent_or_like_new_with_a_mark_passes():
    text = "Excellent condition, light scratch on the back."
    assert answer_for("iPhone 14 128GB Midnight unlocked", "excellent condition, light scratch on the back",
                      f"Apple iPhone 14 128GB in Midnight, unlocked. {text}", condition_note=text) == []
    assert answer_for("PS5 Slim disc 1TB white", "like new, tiny scuff on the side",
                      "PlayStation 5 Slim Disc Edition 1TB in White.", condition_note="Like new, tiny scuff on the side.") == []


def test_the_processor_chip_is_not_damage():
    assert answer_for("iPhone 13 128GB Blue unlocked", "", "Apple iPhone 13 128GB in Blue, unlocked. A15 Bionic chip.") == []


def test_a_no_after_a_list_covers_the_whole_list():
    assert promises_in("box and charger not included") == {"box": {"no"}, "charger": {"no"}}


def test_no_controller_drift_is_not_about_the_controller():
    assert promises_in("no controller drift") == {"working": {"yes"}}


def test_battery_figures_without_a_percent_sign():
    title = "iPhone 13 128GB Blue unlocked"
    assert answer_for(title, "battery health 86", "Apple iPhone 13 128GB in Blue, unlocked. Battery health 86%.") == []
    assert "description has a percentage your notes don't: 95%" in \
        answer_for(title, "battery 84%", "Apple iPhone 13 128GB in Blue, unlocked. Battery health 95.",
                   seller="battery health 95%")


def test_your_locked_or_out_of_warranty_beats_the_seller():
    assert "description says things your inputs don't: unlocked" in \
        answer_for("iPhone 13 128GB Blue", "locked to Vodafone", "Apple iPhone 13 128GB in Blue, unlocked to all networks.",
                   seller="unlocked")
    assert "description says things your inputs don't: warranty" in \
        answer_for("AirPods Pro 2 USB-C", "out of warranty", "Apple AirPods Pro 2, still under Apple warranty.",
                   seller="still has warranty")


def test_invented_bundle_items_fail():
    assert "description says things your inputs don't: cable, headset, stand" in \
        answer_for("PS5 Slim disc 1TB white", "", "PlayStation 5 Slim Disc Edition 1TB in White, with vertical stand, HDMI and headset.")


# ── found by the attack agents: reading the item ───────────────────────────

@pytest.mark.parametrize("game", ["Call of Duty Black Ops 6", "Red Dead Redemption 2"])
def test_colour_words_in_game_titles_dont_count(game):
    assert answer_for("PS5 Slim Disc 1TB White", f"comes with {game}",
                      f"PlayStation 5 Slim Disc Edition, 1TB, White. Comes with {game}.") == []


def test_the_other_edition_mentioned_in_passing_is_fine():
    assert answer_for("PS5 Slim Digital 825GB White", "",
                      "PS5 Slim Digital Edition, 825GB, White. It doesn't have a disc drive.") == []
    assert answer_for("PS5 Slim Disc 1TB White", "",
                      "PS5 Slim Disc Edition, 1TB, White. Plays discs and digital downloads.") == []
    assert fill_from_catalogue("AirPods Pro 2 with USB-C to Lightning cable", "", CATALOGUE)["options"] == \
        {"Connector": None}


@pytest.mark.parametrize("title, notes, description", [
    ("iPhone 15 Pro 256GB Black Titanium unlocked", "",
     "iPhone 15 Pro 256GB in Black Titanium, unlocked. Shows natural signs of use."),
    ("PS5 Slim Digital 30th Anniversary 825GB", "",
     "PS5 Slim Digital Edition, 30th Anniversary, 825GB, in the classic PlayStation grey."),
    ("PS5 Slim Disc 1TB White", "black covers fitted", "PS5 Slim Disc Edition, 1TB, White, with black covers fitted."),
    ("Nintendo Switch OLED Splatoon 3 Edition", "", "Nintendo Switch OLED, Splatoon 3 Edition, blue and yellow design."),
    ("iPhone 13 128GB Blue unlocked", "comes with white charging cable",
     "iPhone 13 128GB in Blue, unlocked. Comes with the white charging cable."),
])
def test_colour_words_that_arent_the_items_colour(title, notes, description):
    assert answer_for(title, notes, description) == []


@pytest.mark.parametrize("title, description", [
    ("PS5 Slim Digital 825GB White", "Sony PS5 Pro Digital Edition, 825GB, White."),
    ("iPhone 15 Pro 256GB Black Titanium unlocked", "Apple iPhone 15 Plus 256GB in Black Titanium, unlocked."),
    ("iPhone 13 Pro 128GB Graphite unlocked", "Apple iPhone 13 mini 128GB in Graphite, unlocked."),
])
def test_a_family_name_with_another_version_fails(title, description):
    model = fill_from_catalogue(title, "", CATALOGUE)["model"]
    assert f"description names a different model from the {model}" in answer_for(title, "", description)


# ── messages ────────────────────────────────────────────────────────────────

LISTING = "PS5 disc edition, 2 controllers, £200"


@pytest.mark.parametrize("message", [
    "Hi, is this still available? Would you take £170 for it?",
    "Hi, does it come with the box? I could do £170.",       # asking about things is fine
    "Could you do 170 cash?",
    "Hi, I know it's listed at £200, would you take £170?",
])
def test_good_messages_pass(message):
    assert check_message(message, 17000, LISTING, asking=20000) == []


@pytest.mark.parametrize("message", [
    "Would you take £160?",
    "£170? or £180 max",
    "Would you take 160 quid?",
    "£170 or £200?",                                         # the asking price as a second offer
    "Is this still available?",                               # no offer at all
])
def test_wrong_price_fails(message):
    assert "the message must offer exactly £170.00 and no other price" in check_message(message, 17000, LISTING, asking=20000)


def test_message_with_a_phone_number_fails():
    assert "message contains a link, email, phone number, handle or long ID number" in \
        check_message("£170? text me on 07700900123", 17000, LISTING)


def test_the_asking_price_cant_hide_a_second_offer():
    message = "It's listed at £200, but would you take £170 or £200?"
    assert "the message must offer exactly £170.00 and no other price" in \
        check_message(message, 17000, LISTING, asking=20000)


def test_a_silly_amount_in_a_message_fails_instead_of_crashing():
    assert "the message must offer exactly £170.00 and no other price" in \
        check_message("Would you take £" + "9" * 40 + "?", 17000, LISTING)


# ── found by the attack agents: messages and leaks ─────────────────────────

@pytest.mark.parametrize("message", [
    "Would you take £170? I can pay by bank transfer straight away.",
    "Would you take £170 if I pay through PayPal friends and family?",
    "Would you take £170? Happy to do it outside eBay if you end the listing.",
])
def test_paying_off_the_platform_fails(message):
    assert "message suggests paying or dealing outside the platform" in \
        check_message(message, 17000, LISTING, asking=20000)


@pytest.mark.parametrize("message", [
    "Would you take £170? My snap is example_seller",
    "Would you take £170? my ig is example.seller",
    "Would you take £170? Message me on Facebook",
    "Would you take £170? Add me on Messenger",
    "Would you take £170? details at bit.ly/example",
    "Would you take £170? WA me",
])
def test_moving_the_chat_elsewhere_fails(message):
    assert "message contains a link, email, phone number, handle or long ID number" in \
        check_message(message, 17000, LISTING, asking=20000)


@pytest.mark.parametrize("message", [
    "Would you take £170? If not, happy to pay the asking £200.",
    "Would you take £170? I could stretch to 200 if you can post it.",
    "Would you consider £170-200?",
    "£170, or 200 if you deliver?",
])
def test_a_second_offer_in_other_words_fails(message):
    assert "the message must offer exactly £170.00 and no other price" in \
        check_message(message, 17000, LISTING, asking=20000)


@pytest.mark.parametrize("message", [
    "Hi, I know the asking price is £200, but would you take £170?",
    "Hi, I see it's £200 ono - would you take £170?",
    "Would you take £170? It's £200 on the listing so hope that's fair.",
    "Hi, do 2 controllers come with it? Would you take £170?",
    "Would you take £170? Could you take 2 more photos of the console?",
    "Would you let it go for 170?",
    "Would you accept 170?",
    "Hi, saw these on Facebook - would you take £170?",
    "Hi, saw your PS5 on FB - would you take £170?",
])
def test_normal_polite_messages_pass(message):
    assert check_message(message, 17000, LISTING, asking=20000) == []


@pytest.mark.parametrize("text", ["Paid 300 at Currys.", "RRP 349.", "Was GBP 120."])
def test_a_listing_never_mentions_what_was_paid(text):
    assert "description mentions a price" in problems(description=f"Apple iPhone 13 128GB, unlocked. {text}")


def test_a_listing_never_suggests_paying_or_talking_elsewhere():
    assert "description suggests paying or dealing outside the platform" in \
        problems(description="Apple iPhone 13 128GB, unlocked. Payment by bank transfer or PayPal friends and family.")
    assert "description contains a link, email, phone number, handle or long ID number" in \
        problems(description="Apple iPhone 13 128GB, unlocked. Message me on Facebook for more photos.")


def test_a_parts_condition_can_come_a_few_words_after_it():
    # Claude Haiku's real sentence from the first live run: backed by "screen perfect"
    assert promises_in("The screen is in perfect condition.") == {"flawless screen": {"yes"}}
    assert answer_for("iPhone 13 128GB Blue unlocked", "light scratch on the back, screen perfect",
                      "Apple iPhone 13 128GB in Blue, unlocked. Light scratch on the back. "
                      "The screen is in perfect condition.") == []


# ── longer messages: more words, nothing made up ───────────────────────────

# the review agents' made-up stories: each one is something only you could know
@pytest.mark.parametrize("story", [
    "It's for my son's birthday.", "I've been looking for one for ages.", "My old PS5 broke last week.",
    "I'm local so can collect.", "I live nearby.", "It'd be a Christmas present.", "It's for the wife.",
    "It's for our son.", "It's for my lad.", "It's for my grandad.", "It's for my hubby.", "It's for my eldest.",
    "It's for my little girl's birthday.", "It's my daughter's birthday next week.", "My son has been asking for one.",
    "It's a present for her.", "It's for Christmas.", "I need it for work.", "It's for uni.", "Mine broke last week.",
    "My phone was nicked.", "My old one's broken.", "My old PS5 Slim broke last week.",
    "My iPhone 12 Pro Max died on me.", "I've been after one of these for ages.",
    "I've been looking for a PS5 for ages.", "I've wanted one for ages.", "I'm a student so money is tight.",
    "It's for personal use, not to resell.", "It's just for me, not for reselling.", "I'm based in Leeds.",
    "I'm only round the corner.", "I'm just up the road.", "I'm around the corner.", "I'm near you.",
    "We're local.", "I live locally.", "I live just round the corner.", "I work round the corner from you.",
    "I'm only 5 minutes away.", "I'm literally round the corner.", "I'm moving next month.",
])
def test_a_made_up_story_about_you_fails(story):
    message = f"Hi mate, would you take £170? {story}"
    assert any(p.startswith("message makes up something about you") for p in
               check_message(message, 17000, LISTING, asking=20000)), message


@pytest.mark.parametrize("line", [
    "Can collect whenever suits you.", "Happy to come to you for it.", "Would be great for my collection.",
    "I know I'm not far off your price.", "I'm in no rush.", "I'm flexible on when I collect.",
    "I'm around all day.", "Could you hold it for me until tonight?", "Thanks for the quick reply mate.",
    "I can collect today, cash in hand mate.", "My best offer, cheers.", "Happy New Year!",
])
def test_ordinary_lines_arent_stories(line):
    assert check_message(f"Hi mate, would you take £170? {line}", 17000, LISTING, asking=20000) == []


def test_saying_the_listings_own_words_back_isnt_a_story():
    listing = "PS5 disc edition, 2 controllers, £200. Unwanted Christmas present, boxed."
    assert check_message("Hi mate, I see it was an unwanted Christmas present. Would you take £170?", 17000,
                         listing, asking=20000) == []


def test_the_offer_isnt_read_as_a_story_about_you():
    assert check_message("Hi mate, £170 is my offer as it stopped working. Can collect today.", 17000,
                         "PS5 disc edition, £200. Stopped working after an update.", asking=20000) == []


@pytest.mark.parametrize("message", [
    "Would you take £170? I can transfer the money to you straight away if you end it early.",
    "Would you take £170 if you end the auction now?",
])
def test_asking_to_end_an_auction_early_is_off_the_platform(message):
    assert "message suggests paying or dealing outside the platform" in \
        check_message(message, 17000, LISTING, asking=20000)


@pytest.mark.parametrize("message", ["Would you take it down to £170?", "Would you take £170? When does the auction end?"])
def test_ordinary_haggling_isnt_off_the_platform(message):
    assert check_message(message, 17000, LISTING, asking=20000) == []


def test_a_message_never_says_the_item_comes_with_what_the_listing_doesnt():
    message = ("Hi mate, would you take £170 as it comes with the charger and the original box? "
               "It's unlocked too. Can collect today.")
    assert check_message(message, 17000, "iPhone 13 128GB Blue. Good condition.", asking=20000) == \
        ["the message says things the listing doesn't: box, charger, unlocked"]


@pytest.mark.parametrize("message", [
    "Does it come with a charger? Is it unlocked? Would you take £170?",
    "Would you take £170? Happy to pay it if it comes with the box.",
    "Would you take £170? No worries if there's no box or charger.",
    "Would you take £170? Just in case, can I collect today?",
])
def test_asking_about_what_comes_with_it_is_fine(message):
    assert check_message(message, 17000, "iPhone 13 128GB Blue. Good condition.", asking=20000) == []


@pytest.mark.parametrize("message", ["Hi mate, would you be happy with £315?", "Are you OK with £315 for it?",
                                     "Just wondering if you'd take £315?"])
def test_an_offer_over_asking_in_any_question_fails(message):
    assert "an offer over the asking price must be said, not asked: \"would you take\" reads like asking for a discount" \
        in check_message(message, 31500, "PS5 Slim disc. Boxed.", asking=30000, kind="more")


def test_a_no_counts_only_in_its_own_sentence():
    from flip.checks import has_fault
    assert has_fault("No box. Broken screen.")
    assert not has_fault("No faults. Boxed.")


def test_a_longer_message_needs_its_words():
    short = "Hi mate, would you take £170?"
    assert check_message(short, 17000, LISTING, asking=20000, min_words=23) == \
        ["the message is 6 words, but a longer one needs at least 23"]
    assert check_message(short, 17000, LISTING, asking=20000) == []


def test_a_controller_that_drifts_is_a_fault_like_one_that_drifted():
    assert has_fault("Left joycon drifts") and has_fault("drifting") and not has_fault("no drift")


@pytest.mark.parametrize("message, allowed, problems", [
    ("Hi, I can pay £190. Let me know and I can arrange collection quickly.", set(),
     ["the message promises collecting, which your own messages don't"]),
    ("Hi, would you take £185 cash?", {"collecting"}, ["the message promises cash, which your own messages don't"]),
    ("Hi mate, would you take £185 cash? Can collect today.", {"collecting", "cash"}, []),
    ("Hi, would you take £185? Could I collect today?", set(), []),  # asking isn't promising
    ("Hi, would you take £185? Happy to pay for postage.", {"cash"},
     ["the message promises postage, which your own messages don't"]),
    ("Hi, saw your post. Would you take £185?", set(), []),  # the listing, not posting it
])
def test_a_message_promises_how_youll_buy_only_the_way_your_messages_do(message, allowed, problems):
    assert check_no_unasked_promises(message, allowed) == problems


@pytest.mark.parametrize("message, promised", [
    ("Hi, would you take £170? I can arrange collection quickly, does that work?", {"collecting"}),  # a tag question
    ("Hi, would you take £170? If that works I can collect today and pay cash.", {"collecting", "cash"}),
    ("Hi, would you take 170 cash on collection?", {"collecting", "cash"}),  # the offer's own sentence, no £
    ("Hi, would you take £170? I'll come and get it tonight.", {"collecting"}),
    ("Hi, would you take £170? Happy to cover shipping.", {"postage"}),
    ("Can pick it up today.", {"collecting"}),
    ("Can pop round tonight.", {"collecting"}),
    ("Hi, would you take £170 for the whole collection?", set()),  # a collection is a thing, not collecting
    ("Hi, would you take £170 for your Pokemon card collection?", set()),
    ("Hi, would you take £170, or is it collection only?", set()),
    ("I'm interested in your Zelda Collector's Edition. Would you take £50?", set()),
    ("Hi, would you take £170? Could I collect today?", set()),  # asking, not promising
    ("Can't collect sorry, could you post it?", set()),
    ("Saw your post, would you take £170?", set()),
])
def test_what_a_message_promises_about_how_youll_buy(message, promised):
    assert promised_in(message) == promised


def test_not_for_parts_isnt_a_fault():
    assert not has_fault("Fully working, not spares or repairs.") and not has_fault("Not for parts.")
    assert has_fault("Spares or repairs.")


def test_the_asking_price_cant_be_misquoted_and_a_lower_offer_cant_offer_more():
    sources = "iPhone 13. Good condition."
    assert check_message("Hi mate, I know you're asking £170 but would you take £170 cash?", 17000, sources, 20000) \
        == ["the message gives the asking price as £170.00, but it's £200.00"]
    assert check_message("Hiya, would you take £170? If not I can pay the full asking price", 17000, sources, 20000) \
        == ['a lower offer can\'t offer more as well: "If not I can pay the full asking price"']
    assert check_message("Hiya, would you take £170? Could go a bit higher if needed", 17000, sources, 20000)
    assert check_message("Hiya, would you take £170? I can't go higher than that", 17000, sources, 20000) == []


@pytest.mark.parametrize("message", ["Hi mate, would you take £210?😊", "Hi mate, would you take £210 x",
                                     "Hi mate, would you take £210..."])
def test_an_offer_is_asked_whatever_comes_after_it(message):
    assert offer_asked(message, 21000)


@pytest.mark.parametrize("message, problem", [
    ("Hi mate, would you take £170? If not, I understand.", False),
    ("Hi mate, best I can go up to is £170 cash if that works?", False),
    ("Hi, would you take £170? Can pay up front today.", False),
    ("Hi, would you take £170? Sorry, I wouldn't be able to go higher.", False),
    ("Hiya, would you take £170? Could go a bit higher if needed", True),
    ("Hiya, would you take £170? If not I can pay the full asking price", True),
])
def test_a_second_offer_is_caught_and_a_polite_closing_isnt(message, problem):
    found = [p for p in check_message(message, 17000, "iPhone 13. Good.", 20000) if "offer more" in p]
    assert bool(found) is problem


@pytest.mark.parametrize("message, promised", [
    ("I'd collect.", {"collecting"}), ("Happy to do collection.", {"collecting"}),
    ("Collection works for me.", {"collecting"}), ("I'd be collecting.", {"collecting"}),
    ("Happy to travel to you.", {"collecting"}), ("I don't mind collecting.", {"collecting"}),
    ("Hiya, would you take £170 posted?", {"postage"}), ("Hiya, would you take £170 sent tracked?", {"postage"}),
    ("Hiya, would you take £170? I can arrange collection quickly, does that work for you?", {"collecting"}),
    ("Hi, would you take £170 or is it postage only?", set()),  # asks about the sale
])
def test_more_ways_of_promising_how_youll_buy(message, promised):
    assert promised_in(message) == promised


def test_no_power_for_spares_is_still_a_fault():
    assert has_fault("No power, spares or repairs.") and has_fault("No sound, spares or repairs.")


# ── what comes after a sentence: a run of emojis can't hang the checks ──────

@pytest.mark.parametrize("sentence, core, after", [
    ("Would you take £210?😊", "Would you take £210?", "😊"),
    ("Would you take £210? x", "Would you take £210?", "x"),
    ("Cheers 👍🏽👍🏽 xx", "Cheers", "👍🏽👍🏽 xx"),
    ("Would you take £210...", "Would you take £210", "..."),
    ("ok 😊 thanks", "ok 😊 thanks", ""),  # an emoji mid-sentence isn't a sign-off
    ("Taxi", "Taxi", ""),
])
def test_what_comes_after_a_sentences_own_end(sentence, core, after):
    from flip.writer import split_sign_off
    assert split_sign_off(sentence) == (core, after)


def test_a_row_of_emojis_mid_sentence_is_checked_at_once():
    """It once tried every way of splitting the row: 12 hearts took 19 seconds, 15 would take 20 minutes."""
    import time
    from flip.writer import split_sign_off
    hearts = "❤️" * 1000
    started = time.monotonic()
    check_message(f"Would you take £185, given the back glass cracked {hearts} still works fine? Can collect today.",
                  18500, f"Back glass cracked {hearts} still works fine. Collection only.", 22000)
    split_sign_off(f"Hi {hearts} mate")
    assert time.monotonic() - started < 2
