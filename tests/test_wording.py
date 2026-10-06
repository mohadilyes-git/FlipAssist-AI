"""The reason, worded (flip.wording, 3 Oct 2026): flip-wording words the reader's flaw sentences, Haiku checks every
clause, Sonnet fixes only a flagged one, and every step falls back without stopping the draft. Pretend models only."""

from decimal import Decimal

from flip.ai import Reply
from flip.message_drafter import draft_message
from flip.offers import check_condition_talk, says_point
from flip.prompts import message_prompt
from flip.wording import CHECKER, SYSTEM, completed, flaw_lines, settings, tidy, worded_reason
from tests.fakes import FakeModel

LISTING = {"id": "l1", "title": "iPhone 13 128GB Blue unlocked",
           "description": "Hairline crack top left of the screen. Batt 79. Otherwise mint.",
           "asking_price": "200", "marketplace": "facebook"}
READING = {"flaws": ["Hairline crack top left of the screen", "Batt 79"], "pickup": "", "no_offers": "",
           "read_by": "flip-reader-5"}
CLAUSE = "there's a hairline crack on the top left of the screen and the battery health is 79%"


def models(wording=CLAUSE, check="ok", fix=None):
    """Fresh pretend models: flip-wording's answer, Haiku's verdict, Sonnet's (verdict, clause)."""
    found = {"wording": FakeModel("flip-wording-3", wording if isinstance(wording, Reply) else {"reason": wording}),
             "check": FakeModel("claude-haiku-5-5", check if isinstance(check, Reply) else {"verdict": check}),
             "fix": FakeModel("claude-sonnet-5-5", *([fix if isinstance(fix, Reply) else
                                                      {"verdict": fix[0], "clause": fix[1]}] if fix else []))}
    return found


def draft(kind="lower", wording=None, mode="auto", reading=READING, listing=LISTING):
    return draft_message(listing, {}, kind=kind, mention=True, reading=reading, writer="template", mode=mode,
                         wording=wording)


def test_the_reason_haiku_passes_is_the_messages_word_for_word():
    used = models()
    result = draft(wording=used)
    assert result["status"] == "ready"
    assert result["answer"]["message"] == f"Hi, would you take £170 cash for it? I'm offering that because {CLAUSE}. " \
                                          "I can come and collect."
    assert result["reason"] == {"clause": CLAUSE, "by": "flip-wording-3", "checked": "ok"}
    assert not used["fix"].asked  # Sonnet only sees what Haiku flags


def test_flip_wording_gets_the_prompt_it_was_trained_with_and_the_readers_whole_sentences():
    used = models()
    draft(wording=used)
    asked = used["wording"].asked[0]
    assert asked["system"] == SYSTEM
    assert asked["user"] == "Title: iPhone 13 128GB Blue unlocked\nThe seller's flaw words:\n" \
                            "- Hairline crack top left of the screen\n- Batt 79"
    assert asked["schema"] == {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}
    # Haiku gets the rules (cached), the seller's words and the clause
    check = used["check"].asked[0]
    assert check["system"][0]["text"] == CHECKER and check["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert flaw_lines(LISTING["title"], READING["flaws"]) in check["user"] and CLAUSE in check["user"]


def test_a_flagged_reason_is_sonnets_fix():
    better = "there's a hairline crack on the top left of the screen and the battery health is 79%"
    result = draft(wording=models(wording="there's a crack on the screen", check="fix", fix=("fix", better)))
    assert result["reason"] == {"clause": better, "by": "claude-sonnet-5-5", "checked": "fixed"}
    assert f"I'm offering that because {better}." in result["answer"]["message"]


def test_a_flagged_reason_sonnet_keeps_or_cant_fix_goes_out_as_flip_wording_wrote_it():
    for fix in (("ok", CLAUSE), Reply("claude-sonnet-5-5", error="couldn't reach the API", reachable=False)):
        result = draft(wording=models(check="fix", fix=fix))
        assert result["reason"] == {"clause": CLAUSE, "by": "flip-wording-3", "checked": "flagged, kept"}
        assert CLAUSE in result["answer"]["message"]


def test_a_check_that_fails_never_stops_the_draft():
    for check in (Reply("claude-haiku-5-5", error="the API said 529: overloaded"),
                  Reply("claude-haiku-5-5", error="couldn't reach the API", reachable=False)):
        result = draft(wording=models(check=check))
        assert result["reason"]["checked"] == "not checked" and result["status"] == "ready"

    class Broken:
        name = "claude-haiku-5-5"

        def ask(self, *args, **kwargs):
            raise TypeError("Could not resolve authentication method")  # no API key: the SDK raises, not answers

    result = draft(wording={**models(), "check": Broken()})
    assert result["reason"]["checked"] == "not checked" and CLAUSE in result["answer"]["message"]


def test_in_local_mode_nothing_leaves_this_mac():
    used = models()
    result = draft(wording=used, mode="local")
    assert result["reason"] == {"clause": CLAUSE, "by": "flip-wording-3", "checked": "not checked"}
    assert not used["check"].asked and not used["fix"].asked


def test_without_flip_wording_code_words_the_reason_as_before():
    before = draft()  # the step off (None): as before 3 Oct
    for wording in ({**models(), "wording": None},
                    models(wording=Reply("flip-wording-3", error="the local model isn't running", reachable=False)),
                    models(wording="")):
        result = draft(wording=wording)
        assert result.get("reason") is None
        assert result["answer"] == before["answer"] and result["status"] == before["status"]


def test_none_drops_the_reason_only_when_haiku_agrees():
    good = {**READING, "flaws": ["Battery health 92%"]}
    quiet = draft(wording=models(wording="none"), reading=good)
    assert quiet["reason"] is None if "reason" in quiet else True
    assert quiet["point"] == [] and quiet["mentioned"] is False  # flip-wording and Haiku: not a flaw by the rules
    unchecked = draft(wording=models(wording="none"), reading=good, mode="local")
    assert unchecked.get("reason") is None and unchecked["point"]  # unchecked: code words the reader's flaw


def test_battery_alone_keeps_alertflips_own_words():
    used = models()
    draft(wording=used, reading={**READING, "flaws": ["Battery health 80%"]})
    assert not used["wording"].asked  # "the battery health is 80%" is code's, exactly as AlertFlip says it


def test_asking_says_you_dont_mind_the_worded_reason():
    result = draft(kind="asking", wording=models())
    assert result["status"] == "ready"
    assert f"don't mind that {CLAUSE}" in result["answer"]["message"]


def test_every_step_is_costed_and_logged_as_the_reasons():
    class Log:
        def __init__(self):
            self.attempts = []

        def attempt(self, item_id, reply, problems, cost, job="draft"):
            self.attempts.append((item_id, reply.model, job, cost))

        def draft(self, result):
            result["draft_id"] = 1

    log = Log()
    used = models(check="fix", fix=("fix", CLAUSE + " and the back is scuffed"))
    used["check"].replies = [Reply("claude-haiku-5-5", answer={"verdict": "fix"}, tokens_in=200, tokens_out=10,
                                   tokens_cached=3000)]
    result = draft_message(LISTING, {}, kind="lower", mention=True, reading=READING, writer="template",
                           wording=used, log=log)
    reasons = [a for a in result["attempts"] if a.get("job") == "reason"]
    assert [a["model"] for a in reasons] == ["flip-wording-3", "claude-haiku-5-5", "claude-sonnet-5-5"]
    assert reasons[0]["cost_pence"] == 0  # flip-wording runs on this Mac
    # Haiku: 200 in + 3,000 from the cache at a tenth + 10 out = $0.0000550 = 0.0044p
    assert reasons[1]["cost_pence"] == Decimal("0.0044")
    assert [(m, j) for _, m, j, _ in log.attempts][:3] == [("flip-wording-3", "reason"), ("claude-haiku-5-5", "reason"),
                                                          ("claude-sonnet-5-5", "reason")]


def test_the_checks_take_a_worded_reason_as_the_listings_own_words():
    point = {"about": "flaw", "says": READING["flaws"], "worded": CLAUSE}
    message = f"Hi, would you take £170? I'm offering that because {CLAUSE}."
    assert says_point(message, point)
    listing = f"{LISTING['title']}. {LISTING['description']}"
    assert check_condition_talk(message, f"{listing}\n{CLAUSE}", point, True, "lower", 17000) == []


def test_the_ai_writer_is_given_the_worded_reason_to_use_as_it_is():
    point = {"about": "flaw", "says": READING["flaws"], "worded": CLAUSE}
    system, user = message_prompt(LISTING, 17000, [], [], "lower", point)
    assert f'"{CLAUSE}" (use this reason as it is)' in system + user


def test_a_quote_cut_at_a_colon_gets_the_rest_of_its_sentence():
    text = "Works for daily use, but sold under needs repair due to two specific faults: Face ID and the rear camera " \
           "don't work. Collection only."
    assert completed(["sold under needs repair due to two specific faults:", "Collection only"], text) == \
        ["sold under needs repair due to two specific faults: Face ID and the rear camera don't work.", "Collection only"]
    assert completed(["Cracked back"], text) == ["Cracked back"]  # not in the text, or no colon: as it is


def test_tidy():
    assert tidy("I'm offering that because the screen is cracked.") == "the screen is cracked"
    assert tidy(' "it’s locked to EE" ') == "it's locked to EE"
    assert tidy("None.") == "none" and tidy("AT&amp;T") == "AT&T"


def test_settings_read_the_environment_and_need_an_api_key_to_check(monkeypatch):
    monkeypatch.delenv("FLIP_WORDING_MODEL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert settings() == {"wording": "flip-wording-3", "check": "claude-haiku-5-5", "fix": "claude-sonnet-5-5"}
    monkeypatch.setenv("FLIP_WORDING_MODEL", "")
    assert settings()["wording"] == ""  # off: code words every reason
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert settings()["check"] == settings()["fix"] == ""  # no key: flip-wording's clause, unchecked


def test_no_flaws_nothing_to_word():
    assert worded_reason("iPhone", [], models=models()) is None
    assert worded_reason("iPhone", ["  "], models=models()) is None


def test_flip_wording_gets_the_readers_sentences_before_the_story_cut():
    """3 Oct: on 500 test listings code's story cut changed 8 quotes, and most lost the part or the fault
    ("I will say that the screen is quite scratched" -> "scratched and I tried to show that..."): flip-wording, which
    was trained on whole sentences and drops a story itself, gets them before the cut; code's wording still gets the cut."""
    listing = {**LISTING, "description": "I will say that the screen is quite scratched and I tried to show that on "
                                         "the last photos. Battery 88%."}
    quote = "I will say that the screen is quite scratched and I tried to show that on the last photos."
    reading = {"flaws": ["scratched and I tried to show that on the last photos."], "quotes": [quote], "pickup": "",
               "no_offers": "", "read_by": "flip-reader-5"}
    used = models(wording="the screen is quite scratched")
    result = draft(wording=used, reading=reading, listing=listing)
    assert used["wording"].asked[0]["user"].endswith(f"- {quote}")
    assert f"- {quote}" in used["check"].asked[0]["user"]  # Haiku checks it against the same sentence
    assert result["reason"]["clause"] == "the screen is quite scratched"
    # ...and the message checks take it as the listing's words: not "copies the seller's own story" (3 Oct review)
    assert result["status"] == "ready" and "because the screen is quite scratched." in result["answer"]["message"]
    without = draft(wording=models(wording="the screen is quite scratched"), listing=listing,
                    reading={k: v for k, v in reading.items() if k != "quotes"})
    assert without["reason"]["clause"] == "the screen is quite scratched"  # a reading without quotes: its flaws


def test_make_it_longer_and_rewrite_keep_the_reason_on_screen():
    """3 Oct review: wording the reason again brought back flip-wording's clause after Sonnet had fixed it, and paid
    for a check of a reason the message didn't give. The reason on screen is kept when the message still says it."""
    fixed = {"clause": "there's a hairline crack on the top left of the screen and the battery health is 79%",
             "by": "claude-sonnet-5-5", "checked": "fixed", "quotes": READING["flaws"]}
    shown = f"Hi, would you take £170 cash for it? I'm offering that because {fixed['clause']}. I can come and collect."
    used = models()
    result = draft_message(LISTING, {}, kind="lower", mention=True, reading=READING, writer="template",
                           wording=used, length="longer", previous=shown, reason_on_screen=fixed)
    assert result["reason"] == {k: fixed[k] for k in ("clause", "by", "checked")}
    assert not used["wording"].asked and not used["check"].asked
    gone = draft_message(LISTING, {}, kind="lower", mention=True, reading=READING, writer="template",
                         wording=(again := models()), length="longer", previous="Hi, would you take £170?",
                         reason_on_screen=fixed)  # you took the reason out: it's worded afresh
    assert again["wording"].asked and gone["reason"]["by"] == "flip-wording-3"


def test_a_reason_from_other_lines_is_worded_again_not_kept():
    """3 Oct: Rewrite kept a reason worded before the seller's "the phone turns off and on sometimes" was added to the
    description, and a new listing got the last one's "there's a scratch on the screen"."""
    old = {"clause": CLAUSE, "by": "flip-wording-3", "checked": "ok", "quotes": ["Batt 79"]}  # another reading's lines
    shown = f"Hi, would you take £170 cash for it? I'm offering that because {CLAUSE}. I can come and collect."
    for reason in (old, {k: v for k, v in old.items() if k != "quotes"}):  # other lines, or none given
        used = models()
        result = draft_message(LISTING, {}, kind="lower", mention=True, reading=READING, writer="template",
                               wording=used, rewrite_of=shown, reason_on_screen=reason)
        assert used["wording"].asked and result["reason"]["checked"] == "ok"  # worded and checked afresh
