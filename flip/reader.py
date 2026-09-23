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
"""

import re

from flip.attempts import try_models
from flip.catalogue import contains, find_phrase, words
from flip.checks import (CONDITION_PROMISES, ESIM, MARKS, NEGATIONS, NOT_A_FLAW, PROBLEM, answered, denied_by,
                         most_slips, slipped, slips)
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
# what comes with the item, and the item's own parts: a mark on a screen protector, a phone case or cover, the box
# or a charger isn't the item's. A "case" is earbuds' own (their charging case), and a "back cover" a phone's back
PROTECTORS = r"(?:(?:(?:screen|glass|lens|camera|privacy|tempered|back|front) ){0,2}protectors?|tempered glass(?! back)|" \
             r"(?:screen|glass) guards?)(?: (?:on|over) (?:the |my )?(?:back |front |rear |main |selfie )?(?:screen|camera|" \
             r"cameras|lens|lenses|back|front|display|glass))?"
CASES = r"(?:(?:phone|clear|silicone|leather|rubber|protective|wallet|flip|magsafe|otterbox|spigen|carry|carrying|travel|" \
        r"battery) ){0,2}(?<!charging )(?:case|cases|covers?)"
THINGS_WITH_IT = r"box|boxes|packaging|charger|chargers|cable|cables|adapter|adaptor|plug"
ACCESSORY = re.compile(rf"\b(?:{PROTECTORS}|{CASES}|{THINGS_WITH_IT})\b")
ACCESSORY_WITH_BUDS = re.compile(rf"\b(?:{PROTECTORS}|(?:phone|clear|silicone|leather|rubber|protective) (?:case|cases|covers?)|"
                                 rf"{THINGS_WITH_IT})\b")
UNDER_IT = re.compile(r"\b(?:under|underneath|beneath|behind) (?:it|them|that|this)\b")  # "a small scratch under it"
EARBUDS = re.compile(r"\b(?:air ?pods?|ear ?buds?|buds|earphones|headphones|beats)\b", re.IGNORECASE)
# what's said about the thing that comes with it but isn't a mark on it, set aside first: what's included ("no
# charger", "comes with the original box"), what made the marks ("light marks from being in a case"), where a mark
# is ("a scratch under the screen protector", "the protector hides a small crack"), and the thing being there or
# not ("screen protector fitted", "never used a screen protector", "took the screen protector off")
WITH_IT = rf"(?:{PROTECTORS}|{CASES}|{THINGS_WITH_IT})"
# ...said before it: included, the cause, where a mark is, used or not ("with a clear case", "from being in a case",
# "under the screen protector", "never used a screen protector", "took the screen protector off")
CONTEXT_BEFORE = (rf"\b(?:no|without|with|plus|including|includes|included|incl|from|by|due to|because of|caused by|under|"
                  rf"underneath|beneath|behind|below|(?:kept|been|always|always been|was|being|put|stored|lived) in|into|had|"
                  rf"has had|always had|kept with|using|used|use|never used|never had|didn['’ ]?t use|didnt use|not used|took|"
                  rf"taken|take|peeled|removed|remove)\s+(?:(?:being|been|kept|in|using|wearing|putting it in)\s+)*(?:(?:a|an|"
                  rf"the|its|my|original|apple|new|spare|free|cheap|old|his|her|their)\s+)*{WITH_IT}(?:\s+(?:off|on))?\b")
# ...or after it: there and doing its job ("screen protector fitted", "the protector hides a small crack")
CONTEXT_AFTER = (rf"\b{WITH_IT}(?:\s+(?:fitted|applied|attached|included|supplied|off|hides?|hiding|covers?|covering|over it|"
                 rf"on top|on(?= since| from| always|$| it\b| the phone)|since (?:new|day one|purchase)|"
                 rf"from (?:new|day one)))+\b")
CONTEXT = re.compile(f"{CONTEXT_BEFORE}|{CONTEXT_AFTER}")
INCLUDED = re.compile(CONTEXT_BEFORE)
# a part that goes on about the one before it, with no subject of its own: "..., easy to peel off", "Screen
# protector - cracked", "Original box, slightly damaged"; and the asides between ("(see photos)")
NO_SUBJECT = re.compile(r"^(?:easy|easily|needs?|can|could|is|are|was|were|has|have|had|got|looks?|slightly|a bit|bit|also|"
                        r"cracked|scratched|chipped|scuffed|marked|dented|damaged|peeling|lifting|starting|it|its|it['’]s|they|"
                        r"they['’]re|theyre|one of them|both of them)\b", re.IGNORECASE)
# the item's own part said to be fine, or not the one marked: "...not the screen", "the screen underneath is perfect"
PART_IS_FINE = re.compile(r"\bnot (?:on )?(?:the |my )?(?:actual |real )?(?:screen|lens|camera|back|phone|glass|display)\b|"
                          r"\b(?:the )?(?:actual |real )?(?:screen|lens|camera|back|phone|glass|display)(?: underneath| itself| "
                          r"below| under it)?(?: is| are| s)? (?:fine|perfect|mint|ok|okay|flawless|unmarked|untouched|undamaged|"
                          r"spotless|pristine)\b")
ASIDE = re.compile(r"^(?:see |as (?:seen |shown )?in (?:the )?|check (?:the )?)?(?:pics?|photos?|pictures?|images?)$",
                   re.IGNORECASE)
WITH_IT_AT_END = re.compile(rf"(?:{WITH_IT})(?:\s+(?:itself|on it|on|fitted))?\s*$", re.IGNORECASE)
PHONE_PARTS = {"screen", "display", "back", "rear", "frame", "housing", "camera", "cameras", "lens", "lenses", "body",
               "glass", "side", "sides", "port", "button", "buttons", "speaker", "bezel", "phone", "iphone", "handset",
               "device", "unit", "battery", "face", "microphone", "mic", "flash", "sim", "earpiece"}
# a part that only points back at a flaw the listing names elsewhere: "the crack does not affect image quality",
# "price reflects the camera lens damage". Its flaw is the other part's, said there
POINTS_BACK = re.compile(r"\b(?:does|do|did|will|would|should) ?n[o']?t (?:really |at all |in any way )?(?:affect|effect|"
                         r"impact|interfere with)|\b(?:doesnt|dont|wont|never) (?:affect|effect|impact)|"
                         r"\b(?:has|have|with) no (?:effect|impact)\b|\bprice (?:reflects|reflected|takes? (?:\w+ )?into "
                         r"account|allows? for|accounts? for)|\bpriced (?:to reflect|accordingly)|"
                         r"\breflected in the price|\bhence the (?:low |cheap )?price", re.IGNORECASE)
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


def as_written(quote, text):
    """A quote put back to the listing's own words when the model put the
    seller's typos right: "Small scratch on the corner" for the listing's
    "Small scratich on the corner" is the listing's. The same words in the
    same order, each the seller's or a slip of it (flip.checks.slips, the
    first letter right). Any other quote stays as it is, and fails rule 1
    if it isn't in the listing: a word the listing doesn't have isn't a typo."""
    if not isinstance(quote, str) or not quote.strip() or in_listing(quote, text):
        return quote
    said = plain_words(quote)
    tokens = [(word, m.start(), m.end()) for m in re.finditer(r"\S+", text) for word in plain_words(m.group())]
    for i in range(len(tokens) - len(said) + 1):
        if all(typed_as(meant, tokens[i + k][0]) for k, meant in enumerate(said)):
            return text[tokens[i][1]:tokens[i + len(said) - 1][2]].strip(" .,;:!?()*•-–—")
    return quote


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
    if part is None or about_other_items(part, text) or on_accessory(with_antecedent(part, text), text) \
            or repeats_a_flaw(part, text) or offered_if_wanted(part, text):
        return "no"  # "...unlike most phones at this price which have scratches", "the protector itself is cracked"
    if battery and low_battery(part):
        return "flaw"  # a figure the listing gives as the battery is now: no word says what's wrong
    if ESIM.search(piece) and esim_everywhere(text):
        at_words = problems_at(piece, esim_fine=True)
        if not at_words:
            return "no"
    part_words = plain_words(part)
    at = find_phrase(part_words, piece_words)[0]
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


def on_accessory(part, text):
    """Whether a part's marks are all on what comes with the item, not on it:
    each clause that says what's wrong names a protector, a phone case or
    cover, the box or a charger, and none of the item's own parts ("The
    protector itself is scratched and cracked at one corner", "case is a bit
    worn", "box has a dent"). What's included isn't what's marked: "no
    charger and the hinge is a bit stiff" is the hinge's. A clause with
    nothing of its own before what's wrong goes on about the one before
    ("...is scratched AND CRACKED at one corner"). "A crack on the screen
    under the protector" names the screen and "back cover cracked" the back:
    those are the phone's. In a listing of earbuds a case is theirs."""
    accessory = ACCESSORY_WITH_BUDS if EARBUDS.search(text) else ACCESSORY
    plain = PART_IS_FINE.sub(" ", CONTEXT.sub(" ", " ".join(plain_words(part))))
    clauses = re.split(rf"\b(?:{'|'.join(sorted(CLAUSE_WORDS))})\b", plain)
    found, last = [], False
    for clause in clauses:
        clean = NOT_A_FLAW.sub(" ", clause).strip()
        if not PROBLEM.search(clean):
            continue
        if PROBLEM.match(re.sub(r"^(?:\w+ly|also|then|got|has|is|are) ", "", clean)) and found:
            found.append(last)  # "and cracked at one corner": the last clause's
            continue
        last = bool(accessory.search(clean)) and not set(accessory.sub(" ", clean).split()) & PHONE_PARTS \
            and not UNDER_IT.search(clean)
        found.append(last)
    return bool(found) and all(found)


def with_antecedent(part, text):
    """A part that goes on about what comes with the item, with that in front
    of it, so on_accessory reads it as that thing's: "...cracks on the screen
    protector, which can be replaced" -> "screen protector can be replaced",
    "Screen protector - cracked", "The protector itself is scratched (see
    photos), easy to peel off" -> "protector easy to peel off". After "which"
    it's the words just before; otherwise only a part with no subject of its
    own (NO_SUBJECT) goes on about the last one, asides aside. A part about
    the item itself is left as it is."""
    at = text.find(part)
    if at < 0:
        return part
    start = max(text.rfind(stop, 0, at) for stop in ".!?\n") + 1
    before = text[start:at]
    if re.search(r"\bwhich[\s,]*$", before, re.IGNORECASE):
        thing = WITH_IT_AT_END.search(re.sub(r"[\s,;:–—-]*\bwhich[\s,]*$", "", before, flags=re.IGNORECASE))
        return f"{thing.group()} {part}" if thing else part
    if not NO_SUBJECT.match(part.strip()):
        return part
    last = next((p for p in reversed(parts_of(before)) if not ASIDE.match(p)), "")
    thing = ACCESSORY.search(INCLUDED.sub(" ", " ".join(plain_words(last))))  # "comes with box, it has a crack": the phone's
    return f"{thing.group()} {part}" if thing and on_accessory(f"{last} cracked", text) else part


IF_WANTED = re.compile(r"\bif (?:you|u) (?:want|like|prefer|wish|would like)\b[^.!?\n]*$", re.IGNORECASE)
CHANGED = re.compile(r"\b(?:be|have|get) (?:it |them |the \w+ )?(?:replaced|repaired|fixed|swapped|changed)\b", re.IGNORECASE)


def offered_if_wanted(part, text):
    """Whether a part offers to change something if you'd like it, the "if"
    said before a comma: "If you want, the battery can be replaced for £20"."""
    at = text.find(part)
    before = re.split(r"[.!?\n]", text[:at])[-1] if at >= 0 else ""
    return bool(CHANGED.search(part)) and bool(IF_WANTED.search(before))


def repeats_a_flaw(part, text):
    """Whether a part only points back at a flaw the listing names in another
    part (POINTS_BACK): "the crack does not affect image quality" after "Crack
    on the camera lens", "price reflects the tiny issues" after "scuffs on the
    side". A flaw said only there is still a flaw: "price reflects the cracked
    back" in a listing that says nothing else about the back."""
    if not POINTS_BACK.search(part):
        return False
    kinds = condition_said(part, typos=True) & FLAWS
    others = [condition_said(other, typos=True) & FLAWS for other in this_items_parts(text) if other.strip() != part.strip()]
    if not kinds:  # "the tiny issues": no kind of its own, so any flaw it points at
        return any(others)
    return all(any(backed(kind, listed) for listed in others) for kind in kinds)


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
    is_item = lambda seg: len(seg) <= MAX_ITEM and (not seg or seg[0] not in ITEM_OPENERS) and not set(seg) & LIST_BREAKS
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
            while k > 0 and not set(segments[k]) & NEGATORS and is_item(segments[k]):
                k -= 1
            head = segments[k]
            denial = [n for n, w in enumerate(head) if w in NEGATORS]
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
            answer = {**answer, "flaws": [as_written(f, text) for f in answer["flaws"]]}
            answer = {**answer, "flaws": [f for f in answer["flaws"]
                                          if not echo(f) and not (isinstance(f, str) and denied(f, text))]}
        answer = {**answer, **{key: as_written(answer[key], text) for key in ("pickup", "no_offers") if key in answer}}
        answer = {**answer, **{key: "" for key in ("pickup", "no_offers") if echo(answer.get(key))}}
        said = answer.get("no_offers")
        if isinstance(said, str) and said.strip() and in_listing(said, text) and not no_offers_ok(said, text):
            answer = {**answer, "no_offers": ""}
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
