"""Messages before you have past messages, AlertFlip's, against what four test
agents wrote to break them (12 Sep 2026): 651 cases, of which a second agent
re-ran and confirmed 242 failures. They're fixed, and kept here as written.
Code only: no AI is asked."""

import pytest

from flip.ai import Reply
from flip.catalogue import load_catalogue
from flip.checks import check_message_manner
from flip.message_drafter import battery_in, draft_message
from flip.offers import point_for
from flip.reader import code_reading, place
from flip.writer import good_words

IPHONE = next(model for model in load_catalogue() if model["id"] == "iphone-13")
PLAIN = "Hi, would you take £210 cash for it? I can come and collect."


def lower(title, description):
    """The lower offer's message for a £250 Facebook listing, with no style."""
    result = draft_message({"id": "t", "title": title, "description": description, "asking_price": "250",
                            "marketplace": "facebook"}, kind="lower", offer=21000)
    return (result["answer"] or {}).get("message")


# ── what isn't a flaw gives no reason ───────────────────────────────────────

@pytest.mark.parametrize("title, description", [
    ('iPhone 13 128GB', 'Faults: none\nUnlocked: yes'),
    ('iPhone 13 128GB', 'Damage: None. Boxed.'),
    ('iPhone 13 128GB', 'Damage: nil'),
    ('iPhone 13 128GB', 'Scratches: 0'),
    ('iPhone 13 128GB', 'Faults - N/A'),
    ('iPhone 13 128GB', 'Scratches - None\nDents - None\nUnlocked'),
    ('iPhone 13 128GB', 'Cracks – no\nScratches – no\nWorking – yes'),
    ('iPhone 13 128GB', 'Scratches? None'),
    ('iPhone 13 128GB', 'Any damage? Nope'),
    ('iPhone 13 128GB', 'Any scratches or dents? No'),
    ('iPhone 13 128GB', 'Any cracks? No. Any dents? No.'),
    ('iPhone 13 128GB', '0 scratches, 0 dents'),
    ('iPhone 13 128GB', 'Scratches ❌ Dents ❌ Cracks ❌'),
    ('iPhone 13 128GB', 'Face ID ✅\nTrue Tone ✅\nScratches ❌\nCracks ❌'),
    ('iPhone 13 128GB', 'Dents: not that I know of'),
    ('iPhone 13 128GB', 'No scratches, dents, or marks.'),
    ('iPhone 13 128GB', 'No cracks, chips, scratches, or dents'),
    ('iPhone 13 128GB', "Doesn't have any marks, scratches, or dents"),
    ('iPhone 13 128GB', 'No visible scratches, dents, or marks on the screen'),
    ('iPhone 13 128GB', 'Free from scratches, scuffs, and dents'),
    ('iPhone 13 128GB', 'No scratches, scuffs and dents.'),
    ('iPhone 13 128GB', 'No scratches, scuffs & dents'),
    ('iPhone 13 128GB', 'Neither scratched nor dented'),
    ('iPhone 13 128GB', 'Never been dropped, cracked or repaired.'),
    ('iPhone 13 128GB', 'Not a single scratch, dent or scuff on it.'),
    ('iPhone 13 128GB', "There isn't a scratch, dent or scuff on it."),
    ('iPhone 13 128GB', "Hasn't been dropped, scratched or dented."),
    ('iPhone 13 128GB', 'Never had any scratches, dents or cracks.'),
    ('iPhone 13 128GB', 'Always kept in a case to prevent scratches'),
    ('iPhone 13 128GB', 'Protected from scratches with a case since day one'),
    ('iPhone 13 128GB', 'Comes with anti-scratch screen protector'),
    ('iPhone 13 128GB', 'Comes with scratch resistant screen protector fitted'),
    ('iPhone 13 128GB', 'Water damage indicator not triggered. Unlocked.'),
    ('iPhone 13 128GB', 'AppleCare+ with accidental damage cover until 2027'),
    ('Dell laptop', 'Intel chip, 8GB RAM'),
    ('Galaxy Watch 5', 'Runs Wear OS, great condition'),
    ('iPhone 13 128GB', 'Hardly a scratch on it.'),
    ('iPhone 13 128GB', 'Barely a mark on it, lovely phone.'),
    ('iPhone 13 128GB', 'Hardly any scratches'),
    ('iPhone 13 128GB', 'Scratch resistant Ceramic Shield front.'),
    ('iPhone 13 128GB', 'Cracked back glass so price reduced'),
    ('iPhone 13 128GB', 'Screen has a crack so selling cheaper'),
    ('iPhone 13 128GB', 'Cheap due to cracked screen'),
    ('iPhone 13 128GB', 'Cracked screen, priced low because of this'),
    ('iPhone 13 128GB', "Small crack on back which is why it's priced low."),
    ('iPhone 13 128GB', 'Price reduced to reflect the crack on the back.'),
    ('iPhone 13 128GB', 'Cheaper than others due to a small crack on the back.'),
])
def test_no_flaw_means_no_reason(title, description):
    assert lower(title, description) == PLAIN


# ── a real flaw is the reason ───────────────────────────────────────────────

@pytest.mark.parametrize("title, description, says", [
    ('iPhone 13 128GB', 'Cracked back. All reasonable offers taken into account.', 'cracked back'),
    ('iPhone 13 128GB', 'No charger and the back is cracked.', 'back'),
    ('iPhone 13 128GB', 'Not boxed and the screen has a crack.', 'crack'),
    ('iPhone 13 128GB', 'iphone 13 128gb no box screen has small crack works perfect', 'crack'),
    ('iPhone 13 128GB', 'no cracks only light scratches on the back', 'scratches'),
    ('iPhone 13 128GB', 'no cracks just a few scratches on back', 'scratches'),
    ('iPhone 13 128GB', 'No box just a small scratch on the back', 'scratch'),
    ('iPhone 13 128GB', 'selling my iphone no offers small crack on back', 'crack'),
    ('iPhone 13 128GB', 'No cracks, light scratches or scuffs on the back', 'scratches'),
    ('iPhone 13 128GB', 'No dents, faint scratches or marks on screen', 'scratches'),
    ('iPhone 13 128GB', 'No cracks, hairline scratches or scuffs on the screen.', 'scratches'),
    ('iPhone 13 128GB', 'No dents, odd scratch or scuff from use.', 'scratch'),
    ('iPhone 13 128GB', 'No cracks or chips, light scratches or scuffs on the frame.', 'scratches'),
    ('iPhone 13 128GB', 'Good condition apart from a small scratch', 'scratch'),
    ('iPhone 13 128GB', 'Excellent condition except small dent on corner', 'dent'),
    ('iPhone 13 128GB', 'No marks apart from tiny scratch on back', 'scratch'),
    ('iPhone 13 128GB', 'Never dropped, no marks except one small scratch on back', 'scratch'),
    ('iPhone 13 128GB', 'No damage except a small dent', 'dent'),
    ('iPhone 13 128GB', 'Good condition apart from cracked back.', 'cracked back'),
    ('iPhone 13 128GB', 'Mint apart from a crack on the back.', 'crack'),
    ('iPhone 13 128GB', 'Perfect except a small scratch.', 'scratch'),
    ('iPhone 13 128GB', 'No issues apart from a small crack.', 'crack'),
    ('iPhone 13 128GB', "Can't fault it apart from a small scratch on the back.", 'scratch'),
    ('iPhone 13 128GB', 'Fully working, other than a scratch on the screen.', 'scratch'),
    ('iPhone 13 128GB', 'No marks bar a small scuff on the back.', 'scuff'),
    ('iPhone 13 128GB', 'No marks except a small scuff on the back.', 'scuff'),
    ('iPhone 13 128GB', 'Stopped working last week', 'working'),
    ('Sony WH-1000XM4 headphones', 'Sound cuts out sometimes', 'cuts out'),
    ('iPhone 13 128GB', 'Turns on and off by itself', 'on and off'),
    ('iPhone 13 128GB', 'Randomly restarts', 'restarts'),
    ('PS5 Slim Disc', 'Powers on but no picture', 'picture'),
    ('PS5 Slim Disc', 'No signal on TV', 'signal'),
    ('iPhone 13 128GB', 'No service, wifi only', 'service'),
    ('iPhone 13 128GB', 'Turns on but no display', 'display'),
    ('iPhone 13 128GB', 'Back is slightly marked', 'marked'),
    ('Sony WH-1000XM4 headphones', 'Ear cushions worn', 'worn'),
    ('iPhone 13 128GB', 'Few scraches on screen', 'scraches'),
    ('iPhone 13 128GB', 'Craked screen', 'craked'),
    ('iPhone 13 128GB', 'Blacklisted, works on wifi', 'blacklisted'),
    ('iPhone 11 64GB', 'Battery needs replacing, drains fast', 'replacing'),
    ('iPhone 8 64GB', 'Battery swollen, screen lifting', 'swollen'),
    ('iPhone 12 64GB', 'No Face ID, otherwise perfect', 'Face ID'),
    ('AirPods Pro 2', 'Left AirPod missing, case and right one only', 'missing'),
    ('airpods pro 2', 'left one has a crackle sometimes case has few marks', 'crackle'),
])
def test_a_real_flaw_is_the_reason(title, description, says):
    message = lower(title, description)
    assert message != PLAIN and says.lower() in message.lower()


# ── ...said as a sentence ───────────────────────────────────────────────────

@pytest.mark.parametrize("title, description, reason", [
    ('iPhone 13 128GB', 'Condition: Cracked screen', "I'm offering that because of the cracked screen."),
    (   'iPhone 13 128GB',
        'Only issue: small scratch on screen',
        "I'm offering that because of the small scratch on screen."),
    ('iPhone 13 128GB', 'Only minor scratches', "I'm offering that because of the minor scratches."),
    (   'iPhone 13 128GB',
        'Excellent condition, no scratches, only a small dent on the back',
        "I'm offering that because of a small dent on the back."),
    (   'iPhone 13 128GB',
        'Just a small scratch on the back',
        "I'm offering that because of a small scratch on the back."),
    ('iPhone 13 128GB', 'Great condition just a few scratches', "I'm offering that because of a few scratches."),
    ('iPhone 13 128GB', '• Cracked screen\n• Unlocked\n• Boxed', "I'm offering that because of the cracked screen."),
    (   'iPhone 13 128GB',
        '► Small scratch on screen\n► Unlocked',
        "I'm offering that because of the small scratch on screen."),
    (   'iPhone 14 Pro 128GB',
        'Good condition | Box and cable included! Small scratch on the camera lens | Battery '
        'Health 88%',
        "I'm offering that because of the small scratch on the camera lens."),
    ('iPhone 13 128GB', 'small scratch on the back x', "I'm offering that because of the small scratch on the back."),
    (   'iPhone 13 128GB',
        'Phone is in good working order with a tiny crack on the bottom left of the screen',
        "I'm offering that because of the tiny crack on the bottom left of the screen."),
    (   'iphone 13 128gb',
        'cracked screen works perfect collection only leeds no offers',
        "I'm offering that because of the cracked screen."),
    (   'iphone 12 64gb',
        'screen cracked still works fine selling cos upgraded',
        "I'm offering that because the screen is cracked."),
    (   'iphone 11',
        'few scratches on back nothing major battery 84 unlocked any network',
        "I'm offering that because of a few scratches on back."),
    (   'iPhone 13 128GB',
        "Small crack on screen doesn't affect use",
        "I'm offering that because of the small crack on screen."),
    ('iPhone 13 128GB', 'Good condition with light scratches', "I'm offering that because of the light scratches."),
    (   'iPhone 13 128GB',
        'Lovely condition few marks on the back',
        "I'm offering that because of a few marks on the back."),
    ('iPhone 13 128GB', '✅ Unlocked\n❌ Small crack on back', "I'm offering that because of the small crack on back."),
    ('iPhone 13 128GB', 'Cracked back 😩', "I'm offering that because of the cracked back."),
    ('iPhone 13 128GB', 'Cracked back costs £80 to fix', "I'm offering that because of the cracked back."),
    ('iPhone 12 cracked back £150 ono', 'Works fine', "I'm offering that because of the cracked back."),
    ('iPhone 13 128GB', 'The only issue is a small scratch', "I'm offering that because of a small scratch."),
    (   'iPhone 13 128GB',
        'Scratch on screen not noticeable when on',
        "I'm offering that because of the scratch on screen."),
    (   'iPhone 13 128GB',
        'Couple of small marks on the back nothing major',
        "I'm offering that because of the small marks on the back."),
    ('iPhone 13 128GB', 'Scratches see pics', "I'm offering that because of the scratches."),
    ('iPhone 13 128GB', 'Screen cracked but works fine', "I'm offering that because the screen is cracked."),
    (   'iPhone 13 128GB',
        'Back glass smashed, everything else works',
        "I'm offering that because the back glass is smashed."),
    ('PS5 Slim Disc', 'HDMI port damaged, sold as seen', "I'm offering that because the HDMI port is damaged."),
    ('iPhone 12 64GB', 'Face ID broken, otherwise perfect', "I'm offering that because the Face ID is broken."),
    ('Nintendo Switch Lite', 'Hinge broken', "I'm offering that because the hinge is broken."),
    ('AirPods Pro 2', 'Case colour faded', "I'm offering that because the case colour is faded."),
    ('iPhone 11 64GB back glass cracked', 'Works perfectly', "I'm offering that because the back glass is cracked."),
    ('IPHONE 11 64GB SCREEN CRACKED', 'WORKS PERFECT', "I'm offering that because the screen is cracked."),
    ('iPhone XR cracked back', 'Works perfectly', "I'm offering that because of the cracked back."),
    ('iPhone 13 cracked back 128GB', 'Works fine', "I'm offering that because of the cracked back."),
    (   'iPhone 12 64GB Face ID not working',
        'Unlocked, boxed',
        "I'm offering that because the Face ID is not working."),
    (   'PS5 disc drive not working',
        'Digital games work fine',
        "I'm offering that because the disc drive is not working."),
    (   'iPhone 13 128GB',
        'Screen: cracked\nBack: perfect\nBattery: 90%',
        "I'm offering that because the screen is cracked."),
    (   'iPhone 13 128GB',
        'Screen: perfect\nBack: cracked\nBattery: 89%',
        "I'm offering that because the back is cracked."),
    ('iPhone 13 128GB', 'In used condition with marks', "I'm offering that because of the marks."),
    (   'iPhone 13 128GB',
        'SMALL CRACK ON BACK. OTHERWISE MINT',
        "I'm offering that because of the small crack on back."),
    (   'iPhone 13 128GB Unlocked - Small Crack On Back',
        'Works perfectly',
        "I'm offering that because of the small crack on back."),
    (   'iPhone 13 128GB',
        'Got a small crack in the corner',
        "I'm offering that because it's got a small crack in the corner."),
    (   'iPhone 12 64GB screen cracked',
        'The screen is cracked but works fine',
        "I'm offering that because the screen is cracked."),
    (   'iPhone 13 128GB - Cracked Screen',
        'Small crack on the screen, works fine',
        "I'm offering that because of the small crack on the screen."),
    (   'iPhone 13 128GB cracked back',
        'Cracked back but works perfectly.',
        "I'm offering that because of the cracked back."),
    (   'iPhone 13 128GB',
        'There is a very small hairline crack on the bottom left corner of the screen.',
        "I'm offering that because of the hairline crack on the bottom left corner of the screen."),
    (   'iPhone 13 128GB',
        'The screen has a tiny scratch that you can only see when the screen is off.',
        "I'm offering that because of the tiny scratch."),
    (   'iPhone 13 128GB',
        '• Cracked back • Face ID works • Unlocked',
        "I'm offering that because of the cracked back."),
    (   'iPhone 13 128GB',
        '✅ Unlocked ✅ Small crack on back ✅ Battery 88%',
        "I'm offering that because of the small crack on back."),
    (   'iPhone 13 128GB',
        'Small crack on the back 😢 still works fine',
        "I'm offering that because of the small crack on the back."),
    ('iPhone 13 128GB', 'Back is slightly marked', "I'm offering that because the back is slightly marked."),
    ('Sony WH-1000XM4 headphones', 'Ear cushions worn', "I'm offering that because the ear cushions are worn."),
    ('iPhone 13 128GB', 'Stopped working last week', "I'm offering that because it stopped working last week."),
    (   'Sony WH-1000XM4 headphones',
        'Sound cuts out sometimes',
        "I'm offering that because the sound cuts out sometimes."),
    ('iPhone 13 128GB', 'Randomly restarts', "I'm offering that because it randomly restarts."),
    ('PS5 Slim Disc', 'Powers on but no picture', "I'm offering that because there's no picture."),
    ('iPhone 13 128GB', 'Blacklisted, works on wifi', "I'm offering that because it's blacklisted."),
    (   'iPhone 8 64GB',
        'Battery swollen, screen lifting',
        "I'm offering that because the battery is swollen and the screen is lifting."),
    ('iPhone 12 64GB', 'No Face ID, otherwise perfect', "I'm offering that because there's no Face ID."),
    (   'AirPods Pro 2',
        'Left AirPod missing, case and right one only',
        "I'm offering that because the left AirPod is missing."),
    ('iPhone 13 128GB', 'Few scraches on screen', "I'm offering that because of a few scraches on screen."),
])
def test_the_reason_reads_as_a_sentence(title, description, reason):
    assert lower(title, description) == f"Hi, would you take £210 cash for it? {reason} I can come and collect."


# ── battery health, as a seller writes it ───────────────────────────────────

@pytest.mark.parametrize("text, health", [
    ("Battery 80% charged, comes with cable", None), ("Battery: 80% limit on (optimised charging)", None),
    ("Battery replaced at 81% last year by Apple", None), ("Battery was at 82% so I had it replaced, works great", None),
    ("Battery health was 84%, now 100% after replacement", None), ("Battery health over 85%", None),
    ("Battery health above 80%", None), ("Battery at 75% charge in the photos.", None),
    ("Battery is on 60% in the photos", None), ("Battery still holds 80% after a full day of use", None),
    ("Battery life is great, still on 70% by bedtime.", None), ("New battery fitted last month, old one was at 76%.", None),
    ("Battery replaced (old one was 79%).", None), ("Battery health 85%+", None),
    ("✅ Battery Health: 80%", "80"), ("80% battery health", "80"), ("BH 79%", "79"), ("Max capacity 82%", "82"),
    ("battery health is 84%, unlocked", "84"), ("Excellent condition, with no scratches! Battery Health: 80%. Unlocked.", "80"),
])
def test_only_battery_health_as_it_is_now_is_read(text, health):
    assert battery_in(text, IPHONE) == health


# ── the checks, on a pretend AI's draft ─────────────────────────────────────

class Says:
    """A pretend model that writes the given message."""

    def __init__(self, message):
        self.message = message

    def ask(self, *args, **kwargs):
        return Reply("gemma3:4b", answer={"message": self.message})


PS5 = {"id": "p", "title": "PS5 Slim Disc Console", "asking_price": "350", "marketplace": "facebook",
       "description": "Selling my PS5 Slim disc version, comes with one controller and the cables. Collection only."}


@pytest.mark.parametrize("kind, offer, message, passes", [
    (   'lower',
        30000,
        'Hi, would you take £300 cash for it? Happy to transfer now to secure it and come and collect tomorrow.',
        False),
    (   'lower',
        30000,
        'Hi, would you take £300 cash for it? I can BACS it over tonight and come and collect tomorrow.',
        False),
    ('lower', 30000, 'Hi, would you take £300 cash for it? Can PayPal you now and come and collect.', False),
    ('lower', 30000, 'Hi, would you take £300 cash for it? Happy to pay up-front. I can come and collect.', False),
    (   'lower',
        30000,
        "Hi, would you take £300 cash for it? I'll pay before collection. I can come and collect.",
        False),
    ('lower', 30000, 'Hi, would you take £300 cash for it? I can come and collect, thanks in advance.', True),
    (   'lower',
        30000,
        'Hi, would you take £300 cash for it? I can come and collect and pay first thing tomorrow.',
        True),
    (   'lower',
        30000,
        'Hi, would you take £300 cash for it? Is it signed out of your Apple account? I can come and collect.',
        False),
    (   'lower',
        30000,
        'Hi, would you take £300 cash for it? Is it signed out of i cloud? I can come and collect.',
        False),
    ('lower', 30000, 'Hi, would you take £300 cash for it? Is FMI turned off? I can come and collect.', False),
    (   'lower',
        30000,
        "Hi, would you take £300 cash for it? Is your Google account removed so there's no FRP lock? I can come and "
        'collect.',
        False),
    ('lower', 30000, "Hi, would you take £300 cash for it? I can come and collect, I'll find my way.", True),
    ('lower', 30000, 'Hi, would you take £300 cash for it? Looks really nice. I can come and collect.', False),
    ('lower', 30000, 'Hi, nice console! Would you take £300 cash for it? I can come and collect.', False),
    ('lower', 30000, 'Hi, would you take £300 cash for that cracking console? I can come and collect.', False),
    (   'lower',
        30000,
        'Hi, would you take £300 cash for it? Tomorrow evening looks great for me to come and collect.',
        True),
    (   'asking',
        35000,
        "Hi, I'll pay the full £350 cash, and will pay it when I come and collect. Could you hold it for me?",
        True),  # "I'll pay" twice is fine (14 Sep)
    ('asking', 35000, "Hi, I'll happily pay the full £350 cash. I'll pay when I come and collect.", True),  # "I'll pay" twice is fine (14 Sep)
    (   'lower',
        30000,
        'Hi is it still available\nWould you take £300 cash for it\nAre you about Saturday\nI can come and collect',
        False),
    ('lower', 30000, 'Hi, is this still available?? Would you take £300 cash for it? I can come and collect.', True),
    ('lower', 30000, 'Hi, would you take £300 cash for it? Collection is not possible for me this week.', False),
    ('lower', 30000, 'Hi, would you take £300 cash for it? Happy for you to drop round with it tonight.', False),
    ('lower', 30000, "Hi, would you take £300 for it? I'll pay cash when I collect.", True),
    ('lower', 30000, 'Hi, would you take £300 cash for it? No problem collecting tonight.', True),
    ('lower', 30000, "Hi, would you take £300 cash for it? Can't wait to collect it.", True),
    ('lower', 30000, 'Hi, would you take £300 for it? Is cash fine? I can come and collect.', True),
    ('lower', 30000, 'Hi, would you take £300 for it? I can pay cash on the spot when I come and collect.', True),
    ('lower', 30000, 'Hi, would you take £300 cash for it? I can come and collect, just drop me a line.', True),
    ('lower', 30000, 'Hi, would you take £300 cash for it? I can come & collect.', True),
    ('more', 36000, "Hi, I'll pay £360 cash if you end the listing and sell it to me. I can come and collect.", True),
    (   'lower',
        30000,
        'Hi, would you take £300 cash for it? Could do a bit more if needed. I can come and collect.',
        False),
    (   'lower',
        30000,
        'Hi, would you take £300 cash for it? Could add a tenner if needed. I can come and collect.',
        False),
    (   'lower',
        30000,
        "Hi, would you take £300 cash for it? There's a bit of wiggle room if not. I can come and collect.",
        False),
    ('more', 36000, 'Hi, £360 cash if you take the listing down and sell it to me? I can come and collect.', False),
    ('lower', 30000, 'Hi, would you take £300 cash for it? I can come and collect ⭐', False),
    ('lower', 30000, 'Hi, would you take £300 cash for it? I can come and collect today‼️', False),
])
def test_the_checks_on_facebook(kind, offer, message, passes):
    result = draft_message(PS5, kind=kind, offer=offer, local=Says(message), mode="local", writer="ai")
    assert (result["status"] == "ready") == passes


@pytest.mark.parametrize("kind, offer, message, passes", [
    ('lower', 30000, 'Hi, would you take £300 for it if we do it outside Vinted?', False),
    ('lower', 30000, 'Hi, would you take £300 for it? We could sort it off the app to save the fees.', False),
])
def test_never_off_the_platform_on_vinted(kind, offer, message, passes):
    result = draft_message({**PS5, "marketplace": "vinted"}, kind=kind, offer=offer, local=Says(message), mode="local",
                           writer="ai")
    assert (result["status"] == "ready") == passes


@pytest.mark.parametrize("marketplace, title, message, passes", [
    # the name offers no cash (check_message_manner below), so since 14 Sep code adds "I can pay cash." and it passes
    ("facebook", "Johnny Cash At Folsom Prison vinyl LP", "Hi, would you take £300 for the Johnny Cash LP? I can come and collect.", True),
    ("ebay", "Johnny Cash At Folsom Prison vinyl LP", "Hi, would you take £300 for the Johnny Cash LP?", True),
    ("facebook", "Pokemon 151 Booster Box", "Hi, would you take £300 cash for the booster box? I can come and collect.", True),
])
def test_a_name_is_no_promise_and_no_question(marketplace, title, message, passes):
    listing = {"id": "n", "title": title, "asking_price": "350", "marketplace": marketplace, "description": "Collection only."}
    result = draft_message(listing, kind="lower", offer=30000, local=Says(message), mode="local", writer="ai")
    assert (result["status"] == "ready") == passes
    if "Johnny Cash" in message and marketplace == "facebook":
        assert check_message_manner(message, must=["cash", "collecting"]) == [
            "the message doesn't say you'll pay cash: on Facebook and Gumtree it does"]
        assert result["answer"]["message"] == ("Hi, would you take £300 for the Johnny Cash LP? I can pay cash. "
                                               "I can come and collect.")


# ── odds and ends ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("quote, said", [("Collection from St. Albans", "St Albans"), ("Pick up Newport (South Wales)",
                                         "Newport South Wales"), ("Collection only, Leeds LS6", "Leeds LS6")])
def test_a_pickup_place_is_its_whole_name(quote, said):
    assert place(quote) == said


@pytest.mark.parametrize("says, words", [("Mint", "it's in mint condition"), ("Like new", "it's like new"),
                                          ("Immaculate", "it's immaculate"), ("As new condition", "it's as new")])
def test_good_condition_in_one_word_is_a_reason_to_pay_more(says, words):
    assert good_words([says]) == words


def test_good_condition_is_no_reason_to_pay_more_with_a_flaw_or_a_denied_list():
    assert point_for("more", "iPhone 13. Excellent condition. Perfect apart from a tiny scratch.",
                     code_reading("Excellent condition. Perfect apart from a tiny scratch.")["flaws"]) is None
    for text in ("iPhone 13 128GB. Great condition, no scratches, scuffs and dents.",
                 "iPhone 13 128GB. Excellent condition, never been dropped, cracked or repaired."):
        assert point_for("more", text, code_reading(text)["flaws"])["about"] == "condition"
