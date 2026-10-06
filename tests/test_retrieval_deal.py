"""Choosing your past messages by the deal a draft is for (26 Sep): the style test showed an eBay draft shown your
Facebook cash messages for the same phone, and a draft giving a reason shown none of your reasons."""
import re

from flip.retrieval import MessageIndex, listing_text

WORDS = ["iphone", "13", "airpods", "ps5", "macbook", "facebook", "ebay", "vinted", "gumtree", "galaxy"]


def embed(texts):
    """A stand-in for MiniLM: one number per word above, so listings with the same words sit close."""
    return [[float(bool(re.search(rf"\b{w}\b", t.lower()))) + 0.01 for w in WORDS] for t in texts]


def index(tmp_path, messages):
    found = MessageIndex(path=tmp_path, embed=embed)
    found.add([{"id": f"m{i}", "listing_title": t, "marketplace": m, "asking_price": a, "my_message": text}
               for i, (m, t, a, text) in enumerate(messages)])
    return found


PAST = [
    ("facebook", "iPhone 13", "220", "Hi mate, would you take £170 cash? Can collect today."),
    ("facebook", "iPhone 13", "200", "Hi mate, would you take £160 cash? Can collect tonight."),
    ("facebook", "iPhone 13", "210", "Hi mate, would you do £180 cash? Can pick it up later."),
    ("ebay", "AirPods", "120", "Hi mate, would you take £95? Can pay straight away."),
    ("vinted", "PS5", "300", "Hi mate, would you do £250? Can pay now."),
    ("ebay", "MacBook", "400", "Hi mate, I'll pay the full £400. Can pay straight away."),
    ("facebook", "Galaxy", "180", "Hi mate, as the screen is cracked would you take £140 cash? Can collect today."),
]
EBAY_LOWER = {"posted": True, "kind": "lower", "reason": False, "market": "ebay", "no_collecting": True, "cash_ok": False}


def test_an_ebay_draft_is_shown_how_you_write_on_ebay_not_your_facebook_cash_messages_for_the_same_phone(tmp_path):
    found = index(tmp_path, PAST)
    old = found.similar(listing_text("iPhone 13", "ebay"))
    assert all(m["marketplace"] == "facebook" for m in old)  # the listing's likeness alone: same phone, wrong deal
    new = found.similar(listing_text("iPhone 13", "ebay"), deal=EBAY_LOWER)
    assert [m["marketplace"] for m in new] == ["ebay", "vinted", "ebay"]
    assert not any(re.search(r"\b(?:cash|collect)\b", m["my_message"]) for m in new)


def test_a_draft_that_gives_a_reason_is_shown_one_of_your_reasons_even_from_where_you_meet_the_seller(tmp_path):
    found = index(tmp_path, PAST)
    new = found.similar(listing_text("iPhone 13", "ebay"), deal={**EBAY_LOWER, "reason": True})
    assert any("cracked" in m["my_message"] for m in new)  # its cash and collecting are taken out when it's shown
    assert sum(m["marketplace"] in ("ebay", "vinted") for m in new) == 2


def test_a_draft_at_asking_is_shown_how_you_offer_the_asking_price(tmp_path):
    found = index(tmp_path, PAST)
    new = found.similar(listing_text("iPhone 13", "ebay"), deal={**EBAY_LOWER, "kind": "asking"})
    assert any("the full" in m["my_message"] for m in new)


def test_a_facebook_draft_is_shown_your_facebook_messages_nearest_listing_first(tmp_path):
    found = index(tmp_path, PAST)
    deal = {"posted": False, "kind": "lower", "reason": False, "market": "facebook", "no_collecting": False,
            "cash_ok": True}
    new = found.similar(listing_text("iPhone 13", "facebook"), deal=deal)
    assert [m["listing_title"] for m in new] == ["iPhone 13", "iPhone 13", "iPhone 13"]


def test_with_no_deal_the_nearest_listings_come_first_as_before(tmp_path):
    found = index(tmp_path, PAST)
    assert [m["id"] for m in found.similar(listing_text("iPhone 13", "facebook"))] == ["m0", "m1", "m2"]
    assert [m["id"] for m in found.similar(listing_text("iPhone 13", "facebook"), leave_out="m0")] == ["m1", "m2", "m6"]


# the second red team (26 Sep), on the deal patch
def test_a_facebook_listing_with_no_cash_is_shown_your_facebook_messages_not_your_ebay_pay_now_ones(tmp_path):
    found = index(tmp_path, PAST)
    deal = {"posted": False, "kind": "lower", "reason": False, "market": "facebook", "no_collecting": False,
            "cash_ok": False}  # "Bank transfer upon collection": the drafter takes the cash out of what it shows
    new = found.similar(listing_text("iPhone 13", "facebook"), deal=deal)
    assert all(m["marketplace"] == "facebook" for m in new)


def test_praise_is_not_a_reason(tmp_path):
    past = PAST + [("facebook", "iPhone 12", "500", "Hiya, I'll pay £520 if you hold it for me, it's in mint condition."),
                   ("facebook", "Galaxy", "120", "Hi mate, as the battery is at 81% would you take £100 cash?")]
    found = index(tmp_path, past)
    deal = {"posted": False, "kind": "lower", "reason": True, "market": "facebook", "no_collecting": False, "cash_ok": True}
    new = found.similar(listing_text("iPhone 13", "facebook"), deal=deal)
    assert not any("mint condition" in m["my_message"] for m in new)
    assert any("81%" in m["my_message"] or "cracked" in m["my_message"] for m in new)


def test_a_message_stored_before_the_asking_price_was_kept_counts_as_missing_so_sync_stores_it_again(tmp_path):
    found = MessageIndex(path=tmp_path, embed=embed)
    found.collection.upsert(ids=["old"], embeddings=embed(["iPhone 13 facebook"]), documents=["Hi, I'll take it at £400."],
                            metadatas=[{"listing_title": "iPhone 13", "marketplace": "facebook"}])
    assert found.ids() == []
    found.add([{"id": "old", "listing_title": "iPhone 13", "marketplace": "facebook", "asking_price": "400",
                "my_message": "Hi, I'll take it at £400."}])
    assert found.ids() == ["old"]


def test_a_collection_only_listing_is_not_shown_your_messages_asking_for_postage(tmp_path):
    past = [("facebook", "iPhone 13", "220", "Hi, would you take £170? Could you post it?"),
            ("facebook", "iPhone 12", "200", "Hi, would you take £150? Could you post it?"),
            ("facebook", "PS5", "300", "Hi, would you take £250? Can collect today."),
            ("facebook", "Galaxy", "180", "Hi, would you take £140? Can collect tonight.")]
    found = index(tmp_path, past)
    deal = {"posted": False, "kind": "lower", "reason": False, "market": "facebook", "no_collecting": False,
            "cash_ok": True, "no_posting": True}
    new = found.similar(listing_text("iPhone 13", "facebook"), n=2, deal=deal)
    assert not any("post it" in m["my_message"] for m in new)


def test_an_older_store_gets_the_asking_price_when_the_app_opens_it_and_is_then_shown_its_kind(tmp_path):
    from flip.style import StyleBook
    rows = [("facebook", "iPhone 13", "400", "Hi, I'll take it at £400. Thanks"),
            ("facebook", "iPhone 12", "300", "Hi, would you take £250? Thanks"),
            ("facebook", "Galaxy", "200", "Hi, would you take £160? Thanks")]
    old = MessageIndex(path=tmp_path / "chroma", embed=embed)
    old.collection.upsert(ids=[f"m{i}" for i in range(3)], embeddings=embed([f"{t} {m}" for m, t, _, _ in rows]),
                          documents=[x for _, _, _, x in rows],
                          metadatas=[{"listing_title": t, "marketplace": m} for m, t, _, _ in rows])  # as before the patch
    book = StyleBook(path=tmp_path / "style.sqlite3", index=None)
    book.add([{"id": f"m{i}", "listing_title": t, "asking_price": a, "marketplace": m, "my_message": x}
              for i, (m, t, a, x) in enumerate(rows)], "added")
    book = StyleBook(path=tmp_path / "style.sqlite3", index=MessageIndex(path=tmp_path / "chroma", embed=embed))  # sync()
    deal = {"posted": False, "kind": "asking", "reason": False, "market": "facebook", "no_collecting": False, "cash_ok": True}
    shown = book.index.similar(listing_text("iPhone 11", "facebook"), n=2, deal=deal)
    assert any("I'll take it at" in m["my_message"] for m in shown)
    assert all(m.get("asking_price") for m in book.index.similar(listing_text("iPhone 11", "facebook"), n=3))
