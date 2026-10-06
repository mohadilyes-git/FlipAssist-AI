"""What your style learns, fixed after the second 26 Sep red team (learning-ai-r4-1 to r4-7, and the AI's side of
v8-integration-11): a time is left out of a habit only where you vary it and what's left reads, wherever it is in the
sentence; asking whether it's on hold or reserved, or whether the battery holds a charge, isn't asking them to hold it,
but "keep the phone for me" is; a closing you wrote with a kind of offer counts for it when that message ended with one
more sentence; "not much notice" isn't calling the offer low; no "Hi," for someone who never greets; and no emoji at or
over asking that isn't your habit. No AI runs: the AI, where there is one, is tests.fakes.FakeModel."""

import pytest

from flip.checks import HOLD, LOWBALL
from flip.message_drafter import check_ai_manner, draft_message
from flip.style import Habits, describe, for_kind, style_card
from tests.fakes import FakeModel

PLAIN = {"id": "x", "title": "iPhone 13 128GB Midnight", "description": "Good condition, unlocked, comes with box.",
         "asking_price": "200", "marketplace": "facebook"}
VINTED = {**PLAIN, "id": "v", "marketplace": "vinted"}


def past(*rows, market="facebook"):
    """Past messages: (text, asking pounds)."""
    return [{"id": f"m{n}", "my_message": text, "asking_price": str(asking), "marketplace": market,
             "listing_title": "iPhone 12 64GB"} for n, (text, asking) in enumerate(rows)]


def drafted(messages, kind="lower", ai=None, listing=PLAIN, **kwargs):
    """The drafter's message, as the red team ran it: your own sentences first, the AI (a FakeModel giving the replies
    in ai, again and again) only if they can't say it."""
    local = FakeModel("gemma3:4b", *[{"message": m} for m in ai] * 3) if ai else None
    api = FakeModel("claude-haiku-5-5", *[{"message": m} for m in ai] * 3) if ai else None
    result = draft_message(listing, style_card(messages) if messages else None, None, local, api, kind=kind, **kwargs)
    return result["status"], result["writer"], (result["answer"] or {}).get("message")


def told(messages, kind="lower", listing=PLAIN):
    """What the AI is told about your style: its "Usually..." and emoji lines."""
    fake = FakeModel("gemma3:4b", *[{"message": "x"}] * 4)
    draft_message(listing, style_card(messages), None, fake, None, kind=kind, writer="ai")
    return [line for line in fake.asked[0]["user"].splitlines() if "Usually" in line or "emoji" in line]


def habit(*ways):
    counted = Habits()
    for way in ways:
        counted.add(way)
    return counted.habit()


# ── learning-ai-r4-1: a time list after "either" or "both" left "Can collect either." ──────────────────────────

@pytest.mark.parametrize("rows, kind, message", [
    ((("Hi mate, would you take £150? Can collect either today or tomorrow.", 180),
      ("Hi mate, would you take £90? Can collect either tonight or tomorrow.", 110)), "lower",
     "Hi mate, would you take £170? Can collect either tonight or tomorrow."),
    ((("hiya would you take £150 cash? im free either 2day or 2moro", 180),
      ("hiya would you take £90 cash? im free either tonight or tmrw", 110),
      ("hiya would you take £60 cash? im free either today or tmrw", 80)), "lower",
     "hiya would you take £170 cash? im free either today or tmrw"),
    ((("Hi, would you take £150? Can pick it up either today or tomorrow.", 180),
      ("Hi, would you take £90? Can pick it up either this evening or tomorrow.", 110)), "asking",
     "Hi, I can pay £200. Can pick it up either this evening or tomorrow."),
    ((("Hi, would you take £150? Free to collect both today and tomorrow.", 180),
      ("Hi, would you take £90? Free to collect both tonight and tomorrow.", 110)), "lower",
     "Hi, would you take £170? Free to collect both tonight and tomorrow."),
    # the old ones, broken the same way before
    ((("Hi, would you take £150? Can collect as early as today.", 180),
      ("Hi, would you take £90? Can collect as early as tomorrow.", 110)), "lower",
     "Hi, would you take £170? Can collect as early as tomorrow."),
    ((("Hi, would you take £150? Can collect any time after today.", 180),
      ("Hi, would you take £90? Can collect any time after tomorrow.", 110)), "lower",
     "Hi, would you take £170? Can collect any time after tomorrow."),
    ((("Hi, would you take £150? Free any time up until tonight.", 180),
      ("Hi, would you take £90? Free any time up until tomorrow.", 110)), "lower",
     "Hi, would you take £170? Free any time up until tomorrow."),
    # the verifier's: the offer sentence, a sign-off after it, two text-speak messages
    ((("Hi, would you take £150 if I collect either today or tomorrow?", 180),
      ("Hi, would you take £90 if I collect either tonight or tomorrow?", 110)), "lower",
     "Hi, would you take £170 if I collect either tonight or tomorrow?"),
    ((("Hiya, would you take £150? Can collect either today or tomorrow 👍", 180),
      ("Hiya, would you take £90? Can collect either tonight or tomorrow 👍", 110)), "lower",
     "Hiya, would you take £170? Can collect either tonight or tomorrow 👍"),
    ((("hiya wud u take £150? can grab it either 2day or tmrw", 180),
      ("hiya wud u take £90? can grab it either 2nite or tmrw", 110)), "lower",
     "hiya wud u take £170? can grab it either 2nite or tmrw"),
    ((("Hi, would you take £150? I'm free both today and tomorrow to collect.", 180),
      ("Hi, would you take £90? I'm free both tonight and tomorrow to collect.", 110)), "lower",
     "Hi, would you take £170? I'm free both tonight and tomorrow to collect."),
])
def test_a_time_a_word_hangs_on_stays_as_you_wrote_it_newest(rows, kind, message):
    assert drafted(past(*rows), kind) == ("ready", "template", message)


def test_the_ai_is_told_the_closing_as_you_wrote_it():
    messages = past(("Hi mate, would you take £150? Can collect either today or tomorrow.", 180),
                    ("Hi mate, would you take £90? Can collect either tonight or tomorrow.", 110))
    assert '- Usually ends with "Can collect either tonight or tomorrow."' in told(messages)
    assert 'Usually ends with "Can collect either tonight or tomorrow."' in describe(style_card(messages))


def test_the_verifiers_controls_for_either():
    """The same either-sentence written twice is yours whole; a list of times at the very end still goes."""
    twice = past(("Hi mate, would you take £150? Can collect either today or tomorrow.", 180),
                 ("Hi mate, would you take £90? Can collect either today or tomorrow.", 110),
                 ("Hi mate, would you take £60? Can collect either tonight or tomorrow.", 80))
    assert drafted(twice)[2] == "Hi mate, would you take £170? Can collect either today or tomorrow."
    at_end = past(("Hi mate, would you take £150? Can collect today or tomorrow.", 180),
                  ("Hi mate, would you take £90? Can collect tonight or tomorrow.", 110))
    assert drafted(at_end)[2] == "Hi mate, would you take £170? Can collect."


# ── learning-ai-r4-3: a time inside a sentence was copied from your newest message into every draft ─────────────

@pytest.mark.parametrize("rows, kind, message", [
    ((("Hi, would you take £150 cash today? Can collect today after work.", 180),
      ("Hi, would you take £90 cash today? Can collect tonight after work.", 110),
      ("Hi, would you take £60? Can collect tomorrow after work.", 80)), "lower",
     "Hi, would you take £170 cash today? Can collect after work."),  # never "pay today, collect tomorrow"
    ((("Hi, would you take £150? Can collect today after work.", 180),
      ("Hi, would you take £90? Can collect tomorrow after work.", 110)), "lower",
     "Hi, would you take £170? Can collect after work."),
    ((("hi wud u take £150? can collect 2day if poss", 180), ("hi wud u take £90? can collect 2nite if poss", 110),
      ("hi wud u take £60? can collect tmrw if poss", 80)), "lower", "hi wud u take £170? can collect if poss"),
    ((("Hi, would you take £150? Can pop in today.", 180), ("Hi, would you take £90? Can pop in tomorrow.", 110)),
     "lower", "Hi, would you take £170? Can pop in."),
    ((("Hi, would you take £150? Can collect today, is that ok?", 180),
      ("Hi, would you take £90? Can collect tonight, is that ok?", 110)), "lower",
     "Hi, would you take £170? Can collect, is that ok?"),
    ((("Hi, would you take £150? Can collect today :)", 180), ("Hi, would you take £90? Can collect tomorrow :)", 110)),
     "lower", "Hi, would you take £170? Can collect :)"),
    ((("Hi, I'll pay £210 today if you can hold it for me.", 200),
      ("Hi, I'll pay £130 tomorrow if you can hold it for me.", 120)), "more",
     "Hi, I'll pay £210 if you can hold it for me."),
    ((("hi would you take £150 today for cash?", 180), ("hi would you take £90 tonight for cash?", 110)), "lower",
     "hi would you take £170 for cash?"),
    ((("Hi, I'll pay the full £200. Could you hold it till tonight for me?", 200),
      ("Hi, I'll pay the full £120. Could you hold it till tomorrow for me?", 120)), "asking",
     "Hi, I'll pay the full £200. Could you hold it for me?"),
    # the verifier's: text-speak, the offer sentence, and a time you always write kept when another one varies
    ((("hi wud u take £150 cash? can collect 2day after work", 180),
      ("hi wud u take £90 cash? can collect tmrw after work", 110)), "lower",
     "hi wud u take £170 cash? can collect after work"),
    ((("Hi, would you take £150 cash today if I come to you?", 180),
      ("Hi, would you take £90 cash tomorrow if I come to you?", 110)), "lower",
     "Hi, would you take £170 cash if I come to you?"),
    ((("Hi, I'll pay the full £200. Could you hold it till tonight for me? Can collect today.", 200),
      ("Hi, I'll pay the full £120. Could you hold it till tomorrow for me? Can collect today.", 120)), "asking",
     "Hi, I'll pay the full £200. Could you hold it for me? Can collect today."),
])
def test_the_time_you_vary_is_left_out_wherever_it_is(rows, kind, message):
    assert drafted(past(*rows), kind) == ("ready", "template", message)


def test_the_verifiers_controls_for_a_time_inside():
    """The same time written twice is yours; a time at the end still goes; the AI is told the closing without it."""
    twice = past(("Hi, would you take £150? Can collect today after work.", 180),
                 ("Hi, would you take £90? Can collect today after work.", 110),
                 ("Hi, would you take £60? Can collect tomorrow after work.", 80))
    assert drafted(twice)[2] == "Hi, would you take £170? Can collect today after work."
    at_end = past(("Hi, would you take £150? Can collect today.", 180), ("Hi, would you take £90? Can collect tomorrow.", 110))
    assert drafted(at_end)[2] == "Hi, would you take £170? Can collect."
    varied = past(("Hi, would you take £150? Can collect today after work.", 180),
                  ("Hi, would you take £90? Can collect tomorrow after work.", 110))
    assert 'Usually ends with "Can collect after work."' in describe(style_card(varied))


@pytest.mark.parametrize("ways, said", [
    # left out where what's left reads
    (("Can collect today and pay cash.", "Can collect tonight and pay cash."), "Can collect and pay cash."),
    (("I'm free today after 5.", "I'm free tomorrow after 5."), "I'm free after 5."),
    (("Can collect today, cash ready.", "Can collect tomorrow, cash ready."), "Can collect, cash ready."),
    (("Can come to yours today after work.", "Can come to yours tomorrow after work."), "Can come to yours after work."),
    (("Can pick it up today.", "Can pick it up tomorrow."), "Can pick it up."),
    (("Can collect later today.", "Can collect later tonight."), "Can collect later."),
    (("Can collect today x", "Can collect tonight x"), "Can collect x"),
    # ...else your newest, as you wrote it: never "Can collect morning.", "Can collect first thing.", "Ideally if
    # possible.", "Can collect or whenever suits.", "Can collect, tomorrow or Saturday."
    (("Can collect tomorrow morning.", "Can collect tmrw morning."), "Can collect tmrw morning."),
    (("Can collect first thing tomorrow.", "Can collect first thing today."), "Can collect first thing today."),
    (("Ideally today if possible.", "Ideally tomorrow if possible."), "Ideally tomorrow if possible."),
    (("I'd prefer tonight if poss.", "I'd prefer tomorrow if poss."), "I'd prefer tomorrow if poss."),
    (("Would tomorrow be ok to collect?", "Would tonight be ok to collect?"), "Would tonight be ok to collect?"),
    (("Can collect today or whenever suits.", "Can collect tonight or whenever suits."),
     "Can collect tonight or whenever suits."),
    (("Can collect today, tomorrow or Saturday.", "Can collect tonight, tomorrow or Saturday."),
     "Can collect tonight, tomorrow or Saturday."),
    (("Can collect by tonight at the latest.", "Can collect by tomorrow at the latest."),
     "Can collect by tomorrow at the latest."),
    (("Can collect today only.", "Can collect tomorrow only."), "Can collect tomorrow only."),
    (("Tonight's best for me.", "Tomorrow's best for me."), "Tomorrow's best for me."),
    (("Can collect today 6-7pm.", "Can collect tomorrow 6-7pm."), "Can collect tomorrow 6-7pm."),
    # a time you write every way isn't one you vary: the same words ways apart keep it
    (("Can collect today.", "Can collect today 👍"), "Can collect today 👍"),
    (("can collect today", "Can collect today."), "Can collect today."),
])
def test_a_time_comes_out_only_where_what_is_left_reads(ways, said):
    assert habit(*ways) == said


# ── learning-ai-r4-2: asking if it's on hold, or about the battery's charge, isn't asking them to hold it ──────

HOLD_PROBLEM = "a lower offer asks them to hold it: holding it is the deal for paying more"
ASKER = past(("Hi mate, would you take £150 cash? Can collect today.", 180),
             ("Hi mate, would you take £90 cash? Can collect tonight.", 110),
             ("Hi mate, would you take £250 cash? Can collect today.", 300))


@pytest.mark.parametrize("opener, offer, message", [
    ("Hi, is this still available or is it on hold?", "Would you take £{p}?",
     "Hi, is this still available or is it on hold? Would you take £170?"),
    ("Hiya, is it still available or reserved?", "Would you take £{p} cash?",
     "Hiya, is it still available or reserved? Would you take £170 cash?"),
    ("Hi, is this still available or has it been reserved?", "Would you take £{p} cash?",
     "Hi, is this still available or has it been reserved? Would you take £170 cash?"),
])
def test_your_opener_asking_if_its_on_hold_stays_on_a_lower_offer(opener, offer, message):
    messages = past(*[(f"{opener} {offer.format(p=p)}", p + 30) for p in (150, 90, 60)])
    assert drafted(messages) == ("ready", "template", message)
    # ...and the AI copying it isn't refused
    assert drafted(messages, writer="ai", ai=[message]) == ("ready", "gemma3:4b", message)


def test_on_vinted_at_asking_your_opener_asking_if_its_reserved_stays():
    messages = past(*[(f"Hi, is it still available or reserved? I can pay £{p}.", p) for p in (150, 90, 60)],
                    market="vinted")
    said = "Hi, is it still available or reserved? I can pay £200."
    assert drafted(messages, "asking", listing=VINTED) == ("ready", "template", said)
    assert drafted(messages, "asking", listing=VINTED, writer="ai", ai=[said]) == ("ready", "gemma3:4b", said)


@pytest.mark.parametrize("said", [
    "Hi mate, would you take £170 cash? Does the battery still hold a good charge? Can collect today.",
    "Hi mate, would you take £170 cash? Is the battery holding ok? Can collect today.",
    "Hi mate, would you take £170 cash? Does the battery hold a full charge? Can collect today.",
    "Hi mate, would you take £170 cash? How's the battery holding up? Can collect today.",  # the control
])
def test_the_ai_asking_about_the_battery_isnt_a_hold(said):
    assert drafted(ASKER, writer="ai", ai=[said]) == ("ready", "gemma3:4b", said)


def test_with_no_style_the_ai_asking_about_the_charge_isnt_a_hold():
    said = "Hi, would you take £170 cash? Does it still hold a decent charge? I can come and collect."
    assert drafted([], writer="ai", ai=[said]) == ("ready", "gemma3:4b", said)


@pytest.mark.parametrize("closing", ["Does the battery still hold a good charge?", "Not on hold for anyone is it?"])
def test_your_own_question_stays_in_a_lower_offer(closing):
    messages = past(*[(f"Hi, would you take £{p} cash? {closing}", a) for p, a in ((150, 180), (90, 110), (60, 80))])
    assert drafted(messages)[2] == f"Hi, would you take £170 cash? {closing}"
    assert f'Usually ends with "{closing}"' in describe(for_kind(style_card(messages), "lower"))


@pytest.mark.parametrize("said", [
    "If so could you hold it for me till Saturday?", "Any chance you could hold it till Saturday?",
    "Any chance of holding it till Saturday?", "Hoping you can reserve it for me till Saturday.",
    "Could you put it on hold for me?", "Can you keep it on hold for me?", "Could it be reserved for me?",
    "Could you keep it reserved for me till Saturday?",
])
def test_a_real_hold_in_a_later_sentence_is_still_refused(said):
    """The verifier's caution: a filter on "can you" let these through; they're still holds."""
    assert HOLD_PROBLEM in check_ai_manner(f"Hi mate, would you take £170 cash? {said} Can collect then.", "lower",
                                           17000, False)


@pytest.mark.parametrize("said", ["Is it already reserved?", "Is it still on hold?", "Unless it's reserved?",
                                  "Is this one reserved?", "It's not on hold is it?", "Does the battery hold much of a charge?",
                                  "Is the battery holding charge well?"])
def test_asking_whether_its_held_already_isnt_a_hold(said):
    assert not HOLD.search(said)


# ── learning-ai-r4-7: "keep the phone for me" and "can you keep it?" are holds ──────────────────────────────────

@pytest.mark.parametrize("said", ["Hi mate, would you take £170 cash? Can you keep the phone for me till Saturday?",
                                  "Hi mate, would you take £170 cash? If so can you keep it? Can collect Saturday.",
                                  "Hi mate, would you take £170 cash? Could you save the phone for me till Saturday?"])
def test_a_lower_offer_asking_them_to_keep_it_is_refused(said):
    assert drafted(ASKER, writer="ai", ai=[said])[0] == "needs you"
    assert HOLD_PROBLEM in check_ai_manner(said, "lower", 17000, False)


def test_your_own_keep_it_over_asking_is_the_one_reason():
    """Not "...if you can hold it for me. Can you keep it?" (two holds)."""
    messages = past(("Hi, I'll pay £210. Can you keep it?", 200), ("Hi, I'll pay £130. Can you keep it?", 120),
                    ("Hi, would you take £60? Can collect today.", 80))
    assert drafted(messages, "more") == ("ready", "template", "Hi, I'll pay £210. Can you keep it?")


@pytest.mark.parametrize("said", ["Happy to keep in touch", "Keep me posted", "Do I get to keep the box?",
                                  "Are you keeping the charger?", "Can I keep the case?", "That would save me a trip"])
def test_keeping_something_else_isnt_a_hold(said):
    assert not HOLD.search(said)


# ── learning-ai-r4-4: one message with one more sentence took your closing from that kind ───────────────────────

LOWER3 = [("Hi, would you take £150? Can collect today.", 180), ("Hi, would you take £90? Can collect today.", 110),
          ("Hi, would you take £250? Can collect today.", 300)]


@pytest.mark.parametrize("extra, kind, message", [
    (("Hi, I can pay £120. Can collect today. Cheers.", 120), "asking", "Hi, I can pay £200. Can collect today."),
    (("Hi, I'll pay £130 if you can hold it for me. Can collect today. Cheers.", 120), "more",
     "Hi, I can pay £210 if you can hold it for me. Can collect today."),
    (("Hi, I can pay £120. Can collect today, thanks.", 120), "asking", "Hi, I can pay £200. Can collect today."),
])
def test_your_closing_stays_when_one_message_of_that_kind_says_more(extra, kind, message):
    assert drafted(past(*LOWER3, extra), kind) == ("ready", "template", message)


def test_two_asking_messages_that_end_differently_keep_your_closing_for_every_kind():
    messages = past(*LOWER3, ("Hi, I can pay £120. Can collect today, cash ready.", 120),
                    ("Hi, I can pay £80. Can collect today. Thanks", 80))
    assert drafted(messages, "asking")[2] == "Hi, I can pay £200. Can collect today."
    assert drafted(messages, "more")[2] == "Hi, I can pay £210 if you can hold it for me. Can collect today."
    assert drafted(messages, "lower")[2] == "Hi, would you take £170? Can collect today."


def test_the_card_and_the_ais_description_keep_your_closing():
    card = style_card(past(*LOWER3, ("Hi, I can pay £120. Can collect today. Cheers.", 120)))
    phrases = card["phrases"]
    assert (phrases["closing"], phrases["closing_lower"], phrases["closing_asking"], phrases["closing_more"]) == \
        ("Can collect today.",) * 4
    assert 'Usually ends with "Can collect today."' in describe(card)
    cash_ready = past(("Hi mate, would you take £150? Can collect tonight.", 180),
                      ("Hi mate, would you take £90? Can collect tonight.", 110),
                      ("Hi mate, would you take £250? Can collect tonight.", 300),
                      ("Hi mate, I can pay £120. Can collect tonight. Cash ready.", 120))
    assert drafted(cash_ready, "asking")[2] == "Hi mate, I can pay £200. Can collect tonight."


def test_an_asking_message_that_ended_otherwise_still_takes_no_closing():
    """g6's deliberate case: "Cash waiting." alone on the one asking message isn't "Can collect tonight."."""
    one_asking = past(("Hi mate, I'll pay £290 if you can hold it for me. Can collect tonight.", 280),
                      ("Hi mate, I can pay £200 cash. Cash waiting.", 200),
                      ("Hi mate, would you take £120? Can collect tonight.", 150),
                      ("Hi mate, would you take £90? Can collect tonight.", 120))
    assert drafted(one_asking, "asking") == ("ready", "template", "Hi mate, I can pay £200.")


# ── learning-ai-r4-5: "not much notice" and "a bit less hassle" don't call the offer low ───────────────────────

NOTICE = [(f"Hi, would you take £{p}? I know it's not much notice but could I collect tonight?", a)
          for p, a in ((150, 180), (90, 110), (250, 300))]


def test_your_request_to_collect_tonight_stays_at_and_over_asking():
    assert drafted(past(*NOTICE), "asking")[2] == \
        "Hi, I can pay £200. I know it's not much notice but could I collect tonight?"
    assert drafted(past(*NOTICE), "more")[2] == \
        "Hi, I can pay £210 if you can hold it for me. I know it's not much notice but could I collect tonight?"
    textspeak = past(*[(f"hi would you take £{p}? i know its not a lot of notice but can i grab it tonight", a)
                       for p, a in ((150, 180), (90, 110), (250, 300))])
    assert drafted(textspeak, "asking")[2] == "hi i can pay £200. i know its not a lot of notice but can i grab it tonight"
    hassle = past(*[(f"Hi, would you take £{p}? Collection would be a bit less hassle than posting.", a)
                    for p, a in ((150, 180), (90, 110), (250, 300))])
    assert drafted(hassle, "asking")[2] == "Hi, I can pay £200. Collection would be a bit less hassle than posting."


def test_the_cheeky_control_still_goes_at_asking():
    cheeky = past(*[(f"Hi, would you take £{p}? I know it's a bit cheeky.", a) for p, a in ((150, 180), (90, 110), (250, 300))])
    assert drafted(cheeky, "asking")[2] == "Hi, I can pay £200."


@pytest.mark.parametrize("said", ["I know it's a bit under.", "Bit under, but cash ready.", "a tad lower 😬",
                                  "Would you go a bit lower for cash?", "a bit less if I collect today?",
                                  "A bit under asking I know", "I know it's not much but I can collect today"])
def test_lowball_still_reads_a_bit_under_said_of_the_offer(said):
    assert LOWBALL.search(said)


@pytest.mark.parametrize("said", ["I know it's not much notice but could I collect tonight?",
                                  "i know its not a lot of notice but can i grab it tonight",
                                  "Collection would be a bit less hassle than posting.",
                                  "I'm a little under 20 mins away so can collect today.", "I'm a bit less than an hour away",
                                  "I know it's not a lot of warning"])
def test_lowball_leaves_notice_hassle_and_distance_alone(said):
    assert not LOWBALL.search(said)


# ── learning-ai-r4-6: someone who never greets but opens differently each time got "Hi," ───────────────────────

VARIED = past(("Is this still available? Would you take £150?", 180), ("Still for sale? Would you take £90?", 110),
              ("Would you take £60 cash?", 80))


def test_someone_who_never_greets_gets_no_greeting_whatever_they_open_with():
    card = style_card(VARIED)
    assert card["no_greeting"] and card["phrases"]["opener"] is None
    assert drafted(VARIED) == ("ready", "template", "Would you take £170?")
    assert drafted(VARIED, "asking") == ("ready", "template", "I can pay £200.")
    assert drafted(VARIED, "more") == ("ready", "template", "I can pay £210 if you can hold it for me.")
    textspeak = past(("still available? wud u take £150", 180), ("is this still for sale? wud u take £90", 110),
                     ("wud u take £60 cash", 80))
    assert drafted(textspeak) == ("ready", "template", "wud u take £170")


def test_someone_who_greets_still_gets_hi():
    """The control: Hi, Hiya, Hello is a greeting, so "Hi,"."""
    greeters = past(("Hi, would you take £150 for it?", 180), ("Hiya, would you take £90 for it?", 110),
                    ("Hello, would you take £250 for it?", 300))
    assert drafted(greeters)[2] == "Hi, would you take £170 for it?"


# ── v8-integration-11 (the AI's side): one cheeky message's 😂 at the asking price ─────────────────────────────

LAUGH = past(("Hi mate, would you take £150? Cheeky I know 😂", 200))


def test_the_ai_isnt_told_one_cheeky_emoji_is_yours_at_or_over_asking():
    assert "- No emojis" in told(LAUGH, "asking") and "- No emojis" in told(LAUGH, "more")
    status, _, _ = drafted(LAUGH, "asking", writer="ai", ai=["Hi mate, I can pay £200 for it. 😂"])
    assert status == "needs you"
    cheeky = past(*[(f"Hi mate, would you take £{p}? Cheeky I know 😂", p + 40) for p in (150, 90, 60)])
    assert "- No emojis" in told(cheeky, "asking")


def test_an_emoji_that_is_your_habit_stays_and_under_asking_nothing_changes():
    thumbs = past(*[(f"Hi mate, would you take £{p}? 👍", p + 40) for p in (150, 90, 60)])
    assert "- Uses emojis" in told(thumbs, "asking")
    assert drafted(thumbs, "asking") == ("ready", "template", "Hi mate, I can pay £200. 👍")
    assert "- Uses emojis" in told(LAUGH, "lower")
    cheeky = past(*[(f"Hi mate, would you take £{p}? Cheeky I know 😂", p + 40) for p in (150, 90, 60)])
    assert drafted(cheeky) == ("ready", "template", "Hi mate, would you take £170? Cheeky I know 😂")
