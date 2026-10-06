"""Your past messages, searchable by meaning: a new listing finds the messages
you wrote for the most similar listings, and those become the AI's style
examples (not facts: the listing's facts come from the listing).

MiniLM, a small model that runs on this Mac, turns each listing into 384
numbers that sit close together when listings mean similar things ("iPhone 13
Midnight" near "iphone13 128gb black"). Chroma keeps the numbers and finds the
nearest. Everything stays in private/chroma, which is never uploaded.
"""

import re
from pathlib import Path

import chromadb

CHROMA_DIR = Path(__file__).resolve().parent.parent / "private" / "chroma"


def minilm():
    """The real embedder: text in, 384 numbers out, on this Mac (downloaded once, about 80 MB)."""
    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
    model = ONNXMiniLM_L6_V2()
    return lambda texts: [[float(x) for x in vector] for vector in model(texts)]


def listing_text(listing_title, marketplace=""):
    """What a listing is searched by: its title and where it was listed."""
    return f"{listing_title} {marketplace}".strip()


def gives_reason(found):
    """Whether a past message gives a flaw of the item as its reason ("as the back glass is cracked", "as the battery
    is at 81%"), as your style card counts one (flip.style.gives_flaw_in), and not praise ("it's in mint condition")."""
    from flip import style
    said = style.statements(found.get("my_message") or "")
    flaw = getattr(style, "gives_flaw_in", None) or (lambda text: bool(re.search(style.MENTIONS["condition"], text, re.I)))
    praise = getattr(style, "PRAISE", None)
    return flaw(praise.sub(" ", said) if praise is not None else said)


def offer_kind(found):
    from flip.style import kind_of
    return kind_of({"asking_price": found.get("asking_price") or "", "my_message": found.get("my_message") or ""})


def deal_rank(found, deal):
    """How well one past message fits the deal a draft is for, best first: the
    same way of buying (meeting the seller on Facebook or Gumtree, or paying
    through eBay or Vinted for a posted item); then a message that talks of
    nothing this listing rules out (collecting or postage, cash) before one
    that does (the drafter takes that out of what it shows, scrubbed, but
    what's left says less); then the same kind of offer (under, at or over
    asking) and giving a reason or not, as this draft will; then the same
    marketplace; then the nearest listing. A fact this can't tell (a message
    pasted with no asking price) counts half."""
    from flip.style import HABIT_WORDS, LOCAL_MARKETS, POSTED_MARKETS
    text, market = found.get("my_message") or "", found.get("marketplace") or ""
    rules = (bool(HABIT_WORDS["collecting"].search(text)) and deal.get("no_collecting", False)) or \
        (bool(HABIT_WORDS["cash"].search(text)) and not deal.get("cash_ok", True)) or \
        (bool(HABIT_WORDS["postage"].search(text)) and deal.get("no_posting", False))
    posted = True if POSTED_MARKETS.search(market) else False if LOCAL_MARKETS.search(market) else None
    way = 0.5 if posted is None else float(posted != deal.get("posted", False))
    kind = offer_kind(found)
    kind_off = 0.5 if kind is None or deal.get("kind") is None else float(kind != deal["kind"])
    reason_off = float(gives_reason(found) != deal.get("reason", False))
    same_market = (market.lower() == (deal.get("market") or "").lower()) if market and deal.get("market") else None
    market_off = 0.5 if same_market is None else float(not same_market)
    return (way, float(rules), kind_off + reason_off, market_off, found.get("distance", 0.0))


def chosen_for(ranked, deal, n):
    """The n examples for a deal, best first (ranked by deal_rank), as a set:
    when this draft gives a reason, at least one of them gives one, and at
    least one makes the same kind of offer: one with the same way of buying
    and nothing the listing rules out if there is one, else one with the same
    way of buying, else any (the drafter takes what the listing rules out out
    of the examples it shows: scrubbed)."""
    chosen = list(ranked[:n])
    needs = [gives_reason] if deal.get("reason") else []
    if deal.get("kind"):
        needs.append(lambda found: offer_kind(found) == deal["kind"])
    kept = set()
    for need in needs:
        have = next((i for i, found in enumerate(chosen) if need(found)), None)
        if have is not None:
            kept.add(have)
            continue
        extra = next((found for found in ranked[n:] if need(found) and deal_rank(found, deal)[:2] == (0.0, 0.0)), None) or \
            next((found for found in ranked[n:] if need(found) and deal_rank(found, deal)[0] == 0.0), None) or \
            next((found for found in ranked[n:] if need(found)), None)
        spare = next((i for i in range(len(chosen) - 1, -1, -1) if i not in kept), None)
        if extra is not None and spare is not None:
            chosen[spare] = extra
            kept.add(spare)
    return chosen


class MessageIndex:
    def __init__(self, path=CHROMA_DIR, embed=None):
        self.embed = embed or minilm()
        client = chromadb.PersistentClient(path=str(path))
        self.collection = client.get_or_create_collection("past_messages", embedding_function=None,
                                                          configuration={"hnsw": {"space": "cosine"}})

    def add(self, messages):
        """Add your past messages, or update them by id."""
        if not messages:
            return
        self.collection.upsert(
            ids=[m["id"] for m in messages],
            embeddings=self.embed([listing_text(m["listing_title"], m.get("marketplace", "")) for m in messages]),
            documents=[m["my_message"] for m in messages],
            metadatas=[{"listing_title": m["listing_title"], "marketplace": m.get("marketplace", ""),
                        "asking_price": m.get("asking_price") or ""} for m in messages])

    def ids(self):
        """The id of every message stored with today's fields. One an older
        version stored, with no asking price, counts as missing, so
        StyleBook.sync() stores it again and the deal can tell its kind of offer."""
        found = self.collection.get(include=["metadatas"])
        metas = found.get("metadatas")
        if metas is None:  # a store that can't say: every message counts as stored
            return list(found["ids"])
        return [id_ for id_, meta in zip(found["ids"], metas) if "asking_price" in (meta or {})]

    def remove(self, ids):
        """Forget messages by id."""
        if ids:
            self.collection.delete(ids=list(ids))

    def similar(self, text, n=3, leave_out=None, deal=None):
        """The n messages you wrote for the listings most like this one, nearest
        first. leave_out skips one message by id: when testing on your own
        messages, a message mustn't be its own example. deal: what the draft
        is for ({"posted", "kind", "reason", "market", "no_collecting",
        "cash_ok"}); with it, the messages for the same kind of deal come
        first (deal_rank) and the listing's likeness only breaks ties: an
        eBay draft is shown how you write on eBay, not your Facebook cash
        messages for the same phone."""
        count = self.collection.count()
        if not count:
            return []
        found = self.collection.query(query_embeddings=self.embed([text]), n_results=count if deal else min(count, n + 1),
                                      include=["documents", "metadatas", "distances"])
        results = [{"id": id_, "my_message": doc, **meta, "distance": distance}
                   for id_, doc, meta, distance in zip(found["ids"][0], found["documents"][0],
                                                      found["metadatas"][0], found["distances"][0])
                   if id_ != leave_out]
        if deal:
            return chosen_for(sorted(results, key=lambda found: deal_rank(found, deal)), deal, n)
        return results[:n]
