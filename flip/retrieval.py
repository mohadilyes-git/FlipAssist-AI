"""Your past messages, searchable by meaning: a new listing finds the messages
you wrote for the most similar listings, and those become the AI's style
examples (not facts: the listing's facts come from the listing).

MiniLM, a small model that runs on this Mac, turns each listing into 384
numbers that sit close together when listings mean similar things ("iPhone 13
Midnight" near "iphone13 128gb black"). Chroma keeps the numbers and finds the
nearest. Everything stays in private/chroma, which is never uploaded.
"""

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
            metadatas=[{"listing_title": m["listing_title"], "marketplace": m.get("marketplace", "")} for m in messages])

    def ids(self):
        """The id of every message stored."""
        return self.collection.get(include=[])["ids"]

    def remove(self, ids):
        """Forget messages by id."""
        if ids:
            self.collection.delete(ids=list(ids))

    def similar(self, text, n=3, leave_out=None):
        """The n messages you wrote for the listings most like this one, nearest
        first. leave_out skips one message by id: when testing on your own
        messages, a message mustn't be its own example."""
        count = self.collection.count()
        if not count:
            return []
        found = self.collection.query(query_embeddings=self.embed([text]), n_results=min(count, n + 1),
                                      include=["documents", "metadatas", "distances"])
        results = [{"id": id_, "my_message": doc, **meta, "distance": distance}
                   for id_, doc, meta, distance in zip(found["ids"][0], found["documents"][0],
                                                      found["metadatas"][0], found["distances"][0])
                   if id_ != leave_out]
        return results[:n]
