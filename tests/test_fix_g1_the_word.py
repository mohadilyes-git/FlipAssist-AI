"""The third red team's findings on "the" and the seller's words (26 Sep): with_the's "the" where the bare words were
right (a span, a feature's name, "of" + what a part describes), the bare parts it missed, the dust wording, how a flaw
happened said with its hedge, and AlertFlip's 250 characters counted before the "the"s code adds. Code only: no AI
is asked (a FakeModel that's never asked has no replies)."""

import pytest

from flip.message_drafter import draft_message
from flip.style import style_card
from flip.writer import flaw_phrase, reason_sentence, the_added, with_the, write_offer
from tests.fakes import FakeModel

# a "given the condition" style, as the red team's draft_probe.py has it
GIVEN = style_card([{"my_message": f"Hello, would you accept £{offer} given the condition? Thanks", "asking_price": asking}
                    for offer, asking in (("150", "200"), ("90", "120"), ("300", "380"))])
# ...and as cause-done-split/repro.py has it
GIVEN_MATE = style_card([{"my_message": f"Hi mate, would you take £{offer} given the condition? Can collect today.",
                          "asking_price": asking, "marketplace": "facebook", "listing_title": "iPhone 13"}
                         for offer, asking in (("150", "200"), ("90", "120"), ("300", "380"))])


def drafted(title, description, flaws=None, asking="200", card=None, kind="lower", market="facebook", pickup="",
            local=None):
    """draft_message with no AI, as the red team ran it: flaws are the reader's quotes, None for code's own reading."""
    listing = {"id": "x", "title": title, "description": description, "asking_price": asking, "marketplace": market}
    reading = None if flaws is None else {"flaws": flaws, "pickup": pickup, "no_offers": "", "read_by": "gemma3:4b"}
    # Say the flaw: Yes, as you'd pick it on the message (14 Oct: whether you give it isn't learned from your style)
    return draft_message(listing, card=card, local=local, api=None, kind=kind, reading=reading, mention=True)


def message(result):
    return (result["answer"] or {}).get("message")


# ── the-word-1: no "the" after the "to" that closes a span ──────────────────

@pytest.mark.parametrize("part, phrase", [
    ("small crack across screen from corner to corner", "the small crack across the screen from corner to corner"),
    ("Crack from top to bottom on the back", "the crack from top to bottom on the back"),
    ("line on screen from left to right", "the line on the screen from left to right"),
    ("scratches front to back", "the scratches front to back"),
    ("Scuffs back to front on the frame", "the scuffs back to front on the frame"),
    ("crack goes from top left to bottom right", "the crack goes from top left to bottom right"),
    ("scratch runs right to left across the back", "the scratch runs right to left across the back"),
    ("Light marks all round the frame, edge to edge", "the light marks all round the frame, edge to edge"),
    ("small marks from top to bottom of the screen", "the small marks from top to bottom of the screen"),
    ("scratch running from corner to corner of screen", "the scratch running from corner to corner of the screen"),
    # the verifier of the-word-7: a span with "by" ("side by side") once "by" takes a "the"
    ("two hairline cracks side by side on back", "two hairline cracks side by side on the back"),
    # controls: a "to" that isn't a span's far end keeps its "the"
    ("damage to back", "the damage to the back"),
    ("small scratch next to camera", "the small scratch next to the camera"),
    ("crack close to camera", "the crack close to the camera"),
    ("small crack on corner to left of camera", "the small crack on the corner to the left of the camera"),
])
def test_a_span_ends_as_the_seller_says_it(part, phrase):
    assert flaw_phrase(part) == phrase


def test_a_span_in_alertflips_message_and_your_given_style():
    description = "fully wkg, bh 84%. small crack across screen from corner to corner but touch fine"
    quote = ["small crack across screen from corner to corner"]
    alertflip = drafted("iPhone 12 64gb", description, quote)
    assert message(alertflip) == "Hi, would you take £170 cash for it? I'm offering that because of the small crack " \
                                 "across the screen from corner to corner. I can come and collect."
    yours = drafted("iPhone 12 64gb", description, quote, card=GIVEN)
    assert message(yours) == "Hello, would you accept £170 given the small crack across the screen from corner to " \
                             "corner? Thanks"
    # code's own reading, as the finder's second example
    told = drafted("iPhone 13 128GB Midnight", "Crack from top to bottom on the back, works perfect", asking="220")
    assert "because of the crack from top to bottom on the back." in message(told)


# ── the-word-2: a feature's name stays whole ────────────────────────────────

@pytest.mark.parametrize("part, phrase", [
    ("Always on display not working", "that the always on display is not working"),
    ("always-on display flickers", "that the always-on display flickers"),
    ("Under display camera has a small mark", "that the under display camera has a small mark"),
    ("under display fingerprint sensor not working", "that the under display fingerprint sensor is not working"),
    ("Built in camera not working", "that the built in camera is not working"),
    ("Built-in camera not working", "that the built-in camera is not working"),
    ("some letters on screen keyboard dont work", "that some letters on screen keyboard dont work"),
    # a shop's display, not the phone's screen
    ("Light scratches from being on display in store", "the light scratches from being on display in store"),
    ("light marks from being on display", "the light marks from being on display"),
    # the verifier's: a name whose "on" isn't a part's
    ("power on button sticks", "that the power on button sticks"),
    # controls: the display, the screen and a camera's sensor are still parts
    ("small scratch on display", "the small scratch on the display"),
    ("small crack is on display", "that the small crack is on the display"),
    ("Fingerprint under screen doesn't work", "that the fingerprint under the screen doesn't work"),
    ("scratch underneath screen protector", "the scratch underneath the screen protector"),
    ("Mute switch on side doesn't work", "that the mute switch on the side doesn't work"),
])
def test_a_features_name_keeps_its_own_words(part, phrase):
    assert flaw_phrase(part) == phrase


def test_a_features_name_in_alertflips_message_and_the_ais_rewrite():
    told = drafted("iPhone 14 Pro 256GB", "Always on display not working, everything else perfect", asking="450")
    assert message(told) == "Hi, would you take £380 cash for it? I'm offering that because the always on display " \
                            "is not working. I can come and collect."
    fold = drafted("Samsung Galaxy Z Fold 4 256GB", "Unlocked to all networks. Under display camera has a small mark, "
                   "inner screen perfect. Comes with box.", ["Under display camera has a small mark"])
    assert "because the under display camera has a small mark." in message(fold)
    shop = drafted("iPhone 15 128GB ex display", "Ex display phone. Light scratches from being on display in store. "
                   "Battery 100%.", ["Light scratches from being on display in store"])
    assert "because of the light scratches from being on display in store." in message(shop)
    # the AI path with no style: code's reason sentence after the AI's words, and the draft the rewrite prompt quotes
    listing = {"id": "x", "title": "iPhone 14 Pro 256GB Deep Purple", "asking_price": "200", "marketplace": "facebook",
               "description": "Phone is in good condition. Always on display not working since update, everything "
                              "else fine. Collection only Bradford."}
    reading = {"flaws": ["Always on display not working"], "pickup": "", "no_offers": "", "read_by": "gemma3:4b"}
    first = message(draft_message(listing, kind="lower", mention=True, reading=reading))
    assert "the always on display is not working" in first
    asked = {"message": "Hi, is this still for sale? Would you accept £170 for it?"}
    local = FakeModel("gemma3:4b", asked, asked)
    again = draft_message(listing, local=local, kind="lower", mention=True, reading=reading, rewrite_of=first)
    assert message(again) == "Hi, is this still for sale? Would you accept £170 for it? I'm offering that because " \
                             "the always on display is not working. I can pay cash and come and collect it."
    assert "the always on the display" not in local.asked[0]["user"]


# ── the-word-3: dust is said with its verb, in lower case, cut at the part ──

@pytest.mark.parametrize("part, phrase", [
    ("small bit of dust under camera lens", "that there's dust under the camera lens"),
    ("Dust inside back camera", "that there's dust inside the back camera"),
    ("There is dust in the camera", "that there's dust in the camera"),
    ("tiny bit of dust inside front camera x", "that there's dust inside the front camera"),
    ("Some dust behind the lens", "that there's dust behind the lens"),
    ("Dust has got into the back camera", "that there's dust inside the back camera"),
    ("dust in charging port", "that there's dust in the charging port"),
    ("DUST IN BACK CAMERA", "that there's dust in the back camera"),
    ("dust inside my camera", "that there's dust inside the camera"),  # the seller's "my" isn't yours
    # the verifier's: the aside after the place went too
    ("dust particle inside main camera lens, doesnt affect photos", "that there's a dust particle inside the main "
                                                                     "camera lens"),
    ("dust spots in camera", "that there are dust spots in the camera"),  # the seller's word for it stays
    # dust in something that isn't a part is said as the seller says it, or by the AI
    ("Rear camera has dust inside", "that the rear camera has dust inside"),
    ("dust in between keys", None),
    ("Dust in camera and a scratch on screen", None),  # one of these with another flaw: the AI words it
])
def test_dust_inside_is_said_with_its_verb(part, phrase):
    assert flaw_phrase(part) == phrase


def test_dust_in_alertflips_message_and_your_given_style():
    lens = drafted("iPhone 12 64gb", "small bit of dust under camera lens, otherwise mint",
                   ["small bit of dust under camera lens"], asking="180")
    assert message(lens) == "Hi, would you take £150 cash for it? I'm offering that because there's dust under the " \
                            "camera lens. I can come and collect."
    description = "Dust inside back camera, photos still ok. Battery 86%"
    yours = drafted("iPhone 13 Pro 128GB", description, ["Dust inside back camera"], asking="300", card=GIVEN)
    assert message(yours) == "Hello, would you accept £255 given that there's dust inside the back camera? Thanks"
    told = drafted("iPhone 13 Pro 128GB", description, asking="300")  # code's own reading
    assert "because there's dust inside the back camera." in message(told)
    assert reason_sentence({"about": "flaw", "says": ["Dust inside back camera", "battery 84%"]}) == \
        "I'm offering that because there's dust inside the back camera and the battery health is 84%."


# ── the-word-4: after "of", a part that says what kind of flaw it is ─────────

@pytest.mark.parametrize("part, phrase", [
    ("slight signs of screen burn", "the slight signs of screen burn"),
    ("Bit of screen burn on keyboard", "a bit of screen burn on the keyboard"),
    ("a bit of case wear", "a bit of case wear"),
    ("small piece of glass missing on back", "the small piece of glass missing on the back"),
    ("loads of screen scratches", "loads of screen scratches"),
    ("tiny amount of screen bleed at bottom", "the tiny amount of screen bleed at the bottom"),
    ("bit of frame wear on corners", "a bit of frame wear on the corners"),
    ("lots of back glass cracks", "lots of back glass cracks"),
    ("chip of glass missing in corner", "the chip of glass missing in the corner"),
    # controls: a part that's the place keeps its "the"
    ("bit of back glass missing", "a bit of the back glass missing"),
    ("crack at bottom of screen", "the crack at the bottom of the screen"),
    ("some wear on corners of case", "some wear on the corners of the case"),
    ("signs of wear on the frame", "the signs of wear on the frame"),
])
def test_a_part_that_says_the_kind_of_flaw_gets_no_the(part, phrase):
    assert flaw_phrase(part) == phrase


def test_screen_burn_in_alertflips_message():
    burn = drafted("iPhone XS 64GB", "slight signs of screen burn, otherwise works perfect",
                   ["slight signs of screen burn"], asking="90")
    assert message(burn) == "Hi, would you take £75 cash for it? I'm offering that because of the slight signs of " \
                            "screen burn. I can come and collect."
    wear = drafted("iPhone 12 Pro 128GB", "a bit of case wear on the frame. 85% battery", ["a bit of case wear"],
                   asking="250")
    assert "because of a bit of case wear." in message(wear)


# ── the-word-5: the 250 characters are counted before the "the"s code adds ──

LONG = {"title": "iPhone 13 Pro Max 256GB Sierra Blue",
        "description": "Small crack on back at bottom left corner near camera. Light scratches on screen and scuffs "
                       "on frame and on corners. Collection from Leeds LS6",
        "flaws": ["Small crack on back at bottom left corner near camera",
                  "Light scratches on screen and scuffs on frame and on corners"]}


def test_alertflips_own_message_isnt_refused_for_the_thes_code_adds():
    """256 characters with the "the"s, 232 as the seller wrote it: sent as written, with no model asked and the
    pickup place kept (it was refused, and the AI's version lost "from Leeds LS6")."""
    local = FakeModel("gemma3:4b")  # no replies: asking it would fail
    result = drafted(LONG["title"], LONG["description"], LONG["flaws"], asking="520", pickup="Leeds LS6", local=local)
    assert (result["status"], result["writer"], local.asked) == ("ready", "template", [])
    assert message(result) == "Hi, would you take £440 cash for it? I'm offering that because of the small crack on " \
                              "the back at the bottom left corner near the camera and the light scratches on the " \
                              "screen and scuffs on the frame and on the corners. I can come and collect from Leeds LS6."
    assert len(message(result)) == 256


def test_a_message_too_long_even_as_the_seller_wrote_it_is_still_refused():
    flaws = ["noticeable crack across back glass from bottom right corner towards camera lens",
             "several light scratches across screen and heavier scuffs along frame edges"]
    result = drafted("iPhone 13 Pro Max 256GB Sierra Blue", ". ".join(flaws) + ". Collection from Leeds LS6", flaws,
                     asking="520", pickup="Leeds LS6")
    assert result["status"] == "needs you"
    assert result["attempts"][0]["problems"] == ["the message is 280 characters: a usual one is under 262"]


def test_the_thes_added_are_measured_against_the_same_message_without_them():
    point = {"about": "flaw", "says": LONG["flaws"]}
    write = lambda: write_offer({}, "lower", 44000, point, pickup="Leeds LS6", in_person=True)  # noqa: E731
    assert the_added(write(), write) == 24  # six "the"s
    assert the_added("Hi, would you take £440 for it? I'm offering that because of the crack on the back.",
                     lambda: "Hi, would you take £440 for it? I'm offering that because of the crack.") == 0
    assert the_added(None, write) == 0
    assert with_the("crack on back") == "crack on the back"  # with_the is itself again afterwards


# ── the-word-6: the "on" of "won't turn on" isn't a part's ──────────────────

@pytest.mark.parametrize("phrase, said", [  # with_the alone: splitting the run-on is the split's (the-word-6)
    ("that it wont turn on screen cracked", "that it wont turn on screen cracked"),
    ("that it doesnt turn on screen is smashed", "that it doesnt turn on screen is smashed"),
    ("that it comes on screen flickers", "that it comes on screen flickers"),
    ("that it wont switch on back cracked", "that it wont switch on back cracked"),
    ("that it shuts down screen goes black", "that it shuts down screen goes black"),
    # controls: a light or a switch on a part is still there
    ("that the flash light on back doesn't work", "that the flash light on the back doesn't work"),
    ("that the mute switch on side is stuck", "that the mute switch on the side is stuck"),
])
def test_a_verbs_on_gets_no_the(phrase, said):
    assert with_the(phrase) == said


# ── the-word-7: the bare parts with_the missed ───────────────────────────────

@pytest.mark.parametrize("part, reason", [
    ("scratches all over back", "because of the scratches all over the back."),
    ("small chip by camera", "because of the small chip by the camera."),
    ("line down screen from top", "because of the line down the screen from top."),
    ("crack in middle of screen", "because of the crack in the middle of the screen."),
    ("Marks on back of phone", "because of the marks on the back of the phone."),
    ("Small crack on back by camera", "because of the small crack on the back by the camera."),
    ("scuffs on charging case", "because of the scuffs on the charging case."),
    ("dent on power button", "because of the dent on the power button."),
    ("small scratch on cover screen", "because of the small scratch on the cover screen."),
    ("left AirPod won't charge in case", "because the left AirPod won't charge in the case."),
    ("dent between screen and frame", "because of the dent between the screen and frame."),
    ("scratch underneath screen protector", "because of the scratch underneath the screen protector."),
    ("dead pixel in centre of screen", "because of the dead pixel in the centre of the screen."),
])
def test_the_parts_it_missed_get_their_the(part, reason):
    assert reason_sentence({"about": "flaw", "says": [part]}) == f"I'm offering that {reason}"


@pytest.mark.parametrize("part, phrase", [  # controls the finder and the verifier named
    ("has round corners scratched", "that it has round corners scratched"),  # no "round": not "the corners"
    ("Mic doesn't work on phone calls", "that the mic doesn't work on phone calls"),  # "phone" only after "of"
    ("volume down button doesn't work", "that the volume down button doesn't work"),  # a button's name
    ("small scratches side by side on screen", "the small scratches side by side on the screen"),
])
def test_the_new_parts_and_prepositions_leave_these_as_they_are(part, phrase):
    assert flaw_phrase(part) == phrase


@pytest.mark.parametrize("phrase, said", [
    ("kept in case since new", "kept in case since new"),
    ("always kept in case", "always kept in case"),
    ("just in case", "just in case"),
    ("doesn't sit in case properly", "doesn't sit in the case properly"),
    ("screen upside down", "screen upside down"),
    ("marks on back of phone case", "marks on the back of phone case"),
])
def test_in_case_and_phone_get_the_only_as_parts(phrase, said):
    assert with_the(phrase) == said


# ── cause-done-split-3: the hedge or denial before the cause goes with it ────

@pytest.mark.parametrize("part, phrase", [
    ("Few marks probably from the case", "a few marks"),
    ("Small crack on screen not due to a drop", "the small crack on the screen"),
    ("Crack on the back isn't from a drop", "the crack on the back"),
    ("Dent on corner possibly from a drop", "the dent on the corner"),
    ("Few scuffs on the corners, from the case", "a few scuffs on the corners"),
    ("Light scratches on the screen, from normal use", "the light scratches on the screen"),
    ("Light scratches on screen probably from keys", "the light scratches on the screen"),
    ("small scuff on the corner prob from the case", "the small scuff on the corner"),
    ("few marks on frame most likely from the case", "a few marks on the frame"),
    ("scratches are from normal use", "the scratches"),
    ("marks on back (from case)", "the marks on the back"),
    ("small dent on corner, possibly from a drop", "the small dent on the corner"),
    # as before (26 Sep blind review)
    ("Marks on frame from case", "the marks on the frame"),
    ("Screen damaged from a drop", "that the screen is damaged"),
])
def test_how_it_happened_goes_with_its_hedge(part, phrase):
    assert flaw_phrase(part) == phrase


def test_how_it_happened_goes_in_the_messages():
    def sent(description, card=None, market="facebook", flaws=None):
        return message(drafted("iPhone 13 128GB", description, flaws, card=card, market=market))
    assert sent("Few marks probably from the case. Battery 91%") == "Hi, would you take £170 cash for it? I'm " \
        "offering that because of a few marks. I can come and collect."
    assert sent("Small crack on screen not due to a drop", GIVEN_MATE) == "Hi mate, would you take £170 given the " \
        "small crack on the screen? Can collect today."
    assert "because of the crack on the back." in sent("Crack on the back isn't from a drop, it just appeared")
    assert "because of the dent on the corner." in sent("Dent on corner possibly from a drop. Screen perfect")
    assert sent("iPhone 12 64GB. Few scuffs on the corners, from the case. Face ID works", market="vinted",
                flaws=["Few scuffs on the corners, from the case"]) == "Hi, would you take £170 for it? I'm offering " \
        "that because of a few scuffs on the corners."


# ── cause-done-split-4: "through the case" says where or when, so it stays ──

@pytest.mark.parametrize("part, phrase", [
    ("Wireless charging doesn't work through the case", "that the wireless charging doesn't work through the case"),
    ("Doesn't charge wirelessly through a case", "that it doesn't charge wirelessly through a case"),
    ("Crack running through the case", "the crack running through the case"),
    ("Hairline crack running through the case", "the hairline crack running through the case"),
    ("Left AirPod doesn't charge from the case", "that the left AirPod doesn't charge from the case"),  # a fault's when
    # after a mark, "due to the case" is how it happened, as "from the case" is: it goes (red team 4, the-word-r4-5,
    # 26 Sep; this said "...due to the case", pinning the regression)
    ("Marks on frame due to the case", "the marks on the frame"),
    # "through" use or wear is still how it happened
    ("scratches through normal use", "the scratches"),
    ("wear on frame through normal use", "the wear on the frame"),
])
def test_through_the_case_isnt_how_it_happened(part, phrase):
    assert flaw_phrase(part) == phrase


def test_through_the_case_in_the_messages():
    told = drafted("iPhone 14 128GB", "Wireless charging doesn't work through the case, charges fine with a cable")
    assert message(told) == "Hi, would you take £170 cash for it? I'm offering that because the wireless charging " \
                            "doesn't work through the case. I can come and collect."
    asking = drafted("iPhone 14 128GB", "Doesn't charge wirelessly through a case, cable charging fine", card=GIVEN_MATE,
                     kind="asking")
    assert message(asking) == "Hi mate, I can pay £200. I don't mind that it doesn't charge wirelessly through a " \
                              "case. Can collect today."
    airpods = drafted("AirPods Pro 2", "AirPods Pro 2nd gen. Crack running through the case but charges fine")
    assert message(airpods) == "Hi, would you take £170 cash for it? I'm offering that because of the crack running " \
                               "through the case. I can come and collect."
