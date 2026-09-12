"""Your writing style, from the messages you've sent to sellers. Plain code,
no AI:

1. A style card: what your messages have in common, such as the greeting you
   open with, how long they are, emojis, and what you usually mention.
2. Your old prices hidden as [OFFER], so an example shows how you word an
   offer without handing the AI a number to copy.
3. Your phrasebook: the opener, offer and closing sentences you use again and
   again, which flip.writer turns into a whole message with no AI.
4. The list of what it learned (learned), one thing a row, each yours to
   remove: a removed one is off the card, the AI is told never to write it,
   and the checks hold every draft to that (check_not_removed).

StyleBook keeps the messages it all comes from, on this Mac.
"""

import copy
import csv
import re
import sqlite3
import statistics
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from flip.catalogue import contains, words
from flip.checks import EMOJI, GREETING_WORDS, ends_asking, promised_in

MENTIONS = {"collecting": r"\bcollect(?:ion|ing)?\b", "cash": r"\bcash\b", "today": r"\b(?:today|tonight|asap)\b",
            "postage": r"\bpost(?:age|ed|ing)\b|\bpost (?:it|them)\b",
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
create table if not exists removed (key text primary key, at text);
"""
# how the list of what it learned names your habits
HABIT_NAMES = {"collecting": "coming to collect", "cash": "paying cash", "postage": "postage", "today": "today or asap"}
SLOTS = (("opener", "Usual opener"), ("offer", "Offer sentence"), ("closing", "Closing"))
CALLED = {"mate", "there", "bro", "pal", "buddy", "m8", "hun", "all"}  # "Hi mate", "Hi there"
GREETING = "Hi"  # in place of a greeting you removed
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
    """What your messages have in common. Empty if there are none yet. What
    they mention is read in what they say, not ask: "what condition is it
    in?" mentions no condition, but the offer's own question counts ("would
    you take £185 cash?" mentions cash). The greeting is counted whatever its
    case ("Hi mate", "hi mate"), written the way you write it most."""
    texts = [m["my_message"] for m in messages if m.get("my_message")]
    if not texts:
        return {}
    share = lambda found: sum(found) / len(texts) >= SHARE
    said = [statements(t) for t in texts]
    card = {"messages": len(texts), "words": int(statistics.median(len(t.split()) for t in texts)),
            "questions": int(statistics.median(t.count("?") for t in texts)),
            "emoji": share(bool(EMOJI.search(t)) for t in texts),
            "mentions": [name for name, pattern in MENTIONS.items()
                         if share(bool(re.search(pattern, t, re.IGNORECASE)) for t in said)]}
    greeting, times = Counter(opening(t).lower() for t in texts).most_common(1)[0]
    if greeting and times / len(texts) >= SHARE:
        card["greeting"] = Counter(opening(t) for t in texts if opening(t).lower() == greeting).most_common(1)[0][0]
    card["phrases"] = phrasebook([m for m in messages if m.get("my_message")])
    asked = Counter(q for t in texts for q in set(questions_in(t)))
    card["asks"] = sorted(q for q, n in asked.items() if n >= HABIT)  # questions you ask every time
    card["promises"] = sorted(set().union(*(promised_in(t) for t in texts)))
    return card


def statements(text):
    """What a message says, not asks: its sentences that don't ask, and the one that makes the offer."""
    return " ".join(s for s in SENTENCES.split(text.strip()) if s.strip() and (not ends_asking(s) or OLD_PRICE.search(s)))


def questions_in(text):
    """A message's questions in their plain words, prices left out:
    "Would you take £185? Still available?" -> ["would you take offer", "still available"]."""
    return [" ".join(words(without_prices(s))) for s in SENTENCES.split(text.strip()) if s.strip() and ends_asking(s)]


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
    takes the place of your usual length, for a longer message. What you
    removed from your style (without) comes last, as what it never writes."""
    if not card:
        return []
    lines = [f'Opens with "{card["greeting"]}"'] if card.get("greeting") else []
    lines += [f"About {words or card['words']} words",
              f"Usually asks {card['questions']} question{'' if card['questions'] == 1 else 's'}",
              "Uses emojis" if card["emoji"] else "No emojis"]
    if card["mentions"]:
        lines.append(f"Usually mentions: {', '.join(card['mentions'])}")
    removed = card.get("removed") or {}
    lines += [f'Never opens with "{greeting}"' for greeting in removed.get("greetings", [])]
    if removed.get("habits"):
        lines.append(f"Never mentions {and_list([HABIT_NAMES[h] for h in removed['habits']])}")
    lines += [f'Never writes "{phrase}"' for phrase in removed.get("phrases", [])]
    lines += [f'Never asks "{question_words(ask)}?"' for ask in removed.get("asks", [])]
    return lines


def learned(card, removed=()):
    """Everything your style puts in a message, one row each, for you to keep
    or remove: [{"key": "greeting:hi mate", "what": "Opens with", "value":
    "Hi mate", "used": True}, ...]. removed: the keys you removed (used is
    False for those); one your messages no longer give is still listed, to
    put back. How long your messages are isn't on it: that's not a thing it
    puts in. Neither is the offer question you ask every time, a question or
    an emoji already in one of your sentences, or an opener that's only your
    greeting."""
    card = card or {}
    rows, keys = [], set()

    def add(key, what, value):
        if key not in keys:
            keys.add(key)
            rows.append({"key": key, "what": what, "value": value, "used": key not in removed})

    phrases = card.get("phrases") or {}
    if card.get("greeting"):
        add(f"greeting:{card['greeting'].lower()}", "Opens with", card["greeting"])
    for habit, name in HABIT_NAMES.items():
        if habit in card.get("mentions", []) or habit in card.get("promises", []):
            add(f"mention:{habit}", "Mentions", name)
    if "condition" in card.get("mentions", []):
        add("says-flaw", "Says the flaw", "as the reason for a lower offer")
    if card.get("emoji"):
        add("emoji", "Emojis", phrases.get("emoji") or "yes")
    for slot, what in SLOTS:
        text = phrases.get(slot)
        if text and words(text) and not (slot == "opener" and greeting_only(text)):
            add(f"phrase:{slot}:{text.lower()}", what, text.replace("[OFFER]", "…"))
    listed = [words(phrases[slot]) for slot, _ in SLOTS if phrases.get(slot)]
    for ask in card.get("asks", []):
        asked = question_words(ask)
        if "offer" in ask.split() or not set(asked.split()) - GREETING_WORDS - CALLED \
                or any(contains(sentence, ask.split()) for sentence in listed):
            continue
        add(f"ask:{asked}", "Asks every time", f"{asked}?")
    for key in sorted(set(removed) - keys):  # removed, and no longer in your messages: still yours to put back
        row = removed_row(key)
        if row:
            add(key, *row)
    return rows


def removed_row(key):
    """What a removed key is called in the list, from the key alone: ("Opens with", "Hi mate")."""
    kind, _, rest = key.partition(":")
    if kind == "phrase":
        slot, _, text = rest.partition(":")
        return (dict(SLOTS)[slot], text.replace("[offer]", "…")) if slot in dict(SLOTS) else None
    return {"greeting": ("Opens with", rest[:1].upper() + rest[1:]), "mention": ("Mentions", HABIT_NAMES.get(rest, rest)),
            "says-flaw": ("Says the flaw", "as the reason for a lower offer"), "emoji": ("Emojis", "yes"),
            "ask": ("Asks every time", f"{rest}?")}.get(kind)


def greeting_only(text):
    """Whether a sentence is nothing but a greeting: "Hi mate!"."""
    return bool(opening(text)) and words(opening(text)) == words(text)


def question_words(ask):
    """A question you ask every time without the greeting it opens with: "hi mate still available" -> "still available"."""
    parts = ask.split()
    while parts[1:] and parts[0] in GREETING_WORDS | CALLED:
        parts = parts[1:]
    return " ".join(parts)


def ungreeted(text, greeting):
    """A message or sentence without a greeting at its start, whatever follows
    it: "Alright mate? Would you take..." -> "Would you take...", "Hi mate 👋,
    would you..." -> "Would you..."."""
    found = re.match(rf"\s*{re.escape(greeting)}(?=\W|$)[\s,.!?:;\-–—]*(?:{EMOJI.pattern}[\s,.!?]*)*", text, re.IGNORECASE)
    if not found:
        return text
    rest = text[found.end():]
    return rest[:1].upper() + rest[1:]


def without(card, removed):
    """Your style card without what you removed from it (learned's keys),
    which is kept in card["removed"]: the AI is told never to write it
    (describe), it's taken out of the examples the AI is shown (scrubbed),
    and the checks refuse a draft that writes it (check_not_removed). A
    removed habit (cash, collecting...) is one your messages no longer
    promise, so the promise check refuses it too. A removal stands whatever
    messages you add later: "Hi mate" stays removed once your greeting is
    "Hi". A removed greeting comes out of your sentences too ("Hi mate,
    would you take..." -> "Hi, would you take...")."""
    removed = set(removed)
    if not card or not removed:
        return card
    card = copy.deepcopy(card)
    phrases = card.setdefault("phrases", {})
    gone = {"greetings": [], "habits": [], "phrases": [], "asks": [], "emoji": False, "flaw": False}
    for key in sorted(removed):
        kind, _, rest = key.partition(":")
        if kind == "greeting":
            mine = (card.get("greeting") or "").lower() == rest
            gone["greetings"].append(card.pop("greeting") if mine else rest)
            for slot, _ in SLOTS:  # your sentences keep their words, with "Hi" for the greeting, or none for "Hi"
                text = phrases.get(slot)
                if text and opening(text).lower() == rest:
                    bare = ungreeted(text, opening(text))
                    phrases[slot] = (bare if rest == GREETING.lower() or not bare else
                                     f"{GREETING}, {bare[:1].lower()}{bare[1:]}") or None
        elif kind == "mention":
            card["mentions"] = [m for m in card.get("mentions", []) if m != rest]
            card["promises"] = [p for p in card.get("promises", []) if p != rest]
            gone["habits"].append(rest)
        elif kind == "says-flaw":
            card["mentions"] = [m for m in card.get("mentions", []) if m != "condition"]
            gone["flaw"] = True
        elif kind == "emoji":
            card["emoji"] = False
            phrases["emoji"] = ""
            for slot, _ in SLOTS:
                if phrases.get(slot) and not words(phrases[slot]):  # a closing that's only "👍"
                    phrases[slot] = None
            gone["emoji"] = True
        elif kind == "phrase":
            slot, _, text = rest.partition(":")
            mine = (phrases.get(slot) or "").lower() == text
            gone["phrases"].append(phrases[slot] if mine else text)
            if mine:
                phrases[slot] = None  # no habit there: the writer words that part, or the AI writes
            gone["asks"] += [question_words(q) for q in questions_in(text)]  # "...is this still available?" goes with it
        elif kind == "ask":
            card["asks"] = [a for a in card.get("asks", []) if question_words(a) != rest]
            gone["asks"].append(rest)
    card["removed"] = gone
    return card


# a habit in any words (check_not_removed, scrubbed): wider than how the card counts it, so a removed habit
# can't come back as "can pop round" or "happy to cover delivery"
HABIT_WORDS = {
    "collecting": re.compile(r"\b(?:collect\w*|pick(?:ing)? (?:it |them )?up|pick ?up|grab (?:it|them)|"
                             r"come (?:and |& )?get|pop (?:round|over|by)|swing by|drop by|nip (?:round|over))\b",
                             re.IGNORECASE),
    "cash": re.compile(r"\bcash\b", re.IGNORECASE),
    "postage": re.compile(r"\b(?:post(?:age|ed|ing)|post (?:it|them)|ship\w*|deliver\w*|courier|tracked|royal mail|"
                          r"evri|hermes|dpd|send (?:it|them))\b", re.IGNORECASE),
    "today": re.compile(r"\b(?:today|tonight|asap)\b", re.IGNORECASE)}
# ...as it's taken out of the offer's own sentence in an example: "Would you take £[OFFER] cash?" -> "...£[OFFER]?"
IN_THE_OFFER = {"cash": re.compile(r"\s*\b(?:(?:in|with|for)\s+)?cash(?:\s+(?:in hand|on collection))?\b", re.IGNORECASE),
                "today": re.compile(r"\s*\b(?:today|tonight|asap)\b", re.IGNORECASE)}
# a reason given about the condition, as it's taken out of an example when you removed "Says the flaw"
CONDITION_REASON = re.compile(rf",?\s+(?:as|because|given|since|due to|seeing as)\s+[^.?!]*?{MENTIONS['condition']}[^.?!]*",
                              re.IGNORECASE)
NEUTRAL_OFFER = "Would you take £[OFFER]?"


def scrubbed(message, card):
    """One of your past messages as the AI is shown it, without what you
    removed from your style, so there's nothing there to copy. Whole
    sentences go: one you removed (whatever its case or full stop), a
    question you removed, one about a habit you removed. The offer's own
    sentence stays, without the habit's word ("...£[OFFER] cash?" ->
    "...£[OFFER]?") or, if that can't be said, as a plain offer. A removed
    greeting, emojis or a reason about the condition go from what's left.
    The price is hidden as in every example (without_prices)."""
    gone = (card or {}).get("removed")
    text = without_prices(message.strip())
    if not gone:
        return text
    removed_sentences = [words(part) for phrase in gone["phrases"] for part in SENTENCES.split(phrase) if words(part)]
    kept = []
    for sentence in (s.strip() for s in SENTENCES.split(text) if s.strip()):
        plain = words(sentence)
        offer = "[OFFER]" in sentence
        if not offer and any(plain == part or len(part) > 2 and contains(plain, part) for part in removed_sentences):
            continue
        asks_removed = any(contains(q.split(), a.split()) for q in questions_in(sentence) for a in gone["asks"])
        if asks_removed and not offer:
            continue
        if asks_removed:  # the offer's sentence asks it too: "would you take £[OFFER], does it come with a charger?"
            sentence = NEUTRAL_OFFER
        habits = [h for h in gone["habits"] if h in HABIT_WORDS and HABIT_WORDS[h].search(sentence)]
        if habits and not offer:
            continue
        for habit in habits:
            sentence = IN_THE_OFFER[habit].sub("", sentence) if habit in IN_THE_OFFER else NEUTRAL_OFFER
        if gone.get("emoji"):
            sentence = re.sub(r"\s{2,}", " ", EMOJI.sub("", sentence)).strip()
        if gone.get("flaw"):
            sentence = CONDITION_REASON.sub("", sentence)
        if words(sentence) or "[OFFER]" in sentence:
            kept.append(sentence)
    text = " ".join(kept)
    for greeting in gone["greetings"]:
        text = ungreeted(text, greeting)
    return text


def check_not_removed(message, card):
    """A draft never writes what you removed from your style (without): the
    greeting, whatever follows it ("Hi mate -", "Hello there"), a habit in
    any words ("can pop round" for collecting), a sentence of your
    phrasebook or a question you ask every time. (No emojis is
    check_message_manner's.)"""
    gone = (card or {}).get("removed")
    if not gone or not isinstance(message, str):
        return []
    problems = []
    said = words(message)
    problems += [f"the message opens with \"{g}\", which you removed from your style"
                 for g in gone["greetings"] if words(g) and said[:len(words(g))] == words(g)]
    problems += [f"the message mentions {HABIT_NAMES[h]}, which you removed from your style"
                 for h in gone["habits"] if h in HABIT_WORDS and (HABIT_WORDS[h].search(message) or h in promised_in(message))]
    plain = words(without_prices(message))
    problems += [f"the message writes \"{p}\", which you removed from your style"
                 for p in gone["phrases"] if words(p) and contains(plain, words(p))]
    asked = [q.split() for q in questions_in(message)]  # "Hi, would you take £90, does it come with a charger?"
    problems += [f"the message asks \"{question_words(a)}?\", which you removed from your style"
                 for a in gone["asks"] if any(contains(q, question_words(a).split()) for q in asked)]
    return problems


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
        self.index, self._card, self._learned_card = index, None, None
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
            self._card = self._learned_card = None
        if self.index is not None:
            self.index.add(rows)
        return rows

    def remove(self, message_id):
        """Forget one message. False if there's no such message."""
        with self.lock:
            gone = self.db.execute("delete from messages where id = ?", (message_id,)).rowcount
            self.db.commit()
            self._card = self._learned_card = None
        if gone and self.index is not None:
            self.index.remove([message_id])
        return bool(gone)

    def card(self):
        """Your style card (style_card), from every message here, oldest
        first, without what you removed from it (without)."""
        with self.lock:
            if self._card is None:
                self._card = without(self.learned_card(), self.removed())
            return self._card

    def learned_card(self):
        """The style card as learned, before anything you removed comes off."""
        with self.lock:
            if self._learned_card is None:
                self._learned_card = style_card(self.messages(newest_first=False))
            return self._learned_card

    def removed(self):
        """The keys of what you removed from your style (learned)."""
        with self.lock:
            return {key for (key,) in self.db.execute("select key from removed")}

    def learned(self):
        """What your style puts in a message, each with whether you still use it (learned)."""
        with self.lock:
            return learned(self.learned_card(), self.removed())

    def use(self, key, used):
        """Keep (used) or remove one thing your style learned, by its key in
        learned. False if your style hasn't learned it: removing it, or
        putting back what isn't removed."""
        with self.lock:
            if used:
                gone = self.db.execute("delete from removed where key = ?", (key,)).rowcount
            elif key in {row["key"] for row in self.learned()}:
                at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                gone = self.db.execute("insert or replace into removed (key, at) values (?, ?)", (key, at)).rowcount
            else:
                gone = 0
            self.db.commit()
            self._card = None
        return bool(gone)

    def sync(self):
        """Make the message search hold exactly the messages here: after a
        crash between the two, or messages stored for search by an older version."""
        rows = self.messages()
        here, stored = {r["id"] for r in rows}, set(self.index.ids())
        self.index.remove(stored - here)
        self.index.add([r for r in rows if r["id"] not in stored])
