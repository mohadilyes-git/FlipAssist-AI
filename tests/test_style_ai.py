"""Our AI reading your style (flip.style_ai, 3 Oct 2026): its suggestions are used only where code checks they're in
your messages, only in the gaps code left, and marked as found by our AI. Made-up messages, a pretend model."""

from flip.message_drafter import draft_message
from flip.style import StyleBook, shortcuts_of, shortened, without
from flip.style_ai import checked, merged, tidy
from tests.fakes import FakeModel

TITLES = ["PS5 Disc Edition", "AirPods Pro 2", "Nintendo Switch OLED", "iPhone 13 128GB", "Dyson V11"]
JO = [{"listing_title": t, "asking_price": "200", "marketplace": "facebook", "my_message": text} for t, text in zip(TITLES, [
    "hiya, wud u take 150 for the ps5? can collect 2day. ta jo x",
    "hiya wud u take 90 for the airpods, can collect 2day. ta jo x",
    "hiya, wud u take 180? love the switch. ta jo x",
    "hiya wud u take 150 for the iphone? can collect 2day. ta jo x",
    "hiya, wud u take 160 for the dyson. ta jo x"])]
SAID = {"greeting": "hiya", "offer": "wud u take 150", "after_offer": ["can collect 2day", "I am paying cash"],
        "likes": "love the switch", "sign_off": "ta jo x",
        "short_words": [{"word": "you", "written": "u"}, {"word": "today", "written": "2day"},
                        {"word": "PS5", "written": "ps"}]}


def test_only_a_sign_off_that_ends_your_messages_is_kept():
    found = checked(SAID, JO)
    assert set(found) == {"sign_off"} and found["sign_off"][0] == "ta jo x"  # the AI fills the sign-off only (3 Oct)
    assert shortcuts_of(JO) == {"you": "u", "would": "wud"}  # code's, from a fixed list ("2day" stays in their sentences)
    for sign in ("lol", "can collect today, cheers x", "cheers from Leeds x", "Unlocked?", "thanks 150"):
        assert checked({**SAID, "sign_off": sign}, JO) == {}, sign  # no thanks/smiley/kiss, or more than a name in it
    assert checked(SAID, JO[:1]) == {}  # one message shows no habit
    assert tidy({"greeting": ["hiya"], "sign_off": 5, "after_offer": [{"x": 1}, "ok"]}) == {"after_offer": ["ok"]}


def test_what_our_ai_found_fills_the_sign_off_only_and_is_marked():
    card = {"messages": 5, "phrases": {"offer": "Would you take £[OFFER]?", "closing": "Can collect. ta jo x"}, "mentions": []}
    filled = merged(card, checked(SAID, JO), JO)
    assert filled["signature"] == "ta jo x" and filled["ai_found"] == ["signature"]
    assert filled["phrases"]["closing"] == "Can collect."  # once: out of the closing
    assert "greeting" not in filled and filled["phrases"]["offer"] == "Would you take £[OFFER]?"
    assert merged({**card, "signature": "Cheers, Dan"}, checked(SAID, JO), JO)["signature"] == "Cheers, Dan"  # code's stays


def test_the_book_learns_with_our_ai_once_and_lists_what_it_found(tmp_path):
    ai = FakeModel("gemma3:4b", SAID)
    book = StyleBook(tmp_path / "style.sqlite3", ai=ai)
    book.add([{k: m[k] for k in ("listing_title", "asking_price", "marketplace", "my_message")} for m in JO], "added")
    assert book.ai_stale() and book.learn_with_ai() and not book.ai_stale()
    assert not book.learn_with_ai() and len(ai.asked) == 1  # read once for these messages
    rows = {r["key"]: (r["what"], r["value"]) for r in book.learned()}
    assert rows["shortcut:you"] == ('Writes "you" as', "u")  # code's
    assert rows["signature"] == ("Signs off with (found by our AI)", "ta jo x")
    assert rows["phrase:closing:can collect 2day."] == ("Closing", "can collect 2day.")  # code's, its sign-off once
    assert StyleBook(tmp_path / "plain.sqlite3").learn_with_ai() is False  # no AI: code alone


def test_a_draft_writes_your_shortcuts_after_the_checks(tmp_path):
    book = StyleBook(tmp_path / "style.sqlite3", ai=FakeModel("gemma3:4b", SAID))
    book.add([{k: m[k] for k in ("listing_title", "asking_price", "marketplace", "my_message")} for m in JO], "added")
    book.learn_with_ai()
    listing = {"title": "iPhone 14", "description": "Collection from Leeds.", "asking_price": "300", "marketplace": "facebook"}
    message = draft_message(listing, book.card(), kind="asking", mention=True, writer="template")["answer"]["message"]
    assert " you " not in f" {message} " and message.endswith("ta jo x"), message
    assert shortened("Could you hold it till today?", {"you": "u", "could": "cud"}) == "Cud u hold it till today?"
    assert shortened("You can collect?", {"you": "u"}) == "U can collect?"
    # never a contraction, a name or place's capital, nor what's kept word for word (3 Oct review)
    assert shortened("I know you're busy, you'd hold it?", {"you": "u"}) == "I know you're busy, you'd hold it?"
    assert shortened("Hi. Would You Like It, the album?", {"would": "wud", "you": "u"}) == "Hi. Wud You Like It, the album?"
    assert shortened("Would you take £150, given that you can see the crack?", {"you": "u"},
                     keep=("you can see the crack",)) == "Would u take £150, given that you can see the crack?"
    gone = without(book.learned_card(), {"shortcut:you"})
    assert "you" not in gone["shortcuts"]


def test_a_sign_off_is_checked_by_how_messages_end():
    """3 Oct eval: "🚗 thanks so much 😊" ends with "thanks so much 😊"."""
    nat = [{**m, "my_message": text} for m, text in zip(JO, [
        "Hey would £260 work? can collect asap 🚗 thanks so much 😊", "Hey would £95 work? 🚗 thanks so much 😊",
        "Hey would £180 work? 🙏 thanks so much 😊", "Hey would £130 work? can collect asap thanks so much 😊",
        "Hey would £160 work? thanks so much 😊"])]
    assert checked({"sign_off": "thanks so much 😊"}, nat)["sign_off"][0] == "thanks so much 😊"
