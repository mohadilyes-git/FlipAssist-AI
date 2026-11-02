"""Your own reason or "don't mind the condition" for any listing, as the
second red team found the first round's fixes (26 Sep, area "leads"): taken
out only when it comes out whole, else kept as you typed it at the asking
price or left to the AI under it; everyday words after it ("tbh", "for a
quick sale") kept; said in a sentence of its own or in other words, never
twice; more leads ("bearing in mind", "for the condition it's in"); your
capital on the first word only; and each module-level clause end its own
name. No AI anywhere: code's own drafts (writer="template"), through the
drafter's checks, or a FakeModel where the AI's turn is the point."""

import re

import pytest

from flip import writer
from flip.message_drafter import draft_message
from flip.style import style_card
from flip.writer import collecting_from, paid_at, with_reason
from tests.fakes import FakeModel

CRACK = {"about": "flaw", "says": ["Small crack on the back"]}
NO_CHARGE = {"about": "flaw", "says": ["Doesn't charge"]}
MARKS_AND_BATTERY = {"about": "flaw", "says": ["Battery health 79%", "Light marks on the frame"]}


def listing(title, description, asking="200"):
    return {"id": "x", "title": title, "description": description, "asking_price": asking, "marketplace": "facebook"}


CRACKED = listing("iPhone 13 128GB", "Small crack on the back, works perfectly")
DEAD_PORT = listing("iPhone 12 64GB", "Doesn't charge, needs a new port")
MINT = listing("iPhone 13 128GB", "Immaculate condition, boxed with charger")
SCRATCHED = listing("iPhone 13 128GB Midnight", "Few scratches on the screen. Works perfectly.")


def reading(*flaws):
    """The listing as the model read it (what the drafter is given)."""
    return {"flaws": list(flaws), "pickup": "", "no_offers": "", "read_by": "gemma3:4b"}


READ = {"cracked": (CRACKED, reading("Small crack on the back")), "dead port": (DEAD_PORT, reading("Doesn't charge")),
        "mint": (MINT, reading())}


def habit(sentence, closing="Can collect today.", opener="Hi mate,", kind="lower"):
    """Three past Facebook messages with the same offer sentence (£X: the old price), under or at the asking price."""
    prices = (("150", "200", "iPhone 12"), ("90", "120", "AirPods Pro"), ("300", "380", "iPhone 14 Pro")) \
        if kind == "lower" else (("200", "200", "iPhone 12"), ("120", "120", "AirPods Pro"), ("380", "380", "iPhone 14 Pro"))
    return [{"my_message": " ".join(p for p in (opener, sentence.replace("£X", f"£{price}"), closing) if p),
             "asking_price": asking, "marketplace": "facebook", "listing_title": title}
            for price, asking, title in prices]


def mixed(asking_sentence, lower_sentence="would you take £X cash?", opener="Hi mate,"):
    """Two lower offers and two at the asking price, as the red team's own persona has them."""
    return [{"my_message": f"{opener} {sentence.replace('£X', '£' + price)} Can collect today.", "asking_price": asking,
             "marketplace": "facebook", "listing_title": title}
            for price, asking, title, sentence in (("150", "200", "iPhone 12", lower_sentence),
                                                   ("90", "120", "AirPods Pro", lower_sentence),
                                                   ("380", "380", "iPhone 14 Pro", asking_sentence),
                                                   ("250", "250", "iPhone 13", asking_sentence))]


def drafted(lst, messages, read, kind="lower", writer_="template", local=None, mention=True):
    """code's own message (or the AI's turn) for the listing: its status, message and the last try's problems."""
    # Say the flaw: Yes, as you'd pick it on the message (14 Oct: whether you give it isn't learned from your style)
    result = draft_message(lst, style_card(messages), kind=kind, reading=read, writer=writer_, local=local,
                           mention=mention)
    problems = result["attempts"][-1]["problems"] if result["attempts"] else result["reasons"]
    return result["status"], (result["answer"] or {}).get("message"), problems


# ── leads-r4-asking-dangling-subject: never "...cash and I'm." ──

@pytest.mark.parametrize("sentence", [
    "I can pay £X cash and I'm not fussed about the condition.",
    "happy to pay £X, I'm not bothered about the condition.",
    "I can do £X cash, im not fussed about the condition.",
    "I can pay £X cash, I really don't mind the condition.",
    "I can pay £X cash, I honestly don't mind the condition.",
    "I can pay £X cash, I am not bothered about the condition.",
    "I can pay £X cash and we don't mind the condition.",
    "I can pay £X cash, I'm not too fussed about the condition.",
])
def test_a_dont_mind_with_its_own_subject_stays_as_you_typed_it_with_no_flaw_to_give(sentence):
    """With no flaw to give, 'I'm not fussed about the condition' was cut to 'I'm.' on every listing: the cut took
    the don't-mind and left its subject. It can't come out whole, so it stays as you typed it, as before V8."""
    as_typed = f"Hi mate, {sentence.replace('£X', '£200')} Can collect today."
    for name in ("cracked", "mint"):
        lst, read = READ[name]
        status, message, _ = drafted(lst, mixed(sentence), read, kind="asking", mention=False)  # Say it: No
        assert (status, message) == ("ready", as_typed), name


def test_with_the_flaw_to_give_your_subject_keeps_its_place():
    """The lower offers name the condition, so the flaw is given: it goes in your words, 'I'm' and all."""
    messages = mixed("I can pay £X cash and I'm not fussed about the condition.",
                     "would you take £X cash given the condition?")
    assert drafted(CRACKED, messages, reading("Small crack on the back"), kind="asking")[:2] == \
        ("ready", "Hi mate, I can pay £200 cash and I'm not fussed about the small crack on the back. Can collect today.")
    assert drafted(MINT, messages, reading(), kind="asking")[:2] == \
        ("ready", "Hi mate, I can pay £200 cash and I'm not fussed about the condition. Can collect today.")


def test_the_ai_isnt_asked_when_your_own_sentence_reads():
    """writer='auto': code's own message goes, the FakeModel is never reached."""
    local = FakeModel("gemma3:4b", *[{"message": "Hi mate, I can pay £200 cash. Can collect today."}] * 3)
    status, message, _ = drafted(MINT, mixed("I can pay £X cash and I'm not fussed about the condition."), reading(),
                                 kind="asking", writer_="auto", local=local)
    assert (status, message) == ("ready", "Hi mate, I can pay £200 cash and I'm not fussed about the condition. "
                                          "Can collect today.")
    assert local.asked == []


def test_a_couple_buying_keeps_their_were_not_fussed():
    """The verifier's persona: 'We can pay £200 cash, we're.' on mint listings, even with the condition named."""
    messages = [{"my_message": m, "asking_price": a, "marketplace": "facebook", "listing_title": t} for m, a, t in (
        ("Hi, is this still available? We can pay £220 cash, we're not fussed about the condition. Can collect this "
         "evening.", "220", "iPhone 13"),
        ("Hi, is this still available? We can pay £110 cash, we're not fussed about the condition. Can collect this "
         "evening.", "110", "AirPods Pro"),
        ("Hi, would you take £160 cash given the condition? Can collect this evening.", "200", "iPhone 12"),
        ("Hi, would you take £90 cash given the condition? Can collect this evening.", "120", "Apple Watch"))]
    assert drafted(MINT, messages, reading(), kind="asking")[:2] == \
        ("ready", "Hi, is this still available? We can pay £200 cash, we're not fussed about the condition. "
                  "Can collect this evening.")
    assert drafted(DEAD_PORT, messages, reading("Doesn't charge"), kind="asking")[:2] == \
        ("ready", "Hi, is this still available? We can pay £200 cash, we're not fussed that it doesn't charge. "
                  "Can collect this evening.")


@pytest.mark.parametrize("sentence", [
    "I'm not fussed about the condition, I can pay £[OFFER] cash.",
    "I can pay £[OFFER] cash, really don't mind the condition.",
    "I can pay £[OFFER] cash and honestly not bothered about the condition.",
    "Can pay £[OFFER] cash, im not too bothered about the condition",
    "Happy to pay £[OFFER], I genuinely don't mind the condition.",
    "We can pay £[OFFER] cash, we're not fussed about the condition.",
    "I'll pay the full £[OFFER], I'm not worried about the marks.",
    "I can pay £[OFFER] cash, don't mind the condition tbh.",
    "I can pay £[OFFER] cash, don't mind the condition at all.",
    "I can pay £[OFFER] cash, don't mind the condition if it works.",
    "I can pay £[OFFER] cash, but don't mind the condition.",
    "Don't mind the condition and I can pay £[OFFER] cash.",
])
def test_a_dont_mind_that_cant_come_out_whole_stays_as_typed(sentence):
    """The verifier's leftovers ("I'm, I can pay...", '...cash, really.', '...cash and honestly.', '...cash, im',
    '...I genuinely.'), and what else would be left half there: '...cash tbh.', '...cash at all.', '...cash if it
    works.' (which changes what you said), '...cash, but.', 'And I can pay...'."""
    assert with_reason(sentence, "asking", None) == sentence


@pytest.mark.parametrize("sentence, without", [
    ("I can pay £[OFFER] cash, don't mind the condition.", "I can pay £[OFFER] cash."),
    ("I can pay £[OFFER] cash, I don't mind the condition.", "I can pay £[OFFER] cash."),
    ("I can pay £[OFFER] cash, i dont mind the condition", "I can pay £[OFFER] cash"),
    ("I can pay £[OFFER] cash and I dont mind the marks.", "I can pay £[OFFER] cash."),
    ("I can pay £[OFFER] cash - don't mind the condition.", "I can pay £[OFFER] cash."),
    ("I can pay £[OFFER] cash, not fussed about the condition, can collect today.",
     "I can pay £[OFFER] cash, can collect today."),
    ("Don't mind the condition, I can pay £[OFFER] cash.", "I can pay £[OFFER] cash."),
    ("I can pay £[OFFER] cash, don't mind the condition mate.", "I can pay £[OFFER] cash mate."),
])
def test_one_that_comes_out_whole_still_goes(sentence, without):
    """The first round's removal where it reads: its comma, dash or 'and' goes with it."""
    assert with_reason(sentence, "asking", None) == without


@pytest.mark.parametrize("sentence, crack", [
    ("I'm not fussed about the condition, I can pay £[OFFER] cash.",
     "I'm not fussed about the small crack on the back, I can pay £[OFFER] cash."),
    ("I can pay £[OFFER] cash, really don't mind the condition.",
     "I can pay £[OFFER] cash, really don't mind the small crack on the back."),
    ("Happy to pay £[OFFER], I genuinely don't mind the condition.",
     "Happy to pay £[OFFER], I genuinely don't mind the small crack on the back."),
])
def test_with_a_flaw_the_same_sentences_take_it_in_your_words(sentence, crack):
    assert with_reason(sentence, "asking", CRACK) == crack


# ── leads-r4-first-dangling-and: never "And the fact I can collect today, would you..." ──

@pytest.mark.parametrize("sentence", [
    "Given the condition, and that I can collect today, would you take £[OFFER]?",
    "Given the condition, and the fact I can collect today, would you take £[OFFER]?",
    "Given the condition, and cash in hand, would you take £[OFFER]?",
    "Given the condition, plus I can collect today, would you take £[OFFER]?",
    "Given the condition, though, would you take £[OFFER]?",
    "Given the condition, and I can collect, would you take £[OFFER]?",
    "Considering the condition, and that it's cash, would you do £[OFFER]?",
    "Considering the condition, but cash in hand, would you take £[OFFER]?",
    "Hi mate, given the condition, and the fact I can collect today, would you do £[OFFER]?",
])
def test_a_reason_said_first_that_leaves_its_and_behind_gets_no_wording(sentence):
    """No flaw to give: 'And that I can collect today, would you take...', 'Though, would you take...'. It can't stay
    on a mint listing, so the AI words it."""
    assert with_reason(sentence, "lower", None) is None


def test_with_a_flaw_a_reason_said_first_still_takes_it():
    """The swap reads, so it stays."""
    sentence = "Given the condition, and the fact I can collect today, would you do £[OFFER]?"
    assert with_reason(sentence, "lower", CRACK) == \
        "Given the small crack on the back, and the fact I can collect today, would you do £[OFFER]?"
    assert with_reason(sentence, "lower", NO_CHARGE) == \
        "Given that it doesn't charge, and the fact I can collect today, would you do £[OFFER]?"


@pytest.mark.parametrize("sentence, none", [
    ("Given the condition, would you take £[OFFER]?", "Would you take £[OFFER]?"),
    ("Given the condition, mate, would you take £[OFFER]?", "Mate, would you take £[OFFER]?"),  # 'Alright, mate, ...'
    ("Given the condition, as I can collect today, would you take £[OFFER]?",
     "As I can collect today, would you take £[OFFER]?"),
    ("Given the condition, cash in hand, would you take £[OFFER]?", "Cash in hand, would you take £[OFFER]?"),
    ("I know it's cheeky, given the condition, but would you take £[OFFER]?", "I know it's cheeky, but would you take £[OFFER]?"),
])
def test_what_reads_without_your_reason_still_goes_without_it(sentence, none):
    assert with_reason(sentence, "lower", None) == none


def test_on_a_mint_listing_the_ai_words_it_and_code_never_sends_and_the_fact():
    """'Hi, and the fact I can collect today, would you do £170?' went out on writer='template' and 'auto'."""
    messages = habit("given the condition, and the fact I can collect today, would you do £X?", closing="",
                     opener="Hi,")
    status, message, problems = drafted(MINT, messages, reading())
    assert (status, message) == ("needs you", None)
    assert problems == ["your offer sentence gives a reason about the condition this draft leaves out"]
    local = FakeModel("gemma3:4b", *[{"message": "Hi, would you do £170? Can collect today."}] * 3)
    assert drafted(MINT, messages, reading(), writer_="auto", local=local)[:2] == \
        ("ready", "Hi, would you do £170? Can collect today.")
    assert drafted(CRACKED, messages, reading("Small crack on the back"))[:2] == \
        ("ready", "Hi, given the small crack on the back, and the fact I can collect today, would you do £170?")


# ── leads-r4-tail-refused: an everyday word after your reason no longer refuses every draft ──

@pytest.mark.parametrize("sentence, cracked, mint", [
    ("would you take £X given the condition tbh?",
     "Hi mate, would you take £170 given the small crack on the back tbh? Can collect today.",
     "Hi mate, would you take £170 tbh? Can collect today."),
    ("would you take £X given the condition tho?",
     "Hi mate, would you take £170 given the small crack on the back tho? Can collect today.",
     "Hi mate, would you take £170 tho? Can collect today."),
    ("would you take £X given the condition to be fair?",
     "Hi mate, would you take £170 given the small crack on the back to be fair? Can collect today.",
     "Hi mate, would you take £170 to be fair? Can collect today."),
    ("would you take £X given the condition for a quick sale?",
     "Hi mate, would you take £170 given the small crack on the back for a quick sale? Can collect today.",
     "Hi mate, would you take £170 for a quick sale? Can collect today."),
    ("would you take £X given the condition as I can collect today?",
     "Hi mate, would you take £170 given the small crack on the back as I can collect today?",
     "Hi mate, would you take £170 as I can collect today?"),
    ("would you take £X given the condition bud?",
     "Hi mate, would you take £170 given the small crack on the back bud? Can collect today.",
     "Hi mate, would you take £170 bud? Can collect today."),
    ("would you take £X given the condition instead?",
     "Hi mate, would you take £170 given the small crack on the back instead? Can collect today.",
     "Hi mate, would you take £170 instead? Can collect today."),
])
def test_your_reason_with_an_everyday_word_after_it_is_swapped_and_taken_out(sentence, cracked, mint):
    """'needs you' on every listing, mint included, with 'no plain wording for what the listing says: Small crack on
    the back'. What the person sent before V8 (BASE)."""
    closing = "" if "collect today?" in sentence else "Can collect today."
    messages = habit(sentence, closing=closing)
    assert drafted(CRACKED, messages, reading("Small crack on the back"))[:2] == ("ready", cracked)
    assert drafted(MINT, messages, reading())[:2] == ("ready", mint)


def test_a_texter_who_doesnt_punctuate_gets_their_draft_back():
    messages = [{"my_message": m, "asking_price": a, "marketplace": "facebook", "listing_title": t} for m, a, t in (
        ("hi mate wud u take 150 given the condition can collect 2day", "200", "iPhone 12"),
        ("hi mate wud u take 90 given the condition can collect 2day", "120", "AirPods Pro"),
        ("hi mate is this still available wud u take 300 given the condition can collect tonight", "380",
         "iPhone 14 Pro"))]
    assert drafted(CRACKED, messages, reading("Small crack on the back"))[:2] == \
        ("ready", "hi mate wud u take 170 given the small crack on the back can collect 2day.")
    assert drafted(MINT, messages, reading())[:2] == ("ready", "hi mate wud u take 170 can collect 2day")


@pytest.mark.parametrize("sentence", [
    "would you take £[OFFER] given the condition of the screen?",  # says which part
    "would you take £[OFFER] given the state of the screen?",
    "would you take £[OFFER] given the condition and age?",
    "would you take £[OFFER] given the condition and that I can collect today?",
    "would you take £[OFFER] given the condition cash on collection?",  # "...given that it doesn't charge cash on..."
    "would you take £[OFFER] given the condition cash?",
    "would you take £[OFFER] given the condition and that?",
    "would you take £[OFFER] given the condition like the scratches?",
    "would you take £[OFFER] given the condition the phone is in?",
])
def test_a_tail_that_carries_your_reason_on_still_gets_no_wording(sentence):
    """The verifier's controls: these say more than the generic words, or read wrong swapped ('given that it doesn't
    charge cash?'), so the AI words them, flaw or none."""
    for point in (CRACK, NO_CHARGE, MARKS_AND_BATTERY, None):
        assert with_reason(sentence, "lower", point) is None


def test_no_wording_from_your_own_words_says_so_not_that_the_listing_has_none():
    """'there's no plain wording for what the listing says: Small crack on the back' blamed the listing."""
    messages = habit("would you take £X given the condition cash on collection?", closing="")
    assert drafted(CRACKED, messages, reading("Small crack on the back"))[2] == \
        ["your own sentence talks about the condition in words code can't put the listing's in: Small crack on the back"]
    assert drafted(MINT, messages, reading())[2] == \
        ["your offer sentence gives a reason about the condition this draft leaves out"]


@pytest.mark.parametrize("tail", ["tbh", "at all", "and can collect today"])
def test_at_asking_your_dont_mind_with_a_tail_takes_the_flaw_and_stays_with_none(tail):
    """'...don't mind the condition tbh.' was refused on every listing; taking it out would leave '...cash tbh.'."""
    messages = [{"my_message": m, "asking_price": a, "marketplace": "facebook", "listing_title": t} for m, a, t in (
        (f"Hi mate, is this still available? I can pay £200 cash, don't mind the condition {tail}. Can collect today.",
         "200", "iPhone 12"),
        (f"Hi mate, is this still available? I can pay £120 cash, don't mind the condition {tail}. Can collect today.",
         "120", "AirPods Pro"),
        ("Hi mate, is this still available? Would you take £300 cash given the condition? Can collect today.", "380",
         "iPhone 14 Pro"),
        ("Hi mate, is this still available? Would you take £150 cash given the condition? Can collect today.", "200",
         "iPhone 13"))]
    status, message, _ = drafted(CRACKED, messages, reading("Small crack on the back"), kind="asking")
    assert status == "ready" and f"don't mind the small crack on the back {tail}" in message
    assert drafted(DEAD_PORT, messages, reading("Doesn't charge"), kind="asking")[0] == "ready"
    status, message, _ = drafted(MINT, messages, reading(), kind="asking")
    assert status == "ready" and f"I can pay £200 cash, don't mind the condition {tail}" in message


def test_as_long_as_it_works_is_said_of_a_crack_never_of_a_phone_that_doesnt_charge():
    """'given that it doesn't charge as long as it works' contradicts itself: the checks refuse it."""
    messages = habit("would you take £X given the condition as long as it works?")
    assert drafted(CRACKED, messages, reading("Small crack on the back"))[:2] == \
        ("ready", "Hi mate, would you take £170 given the small crack on the back as long as it works? Can collect today.")
    assert drafted(DEAD_PORT, messages, reading("Doesn't charge"))[0] == "needs you"
    assert drafted(MINT, messages, reading())[:2] == ("ready", "Hi mate, would you take £170 as long as it works? "
                                                                "Can collect today.")


# ── leads-r4-asking-variants-twice: one "don't mind", wherever and however you say it ──

def asking_persona(asking_sentence):
    """2 at asking with your sentence, 2 lower offers that name the condition (so the flaw is given)."""
    return [{"my_message": m, "asking_price": a, "marketplace": "facebook", "listing_title": t} for m, a, t in (
        (f"Hi mate, is this still available? {asking_sentence.replace('£X', '£200')} Can collect today.", "200",
         "iPhone 12"),
        (f"Hi mate, is this still available? {asking_sentence.replace('£X', '£120')} Can collect today.", "120",
         "AirPods Pro"),
        ("Hi mate, is this still available? Would you take £300 cash given the condition? Can collect today.", "380",
         "iPhone 14 Pro"),
        ("Hi mate, is this still available? Would you take £150 cash given the condition? Can collect today.", "200",
         "iPhone 13"))]


@pytest.mark.parametrize("sentence, cracked, dead_port", [
    ("I can pay £X cash. Don't mind the condition.",
     "Hi mate, is this still available? I can pay £200 cash. Don't mind the small crack on the back. Can collect today.",
     "Hi mate, is this still available? I can pay £200 cash. Don't mind that it doesn't charge. Can collect today."),
    ("I can pay £X cash. Not fussed about the condition.",
     "Hi mate, is this still available? I can pay £200 cash. Not fussed about the small crack on the back. "
     "Can collect today.",
     "Hi mate, is this still available? I can pay £200 cash. Not fussed that it doesn't charge. Can collect today."),
    ("I can pay £X cash, don't care about the condition.",
     "Hi mate, is this still available? I can pay £200 cash, don't care about the small crack on the back. "
     "Can collect today.",
     "Hi mate, is this still available? I can pay £200 cash, don't care that it doesn't charge. Can collect today."),
    ("I can pay £X cash, dont care about the marks.",
     "Hi mate, is this still available? I can pay £200 cash, dont care about the small crack on the back. "
     "Can collect today.",
     "Hi mate, is this still available? I can pay £200 cash, dont care that it doesn't charge. Can collect today."),
])
def test_your_dont_mind_takes_the_flaw_once_in_its_own_sentence_or_words(sentence, cracked, dead_port):
    """'I can pay £200 cash. I don't mind the small crack on the back. Don't mind the condition.' and '...cash, don't
    care about the condition. I don't mind the small crack on the back.'"""
    messages = asking_persona(sentence)
    assert drafted(CRACKED, messages, reading("Small crack on the back"), kind="asking")[:2] == ("ready", cracked)
    assert drafted(DEAD_PORT, messages, reading("Doesn't charge"), kind="asking")[:2] == ("ready", dead_port)


def test_with_no_flaw_to_give_your_own_sentence_of_not_minding_stays():
    """It claims nothing: as you typed it on a mint listing (the comma form goes, as the first round has it)."""
    assert drafted(MINT, asking_persona("I can pay £X cash. Don't mind the condition."), reading(), kind="asking")[:2] == \
        ("ready", "Hi mate, is this still available? I can pay £200 cash. Don't mind the condition. Can collect today.")
    assert drafted(MINT, asking_persona("I can pay £X cash, don't care about the condition."), reading(),
                   kind="asking")[:2] == ("ready", "Hi mate, is this still available? I can pay £200 cash. Can collect today.")


@pytest.mark.parametrize("sentence", [
    "I can pay £X cash, condition doesn't bother me.",
    "I can pay £X cash, the condition doesn't matter.",
    "I can pay £X cash, happy with the condition.",
    "I can pay £X cash, the condition isn't an issue.",
    "I can pay £X cash, not bothered what condition it's in.",
    "I can pay £X cash. Condition doesn't bother me.",
])
def test_not_minding_in_words_code_cant_swap_gets_no_second_one(sentence):
    """No 'I don't mind the small crack on the back.' next to your 'condition doesn't bother me': the AI words it,
    and with no flaw to give it's sent as you typed it."""
    messages = asking_persona(sentence)
    for name in ("cracked", "dead port"):
        lst, read = READ[name]
        status, message, problems = drafted(lst, messages, read, kind="asking")
        assert (status, message) == ("needs you", None), name
        assert problems[0].startswith("your own sentence talks about the condition in words code can't put"), name
    status, message, _ = drafted(MINT, messages, reading(), kind="asking")
    assert status == "ready" and sentence.replace("£X", "£200") in message


def test_your_dont_mind_about_something_else_still_gets_the_flaw_after_it():
    """Not about the condition: the first round's control."""
    assert with_reason("I can pay £[OFFER], don't mind collecting.", "asking", CRACK) == \
        "I can pay £[OFFER], don't mind collecting. I don't mind the small crack on the back."
    assert with_reason("I can pay £[OFFER] cash if it's in good condition.", "asking", CRACK) is None  # never both


def test_your_reason_in_a_sentence_of_its_own_under_asking_takes_the_flaw_and_goes_on_mint():
    """The verifier's side check: 'Would you take £170, given the small crack on the back? Given the condition.', and
    on mint '...£170? Given the condition.'"""
    messages = [{"my_message": m, "asking_price": a, "marketplace": "facebook", "listing_title": t} for m, a, t in (
        ("Hi mate, would you take £150? Given the condition. Can collect today.", "200", "iPhone 12"),
        ("Hi mate, would you take £85? Given the condition. Can collect tonight.", "110", "AirPods Pro"),
        ("Hi mate, would you take £240? Given the condition. Can collect today.", "300", "iPhone 13 Pro"))]
    assert drafted(CRACKED, messages, reading("Small crack on the back"))[:2] == \
        ("ready", "Hi mate, would you take £170? Given the small crack on the back. Can collect today.")
    assert drafted(DEAD_PORT, messages, reading("Doesn't charge"))[:2] == \
        ("ready", "Hi mate, would you take £170? Given that it doesn't charge. Can collect today.")
    assert drafted(MINT, messages, reading())[:2] == ("ready", "Hi mate, would you take £170? Can collect today.")


# ── leads-r4-unlisted-leads: "bearing in mind", "for the condition it's in", "cus of"... ──

@pytest.mark.parametrize("reason, scratched", [
    ("bearing in mind the scratches", "Would you take £170 bearing in mind a few scratches on the screen?"),
    ("bearing in mind the condition", "Would you take £170 bearing in mind a few scratches on the screen?"),
    ("taking into account the condition", "Would you take £170 taking into account a few scratches on the screen?"),
    ("for the condition it's in", "Would you take £170 given a few scratches on the screen?"),
    ("cus of the scratches", "Would you take £170 cus of a few scratches on the screen?"),
    ("in light of the condition", "Would you take £170 in light of a few scratches on the screen?"),
])
def test_a_lead_the_first_round_didnt_list_takes_the_flaw_and_goes_on_mint(reason, scratched):
    """'Hi, would you take £170 bearing in mind the condition, given a few scratches on the screen?', and the
    generic reason kept on mint listings. These messages never greet, so no "Hi," either (learning-ai-r4-6)."""
    varied = [{"my_message": m, "asking_price": a, "marketplace": "facebook", "listing_title": "iPhone 12"}
              for m, a in ((f"Is this still available? Would you take £150 {reason}?", "180"),
                           (f"Still for sale? Would you take £90 {reason}?", "110"),
                           (f"Would you take £60 {reason}?", "80"))]
    assert drafted(SCRATCHED, varied, reading("Few scratches on the screen"))[:2] == ("ready", scratched)
    assert drafted(MINT, varied, reading())[:2] == ("ready", "Would you take £170?")


def test_taking_the_condition_into_account_is_left_to_the_ai():
    """Code can't put the flaw inside it: no wording, flaw or none, never ', given ...' after it."""
    sentence = "Would you take £[OFFER] taking the condition into account?"
    for point in (CRACK, NO_CHARGE, None):
        assert with_reason(sentence, "lower", point) is None


@pytest.mark.parametrize("sentence, crack, no_charge, two", [
    ("would you take £[OFFER] in view of the condition?", "would you take £[OFFER] in view of the small crack on the back?",
     "would you take £[OFFER] because it doesn't charge?",
     "would you take £[OFFER] in view of the light marks on the frame and because the battery health is 79%?"),
    ("would you take £[OFFER] owing to the condition?", "would you take £[OFFER] owing to the small crack on the back?",
     "would you take £[OFFER] because it doesn't charge?",
     "would you take £[OFFER] owing to the light marks on the frame and because the battery health is 79%?"),
    ("would you take £[OFFER] bearing in mind the condition?",
     "would you take £[OFFER] bearing in mind the small crack on the back?",
     "would you take £[OFFER] bearing in mind that it doesn't charge?",
     "would you take £[OFFER] bearing in mind the light marks on the frame and that the battery health is 79%?"),
    ("For the condition it's in, would you take £[OFFER]?", "Given the small crack on the back, would you take £[OFFER]?",
     "Given that it doesn't charge, would you take £[OFFER]?",
     "Given the light marks on the frame and that the battery health is 79%, would you take £[OFFER]?"),
    ("would you take £[OFFER] for its condition?", "would you take £[OFFER] given the small crack on the back?",
     "would you take £[OFFER] given that it doesn't charge?",
     "would you take £[OFFER] given the light marks on the frame and that the battery health is 79%?"),
    ("would you take £[OFFER] becoz of the scratches?", "would you take £[OFFER] becoz of the small crack on the back?",
     "would you take £[OFFER] becoz it doesn't charge?",
     "would you take £[OFFER] becoz of the light marks on the frame and becoz the battery health is 79%?"),
])
def test_each_new_lead_reads_with_things_and_facts(sentence, crack, no_charge, two):
    """Never 'in view it doesn't charge' nor 'for the small crack on the back' (what you'd pay for)."""
    assert with_reason(sentence, "lower", CRACK) == crack
    assert with_reason(sentence, "lower", NO_CHARGE) == no_charge
    assert with_reason(sentence, "lower", MARKS_AND_BATTERY) == two
    assert re.sub(r"\s+", " ", with_reason(sentence, "lower", None)) in ("would you take £[OFFER]?",
                                                                          "Would you take £[OFFER]?")


def test_for_the_phone_isnt_a_reason():
    sentence = "would you take £[OFFER] for the phone, given the condition?"
    assert with_reason(sentence, "lower", CRACK) == "would you take £[OFFER] for the phone, given the small crack on the back?"
    assert with_reason(sentence, "lower", None) == "would you take £[OFFER] for the phone?"
    assert with_reason("Would you take £[OFFER] for it?", "lower", CRACK) == \
        "Would you take £[OFFER] for it, given the small crack on the back?"


# ── leads-r4-led-capital: your capital on the first word only ──

@pytest.mark.parametrize("sentence, two", [
    ("Because of the condition, would you take £[OFFER]?",
     "Because of the light marks on the frame and because the battery health is 79%, would you take £[OFFER]?"),
    ("Cos of the condition would you take £[OFFER]?",
     "Cos of the light marks on the frame and cos the battery health is 79% would you take £[OFFER]?"),
    ("Would you take £[OFFER] Because of the condition?",
     "Would you take £[OFFER] Because of the light marks on the frame and because the battery health is 79%?"),
    ("because of the condition, would you take £[OFFER]?",
     "because of the light marks on the frame and because the battery health is 79%, would you take £[OFFER]?"),
])
def test_your_capitalised_lead_isnt_repeated_with_its_capital(sentence, two):
    """'...frame and Because the battery health is 79%', '...and Cos the battery...'."""
    assert with_reason(sentence, "lower", MARKS_AND_BATTERY) == two


def test_the_style_test_listing_reads_with_one_capital():
    e2 = {"id": "E2", "title": "iPhone 12 Pro 128GB Pacific Blue Unlocked", "asking_price": "190", "marketplace": "facebook",
          "description": "Good working order. Battery health 79%. Light marks on the frame, screen is perfect. Unlocked to "
                         "all networks. Collection from Leeds."}
    messages = habit("Because of the condition, would you take £X?", opener="Is this still available?")
    expected = ("ready", "Is this still available? Because of the light marks on the frame and because the battery "
                         "health is 79%, would you take £160? Can collect today.")
    assert drafted(e2, messages, None)[:2] == expected  # code reading the listing
    assert drafted(e2, messages, reading("Battery health 79%", "Light marks on the frame"))[:2] == expected


# ── leads-r4-clause-end-name-clash: each clause end its own name ──

def test_the_three_clause_ends_are_three_names_none_shadowed():
    """writer.CLAUSE_END was bound three times, so collecting_from ran on paid_at's regex."""
    assert not hasattr(writer, "CLAUSE_END")
    assert isinstance(writer.GENERIC_CLAUSE_END, str) and writer.GENERIC_CLAUSE_END in writer.GENERIC_REASON.pattern
    assert writer.PLACE_CLAUSE_END.pattern != writer.PAY_CLAUSE_END.pattern
    assert writer.collecting_from.__globals__["PLACE_CLAUSE_END"] is writer.PLACE_CLAUSE_END


@pytest.mark.parametrize("closing, said", [
    ("Can collect today - near you?", "Can collect today - near you?"),  # a place later in the clause
    ("Can collect today - at yours?", "Can collect today - at yours?"),
    ("Can collect today: at yours or in Leeds.", "Can collect today: at yours or in Leeds."),
    ("Can collect tonight since I'm at work in Leeds till 6.", "Can collect tonight since I'm at work in Leeds till 6."),
    ("Can collect today given I'm in Leeds anyway.", "Can collect today given I'm in Leeds anyway."),
    ("Can collect today then in town if easier.", "Can collect from Leeds LS6 today then in town if easier."),
])
def test_collecting_from_ends_the_clause_where_places_end_it(closing, said):
    assert collecting_from(closing, "Leeds LS6") == said


def test_paid_at_still_ends_the_clause_where_paying_ends_it():
    assert paid_at("I'll pay £[OFFER] cash if you can hold it for me.", "today") == \
        "I'll pay £[OFFER] cash today if you can hold it for me."
    assert paid_at("I can pay £[OFFER] - cash ready.", "tonight") == "I can pay £[OFFER] tonight - cash ready."
