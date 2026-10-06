"""The fourth red team's findings on "the" and the seller's words (26 Sep), most of them made by the third red team's
fixes: a foldable's "inside screen" said "the inside the screen", what dust does cut off, a span's rule firing on "on
back to right side", the name and verb guards dropping a right "the", "due to the case" kept, and the subject left
before how it happened ("because of the scuffs on the frame they."). The findings' own inputs and the verifiers'
controls. Code only: no AI is asked (a FakeModel that's never asked has no replies)."""

import pytest

from flip.message_drafter import draft_message
from flip.reader import read_listing_with_ai
from flip.style import style_card
from flip.writer import flaw_phrase, reason_sentence, with_the
from tests.fakes import FakeModel

# a "given the condition" style, as the red team's draft_probe.py has it
GIVEN = style_card([{"my_message": f"Hello, would you accept £{offer} given the condition? Thanks",
                     "asking_price": asking} for offer, asking in (("150", "200"), ("90", "120"), ("300", "380"))])


def drafted(title, description, flaws=None, asking="200", card=None, kind="lower", market="facebook", local=None):
    """draft_message with no AI, as the red team ran it: flaws are the reader's quotes, None for code's own reading."""
    listing = {"id": "x", "title": title, "description": description, "asking_price": asking, "marketplace": market}
    reading = None if flaws is None else {"flaws": flaws, "pickup": "", "no_offers": "", "read_by": "gemma3:4b"}
    return draft_message(listing, card=card, local=local, api=None, kind=kind, reading=reading,
                         **({"mention": True} if flaws is not None else {}))


def read_and_drafted(title, description, quotes, asking="200", card=None):
    """The production path: a reader model's quotes through read_listing_with_ai, then draft_message (no AI writer)."""
    listing = {"id": "x", "title": title, "description": description, "asking_price": asking, "marketplace": "facebook"}
    reader = FakeModel("flip-reader-5", {"flaws": quotes, "pickup": "", "no_offers": ""})
    reading = read_listing_with_ai(listing, reader)
    return draft_message(listing, card=card, local=None, api=None, kind="lower", mention=True,
                         reading={k: reading[k] for k in ("flaws", "pickup", "no_offers", "read_by")})


def message(result):
    return (result["answer"] or {}).get("message")


def reason(part):
    return reason_sentence({"about": "flaw", "says": [part]})


# ── the-word-r4-1: a part's own name keeps its words ("the inside screen") ──

@pytest.mark.parametrize("part, said", [
    ("inside screen cracked", "because the inside screen is cracked."),
    ("small crack on the inside screen", "because of the small crack on the inside screen."),  # the seller's own "the"
    ("Inside Display doesn't work", "because the inside Display doesn't work."),
    ("Inside screen protector lifting at the crease", "because of the inside screen protector lifting at the crease."),
    ("small scratch on inside screen near hinge", "because of the small scratch on inside screen near the hinge."),
    ("Inside display has a few dead pixels on the left side", "because the inside display has a few dead pixels on "
                                                               "the left side."),
    ("inside screen flickers sometimes", "because the inside screen flickers sometimes."),
    ("inside lid has a few marks", "because the inside lid has a few marks."),
    ("inside camera has a small mark", "because the inside camera has a small mark."),
    ("underneath screen protector scratched", "because the underneath screen protector is scratched."),
    ("the only down side is a small chip on frame", "because the only down side is a small chip on the frame."),
    # the verifier's
    ("Inside display cracked near the hinge", "because of the inside display cracked near the hinge."),
    ("inside screen dead", "because the inside screen is dead."),
    ("inside lid has keyboard marks on screen", "because the inside lid has keyboard marks on the screen."),
    ("slightly two black spots on the inside screen", "because of the slightly two black spots on the inside screen."),
    # a downside in two words, however it's said
    ("one down side is a small scratch on back", "because one down side is a small scratch on the back."),
    ("the only down side to it is a scratch on back", "because the only down side to it is a scratch on the back."),
    # ...and "near" after "the" is a name too ("the near the side" on every build before)
    ("dent on the near side", "because of the dent on the near side."),
])
def test_a_parts_own_name_keeps_its_words(part, said):
    assert reason(part) == f"I'm offering that {said}"


@pytest.mark.parametrize("part, said", [  # controls: these still get their "the"
    ("scratch underneath screen protector", "because of the scratch underneath the screen protector."),
    ("line down screen from top", "because of the line down the screen from top."),
    ("crack down side of screen", "because of the crack down the side of the screen."),
    ("line down side", "because of the line down the side."),
    ("small scratch on cover screen", "because of the small scratch on the cover screen."),
    ("screen protector has a crack in middle", "because the screen protector has a crack in the middle."),
])
def test_a_place_still_gets_its_the(part, said):
    assert reason(part) == f"I'm offering that {said}"


def test_inside_is_no_place_with_the():
    # a listing's "inside screen" is a foldable's inner screen: the seller's words stay, never "inside the screen"
    assert with_the("the scratch inside screen") == "the scratch inside screen"
    assert with_the("the paint peeled on inside front") == "the paint peeled on inside front"
    assert with_the("the underneath screen protector") == "the underneath screen protector"
    assert with_the("the scratch underneath screen protector") == "the scratch underneath the screen protector"


def test_a_foldables_inside_screen_in_alertflips_message_and_your_given_style():
    description = "inside screen cracked but still works with touch. outer screen perfect. collection only"
    told = drafted("Samsung Galaxy Z Fold 4 256gb unlocked", description, asking="250")  # code's own reading
    assert message(told) == "Hi, would you take £210 cash for it? I'm offering that because the inside screen is " \
                            "cracked. I can come and collect."
    yours = drafted("Samsung Galaxy Z Fold 4 256gb unlocked", description, ["inside screen cracked"], asking="250",
                    card=GIVEN)
    assert message(yours) == "Hello, would you accept £210 given that the inside screen is cracked? Thanks"
    seller_the = drafted("Samsung Galaxy Z Fold 3 256GB", "small crack on the inside screen, cover screen fine. "
                         "collection only Leeds", ["small crack on the inside screen"], asking="220")
    assert message(seller_the) == "Hi, would you take £185 cash for it? I'm offering that because of the small crack " \
                                  "on the inside screen. I can come and collect."
    display = drafted("Samsung Galaxy Z Fold 3 256GB", "Inside Display doesn't work, cover screen works fine. Sold as "
                      "seen", asking="120")
    assert "because the inside Display doesn't work." in message(display)
    produced = read_and_drafted("Samsung Galaxy Z Fold 4 256gb", "inside screen cracked but still works with touch. "
                                "outer screen perfect", ["inside screen cracked"])
    assert (produced["status"], message(produced)) == ("ready", "Hi, would you take £170 cash for it? I'm offering "
                                                       "that because the inside screen is cracked. I can come and "
                                                       "collect.")


def test_the_ais_rewrite_isnt_shown_the_inside_the_screen():
    listing = {"id": "x", "title": "Samsung Galaxy Z Fold 4 256gb unlocked", "asking_price": "200",
               "marketplace": "facebook", "description": "inside screen cracked but still works with touch. outer "
                                                         "screen perfect"}
    reading = {"flaws": ["inside screen cracked"], "pickup": "", "no_offers": "", "read_by": "gemma3:4b"}
    first = message(draft_message(listing, kind="lower", mention=True, reading=reading))
    asked = {"message": "Hi, is this still for sale? Would you accept £170 for it?"}
    local = FakeModel("gemma3:4b", asked, asked)
    again = draft_message(listing, local=local, kind="lower", mention=True, reading=reading, rewrite_of=first)
    assert message(again) == "Hi, is this still for sale? Would you accept £170 for it? I'm offering that because " \
                             "the inside screen is cracked. I can pay cash and come and collect it."
    assert "inside the screen" not in local.asked[0]["user"]


# ── the-word-r4-2: what the dust does stays, in its words ──────────────────

@pytest.mark.parametrize("part, phrase", [
    ("dust in charging port stops it charging", "that dust in the charging port stops it charging"),
    ("Dust in lens shows on photos", "that dust in the lens shows on photos"),
    ("dust in the front camera makes selfies blurry", "that dust in the front camera makes selfies blurry"),
    ("dust in camera makes pictures a bit blurry", "that dust in the camera makes pictures a bit blurry"),
    ("dust in camera affects photos", "that dust in the camera affects photos"),
    ("Dust in Face ID camera", "that there's dust in the Face ID camera"),  # the name keeps its capitals
    # in the seller's words for it, whatever their capitals, with its kiss and aside left out
    ("dust spots in camera show on photos", "that dust spots in the camera show on photos"),
    ("a dust particle in lens shows on pics", "that a dust particle in the lens shows on pics"),
    ("DUST IN LENS SHOWS ON PHOTOS", "that dust in the lens shows on photos"),
    ("dust in lens shows on photos x", "that dust in the lens shows on photos"),
    ("dust in usb-c port stops it charging", "that dust in the USB-C port stops it charging"),
    # a verb isn't a place: "the lens makes camera" was the place on the third red team's fix
    ("dust in lens makes camera blurry", "that dust in the lens makes camera blurry"),
    ("dust in charging port stops phone charging", "that dust in the charging port stops phone charging"),
])
def test_what_the_dust_does_stays(part, phrase):
    assert flaw_phrase(part) == phrase


@pytest.mark.parametrize("part, phrase", [
    # as before: an aside after a comma, a denial, a clause with more in it
    ("Dust inside back camera", "that there's dust inside the back camera"),
    ("dust particle inside main camera lens, doesnt affect photos", "that there's a dust particle inside the main "
                                                                     "camera lens"),
    ("dust in charging port, charges fine", "that there's dust in the charging port"),
    ("dust in camera makes no difference to photos", "that there's dust in the camera"),
    ("Dust in back camera lens shows in photos but doesnt affect quality", "that there's dust in the back camera lens"),
    ("dust in the main camera which blurs photos slightly", "that there's dust in the main camera"),
    # "makes" only with what it makes them: code's own 8-word quote can stop short of it
    ("of dust in the lens makes photos a bit", "that there's dust in the lens"),
    ("dust in the speaker makes it quiet", "that there's dust in the speaker"),
    # another flaw run on after it: no plain wording, the AI words it
    ("dust in lens makes photos blurry screen cracked", None),
    ("Dust in camera and a scratch on screen", None),
])
def test_dust_is_said_alone_when_what_follows_isnt_what_it_does(part, phrase):
    assert flaw_phrase(part) == phrase


def test_what_the_dust_does_in_alertflips_message_and_your_given_style():
    description = "dust in charging port stops it charging, works on wireless charger. battery 86%"
    quote = ["dust in charging port stops it charging"]
    alertflip = drafted("iPhone 12 64gb", description, quote, asking="160")
    assert message(alertflip) == "Hi, would you take £135 cash for it? I'm offering that because dust in the " \
                                 "charging port stops it charging. I can come and collect."
    yours = drafted("iPhone 12 64gb", description, quote, asking="160", card=GIVEN)
    assert message(yours) == "Hello, would you accept £135 given that dust in the charging port stops it " \
                             "charging? Thanks"
    lens = "Dust in lens shows on photos 📷 otherwise great phone"
    for flaws in (None, ["Dust in lens shows on photos"]):  # code's own reading, and the reader's quote
        told = drafted("iPhone 11 Pro", lens, flaws, asking="170")
        assert message(told) == "Hi, would you take £140 cash for it? I'm offering that because dust in the lens " \
                                "shows on photos. I can come and collect."
    selfies = drafted("iPhone 13 128gb blue", "dust in the front camera makes selfies blurry, back camera fine. no "
                      "offers below 250", ["dust in the front camera makes selfies blurry"], asking="280")
    assert "because dust in the front camera makes selfies blurry." in message(selfies)
    produced = read_and_drafted("iPhone 11 Pro", lens, ["Dust in lens shows on photos"])
    assert "because dust in the lens shows on photos." in message(produced)
    # a second flaw after "and" is split off and said too
    assert reason("dust in lens shows on photos and small crack on back") == "I'm offering that because of the small " \
        "crack on the back and because dust in the lens shows on photos."


# ── the-word-r4-3: "on back to right side" is a place, then which way ───────

@pytest.mark.parametrize("part, phrase", [
    ("small mark on back to right side", "the small mark on the back to the right side"),
    ("crack on back to left", "the crack on the back to the left"),
    ("scratches across back to left side", "the scratches across the back to the left side"),
    ("chip on edge to bottom", "the chip on the edge to the bottom"),
    ("scratch along edge to corner", "the scratch along the edge to the corner"),
    ("crack at bottom to right", "the crack at the bottom to the right"),
    # controls: a span still ends as the seller says it
    ("small crack across screen from corner to corner", "the small crack across the screen from corner to corner"),
    ("crack goes from top left to bottom right", "the crack goes from top left to bottom right"),
    ("crack on top left to bottom right", "the crack on the top left to bottom right"),
    ("small marks from top to bottom of the screen", "the small marks from top to bottom of the screen"),
    ("scratches on back from top to bottom", "the scratches on the back from top to bottom"),
    ("two hairline cracks side by side on back", "two hairline cracks side by side on the back"),
    ("Light marks all round the frame, edge to edge", "the light marks all round the frame, edge to edge"),
    ("chip on corner to left of camera", "the chip on the corner to the left of the camera"),
])
def test_a_placed_part_starts_no_span(part, phrase):
    assert flaw_phrase(part) == phrase


def test_a_placed_part_in_alertflips_message():
    told = drafted("iPhone 12 64gb", "small mark on back to right side, screen mint", ["small mark on back to right "
                                                                                       "side"])
    assert message(told) == "Hi, would you take £170 cash for it? I'm offering that because of the small mark on the " \
                            "back to the right side. I can come and collect."


# ── the-word-r4-4: "always" names the display only, "left" is a side ───────

@pytest.mark.parametrize("part, said", [
    ("black spot always on screen", "because of the black spot always on the screen."),
    ("line always at bottom of screen", "because of the line always at the bottom of the screen."),
    ("dead pixel always at top of display", "because of the dead pixel always at the top of the display."),
    ("green line always on screen", "because of the green line always on the screen."),
    ("screen has a line always down middle", "because the screen has a line always down the middle."),
    ("small scratch top left on display", "because of the small scratch top left on the display."),
    ("dead pixel bottom left on display", "because of the dead pixel bottom left on the display."),
    ("small scratch top right on display", "because of the small scratch top right on the display."),
    ("pink line coming on screen occasionally", "because of the pink line coming on the screen occasionally."),
    # controls: the names and the shop's display stay as they were
    ("Always on display not working", "because the always on display is not working."),
    ("always-on display flickers", "because the always-on display flickers."),
    ("light marks from being on display", "because of the light marks from being on display."),
    ("Light scratches from being on display in store", "because of the light scratches from being on display in "
                                                       "store."),
])
def test_the_name_guards_fire_only_on_names(part, said):
    assert reason(part) == f"I'm offering that {said}"


@pytest.mark.parametrize("phrase, said", [
    ("that it comes on screen flickers", "that it comes on screen flickers"),  # the phone's "comes on"
    ("that it doesnt come on screen black", "that it doesnt come on screen black"),
    ("the green line comes on screen", "the green line comes on the screen"),  # a line's: it's on the screen
    ("the error message keeps coming on screen", "the error message keeps coming on the screen"),
    ("that the power on button sticks", "that the power on button sticks"),
])
def test_comes_on_is_a_verbs_only_after_the_phone(phrase, said):
    assert with_the(phrase) == said


# ── the-word-r4-5: "due to the case" after a mark goes, as "from the case" ──

@pytest.mark.parametrize("part, phrase", [
    ("slight wear on corners due to the case", "the slight wear on the corners"),
    ("scuffs on corners due to case", "the scuffs on the corners"),
    ("Slight marks on sides due to case but screen is perfect", "the slight marks on the sides"),  # a real listing's
    ("Small discolour on top right corner due to case", "the small discolour on the top right corner"),
    # controls: a case after a fault says when, and stays
    ("Wireless charging doesn't work through the case", "that the wireless charging doesn't work through the case"),
    ("Wireless charging doesn't work due to the case", "that the wireless charging doesn't work due to the case"),
    ("Left AirPod doesn't charge from the case", "that the left AirPod doesn't charge from the case"),
    ("Crack running through the case", "the crack running through the case"),
])
def test_due_to_the_case_after_a_mark_goes(part, phrase):
    assert flaw_phrase(part) == phrase


def test_due_to_the_case_in_alertflips_message_and_your_given_style():
    description = "slight wear on corners due to the case, screen mint, 86% battery"
    told = drafted("iPhone 12 128gb", description, asking="220")
    assert message(told) == "Hi, would you take £185 cash for it? I'm offering that because of the slight wear on " \
                            "the corners. I can come and collect."
    yours = drafted("iPhone 12 128gb", description, ["slight wear on corners due to the case"], asking="220",
                    card=GIVEN)
    assert message(yours) == "Hello, would you accept £185 given the slight wear on the corners? Thanks"


# ── the-word-r4-6: how it happened goes with its subject ────────────────────

@pytest.mark.parametrize("part, phrase", [
    ("scuffs on frame they are from the case", "the scuffs on the frame"),
    ("small scratch on screen it was from keys", "the small scratch on the screen"),
    ("marks on back they're from the case", "the marks on the back"),
    ("few scuffs on corners these are from the case", "a few scuffs on the corners"),
    ("light marks on frame this is from the case", "the light marks on the frame"),
    ("Small dent on corner, it was from a drop", "the small dent on the corner"),
    ("Scratches on back, all from the case", "the scratches on the back"),
    ("Small chip on corner from dropping it", "the small chip on the corner"),
    # the verifier's
    ("Few scratches on the back, these are just from normal use", "a few scratches on the back"),
    ("scuff on corner it was from being in my bag", "the scuff on the corner"),
    ("Small marks on the frame they are just from use", "the small marks on the frame"),
    ("Scratches on screen are all from use", "the scratches on the screen"),
    # controls: as before (the third red team's), and a pronoun with no verb is the flaw's own
    ("Few marks probably from the case", "a few marks"),
    ("Crack on the back isn't from a drop", "the crack on the back"),
    ("light scratches on screen its from normal use", "the light scratches on the screen"),
    ("marks on it from keys", "the marks on it"),
    ("dent on frame which is from a drop", "the dent on the frame"),
])
def test_how_it_happened_goes_with_its_subject(part, phrase):
    assert flaw_phrase(part) == phrase


def test_how_it_happened_goes_with_its_subject_in_the_messages():
    told = drafted("iPhone 13 128gb", "scuffs on frame they are from the case. fully working, unlocked", asking="250")
    assert message(told) == "Hi, would you take £210 cash for it? I'm offering that because of the scuffs on the " \
                            "frame. I can come and collect."
    yours = drafted("iPhone 13 128gb", "scuffs on frame they are from the case. fully working, unlocked", asking="250",
                    card=GIVEN)
    assert message(yours) == "Hello, would you accept £210 given the scuffs on the frame? Thanks"
    keys = drafted("iPhone 12 64gb", "small scratch on screen it was from keys. battery 88%")
    assert "because of the small scratch on the screen." in message(keys)
    back = drafted("iPhone 14", "marks on back they're from the case, all works perfect", asking="350")
    assert "because of the marks on the back." in message(back)
    dropped = drafted("iPhone 12", "Small chip on corner from dropping it. Face ID works")
    assert "because of the small chip on the corner." in message(dropped)
    produced = read_and_drafted("iPhone 13 128gb", "scuffs on frame they are from the case. fully working, unlocked",
                                ["scuffs on frame they are from the case"])
    assert "because of the scuffs on the frame." in message(produced)
