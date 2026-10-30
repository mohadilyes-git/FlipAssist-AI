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
import json
import re
import sqlite3
import statistics
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from flip.catalogue import contains, words
from flip.checks import (COLLECT_TALK, EMOJI, GREETING_WORDS, HOLD, LOWBALL, PAY_FIRST, SIGN_OFF, ends_asking,
                         promised_in)
from flip.checks import PRIOR_TALK, UNDER_ASKING_TALK, check_no_contact_details, check_no_story, prices_in
from flip.money import to_pence

MENTIONS = {"collecting": r"\bcollect(?:ion|ing)?\b", "cash": r"\bcash\b", "today": r"\b(?:today|tonight|asap)\b",
            "postage": r"\bpost(?:age|ed|ing)\b|\bpost (?:it|them)\b",
            "condition": r"\b(?:condition|scratch\w*|crack\w*|dent(?:s|ed)?|scuff\w*|chip(?:s|ped)?|marks?|broken|"
                         r"damage\w*|fault\w*|flaw\w*|wear|mint)\b"}
# the flaw given as a reason in words that are a flaw only there: "As the battery is at 84% I'd need to replace it",
# "as there's some screen burn" (26 Sep: missed, so a buyer who gives the flaw was learned as one who doesn't).
# Alone they're often something else: "if that doesn't work for you", "battery health doesn't bother me"
REASON_FLAW = re.compile(r"(?<!as long )(?<!so long )\b(?:as|because|given|since|due to|with|seeing as|considering|"
                         r"what with)\b"  # not your own reason or wish: "as mine's smashed", "for my son as his is
                         # smashed", "as I'm not working tomorrow", "as long as the battery is over 85%", "with good battery"
                         r"(?![^.?!]{0,20}?\b(?:mine|my|long as|his|hers|her|theirs|their)\b)"
                         r"(?!\s+(?:i'?m|i am|i'?ll|i will|i'?ve|i have|i need|i want)\b)"
                         r"(?!\s+(?:good|great|decent|healthy|strong|high|a good|a decent|a healthy)\b)[^.?!]{0,60}?"
                         r"\b(?:batter(?:y|ies)|bh|burn(?:-?in|t|s)?|repair\w*|replac\w*|smash\w*|shatter\w*|bent|"
                         r"not working|(?:doesn'?t|does not|isn'?t|won'?t) work\w*|glitch\w*|ghosting|dead pixels?|"
                         r"loose|stiff|drift\w*|worn)\b", re.IGNORECASE)
DONT_MIND = re.compile(r"\b(?:doesn'?t|don'?t|won'?t) (?:bother|matter|mind)\b|\bnot (?:fussed|bothered)\b|"
                       r"\b(?:sort|fix) it myself\b|\bno (?:problem|worries)\b", re.IGNORECASE)
# good condition said when paying over asking ("as it's mint"), learned apart from giving a flaw (26 Sep)
PRAISE = re.compile(r"\b(?:condition|mint|immaculate|pristine|perfect|flawless|excellent|like new|as new)\b", re.IGNORECASE)
SHARE = 0.4  # a habit is something at least 40% of your messages do
HABIT = 2  # a sentence in at least 2 of your messages is one you'd write again
SENTENCES = re.compile(r"(?<=[.!?…])\s+|(?<=[.!?…][\U0001F300-\U0001FAFF☀-➿])\s+")  # "£170?😊 Can collect" is two
# one whole emoji, its skin tone and joins included: "👍🏽" is one, and a lone "🏽" is none
WHOLE_EMOJI = re.compile("[\U0001F300-\U0001F3FA\U0001F400-\U0001FAFF☀-➿]"
                         "(?:[\U0001F3FB-\U0001F3FF]|\ufe0f|\u200d[\U0001F300-\U0001FAFF☀-➿])*")
# the asking price said back, which isn't an offer: "still available at £220?", "you're asking £220"
ASKING_SAID = re.compile(r"\b(?:available (?:at|for)|asking|listed (?:at|for)|price (?:is|of)|priced at|still)\s+£",
                         re.IGNORECASE)  # "is it still £220?" checks the price, it doesn't offer
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
create table if not exists ai_style (key text primary key, proposals text, model text, at text);
"""
# how the list of what it learned names your habits
HABIT_NAMES = {"collecting": "coming to collect", "cash": "paying cash", "postage": "postage", "today": "today or asap"}
SLOTS = (("opener", "Usual opener"), ("offer", "Offer sentence"), ("closing", "Closing"))
# how you word the offer for each kind, when it's your habit there: under asking you may ask ("Would you do
# £[OFFER]?") and at asking say it ("I'll pay the full £[OFFER]"). Listed only where it isn't your usual one
KIND_SLOTS = (("offer_lower", "Offer under asking"), ("offer_asking", "Offer at asking"),
              ("offer_more", "Offer over asking"))
OFFER_SLOTS = ("offer", *(slot for slot, _ in KIND_SLOTS))
# ...and how you end each kind (26 Sep red team: "Could you hold it for me?", written only when paying asking, ended a
# lower offer). Your closing ("closing") is then one you write with every kind of offer you make
KINDS = ("lower", "asking", "more")
CLOSING_KIND_SLOTS = (("closing_lower", "Closing under asking"), ("closing_asking", "Closing at asking"),
                      ("closing_more", "Closing over asking"))
KIND_CLOSINGS = tuple(slot for slot, _ in CLOSING_KIND_SLOTS)
# ...and the sign-off you end every kind of message with ("Kind regards, Sam"), the last one to fall back on (not
# listed: it's the end of your closings)
CLOSING_SLOTS = ("closing", *KIND_CLOSINGS, "sign_off")
# a closing's last sentence that only signs off: "Kind regards, Sam", "Many thanks", "Cheers then", "Ta x"
SIGNED = re.compile(r"^(?:(?:many|much|big|massive|huge)\s+)?(?:thanks?|thank\s+you|thx|ta|cheers|regards|kind\s+regards|"
                    r"best(?:\s+(?:wishes|regards))?|warm\s+regards|appreciated|speak\s+soon)"
                    r"(?:\s+(?:a\s+lot|so\s+much|very\s+much|kindly|again|then|in\s+advance|mate|pal|bud|love|hun))*"
                    r"[\s,!.]*(?:[A-Z][a-z]+)?[\s!.]*(?:x{1,3}|[\U0001F300-\U0001FAFF\u2600-\u27BF])*\s*$", re.IGNORECASE)
CALLED = {"mate", "there", "bro", "pal", "buddy", "m8", "hun", "all", "bud", "fella", "boss", "love", "chief", "lad",
          "lads", "guys", "folks", "babe", "pet", "duck", "mucker"}  # "Hi mate", "Hi there", "Alright bud", "Morning fella"
GREETING = "Hi"  # in place of a greeting you removed
OLD_PRICE = re.compile(rf"£\s?{AMOUNT}"
                       rf"|\b{AMOUNT}\s?(quid|pounds)\b"
                       rf"|\b(take|do|accept|consider|offer|pay|stretch to|go to|let it go for|"
                       # "ill give u 280 if u hold it", not "Will give 5 star feedback" (26 Sep)
                       rf"give(?: (?:u|you|ya))?(?=\s+{AMOUNT}\s*(?:cash|quid|pounds|for|if|and|ono|[?.!,]|$)))"
                       rf"\s+{AMOUNT}\b", re.IGNORECASE)
# a price said back before the offer: "I know you're asking £220 but would you take £180?" (kind_of)
SAID_BACK = re.compile(r"\b(?:asking|listed (?:at|for)|priced at|price (?:is|of)|still|you(?:'re| are)? (?:after|wanting)|"
                       r"you want|on for|up for)\s*(?:it\s+)?(?:for\s+|at\s+)?$", re.IGNORECASE)
# where you meet the seller (Facebook, Gumtree) and where it's posted (eBay, Vinted): your sentences are learned
# for each as well as for all your messages, so "Can collect today." stays on Facebook and "Can pay straight away."
# on Vinted (26 Sep)
LOCAL_MARKETS = re.compile(r"\b(?:facebook|fb|gumtree)\b", re.IGNORECASE)
POSTED_MARKETS = re.compile(r"\b(?:ebay|vinted)\b", re.IGNORECASE)
MARKET_GROUPS = (("in_person", LOCAL_MARKETS, "on Facebook and Gumtree"), ("posted", POSTED_MARKETS, "on eBay and Vinted"))
# what doesn't make a sentence another one (habit_key): an emoji, when you'd come ("...hold it for me until this
# evening" and "...until tomorrow" are one habit), and the item named after the offer ("Would you consider £[OFFER]
# for the AirPods?" is "Would you consider £[OFFER]?")
TIMES = r"(?:today|tonight|tomorrow|tmrw|tmr|tomoz|2day|2nite|2moro|this (?:evening|afternoon|morning))"
WHEN = re.compile(rf"\s*\b(?:(?:until|till|til|by)\s+)?{TIMES}\b", re.IGNORECASE)
# a sentence where when is the point: "Can collect today, not tomorrow" is no habit of "Can collect tomorrow, not today"
CONTRAST = re.compile(r"\b(?:not|but|unless|except|instead|rather)\b|n'?t\b", re.IGNORECASE)
ITEM_AFTER = re.compile(r"\s+(?:for|on) (?:the|your|this|that) (?P<item>[\w'’ -]+?)(?=\s*(?:[?.!]|$))", re.IGNORECASE)
LOWERCASE = 2 / 3  # of your messages in lower case: then your drafts are too
LOWER_THAN = re.compile(r"\b(?:less|lower) than £?\[OFFER\]|\bbelow £?\[OFFER\]|\bunder £?\[OFFER\]", re.IGNORECASE)
# what after "for the" isn't the item ("Can collect on the day.") and what's an item whatever the title says ("for the phone")
FLAW_IN_TITLE = re.compile(r"\b(?:scratch\w*|crack\w*|dent(?:s|ed)?|scuff\w*|chip(?:s|ped)?|marks?|marked|broken|damage\w*|"
                           r"fault\w*|faulty|smash\w*|spares|repairs?|for parts)\b", re.IGNORECASE)
NOT_THE_ITEM = {"day", "price", "time", "weekend", "evening", "morning", "night", "today", "tomorrow", "week", "month",
                "year", "it", "lot", "deal", "offer", "money", "cash", "collection", "post", "postage", "asking"}
GENERIC_ITEMS = {"phone", "phones", "console", "laptop", "tablet", "headphones", "earbuds", "watch", "item", "set",
                 "bundle", "bike", "tv", "camera", "speaker", "one", "handset", "pair", "trainers", "controller", "unit",
                 "device", "machine", "kit"}  # "for this one", "for the handset"
# a greeting that's often a word of something else: "Morning pick up?", "Evening collection ok?", "Alright if I..."
WEAK_GREETINGS = {"alright", "morning", "afternoon", "evening"}
STARTS = {"is", "are", "would", "wud", "do", "does", "can", "could", "u", "you", "i", "im", "i'm", "just", "hope",
          "any", "how", "what", "still"}

# your sign-off as you write it at the very end of a message: your name, a smiley and your thanks, in any order
# ("remi :), cheers", "Cheers, Sam :)", "- Dan"). Seen in a real setup on 3 Oct: a sign-off like "remi :), cheers" was
# learned as "cheers" (SIGNED knows thanks with a name after them, not before, and no smileys), and drafts ended "Cheers"
SMILEY = r"[:;=]-?[)(DPp3\]\[]|<3|\(:"
TAIL_TOKEN = re.compile(rf"(?P<smiley>{SMILEY})|(?P<emoji>{WHOLE_EMOJI.pattern})|(?P<word>[^\W\d_][\w'’]*)"
                        r"|(?P<number>\d[\w.,]*)|(?P<mark>[^\s\w])")  # a number ends a sign-off: "...take £150? 👍"
CORE_THANKS = {"thanks", "thank", "thankyou", "thx", "ty", "ta", "cheers", "regards", "appreciated"}
# ...and words only of a sign-off when they come with those ("Kind regards", "Many thanks", "Speak soon"): never taken off
# a draft's end on their own (3 Oct review: "Thank you so much" lost its "much")
THANKS = CORE_THANKS | {"kind", "best", "wishes", "many", "much", "again", "speak", "soon"}
# the last words of a message that are no name: "...can collect today", "...let me know", "...if that's ok"
NOT_A_NAME = {"it", "me", "now", "today", "tomorrow", "tonight", "please", "pls", "plz", "you", "u", "asap", "offer",
              "cash", "collect", "collection", "know", "later", "the", "a", "an", "i", "for", "on", "in", "and", "to",
              "of", "my", "your", "is", "ok", "okay", "yes", "no", "there", "here", "that", "this", "them", "then", "too",
              "price", "deal", "pickup", "post", "postage", "posted", "morning", "evening", "afternoon", "night", "week",
              "weekend", "up", "out", "back", "soon", "time", "if", "so", "be", "do", "go", "get", "can", "will", "would",
              "could", "fine", "great", "good", "thing", "things", "one", "all", "x", "xx", "xxx"} | CALLED


def sign_off_names(messages):
    """The names you sign with: a word among the last three of at least HABIT messages, and SHARE of them, that's
    none of thanks, a call ("mate"), a common last word ("today") or the item's, and is signed there: after your
    thanks ("Cheers, Sam"), or starting a part of its own (after a full stop, a comma or a spaced dash) with only
    thanks or smileys after it ("...collect. remi :), cheers", "- Dan"). Not "condition" in "...given the
    condition? Thanks", nor "ish" in "tonight-ish", nor "tmr" in "Can collect tmr."."""
    seen = Counter()
    for m in messages:
        text = m["my_message"]
        said = [t.group("word").lower() for t in TAIL_TOKEN.finditer(text) if t.group("word")]
        item = set(words(m.get("listing_title") or ""))
        for w in {w for w in said[-3:] if w.isalpha() and 2 <= len(w) <= 15 and w not in THANKS | NOT_A_NAME | WHEN_WORDS
                  and w not in item and w not in GREETING_WORDS}:
            at = tail_start(text, THANKS | {w})
            if at is None:
                continue
            tail = list(TAIL_TOKEN.finditer(text, at))
            for i, t in enumerate(tail):
                if (t.group("word") or "").lower() != w or text[t.end():].lstrip().startswith("?"):
                    continue  # "Unlocked?" asks, it doesn't sign
                after_thanks = any((u.group("word") or "").lower() in THANKS for u in tail[:i])
                before = text[:t.start()].rstrip()
                starts_part = not before or before[-1] in ".!?,;:)\n" or re.search(r"\s[-–—~]$", before) is not None
                if after_thanks or starts_part:
                    seen[w] += 1
                    break
    return {w for w, n in seen.items() if n >= HABIT and n / max(1, len(messages)) >= SHARE}


def tail_start(text, allowed):
    """Where a message's sign-off starts: the first of its last words that are all smileys, emojis, marks or allowed
    words ("you" after "thank"), from a word or smiley, not a mark; None when it ends with none."""
    tokens = list(TAIL_TOKEN.finditer(text or ""))
    start = None
    for i in range(len(tokens) - 1, -1, -1):
        token = tokens[i]
        word = (token.group("word") or "").lower()
        if token.group("mark"):
            continue
        thanked = word == "you" and i and (tokens[i - 1].group("word") or "").lower() == "thank"
        if token.group("smiley") or token.group("emoji") or word in allowed or thanked:
            start = token.start()
            continue
        break
    return start


def said_tail(tail):
    """A sign-off as it's counted: its words and smileys in lower case, marks left out ("remi:). cheers" ->
    "remi :) cheers")."""
    return " ".join(t.group().lower() for t in TAIL_TOKEN.finditer(tail) if not t.group("mark"))


def signature(messages):
    """The sign-off you end your messages with, as you write it most ("remi :), cheers"), when it has your name or a
    smiley (a plain "Cheers" is the phrasebook's sign_off) and it ends at least HABIT and SHARE of your messages; else
    None. drafts end with it (signed_with), whoever wrote the rest."""
    mine = [m for m in messages if m.get("my_message")]
    if len(mine) < HABIT:
        return None
    names = sign_off_names(mine)
    allowed = THANKS | names
    tails = []
    for m in mine:
        at = tail_start(m["my_message"], allowed)
        tails.append(m["my_message"][at:].strip().rstrip(" .") if at is not None else "")
    keys = [said_tail(tail) for tail in tails]
    counted = Counter(key for key in keys if key)
    if not counted:
        return None
    key, n = counted.most_common(1)[0]
    if n < HABIT or n / len(mine) < SHARE:
        return None
    # your name with your thanks or a smiley ("remi :), cheers", "Thanks, Dan"), or thanks with a smiley ("thanks :)"):
    # not "lol", "Leeds" or a bare word that ends your messages (3 Oct review), nor a lone emoji (the phrasebook's)
    said = set(key.split())
    smiled = bool(re.search(SMILEY, key) or WHOLE_EMOJI.search(key))
    if not (said & names and (said & CORE_THANKS or smiled) or said & CORE_THANKS and smiled):
        return None
    return Counter(tail for tail, k in zip(tails, keys) if k == key).most_common(1)[0][0]


def tail_words(tail):
    """A sign-off's words alone, in lower case, its emojis, smileys and marks left out: "😊 Many thanks! 🙏" -> "many
    thanks". "Many thanks! 🙏" is "Many thanks! 😊" with another emoji, not another sign-off (14 Oct hunt: drafts ended
    "Many thanks! 🙏 Many thanks! 😊" and "😊 Cheers, Sam. Cheers, Sam")."""
    return " ".join(t.group().lower() for t in TAIL_TOKEN.finditer(tail or "") if t.group("word"))


# the words of a sign-off that are no name ("Thanks a lot", "Thank you so much", "Ta x"), and what's never a name in
# one: "Best offer." and "Thanks for it" don't sign off
SIGN_WORDS = THANKS | {"thank", "you", "a", "lot", "so", "very", "kindly", "then", "in", "advance", "mate", "pal", "bud",
                       "love", "hun", "warm", "big", "massive", "huge", "x", "xx", "xxx"}


def signed_part(text):
    """Where a text's last part starts when it only signs off, whoever's sign-off it is (SIGNED: "Many thanks",
    "Kind regards", "Thanks a lot", "Cheers mate, Sam"): its last sentence, else what's after its last comma
    ("...can collect today, thanks a lot"); None when it ends with no such part. A word in it that's no name ("Best
    offer.", "Cheers for that") makes it none."""
    text = text or ""
    breaks = [m.end() for m in re.finditer(r"[.!?…]+\s+|(?<=[\U0001F300-\U0001FAFF☀-➿])\s+", text.rstrip())]
    sentence = breaks[-1] if breaks else 0
    commas = [m.end() for m in re.finditer(r",\s*", text[sentence:])]
    for at in (sentence, *([sentence + commas[-1]] if commas else [])):
        part = text[at:]
        if not part.strip() or not SIGNED.match(part.strip()):
            continue
        said = [w for w in tail_words(part).split() if w not in SIGN_WORDS]
        if len(said) <= 1 and not set(said) & NOT_A_NAME:
            return at + len(part) - len(part.lstrip())
    return None


def own_tail(text, sign_off):
    """Where the sign-off a text ends with starts, when that's yours (the same words, whatever emoji or smiley it comes
    with), plain thanks the writer put there ("Cheers", "Thank you") or another sign-off of yours (signed_part: "Many
    thanks", "Thanks a lot"); else None: "...so much", "...soon" or the "Max" of "iPhone 14 Pro Max" stay (3 Oct
    review). An emoji or smiley before its first word stays the message's, unless your sign-off starts with one
    ("...£340? 😊 Cheers, Sam" is signed already)."""
    allowed = CORE_THANKS | {t.group().lower() for t in TAIL_TOKEN.finditer(sign_off) if t.group("word")}
    found = []
    at = tail_start(text, allowed)
    if at is not None:
        said = tail_words(text[at:])
        plain = all(w in CORE_THANKS or w == "you" for w in said.split())
        if said and (said == tail_words(sign_off) or plain):
            found.append(at)
    # ...or the whole last sentence when it only signs off: "Many thanks" or "Kind regards" left "Many." and "Kind."
    # before yours (14 Oct hunt: "...Can collect today. Many. Thanks, Dan")
    if (part := signed_part(text)) is not None:
        found.append(part)
    if not found:
        return None
    at = min(found)
    first = next((t for t in TAIL_TOKEN.finditer(sign_off) if not t.group("mark")), None)
    if first is not None and first.group("word"):
        word = next((t for t in TAIL_TOKEN.finditer(text, at) if t.group("word")), None)
        at = word.start() if word is not None else at
    return at


def unsigned(text, sign_off):
    """A message without your sign-off at its end, for comparing or adding to it (Rewrite, Make it longer)."""
    if not sign_off or not isinstance(text, str):
        return text
    at = own_tail(text, sign_off)
    return text[:at].rstrip(" ,-–—") if at is not None and tail_words(text[at:]) == tail_words(sign_off) else text


def signed_with(text, sign_off):
    """A draft that ends with your sign-off ("...I can come and collect. remi :), cheers"): the one it ends with
    (a "Cheers" the writer put there, or yours) swapped for yours, as you write it. A question before it keeps its
    "?" ("Hi, would you take £295? cheers Dan", not "...£295. cheers Dan": 14 Oct hunt), and "…" is an end."""
    if not sign_off or not isinstance(text, str) or not text.strip():
        return text
    at = own_tail(text, sign_off)
    body = (text[:at] if at is not None else text).rstrip(" ,-–—")
    # an emoji the body ends with that your sign-off has too goes: the sign-off brings it ("...on the spot. Many thanks!
    # 😊", never "...on the spot. 😊 Many thanks! 😊": 14 Oct, the owner's style test)
    while body and (last := [m for m in WHOLE_EMOJI.finditer(body)][-1:]) and last[0].end() == len(body) and \
            last[0].group() in sign_off:
        body = body[:last[0].start()].rstrip(" ,-–—")
    if not body:
        return sign_off
    if body[-1] in ".?!)…" or WHOLE_EMOJI.search(body[-2:]) or re.search(rf"(?:{SMILEY})$", body):
        return f"{body} {sign_off}"
    last = [s for s in SENTENCES.split(body) if s.strip()][-1:]
    return f"{body}{'?' if last and ends_asking(last[0]) else '.'} {sign_off}"


# saying you like the item: "I like the switch a lot", "i really like it", "I loved the phone" (seen in a real setup on
# 3 Oct: said every time, never learned, as the item's name changes each time). Learned as "I like the {item}", the
# item's name put in for each listing
LIKES = re.compile(r"\bi\s+(?P<really>really\s+|do\s+|absolutely\s+|honestly\s+)?(?P<verb>like|love|loved|liked|luv)\s+"
                   r"(?:the\s+(?:the\s+)?(?P<item>[\w'’-]+)|(?P<it>it|this|that)\b)", re.IGNORECASE)


# what kind of thing a listing is, from its title, for how you name each kind ("the phone", but "the ps5")
ITEM_KINDS = (("laptop", r"\b(?:laptop|macbook|notebook|chromebook)\b"), ("tablet", r"\b(?:ipad|tablet)\b"),
              ("watch", r"\bwatch\b"), ("phone", r"\b(?:iphone|phone|galaxy|pixel)\b"),
              ("console", r"\b(?:ps[345]|playstation|xbox|switch)\b"), ("headphones", r"\b(?:airpods|headphones|earbuds)\b"))


def item_kind(title):
    """"phone", "console", "laptop"... for a title, or None."""
    return next((kind for kind, pattern in ITEM_KINDS if re.search(pattern, title or "", re.IGNORECASE)), None)


def item_naming(messages):
    """How you name the item when you say you like it: "generic" ("the phone", "the console"), "family" (the
    title's own short name: "the ps5", "the macbook", "the dyson") or "model", for all your messages ("all") and for
    each kind of item you named at least HABIT times ("phone": "generic"); {} when there's no telling. For example
    "the phone" for phones and "the ps5", "the macbook" and "the dyson" for the rest, never the model."""
    votes, by_kind = Counter(), {}
    for m in messages:
        title = m.get("listing_title") or ""
        short = [w.lower() for w in re.findall(r"[A-Za-z0-9][\w'’-]*", title)][:3]  # "PS5" whole, not "ps" "5"
        for said in LIKES.finditer(m.get("my_message") or ""):
            named = (said.group("item") or "").lower()
            if not named:
                continue  # "it", "this": no name
            way = "generic" if named in GENERIC_ITEMS else "family" if named in short else "model"
            votes[way] += 1
            by_kind.setdefault(item_kind(title), Counter())[way] += 1
            break
    found = {}
    if votes and votes.most_common(1)[0][1] >= HABIT:
        found["all"] = votes.most_common(1)[0][0]
    for kind, counted in by_kind.items():
        way, n = counted.most_common(1)[0]
        if kind and n >= HABIT and way != found.get("all"):
            found[kind] = way
    return found


def likes_of(messages):
    """How you say you like the item, with its name left for the listing's ("I like the {item}", "I really love the
    {item}"), when at least HABIT and SHARE of your messages say it; else None. "the" + a word of the listing's
    title or a word for any item ("the phone"), or "it"/"this"."""
    mine = [m for m in messages if m.get("my_message")]
    found = []
    for m in mine:
        item = set(words(m.get("listing_title") or "")) | GENERIC_ITEMS
        for said in LIKES.finditer(m["my_message"]):
            if said.group("it") or set(words(said.group("item") or "")) & item:
                found.append(said)
                break
    if len(found) < HABIT or len(found) / max(1, len(mine)) < SHARE:
        return None
    really = sum(bool(f.group("really") and f.group("really").strip().lower() == "really") for f in found) * 2 > len(found)
    verb = Counter("love" if f.group("verb").lower().startswith(("lov", "luv")) else "like" for f in found).most_common(1)[0][0]
    return f"I {'really ' if really else ''}{verb} the {{item}}"


# the words a draft may write short your way, and never anything else: names, items and places stay as written
SHORTENED = {"you": {"u"}, "your": {"ur"}, "please": {"pls", "plz"}, "thanks": {"thx"}, "would": {"wud"},
             "could": {"cud"}, "because": {"cos", "coz", "cuz"}, "okay": {"ok"}, "message": {"msg"}}
# (not when: "2day", "2nite" and "tmrw" stay in your own sentences as you wrote them, but a draft's "tonight" isn't
# rewritten, as the checks that say a time once read it; nor words that are often something else: "are" in "the sides
# are scratched", "great" in "Great Yarmouth", "cd" a CD, "yr" a year: 3 Oct review)


def shortcuts_of(messages):
    """The everyday words you write short (SHORTENED), when the short way is in at least HABIT and SHARE of your
    messages and more often than the word in full: {"you": "u", "today": "2day"} (3 Oct)."""
    mine = [m.get("my_message") or "" for m in messages if m.get("my_message")]
    whole = lambda text: re.findall(r"[\w'’]+", text.lower())  # "2day" whole (words() splits off its 2)
    uses = Counter(w for text in mine for w in whole(text))
    found = {}
    for word, ways in SHORTENED.items():
        if " " in word:
            continue
        for written in sorted(ways):
            held = sum(written in whole(text) for text in mine)
            if held >= HABIT and held / max(1, len(mine)) >= SHARE and uses[written] > uses[word]:
                found[word] = written
                break
    return found


def shortened(text, shortcuts, keep=()):
    """A draft with the words you write short written your way ("Could you hold it?" -> "Could u hold it?"): only
    those (SHORTENED), as whole words, never in a contraction ("you're"), a name or place written with a capital
    inside a sentence ("Great Yarmouth"), nor in keep: your sign-off, the checked reason and the item's name, which
    stay word for word (3 Oct review: "Thank u, Sam :)", and a fixed reason the message no longer had)."""
    if not shortcuts or not isinstance(text, str):
        return text
    held = [k for k in keep if isinstance(k, str) and k.strip() and k in text]
    for n, k in enumerate(held):
        text = text.replace(k, f"\x00{n}\x00")
    for word, written in shortcuts.items():
        if word not in SHORTENED or written not in SHORTENED[word]:
            continue

        def short(m):
            starts = m.start() == 0 or re.search(r"[.!?]\s+$", text[:m.start()]) is not None
            if m.group()[:1].isupper() and not starts:
                return m.group()  # a name's or a place's capital, not a sentence's
            return written[:1].upper() + written[1:] if starts and m.group()[:1].isupper() else written
        text = re.sub(rf"(?<![\w'’]){re.escape(word)}(?![\w'’])", short, text, flags=re.IGNORECASE)
    for n, k in enumerate(held):
        text = text.replace(f"\x00{n}\x00", k)
    return text


# a long sentence of yours as its parts: "Hi, I can do [OFFER] and I can pick it up tonight, I love the switch." is
# "I can do [OFFER]", "I can pick it up tonight" and "I love the switch" (seen in a real setup on 3 Oct: long sentences,
# never the same twice, so the offer and the closing were never learned). Learned only where no whole sentence is a habit
CLAUSE_BREAK = re.compile(r"\s*[,;]\s*|\s+(?:and|but|because|cos|so|as)\s+(?=(?:i|we|u|you|i'?ll|i'?m|i'?d|if|can|will)\b)"
                          r"|\s+because\s+|\s+(?=i\s+(?:really\s+|do\s+)?(?:like|love|loved)\b)", re.IGNORECASE)
# ("and" breaks only where a new part starts: "...pay [OFFER] and I can come", never "come and collect")


def clauses(sentence):
    """A sentence's parts (CLAUSE_BREAK), without the marks that end them."""
    return [part.strip(" .!") for part in CLAUSE_BREAK.split(sentence or "") if part and part.strip(" .!")]


def offer_clause(sentence):
    """The part of your offer sentence that makes the offer, without your greeting, its price as AlertFlip writes it
    (how you write it is price_style's): "Hi, I can pay [OFFER]£ for it and ..." -> "I can pay £[OFFER]"."""
    core = ungreeted(sentence, opening(sentence)) if opening(sentence) else sentence
    part = next((c for c in clauses(core) if "[OFFER]" in c), None)
    if not part or ends_asking(part):
        return None
    part = re.sub(r"\s*£?\s?\[OFFER\]\s?£?", " £[OFFER]", part).strip()
    part = re.sub(r"\s+for (?:it|this|them)$", "", part, flags=re.IGNORECASE)
    return part[:1].upper() + part[1:] + "."


def closing_clause(part):
    """A part of what you write after your offer, as it's counted for your closing ("I can come and collect it" ->
    "I can come and collect"), or None for one that's no closing: your sign-off, how you like the item, the flaw,
    a price, a question, or one word."""
    if (not part or ends_asking(part) or "[OFFER]" in part or re.search(r"\d", part) or LIKES.search(part)
            or re.search(MENTIONS["condition"], part, re.IGNORECASE) or DONT_MIND.search(part)
            or tail_start(part, THANKS) == 0 or SIGNED.match(part.strip()) or len(words(part)) < 2):
        return None
    part = re.sub(r"\s+(?:it|them)$", "", part.strip(), flags=re.IGNORECASE)
    if tail_start(part, THANKS) is not None or TAIL_TOKEN.search(part) and re.search(SMILEY, part):
        return None  # "...collect. remi :)" left in it
    return part[:1].upper() + part[1:]


# how you write your offer's price, when it isn't AlertFlip's "£185": "185£", "185" or "185 quid" (3 Oct)
PRICE_STYLES = {"after": "170£", "bare": "170", "word": "170 quid"}


def price_style(messages):
    """How most of your messages write their offer's price: "after" ("115£"), "bare" ("185") or "word" ("185
    quid"), when at least HABIT and SHARE do; None when that's "£185", as AlertFlip writes it, or no one way is a
    habit."""
    seen = Counter()
    for m in messages:
        text = m.get("my_message") or ""
        found = next((p for p in OLD_PRICE.finditer(text) if not SAID_BACK.search(text[:p.start()])), None)
        if not found:
            continue
        said, after = found.group(), text[found.end():found.end() + 2]
        seen["before" if "£" in said else "word" if found.group(1) else "after" if re.match(r"\s?£", after) else "bare"] += 1
    if not seen:
        return None
    style, n = seen.most_common(1)[0]
    return style if style != "before" and n >= HABIT and n / max(1, len(messages)) >= SHARE else None


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
    """The greeting a message opens with: "Hi mate, is this..." -> "Hi mate",
    and typed with no comma after it: "hi wud u take £240?" -> "hi", "Hey
    mate is this still available?" -> "Hey mate"."""
    first = re.split(r"[,.!?\n]", text.strip(), maxsplit=1)[0].strip()
    tokens = first.split()
    if not tokens or tokens[0].lower() not in GREETING_WORDS:
        return ""
    if tokens[0].lower() in WEAK_GREETINGS and len(tokens) > 1 and tokens[1].lower() not in CALLED | STARTS:
        return ""  # "Evening collection ok?", "Morning pick up?": the word of something else
    if len(tokens) <= 3:
        return first
    if tokens[1].lower() in CALLED:
        return " ".join(tokens[:2])
    return "" if tokens[0].lower() in WEAK_GREETINGS and tokens[1].lower() not in STARTS else tokens[0]


def habit_key(sentence):
    """A sentence as it's counted for a habit: its words in lower case,
    without its emojis or when you'd come, so "I'll do £[OFFER] if you can
    save it for me 🙏😊" and "...for me 🙏", or "...hold it for me until this
    evening." and "...until tomorrow.", are one habit. An emoji on its own
    ("🙏") stays itself."""
    plain = WHOLE_EMOJI.sub(" ", sentence)
    if not re.search(r"\w", plain):
        return sentence.strip()
    plain = plain if CONTRAST.search(plain) else WHEN.sub(" ", plain)
    return " ".join(re.findall(r"[\w£\[\]'’]+", plain.lower()))


def without_item(sentence, item):
    """A sentence without the item named after the offer, when that's the
    listing's own: "Would you consider £[OFFER] for the AirPods?" -> "Would
    you consider £[OFFER]?", so it's a habit whatever you're buying. item:
    the title's words that name the item."""
    found = ITEM_AFTER.search(sentence)
    named = set(words(found.group("item"))) if found else set()
    if not named or named & NOT_THE_ITEM or not (named <= item or named <= GENERIC_ITEMS):
        return sentence
    return sentence[:found.start()] + sentence[found.end():]


def case_places(text):
    """The letters where a capital would go: a sentence's first letter (not
    one that starts with a price, a number or an emoji) and "i" on its own.
    A name's capitals ("iPhone", "PS5") aren't one."""
    starts = [s.strip()[0] for s in SENTENCES.split(text.strip()) if s.strip() and s.strip()[0].isalpha()]
    return starts + re.findall(r"\b[iI]\b", text)


def is_lowercase(text):
    """Whether a message is written in lower case where a capital would go:
    "hi wud u take £240 cash? can come 2day". One with no such place ("£170
    cash?") says nothing either way (case_places)."""
    places = case_places(text)
    return bool(places) and all(c.islower() for c in places)


def gives_flaw_in(statement):
    """Whether one of your sentences gives a flaw: main's words for it anywhere ("scratches",
    "cracked"), the rest inside a reason ("as the battery is at 84%"), and never
    in don't-mind wording ("battery health doesn't bother me")."""
    # sentence by sentence: "No worries if not." at the end doesn't take back "as the back is cracked" (26 Sep red team)
    return any(not DONT_MIND.search(part) and bool(re.search(MENTIONS["condition"], part, re.IGNORECASE)
                                                   or REASON_FLAW.search(part))
               for part in SENTENCES.split(statement) if part.strip())


# when you'd come, as it ends a sentence (before its full stop and any sign-off), one time or a list of them: "Can
# collect today." and "Can collect today or tomorrow." go without it, the whole list (Habits)
WHEN_AT_END = re.compile(rf"[,;:]?\s*\b(?:(?:until|till|til|by)\s+)?{TIMES}(?:\s*(?:or|and|&|/)\s*{TIMES})*\b"
                         r"(?=[\s.!?…]*$)", re.IGNORECASE)
# ...and what doesn't read once a time is out, either side of where it was (26 Sep red team: "Can collect or Saturday.",
# "Free from till Sunday", "Can collect either.", "Can collect as early as."): a word it hangs on, as what it's about
# ("either today or tomorrow", "both tonight and...", "as early as today", "any time after today", "from today", "is
# tonight ok?", "first thing tomorrow", "I'd prefer tonight", "ideally tonight"). "Can pop in today" and "later on
# today" read without it...
HUNG_ON = re.compile(r"(?<![\w'’])(?:either|both|neither|between|from|for|since|after|before|as|than|of|to|or|and|n|nor|"
                     r"but|if|whether|is|are|was|be|been|would|could|will|can|should|does|do|did|make|prefer|like|want|"
                     r"fancy|say|even|only|thing|ideally|hopefully|preferably|probably|maybe|possibly|perhaps)\s*$|"
                     r"[&/+]\s*$", re.IGNORECASE)
# ...or what joins it to more of when after it, or says it's the time that suits: "today or Saturday", "today till
# Sunday", "today and tomorrow", "tonight, Saturday or Sunday", "tonight's", "tomorrow morning", "today 6-7pm", "today
# only", "tomorrow works" ("today and pay cash" and "today, is that ok?" read without it)
MORE_WHEN = rf"(?:(?:{TIMES}|later|whenever|any ?time|(?:the )?weekend|(?:mon|tue|wed|thu|fri|sat|sun)\w*|this|next)\b|\d)"
JOINED_ON = re.compile(rf"['’]s\b|\s*(?:[&/+\-–\d]|(?:or|nor|n|till|til|until|through|thru|than|only|onwards?|ish|too|"
                       r"morning|afternoon|evening|eve|night|lunch\w*|teatime|latest|earliest|at the (?:latest|earliest)|"
                       rf"is|isn['’]?t|was|would|will|works?|suits?|ok|okay|good|fine|alright|better)\b|"
                       rf"(?:and|to)\s+{MORE_WHEN})|\s*,\s*{MORE_WHEN}", re.IGNORECASE)


def time_places(sentence):
    """The times a sentence gives ("today", "till tomorrow"), each with its
    place among its other words, as habit_key counts them: "Can collect
    today after work." -> [(2, <"today">)]."""
    return [(len(re.findall(r"[\w£\[\]'’]+", WHEN.sub(" ", sentence[:found.start()]))), found)
            for found in WHEN.finditer(sentence)]


def times_said(sentence):
    """The times a sentence gives, by their place (time_places): "Can collect
    today after work." -> {2: ("today",)}; "till tomorrow" and "until
    tomorrow" are one time."""
    said = {}
    for where, found in time_places(sentence):
        time = re.sub(r"^(?:(?:until|till|til|by)\s+)", "", found.group().strip().lower())
        said[where] = (*said.get(where, ()), time)
    return said


def without_when(sentence, varied):
    """A sentence without its times at these places (times_said), or None
    when one can't come out and leave it reading. A list of times that ends
    it goes whole ("Can collect today or tomorrow." -> "Can collect."); one
    inside it goes alone ("Can collect today after work." -> "Can collect
    after work."), never one a word hangs on (HUNG_ON), one joined to more
    of when (JOINED_ON), nor one with less than two words of its own clause
    before it ("Today if possible.", "Hi, tonight if poss"). As it is when
    none of its times is at one of them."""
    end = WHEN_AT_END.search(sentence)
    spans = []
    for where, found in time_places(sentence):
        if where in varied:
            span = end.span() if end and found.start() >= end.start() else found.span()
            spans += [span] if span not in spans else []
    if not spans:
        return sentence
    for start, stop in sorted(spans, reverse=True):
        before, after = sentence[:start], sentence[stop:]
        # ...nor "up" before "until tonight": "Free any time up until tonight." isn't "Free any time up."
        up_to = re.match(r"\W*(?:until|till|til|by)\b", sentence[start:stop], re.IGNORECASE) and \
            re.search(r"\bup\s*$", before, re.IGNORECASE)
        own = re.findall(r"[\w£\[\]'’]+", re.split(r"[.!?…,;:]", before)[-1])  # its clause's words before it
        if HUNG_ON.search(before) or JOINED_ON.match(after) or up_to or len(own) < 2:
            return None
        sentence = before.rstrip() + after
    plain = re.sub(r"\s+([.,!?])", r"\1", re.sub(r",\s*(?=[,.!?…]|$)", "", re.sub(r"\s{2,}", " ", sentence))).strip()
    return plain if len(re.findall(r"[A-Za-z']+", plain)) >= 2 and not re.match(r"\W", plain) else None


class Habits:
    """Sentences counted for one part of your phrasebook (an opener, an offer
    sentence, a closing): near-repeats count as one (habit_key), written the
    way you write it most, the newest of equals. Each is kept with the kinds
    of offer it came with (kind_of), for a habit you write whatever the offer."""

    def __init__(self):
        self.keys, self.ways, self.last, self.kinds = Counter(), {}, {}, {}

    def add(self, sentence, kind=None):
        key = habit_key(sentence)
        self.keys[key] += 1
        self.ways.setdefault(key, Counter())[sentence] += 1
        self.last[sentence] = sum(self.keys.values())
        self.kinds.setdefault(key, set()).add(kind)

    def habit(self, kinds=()):
        """Your habit here, or None when no sentence is in HABIT of your
        messages. kinds: only one you wrote with each of these kinds of
        offer ("lower", "asking", "more"): "Could you hold it for me?",
        written only when paying asking, isn't how you end a lower offer
        (26 Sep red team)."""
        key = next((key for key, n in self.keys.most_common() if n >= HABIT and set(kinds) <= self.kinds[key]), None)
        if key is None:
            return None
        ways = self.ways[key]
        best = max(ways, key=lambda sentence: (ways[sentence], self.last[sentence]))
        if len(ways) > 1 and ways[best] < HABIT and not CONTRAST.search(best):
            # ways that differ in when ("until this evening", "until tomorrow"): said without the time you vary, as no
            # one time is your habit and it would clash with a draft's closing ("hold it till tonight. Can collect
            # today."), its sign-off kept ("Can collect today 👍" -> "Can collect 👍"). Wherever it is: "Can collect
            # today after work." and "...tomorrow after work." are "Can collect after work."; and only that one: a
            # time you write every way stays ("Could you hold it till tonight for me? Can collect today." and "...till
            # tomorrow for me? Can collect today." are "Could you hold it for me? Can collect today."). As you wrote
            # it newest where what's left wouldn't read (without_when): "Can collect either tonight or tomorrow.",
            # never "Can collect either." (26 Sep red team, round 2: only a time that ended the sentence went)
            said = [times_said(way) for way in ways]
            varied = {where for where in set().union(*said) if len({times.get(where) for times in said}) > 1}
            core = SIGN_OFF.sub("", best).rstrip()
            plain = without_when(core, varied)
            return f"{plain}{best[len(core):]}" if plain else best
        return best


# a word of when: a day, a month, a time of day or soon, as sellers and buyers type them ("Saturday", "sat", "dec",
# "2nite", "tmrw", "asap", "lunchtime"). Never a place, nor a word of one's name, so a place ends where one starts:
# "collect from Leeds LS6 Saturday" is from "Leeds LS6" (26 Sep red team). Shared with flip.message_drafter (its
# made-up place check), flip.writer (collecting_from) and flip.reader (the pickup place)
WHEN_WORDS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "mon", "tue", "tues", "wed",
              "weds", "thu", "thur", "thurs", "fri", "sat", "sun", "mondays", "tuesdays", "wednesdays", "thursdays",
              "fridays", "saturdays", "sundays", "weekday", "weekdays", "weekend", "weekends", "week", "weeks", "month",
              "day", "days", "january", "february", "march", "april", "may", "june", "july", "august", "september",
              "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct",
              "nov", "dec", "today", "tonight", "tonite", "tomorrow", "tomorow", "tommorow", "tommorrow", "tmrw", "tmr",
              "tmoz", "tomoz", "tomo", "2day", "2nite", "2night", "2moro", "2morro", "2morrow", "2mrw", "asap", "now",
              "later", "soon", "morning", "mornings", "afternoon", "afternoons", "evening", "evenings", "eve", "night",
              "nights", "midday", "noon", "lunch", "lunchtime", "teatime", "dinner", "dinnertime", "daylight",
              "christmas", "xmas", "easter"}
# ...or in figures: "6pm", "5-7pm", "6.30", "18:00", "the 12th"
WHEN_FIGURE = r"\d{1,2}(?:[:.]\d\d)?(?:\s*[-–]\s*\d{1,2}(?:[:.]\d\d)?)?\s*(?:am|pm)\b|\d{1,2}[:.]\d\d\b|\d{1,2}(?:st|nd|rd|th)\b"
WHEN_WORD = rf"(?i:(?:{'|'.join(sorted(WHEN_WORDS, key=len, reverse=True))})\b|{WHEN_FIGURE})"
# ...said between collecting and where: "Can collect today from Headingley", "on Saturday from", "at 6pm from", and
# with a dash, colon or dots after it: "Can collect tonight - in Leeds if ok?" (26 Sep red team: its Leeds got past the
# made-up place check, as "Can collect tonight in Leeds" doesn't)
WHEN_BEFORE = rf"(?:(?i:on|this|next|at)\s+)?{WHEN_WORD}(?:\s+{WHEN_WORD})?\s*[,:\-–—…]*\s+"
# where a past message says you'll collect from: "Can collect from Leeds today", "can pick up in rotherham", "collect
# from LS6", "Can collect today from Headingley", "Collection from Wakefield is fine" (not "from yours", "in person",
# "at half 6", "from 6pm"): when you do, your collecting sentence takes the listing's place
PLACE_SAID = re.compile(rf"\b(?:collect(?:ing|ion|ed)?|pick(?:ing)? (?:it |them )?up|pick-?up|meet|come|get it|grab it)"
                        rf"\s+(?:it\s+|them\s+)?(?:{WHEN_BEFORE})?(?:from|in|at|near)\s+(?P<place>[A-Za-z][\w'-]*)",
                        re.IGNORECASE)
# what after "collect from", "in", "at" or "near" isn't a place: "from yours", "in person", "in public", "at half 6",
# "at whatever time suits", "at ur convenience", "at six", "from Friday". One list for names_places here and the
# drafter's made-up place check (flip.message_drafter), which had drifted apart: "Can collect in person today." was
# refused as a place, "person" (26 Sep red team)
NUMBERS_IN_WORDS = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
                    "fifteen", "twenty", "thirty", "forty"}
NOT_A_PLACE = WHEN_WORDS | NUMBERS_IN_WORDS | {
    "you", "yours", "your", "you're", "youre", "u", "ur", "urs", "ya", "yer", "me", "my", "mine", "us", "our", "ours",
    "his", "her", "hers", "their", "theirs", "home", "work", "there", "here", "anywhere", "somewhere", "the", "a", "an",
    "any", "anytime", "whenever", "whatever", "once", "after", "before", "around", "about", "under", "roughly", "approx",
    "some", "short", "notice", "this", "next", "least", "latest", "earliest", "convenience", "person", "public", "middle",
    "half", "quarter", "few", "time", "moment", "cash", "hand"}
# ...but "the", or a number with a capital, and a name after it start a place's name: "Seven Sisters", "the Trafford
# Centre" ("at Six Thirty", "at the Weekend" and "at seven" are when)
NAME_AFTER = re.compile(r"\s+([A-Z][\w'-]*)")


def names_places(texts):
    """Whether your messages name where you'll collect from, in at least
    HABIT of them: "Can collect from Leeds today" and "Can collect today from
    Headingley" do, "Can collect today", "Can collect from yours" and "Can
    collect in person" don't."""
    def named(found, text):
        word, after = found.group("place"), NAME_AFTER.match(text, found.end("place"))
        starts_name = word.lower() == "the" or word[:1].isupper() and word.lower() in NUMBERS_IN_WORDS
        return word.lower() not in NOT_A_PLACE or starts_name and bool(after) and after.group(1).lower() not in NOT_A_PLACE
    return sum(any(named(m, t) for m in PLACE_SAID.finditer(t)) for t in texts) >= HABIT


def style_card(messages):
    """What your messages have in common. Empty if there are none yet. What
    they mention is read in what they say, not ask: "what condition is it
    in?" mentions no condition, but the offer's own question counts ("would
    you take £185 cash?" mentions cash). The greeting is counted whatever its
    case ("Hi mate", "hi mate"), written the way you write it most."""
    mine = [m for m in messages if m.get("my_message")]
    texts = [m["my_message"] for m in mine]
    if not texts:
        return {}
    share = lambda found: sum(found) / len(texts) >= SHARE
    said = [statements(t) for t in texts]
    # the flaw is a reason for a lower offer: whether you give it is counted on those, when there are enough; good
    # condition is a reason for paying more, counted on those (26 Sep)
    kinds = [kind_of(m) for m in mine]
    pool = lambda kind: [s for s, k in zip(said, kinds) if k == kind] if kinds.count(kind) >= HABIT else said
    # ...on the listings that had a flaw, when the titles show that for at least HABIT of them: "I like the PS5"
    # under a flawless one says nothing of whether you give a flaw (3 Oct: 1 of 5 lower offers gave one, but 1 of
    # the 2 with a flaw did)
    flawed = [s for s, k, m in zip(said, kinds, mine) if k == "lower" and FLAW_IN_TITLE.search(m.get("listing_title") or "")]
    lower = flawed if len(flawed) >= HABIT else pool("lower")
    gives_flaw = sum(map(gives_flaw_in, lower)) / len(lower) >= SHARE
    praised = lambda said: any(PRAISE.search(part) and not DONT_MIND.search(part) for part in SENTENCES.split(said))
    praises = sum(map(praised, pool("more"))) / len(pool("more")) >= SHARE
    card = {"messages": len(texts), "words": int(statistics.median(len(t.split()) for t in texts)),
            "questions": int(statistics.median(t.count("?") for t in texts)),
            "emoji": share(bool(EMOJI.search(t)) for t in texts),
            "mentions": [name for name, pattern in MENTIONS.items()
                         if (gives_flaw if name == "condition" else
                             share(bool(re.search(pattern, t, re.IGNORECASE)) for t in said))]}
    card["praise"] = praises
    card["asks_lower"] = asks_lower(mine)
    greeting, times = Counter(opening(t).lower() for t in texts).most_common(1)[0]
    if greeting and times / len(texts) >= SHARE:
        card["greeting"] = Counter(opening(t) for t in texts if opening(t).lower() == greeting).most_common(1)[0][0]
        greeted = [t for t in texts if opening(t).lower() == greeting]
        # typed with a space and a small letter after it, most times: "hi wud u take..." ("Hi mate! Would" isn't)
        if sum(bool(re.match(rf"\s*{re.escape(opening(t))}\s+[a-z]", t)) for t in greeted) * 2 > len(greeted):
            card["greeting_bare"] = True
        # ...and the mark you type after it, when it's not a comma: "Hi mate! Would you take..."
        marks = Counter(m.group(1) for t in greeted for m in [re.match(rf"\s*{re.escape(opening(t))}\s*([,!.])", t)] if m)
        if marks and marks.most_common(1)[0][0] in "!.":
            card["greeting_mark"] = marks.most_common(1)[0][0]
    elif sum(not opening(t) for t in texts) * 2 > len(texts):
        # ...or none: most of your messages open with what they say ("£150 cash? Can collect today."), so a draft
        # doesn't greet either (26 Sep red team: "Hi," was put in front). "Hi"/"Hiya"/"Hello" every time is a greeting
        card["no_greeting"] = True
    cased = [t for t in texts if case_places(t)]  # "£170 cash?" says nothing about how you write
    if len(cased) >= HABIT and sum(map(is_lowercase, cased)) / len(cased) >= LOWERCASE:
        card["lowercase"] = True
    card["phrases"] = phrasebook(mine)
    # ...and for where you buy: the messages you wrote on Facebook and Gumtree, and on eBay and Vinted
    card["by_market"] = {group: phrasebook(there) for group, pattern, _ in MARKET_GROUPS
                         for there in [[m for m in mine if pattern.search(m.get("marketplace") or "")]]
                         if len(there) >= HABIT}
    asked = Counter(q for t in texts for q in set(questions_in(t)))
    card["asks"] = sorted(q for q, n in asked.items() if n >= HABIT)  # questions you ask every time
    card["promises"] = sorted(set().union(*(promised_in(t) for t in texts)))
    card["names_places"] = names_places(texts)
    if (signed := signature(mine)):
        card["signature"] = signed
        # ...once: out of your closings, where it was learned too, so removing it removes it (3 Oct review), and out of
        # an offer sentence it ends ("Hi, would you take £185, cheers Dan": 14 Oct hunt, the reason went after it and it
        # came twice, "...£255, cheers Dan, given the small crack on the back? cheers Dan")
        for book in (card["phrases"], *card["by_market"].values()):
            for slot in ("opener", *OFFER_SLOTS, *CLOSING_SLOTS):
                if isinstance(book.get(slot), str) and book[slot]:
                    left = unsigned(book[slot], signed)
                    book[slot] = left if words(left) else None
        # ...and not on a kind of offer you've sent at least HABIT of without it (signed only under asking)
        allowed = THANKS | sign_off_names(mine)
        signed_kinds = {kind_of(m) for m in mine for at in [tail_start(m["my_message"], allowed)]
                        if at is not None and tail_words(m["my_message"][at:]) == tail_words(signed)}
        made = Counter(kind_of(m) for m in mine)
        card["signature_skip"] = sorted(k for k in KINDS if made[k] >= HABIT and k not in signed_kinds)
    if (likes := likes_of(mine)):
        card["likes"] = likes
        if (naming := item_naming(mine)):
            card["item_naming"] = naming  # {"all": "family", "phone": "generic"}
    if (style := price_style(mine)):
        card["price_style"] = style
    if (short := shortcuts_of(mine)):
        card["shortcuts"] = short
    return card


def statements(text):
    """What a message says, not asks: its sentences that don't ask, and the one that makes the offer."""
    return " ".join(s for s in SENTENCES.split(text.strip()) if s.strip() and (not ends_asking(s) or OLD_PRICE.search(s)))


def questions_in(text):
    """A message's questions in their plain words, prices left out:
    "Would you take £185? Still available?" -> ["would you take offer", "still available"]."""
    return [" ".join(words(without_prices(s))) for s in SENTENCES.split(text.strip()) if s.strip() and ends_asking(s)]


def closing_parts(closing):
    """A closing's sentences, a sign-off after a comma one of its own: "Can
    collect today, thanks." -> ["Can collect today", "thanks."]."""
    parts = []
    for sentence in (s.strip() for s in SENTENCES.split(closing.strip()) if s.strip()):
        said, comma, signed = sentence.rpartition(",")
        parts += [said.strip(), signed.strip()] if comma and said.strip() and SIGNED.match(signed.strip()) else [sentence]
    return parts


def phrasebook(messages):
    """The sentences you write around an offer, with old prices hidden: your
    opener ("Hi mate, is this still available?"), how you word the offer
    ("Would you take £[OFFER] cash?") and your closing ("Can collect today."),
    each the one you use most if it's in at least HABIT messages, else None
    ("" when that's nothing: most of your messages start with the offer).
    Plus the emoji you use most, in at least HABIT messages ("" when they
    have none, None when none is a habit yet): never one that only came
    with words calling the offer low ("Cheeky I know 😂"), which on an
    offer of the asking price reads as a joke. Only messages with one price
    count, so the price in a habit is always the offer, and a sentence that
    names its own item ("is the iPhone still available?") is never a habit.
    The offer is learned for each kind too (offer_lower, offer_asking,
    offer_more), from the messages whose offer was under, at or over the
    listing's asking price: 3 messages paying asking ("I can pay £[OFFER]")
    don't make the way you ask for less. So is the closing (closing_lower,
    closing_asking, closing_more), else it's your closing that came with
    that kind: "Could you hold it for me?" from 2 messages paying asking
    ends an offer of the asking price, not one under it (for_kind picks the
    one for a draft). Your closing ("closing") is one you write with every
    kind of offer you make."""
    openers, offers, closings, emoji = Habits(), Habits(), Habits(), Counter()
    sign_offs = Habits()  # each message's last sentence when it only signs off ("Kind regards, Sam")
    offer_parts, closing_parts_ = Habits(), Habits()  # the parts of your long sentences (clauses)
    plainly = set()  # emojis that came with more than words calling the offer low
    sentence_kinds = {}  # each sentence of a closing (habit_key) and the kinds of offer it came with
    priced = 0
    by_kind = {slot: Habits() for slot, _ in KIND_SLOTS + CLOSING_KIND_SLOTS}
    for m in messages:
        if len(OLD_PRICE.findall(m["my_message"])) != 1 or ASKING_SAID.search(m["my_message"]):
            continue  # one price, the offer: not "still available at £220?" or "you're asking £220"
        text = without_prices(m["my_message"])
        item = {w for w in words(m.get("listing_title") or "") if w not in TITLE_FILLER}
        names_item = lambda sentence: bool(item & set(words(sentence)))
        sentences = [s.strip() for s in SENTENCES.split(text.strip()) if s.strip()]
        # each emoji once a message ("🙏🙏" is one message's), and whether it came in a sentence that doesn't call the
        # offer low: one message's 😂 isn't a habit, nor is "Cheeky I know 😂" every time (26 Sep red team)
        emoji.update({found for sentence in sentences for found in WHOLE_EMOJI.findall(sentence)})
        plainly.update(found for sentence in sentences if not LOWBALL.search(sentence)
                       for found in WHOLE_EMOJI.findall(sentence))
        at = next(i for i, s in enumerate(sentences) if "[OFFER]" in s)
        opener, offer, closing = (without_item(part, item) for part in (" ".join(sentences[:at]), sentences[at],
                                                                          " ".join(sentences[at + 1:])))
        kind = kind_of(m)
        priced += 1
        # your usual offer sentence is the one you make an offer with, not how you ask them to hold it for more, nor
        # asking whether they'd go lower ("Would you take less than £[OFFER]?": 26 Sep red team)
        offering = kind != "more" and not LOWER_THAN.search(offer)
        for counts, sentence in ((openers, opener), *(((offers, offer),) if offering else ()), (closings, closing)):
            if not names_item(sentence):
                counts.add(sentence, kind)
        if offering and (part := offer_clause(offer)) and not names_item(part):
            offer_parts.add(part, kind)
        # ...and the parts after it, its sign-off left out: "Cheers mate, Sam" isn't the parts "Cheers mate" and "Sam"
        # (14 Oct hunt: Offer more ended "...hold it for me. Cheers mate." and "...Jess x.")
        ends = signed_part(closing)
        unsigned_closing = closing[:ends] if ends is not None else closing
        after = clauses(offer[offer.index("[OFFER]"):])[1:] + [c for sentence in SENTENCES.split(unsigned_closing.strip())
                                                               if sentence.strip() for c in clauses(sentence)]
        for part in dict.fromkeys(filter(None, (closing_clause(c) for c in after))):  # each once a message
            if not names_item(part):
                closing_parts_.add(part, kind)
        if kind and not names_item(offer):
            by_kind[f"offer_{kind}"].add(offer)
        if kind and not names_item(closing):
            by_kind[f"closing_{kind}"].add(closing)
            for part in closing_parts(closing):
                sentence_kinds.setdefault(habit_key(part), set()).add(kind)
        last = SENTENCES.split(closing.strip())[-1].strip() if closing.strip() else ""
        if last and SIGNED.match(last):
            sign_offs.add(last, kind)
    counted = priced  # priced messages: with none, there's no saying you use no emoji
    # ...nor with emojis that aren't a habit yet: None, so where you buy your emoji is still the one of all your
    # messages; "" only when these messages have none
    usual = next((found for found, n in emoji.most_common() if n >= HABIT and found in plainly), None)
    book = {"opener": openers.habit(), "offer": offers.habit(),
            **{slot: counts.habit() for slot, counts in by_kind.items() if slot in OFFER_SLOTS},
            "emoji": usual if usual is not None else "" if counted and not emoji else None}
    # your closing whatever the offer: one you wrote with every kind of offer you make (a message with no asking price
    # is no kind)...
    made = {kind: sum(by_kind[f"closing_{kind}"].keys.values()) for kind in KINDS}  # closings counted for each kind
    # (a closing came with a kind when each of its sentences did, whatever that message ended with besides: "Can
    # collect today." came with the offer of the asking price that ended "Can collect today. Cheers.", 26 Sep red team,
    # round 2: that one message took your closing from every offer at and over asking)
    for key, ways in closings.ways.items():
        parts = [habit_key(part) for part in closing_parts(max(ways, key=ways.get))]
        if parts:
            closings.kinds[key] |= set.intersection(*(sentence_kinds.get(part, set()) for part in parts))
    book["closing"] = closings.habit({kind for kind, n in made.items() if n})
    if book["offer"] is None:  # no offer sentence repeats whole: the part of them that makes the offer, if one does
        book["offer"] = offer_parts.habit()
    def parts_closing(kinds):
        """The parts after your offer you write again and again, written with each of these kinds of offer (as
        closings.habit: "Can collect tonight." from lower offers alone doesn't end one of the asking price), most
        written first, two at most, as a closing; None with none."""
        said, says = [], set()
        for key, n in closing_parts_.keys.most_common():
            if n < HABIT or not set(kinds) <= closing_parts_.kinds[key]:
                continue
            way = max(closing_parts_.ways[key], key=closing_parts_.ways[key].get)
            # ...never two saying the same thing, from different messages (14 Oct hunt: "I can collect this evening.
            # Can pick up today.", "Can pay cash on collection. Can collect tonight.")
            habit = {name for name, pattern in HABIT_WORDS.items() if pattern.search(way)}
            if habit & says:
                continue
            said.append(way)
            says |= habit
            if len(said) == 2:
                break
        # each part ends with a full stop, not after a kiss or an emoji ("Jess x.")
        ended = [way if re.search(r"(?:[.!?…]|\bx{1,3}|[\U0001F300-\U0001FAFF☀-➿])$", way) else f"{way}." for way in said]
        return " ".join(ended) if said else None
    if book["closing"] is None:  # ...and the parts after it you write again and again, with every kind you make
        book["closing"] = parts_closing({kind for kind, n in made.items() if n})
    book["sign_off"] = sign_offs.habit()  # "Kind regards, Sam": for_kind's last fallback, whatever the offer
    # ...and for each kind, the one you write with it, else your closing that came with that kind, or with none of
    # it yet, with every kind you have HABIT messages of: one asking-price message ending "Cash waiting." doesn't
    # take "Can collect tonight." from your offers over asking
    for kind in KINDS:
        own = by_kind[f"closing_{kind}"].habit()
        book[f"closing_{kind}"] = own if own is not None else closings.habit(
            {kind} if made[kind] else {other for other, n in made.items() if n >= HABIT})
        if book[f"closing_{kind}"] is None and made[kind]:  # no whole one: the parts you write with this kind (3 Oct)
            book[f"closing_{kind}"] = parts_closing({kind})
    return book


def for_market(card, marketplace):
    """Your style card for a listing on this marketplace: each sentence of
    your phrasebook from the messages you wrote where you meet the seller
    (Facebook, Gumtree) or where it's posted (eBay, Vinted), when you have a
    habit there, else from all your messages."""
    group = next((name for name, pattern, _ in MARKET_GROUPS if pattern.search(marketplace or "")), None)
    there = ((card or {}).get("by_market") or {}).get(group)
    if not there:
        return card
    every = card.get("phrases") or {}
    # where you meet the seller, a habit of all your messages that posts ("would you accept £[OFFER] posted?") isn't
    # yours here (26 Sep red team); on eBay and Vinted the drafter takes collecting and cash out instead
    # in person: no posting talk, nor paying first ("Can pay straight away." is an eBay closing; on Facebook you pay
    # when you collect)
    fits = lambda text: not (group == "in_person" and isinstance(text, str) and
                             (HABIT_WORDS["postage"].search(text) or PAY_FIRST.search(text)))
    return {**card, "phrases": {slot: there[slot] if there.get(slot) is not None else
                                every.get(slot) if fits(every.get(slot)) else None
                                for slot in {*every, *there}}}


def for_kind(card, kind):
    """Your style card for one kind of offer ("lower", "asking" or "more"):
    its closing is the one for that kind (closing_lower, closing_asking,
    closing_more, as the phrasebook learned it), and it never asks them to
    hold it under asking (holding it is the deal for paying asking) nor
    calls the offer low at or over asking. Only the sentence that does
    goes: "Can collect today. Could you hold it for me?" ends a lower offer
    "Can collect today." (26 Sep red team: the hold of your asking-price
    messages ended a lower offer, and "I know it's a bit less than you're
    after." one of the asking price). So the writer and the AI's
    description of your style (describe) end it the same way."""
    phrases = (card or {}).get("phrases")
    if not phrases or kind not in KINDS:
        return card
    # with no habit for this kind (None: one message paying asking), your closing for every kind, else the sign-off
    # you always end with, its wrong sentences out below (26 Sep: Sam's one full-price message on Facebook left "I'd
    # be happy to pay the full £250." with no "Kind regards, Sam")
    closing = next((phrases[slot] for slot in (f"closing_{kind}", "closing", "sign_off") if phrases.get(slot) is not None),
                   None)
    # under asking no hold; at or over it nothing calling the offer low or less (UNDER_ASKING_TALK, 26 Sep)
    wrong = HOLD.search if kind == "lower" else lambda text: LOWBALL.search(text) or UNDER_ASKING_TALK.search(text)
    if closing and wrong(closing):
        closing = " ".join(s.strip() for s in SENTENCES.split(closing) if s.strip() and not wrong(s))
    # ...and at or over asking, emojis only when your phrasebook has one, the one the writer adds: not one message's 😂,
    # nor one that only came with "Cheeky I know" (26 Sep red team, round 2: the AI was still told "Uses emojis", and its
    # "Hi mate, I can pay £200 for it. 😂" went out)
    plain = {} if kind == "lower" else {"emoji": bool(card.get("emoji") and phrases.get("emoji"))}
    # the closing for this offer in place of yours, the kinds' own gone (so this is the same card again for it)
    return {**card, **plain, "phrases": {**{slot: text for slot, text in phrases.items() if slot not in KIND_CLOSINGS},
                                         "closing": closing}}


def kind_of(message):
    """The kind of offer a past message made, by its one price against the
    listing's asking price: "lower", "asking" or "more"; None with no asking
    price to tell by (a message pasted without one)."""
    text = message["my_message"]
    try:
        listed = re.search(AMOUNT, message.get("asking_price") or "")  # "£220 ONO" is £220
        asking = to_pence(listed.group()) if listed else None
        # the offer: the first price that isn't said back ("you're asking £220 but would you take £180?")
        price = next((m for m in OLD_PRICE.finditer(text) if not SAID_BACK.search(text[:m.start()])), None)
        found = re.search(AMOUNT, price.group()) if price else None
        offered = to_pence(found.group()) if found else None
    except (ValueError, AttributeError):
        return None
    if not asking or offered is None:
        return None
    return "lower" if offered < asking else "asking" if offered == asking else "more"


# an offer asked with no question mark: "wud u take £150 cash", "how about £60", "any chance of £90" (26 Sep)
ASKED = re.compile(r"\b(?:would|could|will|can|wud|wld|cud|cld)\s+(?:you|u|ya)\b|\b(?:how|what) about\b|\bany chance\b|"
                   r"\bwould\s+£", re.IGNORECASE)


def asks_lower(messages):
    """Whether you ask your offers under the asking price: the sentence with
    the price asks ("Would you take £150?", "wud u do £90", "Any chance of
    £250?") in at least half of your messages that offered less than the
    listing asked, or whose asking price isn't known (kind_of). Not the ones
    paying asking or more: "I'll pay £[OFFER] cash." there says nothing of
    how you ask for less. None with fewer than HABIT to tell by: then a lower
    offer is asked, as AlertFlip's are. 26 Sep red team: with no habit for
    the offer, a chatty writer whose lower offers asked 4 times in 5 had the
    AI's "Hi, I'll pay the full £170 cash." let through."""
    asked = []
    for m in messages:
        if kind_of(m) in ("asking", "more"):
            continue
        for sentence in SENTENCES.split(m["my_message"].strip()):
            if any(not SAID_BACK.search(sentence[:p.start()]) for p in OLD_PRICE.finditer(sentence)):
                asked.append(ends_asking(sentence) or bool(ASKED.search(sentence)))
                break
    return sum(asked) * 2 >= len(asked) if len(asked) >= HABIT else None


def sendable(text):
    """Your opener or closing without the sentences the checks refuse
    whatever the listing, even word for word: a story about you ("I'm only
    round the corner"), contact details, talk of a chat there hasn't been
    ("as you said") or a second price ("Can collect at 6 or 7" reads "or 7"
    as £7). describe() doesn't tell the AI to write what's always turned
    down (26 Sep red team: 'Usually ends with "Can collect after 6pm."' was,
    until the number check knew your own sentences)."""
    if not text:
        return text
    return " ".join(s.strip() for s in SENTENCES.split(text) if s.strip() and not (
        check_no_story("", s) or check_no_contact_details("", s) or PRIOR_TALK.search(re.sub(r"[’‘ʼ]", "'", s))
        or prices_in(s)))


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
    if card.get("lowercase"):
        lines.append("Writes all in lower case")
    elif (card.get("removed") or {}).get("lowercase"):
        lines.append("Writes with capitals as usual, never all in lower case")  # you removed it: the AI is told
    if card["mentions"]:
        lines.append(f"Usually mentions: {', '.join(card['mentions'])}")
    phrases = card.get("phrases") or {}  # the sentences you open and close with, which the AI dropped (26 Sep: "Cheers")
    opener, closing = (sendable(phrases.get(slot)) for slot in ("opener", "closing"))  # not one that'd be refused
    if opener and re.search(r"[A-Za-z]", opener) and not greeting_only(opener):
        lines.append(f'Usually starts with "{opener}"')
    if closing and re.search(r"\w", closing):
        lines.append(f'Usually ends with "{closing}"')
    if card.get("likes"):
        lines.append(f'Says they like the item: "{card["likes"].replace("{item}", "[item]")}"')
    if card.get("signature"):
        lines.append(f'Always signs off with "{card["signature"]}"')
    if card.get("price_style") in PRICE_STYLES:
        lines.append(f'Writes prices like "{PRICE_STYLES[card["price_style"]]}"')
    lines += [f'Writes "{written}" for "{word}"' for word, written in sorted((card.get("shortcuts") or {}).items())]
    removed = card.get("removed") or {}
    lines += [f'Never opens with "{greeting}"' for greeting in removed.get("greetings", [])]
    if removed.get("habits"):
        lines.append(f"Never mentions {and_list([HABIT_NAMES[h] for h in removed['habits']])}")
    lines += [f'Never writes "{phrase}"' for phrase in removed.get("phrases", [])]
    lines += [f'Never asks "{question_words(ask)}?"' for ask in removed.get("asks", [])]
    if removed.get("likes"):
        lines.append("Never says they like the item")
    return lines


def learned(card, removed=(), finder=""):
    """Everything your style puts in a message, one row each, for you to keep
    or remove: [{"key": "greeting:hi mate", "what": "Opens with", "value":
    "Hi mate", "used": True}, ...]. removed: the keys you removed (used is
    False for those); one your messages no longer give is still listed, to
    put back. How long your messages are isn't on it: that's not a thing it
    puts in. Neither is the offer question you ask every time, a question or
    an emoji already in one of your sentences, or an opener that's only your
    greeting. finder: the model that found what code didn't (flip-style-1b), as
    the app names it: "Signs off with (found by flip-style-1b)"."""
    card = card or {}
    rows, keys = [], set()

    def add(key, what, value):
        if key not in keys:
            keys.add(key)
            rows.append({"key": key, "what": what, "value": value, "used": key not in removed})

    phrases = card.get("phrases") or {}
    ai = set(card.get("ai_found") or ())
    marked = lambda what, part: f"{what} (found by {finder or 'the style reader'})" if part in ai else what
    if card.get("greeting"):
        add(f"greeting:{card['greeting'].lower()}", marked("Opens with", "greeting"), card["greeting"])
    for habit, name in HABIT_NAMES.items():
        if habit in card.get("mentions", []) or habit in card.get("promises", []):
            add(f"mention:{habit}", "Mentions", name)
    if "condition" in card.get("mentions", []):
        add("says-flaw", "Says the flaw", "as the reason for a lower offer")
    if card.get("praise"):
        add("praise", "Says it's in good condition", "as the reason for paying more")
    if card.get("emoji"):
        add("emoji", "Emojis", phrases.get("emoji") or "yes")
    if card.get("lowercase"):
        add("lowercase", "Writes", "all in lower case")
    if card.get("likes"):
        add("likes", marked("Says you like the item", "likes"), card["likes"].replace("{item}", "[item]"))
    if card.get("signature"):
        add("signature", marked("Signs off with", "signature"), card["signature"])
    for word, written in sorted((card.get("shortcuts") or {}).items()):
        add(f"shortcut:{word}", marked(f'Writes "{word}" as', "shortcuts"), written)
    if card.get("price_style") in PRICE_STYLES:
        add("price-style", "Writes prices as", PRICE_STYLES[card["price_style"]])
    offers = set()  # each offer sentence once, whichever kinds it's for: "Hiya, can do £… today." under and at asking
    # (and each closing: "Can collect today." under asking is your closing, listed once as that)
    # yours for all your messages, then where you buy, when that's another: "Closing on eBay and Vinted"
    for book, where in ((phrases, ""), *(((card.get("by_market") or {}).get(group) or {}, f" {label}")
                                         for group, _, label in MARKET_GROUPS)):
        for slot, what in SLOTS + KIND_SLOTS + CLOSING_KIND_SLOTS:
            text = book.get(slot)
            if text and words(text) and not (slot == "opener" and greeting_only(text)) and text.lower() not in offers:
                add(f"phrase:{slot}:{text.lower()}", marked(what, slot) + where if not where else what + where,
                    text.replace("[OFFER]", "…"))
                if slot in OFFER_SLOTS + CLOSING_SLOTS:
                    offers.add(text.lower())
    listed = [words(book[slot]) for book in (phrases, *((card.get("by_market") or {}).values()))
              for slot, _ in SLOTS + KIND_SLOTS + CLOSING_KIND_SLOTS if book.get(slot)]
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
        slots = dict(SLOTS + KIND_SLOTS + CLOSING_KIND_SLOTS)
        return (slots[slot], text.replace("[offer]", "…")) if slot in slots else None
    return {"greeting": ("Opens with", rest[:1].upper() + rest[1:]), "mention": ("Mentions", HABIT_NAMES.get(rest, rest)),
            "says-flaw": ("Says the flaw", "as the reason for a lower offer"), "emoji": ("Emojis", "yes"),
            "lowercase": ("Writes", "all in lower case"), "ask": ("Asks every time", f"{rest}?"),
            "praise": ("Says it's in good condition", "as the reason for paying more"),
            "likes": ("Says you like the item", "I like the [item]"), "signature": ("Signs off with", "your sign-off"),
            "price-style": ("Writes prices as", "your way"), "shortcut": (f'Writes "{rest}" short', "your way")}.get(kind)


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
    books = [phrases, *(card.get("by_market") or {}).values()]  # all your messages', and where you buy
    gone = {"greetings": [], "habits": [], "phrases": [], "asks": [], "emoji": False, "flaw": False, "likes": False}
    # sentences first, as they were learned: a greeting removed after would reword them out of reach
    for key in sorted(removed, key=lambda key: (not key.startswith("phrase:"), key)):
        kind, _, rest = key.partition(":")
        if kind == "greeting":
            mine = (card.get("greeting") or "").lower() == rest
            gone["greetings"].append(card.pop("greeting") if mine else rest)
            for book in books:  # your sentences keep their words, with "Hi" for the greeting, or none for "Hi"
                for slot, _ in SLOTS + KIND_SLOTS + CLOSING_KIND_SLOTS:
                    text = book.get(slot)
                    if text and opening(text).lower() == rest:
                        bare = ungreeted(text, opening(text))
                        lowered = bare if re.match(r"I\b|I'", bare) else bare[:1].lower() + bare[1:]  # "I" keeps it
                        book[slot] = (bare if rest == GREETING.lower() or not bare else f"{GREETING}, {lowered}") or None
        elif kind == "mention":
            card["mentions"] = [m for m in card.get("mentions", []) if m != rest]
            card["promises"] = [p for p in card.get("promises", []) if p != rest]
            gone["habits"].append(rest)
        elif kind == "says-flaw":
            card["mentions"] = [m for m in card.get("mentions", []) if m != "condition"]
            gone["flaw"] = True
        elif kind == "emoji":
            card["emoji"] = False
            for book in books:
                book["emoji"] = ""
                for slot, _ in SLOTS + KIND_SLOTS + CLOSING_KIND_SLOTS:
                    if book.get(slot) and not words(book[slot]):  # a closing that's only "👍"
                        book[slot] = None
            gone["emoji"] = True
            if card.get("signature"):  # "Thanks 😊" is "Thanks" (3 Oct review)
                plain = re.sub(r"\s{2,}", " ", WHOLE_EMOJI.sub("", card["signature"])).strip(" ,")
                if words(plain):
                    card["signature"] = plain
                else:
                    card.pop("signature")
        elif kind == "lowercase":
            card.pop("lowercase", None)
            gone["lowercase"] = True
        elif kind == "praise":
            card["praise"] = False
        elif kind == "likes":
            card.pop("likes", None)
            gone["likes"] = True
        elif kind == "signature":
            if card.get("signature"):
                gone["phrases"].append(card.pop("signature"))
        elif kind == "price-style":
            card.pop("price_style", None)
        elif kind == "shortcut":
            card["shortcuts"] = {w: v for w, v in (card.get("shortcuts") or {}).items() if w != rest}
        elif kind == "phrase":
            slot, _, text = rest.partition(":")
            # the habit, whichever way of it you wrote: "Can collect today." and "Can collect tonight." are one
            same = lambda sentence: bool(sentence) and habit_key(sentence) == habit_key(text)
            written = next((book[slot] for book in books if same(book.get(slot))), None)
            gone["phrases"].append(written or text)
            # no habit there: the writer words that part, or the AI writes. An offer sentence or a closing is one
            # sentence to you, so it goes from every kind of offer that has it, wherever you buy
            for book in books:
                for other in OFFER_SLOTS if slot in OFFER_SLOTS else CLOSING_SLOTS if slot in CLOSING_SLOTS else (slot,):
                    if same(book.get(other)):
                        book[other] = None
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
                             r"come (?:and |& )?get|pop (?:round|over|by)|swing by|drop by|nip (?:round|over))\b"
                             rf"|{COLLECT_TALK.pattern}",  # and every way the checks read of coming to the seller
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
        if gone.get("likes"):  # "I like the ps5 so much" out, wherever it is in the sentence
            sentence = re.sub(rf"[,\s]*(?:{LIKES.pattern})(?:\s+(?:so much|a lot|loads))?", "", sentence,
                              flags=re.IGNORECASE).strip(" ,")
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
    # a habit out for this listing only (cash on eBay, collecting on a posted one) is check_message_manner's, which
    # reads the listing's title: "the Johnny Cash LP" names it, it doesn't offer it
    problems += [f"the message mentions {HABIT_NAMES[h]}, which you removed from your style"
                 for h in gone["habits"] if h not in gone.get("listing_habits", ()) and h in HABIT_WORDS
                 and (HABIT_WORDS[h].search(message) or h in promised_in(message))]
    plain = words(without_prices(message))
    keys = {habit_key(sentence) for sentence in SENTENCES.split(without_prices(message)) if sentence.strip()}
    problems += [f"the message writes \"{p}\", which you removed from your style"
                 for p in gone["phrases"] if words(p) and (contains(plain, words(p)) or habit_key(p) in keys)]
    if gone.get("likes") and LIKES.search(message):
        problems.append("the message says you like the item, which you removed from your style")
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
    if card.get("lowercase"):
        rows.append(("Writes", "all in lower case"))
    rows.append(("Says the flaw", "yes" if "condition" in card["mentions"] else "no"))
    return rows


def phrase_rows(card):
    """The phrasebook as the app shows it, the offer price left out:
    [("Usual opener", "Hi mate,"), ("Offer sentence", "Would you take £… cash?")]."""
    every = (card or {}).get("phrases") or {}
    named = (("opener", "Usual opener"), ("offer", "Offer sentence"), *KIND_SLOTS, ("closing", "Closing"),
             *CLOSING_KIND_SLOTS, ("emoji", "Emoji"))
    rows, offers = [], set()
    # all your messages' habits, then where you buy, when that's another ("Closing on eBay and Vinted")
    for book, where in ((every, ""), *((((card or {}).get("by_market") or {}).get(group) or {}, f" {label}")
                                       for group, _, label in MARKET_GROUPS)):
        for key, label in named:
            text = book.get(key)
            if not text or where and text.lower() == (every.get(key) or "").lower() \
                    or key in OFFER_SLOTS + CLOSING_SLOTS and text.lower() in offers:
                continue  # each offer sentence and closing once, and a habit where you buy only when it's another
            rows.append((label + where, text.replace("[OFFER]", "…")))
            offers |= {text.lower()} if key in OFFER_SLOTS + CLOSING_SLOTS else set()
    return rows


class StyleBook:
    """The messages your style is learned from, kept on this Mac (private/ is
    never uploaded): the ones you wrote or pasted in the app, the drafts you
    approved, and any learned from a CSV. The style card and the message
    search follow every change, so the next draft already writes like the
    message you just added. index is the MessageIndex to keep in step, or
    None for no search."""

    def __init__(self, path=STYLE_DB, index=None, ai=None):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)  # the API answers from more than one thread
        self.lock = threading.RLock()
        self.db.executescript(TABLE)
        self.index, self._card, self._learned_card = index, None, None
        # our AI, which also reads your messages when they change (flip.style_ai): None, code alone (tests)
        self.ai, self._learning = ai, False
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

    def set_up(self, messages):
        """Your answers from setting up your style (as add takes them), in place of your last setup's: every message
        you wrote or pasted in the app (source "added") goes, and what you removed from your style is cleared, so it's
        learned from these afresh. The drafts you approved and any CSV stay. All at once: a failure changes nothing.
        The new rows, as add gives them."""
        at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = [{"id": f"msg-{uuid.uuid4().hex[:12]}", "listing_title": m.get("listing_title") or "",
                 "asking_price": m.get("asking_price") or "", "marketplace": m.get("marketplace") or "",
                 "my_message": m["my_message"].strip(), "source": "added", "at": at} for m in messages]
        with self.lock:
            old = [row_id for (row_id,) in self.db.execute("select id from messages where source = 'added'")]
            try:
                self.db.execute("delete from messages where source = 'added'")
                self.db.execute("delete from removed")
                self.db.executemany(
                    "insert into messages (id, listing_title, asking_price, marketplace, my_message, source, at) "
                    "values (:id, :listing_title, :asking_price, :marketplace, :my_message, :source, :at)", rows)
                self.db.commit()
            except sqlite3.Error:
                self.db.rollback()
                raise
            self._card = self._learned_card = None
        if self.index is not None:
            self.index.remove(old)
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
        """The style card as learned, before anything you removed comes off: by code, its gaps filled by what our AI
        found that's in your messages (flip.style_ai)."""
        from flip.style_ai import checked, merged  # flip.style_ai builds on this module
        with self.lock:
            if self._learned_card is None:
                messages = self.messages(newest_first=False)
                card = style_card(messages)
                # with our AI off (FLIP_STYLE_AI=), code alone: an older reading isn't used either (6 Oct review)
                proposals = self.ai_proposals() if self.ai is not None else {}
                try:  # what our AI stored can never break your style: code's card, as it was, if it does
                    self._learned_card = merged(card, checked(proposals, messages), messages) if proposals else card
                except Exception:  # noqa: BLE001
                    self._learned_card = card
            return self._learned_card

    def ai_proposals(self):
        """Our AI's newest suggestions ({} before any): checked against your messages as they are now, so ones made
        before your last change are still safe to use until it reads them again."""
        with self.lock:
            row = self.db.execute("select proposals from ai_style order by rowid desc limit 1").fetchone()
        try:
            return json.loads(row[0]) if row else {}
        except ValueError:
            return {}

    def ai_stale(self):
        """Whether our AI hasn't read your messages as they are now: a reading by another model counts as none, so a new
        style model (flip-style-1b after plain Gemma, 6 Oct) reads them again."""
        from flip.style_ai import messages_key
        with self.lock:
            key = messages_key(self.messages(newest_first=False))
            row = self.db.execute("select model from ai_style where key = ?", (key,)).fetchone()
        return row is None or (self.ai is not None and row[0] != getattr(self.ai, "name", ""))

    def learn_with_ai(self):
        """Our AI reads your messages (flip.style_ai.propose) and its suggestions are kept for the card, an answer of
        no habits too (so it isn't asked again for the same messages); nothing when there's no AI, it can't answer, or
        it has read these messages already. True when it learned."""
        from flip.style_ai import messages_key, propose
        if self.ai is None or not self.ai_stale():
            return False
        messages = self.messages(newest_first=False)
        proposals = propose(messages, self.ai)
        if proposals is None:
            return False
        at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.lock:
            self.db.execute("insert or replace into ai_style (key, proposals, model, at) values (?, ?, ?, ?)",
                            (messages_key(messages), json.dumps(proposals, ensure_ascii=False),
                             getattr(self.ai, "name", ""), at))
            self.db.commit()
            self._card = self._learned_card = None
        return True

    def learn_later(self):
        """learn_with_ai in the background, once at a time (about 9 s on this Mac): the next card has what it found."""
        with self.lock:  # checked and taken together: two requests at once start one learning (3 Oct review)
            if self.ai is None or self._learning or not self.ai_stale():
                return False
            self._learning = True

        def run():
            try:
                self.learn_with_ai()
            finally:
                self._learning = False
        threading.Thread(target=run, daemon=True).start()
        return True

    def removed(self):
        """The keys of what you removed from your style (learned)."""
        with self.lock:
            return {key for (key,) in self.db.execute("select key from removed")}

    def learned(self):
        """What your style puts in a message, each with whether you still use it (learned), what our AI found named
        by the model that found it."""
        from flip.ai import shown_name
        with self.lock:
            row = self.db.execute("select model from ai_style order by rowid desc limit 1").fetchone()
            return learned(self.learned_card(), self.removed(), finder=shown_name(row[0]) if row and row[0] else "")

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
