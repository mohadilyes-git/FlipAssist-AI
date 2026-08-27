"""Your writing style, from the messages you've sent to sellers. Plain code,
no AI:

1. A style card: what your messages have in common, such as the greeting you
   open with, how long they are, emojis, and what you usually mention.
2. Your old prices hidden as [OFFER], so an example shows how you word an
   offer without handing the AI a number to copy.
3. Your phrasebook: the opener, offer and closing sentences you use again and
   again, which flip.writer turns into a whole message with no AI.

StyleBook keeps the messages it all comes from, on this Mac.
"""

import csv
import re
import sqlite3
import statistics
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from flip.catalogue import words
from flip.checks import promised_in

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
GREETING_WORDS = {"hi", "hiya", "hello", "hey", "alright", "morning", "afternoon", "evening", "yo"}
MENTIONS = {"collecting": r"\bcollect(?:ion|ing)?\b", "cash": r"\bcash\b", "today": r"\b(?:today|tonight|asap)\b",
            "postage": r"\bpost(?:age|ed)?\b",
            "condition": r"\b(?:condition|scratch\w*|crack\w*|dent(?:s|ed)?|scuff\w*|chip(?:s|ped)?|marks?|broken|"
                         r"damage\w*|fault\w*|flaw\w*|wear|mint)\b"}
SHARE = 0.4  # a habit is something at least 40% of your messages do
HABIT = 2  # a sentence in at least 2 of your messages is one you'd write again
SENTENCES = re.compile(r"(?<=[.!?])\s+")
# one whole emoji, its skin tone and joins included: "👍🏽" is one, and a lone "🏽" is none
WHOLE_EMOJI = re.compile("[\U0001F300-\U0001F3FA\U0001F400-\U0001FAFF☀-➿]"
                         "(?:[\U0001F3FB-\U0001F3FF]|\ufe0f|\u200d[\U0001F300-\U0001FAFF☀-➿])*")
# the asking price said back, which isn't an offer: "still available at £220?", "you're asking £220"
ASKING_SAID = re.compile(r"\b(?:available (?:at|for)|asking|listed (?:at|for)|price (?:is|of)|priced at)\s+£",
                         re.IGNORECASE)
# title words that don't name the item
TITLE_FILLER = {"with", "and", "for", "the", "of", "in", "on", "to", "or", "plus", "new", "used"}
AMOUNT = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?"  # a comma only between thousands: "£185, cash" keeps its comma
STYLE_DB = Path(__file__).resolve().parent.parent / "private" / "style.sqlite3"
FIELDS = ("id", "listing_title", "asking_price", "marketplace", "my_message", "source", "at")
TABLE = """
create table if not exists messages (
    n integer primary key, id text unique, listing_title text, asking_price text, marketplace text,
    my_message text, source text, at text);
"""
OLD_PRICE = re.compile(rf"£\s?{AMOUNT}"
                       rf"|\b{AMOUNT}\s?(quid|pounds)\b"
                       rf"|\b(take|do|accept|consider|offer|pay|stretch to|go to|let it go for)\s+{AMOUNT}\b",
                       re.IGNORECASE)


def load_messages(path):
    """Your past messages from a CSV: testset/messages.example.csv shows the columns."""
    with open(path, newline="", encoding="utf-8-sig") as f:  # -sig: Excel's UTF-8 marker
        return [{key: (value or "").strip() for key, value in row.items()} for row in csv.DictReader(f)]


def without_prices(text):
    """"Would you take £170? or 170 quid" -> "Would you take £[OFFER]? or [OFFER] quid"."""
    def hide(match):
        if match.group(1):
            return f"[OFFER] {match.group(1)}"
        if match.group(2):
            return f"{match.group(2)} [OFFER]"
        return "£[OFFER]"
    return OLD_PRICE.sub(hide, text)


def opening(text):
    """The greeting a message opens with: "Hi mate, is this..." -> "Hi mate"."""
    first = re.split(r"[,.!?\n]", text.strip(), maxsplit=1)[0].strip()
    return first if 0 < len(first.split()) <= 3 and first.split()[0].lower() in GREETING_WORDS else ""


def style_card(messages):
    """What your messages have in common. Empty if there are none yet."""
    texts = [m["my_message"] for m in messages if m.get("my_message")]
    if not texts:
        return {}
    share = lambda found: sum(found) / len(texts) >= SHARE
    card = {"messages": len(texts), "words": int(statistics.median(len(t.split()) for t in texts)),
            "questions": int(statistics.median(t.count("?") for t in texts)),
            "emoji": share(bool(EMOJI.search(t)) for t in texts),
            "mentions": [name for name, pattern in MENTIONS.items()
                         if share(bool(re.search(pattern, t, re.IGNORECASE)) for t in texts)]}
    greeting, times = Counter(opening(t) for t in texts).most_common(1)[0]
    if greeting and times / len(texts) >= SHARE:
        card["greeting"] = greeting
    card["phrases"] = phrasebook([m for m in messages if m.get("my_message")])
    card["promises"] = sorted(set().union(*(promised_in(t) for t in texts)))
    return card


def phrasebook(messages):
    """The sentences you write around an offer, with old prices hidden: your
    opener ("Hi mate, is this still available?"), how you word the offer
    ("Would you take £[OFFER] cash?") and your closing ("Can collect today."),
    each the one you use most if it's in at least HABIT messages, else None
    ("" when that's nothing: most of your messages start with the offer).
    Plus the emoji you use most, or "". Only messages with one price count,
    so the price in a habit is always the offer, and a sentence that names
    its own item ("is the iPhone still available?") is never a habit."""
    openers, offers, closings, emoji = Counter(), Counter(), Counter(), Counter()
    for m in messages:
        if len(OLD_PRICE.findall(m["my_message"])) != 1 or ASKING_SAID.search(m["my_message"]):
            continue  # one price, the offer: not "still available at £220?" or "you're asking £220"
        text = without_prices(m["my_message"])
        emoji.update(WHOLE_EMOJI.findall(text))
        item = {w for w in words(m.get("listing_title") or "") if w not in TITLE_FILLER}
        names_item = lambda sentence: bool(item & set(words(sentence)))
        sentences = [s.strip() for s in SENTENCES.split(text.strip()) if s.strip()]
        at = next(i for i, s in enumerate(sentences) if "[OFFER]" in s)
        opener, offer, closing = " ".join(sentences[:at]), sentences[at], " ".join(sentences[at + 1:])
        for counts, sentence in ((openers, opener), (offers, offer), (closings, closing)):
            if not names_item(sentence):
                counts[sentence] += 1
    habit = lambda counts: next((text for text, n in counts.most_common() if n >= HABIT), None)
    return {"opener": habit(openers), "offer": habit(offers), "closing": habit(closings),
            "emoji": emoji.most_common(1)[0][0] if emoji else ""}


def describe(card, words=None):
    """The style card as short lines for the AI (and for you to check). words
    takes the place of your usual length, for a longer message."""
    if not card:
        return []
    lines = [f'Opens with "{card["greeting"]}"'] if card.get("greeting") else []
    lines += [f"About {words or card['words']} words",
              f"Usually asks {card['questions']} question{'' if card['questions'] == 1 else 's'}",
              "Uses emojis" if card["emoji"] else "No emojis"]
    if card["mentions"]:
        lines.append(f"Usually mentions: {', '.join(card['mentions'])}")
    return lines


def and_list(names):
    """["cash", "collecting"] -> "cash and collecting"."""
    return " and ".join([", ".join(names[:-1]), names[-1]]) if len(names) > 1 else "".join(names)


def traits(card):
    """The style card as the app shows it: [("Opens with", "'Hi mate'"),
    ("Length", "about 12 words"), ("Mentions", "cash and collecting"),
    ("Says the flaw", "yes")]. Empty before there are any messages."""
    if not card:
        return []
    said = [name for name in card["mentions"] if name != "condition"]
    rows = [("Opens with", f"'{card['greeting']}'")] if card.get("greeting") else []
    rows.append(("Length", f"about {card['words']} words"))
    if said:
        rows.append(("Mentions", and_list(said)))
    if card["emoji"]:
        rows.append(("Emojis", "yes"))
    rows.append(("Says the flaw", "yes" if "condition" in card["mentions"] else "no"))
    return rows


def phrase_rows(card):
    """The phrasebook as the app shows it, the offer price left out:
    [("Usual opener", "Hi mate,"), ("Offer sentence", "Would you take £… cash?")]."""
    book = (card or {}).get("phrases") or {}
    named = (("opener", "Usual opener"), ("offer", "Offer sentence"), ("closing", "Closing"), ("emoji", "Emoji"))
    return [(label, book[key].replace("[OFFER]", "…")) for key, label in named if book.get(key)]


class StyleBook:
    """The messages your style is learned from, kept on this Mac (private/ is
    never uploaded): the ones you wrote or pasted in the app, the drafts you
    approved, and any learned from a CSV. The style card and the message
    search follow every change, so the next draft already writes like the
    message you just added. index is the MessageIndex to keep in step, or
    None for no search."""

    def __init__(self, path=STYLE_DB, index=None):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)  # the API answers from more than one thread
        self.lock = threading.RLock()
        self.db.executescript(TABLE)
        self.index, self._card = index, None
        if index is not None:
            self.sync()

    def messages(self, newest_first=True):
        with self.lock:
            rows = self.db.execute(f"select {', '.join(FIELDS)} from messages order by n "
                                   f"{'desc' if newest_first else 'asc'}").fetchall()
        return [dict(zip(FIELDS, row)) for row in rows]

    def add(self, messages, source):
        """Add messages, each a listing_title, asking_price, marketplace and
        my_message. One with an id that's here already takes its place, so
        learning the same CSV twice, or approving a draft twice, keeps one copy."""
        at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = [{"id": m.get("id") or f"msg-{uuid.uuid4().hex[:12]}", "listing_title": m.get("listing_title") or "",
                 "asking_price": m.get("asking_price") or "", "marketplace": m.get("marketplace") or "",
                 "my_message": m["my_message"].strip(), "source": source, "at": at} for m in messages]
        with self.lock:
            self.db.executemany(
                "insert into messages (id, listing_title, asking_price, marketplace, my_message, source, at) "
                "values (:id, :listing_title, :asking_price, :marketplace, :my_message, :source, :at) "
                "on conflict(id) do update set listing_title = excluded.listing_title, asking_price = "
                "excluded.asking_price, marketplace = excluded.marketplace, my_message = excluded.my_message, "
                "source = excluded.source, at = excluded.at", rows)
            self.db.commit()
            self._card = None
        if self.index is not None:
            self.index.add(rows)
        return rows

    def remove(self, message_id):
        """Forget one message. False if there's no such message."""
        with self.lock:
            gone = self.db.execute("delete from messages where id = ?", (message_id,)).rowcount
            self.db.commit()
            self._card = None
        if gone and self.index is not None:
            self.index.remove([message_id])
        return bool(gone)

    def card(self):
        """Your style card (style_card), from every message here, oldest first."""
        with self.lock:
            if self._card is None:
                self._card = style_card(self.messages(newest_first=False))
            return self._card

    def sync(self):
        """Make the message search hold exactly the messages here: after a
        crash between the two, or messages stored for search by an older version."""
        rows = self.messages()
        here, stored = {r["id"] for r in rows}, set(self.index.ids())
        self.index.remove(stored - here)
        self.index.add([r for r in rows if r["id"] not in stored])
