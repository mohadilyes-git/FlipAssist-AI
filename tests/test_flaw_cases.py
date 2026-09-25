"""Breaking the 23 Sep flaw reading: four test agents wrote 2,417 made-up cases against the battery rule, the new
flaw words, the guards against wrong flaws and the way it all fits together, and a second agent re-ran every
failure: 63 confirmed. Each one is kept here, in made-up words."""

import pytest

from flip.checks import has_fault
from flip.message_drafter import draft_message
from flip.offers import check_condition_talk, point_for, says_point
from flip.reader import code_reading, flaws_in, reading_from
from flip.writer import write_offer

TITLE = "iPhone 12 64GB Blue"


def read(line, title=TITLE):
    """Code's own flaws, and the AI's quote of the whole line, as rule 2 judges it."""
    text = f"{title}\n{line}"
    return code_reading(text)["flaws"], flaws_in(line, text)


def lower_offer(description, title="iPhone 13 128GB"):
    listing = {"id": "x", "title": title, "asking_price": "250", "marketplace": "facebook", "description": description}
    return draft_message(listing, kind="lower", offer=23500)["answer"]["message"]


# ── the battery: only its health now, 85% or under ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("line", [
    # a model's number or its storage before a battery word
    "iPhone 13 battery is good, unlocked", "iPhone 12 battery life amazing", "iPhone 11 64 battery good",
    "Redmi Note 12 battery good", "iPhone 15 batt health excellent",
    # a rating, a date, a price, a discount, a condition
    "Screen 10/10 battery 10/10", "Battery health 10/10", "battery 10 out of 10", "Battery health checked on 25 March",
    "Battery health checked 15/10 all good", "Battery fine 80 for quick sale", "Battery good 70 collection only",
    "Battery health amazing 75 or swap", "Battery good 50% cheaper than CEX", "Battery is fine 20% off this week only",
    "battery is good 80% condition overall",
    # a charge level, a limit, what's left
    "Battery level 60% in photos", "Battery 80% charged in the pics", "Battery set to 80% limit to protect it",
    "Battery charges to 80% max", "Battery at 40% charge in the photos", "Battery lasts all day still 60% left at bedtime",
    "Battery percentage showing 60% in the photo", "Battery good on 50% in pics", "Battery 80% charge limit on",
    # a bound upwards, the past, more than 85
    "Battery health 80% or more", "Battery health 80% or higher", "Battery health 80% upwards", "Battery health 85.5%",
])
def test_a_figure_that_isnt_the_batterys_health_now_is_no_flaw(line):
    assert read(line) == ([], [])


@pytest.mark.parametrize("line, flaw", [
    # 🔋 and the separators that used to cut a figure from its word
    ("🔋 80%", "🔋 80%"), ("Unlocked to all networks 🔋80%", "🔋80%"), ("Battery health - 82%", "Battery health 82%"),
    ("Battery health – 82%", "Battery health 82%"), ("Battery health (82%)", "Battery health 82%"),
    ("Battery health | 80%", "Battery health 80%"), ("Battery health • 80%", "Battery health 80%"),
    ("Battery health:-\n79%", "Battery health 79%"), ("Battery Health :-\n80%", "Battery Health 80%"),
    ("Battery health\r\n79%", "Battery health 79%"), ("Battery health:\n- 79%", "Battery health 79%"),
    ("Battery condition:\n79%", "Battery condition 79%"), ("Battery health -> 80%", "Battery health -> 80%"),
    # a word elsewhere in the line that isn't about the battery
    ("Battery health 82% still under warranty", "Battery health 82%"),
    ("Phone is about 2 years old battery health 81%", "battery health 81%"),
    ("Battery health 80% + original box", "Battery health 80%"), ("Battery health 83% was my work phone", "Battery health 83%"),
    ("Battery health 81% nearly 2 years old", "Battery health 81%"),
    ("Battery health 79% screen protector on since day one", "Battery health 79%"),
    ("Battery health 81% could be replaced if you want", "Battery health 81%"),
    # rough, or a ceiling: still 85 or under
    ("Battery health around 80%", "Battery health around 80%"), ("Battery health below 80%", "Battery health below 80%"),
    # a decimal is one figure
    ("Battery health 84.5%", "Battery health 84.5%"), ("Battery health 79.8%", "Battery health 79.8%"),
])
def test_a_battery_health_now_of_85_or_under_is_a_flaw_however_its_written(line, flaw):
    assert read(line) == ([flaw], [flaw])


def test_a_battery_and_another_flaw_in_one_part_are_two_flaws():
    assert read("Battery health 79% small crack on back") == \
        (["Battery health 79%", "small crack on back"], ["Battery health 79%", "small crack on back"])
    assert read("Cracked back and battery health 79%")[0] == ["Cracked back", "battery health 79%"]
    assert lower_offer("Battery health 80%", title="iPhone 13 128GB cracked back BH 80%") == \
        "Hi, would you take £235 cash for it? I'm offering that because of the cracked back and because the battery " \
        "health is 80%. I can come and collect."
    assert lower_offer("Cracked back. 🔋 80%") == "Hi, would you take £235 cash for it? I'm offering that because " \
        "of the cracked back and because the battery health is 80%. I can come and collect."


def test_a_denial_next_to_the_battery_is_no_reason():
    reading = reading_from({"flaws": ["No issues battery health 81%"], "pickup": "", "no_offers": ""},
                           f"{TITLE}. No issues battery health 81%", "gemma")
    assert reading["flaws"] == ["battery health 81%"]
    assert lower_offer("No issues battery health 81%") == \
        "Hi, would you take £235 cash for it? I'm offering that because the battery health is 81%. I can come and collect."


def test_the_battery_reason_needs_its_own_figure_and_two_figures_are_none():
    point = {"about": "battery", "says": ["battery health 80%"], "battery": "80"}
    assert not says_point("Would you take £150 as the battery health is 18%?", point)
    assert not says_point("Would you take £150? The battery health is fine.", point)
    assert says_point("Would you take £150 as the battery health is 80%?", point)
    # "79% BH" in the title, "Battery health 80%" below: no reason that says both
    assert point_for("lower", "iPhone 13 128GB 79% BH. Battery health 80%.") is None
    assert lower_offer("Battery health 84.5%") == \
        "Hi, would you take £235 cash for it? I'm offering that because the battery health is 84.5%. I can come and collect."


# ── the new words: what's wrong with the phone, not with the seller, the buyers or the sale ────────────────────

@pytest.mark.parametrize("line", [
    "I no longer work from home so don't need it", "Seller will no longer respond after 6pm",
    "No longer charging for postage, collection is free", "Selling as I no longer work in an office",
    "The small screen no longer works for me", "Can't confirm collection times until Friday",
    "Unable to confirm a viewing time until the weekend", "Unable to verify my Facebook account so message me on here",
    "Updated it up to iOS 26", "Can update up to iOS 26", "Supports up to iOS 26, the latest",
    "Not sure what's wrong with people on here", "Don't know what's wrong with Facebook, it keeps removing my listing",
    "Barely a nick on it", "Hardly a nick on it", "Hardly any nicks, really well looked after", "Free from nicks and scratches",
    "Selling my son Nicks old iPhone as he's upgraded", "Collection near St Nicks church", "No SIM tray tool included",
    "No physical SIM card included, just the phone", "No SIM tray issues", "Unknown battery cycles, health 91%",
    "Sorry my mind went blank, it's the 128GB", "Fully tested",
])
def test_everyday_words_near_the_new_ones_are_no_flaw(line):
    assert read(line) == ([], [])


@pytest.mark.parametrize("line", [
    "Phone no longer powers up", "Screen no longer comes on", "No longer holding charge", "It no longer starts up",
    "Not fully tested", "Haven't fully tested it", "Unable to test as I don't have a charger", "Couldn't test the cameras",
    "Not able to confirm it works", "Couldn't confirm it charges", "Un-tested, sold as seen",
    "The odd nick on the frame", "A wee nick on the corner", "1 nick on the side", "Another nick on the bottom",
    "Doesn't have a SIM tray", "Can only use eSIM", "Only works on eSIM", "Physical SIM not supported",
    "Non genuine Apple screen fitted", "Battery is non-genuine", "Screen is not genuine", "Aftermarket screen fitted",
    "Third party battery", "Non-original back glass", "Important battery message in settings",
    "Couldn't verify the battery as genuine", "Camera comes up as unknown in settings",
    "Screen is completely blank", "Screen has gone blank", "Back camera is just blank", "Cameras are blank",
    "Only charging wirelessly at the moment", "Charges wirelessly only", "Wireless charging only",
    "Only charges via MagSafe", "Will only charge on MagSafe", "Upto iOS 16 only", "Can't update past iOS 16",
    "Max iOS 16", "Won't update beyond iOS 15", "Can only update to iOS 16", "Not too sure what's wrong with it",
    "No idea what the fault is", "Left it charging overnight and in the morning it no longer turns on",
])
def test_more_ways_sellers_say_the_new_flaws(line):
    flaws, quoted = read(line)
    assert quoted and flaws


@pytest.mark.parametrize("notes", ["I no longer work from home so don't need it", "No controller has been tested working",
                                   "No longer charging for postage"])
def test_your_own_notes_read_as_before(notes):
    assert not has_fault(notes)


def test_an_issue_isnt_damage_and_a_message_names_only_the_listings_own():
    listing = "iPhone 13 128GB. Sold untested. Works perfectly."
    point = point_for("lower", listing)
    for message in ("Hi, would you take £150 cash given the damage?", "Hi, would you take £150 cash as it's damaged?"):
        assert any("damage" in p for p in check_condition_talk(message, listing, point, True))
    esim = "iPhone 15 Pro 128GB. US model, eSIM only. Works perfectly."
    assert any("part" in p for p in check_condition_talk("Hi, would you take £150 cash given the non-Apple screen?",
                                                       esim, point_for("lower", esim), True))


@pytest.mark.parametrize("flaw, reason", [
    ("It no longer turns on", "it no longer turns on"), ("Only charges wirelessly", "it only charges wirelessly"),
    ("Only runs up to iOS 15", "it only runs up to iOS 15"), ("Sold untested", "it's untested"),
    ("No SIM tray", "it's eSIM only"), ("Not sure what's wrong with it", "you're not sure what's wrong with it"),
])
def test_the_no_ai_reason_says_the_new_flaws_in_plain_words(flaw, reason):
    assert write_offer({}, "lower", 9000, {"about": "flaw", "says": [flaw]}) == \
        f"Hi, would you take £90 for it? I'm offering that because {reason}."


# ── what comes with it, and what only points back at a flaw ───────────────────────────────────────────────────

@pytest.mark.parametrize("line", [
    "Small scratch under the screen protector", "There's a scratch underneath the screen protector",
    "Screen protector hides a small crack", "Crack under the camera lens protector",
    "Never used a screen protector so there are some marks", "Took the screen protector off and found a crack",
    "Has a screen protector on with a small scratch under it", "Always had a screen protector and the battery needs replacing",
    "Screen protector on but Face ID doesn't work", "Screen protector fitted has a dent on the corner",
    "Comes with box, it has a small crack", "One dead pixel 5mm from the top", "Dead pixel 2cm from the top left",
    "No scratches has been dented on the corner", "The screen is easy to peel off the frame",
    "Small 2mm white dot on the screen about 1cm from the top left corner",
])
def test_the_phones_own_flaw_stays_whatever_is_said_around_it(line):
    assert read(line)[1]


@pytest.mark.parametrize("line", [
    "Crack is only on the screen protector not the screen", "Scratches are on the protector not the actual screen",
    "Camera protector is cracked not the lens", "The protector on the back camera is cracked",
    "Comes with a tempered glass screen protector which has a small crack in it", "Screen protector - cracked",
    "Screen protector (cracked) but screen is perfect", "Screen protector cracked, needs replacing",
    "Screen protector on, its cracked but the screen underneath is fine", "Tempered glass on the front is cracked",
    "Screen guard is cracked", "None of the parts have been replaced", "Not a single part has been replaced",
    "No screen or battery has ever been replaced", "Nothing on it has been replaced", "Nothing's been repaired",
    "There are no parts that have been replaced", "48MP Main camera with 100% Focus Pixels", "2556 by 1179 pixels",
    "Second-generation Ultra Wideband chip", "NFC chip for Apple Pay", "Upgraded to a Pixel so selling this",
    "Back glass can be replaced if u want", "Battery could be replaced if you wanted",
    "Screen can be replaced for £40 extra if you want", "If you want, the battery can be replaced for £20",
])
def test_what_isnt_a_flaw_of_the_phone_stays_none(line):
    assert read(line) == ([], [])


@pytest.mark.parametrize("description", [
    "Upgraded from my iPhone 13. eSIM only.", "eSIM only. Open to swaps for a PS5",
    "eSIM only, comes with AirPods Pro 2 for £100 extra", "Not the iPhone 17 Pro, the Air. eSIM only.",
])
def test_esim_only_is_no_flaw_of_an_air_whatever_else_the_listing_names(description):
    assert code_reading(f"iPhone Air 256GB Sky Blue\n{description}")["flaws"] == []
    assert flaws_in("eSIM only", f"iPhone Air 256GB Sky Blue\n{description}") == []


def test_on_an_air_a_flaw_next_to_esim_only_keeps_the_sellers_words():
    assert code_reading("iPhone Air 256GB\nPhone is eSIM only and has a dent")["flaws"] == \
        ["Phone is eSIM only and has a dent"]


def test_a_label_answered_on_its_own_line_denies_it():
    assert read("Unlocked to all networks\nFaults: none\nDamage: none")[0] == []


# ── the second round (23 Sep): what comes with the phone, more ways to say it (made up) ────────────────────────

PHONE, BUDS, PS5 = "iPhone 13 128GB", "AirPods Pro 2nd Gen", "PS5 Disc Edition 825GB"


@pytest.mark.parametrize("title, line", [
    (PHONE, "Comes with box and charger, has a small crack"), (PHONE, "Boxed + charger, it has a small crack"),
    (PHONE, "comes with a case and charger it has a small crack"), (PS5, "Comes with box and cables, has a small scratch on the top"),
    (PHONE, "Couple of small marks from a rugged case"), (PHONE, "Kept in a pink case, has a few light scratches"),
    (PHONE, "Small crack under the Zagg screen protector"), (PHONE, "Comes with 20W charger, it has a small crack"),
    (PHONE, "Screen protector is hiding a small crack"), (PHONE, "Screen protector put on to cover a small crack"),
    (PHONE, "Light scratch visible through the screen protector"), (PHONE, "Screen protector cracked with a small scratch underneath"),
    (PHONE, "The case has left a few marks on the corners"), (PHONE, "Cheap case scratched the edges a bit"),
    (PHONE, "Edges are a bit marked where the case rubbed"), (PHONE, "Small chip on the edge a case would cover it"),
    (PHONE, "Small crack on the corner box not included"), (PHONE, "Box has a small dent and cracked back glass"),
    (PHONE, "Doesn't charge via cable"), (PHONE, "Wont charge with a lightning cable"),
    (PHONE, "If you want, the cracked screen can be replaced for £40"), (PHONE, "If u want the cracked back can be repaired for £30"),
    (PHONE, "No scratches, dents and screen cracked"), (PS5, "Top cover has a small crack near the vent"),
    (BUDS, "Case has a few scratches"), ("Galaxy S23 128GB", "Back cover cracked"),
])
def test_the_items_own_mark_stays_whatever_comes_with_it(title, line):
    assert flaws_in(line, f"{title}\n{line}")


@pytest.mark.parametrize("title, line", [
    (PHONE, "Comes with a case that has a crack"), (PHONE, "Comes with the original box that's slightly damaged"),
    (PHONE, "The screen protector on the phone is cracked"), (PHONE, "With case (cracked)"),
    (PHONE, "Includes original box – slightly damaged"), (PHONE, "Box included but it's a bit damaged"),
    (PHONE, "Comes with the lens protectors, they're both cracked"), (PHONE, "Comes with 2 cases, one is cracked"),
    (PHONE, "Screen protector has a crack at the top of the screen"), (PHONE, "Camera protector cracked over the lens"),
    (PHONE, "Swaps for AirPods considered. Case has a few scratches"), (BUDS, "Comes with a Spigen cover, cover has a few scratches"),
    (BUDS, "Comes with a keyring case which is scratched"), (PHONE, "Crack on the screen (protector only)"),
    (PHONE, "If you would like the battery replaced I can do it for £20"), (PHONE, "If wanted I can get the back glass replaced"),
    (PHONE, "The box has got a bit of damage"),
])
def test_a_mark_said_of_what_comes_with_it_is_none(title, line):
    text = f"{title}\n{line}"
    assert flaws_in(line, text) == [] and code_reading(text)["flaws"] == []


@pytest.mark.parametrize("description, flaws", [
    ("Light scratches on the screen. Price reflects the damage to the back.",
     ["Light scratches on the screen", "Price reflects the damage to the back"]),
    ("Case is scratched. Price reflects the scratched screen.", ["Price reflects the scratched screen"]),
    ("- Price reflects the cracked back", ["Price reflects the cracked back"]),
    ("Crack on the back. The crack is not affecting use.", ["Crack on the back"]),
    ("Crack on the back. Priced low because of the crack.", ["Crack on the back"]),
])
def test_a_part_that_points_back_is_a_flaw_only_where_nothing_else_says_it(description, flaws):
    assert code_reading(f"{PHONE}\n{description}")["flaws"] == flaws


# ── the Vinted test (23 Sep): the words it found missing, each with its look-alike (made up) ────────────────────

@pytest.mark.parametrize("line", [
    "Battery low", "Struggles to hold charge", "At first will take a long time to charge", "Battery may need a replacement",
    "Battery could do with servicing", "Battery probably won't last as long", "Face ID is disabled", "Loud speaker very low",
    "The speaker could do with a clean", "A new screen may be required", "Camera lens needing replacement", "Needs to get fixed",
    "Needs new front screen and back screen", "Water affected the screen display", "Back glass camera cover came off",
    "A really small bump in one of the top corners", "Screen has been changed with soft OLED", "Brand new display installed",
    "Well used", "Slight paint gone", "For spare parts or repair", "Ideal for someone looking to repair it",
    "Don't know whether they work", "Not sure if working anymore", "Running ios 9",
])
def test_the_vinted_words_are_flaws(line):
    text = f"{TITLE}\n{line}"
    assert flaws_in(line, text) and code_reading(text)["flaws"]


@pytest.mark.parametrize("line", [
    "Battery lasts all day", "Face ID works perfectly", "Screen protector can easily be removed or replaced if preferred",
    "Never had a screen replaced", "All original parts", "Original screen", "No visible signs of use", "iOS 18.4",
    "The blacked out mark in the photo is photo edited", "No charging cable", "Big camera bump", "Low price for a quick sale",
])
def test_the_vinted_look_alikes_are_none(line):
    assert read(line) == ([], [])


def test_gemmas_quote_with_the_sellers_words_left_out_is_the_sellers_whole_phrase():
    from flip.reader import as_written
    text = f"{TITLE}. Needs new front screen and back screen. Screen is not cracked."
    assert as_written("needs new back screen", text) == "Needs new front screen and back screen"
    assert as_written("Screen is cracked", text) == "Screen is not cracked"  # what's kept is the seller's: a denial
    assert as_written("Display has a small scratch", text) == "Display has a small scratch"  # made up: still fails


def test_gemmas_own_instruction_copied_into_a_flaw_is_taken_off():
    from flip.ai import Reply
    from flip.reader import tidied
    text = f"{TITLE}. The back glass is cracked across the logo."
    for copied, kept in [("each fault, damage, mark or sign of wear the listing mentions, copied word for word.", []),
                         ("each fault, damage, mark or sign of wear the phone has", []),
                         ("each fault, damage, mark or sign of wear the back glass is cracked across the logo",
                          ["the back glass is cracked across the logo"])]:
        reply = Reply("gemma3:4b", answer={"flaws": [copied], "pickup": "", "no_offers": ""})
        assert tidied(reply, text).answer["flaws"] == kept


@pytest.mark.parametrize("line, flaws", [
    ("Iphone 12 White | 64Gb | 79% Maximum Battery Capacity", ["79% Maximum Battery Capacity"]),  # "Maximum" between
    ("92% Maximum Battery Capacity", []),
    ("Apple iPhone SE 64GB Unlocked iOS 4.7in 8MP", []),  # a 4.7in screen, not iOS 4
    ("On iOS 15.8, the last it gets", ["On iOS 15.8"]),
])
def test_a_figure_read_whole(line, flaws):
    assert code_reading(f"{TITLE}\n{line}")["flaws"] == flaws
