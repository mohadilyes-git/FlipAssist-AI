"""Reading the seller's listing with AI: its flaws, where to collect, and
whether the seller takes offers, each in the seller's own words.

Sellers describe flaws in endless ways ("black dot on the screen", "hinge is
stiff", "left joycon drifts") that a word list can't keep up with: on 24 test
listings code alone found 10 of 17 flaws, and Gemma and Haiku all 17. But AI
can make things up, so code checks everything it reads, against the
seller's own sentence:

1. Word for word: every quote must be in the listing, capitals, punctuation,
   apostrophes and hyphens aside ("doesnt" is "doesn't"). A flaw it can't
   quote is a flaw it made up.
2. In its sentence, a quote is a flaw only if the seller says something's
   wrong: not "no black spots on the screen" (a reading that quotes a denied
   flaw fails), not "works perfectly", "scratch free" or "doesn't affect use",
   and nothing about the sale ("smoke free home", "buyer pays postage"). One
   flaw per quote: "Scratch on the back, see pics" is "Scratch on the back".
   A one-word quote counts only if code knows the word ("cracked").
3. The flaws code finds by itself always stay: AI can add a flaw, never take
   one away, and a fragment of code's flaw ("Screen" of "Screen cracked")
   doesn't replace it.

"No offers" must be words that say it ("price is firm", "no offers"), in a
listing that says nowhere that it takes offers ("open to offers", "offers
over £400") and doesn't limit it ("no offers under £250"). The pickup is cut
to a place's name ("Collection only, Leeds LS6" -> "Leeds LS6"). Gemma reads
first and Haiku gets one try when Gemma's reading fails a check, as for
drafts (flip.attempts). With no model, or none that passes, the reading is
code's alone.
"""

import re

from flip.attempts import try_models
from flip.catalogue import contains, find_phrase, words
from flip.checks import NEGATIONS, has_fault
from flip.offers import FLAWS, LISTING_PARTS, condition_said, read_listing
from flip.prompts import READING_SCHEMA, reading_prompt

# the listing's parts: its sentences and clauses, and what follows "apart from" or "except"
SPLIT = re.compile(LISTING_PARTS.pattern + r"|\b(?:apart from|except(?: for)?|other than|save for)\b", re.IGNORECASE)
MAX_FLAW = 12  # words: a flaw, not a paragraph
# a part that says nothing is wrong: "no marks", "screen has no scratches", "scratch free", "not a single
# scratch", "never been dropped", "doesn't affect use" (and "doesnt effect use"), "can't see it"
NOTHING_WRONG = re.compile(
    r"\b(?:no|zero|without(?: any)?|free of|never had(?: any)?)\s+(?:\w+\s+){0,3}?(?:marks?|scratch\w*|scuffs?|"
    r"dents?|cracks?|chips?|damage|issues?|problems?|faults?|drift|dead pixels?|pixels?|burn(?:-in)?|wear|signs?|"
    r"lines?|dots?|spots?|ghost\w*|defects?|cosmetic\w*)\b"
    r"|\b(?:scratch|mark|damage|fault|issue|dent|scuff)[- ]free\b"
    r"|\bnot (?:a|one)(?: single)? (?:mark|scratch|scuff|dent|chip|crack)\b"
    r"|\bnever (?:been )?(?:dropped|repaired|opened|damaged|cracked)\b"
    r"|\b(?:doesn'?t|doesnt|does not|won'?t|wont|will not)\s+(?:affect|effect|bother|matter|impact)\b"
    r"|\b(?:can'?t|cannot|can not)\s+(?:see|notice|tell)\b"
    r"|\b(?:not|isn'?t|barely|hardly|not really)\s+(?:noticeable|visible)(?:$|\s+(?:when|unless|in|on|from)\b)"
    r"|\bnothing wrong\b", re.IGNORECASE)
# what only praises the item: "works perfectly", "great condition", the "works" of "cracked but works"
PRAISE = re.compile(r"\b(?:works?|working)\s+(?:perfectly|fine|great|well|100%|as it should)\b|\bfully working\b"
                    r"|\bperfect(?:ly)?\b|\blike new\b|\bmint\b|\bimmaculate\b|\bflawless\b|\bpristine\b"
                    r"|\b(?:very |really )?(?:great|good|excellent|lovely|fab|fantastic|top|decent|nice|brilliant|"
                    r"amazing|superb)\s+(?:condition|nick|shape)\b"
                    r"|\bcondition\s+(?:is\s+)?(?:great|good|excellent|lovely|perfect|mint)\b"
                    r"|\b(?:barely|hardly)\s+used\b|\bwell looked after\b"
                    r"|^(?:fully |still |everything |all )?(?:works?|working)$", re.IGNORECASE)
# ...unless it's denied: "isn't perfect", "doesn't work well"
NOT_PRAISE = re.compile(r"\b(?:not|isn'?t|doesn'?t|don'?t|never)\s+(?:\w+\s+)?$", re.IGNORECASE)
# words left once the praise is gone that still don't say anything's wrong
PRAISE_FILLER = {"it", "its", "is", "in", "and", "the", "a", "very", "really", "so", "overall", "condition", "item",
                 "all", "everything", "still", "fully", "works", "working", "used", "s"}
# a part about the sale, not the item: "smoke free home", "buyer pays postage", "hence the price", "see pics"
SALE = re.compile(r"\b(?:pay|paid|pays|price|priced|buyer|offers?|collection|collect|postage|post|delivery|deliver|"
                  r"courier|cash|smoke|pets?|home|swaps?|trade|ono|ovno|bargain|quick sale|must go|message me|dm|"
                  r"pictured|photos?|pics?|pictures?)\b", re.IGNORECASE)
# "no picture", "no sound": a fault, where "no box" is only a missing extra
FAULT_ABSENCE = re.compile(r"^(?:no|zero)\s+(?:sound|power|picture|signal|display|image|wifi|wi-fi|charge|charging|"
                           r"service|audio|video|bluetooth|network)\b", re.IGNORECASE)
# "no offers" in words that say it...
NO_OFFERS = re.compile(r"\b(?:no offers|price (?:is )?firm|firm (?:on (?:the )?price|price|at £?\d+)|"
                       r"not (?:open to|accepting|taking|interested in) (?:any )?offers|offers not accepted|"
                       r"no haggl\w*|non[- ]?negotiable|not negotiable|won'?t (?:go|accept) (?:any )?(?:lower|less)|"
                       r"no lower|no less|fixed price|price is fixed)\b|£\s?\d+\s+firm\b", re.IGNORECASE)
# ...never in a listing that takes offers...
TAKES_OFFERS = re.compile(r"\b(?:open to(?: \w+)? offers?|offers? (?:welcome|considered|accepted|over|above|in the "
                          r"region)|or (?:best |nearest )?offers?|o\.?v?\.?n\.?o\b|best offer|(?:consider|take|accept)"
                          r"(?:s|ing)? (?:any |all |sensible |reasonable )?offers|taking offers|make (?:me )?an offer|"
                          r"any offers|happy to haggle|haggling (?:welcome|ok)|(?:isn'?t|not) (?:a )?firm|"
                          r"sensible offers?|reasonable offers?|no (?:silly|stupid|daft|cheeky|low ?ball|time ?wasters?)"
                          r"(?: offers?)?)\b", re.IGNORECASE)
# ...or one that only limits them: "no offers under £250", "had no offers"
LIMITED_OFFERS = re.compile(r"\bno offers (?:under|below|less than|over|until|till|before|yet|so far)\b"
                            r"|\b(?:had|got|received|getting|due to) no offers\b", re.IGNORECASE)
# the place in a pickup quote, without the words around it
PLACE_LEAD = re.compile(r"^(?:(?:can\s+)?(?:be\s+)?(?:collection|collect(?:ed)?|pick\s?up|pickup|meet(?:\s+up)?|based|"
                        r"located|situated|i'?m|i\s+am|local)(?:\s+(?:only|is|from|in|near|at|around|to))*\s*[,:\-–]?\s*"
                        r"|(?:from|in|near|at|around|the)\s+)+", re.IGNORECASE)
PLACE_END = re.compile(r"\s*(?:[.!?;\n]|\s[-–—]\s|,|\bor\b|\bif\b|\bonly\b|\bplease\b|\band\b).*$", re.IGNORECASE)
NOT_A_PLACE = {"collect", "collection", "collected", "pick", "pickup", "post", "postage", "posted", "cash", "me", "i'm",
               "im", "i", "you", "your", "can", "local", "locally", "home", "house", "address", "delivery", "courier",
               "halfway", "anywhere", "today", "tonight", "tomorrow", "weekend", "weekends", "evening", "evenings",
               "morning", "mornings", "afternoon", "asap", "monday", "tuesday", "wednesday", "thursday", "friday",
               "saturday", "sunday", "weekday", "weekdays", "please", "text", "message", "call", "dm", "free",
               "available", "only"}
POSTCODE = re.compile(r"[A-Z]{1,2}\d[A-Z\d]?(?:\s*\d[A-Z]{2})?")
MAX_PLACE = 6  # words: a place's name, not a sentence


def plain_words(text):
    """The words of a text with apostrophes and hyphens inside words taken
    out, so "doesn't" and "doesnt", "Joy-Con" and "joycon" are the same."""
    return words(re.sub(r"(?<=\w)['’‘ʼ\-–](?=\w)", "", text))


def in_listing(quote, text):
    """Rule 1: the quote is in the text word for word, capitals, punctuation,
    apostrophes and hyphens aside."""
    quoted = plain_words(quote)
    return bool(quoted) and contains(plain_words(text), quoted)


def parts_of(text):
    """The listing's sentences and clauses, cut also at "apart from" and
    "except", without bullets: "✅ No scratches" is "No scratches"."""
    found = (part.strip(" .,;:!*•-–—✅❌✔✖☑✔✖") for part in SPLIT.split(text) if part)
    return [part for part in found if part]


def only_praise(part):
    """Whether all a part says is that the item's fine: "great condition",
    "works perfectly", "mint", but not "isn't perfect"."""
    praised = [m for m in PRAISE.finditer(part) if not NOT_PRAISE.search(part[:m.start()])]
    if not praised:
        return False
    rest = part
    for m in reversed(praised):
        rest = rest[:m.start()] + " " + rest[m.end():]
    return not set(words(rest)) - PRAISE_FILLER


def code_knows(part):
    """Whether code reads a flaw in a part by itself: "cracked", "dent", "faulty"."""
    return bool(condition_said(part) & FLAWS) or has_fault(part)


def judge(piece, text):
    """Rule 2 for one piece of a flaw quote, in the listing part it came
    from: "flaw", "denied" (the seller says it isn't so) or "no" (not a flaw:
    praise, the sale, a missing extra, one word code doesn't know, too long)."""
    piece_words = plain_words(piece)
    found = [part for part in parts_of(text) if contains(plain_words(part), piece_words)]
    if not found or not piece_words:
        return "no"
    part = found[0]
    part_words = plain_words(part)
    before = part_words[:find_phrase(part_words, piece_words)[0]]
    if set(before) & (NEGATIONS | {"zero"}) or NOTHING_WRONG.search(part):
        return "denied"
    if only_praise(part) or SALE.search(part) or len(piece_words) > MAX_FLAW:
        return "no"
    if re.match(r"(?:no|without|missing)\b", part, re.IGNORECASE) and not FAULT_ABSENCE.match(part):
        return "no"  # "no box": a missing extra isn't the item's condition
    if len(piece_words) == 1 and not code_knows(piece):
        return "no"  # "screen" alone says nothing's wrong
    return "flaw"


def flaws_in(quote, text):
    """Rule 2 for one quote: its first piece that says something's wrong, plus
    any later piece code reads as a flaw by itself ("Cracked back, scratched
    screen"). Asides like "see pics" or "(top right)" aren't flaws."""
    kept = []
    for piece in parts_of(quote):
        if judge(piece, text) == "flaw" and (not kept or code_knows(piece)):
            kept.append(piece)
    return kept


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
    denied = [q for q in answer["flaws"] if q.strip() and in_listing(q, text) and not flaws_in(q, text)
              and any(judge(piece, text) == "denied" for piece in parts_of(q))]  # "no stick drift" as a flaw
    if denied:
        problems.append(f"the reading gives as flaws what the seller says isn't so: {', '.join(map(repr, denied))}")
    said = answer["no_offers"].strip()
    if said and not no_offers_ok(said, text):
        problems.append(f"\"{said}\" doesn't say the seller won't take offers")
    return problems


def code_no_offers(text):
    """"No offers" as code reads it: the whole part that says it, if it checks out."""
    return next((part for part in parts_of(text) if NO_OFFERS.search(part) and no_offers_ok(part, text)), "")


def code_reading(text):
    """The listing read by code alone: its own flaw words, and "no offers" in
    the usual words. No pickup place: that takes reading."""
    return {"flaws": read_listing(text)["flaws"], "pickup": "", "no_offers": code_no_offers(text), "read_by": "code"}


def place(quote):
    """The place's name in a pickup quote, or "" if there's none: "Collection
    only, Leeds LS6" -> "Leeds LS6", "collection from leeds" -> "Leeds".
    Not a day, a way of buying ("cash on collection") or a sentence."""
    found = re.sub(r"^[^A-Za-z0-9]+", "", quote.replace("(", " ").replace(")", " ").strip())
    found = PLACE_END.sub("", PLACE_LEAD.sub("", found)).strip(" .,;:!-–")
    if not found or len(found.split()) > MAX_PLACE:
        return ""
    if {w.lower().strip("'’") for w in found.split()} & NOT_A_PLACE:
        return ""
    if found[:1].isupper() or found[:1].isdigit() or POSTCODE.fullmatch(found.upper()):
        return found
    return found.title() if found.isalpha() else ""  # "leeds"


def reading_from(answer, text, read_by):
    """A model's reading that passed check_reading, with rules 2 and 3 applied."""
    flaws = [piece for quote in answer["flaws"] for piece in flaws_in(quote, text)]
    for flaw in read_listing(text)["flaws"]:  # rule 3: AI adds flaws, never takes one away
        flaws = [f for f in flaws if not contains(plain_words(flaw), plain_words(f))]  # code's whole flaw, not a piece
        if not any(contains(plain_words(f), plain_words(flaw)) for f in flaws):
            flaws.append(flaw)
    pickup = place(answer["pickup"])
    said = answer["no_offers"].strip()
    return {"flaws": list({f.lower(): f for f in flaws}.values()),  # the same words once
            "pickup": pickup if pickup and in_listing(pickup, text) else "",
            "no_offers": said if said and no_offers_ok(said, text) else code_no_offers(text), "read_by": read_by}


def read_listing_with_ai(listing, local=None, api=None, mode="auto", log=None):
    """The listing (title and description) read by AI and checked by code, or
    by code alone when no model's reading passes. Returns the reading
    ({"flaws", "pickup", "no_offers", "read_by"}) with the attempts made and
    the reasons for falling back, as a draft does."""
    text = f"{listing.get('title') or ''}. {listing.get('description') or ''}"
    result = {"item_id": listing.get("id"), "reasons": [], "attempts": []}
    system, user = reading_prompt(listing)
    answer = try_models(mode, {"local": local, "api": api},
                        ask=lambda ai: ai.ask(system, user, [], READING_SCHEMA),
                        check=lambda found: check_reading(found, text), result=result, log=log)
    reading = code_reading(text) if answer is None else reading_from(answer, text, result["attempts"][-1]["model"])
    return {**reading, "attempts": result["attempts"], "reasons": result["reasons"]}
