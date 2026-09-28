"""Reading the seller's listing with AI: its flaws, where to collect, and
whether the seller takes offers, each in the seller's own words.

Sellers describe flaws in endless ways ("black dot on the screen", "hinge is
stiff", "left joycon drifts") that a word list can't keep up with: on 24 test
listings code alone found 10 of 17 flaws, and Gemma and Haiku all 17. But AI
can make things up, so code checks everything it reads:

1. Word for word: every quote must be in the listing, capitals, punctuation,
   apostrophes and hyphens aside ("doesnt" is "doesn't", "Joy-Con" is
   "Joy Con"). A flaw it can't quote is a flaw it made up. A quote whose
   only difference is the seller's typos put right ("Small scratch" for
   "Small scratich") is put back to the seller's words.
2. A flaw says something is wrong in so many words (flip.checks.PROBLEM:
   "crack", "dot", "stiff", "drifts", "not working"...), and the seller
   doesn't deny it in the same clause ("no black spots", "there aren't any
   dots", "free of screen burn", "screen burn: none"). A reading that gives a
   denied flaw fails. What doesn't say anything's wrong ("battery health 90%",
   "unlocked to all networks", "see pics", "screen is perfect") isn't a flaw,
   nor is a mark on the screen protector ("the protector itself is
   scratched"); a battery health of 85% or under is ("Battery health 79%":
   the user's line, read from their labels). A seller's own story is cut to
   the flaw ("I dropped it and cracked the back" -> "cracked the back").
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

FlipAssist's own reader reads in Gemma's place when Ollama has it
(reader_for): flip-reader-5, Gemma 3 4B fine-tuned on 33,160 labelled
listings to quote exactly the sentences that state a flaw. Its reading gets
the safety checks only (reading_checked: rule 1, the denial check, a seller's
story cut to the flaw, the pickup and "no offers" checks), not rules 2 and 3.
On 5,032 listings no model had seen (26 Sep 2026) rules 2 and 3 took the
flaws it found from 96.5% to 89.4% on UK iPhones and from 94.3% to 68.3% on
US and Canadian listings, and it was as good as round 4's reader (95.3% of
3,162 double-checked flaws each, 18 false alarms each).
"""

import json
import os
import re
import urllib.request
from functools import lru_cache

from flip.ai import LocalModel
from flip.attempts import try_models
from flip.catalogue import contains, find_phrase, words
from flip.checks import (CONDITION_PROMISES, ESIM, MARKS, NEGATIONS, NOT_A_FLAW, PROBLEM, answered, denied_by,
                         most_slips, negation_at, slipped, slips)
from flip.offers import (FLAWS, PARTS, backed, battery_apart, condition_said, esim_everywhere, figures_joined,
                         low_battery, read_listing, sentence_parts, this_items_parts)
from flip.prompts import READING_SCHEMA, READING_SYSTEM, reading_prompt

# the listing's parts: its sentences and clauses, and what follows "apart from" or "except"
SPLIT = PARTS
# where a clause starts, for whether a "no" before a flaw belongs to it: "No charger and the hinge is stiff"
CLAUSE_WORDS = {"and", "but", "plus", "as", "because", "since", "though", "although", "however", "whereas", "while",
                "which"}
MAX_FLAW = 15  # words: a flaw, not a paragraph (a sentence about one flaw can run to 15)
MAX_BEFORE = 6  # words back a "no" can still deny a flaw
# FlipAssist's own fine-tuned reader (round 5), when Ollama has it; FLIP_READER_MODEL= (empty) reads with Gemma
READER = os.environ.get("FLIP_READER_MODEL", "flip-reader-5").strip()
# a denial, its apostrophe gone the way plain_words takes it out: "arent", "doesnt", "free (of)"
NEGATORS = NEGATIONS | {"zero", "free", "arent", "isnt", "doesnt", "hasnt", "havent", "dont", "wont", "cant", "wasnt",
                        "werent", "didnt", "never", "none", "nothing", "nor"}
DENIED_AFTER = {"none", "no", "nil", "na", "nope"}  # "Screen burn: none"
# words that make a part a statement of its own, not one more item in a list: "screen has a crack or two"
LIST_BREAKS = {"is", "are", "was", "were", "be", "been", "being", "has", "have", "had", "does", "do", "did", "comes",
               "come", "came", "works", "work", "working", "needs", "need", "got", "gets", "get", "looks", "look",
               "shows", "show", "there", "but", "though", "although", "however", "which", "apart",
               "except", "still", "just", "only"}
# an item that opens with one of these is a thing of its own: "no scratches, a small dent on the back",
# "no cracks, light scratches or scuffs on the back"
ITEM_OPENERS = {"a", "an", "one", "some", "the", "few", "couple", "slight", "small", "minor", "tiny", "light", "faint",
                "hairline", "odd", "little", "deep", "bit"}
# what may come between a "no" and the first thing it denies: "never BEEN dropped", "doesn't HAVE ANY
# scratches", "not A SINGLE scratch", "free FROM scratches", "no VISIBLE scratches"
AFTER_DENIAL = {"been", "had", "have", "has", "got", "any", "a", "an", "single", "one", "even", "ever", "visible",
                "noticeable", "obvious", "major", "signs", "sign", "of", "from", "so", "much"}
# a list with "and" denies its items only when the first is damage itself: "no scratches, scuffs and dents",
# "never dropped, scratched and dented", never "no charger, cracked screen and dents"
DAMAGE_EVENTS = {"dropped", "repaired", "opened", "damaged", "smashed", "water"}
# "or" that doesn't close a list: "a dent or two", "a week or so"
NOT_A_CHOICE = {"two", "three", "so", "2", "3", "more"}
MAX_ITEM = 4  # words of one item in a list: "visible damage", not a sentence
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
# what comes with the item (the user, 23 Sep: a mark on one is no flaw of the item's): a screen or camera protector,
# a phone case or cover, the box, a charger or cable. A mark is the thing's only when it's said OF it ("the protector
# itself is scratched", "case that has a crack"), right BEFORE it ("cracked screen protector") or ON it ("scratches on
# the protector", "damage to the box"): a mark under it, hidden by it, made by it or anywhere else is the item's
PROTECTORS = r"(?:(?:(?:screen|glass|lens|camera|privacy|tempered|back|front|matte|anti-glare) ){0,2}protectors?|" \
             r"tempered glass(?! back)|(?:screen|glass) guards?)(?: (?:on|over) (?:the |my |it(?=\b))?(?:back |front |rear |main " \
             r"|selfie )?(?:screen|camera|cameras|lens|lenses|back|front|display|glass|phone|iphone)?)?"
CASE_KINDS = r"(?:phone|clear|silicone|leather|rubber|protective|wallet|flip|magsafe|otterbox|spigen|carry|carrying|" \
             r"travel|battery|keyring|keychain|hard|soft)"
THINGS_WITH_IT = r"box|boxes|packaging|charger|chargers|charging cable|cable|cables|adapter|adaptor|plug"
WITH_IT = {  # by what the listing sells (its title): earbuds' plain "case" is theirs, a console's "covers" its panels
    "item": rf"(?:{PROTECTORS}|(?:{CASE_KINDS} ){{0,2}}(?:(?<!charging )(?:case|cases)|(?<!back )(?<!rear )(?<!battery )"
            rf"(?<!camera )(?<!glass )covers?)|{THINGS_WITH_IT})",
    "earbuds": rf"(?:{PROTECTORS}|(?:{CASE_KINDS} ){{1,2}}(?:case|cases)|(?:{CASE_KINDS} ){{0,2}}covers?|{THINGS_WITH_IT})",
    "console": rf"(?:{PROTECTORS}|(?:{CASE_KINDS} ){{0,2}}(?:case|cases)|{THINGS_WITH_IT})"}
EARBUDS = re.compile(r"\b(?:air ?pods?|ear ?buds?|buds|earphones|headphones)\b", re.IGNORECASE)
CONSOLES = re.compile(r"\b(?:ps[45]|playstation ?[45]|xbox)\b", re.IGNORECASE)
MARK = r"(?:crack\w*|scratch\w*|scuff\w*|dent\w*|chip(?:s|ped)?|marks?|marked|damage\w*|worn|wear|ripped|rips?|torn|" \
       r"tears?|broken|smash\w*|shatter\w*|peel\w*|lift\w*|bubbl\w*|nicks?|nicked|split|bent|faded|discolou?r\w*|" \
       r"yellow(?:ed|ing)|stain\w*|battered|tatty|tired)"
MARKED = r"(?:cracked|scratched|scuffed|dented|chipped|marked|damaged|worn|ripped|torn|broken|smashed|shattered|" \
         r"peel(?:ing|ed)|lifting|bubbl(?:ing|ed)|nicked|split|bent|faded|discolou?red|yellowed|stained|battered|tatty|tired)"
ITEM_PARTS = r"(?:screen|display|back|rear|frame|housing|camera|cameras|lens|lenses|body|phone|iphone|handset|device|" \
             r"console|joy-?cons?|hinge|controller)"
# what keeps a mark off the thing it's said with: a word for hiding or causing it, or a new clause ("the case HAS LEFT
# a few marks", "screen protector IS HIDING a small crack", "box has a dent AND cracked back glass")
NOT_ITS = r"(?:hid\w*|cover\w*|conceal\w*|over|left|leaves|caused|causes|made|makes|rubbed|rubs|gave|gives|under|" \
          r"underneath|beneath|behind|protect\w*|stop\w*|prevent\w*|keep\w*|saved?|and|but)\b"
# ...and what comes after it: an object ("case SCRATCHED THE edges"), something under it, or the item's own part
AFTER_IT = rf"(?!\s+(?:the|my|its|his|her|their)\b)(?!\s+(?:underneath|beneath|under (?:it|there)|below)\b)" \
           rf"(?!\s+(?:on|to|of|in)\s+(?:the |my |its |a )?{ITEM_PARTS}\b)"
# the seller's own note that a mark is the protector's: "Crack on the screen (protector only)", "- it's only the screen
# protector"
NOTED_AFTER = re.compile(r"^\s*[-–—(,:]?\s*(?:but\s+)?(?:(?:it['’]?s|its|it is|that['’]?s|thats|this is)\s+(?:only\s+|just\s+)?"
                         r"(?:on\s+)?|only\s+(?:on\s+)?)(?:the\s+)?(?:screen\s+|camera\s+|lens\s+|glass\s+)?(?:protector|case|cover)s?\b|"
                         r"^\s*\(\s*(?:the\s+)?(?:screen\s+)?protector\s+only\b", re.IGNORECASE)


@lru_cache(maxsize=8)
def marks_on_it(kind):
    """A mark said of, before or on a thing that comes with the item (WITH_IT[kind]), to be set aside."""
    with_it = WITH_IT[kind]
    marks = rf"{MARK}(?:\s+(?:and|&|or)\s+(?:[\w-]+\s+)?{MARK}(?!\s+(?:[\w-]+\s+)?{ITEM_PARTS}\b))*"
    degree = r"(?:(?:slightly|a bit|bit|badly|lightly|very|quite|really|a little|totally|completely|all|both)\s+)*"
    # a word between a mark and the thing it's on that only describes the thing: "cracked PINK case", not "marked WHERE
    # THE case" or "chip on the EDGE a case"
    gap_word = rf"(?!(?:and|or|where|when|by|from|with|in|on|at|of|to|the|a|an|my|its|his|her|their|under|behind|because|" \
               rf"cos|as|so|that|which|while|if|would|could|will|can|cant|didnt|dont|not|no|{ITEM_PARTS}|edges?|corners?|" \
               rf"sides?|top|bottom)\b)[\w-]+\s+"
    gap = rf"(?:(?!{NOT_ITS})[\w-]+\s+){{0,3}}?"
    its = r"(?:\s+(?:itself|themselves|that|which|it['’]?s|its|it is|they['’]?re|theyre|they are|one(?: of them)? is|" \
          r"both are))?"
    return re.compile(
        rf"\b{with_it}{its}\s+(?:can|could|will|may|might)?\s*(?:easily\s+)?(?:be\s+)?(?:replaced|removed|swapped|changed)\b"
        rf"|\b{with_it}{its}\s+(?:needs?|could do with|requires?)\s+(?:replacing|replaced|changing|a new one|to be replaced)\b"
        rf"|\b{with_it}(?:\s+(?:itself|themselves))?(?:\s+(?:that|which)['’]?s|(?:\s+(?:that|which))?\s+(?:is|are|was|were|"
        rf"has|have|had|has got|have got|got|s|looks?|looking|seems?|appears?))\s+{gap}{marks}\b{AFTER_IT}"
        rf"|\b{with_it}{its}\s+{degree}{MARKED}(?:\s+(?:and|&)\s+{degree}{MARKED})*\b{AFTER_IT}"
        rf"|\b{with_it}\s+(?:is\s+)?(?:easy|easily|simple|quick)\s+to\s+(?:peel|remove|replace|take off|swap)\w*"
        rf"|\b{MARKED}\s+(?:{gap_word}){{0,2}}?{with_it}\b"
        rf"|\b{MARK}\s+(?:(?:is|are|s|only|just|all|both|mostly)\s+){{0,2}}(?:on|to|of|in|across)\s+(?:the |my |its |a |an |"
        rf"his |her |their )?(?:{gap_word}){{0,2}}?{with_it}\b", re.IGNORECASE)


def kind_of_item(text):
    """What the listing sells, by its title, for what comes with it: "earbuds", "console" or "item"."""
    title = re.split(r"\n|(?<=\S)\.\s", text, maxsplit=1)[0]
    return "earbuds" if EARBUDS.search(title) else "console" if CONSOLES.search(title) else "item"


def without_its_things(piece, text):
    """A piece with the marks on what comes with the item blanked out (marks_on_it), so they're no flaw of the item's:
    "Comes with box, box has a small dent" keeps nothing; "Screen protector cracked with a small scratch underneath"
    keeps the scratch."""
    return marks_on_it(kind_of_item(text)).sub(lambda m: " " * len(m.group()), piece)


def its_things_words(part_words, text):
    """Which of a part's words (plain_words) are a mark on what comes with the
    item (marks_on_it), by their place in the part."""
    joined, starts, at = " ".join(part_words), [], 0
    for word in part_words:
        starts.append(at)
        at += len(word) + 1
    spans = [m.span() for m in marks_on_it(kind_of_item(text)).finditer(joined)]
    return {n for n, start in enumerate(starts) if any(a <= start < b for a, b in spans)}


def noted_as_its_things(part, text):
    """Whether the seller says straight after a part that its mark is the protector's: "Crack on the screen
    (protector only)", "Small scratch on the screen - it's on the protector not the actual screen"."""
    at = text.find(part)
    return at >= 0 and bool(NOTED_AFTER.match(text[at + len(part):at + len(part) + 80]))


# a part that goes on about a thing that comes with the item, with nothing of its own but the mark: "Original box,
# slightly damaged", "Screen protector - cracked", "Comes with a case but it's a bit worn", "...protector, easy to peel
# off". Not "it has a crack" (that's the item), and not after a thing that's only where the item was kept ("kept in a
# case, slightly scratched")
NO_SUBJECT = re.compile(rf"^(?:(?:but|although|though|and)\s+)?(?:(?:it['’]?s|its|it is|they['’]?re|theyre|they are|one is|"
                        rf"one of them is|both are|both)\s+)?(?:(?:slightly|a bit|bit|badly|lightly|very|quite|really|a little|"
                        rf"both|all)\s+)*(?:{MARKED}|easy|easily|needs? (?:replacing|replaced|changing|a new one|to be "
                        rf"replaced))\b", re.IGNORECASE)
KEPT_IN = rf"\b(?:kept|always|been|was|lived|stored|put|used|using|use|in|inside|into|under|underneath|beneath|behind|" \
          rf"from|by|caused by|due to|because of|never used|never had|didn['’]?t use|didnt use|not used|no|without)\s+" \
          rf"(?:[\w-]+\s+){{0,3}}?{WITH_IT['item']}\b"
ASIDE = re.compile(r"^(?:see |as (?:seen |shown )?in (?:the )?|check (?:the )?)?(?:pics?|photos?|pictures?|images?)$",
                   re.IGNORECASE)


# a part that only points back at a flaw the listing names elsewhere: "the crack does not affect image quality",
# "price reflects the camera lens damage". Its flaw is the other part's, said there
POINTS_BACK = re.compile(r"\b(?:(?:does|do|did|will|would|should) ?n[o']?t|doesnt|dont|wont|won['’]t|isn['’]?t|aren['’]?t|"
                         r"is not|are not|never) (?:really |at all |in any way )?(?:affect\w*|effect\w*|impact\w*|"
                         r"interfer\w* with)|\b(?:has|have|with|makes?) no (?:effect|impact|difference)\b|\bprice "
                         r"(?:reflects|reflected|takes? (?:\w+ )?into account|allows? for|accounts? for|(?:has been |was )?"
                         r"(?:reduced|lowered|dropped) (?:for|because of|due to))|\bpriced (?:to reflect|accordingly|low|cheap|"
                         r"lower)\b|\breflected in the price|\bhence the (?:low |cheap )?price|\b(?:cheap|cheaper|low price|"
                         r"priced low) (?:because of|due to|for)\b|\b(?:only|purely|just) cosmetic\b", re.IGNORECASE)
# where on the item a flaw is: a pointer that names a place no other flaw names says something new
PLACE_WORDS = re.compile(r"\b(?:screen|display|back|rear|frame|edges?|corners?|sides?|camera|lens|lenses|housing|bezel|port|"
                         r"buttons?|speaker|top|bottom|face id|stick|hinge)\b", re.IGNORECASE)
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


MAX_SKIPPED = 4  # the seller's words a quote can leave out of one sentence: "needs new back screen" from "...front screen and back screen"


def as_written(quote, text):
    """A quote put back to the listing's own words when the model put the
    seller's typos right or left a few of their words out: "Small scratch on
    the corner" for the listing's "Small scratich on the corner", "needs new
    back screen" for "needs new front screen and back screen". The quote's
    words in the same order inside one sentence, each the seller's or a slip
    of it (flip.checks.slips, the first letter right), with at most
    MAX_SKIPPED of the seller's words between: what's kept is the seller's
    whole phrase, so a "not" left out still counts. Any other quote stays as
    it is, and fails rule 1 if it isn't in the listing: a word the listing
    doesn't have isn't a typo."""
    if not isinstance(quote, str) or not quote.strip() or in_listing(quote, text):
        return quote
    said = plain_words(quote)
    best = None
    for sentence in re.finditer(r"[^.!?\n]+", text):
        tokens = [(word, sentence.start() + m.start(), sentence.start() + m.end())
                  for m in re.finditer(r"\S+", sentence.group()) for word in plain_words(m.group())]
        for first in (n for n, token in enumerate(tokens) if said and typed_as(said[0], token[0])):
            found = followed(said[1:], tokens, first + 1, MAX_SKIPPED)
            if found is not None and (best is None or found[0] < best[0]):
                best = (found[0], tokens[first][1], tokens[found[1]][2] if found[1] is not None else tokens[first][2])
    return text[best[1]:best[2]].strip(" .,;:!?()*•-–—") if best else quote


def followed(words, tokens, at, skips):
    """Where the rest of a quote's words are found in order from token at on,
    skipping at most skips tokens: (tokens skipped, the last one's place), or None."""
    if not words:
        return 0, None
    for n in range(at, min(len(tokens), at + skips + 1)):
        if typed_as(words[0], tokens[n][0]):
            rest = followed(words[1:], tokens, n + 1, skips - (n - at))
            if rest is not None:
                return rest[0] + n - at, rest[1] if rest[1] is not None else n
    return None


def typed_as(meant, typed):
    """Whether the seller's word is the model's, or a slip of it: "stcratches" for "scratches"."""
    if meant == typed:
        return True
    most = most_slips(meant)
    return bool(most) and typed[:1] == meant[:1] and slips(typed[1:], meant[1:], most) <= most


def parts_of(text):
    """The listing's sentences and clauses, cut also at "apart from" and
    "except", without bullets: "✅ No scratches" is "No scratches"."""
    found = (part.strip(" .,;:!*•-–—✅❌✔✖☑✔✖") for part in SPLIT.split(text) if part)
    return [part for part in found if part]


# a typed mark word with one slip still says what's wrong: "few scraches", "craked screen"
MARK_WORDS = {word for kind in MARKS for word in CONDITION_PROMISES[kind]}


def problems_at(piece, esim_fine=False):
    """Where in a quote (its plain_words) each word that says something's
    wrong is: typos allowed ("scraches"), a guard against one or a part's
    name not ("scratch resistant", "Intel chip"). esim_fine: every one of
    the model is eSIM only (flip.offers.esim_everywhere), so that's no flaw."""
    clean = NOT_A_FLAW.sub(lambda m: " " * len(m.group()), piece)
    if esim_fine:
        clean = ESIM.sub(lambda m: " " * len(m.group()), clean)
    found = {len(plain_words(clean[:m.start()])) for m in PROBLEM.finditer(clean)}
    found |= {n for n, word in enumerate(plain_words(clean)) if slipped(word) in MARK_WORDS}
    return sorted(found)


def judge(piece, text):
    """Rule 2 for one piece of a flaw quote: "flaw", "denied" (the seller
    says it isn't so) or "no" (it doesn't say anything's wrong, or isn't in
    the listing as one part). Each word in it that says something's wrong
    is judged on its own: "no cracks only light scratches" is a flaw."""
    piece_words = plain_words(piece)
    at_words = problems_at(piece)
    battery = low_battery(piece)
    if not piece_words or not (at_words or battery) or len(piece.split()) > MAX_FLAW:
        return "no"
    text = figures_joined(answered(text))  # "Faults: none" -> "no Faults"; "Battery health\n79%" is one part
    part = next((p for p in parts_of(text) if contains(plain_words(p), piece_words)), None)
    if part is None or about_other_items(part, text):
        return "no"  # "...unlike most phones at this price which have scratches"
    if battery and low_battery(part):
        return "flaw"  # a figure the listing gives as the battery is now: no word says what's wrong
    if repeats_a_flaw(part, text) or offered_if_wanted(part, text) or noted_as_its_things(part, text):
        return "no"  # "the crack does not affect photos", "Crack on the screen (protector only)"
    thing = with_antecedent(part, text)
    if thing != part and not PROBLEM.search(without_its_things(thing, text)):
        return "no"  # "Original box, slightly damaged": the box's
    part_words = plain_words(part)
    at = find_phrase(part_words, piece_words)[0]
    theirs = its_things_words(part_words, text)  # "The protector is scratched": however much of it the quote has
    at_words = [n for n in problems_at(piece, esim_fine=bool(ESIM.search(piece)) and esim_everywhere(text))
                if at + n not in theirs]
    if not at_words:
        return "no"
    # the words of its own clause before it in the listing, then the quote's own words before the problem word
    head = " ".join(part_words[:at]).replace("no longer", " ").split()  # "no longer needed" denies nothing here
    after = part_words[at + len(piece_words):at + len(piece_words) + 2]
    if set(after) & DENIED_AFTER or in_denied_list(part, text):
        return "denied"
    denied_last = False
    for n in at_words:
        # the words leading to it in its own clause: the listing's before the quote, then the quote's own
        # ("Hinge isn't loose"), from the last clause word on ("No charger AND the back is cracked")
        lead = head[-MAX_BEFORE:] + piece_words[:n]
        lead = lead[max((k + 1 for k, w in enumerate(lead) if w in CLAUSE_WORDS), default=0):]
        following = (piece_words[n + 1:] + after)[:1]  # "scratch free", "scratch-free screen": free of it
        listed = not lead and denied_last and (piece_words[n - 1:n] or head[-1:]) in (["and"], ["or"], ["nor"])
        if not listed and not denied_by(lead, NEGATORS) and following != ["free"]:
            return "flaw"
        denied_last = True
    return "denied"


def about_other_items(part, text):
    """Whether a part of the listing is about other items, not this one
    (flip.offers.sentence_parts): "my previous iPhone had suffered water damage"."""
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        if part in sentence:
            return any(other for piece, other in sentence_parts(sentence)
                       if piece.strip() and (part in piece or piece.strip() in part))
    return False


def with_antecedent(part, text):
    """A part that goes on about a thing that comes with the item, with that
    thing in front of it, so its mark is read as the thing's: "...cracks on
    the screen protector, which can be replaced", "Screen protector - cracked"
    -> "screen protector cracked", "The protector is scratched (see photos),
    easy to peel off" -> "protector easy to peel off". After "which" it's the
    thing just before; otherwise only a part with nothing of its own but the
    mark (NO_SUBJECT), after a thing that isn't only where the item was kept
    (KEPT_IN). A part about the item itself is left as it is."""
    at = text.find(part)
    if at < 0:
        return part
    start = max(text.rfind(stop, 0, at) for stop in ".!?\n") + 1
    before = text[start:at]
    things = WITH_IT[kind_of_item(text)]
    if re.search(r"\bwhich[\s,]*$", before, re.IGNORECASE):
        thing = re.search(rf"{things}(?:\s+(?:itself|on it|on|fitted|included|applied|supplied|attached))?\s*$",
                          re.sub(r"[\s,;:–—-]*\bwhich[\s,]*$", "", before, flags=re.IGNORECASE), re.IGNORECASE)
        return f"{thing.group()} {part}" if thing else part
    if not NO_SUBJECT.match(part.strip()):
        return part
    last = next((p for p in reversed(parts_of(before)) if not ASIDE.match(p)), "")
    named = list(re.finditer(rf"\b{things}\b", re.sub(KEPT_IN, " ", " ".join(plain_words(last)))))
    return f"{named[-1].group()} {part}" if named else part


# a change offered if you'd like it, the "if" said before a comma: "If you want, the battery can be replaced for £20",
# "If you'd like the battery replaced I can do it for £20", "If wanted I can get the back glass replaced"
IF_WANTED = re.compile(r"\bif (?:(?:you|u)(?:['’]?d| would)? (?:want|like|prefer|wish|would like)\b|wanted\b|needed\b|"
                       r"desired\b|preferred\b|required\b)[^.!?\n]*$", re.IGNORECASE)
CHANGED = re.compile(r"\b(?:(?:be|have|get|got) (?:it |them |the [\w-]+(?: [\w-]+)? )?|(?:the |a )?(?:[\w-]+ )?)(?:replaced|"
                     r"repaired|fixed|swapped|changed)\b", re.IGNORECASE)


def offered_if_wanted(part, text):
    """Whether a part only offers a change if you'd like it, the "if" said
    before it: "If you want, the battery can be replaced for £20". A flaw
    named with the offer is still the listing's: "If you want, the cracked
    screen can be replaced for £40" has a cracked screen."""
    at = text.find(part)
    before = re.split(r"[.!?\n]", text[:at])[-1] if at >= 0 else ""
    wanted = IF_WANTED.search(before) or IF_WANTED.search(part.split(",")[0] + " ")
    return bool(wanted) and bool(CHANGED.search(part)) and not PROBLEM.search(CHANGED.sub(" ", part))


def repeats_a_flaw(part, text):
    """Whether a part only points back at a flaw the listing names in another
    part (POINTS_BACK): "the crack does not affect image quality" after "Crack
    on the camera lens", "price reflects the tiny issues" after "scuffs on the
    side". A flaw said only there is still a flaw: "price reflects the cracked
    back" in a listing that says nothing else about the back, or "Light
    scratches on the screen. Price reflects the damage to the back."."""
    if not POINTS_BACK.search(part):
        return False
    own = plain_words(part)
    kinds = condition_said(part, typos=True) & FLAWS
    places = {m.group().lower() for m in PLACE_WORDS.finditer(part)}
    others = [(condition_said(other, typos=True) & FLAWS, {m.group().lower() for m in PLACE_WORDS.finditer(other)})
              for other in this_items_parts(text) if plain_words(other) != own]  # "- Price reflects...": its own bullet
    said = [(listed, at) for listed, at in others if listed and (not places or places & at)]
    if not kinds:  # "the tiny issues": no kind of its own, so any flaw it points at
        return bool(said)
    return all(any(backed(kind, listed) for listed, _ in said) for kind in kinds)


# a part and what's wrong with it, a statement of its own: "screen cracked", "back glass smashed"
PART_BROKEN = re.compile(r"\b(?:screen|back|glass|lens|camera|frame|display|housing|corner|side) (?:\w+ )?(?:cracked|smashed|"
                         r"scratched|chipped|dented|broken|damaged|shattered)\b")


def in_denied_list(part, text):
    """"With no scratches, scuffs or visible damage": a "no" before the first
    item of a list that ends in "or" (or "nor") denies every item, so the
    part "scuffs or visible damage" is no flaw; so does one that ends in
    "and" or "&" when its first item is damage ("no scratches, scuffs and
    dents"). Otherwise a comma only lists things ("No charger, cracked
    screen" still has a cracked screen), and an item that says something of
    its own ("a small dent on the back", "screen has a crack or two") isn't
    one more item of the list."""
    target = plain_words(part)
    is_item = lambda seg: len(seg) <= MAX_ITEM and (not seg or seg[0] not in ITEM_OPENERS) and not set(seg) & LIST_BREAKS \
        and not PART_BROKEN.search(" ".join(seg))
    closes = lambda seg: any(w in ("or", "nor") and seg[n + 1:n + 2] != [] and seg[n + 1] not in NOT_A_CHOICE
                             for n, w in enumerate(seg))
    closes_with_and = lambda raw: bool(re.search(r"(?:^|\s)(?:and|&)\s+\S", raw))
    for sentence in re.split(r"[.!?;\n]+", answered(text)):
        raw = sentence.split(",")
        segments = [plain_words(s) for s in raw]
        for i in range(1, len(segments)):
            if not contains(segments[i], target):
                continue
            # from this item on, every segment up to the one that closes the list is a bare item
            end = next((j for j in range(i, len(segments)) if closes(segments[j]) or closes_with_and(raw[j])), None)
            if end is None or not all(is_item(item) for seg in segments[i:end + 1] for item in list_items(seg)):
                continue
            # back over bare items ("no scratches, scuffs, dents or marks") to the first, which has the "no"
            k = i - 1
            while k > 0 and not any(negation_at(segments[k], n, NEGATORS) for n in range(len(segments[k]))) \
                    and is_item(segments[k]):
                k -= 1
            head = segments[k]
            denial = [n for n in range(len(head)) if negation_at(head, n, NEGATORS)]
            first = head[denial[-1] + 1:] if denial else []
            while first and first[0] in AFTER_DENIAL:
                first = first[1:]
            if not first or not is_item(first):
                continue
            if closes(segments[end]) or PROBLEM.search(" ".join(first)) or set(first) & DAMAGE_EVENTS:
                return True
    return False


def list_items(segment):
    """A segment's items, split at "or" or "and": "dents or marks on the screen" -> [dents], [marks on the screen]."""
    items, item = [], []
    for w in segment:
        if w in ("or", "nor", "and"):
            items.append(item)
            item = []
        else:
            item.append(w)
    return items + [item]


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
    found = []
    for piece in parts_of(figures_joined(quote)):
        if judge(piece, text) != "flaw":
            continue
        apart = battery_apart(piece)  # "Battery health 79% small crack on back": two flaws, each in its own words
        found += [trimmed(piece)] if apart is None else \
            [trimmed(p) if n != 1 else p for n, p in enumerate(apart) if n == 1 or (p and judge(p, text) == "flaw")]
    return found


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
    found = re.sub(r"\s+", " ", re.sub(r"^[^A-Za-z0-9]+", "", quote.replace("(", " ").replace(")", " ").strip()))
    found = re.sub(r"\b(St|Gt|Lt|Upr|Lwr)\.(?= [A-Z])", r"\1", found)  # "St. Albans" is no sentence's end
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
    """A flaw the seller says isn't so: "no scratches", "no stick drift".
    Not one the seller makes an exception to ("no scratches other than a
    tiny one on the corner"): excepted."""
    return bool(quote.strip()) and in_listing(quote, text) and not flaws_in(quote, text) \
        and any(judge(piece, text) == "denied" for piece in parts_of(quote)) and not excepted(quote, text)


# what a "no" makes an exception to: "No marks OTHER THAN a tiny one on the corner", "Not a single scratch EXCEPT the
# camera lens", "No problems APART FROM it being a bit slow", "No scratches BUT a small one on the back", also as typed
# ("excpet", "appart from", "aside form", "other then", "exc."); "bar" and "save" only before an amount ("bar a tiny
# one", "save the small one"), not "bar none". What follows still has to look like a flaw (excepted)
EXCEPTIONS = re.compile(r"\b(?:oth(?:er|e)\s+th[ae]n|ap+art\s+f(?:ro|or|r)?m|a\s+part\s+from|asides?\s+f(?:ro|or)m|"
                        r"exc?e?pt(?:ing|\s+for)?|excpet|expect|barring|minus|besides|excluding|excl?\.|outside\s+of|"
                        r"with\s+the\s+exception\s+of|the\s+(?:only\s+)?exception\s+(?:is|being)|unless\s+you\s+count|"
                        r"but(?:\s+for)?|only(?:\s+with)?|just|beyond|save\s+for|"
                        r"(?:bar|save)(?=\s+(?:an?\s+|the\s+)?(?:one|two|three|\d+|some|few|couple|light|minor|small|tiny|"
                        r"slight|faint|hairline)\b))(?:\b|(?<=\.))", re.IGNORECASE)
# ...and a "no" about anything else, which leaves the rest of the quote said: "Selfie camera is a little blurry, but NO
# OTHER issues", "Small dent on the lid, NOTHING ELSE", "Speaker is tinny, OTHERWISE NO issues", "no issues ELSEWHERE"
NONE_ELSE = re.compile(r"\b(?:no|not\s+any|without\s+any|nothing)\s+(?:other|else|further|more|additional|extra)\b"
                       r"|\bnothing\s+else\b|\b(?:no|nothing|not)\s+(?:\w+\s+){0,2}(?:otherwise|elsewhere|anywhere\s+else)\b"
                       r"|\botherwise\s+(?:no|nothing|not)\b", re.IGNORECASE)
# what's wrong in words the flaw words leave out: "a bit SLOW", "a little BLURRY", "speaker is TINNY", "CAN'T USE Face ID"
SYMPTOMS = re.compile(r"\b(?:blurr?y|blurred|fuzzy|grainy|tinny|muffled|crackly|floppy|dim|dimmer|slow|slower|sluggish|"
                      r"warm|hot|unresponsive|temperamental|patchy|dodgy|iffy|hit and miss|drops? (?:calls|signal|out)|"
                      r"laggy|lags|lagging|glitchy|freezes|freezing|"
                      r"(?:can'?t|cannot|won'?t|doesn'?t|does not) (?:use|make|receive|hear|read|recogni[sz]e|detect|"
                      r"update|install|download|connect|charge|turn|hold|have true tone))\b", re.IGNORECASE)
# ...and, only straight after a plain exception ("No marks apart from a small DING", "no problems excpet face id QUIT
# WORKING", "No issues aside form the ultra wide camera, it shows a BLACK SCREEN"), more ways a fault is said: words a
# "no" anywhere else in the sentence can't be trusted with (the 26 Sep red team: "never once in three years had a black
# screen", "nowhere near Service Recommended", "only selling as I'm coming off contract")
MORE_SYMPTOMS = re.compile(r"\b(?:creak\w*|dings?|dinged|quit working|playing up|acting up|black screen|wearing off|"
                           r"worn off|rubbed off|works? (?:about |only )?half the time|works? (?:only )?sometimes|"
                           r"only lasts (?:about |around |roughly )?(?:an? |one |two |\d+ )?(?:hour|hr)s?|"
                           r"lasts? (?:about |around |roughly |maybe )?(?:an?|one|1) (?:hour|hr)|service recommended|"
                           r"replace (?:soon|now)|service battery|got wet|(?:water|liquid) damaged?|(?:fell|dropped|went) "
                           r"(?:it )?(?:in|into) (?:the |a |some )?(?:\w+ )?(?:water|sink|toilet|pool|bath|puddle|lake|sea|"
                           r"river)|(?:speakers?|earpiece|mic|microphone)(?:'s| is| are| sounds?| gets?| seems?| has gone| went)"
                           r"(?: (?:a bit|very|really|real|quite|pretty|too|so|super|kinda|a little))? (?:quiet|faint)|"
                           r"(?:doesn'?t|does not|don'?t|won'?t|isn'?t) always (?:work|connect|charge|read|recogni[sz]e|"
                           r"unlock|respond|register|detect|pair))\b", re.IGNORECASE)
# the exceptions that name a flaw for sure; "but", "only" and "just" often only go on ("No scratches, only selling as
# I'm coming off contract")
WEAK_EXCEPTIONS = re.compile(r"^(?:but|only|just|expect)\b", re.IGNORECASE)  # "Don't EXPECT to find a scratch"
# an exception typed so the listing's parts don't end there ("APPART FROM a small chip"): what follows is judged on its own
TYPED_EXCEPTIONS = re.compile(r"^(?:oth(?:er|e)\s+then|othe\s+than|ap+art\s+f(?:or|r)m|app+art\s+from|a\s+part\s+from|"
                              r"asides?\s+form|excpet|exept|excep\b)", re.IGNORECASE)
# a symptom said of what comes with the item, before it: "the charger gets warm", "the box got wet", "the case is
# wearing off"; not "gets hot when charging with a 20W charger" or "tinny even with the case off"
USED_WITH = re.compile(r"\b(?:off|on|from|with|without|via|using|by|to) (?:the |a |an |its |my )?(?:charger|charging cable|"
                       r"cable|plug|adapter|adaptor|mains)\b|\b(?:charger|charging|charge|cable) (?:port|socket|connector|"
                       r"pins?)\b|\bcover (?:screen|display)\b", re.IGNORECASE)  # the item's own: "the charger port", a Flip's "cover screen"
WITH_ITS_THINGS = re.compile(rf"\b(?:{WITH_IT['item']}|sleeves?|skins?|stands?|docks?|straps?|pouch(?:es)?|bags?|"
                             rf"earphones|headphones|ear ?buds|air ?pods|stylus|sim (?:card|tool|pin)|leads?|cords?|"
                             rf"wallets?|folios?|dongles?|stickers?|mounts?|power ?banks?|battery packs?|hubs?|"
                             rf"pop ?sockets?|films?)\b", re.IGNORECASE)
# ...or of another phone: "unlike my old phone that got wet", "my last 12 quit working"
OTHER_ITEM = re.compile(r"\b(?:my|his|her|their|your|our) (?:old|last|previous|other|partner'?s|mate'?s|friend'?s)\b|"
                        r"\bunlike\b|\bmost (?:phones|laptops|macbooks|\d+s)\b", re.IGNORECASE)
# real words that in a listing are a flaw word typed wrong, the labellers' typo list ("few STARCHES", "small SCAPES",
# "minor SCRUFFS", "a couple of DINTS", "screen is CREAKED"), or a wear word of their own ("a bit SCRUFFY")
TYPED_FLAWS = re.compile(r"\b(?:starch(?:es)?|scapes?|scruffs?|scruffy|dints?|dinted|creaked)\b", re.IGNORECASE)
# "NOTHING MORE THAN light wear on the corners", "NO MORE THAN a couple of light scratches", "nothing worse than a few
# hairline scratches": what follows is all there is, so it is said; the "no" denies only that there is more
NO_MORE_THAN = re.compile(r"\b(?:no|nothing|not)\s+(?:much\s+)?(?:more|worse)(?:\s+serious)?\s+than\b", re.IGNORECASE)
# a "no"'s exception that only says how much or where, so it is more of what the "no" was about: "other than a TINY ONE
# on the CORNER", "except the CAMERA LENS", "apart from THOSE on the BACK CORNERS"
REFERS_BACK = {"one", "ones", "few", "couple", "some", "little", "tiny", "teeny", "small", "minor", "light", "slight",
               "faint", "hairline", "single", "two", "three", "2", "3", "very", "really", "bit", "barely", "micro"}
ITEM_PLACES = {"camera", "cameras", "lens", "lenses", "screen", "display", "back", "front", "corner", "corners", "edge",
               "edges", "frame", "side", "sides", "bezel", "bezels", "lid", "hinge", "port", "ports", "button", "buttons",
               "keyboard", "key", "keys", "trackpad", "touchpad", "bottom", "top", "left", "right", "rear", "glass",
               "casing", "body", "base", "palm", "rest", "near", "around", "by", "under", "underneath", "upper", "lower",
               "middle", "centre", "center", "speaker", "speakers", "grille", "logo", "notch", "rim", "surface",
               "earpiece", "up", "across", "along", "dynamic", "island", "inner", "outer", "chin", "crease", "sensor",
               "flash", "volume", "power", "mute", "tray", "titanium", "aluminium", "aluminum", "ring", "bump", "selfie",
               "touch", "bar", "beside", "sim"}
# filler between them: "a", "the", "those", "on"
FILLER = {"that", "this", "these", "those", "it", "them", "the", "a", "an", "and", "or", "of", "on", "in", "at", "to",
          "for", "is", "are", "was", "were", "s", "there", "which", "just", "only"}


def flaw_said(part, text, more=False):
    """Whether a part of a quote says something is wrong without a "no" of its
    own: a flaw word the listing doesn't deny, a battery at 85% or under, or a
    symptom ("a bit slow", "can't use Face ID") or a flaw word typed as another
    word ("few scapes") with no "not" just before it, and not said of what
    comes with the item or of another phone. more: also MORE_SYMPTOMS, for
    what follows a plain exception."""
    if not part.strip():
        return False
    if low_battery(part) or any(judge(piece, text) == "flaw" for piece in parts_of(part)):
        return True
    for words in (SYMPTOMS, TYPED_FLAWS) + ((MORE_SYMPTOMS,) if more else ()):
        for found in words.finditer(part):
            lead = part[:found.start()]
            if WITH_ITS_THINGS.search(USED_WITH.sub(" ", lead)) or OTHER_ITEM.search(lead):
                continue  # "the charger gets warm", "unlike my old phone that got wet"
            before = plain_words(lead)[-3:]
            if not any(negation_at(before, n, NEGATORS) for n in range(len(before))):
                return True
    return False


def excepted(quote, text):
    """Whether a quote with a "no" in it still says something is wrong:
    1. what follows "except", "other than", "apart from"... says it ("apart
       from it being a bit slow"), or only says how much or where, so it is
       more of the flaw the "no" was about ("No marks other than a tiny one
       on the corner");
    2. that is itself a "no" or points back ("apart from that, no issues"),
       or the "no" is about anything else ("but no other issues"), and the
       rest of the quote says it ("Camera is a little blurry").
    3. what follows "nothing more than" or "no more than" says it ("Nothing
       more than light wear on the corners");
    4. another part of it says it in words the flaw words leave out ("A bit
       slow, no cracks", "Few scapes around the edges, no cracks").
    Only what looks like a flaw counts: not "only one owner", "no other
    issues, battery health is 91%" or "apart from that, no issues"."""
    for found in EXCEPTIONS.finditer(quote):
        before, after = quote[:found.start()], quote[found.end():]
        more = not WEAK_EXCEPTIONS.match(found.group(0))
        if flaw_said(after, text, more) or (TYPED_EXCEPTIONS.match(found.group(0)) and flaw_said(after, after, more)):
            return True  # "...apart from it being a bit slow"; on its own when it's typed ("appart from a small chip")
        said = [w for w in plain_words(after) if w not in FILLER]
        if said and all(w in REFERS_BACK or w in ITEM_PLACES for w in said) and \
                any(judge(piece, text) == "denied" for piece in parts_of(before)):
            return True  # "No marks other than a tiny one on the corner"
        if flaw_said(before, text):
            return True  # "Camera is a bit blurry, apart from that no issues"
    for found in NONE_ELSE.finditer(quote):
        if flaw_said(quote[:found.start()], text) or flaw_said(quote[found.end():], text):
            return True  # "Selfie camera is a little blurry, but no other issues"
    for found in NO_MORE_THAN.finditer(quote):
        after = quote[found.end():]
        if flaw_said(after, after, more=True):
            return True  # "Nothing more than light wear on the corners": judged on its own, as the "no" isn't about it
    # a part beside the "no" that says what's wrong in words the flaw words leave out: "A bit slow, no cracks no
    # scratches", "Few scapes around the edges, no cracks on the screen"
    return any(judge(piece, text) != "denied" and flaw_said(piece, text) for piece in parts_of(quote))


# the reading's own instruction copied into a flaw: "each fault, damage, mark or sign of wear the listing mentions,
# copied word for word", "...the phone has", "...the back glass is cracked" (with a flaw of the listing's after it)
INSTRUCTION = re.compile(r"^\s*each fault,? damage,? mark or sign of wear\b[\s,:;-]*(?:(?:the listing|it) mentions[\s,:;.-]*)?"
                         r"(?:copied word for word[\s,:;.-]*)?(?:(?:the|this) (?:phone|item|listing) has[\s,:;.-]*)?", re.IGNORECASE)


def without_instruction(quote, text):
    """A flaw quote with the reading's own instruction copied in front taken
    off: what's left if it's the listing's ("the back glass is cracked"),
    else nothing."""
    found = INSTRUCTION.match(quote) if isinstance(quote, str) else None
    if not found:
        return quote
    rest = quote[found.end():].strip(" .,;:-")
    return rest if rest and in_listing(rest, text) else ""


def tidied(reply, text):
    """A reading without what code can tell for sure is no flaw of the listing's:
    1. what the model copied from its own instructions rather than the listing:
       "each fault, damage, mark or sign of wear the listing mentions" as a
       flaw, the example "Leeds LS6" as the pickup place;
    2. a flaw the seller says isn't so: "no scratches" (a small model lists
       every condition word it sees).
    3. a "no offers" that's the seller's words but doesn't say it: "Open to
       reasonable offers", "£550 or nearest offer" (code reads no offers
       for itself instead, as with none).
    Each is dropped and the rest is checked as usual: failing the whole
    reading for it paid the API to read the listing again. A quote that's in
    the listing too stays; anything else wrong still fails the reading.
    First, a quote with the seller's typos put right goes back to the
    seller's words (as_written)."""
    answer = reply.answer
    echo = lambda quote: isinstance(quote, str) and bool(quote.strip()) and in_listing(quote, READING_SYSTEM) \
        and not in_listing(quote, text)
    if isinstance(answer, dict):
        if isinstance(answer.get("flaws"), list):
            answer = {**answer, "flaws": [as_written(f, text) for f in map(lambda f: without_instruction(f, text),
                                                                             answer["flaws"]) if f != ""]}
            answer = {**answer, "flaws": [f for f in answer["flaws"]
                                          if not echo(f) and not (isinstance(f, str) and denied(f, text))]}
        answer = {**answer, **{key: as_written(answer[key], text) for key in ("pickup", "no_offers") if key in answer}}
        answer = {**answer, **{key: "" for key in ("pickup", "no_offers") if echo(answer.get(key))}}
        said = answer.get("no_offers")
        if isinstance(said, str) and said.strip() and in_listing(said, text) and not no_offers_ok(said, text):
            answer = {**answer, "no_offers": ""}
        reply.answer = answer
    return reply


def installed(model, url):
    """Whether the Ollama at url has the model, by its name ("flip-reader-5"
    or "flip-reader-5:latest"); not when Ollama doesn't answer."""
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=2) as answer:
            names = {m.get("name") for m in json.load(answer).get("models") or [] if isinstance(m, dict)}
    except (OSError, ValueError, AttributeError):
        return False
    return model in names or f"{model}:latest" in names


def reader_for(local):
    """The model that reads a listing: FlipAssist's own reader (READER) when
    Ollama has it, else the local model given (Gemma, which also writes the
    drafts). Anything that isn't a LocalModel (none, a test's stand-in) stays."""
    if not READER or not isinstance(local, LocalModel) or local.name == READER or not installed(READER, local.url):
        return local
    return LocalModel(name=READER, url=local.url, timeout=local.timeout)


def fine_tuned(model):
    """Whether a model is one of FlipAssist's own fine-tuned readers ("flip-reader-5")."""
    return isinstance(model, str) and model.split(":")[0].startswith("flip-reader")


def reading_checked(answer, text, read_by):
    """A fine-tuned reader's reading that passed check_reading, with the
    safety checks only: each quote is the listing's (rule 1, checked already),
    a seller's story is cut to the flaw, the same words count once, and the
    pickup and "no offers" are checked as for any reading. Not rules 2 and 3:
    it was trained to quote exactly the sentences that state a flaw, and
    cutting its quotes into code's pieces lost flaws it had found."""
    flaws = [trimmed(quote) for quote in answer["flaws"] if isinstance(quote, str) and quote.strip()]
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
                        ask=lambda ai: tidied(ai.ask(system, user, [], READING_SCHEMA), text),
                        check=lambda found: check_reading(found, text), result=result, log=log)
    model = result["attempts"][-1]["model"] if answer is not None else None
    reading = code_reading(text) if answer is None else \
        (reading_checked if fine_tuned(model) else reading_from)(answer, text, model)
    return {**reading, "attempts": result["attempts"], "reasons": result["reasons"]}
