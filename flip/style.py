"""Your writing style, from the messages you've sent to sellers. Plain code,
no AI:

1. A style card: what your messages have in common, such as the greeting you
   open with, how long they are, emojis, and what you usually mention.
2. Your old prices hidden as [OFFER], so an example shows how you word an
   offer without handing the AI a number to copy.
"""

import csv
import re
import statistics
from collections import Counter

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
GREETING_WORDS = {"hi", "hiya", "hello", "hey", "alright", "morning", "afternoon", "evening", "yo"}
MENTIONS = {"collecting": r"\bcollect(?:ion|ing)?\b", "cash": r"\bcash\b", "today": r"\b(?:today|tonight|asap)\b",
            "postage": r"\bpost(?:age|ed)?\b",
            "condition": r"\b(?:condition|scratch\w*|crack\w*|dent(?:s|ed)?|scuff\w*|chip(?:s|ped)?|marks?|broken|"
                         r"damage\w*|fault\w*|flaw\w*|wear|mint)\b"}
SHARE = 0.4  # a habit is something at least 40% of your messages do
OLD_PRICE = re.compile(r"£\s?\d[\d,]*(?:\.\d{2})?"
                       r"|\b\d[\d,]*(?:\.\d{2})?\s?(quid|pounds)\b"
                       r"|\b(take|do|accept|consider|offer|pay|stretch to|go to|let it go for)\s+\d[\d,]*(?:\.\d{2})?\b",
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
    return card


def describe(card):
    """The style card as short lines for the AI (and for you to check)."""
    if not card:
        return []
    lines = [f'Opens with "{card["greeting"]}"'] if card.get("greeting") else []
    lines += [f"About {card['words']} words",
              f"Usually asks {card['questions']} question{'' if card['questions'] == 1 else 's'}",
              "Uses emojis" if card["emoji"] else "No emojis"]
    if card["mentions"]:
        lines.append(f"Usually mentions: {', '.join(card['mentions'])}")
    return lines
