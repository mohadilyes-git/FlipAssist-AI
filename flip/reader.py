"""Reading the seller's listing with AI: its flaws, where to collect, and
whether the seller takes offers, each in the seller's own words.

Sellers describe flaws in endless ways ("black dot on the screen", "hinge is
stiff", "left joycon drifts") that a word list can't keep up with: on 24 test
listings code alone found 10 of 17 flaws, and Gemma and Haiku all 17. But AI
can make things up, so code checks everything it reads:

1. Word for word: every quote must be in the listing, capitals, punctuation,
   apostrophes and hyphens aside ("doesnt" is "doesn't", "Joy-Con" is
   "Joy Con"). A flaw it can't quote is a flaw it made up.
2. A flaw says something is wrong in so many words (flip.checks.PROBLEM:
   "crack", "dot", "stiff", "drifts", "not working"...), and the seller
   doesn't deny it in the same clause ("no black spots", "there aren't any
   dots", "free of screen burn", "screen burn: none"). A reading that gives a
   denied flaw fails. What doesn't say anything's wrong ("battery health 90%",
   "unlocked to all networks", "see pics", "screen is perfect") isn't a flaw,
   and a seller's own story is cut to the flaw ("I dropped it and cracked the
   back" -> "cracked the back").
3. The flaws code finds by itself are judged the same way and always stay:
   AI can add a flaw, never take one away. When the AI quotes the flaw more
   precisely ("cracked back" in "Good condition apart from cracked back"),
   its words are kept; when code's part says more ("Cracked back and
   scratched screen" for "scratched screen"), code's are.

"No offers" must be words that say it ("price is firm", "no offers", "price:
firm"), in a listing that doesn't take offers ("open to offers", "offers over
£400") and doesn't only limit them ("no offers under £250"). The pickup is
cut to a place's name ("Collection only, Leeds LS6" -> "Leeds LS6"), never a
day, a time or a way of buying. Gemma reads first and Haiku gets one try when
Gemma's reading fails a check, as for drafts (flip.attempts). With no model,
or none that passes, the reading is code's alone.
"""

import re

from flip.attempts import try_models
from flip.catalogue import contains, find_phrase, words
from flip.checks import NEGATIONS, PROBLEM
from flip.offers import LISTING_PARTS, read_listing
from flip.prompts import READING_SCHEMA, READING_SYSTEM, reading_prompt

# the listing's parts: its sentences and clauses, and what follows "apart from" or "except"
SPLIT = re.compile(LISTING_PARTS.pattern + r"|\b(?:apart from|except(?: for)?|other than|save for)\b", re.IGNORECASE)
# where a clause starts, for whether a "no" before a flaw belongs to it: "No charger and the hinge is stiff"
CLAUSE_WORDS = {"and", "but", "plus", "as", "because", "since", "though", "although", "however", "whereas", "while",
                "which"}
MAX_FLAW = 12  # words: a flaw, not a paragraph
MAX_BEFORE = 6  # words back a "no" can still deny a flaw
# a denial, its apostrophe gone the way plain_words takes it out: "arent", "doesnt", "free (of)"
NEGATORS = NEGATIONS | {"zero", "free", "arent", "isnt", "doesnt", "hasnt", "havent", "dont", "wont", "cant", "wasnt",
                        "werent", "didnt", "never", "none", "nothing", "nor"}
DENIED_AFTER = {"none", "no", "nil", "na", "nope"}  # "Screen burn: none"
# a seller's own story, cut to the flaw: "I dropped it and cracked the back"
FIRST_PERSON = re.compile(r"\b(?:I|I'?ve|I'?m|I'?d|[Mm]y|[Mm]ine|[Ww]e|[Ww]e'?ve|[Oo]ur)\b")
# "no offers" in words that say it...
NO_OFFERS = re.compile(r"\b(?:no offers|price\s*[:\-]?\s*(?:is\s+)?firm|firm (?:on (?:the )?price|price|at £?\d+)|"
                       r"not (?:open to|accepting|taking|interested in) (?:any )?offers|offers not accepted|"
                       r"offers\s*[:\-]\s*no\b|no swaps (?:or|and|/) offers|no haggl\w*|non[- ]?negotiable|"
                       r"(?:isn'?t|is not|not) negotiable|won'?t (?:go|accept) (?:any )?(?:lower|less)|no lower|"
                       r"no less|fixed price|price is fixed)\b|£\s?\d+\s+firm\b", re.IGNORECASE)
# ...never in a listing that takes offers...
TAKES_OFFERS = re.compile(r"\b(?:open to(?: \w+)? offers?|offers? (?:welcome|considered|accepted|over|above|in the "
                          r"region)|\d\s*or (?:best |nearest )?offers?|o\.?v?\.?n\.?o\b|or nearest offer|best offer|"
                          r"(?:consider|take|accept)"
                          r"(?:s|ing)? (?:any |all |sensible |reasonable )?offers|taking offers|make (?:me )?an offer|"
                          r"any (?:reasonable |sensible )?offers (?:considered|welcome|accepted)|any offers\?|"
                          r"happy to haggle|haggling (?:welcome|ok)|(?:isn'?t|not) (?:a )?firm|sensible offers?|"
                          r"reasonable offers?|no (?:silly|stupid|daft|cheeky|low ?ball) offers?)", re.IGNORECASE)
# ...or one that only limits them: "no offers under £250", "had no offers"
LIMITED_OFFERS = re.compile(r"\bno offers (?:under|below|less than|over|until|till|before|yet|so far)\b"
                            r"|\b(?:had|got|received|getting|due to) no offers\b", re.IGNORECASE)
# the place in a pickup quote, without the words around it
PLACE_LEAD = re.compile(r"^(?:(?:can\s+)?(?:be\s+)?(?:collection|collect(?:ed)?|pick\s?up|pickup|meet(?:\s+up)?|based|"
                        r"located|situated|i'?m|i\s+am|local)(?:\s+(?:only|is|from|in|near|at|around|to))*\s*[,:\-–]?\s*"
                        r"|(?:from|in|near|at|around|the)\s+)+", re.IGNORECASE)
PLACE_END = re.compile(r"\s*(?:[.!?;\n]|\s[-–—]\s|,|\b(?:or|if|only|please|and|after|before|between|until|till|"
                       r"weekdays?|weekends?|evenings?|mornings?|afternoons?)\b|\d{1,2}(?::\d\d)?\s*(?:am|pm)\b).*$",
                       re.IGNORECASE)
NOT_A_PLACE = {"collect", "collection", "collected", "pick", "pickup", "post", "postage", "posted", "cash", "me", "i'm",
               "im", "i", "you", "your", "can", "local", "locally", "home", "house", "address", "delivery", "courier",
               "halfway", "anywhere", "today", "tonight", "tomorrow", "weekend", "weekends", "evening", "evenings",
               "morning", "mornings", "afternoon", "asap", "monday", "tuesday", "wednesday", "thursday", "friday",
               "saturday", "sunday", "mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri", "sat", "sun",
               "weekday", "weekdays", "please", "text", "message", "call", "dm", "free", "available", "only", "none",
               "no", "n/a", "na", "unknown", "null", "nil", "stated", "specified", "person", "mine", "work", "office",
               "preferred", "anytime", "essential", "needed", "required", "possible", "welcome", "pm", "am"}
POSTCODE = re.compile(r"[A-Z]{1,2}\d[A-Z\d]?(?:\s*\d[A-Z]{2})?")
MAX_PLACE = 6  # words: a place's name, not a sentence


def plain_words(text):
    """The words of a text with apostrophes and hyphens inside words taken
    out, so "doesn't" and "doesnt", "Joy-Con" and "joycon" are the same."""
    return words(re.sub(r"(?<=\w)['’‘ʼ\-–](?=\w)", "", text))


def in_listing(quote, text):
    """Rule 1: the quote is in the text word for word, capitals, punctuation,
    apostrophes and hyphens aside: a hyphen counts as nothing ("joycon") or
    as a space ("Stoke on Trent")."""
    for split in (plain_words, words):
        quoted = split(quote)
        if quoted and contains(split(text), quoted):
            return True
    return False


def parts_of(text):
    """The listing's sentences and clauses, cut also at "apart from" and
    "except", without bullets: "✅ No scratches" is "No scratches"."""
    found = (part.strip(" .,;:!*•-–—✅❌✔✖☑✔✖") for part in SPLIT.split(text) if part)
    return [part for part in found if part]


def judge(piece, text):
    """Rule 2 for one piece of a flaw quote: "flaw", "denied" (the seller
    says it isn't so) or "no" (it doesn't say anything's wrong, or isn't in
    the listing as one part)."""
    piece_words = plain_words(piece)
    problem = PROBLEM.search(piece)
    if not piece_words or not problem or len(piece_words) > MAX_FLAW:
        return "no"
    part = next((p for p in parts_of(text) if contains(plain_words(p), piece_words)), None)
    if part is None:
        return "no"
    part_words = plain_words(part)
    at = find_phrase(part_words, piece_words)[0]
    # the words of its own clause before it in the listing, then the quote's own words before the problem word
    head = " ".join(part_words[:at]).replace("no longer", " ").split()  # "no longer needed" denies nothing here
    starts = [i for i, w in enumerate(head) if w in CLAUSE_WORDS]
    before = head[starts[-1] + 1:] if starts else head
    own = plain_words(piece[:problem.start()])  # "Hinge isn't loose": the quote's own words before the problem
    after = part_words[at + len(piece_words):at + len(piece_words) + 2]
    # "scratch free", "scratch-free screen": free of it
    following = (plain_words(piece[problem.end():]) + after)[:1]
    if set(before[-MAX_BEFORE:]) & NEGATORS or set(own) & NEGATORS or set(after) & DENIED_AFTER or following == ["free"]:
        return "denied"
    return "flaw"


def trimmed(flaw):
    """A seller's own story cut to the flaw: "I dropped it and cracked the
    back" -> "cracked the back". Anything else stays as it is."""
    if not FIRST_PERSON.search(flaw):
        return flaw
    problem = PROBLEM.search(flaw)
    return flaw[problem.start():].strip() if problem else flaw


def flaws_in(quote, text):
    """Rule 2 for one quote: each of its pieces that says something's wrong,
    in the seller's words. Asides ("see pics", "(top right)") and facts
    ("battery health 88%") aren't flaws."""
    return [trimmed(piece) for piece in parts_of(quote) if judge(piece, text) == "flaw"]


def takes_offers(text):
    """Whether a listing says it takes offers ("open to offers", "offers over
    £400"); "not accepting offers" doesn't."""
    return any(not re.search(r"\b(?:not|no|never|won'?t|don'?t|doesn'?t|isn'?t)\s+$", text[:m.start()], re.IGNORECASE)
               for m in TAKES_OFFERS.finditer(text))


def no_offers_ok(quote, text):
    """Whether the seller's words really say no offers, in a listing that
    says nowhere that it takes them and doesn't only limit them."""
    return bool(NO_OFFERS.search(quote)) and not takes_offers(text) and not LIMITED_OFFERS.search(text)


def check_reading(answer, text):
    """What's wrong with a model's reading of the listing text: anything it
    quotes that isn't there (rule 1), a flaw the seller denies, and "no
    offers" in words that don't say it. A reading that fails goes to the next model."""
    fields_ok = isinstance(answer, dict) and isinstance(answer.get("flaws"), list) and \
        all(isinstance(f, str) for f in answer["flaws"]) and \
        isinstance(answer.get("pickup"), str) and isinstance(answer.get("no_offers"), str)
    if not fields_ok:
        return ["the reading isn't in the agreed shape"]
    problems = []
    made_up = [q for q in [*answer["flaws"], answer["pickup"], answer["no_offers"]]
               if q.strip() and not in_listing(q, text)]
    if made_up:
        problems.append(f"the reading quotes words that aren't in the listing: {', '.join(map(repr, made_up))}")
    said_not = [q for q in answer["flaws"] if denied(q, text)]  # "no stick drift" as a flaw
    if said_not:
        problems.append(f"the reading gives as flaws what the seller says isn't so: {', '.join(map(repr, said_not))}")
    said = answer["no_offers"].strip()
    if said and not no_offers_ok(said, text):
        problems.append(f"\"{said}\" doesn't say the seller won't take offers")
    return problems


def code_no_offers(text):
    """"No offers" as code reads it: the whole part that says it, if it checks out."""
    return next((part for part in parts_of(text) if NO_OFFERS.search(part) and no_offers_ok(part, text)), "")


def code_flaws(text):
    """The flaws code reads by itself (flip.offers.read_listing), judged by
    rule 2 too: code's own reading of "no screen burn or dead pixels" isn't a flaw."""
    return [trimmed(flaw) for flaw in read_listing(text)["flaws"] if judge(flaw, text) == "flaw"]


def code_reading(text):
    """The listing read by code alone: its own flaw words, and "no offers" in
    the usual words. No pickup place: that takes reading."""
    return {"flaws": code_flaws(text), "pickup": "", "no_offers": code_no_offers(text), "read_by": "code"}


def place(quote):
    """The place's name in a pickup quote, or "" if there's none: "Collection
    only, Leeds LS6" -> "Leeds LS6", "collection from leeds" -> "Leeds". Not
    a day or a time, a way of buying ("cash on collection") or a sentence."""
    found = re.sub(r"^[^A-Za-z0-9]+", "", quote.replace("(", " ").replace(")", " ").strip())
    found = PLACE_END.sub("", PLACE_LEAD.sub("", found)).strip(" .,;:!-–")
    if not found or len(found.split()) > MAX_PLACE:
        return ""
    pieces = {w.lower().strip("'’") for w in re.split(r"[\s/\-–]+", found)} | {found.lower()}
    if pieces & NOT_A_PLACE or re.search(r"\d\s*(?:am|pm)", found, re.IGNORECASE):
        return ""
    if found[:1].isupper() or found[:1].isdigit() or POSTCODE.fullmatch(found.upper()):
        return found
    # a lowercase name only right after "from", "in", "near" or "at": "collection from leeds"
    named = re.search(rf"\b(?:from|in|near|at)\s+{re.escape(found)}\b", quote, re.IGNORECASE)
    return found.title() if named and found.replace(" ", "").isalpha() else ""


def reading_from(answer, text, read_by):
    """A model's reading that passed check_reading, with rules 2 and 3 applied."""
    flaws = [piece for quote in answer["flaws"] for piece in flaws_in(quote, text)]
    for flaw in code_flaws(text):  # rule 3: AI adds flaws, never takes one away
        if any(contains(plain_words(f), plain_words(flaw)) for f in flaws):
            continue  # the AI already has all of it
        inside = [f for f in flaws if contains(plain_words(flaw), plain_words(f))]
        said = " ".join(inside)
        if inside and all(PROBLEM.search(said) and m.group().lower() in said.lower() for m in PROBLEM.finditer(flaw)):
            continue  # the AI's quote is the precise part of it: "cracked back", not "Good condition apart from..."
        flaws = [f for f in flaws if f not in inside] + [flaw]
    pickup = place(answer["pickup"])
    said = answer["no_offers"].strip()
    return {"flaws": list({f.lower(): f for f in flaws}.values()),  # the same words once
            "pickup": pickup if pickup and in_listing(pickup, text) else "",
            "no_offers": said if said and no_offers_ok(said, text) else code_no_offers(text), "read_by": read_by}


def denied(quote, text):
    """A flaw the seller says isn't so: "no scratches", "no stick drift"."""
    return bool(quote.strip()) and in_listing(quote, text) and not flaws_in(quote, text) \
        and any(judge(piece, text) == "denied" for piece in parts_of(quote))


def tidied(reply, text):
    """A reading without what code can tell for sure is no flaw of the listing's:
    1. what the model copied from its own instructions rather than the listing:
       "each fault, damage, mark or sign of wear the listing mentions" as a
       flaw, the example "Leeds LS6" as the pickup place;
    2. a flaw the seller says isn't so: "no scratches" (a small model lists
       every condition word it sees).
    Each is dropped and the rest is checked as usual: failing the whole
    reading for it paid the API to read the listing again. A quote that's in
    the listing too stays; anything else wrong still fails the reading."""
    answer = reply.answer
    echo = lambda quote: isinstance(quote, str) and bool(quote.strip()) and in_listing(quote, READING_SYSTEM) \
        and not in_listing(quote, text)
    if isinstance(answer, dict):
        if isinstance(answer.get("flaws"), list):
            answer = {**answer, "flaws": [f for f in answer["flaws"]
                                          if not echo(f) and not (isinstance(f, str) and denied(f, text))]}
        answer = {**answer, **{key: "" for key in ("pickup", "no_offers") if echo(answer.get(key))}}
        reply.answer = answer
    return reply


def read_listing_with_ai(listing, local=None, api=None, mode="auto", log=None):
    """The listing (title and description) read by AI and checked by code, or
    by code alone when no model's reading passes. Returns the reading
    ({"flaws", "pickup", "no_offers", "read_by"}) with the attempts made and
    the reasons for falling back, as a draft does."""
    text = f"{listing.get('title') or ''}. {listing.get('description') or ''}"
    result = {"item_id": listing.get("id"), "reasons": [], "attempts": []}
    system, user = reading_prompt(listing)
    answer = try_models(mode, {"local": local, "api": api},
                        ask=lambda ai: tidied(ai.ask(system, user, [], READING_SCHEMA), text),
                        check=lambda found: check_reading(found, text), result=result, log=log)
    reading = code_reading(text) if answer is None else reading_from(answer, text, result["attempts"][-1]["model"])
    return {**reading, "attempts": result["attempts"], "reasons": result["reasons"]}
