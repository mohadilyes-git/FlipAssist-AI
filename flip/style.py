"""Your writing style, from the messages you've sent to sellers. Plain code,
no AI:

1. A style card: what your messages have in common, such as the greeting you
   open with, how long they are, emojis, and what you usually mention.
2. Your old prices hidden as [OFFER], so an example shows how you word an
   offer without handing the AI a number to copy.
3. Your phrasebook: the opener, offer and closing sentences you use again and
   again, which flip.writer turns into a whole message with no AI.
"""

import csv
import re
import statistics
from collections import Counter

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
# title words that don't name the item
TITLE_FILLER = {"with", "and", "for", "the", "of", "in", "on", "to", "or", "plus", "new", "used"}
AMOUNT = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?"  # a comma only between thousands: "£185, cash" keeps its comma
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
        if len(OLD_PRICE.findall(m["my_message"])) != 1:
            continue
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
