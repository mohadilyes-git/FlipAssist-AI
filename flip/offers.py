"""Three kinds of offer, and what the listing gives you to say with each.

Code reads the seller's own words about the item's condition:
- lower: a flaw the listing mentions is the reason for offering less ("as the
  back is broken"), unless the seller says the price already allows for it;
- asking: you say you don't mind the flaw;
- more: good condition the listing describes, with no flaw, is the reason for
  paying more.

Your style decides whether that point goes in by itself: it does if your past
messages usually mention condition. If they don't, the draft leaves it out and
asks you. Either way the check holds the message to the listing: it talks
about the condition only when it's meant to, says only what the listing says,
and then must say the point. Asking about the condition is always fine ("any
scratches?").
"""

import re

from flip.catalogue import words
from flip.checks import LEVELS, MARKS, NEGATIONS, clauses, has_fault, promises_in

# the seller says the price already allows for the flaw: a lower offer mustn't use it again
PRICED_IN = re.compile(r"\b(?:hence (?:the |why )?(?:the |low |cheap )?price|priced accordingly|priced to reflect|"
                       r"price reflects|reflected in (?:the )?price|taken into account|"
                       r"why it (?:is )?(?:so )?cheap|hence (?:so )?cheap)\b")
# good condition in so many words: below "excellent" and "flawless", which the checks already read
GOOD = re.compile(r"\b(?:good|great|nice|lovely|decent|fab|fantastic|brilliant|top) condition\b"
                  r"|\bcondition (?:is )?(?:very |really )?(?:good|great|nice|lovely)\b")
# damage the checks' mark words don't cover: "cosmetic damage", "smashed screen"
DAMAGE = re.compile(r"\b(?:damage|damaged|smashed|shattered|bent|torn|ripped|stained|faded|peeling)\b")
GOOD_LEVELS = ["good", "excellent", "flawless"]  # each one backs the ones before it
FLAWS = MARKS | {"fault", "damage"}
# "I don't mind the scratch" isn't "no scratch": the "don't" is about you, not the item
ATTITUDE = re.compile(r"\b(?:don'?t|do not|doesn'?t|does not)\s+(?:mind|bother me|matter)\b"
                      r"|\bnot (?:too |that |really |at all )?(?:bothered|fussed|worried)(?: about| by)?\b"
                      r"|\bno (?:problem|bother|worries|issue) with\b", re.IGNORECASE)
# an offer at the asking price says you don't mind the flaw, not just names it
DONT_MIND = re.compile(r"\b(?:don'?t|do not) mind\b|\bnot (?:too |that |really |at all )?(?:bothered|fussed|worried)\b"
                       r"|\bno (?:problem|bother|issue|worries)\b|\b(?:fine|happy|ok|okay|alright) with\b|\beven with\b"
                       r"|\bdespite\b|\bregardless of\b|\bdoesn'?t (?:bother|matter)\b", re.IGNORECASE)
# a listing read one part at a time: sentences, and what follows "but", "which"...
LISTING_PARTS = re.compile(r"[,.;!?\n()]|\s[-–—]\s|\b(?:but|which|though|although|otherwise|however|hence)\b",
                           re.IGNORECASE)
MAX_QUOTE = 8  # words of the seller's to show: enough to recognise, short enough to read
ASK = {"lower": "Mention it as the reason for your offer?",
       "asking": "Say you don't mind it?",
       "more": "Give that as the reason you're paying more?"}


def unnegated(pattern, text):
    """True if the pattern is in the text without a "no" or "not" just before it."""
    joined = " ".join(words(text))
    return any(not NEGATIONS & set(joined[:m.start()].split()[-3:]) for m in pattern.finditer(joined))


def condition_said(text):
    """What a text says about the item's condition: kinds of flaw ("scratch",
    "crack", "fault", "damage"...) and how good it calls it ("good",
    "excellent", "flawless"). "No scratches" says neither."""
    text = ATTITUDE.sub(" fine with ", re.sub(r"[’‘ʼ]", "'", text))
    claims = promises_in(text)
    said = {kind for kind in MARKS if "yes" in claims.get(kind, set())}
    said |= {key.split()[0] for key, saids in claims.items() if key.split()[0] in LEVELS and "yes" in saids}
    if has_fault(text):
        said.add("fault")
    if unnegated(DAMAGE, text):
        said.add("damage")
    if unnegated(GOOD, text):
        said.add("good")
    return said


# ── reading the listing ─────────────────────────────────────────────────────

def quote(part, kinds):
    """The seller's own words for one part of the listing. A long part is cut
    to the few words around what it says: "...battery health 86% small crack
    on the back camera lens" -> "small crack on the back camera lens"."""
    tokens = part.split()
    if len(tokens) > MAX_QUOTE:
        says = lambda start, end: condition_said(" ".join(tokens[start:end])) & kinds
        end = next(e for e in range(1, len(tokens) + 1) if says(0, e))
        start = max(0, next(s for s in range(end - 1, -1, -1) if says(s, end)) - 1)
        tokens = tokens[start:start + MAX_QUOTE]
    return " ".join(tokens).strip(" *-–—:")


def read_listing(text):
    """What the listing says about the item's condition, in the seller's own
    words: {"flaws": ["Broken back"], "good": [], "priced_in": False}. A part
    with a flaw is a flaw even when it also praises: "good condition apart
    from a scratch"."""
    text = re.sub(r"\bcondition\s*[:\-–—]\s*", "condition ", text, flags=re.IGNORECASE)  # "Condition: good"
    found = {"flaws": [], "good": [], "priced_in": bool(PRICED_IN.search(" ".join(words(text))))}
    for part in LISTING_PARTS.split(text):
        said = condition_said(part)
        if said & FLAWS:
            found["flaws"].append(quote(part, said & FLAWS))
        elif said & set(GOOD_LEVELS):
            found["good"].append(quote(part, said & set(GOOD_LEVELS)))
    return found


def point_for(kind, text):
    """What's worth saying with this kind of offer, read from the listing
    (title and description), or None: {"about": "flaw" or "condition",
    "says": up to two parts of the listing, in the seller's words}."""
    read = read_listing(text)
    if read["flaws"] and (kind == "asking" or (kind == "lower" and not read["priced_in"])):
        about, says = "flaw", read["flaws"]
    elif kind == "more" and read["good"] and not read["flaws"]:
        about, says = "condition", read["good"]
    else:
        return None
    return {"about": about, "says": list({s.lower(): s for s in says}.values())[:2]}  # the same words once


def quoted(point):
    """'"Broken back" and "scratch on the screen"'"""
    return " and ".join(f'"{s}"' for s in point["says"])


def question_for(kind, point):
    """What the app asks you when a draft leaves the point out."""
    return f"The listing says {quoted(point)}. {ASK[kind]}"


# ── checking a message ──────────────────────────────────────────────────────

def backed(kind, listed):
    """Whether what a listing says backs one thing a message says about the
    condition. A general word backs a particular one: the listing's "marks"
    or "damage" backs "scratches". "Excellent" backs "good", never the other
    way round."""
    if kind in GOOD_LEVELS:
        return any(GOOD_LEVELS.index(level) >= GOOD_LEVELS.index(kind) for level in listed & set(GOOD_LEVELS))
    if kind == "damage":
        return bool(listed & FLAWS)
    if kind in MARKS:
        return bool({kind, "mark", "damage"} & listed) or (kind == "mark" and bool(listed & MARKS))
    return kind in listed


def check_condition_talk(message, listing_text, point, mention, kind="lower"):
    """A message talks about the item's condition only when this draft is
    meant to (there's a point, and it's mentioned), says only what the listing
    does, and then must say the point: at the asking price, that you don't
    mind it. Questions don't count as talking about it: "any scratches?"
    claims nothing. A one-word clause ("Perfect,") isn't about the item."""
    if not isinstance(message, str) or not message.strip():
        return []  # check_message reports that
    message = re.sub(r"[’‘ʼ]", "'", message)
    stated = set().union(*(condition_said(clause) for clause, asks in clauses(message)
                           if not asks and len(words(clause)) > 1))
    point_kinds = condition_said(". ".join(point["says"])) if point else set()
    says_point = any(backed(kind, point_kinds) for kind in condition_said(message))
    problems = []
    if point and mention:
        if not says_point:
            problems.append(f"the message leaves out what the listing says: {quoted(point)}")
        elif kind == "asking" and not DONT_MIND.search(message):
            problems.append(f"the message names {quoted(point)} but doesn't say you don't mind it")
    elif stated or says_point:
        problems.append("the message talks about the condition, but this draft leaves that out")
    unbacked = sorted(kind for kind in stated if not backed(kind, condition_said(listing_text)))
    if unbacked:
        problems.append(f"the message says things about the condition the listing doesn't: {', '.join(unbacked)}")
    return problems
