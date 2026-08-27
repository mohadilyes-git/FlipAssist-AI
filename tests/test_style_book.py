"""The messages your style is learned from: the style card and the message
search follow every message added or deleted, with no AI and nothing uploaded."""

from flip.retrieval import MessageIndex
from flip.style import StyleBook, phrase_rows, style_card, traits
from tests.fakes import fake_embed

SENT = [{"id": "m1", "listing_title": "iPhone 13 128GB", "asking_price": "220", "marketplace": "facebook",
         "my_message": "Hi mate, would you take £185 cash? Can collect today."},
        {"id": "m2", "listing_title": "PS5 Slim disc", "asking_price": "300", "marketplace": "facebook",
         "my_message": "Hi mate, would you take £255 cash? Can collect today."}]


def book(tmp_path, index=True):
    return StyleBook(tmp_path / "style.sqlite3",
                     MessageIndex(tmp_path / "chroma", embed=fake_embed) if index else None)


def test_the_search_follows_every_message_added_and_deleted(tmp_path):
    found = book(tmp_path)
    found.add(SENT, "csv")
    assert [m["id"] for m in found.index.similar("iPhone 13 128GB facebook", n=1)] == ["m1"]
    found.remove("m1")
    assert [m["id"] for m in found.index.similar("iPhone 13 128GB facebook")] == ["m2"]
    assert found.remove("m1") is False


def test_learning_the_same_messages_twice_keeps_one_copy(tmp_path):
    found = book(tmp_path)
    found.add(SENT, "csv")
    found.add(SENT, "csv")
    assert len(found.messages()) == 2 and sorted(found.index.ids()) == ["m1", "m2"]


def test_the_search_catches_up_with_messages_it_missed(tmp_path):
    book(tmp_path, index=False).add(SENT, "csv")  # stored, but never searched
    MessageIndex(tmp_path / "chroma", embed=fake_embed).add([{**SENT[0], "id": "gone"}])  # searched, but gone
    assert sorted(book(tmp_path).index.ids()) == ["m1", "m2"]


def test_the_card_is_the_one_your_messages_give_and_changes_with_them(tmp_path):
    found = book(tmp_path, index=False)
    found.add(SENT, "csv")
    assert found.card() == style_card(SENT)
    found.remove("m2")
    assert found.card()["messages"] == 1


def test_the_card_in_words():
    card = style_card(SENT)
    assert traits(card) == [("Opens with", "'Hi mate'"), ("Length", "about 10 words"),
                            ("Mentions", "collecting, cash and today"), ("Says the flaw", "no")]
    # the greeting and the offer share a sentence, so there's no opener of its own
    assert phrase_rows(card) == [("Offer sentence", "Hi mate, would you take £… cash?"), ("Closing", "Can collect today.")]
    assert traits({}) == [] and phrase_rows({}) == []
