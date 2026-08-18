"""Writing an offer message with no AI: your own sentences (the phrasebook
in your style card), the price code set, the listing's flaw or good condition
in the seller's words, and the questions the listing leaves open.

In a blind test on 18 Aug 2026 (252 drafts, 3 judges each) this beat the AI
drafter for a reseller with no past messages (judged best 97% of the time)
and for one whose messages repeat (88%). For a chatty reseller whose
messages all differ it was a coin flip, so the AI writes for them
(flip.message_drafter decides). Nothing here can make anything up: every
word is yours, the seller's or one of the fixed phrases below, and it never
offers to collect unless your own messages do. When the seller's words
don't fit a sentence it knows how to write ("I dropped it and cracked the
back"), it writes nothing and the AI gets its turn.
"""

import re

from flip.checks import ASKS_YOU, SIGN_OFF, ends_asking
from flip.prompts import offer_words
from flip.style import opening

# the offer in plain words, for when your messages have no habit for it
NEUTRAL = {"lower": "would you take £[OFFER] for it?", "asking": "I can pay £[OFFER] for it.",
           "more": "I can pay £[OFFER] for it."}
GREETING, THANKS = "Hi", "Thanks."
FILLER = "Let me know what you think."
MAX_FLAW = 12  # words of the seller's to say back
# a flaw quoted from the listing that starts with a verb goes after "that it": "that it doesn't charge"
VERB_START = re.compile(r"^(?:has|have|had|is|isn'?t|was|wasn'?t|does|doesn'?t|did|didn'?t|won'?t|can'?t|cannot|"
                        r"needs?|got|comes|works|turns|only)\b", re.IGNORECASE)
ARTICLE = re.compile(r"^(?:a|an|some|the|one|two|2)\b", re.IGNORECASE)
# ...and one with a verb in it goes after "that the": "that the left joycon drifts", "that the hinge is stiff"
VERB_INSIDE = re.compile(r"\b(?:is|are|was|were|has|have|doesn'?t|don'?t|won'?t|can'?t|needs?|keeps|drifts|"
                         r"crackles|rattles|flickers|sticks|buzzes|squeaks|wobbles|lags|freezes|overheats|drains)\b",
                         re.IGNORECASE)
# "It's cracked", "There's a crack": the subject the sentence gets from the seller
SUBJECT = re.compile(r"^(?:(it'?s|it is)|(it has|it'?s got|has got)|(there'?s|there is|there are))\s+", re.IGNORECASE)
# a seller's own story ("I dropped it", "my son cracked it") isn't yours to say
FIRST_PERSON = re.compile(r"\b(?:i|i'?ve|i'?m|i'?d|my|me|mine|we|we'?ve|our|us)\b", re.IGNORECASE)
SPARES = re.compile(r"\b(?:spares|repairs|for parts)\b", re.IGNORECASE)
NEGATED = re.compile(r"\b(?:not|no|never|isn'?t)\b", re.IGNORECASE)
NO_FAULT = re.compile(r"^no\s+(?:sound|power|picture|signal|display|image|wifi|charge|charging|service|audio|video)\b",
                      re.IGNORECASE)
# good condition in a shape this can say: "as it's in excellent condition"
GOOD_CONDITION = re.compile(r"\b((?:very |really )?(?:good|great|excellent|mint|perfect|lovely|immaculate|flawless|"
                            r"pristine|fab|fantastic|brilliant|top|decent|nice|amazing|superb|like new))\s+"
                            r"(?:condition|nick|shape)\b"
                            r"|\bcondition\s*(?:is\s*|:\s*)?(?:very |really )?(good|great|excellent|mint|perfect|"
                            r"lovely|immaculate|flawless|pristine)\b", re.IGNORECASE)
GOOD_AS_IS = re.compile(r"^(?:barely|hardly) used$|^well looked after$|^not a (?:mark|scratch) on it$", re.IGNORECASE)
# for an offer at or over asking, nothing that calls it low: "I know it's a bit cheeky"
LOWBALL = re.compile(r"\b(?:cheeky|lowball|low ball|low offer|lowest|sorry|under (?:the |your )?asking|go lower|"
                     r"wiggle|cheap|bit low|too low)\b", re.IGNORECASE)
# what may follow the price in "I can pay £X ...": nothing else from a question makes sense there
SAFE_TAIL = re.compile(r"^(?:\s*(?:cash(?: on collection| in hand)?|for (?:it|this|them|these)|on collection))?\s*$",
                       re.IGNORECASE)
SENTENCES = re.compile(r"(?<=[.!?])\s+")
EMOJI_END = re.compile("[\U0001F300-\U0001FAFF☀-➿]+$")
QUESTION_FILLER = {"does", "it", "come", "with", "a", "an", "the", "what", "whats", "s", "is", "any", "how", "hows",
                   "are", "all", "included", "or", "and", "original"}


def repeats(card):
    """Whether your messages repeat: you have a habit for how you open and
    how you word the offer. Then this writes them; if not, the AI does."""
    phrases = (card or {}).get("phrases") or {}
    return phrases.get("opener") is not None and phrases.get("offer") is not None


def lower_first(text):
    """'Broken back' -> 'broken back'; 'HDMI port', 'Face ID' and 'I' keep their capitals."""
    first = text.split()
    if not first or re.match(r"I\b|(?:Face|Touch) ID\b", text) or len(first[0]) > 1 and first[0].isupper():
        return text
    return text[:1].lower() + text[1:]


def flaw_phrase(part):
    """One flaw in the seller's words, to go after "given" or "I don't mind":
    'the broken back', 'that it doesn't charge', 'that the hinge is stiff',
    "that it's cracked". None when the words don't fit a sentence: the
    seller's own story ("I dropped it"), a denied fault ("not spares or
    repairs"), or more words than a reason should have."""
    part = part.strip().rstrip(".!")
    if not part or FIRST_PERSON.search(part) or len(part.split()) > MAX_FLAW:
        return None
    if SPARES.search(part):
        return None if NEGATED.search(part) else "that it's sold as spares or repairs"
    subject = SUBJECT.match(part)
    if subject:
        rest = part[subject.end():]
        return f"that it's {rest}" if subject.group(1) else f"that it has {rest}" if subject.group(2) else \
            f"that there's {rest}" if subject.group(3).lower() != "there are" else f"that there are {rest}"
    part = lower_first(part)
    if NO_FAULT.match(part):
        return f"that there's {part}"  # "that there's no picture"
    if re.match(r"not\b", part, re.IGNORECASE):
        return f"that it's {part}"  # "that it's not holding charge"
    if VERB_START.match(part):
        return f"that it {part}"
    if VERB_INSIDE.search(part):
        return f"that {part}" if ARTICLE.match(part) else f"that the {part}"
    if len(part.split()) == 1 and re.search(r"(?:ed|en)$", part):
        return f"that it's {part}"  # "cracked"
    return part if ARTICLE.match(part) else f"the {part}"


def flaw_words(says):
    """The listing's flaws together: 'the broken back and the cracked screen',
    or None if one of them can't be said (flaw_phrase)."""
    phrases = [flaw_phrase(part) for part in says]
    return None if None in phrases else " and ".join(phrases)


def good_words(says):
    """The listing's good condition: "it's in excellent condition" (from
    "Excellent condition", "Phone is in excellent condition" or "Condition:
    Excellent"), "it's barely used". None for words in another shape."""
    part = says[0].strip().rstrip(".!")
    found = GOOD_CONDITION.search(part)
    if found:
        return f"it's in {(found.group(1) or found.group(2)).lower()} condition"
    if GOOD_AS_IS.match(part):
        return f"there's {part.lower()}" if part.lower().startswith("not") else f"it's {part.lower()}"
    return None


def merge_questions(questions):
    """'Does it come with a charger?' + 'Does it come with the box?' -> 'Does it come with a charger and the box?'"""
    start = "Does it come with "
    come = [q for q in questions if q.startswith(start)]
    if len(come) < 2:
        return list(questions)
    joined = start + " and ".join(q[len(start):-1] for q in come) + "?"
    return [joined if q == come[0] else q for q in questions if q not in come[1:]]


def split_sign_off(sentence):
    """A sentence and what comes after its own end: ("Would you take £[OFFER]?", "😊")."""
    sentence = sentence.rstrip()
    core = SIGN_OFF.sub("", sentence).rstrip()
    return core, sentence[len(core):].strip()


def as_statement(sentence):
    """At or over the asking price the offer is said, not asked:
    'Would you take £[OFFER] cash?' -> 'I can pay £[OFFER] cash.' Only a safe
    ending is kept after the price ("cash", "for it"), and the sign-off
    after the sentence: "...£[OFFER]?😊" -> "...£[OFFER]. 😊"."""
    core, sign = split_sign_off(sentence)
    if not ends_asking(core) or "[OFFER]" not in core:
        return sentence
    greeting = opening(core)
    tail = re.sub(r"^\s*(?:quid|pounds)\b", "", core[core.index("[OFFER]") + len("[OFFER]"):].rstrip(" ?"))
    tail = tail if SAFE_TAIL.match(tail) else ""
    return f"{greeting + ', ' if greeting else ''}I can pay £[OFFER]{tail}.{' ' + sign if sign else ''}"


def with_reason(sentence, kind, point):
    """The listing's point in the offer sentence (lower, more) or after it
    (asking), before any sign-off the sentence ends with. None if the
    listing's words can't be said (flaw_words, good_words)."""
    if not point:
        return sentence
    said = good_words(point["says"]) if kind == "more" else flaw_words(point["says"])
    if said is None:
        return None
    core, sign = split_sign_off(sentence)
    tail = f" {sign}" if sign else ""
    end = core[-1] if core[-1:] in (".", "?", "!") else ""
    body = core[:-1] if end else core
    end = end or ("?" if ASKS_YOU.search(core) else ".")
    if kind == "lower":
        return f"{body}, given {said}{end}{tail}"
    if kind == "more":
        return f"{body}, as {said}{end}{tail}"
    return f"{core}{'' if core[-1:] in ('.', '?', '!') else '.'} I don't mind {said}.{tail}"


def join(*parts):
    """Sentences into one message: after a greeting ending in a comma the next
    sentence carries on in lower case; after a full stop it starts with a capital."""
    text = ""
    for part in (p.strip() for p in parts if p and p.strip()):
        if text.endswith(",") and part[:1].isupper() and not re.match(r"I\b", part):
            part = part[:1].lower() + part[1:]
        elif text[-1:] in (".", "?", "!") and part[:1].islower():
            part = part[:1].upper() + part[1:]
        text = f"{text} {part}".strip()
    return text


def greeting_apart(sentence):
    """("Hi mate,", "would you take £185?") from "Hi mate, would you take
    £185?", so anything added goes after the greeting; ("", sentence) when it
    has none, or is nothing but one ("Hi mate!")."""
    greeting = opening(sentence)
    rest = sentence[len(greeting):].lstrip(" ,") if greeting else ""
    return (f"{greeting},", rest) if re.search(r"\w", rest) else ("", sentence)


def collecting_from(closing, pickup):
    """Your own collecting sentence with the place the listing gives:
    'Can collect today.' -> 'Can collect from Leeds LS6 today.' A closing
    that doesn't collect stays as it is: the place goes in only when you say
    you'll collect."""
    if not pickup or not re.search(r"\bcollect\b", closing, re.IGNORECASE):
        return closing
    return re.sub(r"\bcollect\b", f"collect from {pickup}", closing, count=1, flags=re.IGNORECASE)


def fit(opener, middle, closing, at_least, item, already=""):
    """opener + middle (the offer and any questions) + closing. A longer
    message that's still short gets "I'm interested in your <item>.", then
    "Let me know what you think.": the only things it can add without making
    anything up, and never twice (already: what's there)."""
    interest = f"I'm interested in your {item}."
    extras = [([], [])]
    if interest.lower() not in already.lower():
        extras.append(([interest], []))
    if FILLER.lower() not in already.lower():
        extras.append((extras[-1][0], [FILLER]))
    text = ""
    for before, after in extras:
        text = join(opener, *before, *middle, *after, closing)
        if len(text.split()) >= at_least:
            break
    return text


def priced(text, offer):
    return text.replace("£[OFFER]", offer_words(offer)).replace("[OFFER]", f"{offer // 100:,}")


def write_offer(card, kind, offer, point=None, questions=(), at_least=0, item="item", pickup=""):
    """One offer message from your phrasebook (card["phrases"]), or in plain
    words if you have no past messages; None if the listing's point can't be
    said in a sentence this knows (then the AI writes). point: the listing's
    flaw or good condition to give as the reason (flip.offers), only when
    it's to be said. questions: the open ones, for a longer message.
    at_least: the words a longer message needs. item: what to call the item.
    pickup: where the listing says to collect."""
    card = card or {}
    phrases = card.get("phrases") or {}
    opener = phrases.get("opener")
    opener = opener if opener is not None else f"{card.get('greeting') or GREETING},"
    offer_sentence = phrases.get("offer") or NEUTRAL[kind]
    closing = collecting_from(phrases["closing"], pickup) if phrases.get("closing") else "" if card else THANKS
    if kind != "lower":  # at or over asking: said, and never called low
        offer_sentence = as_statement(offer_sentence)
        if LOWBALL.search(offer_sentence):
            offer_sentence = NEUTRAL[kind]
        opener = opener if not LOWBALL.search(opener) else f"{card.get('greeting') or GREETING},"
        closing = closing if not LOWBALL.search(closing) else ""
    if not opener:  # "Hi mate, would you take £185?": anything added goes after "Hi mate,"
        opener, offer_sentence = greeting_apart(offer_sentence)
    reasoned = with_reason(offer_sentence, kind, point)
    if reasoned is None:
        return None
    text = fit(opener, [reasoned, *merge_questions(questions)], closing, at_least, item)
    if card.get("emoji") and phrases.get("emoji") and phrases["emoji"] not in text:
        text = f"{text} {phrases['emoji']}"
    return priced(text, offer)


def asked_already(question, text):
    """Whether a draft already asks this question: its words ("charger",
    "battery health") are in one of the draft's questions."""
    keys = {w for w in re.findall(r"[a-z]+", question.lower()) if w not in QUESTION_FILLER}
    asked = set()
    for sentence in SENTENCES.split(text):
        if ends_asking(sentence):
            asked |= set(re.findall(r"[a-z]+", sentence.lower()))
    return bool(keys) and keys <= asked


def make_longer(previous, questions=(), at_least=0, item="item"):
    """The draft on screen with the open questions it doesn't ask yet, added
    before its closing (a last sentence with no price and no question),
    every word of it kept."""
    sentences = [s.strip() for s in SENTENCES.split(previous.strip()) if s.strip()]
    last = sentences[-1] if sentences else ""
    closing = last if len(sentences) > 1 and "£" not in last and not ends_asking(last) else ""
    body = sentences[:-1] if closing else sentences
    opener, first = greeting_apart(body[0]) if body else ("", "")
    if opener:
        body = [first, *body[1:]]
    elif len(body) > 1:
        opener, body = body[0], body[1:]
    new = [q for q in merge_questions(questions) if not asked_already(q, previous)]
    return fit(opener, [*body, *new], closing, at_least, item, already=previous)
