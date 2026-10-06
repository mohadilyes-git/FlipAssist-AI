"""Where you collect from, 26 Sep red team (time-place-02, 03, 07, 08, 09, 10 and
v8-integration-8): the listing's place goes into your collecting sentence only
where it reads, never the seller's door, and the made-up place check and
names_places share one list of words that aren't places. Pretend models only."""

import pytest

from flip import message_drafter, reader, style
from flip.message_drafter import draft_message, said_place
from flip.reader import place
from flip.style import names_places, style_card
from flip.writer import collecting_from
from tests.fakes import FakeModel


def facebook(description):
    return {"id": "x", "title": "iPhone 13 128GB", "description": description, "asking_price": "200",
            "marketplace": "facebook"}


def card(*rows):
    """A style card from (message, asking price) rows, all sent on Facebook."""
    return style_card([{"my_message": text, "asking_price": asking, "marketplace": "facebook",
                        "listing_title": "iPhone 13"} for text, asking in rows])


def drafted(listing, past=None, pickup="", **kwargs):
    reading = {"flaws": [], "pickup": pickup, "no_offers": "", "read_by": "gemma3:4b"}
    return draft_message(listing, past, reading=reading, kind="lower", **kwargs)


def message(result):
    return (result.get("answer") or {}).get("message")


def problems(result):
    return [p for attempt in result["attempts"] for p in attempt["problems"]]


def ai(text):
    return FakeModel("gemma3:4b", {"message": text}, {"message": text})


LOWER3 = (("150", "180"), ("90", "110"), ("60", "80"))


# ── time-place-02: the place goes in only where it reads ────────────────────

BRADFORD = facebook("iPhone 13 128gb unlocked, fully wkg, bh 88%. Collection from Bradford BD7.")
NAMES_TOWNS = (("Hi mate, would you take £240? Can collect from Wakefield tonight.", "280"),
               ("Hi mate, would you take £100? Can collect from Halifax tonight.", "130"))


@pytest.mark.parametrize("closing, expected", [
    ("Can collect at yours today.", "Hi mate, would you take £170? Can collect at yours today."),
    ("Can collect this Saturday.", "Hi mate, would you take £170? Can collect from Bradford BD7 this Saturday."),
    ("Can collect the phone today.", "Hi mate, would you take £170? Can collect the phone from Bradford BD7 today."),
])
def test_the_listings_place_goes_where_it_reads_not_in_front_of_where_or_what(closing, expected):
    """time-place-02: "Can collect from Bradford BD7 at yours today.", "Can collect this from Bradford BD7 Saturday."."""
    past = card(*[(f"Hi mate, would you take £{p}? {closing}", a) for p, a in LOWER3], *NAMES_TOWNS)
    result = drafted(BRADFORD, past, "Bradford BD7", writer="template")
    assert (result["status"], result["writer"], message(result)) == ("ready", "template", expected)


def test_a_town_your_closing_names_is_never_joined_to_the_listings():
    """time-place-02: 'Can collect from Bradford BD7 in Leeds today.' got past the made-up place check; left as you
    wrote it, "Leeds" isn't the listing's, so it's refused, never sent with a second place."""
    past = card(*[(f"Hi mate, would you take £{p}? Can collect in Leeds today.", a) for p, a in LOWER3])
    result = drafted(BRADFORD, past, "Bradford BD7", writer="template")
    assert result["status"] == "needs you" and message(result) is None
    assert problems(result) == ["the message says it'll collect from a place the listing doesn't: Leeds"]


@pytest.mark.parametrize("closing, said", [
    ("Can collect today.", "Can collect from Leeds LS6 today."),
    ("Can collect it today.", "Can collect it from Leeds LS6 today."),
    ("I can come and collect.", "I can come and collect from Leeds LS6."),
    ("can collect 2nite", "can collect from Leeds LS6 2nite"),
    ("Can collect this evening.", "Can collect from Leeds LS6 this evening."),
    ("Can collect this today.", "Can collect this from Leeds LS6 today."),  # "this" is what's collected
    ("Can collect them tomorrow.", "Can collect them from Leeds LS6 tomorrow."),
    ("Can collect in person today.", "Can collect from Leeds LS6 in person today."),
    ("Can collect and pay cash.", "Can collect from Leeds LS6 and pay cash."),
    ("can collect x", "can collect from Leeds LS6 x"),
    ("Can collect at lunch.", "Can collect from Leeds LS6 at lunch."),
    # where it would clash or garble, the sentence stays as you wrote it
    ("Can collect at yours today.", "Can collect at yours today."),
    ("Can collect in Leeds today.", "Can collect in Leeds today."),
    ("Can collect today in Leeds.", "Can collect today in Leeds."),
    ("Can collect tonight at yours.", "Can collect tonight at yours."),
    ("Can collect it at yours.", "Can collect it at yours."),
    ("Can collect in town today.", "Can collect in town today."),
    ("Can collect the same day.", "Can collect the same day."),
    ("Where can I collect?", "Where can I collect?"),
    ("Can collect from yours today.", "Can collect from yours today."),
    ("Can pick it up today.", "Can pick it up today."),  # no "collect": as before
])
def test_collecting_from_reads_whats_after_collect(closing, said):
    assert collecting_from(closing, "Leeds LS6") == said


# ── time-place-03: never the seller's door ──────────────────────────────────

@pytest.mark.parametrize("line, said", [
    ("Collection from 78, Example Lane, Ilford.", "I can come and collect."),  # the reading keeps "78"
    ("Collection from Flat 2, 10 High St, Leeds.", "I can come and collect."),
    ("Pick up only Unit 4, Leeds Road Industrial Estate", "I can come and collect."),
    ("Collection from 12-14 High Street, Bradford", "I can come and collect."),
    ("Collection from Example Lane IG1 2AC", "I can come and collect from IG1."),  # the postcode's area alone
])
def test_alertflips_message_never_says_the_sellers_door_back(line, said):
    description = f"iPhone 13 128gb unlocked, fully wkg, bh 88%. {line}"
    pickup = place(line)
    assert pickup and reader.in_listing(pickup, description)  # what the reading hands the drafter
    result = drafted(facebook(description), None, pickup, writer="template")
    assert (result["status"], message(result)) == ("ready", f"Hi, would you take £170 cash for it? {said}")


@pytest.mark.parametrize("pickup, said", [
    ("78", ""), ("78 Example Lane", ""), ("Flat 2", ""), ("Unit 4", ""), ("12-14 High Street", ""), ("No. 5", ""),
    ("Ground floor flat", ""), ("Example Lane IG1 2AC", "IG1"),
    # a street name with no door is said as the listing gives it: these were "" here, which left out areas and stations
    # named the same way ("Liverpool Street station", "Ladbroke Grove"; second red team, 26 Sep, tp4-places-dropped)
    ("Example Lane", "Example Lane"), ("High St", "High St"),
    ("SE1 9CK", "SE1"), ("Leeds LS6 4AK", "Leeds LS6"),
    # places stay whole: "St" starting a name is a saint, "Bury St Edmunds" is a town
    ("Leeds LS6", "Leeds LS6"), ("Leeds city centre", "Leeds city centre"), ("St Albans", "St Albans"),
    ("Bury St Edmunds", "Bury St Edmunds"), ("Stoke-on-Trent", "Stoke-on-Trent"), ("Bethnal Green", "Bethnal Green"),
    ("Trafford Centre", "Trafford Centre"), ("Unity Works", "Unity Works"), ("Seven Sisters", "Seven Sisters"),
])
def test_the_pickup_is_said_as_its_area(pickup, said):
    assert said_place(pickup) == said


def test_a_full_postcode_is_said_as_its_area_by_your_own_sentences_too():
    placer = card(("Hi mate, would you take £150? Can collect today.", "180"),
                  ("Hi mate, would you take £90? Can collect today.", "110"), *NAMES_TOWNS)
    result = drafted(facebook("iPhone 13 fully wkg. Collection from Leeds LS6 4AK."), placer, "Leeds LS6 4AK",
                     writer="template")
    assert message(result) == "Hi mate, would you take £170? Can collect from Leeds LS6 today."


# ── time-place-07 and v8-integration-8: everyday words aren't made-up places

LEEDS_NO_PICKUP = facebook("iPhone 13 128gb unlocked, fully wkg, bh 88%. Collection Leeds.")


@pytest.mark.parametrize("closing", ["Can collect in person today.", "Can collect at ur convenience.",
                                     "Can collect at lunchtime.", "Can collect in person."])
def test_your_own_closing_with_an_everyday_word_is_sent(closing):
    """time-place-07: refused as made-up places "person", "ur", "lunchtime"."""
    past = card(*[(f"Hi, would you take £{p}? {closing}", a) for p, a in LOWER3])
    result = drafted(LEEDS_NO_PICKUP, past, writer="template")
    assert (result["status"], result["writer"], message(result)) == \
        ("ready", "template", f"Hi, would you take £170? {closing}")


@pytest.mark.parametrize("closing", ["Can collect in person today.", "Can collect at ur convenience."])
def test_the_ai_copying_your_closing_isnt_refused_for_it(closing):
    """time-place-07: with auto the AI's draft using your closing was refused twice, 'needs you'."""
    past = card(*[(f"Hi, would you take £{p}? {closing}", a) for p, a in LOWER3])
    result = drafted(LEEDS_NO_PICKUP, past, local=ai(f"Hi, would you take £170? {closing}"), writer="ai")
    assert (result["status"], result["writer"], message(result)) == \
        ("ready", "gemma3:4b", f"Hi, would you take £170? {closing}")


PLAIN = {"id": "x", "title": "iPhone 13 128GB Midnight", "description": "Good condition, unlocked, comes with box.",
         "asking_price": "200", "marketplace": "facebook"}


def wud_u(closing):
    return card(*[(f"hi wud u take £{p} cash? {closing}", a) for p, a in (("150", "180"), ("90", "110"), ("250", "300"))])


@pytest.mark.parametrize("closing", ["can collect at lunch", "can collect from urs", "can collect in evening",
                                     "Happy to collect in person.", "Can collect in half an hour.",
                                     "can collect from yours", "can collect today"])  # the last two: the controls
def test_the_drafters_place_check_reads_everyday_words_as_everyday(closing):
    """v8-integration-8: refused as the places "lunch", "urs", "evening", "person", "half"."""
    result = draft_message(PLAIN, wud_u(closing), kind="lower", writer="template")
    assert (result["status"], result["writer"]) == ("ready", "template") and problems(result) == []
    assert message(result).lower() == f"hi wud u take £170 cash? {closing.lower()}"
    if closing == "can collect at lunch":
        assert message(result) == "hi wud u take £170 cash? can collect at lunch"


def test_the_ai_copying_at_lunch_passes_and_a_made_up_town_in_lower_case_doesnt():
    """v8-integration-8: the AI that kept "can collect at lunch" was refused 4 times. A town still isn't."""
    lunch = draft_message(PLAIN, wud_u("can collect at lunch"), local=ai("hi wud u take £170 cash? can collect at lunch"),
                          kind="lower", writer="ai")
    assert (lunch["status"], message(lunch)) == ("ready", "hi wud u take £170 cash? can collect at lunch")
    town = draft_message(PLAIN, wud_u("can collect at lunch"), local=ai("hi wud u take £170 cash? can collect from rotherham"),
                         kind="lower", writer="ai")
    assert "the message says it'll collect from a place the listing doesn't: rotherham" in problems(town)


def test_one_list_of_words_that_arent_places():
    """The drafter's list had drifted from style's (no "ur", "lunch", "person"): it's the same list now."""
    assert message_drafter.NOT_A_PLACE is style.NOT_A_PLACE
    assert {"person", "public", "half", "whatever", "earliest", "convenience", "daylight", "teatime", "dinner", "few",
            "cash", "monday", "sat", "december", "six", "ur", "urs", "lunch"} <= style.NOT_A_PLACE


# ── time-place-08: when after the place isn't part of it ────────────────────

LEEDS_LS6 = facebook("iPhone 13 128gb unlocked, fully wkg, bh 88%. Collection from Leeds LS6.")


def test_a_day_after_the_listings_place_isnt_read_as_part_of_it():
    """time-place-08 (a): refused as the place "Leeds LS6 Saturday"."""
    past = card(*[(f"Hi mate, would you take £{p}? Can collect Saturday.", a) for p, a in LOWER3],
                ("Hi mate, would you take £240? Can collect from Bradford tonight.", "280"),
                ("Hi mate, would you take £100? Can collect from Wakefield tonight.", "130"))
    result = drafted(LEEDS_LS6, past, "Leeds LS6", writer="template")
    assert (result["status"], message(result)) == ("ready", "Hi mate, would you take £170? Can collect from Leeds LS6 Saturday.")


def test_2nite_after_the_listings_place_isnt_read_as_part_of_it():
    """time-place-08 (b): refused as the place "Leeds LS6 2nite"."""
    past = card(*[(f"hi wud u take £{p}? can collect 2nite", a) for p, a in LOWER3],
                ("hi wud u take £240? can pick up in rotherham 2nite", "280"),
                ("hi wud u take £100? can collect from bradford 2nite", "130"))
    result = drafted(LEEDS_LS6, past, "Leeds LS6", writer="template")
    assert (result["status"], message(result)) == ("ready", "hi wud u take £170? can collect from leeds ls6 2nite")


@pytest.mark.parametrize("tail", ["on Saturday.", "Saturday morning.", "ASAP.", "2moro", "this Saturday.", "tomorrow.",
                                  "at 6pm."])
def test_the_ais_place_then_when_is_accepted(tail):
    """time-place-08 (c): the AI's "Can collect from Leeds LS6 on Saturday." was refused twice."""
    past = card(("Hi mate, would you take £150? Can collect Saturday.", "180"),
                ("Hi mate, would you take £90? Can collect Saturday.", "110"))
    text = f"Hi mate, would you take £170? Can collect from Leeds LS6 {tail}"
    result = drafted(LEEDS_LS6, past, "Leeds LS6", local=ai(text), writer="ai")
    assert (result["status"], message(result)) == ("ready", text)


def test_a_made_up_place_before_a_day_is_still_refused():
    past = card(("Hi mate, would you take £150? Can collect Saturday.", "180"),
                ("Hi mate, would you take £90? Can collect Saturday.", "110"))
    result = drafted(LEEDS_LS6, past, "Leeds LS6", local=ai("Hi mate, would you take £170? Can collect from Bradford on "
                                                            "Saturday."), writer="ai")
    assert "the message says it'll collect from a place the listing doesn't: Bradford" in problems(result)


def test_from_a_day_is_no_place():
    """time-place-08's side note: your own "Can collect from Friday." was refused as the place "Friday"."""
    past = card(*[(f"Hi, is this still available? Would you take £{p} cash? Can collect from Friday.", a)
                  for p, a in (("150", "180"), ("90", "110"), ("240", "280"))])
    assert not past["names_places"]
    result = drafted(facebook("iPhone 13 128gb unlocked, fully wkg, bh 88%. Collection SE1 9CK."), past, "SE1 9CK",
                     writer="template")
    assert (result["status"], message(result)) == \
        ("ready", "Hi, is this still available? Would you take £170 cash? Can collect from Friday.")


# ── time-place-09: names_places counts places, not "in person" ──────────────

def test_collecting_in_person_isnt_naming_a_place():
    """time-place-09: 'Can collect from SE1 9CK in person today.' from someone who never names a place."""
    past = card(*[(f"Hi, is this still available? Would you take £{p} cash? Can collect in person today.", a)
                  for p, a in (("150", "180"), ("90", "110"), ("240", "280"))])
    assert not past["names_places"]
    result = drafted(facebook("iPhone 13 128gb unlocked, fully wkg, bh 88%. Collection SE1 9CK."), past, "SE1 9CK",
                     writer="template")
    assert (result["status"], message(result)) == \
        ("ready", "Hi, is this still available? Would you take £170 cash? Can collect in person today.")


@pytest.mark.parametrize("closing", ["Can come in half an hour.", "Happy to meet in public.", "Can collect at half 6.",
                                     "Can collect at whatever time suits.", "Can collect at six.", "Can collect from Monday.",
                                     "Can collect at ur earliest convenience.", "Can collect in December.",
                                     "Can collect at the Weekend.", "Can collect at Six Thirty."])
def test_everyday_words_after_collect_arent_places(closing):
    assert not names_places([f"Hi, would you take £150? {closing}"] * 2)


@pytest.mark.parametrize("texts", [
    ["Hi mate, would you take £150? Can collect from Leeds today.", "hi wud u take 90? can pick up in rotherham 2nite"],
    ["Happy to meet at McDonald's.", "Can collect from Seven Sisters."],  # a number that starts a name
    ["Can collect from the Trafford Centre.", "Can collect from the Arndale."],
])
def test_places_still_count(texts):
    assert names_places(texts)


@pytest.mark.parametrize("quote, found", [
    # the reading's pickup: a word of when or an everyday word is no place (flip.style's lists)
    ("Collection from next week", ""), ("Collection in public", ""), ("Collection at earliest convenience", ""),
    ("Collection from December", ""), ("Collection from Leeds 2nite", ""), ("Collection from here", ""),
    ("Collection from Leeds now", ""), ("collection from next door", ""),
    # ...and places with "the" or a number in them stay
    ("Collection from Seven Sisters", "Seven Sisters"), ("Collection from Bourton-on-the-Water", "Bourton-on-the-Water"),
    ("collection from rotherham", "Rotherham"), ("Collection from Stratford-upon-Avon", "Stratford-upon-Avon"),
    ("Collection from Leeds, weekdays only", "Leeds"),
])
def test_the_readings_pickup_shares_the_words_that_arent_places(quote, found):
    assert place(quote) == found


# ── time-place-10: a place said after the time, or with "Collection" ────────

def test_a_place_named_after_the_time_counts():
    """time-place-10: names_places was False, so the listing's place was left out."""
    past = card(*[(f"Hi mate, would you take £{p}? Can collect today.", a) for p, a in LOWER3],
                ("Hi mate, would you take £240? Can collect today from Headingley.", "280"),
                ("Hi mate, would you take £100? Can collect tonight from Bradford.", "130"),
                ("Hi mate, would you take £120? Collection from Wakefield is fine.", "140"))
    assert past["names_places"]
    result = drafted(LEEDS_LS6, past, "Leeds LS6", writer="template")
    assert (result["status"], message(result)) == ("ready", "Hi mate, would you take £170? Can collect from Leeds LS6 today.")


def test_a_made_up_place_after_the_time_is_refused():
    """time-place-10's related note: 'Can collect today from Wakefield.' on a Leeds LS6 listing was sent."""
    past = card(*[(f"Hi mate, would you take £{p}? Can collect today from Wakefield.", a) for p, a in LOWER3])
    result = drafted(LEEDS_LS6, past, "Leeds LS6", writer="template")
    assert result["status"] == "needs you"
    assert problems(result) == ["the message says it'll collect from a place the listing doesn't: Wakefield"]
