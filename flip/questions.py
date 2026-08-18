"""Questions a longer message may ask the seller: only what the listing
doesn't already answer.

The questions are data (data/questions.json), by category. Code picks the open
ones, so a longer message says more without making anything up: a question
claims nothing, so it can't put a wrong fact in your mouth.
"""

import json
import re

from flip.catalogue import DATA
from flip.checks import MARKS, PROMISES, REASON, promises_in
from flip.offers import condition_said, read_listing

MAX_QUESTIONS = 3  # a longer message, not a questionnaire
NEGATED_BEFORE = re.compile(r"\b(?:not|no|doesn'?t|don'?t|isn'?t|without|missing|never)\b(?:\s+\S+){0,4}\s*$")
# claims that answer "any marks or scratches?", yes or no: "no scratches" answers it too
CONDITION_ANSWERS = MARKS | {"new", "sealed", "flawless", "excellent"}
# ways a listing answers a question that the checks' claim words don't cover.
# Read on the plain lowercase text: words() would drop the %. A bare "BH" isn't
# enough: it's also a Bournemouth postcode
ALSO_ANSWERS = [
    (re.compile(r"\b(?:bh|health)\s*:?\s*\d{2,3}\s*%|\b\d{2,3}\s*%\s*(?:bh|(?:battery )?health)\b"
                r"|\bmax(?:imum)? capacity\b"), {"battery"}),
    (re.compile(r"\b(?:phone|handset|console|unit|device|buds|earbuds|headphones) only\b|\bnothing else\b"),
     {"charger", "cable", "box", "controller"}),
    (re.compile(r"\b(?:pads?|joypads?|gamepads?)\b"), {"controller"}),
    (re.compile(r"\bwires?\b"), {"cable"}),
    (re.compile(r"\b(?:all|any) networks?\b|\bopen to all\b"), {"unlocked"}),
    # "boxed with all accessories": everything that comes with it is there
    (re.compile(r"\ball (?:the |its |original )?(?:accessories|extras)\b|\bcomes with everything\b"
                r"|\beverything included\b|\bcomplete (?:set|with everything)\b"), {"charger", "cable", "controller"}),
]


def load_questions():
    data = json.loads((DATA / "questions.json").read_text(encoding="utf-8"))
    del data["about"]
    return data


def answered(text, flaws=None):
    """What the listing already answers: the claims the checks read ("box",
    "battery", "unlocked"...), yes or no, plus the other ways listings say
    them ("BH 91%", "console only", "all networks"), and "condition" if it
    says anything about the item's condition. "No box" answers the box
    question too, and "no scratches" the marks question. flaws: the listing's
    flaws as flip.reader read them ("black dot on the screen"), which answer
    the marks question even when code has no word for them."""
    found = set(promises_in(text))
    read = read_listing(text)
    if flaws or condition_said(text) or read["flaws"] or read["good"] or \
            {key.split()[0] for key in found} & CONDITION_ANSWERS:
        found.add("condition")
    for pattern, answers in ALSO_ANSWERS:
        for m in pattern.finditer(text.lower()):
            sentence = re.split(r"[.!?;\n]", text.lower()[:m.start()])[-1]
            if not NEGATED_BEFORE.search(sentence):  # "doesn't come with all the accessories" answers nothing
                found |= answers
    return found


def open_questions(text, category=None, questions=None, flaws=None):
    """The questions the listing doesn't answer, its category's first, at most
    MAX_QUESTIONS. category is the catalogue's ("phones", "consoles"...), or
    None for a listing the catalogue doesn't know: then only the general ones.
    flaws: as for answered()."""
    questions = questions or load_questions()
    done = answered(text, flaws)
    pool = [*questions.get(category, []), *questions["any"]]
    return [q["ask"] for q in pool if not done & set(q["unless"])][:MAX_QUESTIONS]


def check_no_answered_questions(message, text):
    """A message doesn't ask what the listing already says about what comes
    with the item: "Does it come with the box?" on a boxed listing reads as if
    you hadn't read it. Condition and battery questions are left alone: "any
    other marks?" is a fair follow-up."""
    done = answered(text)
    asked = set()
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", message.strip()):
        if sentence.rstrip().endswith("?"):
            question = REASON.split(sentence)[0]  # "would you take £170 as it's boxed?" asks only the first part
            asked |= {key for key in promises_in(question) if key in PROMISES}
    if asked & done:
        return [f"the message asks what the listing already says: {', '.join(sorted(asked & done))}"]
    return []
