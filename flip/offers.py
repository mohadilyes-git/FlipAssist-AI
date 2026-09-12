"""Three kinds of offer, and what the listing gives you to say with each.

Code reads the seller's own words about the item's condition:
- lower: a flaw the listing mentions is the reason for offering less ("as the
  back is broken"), unless the seller says the price already allows for it;
- asking: you say you don't mind the flaw;
- more: good condition the listing describes, with no flaw, is the reason for
  paying more.

Your style decides whether that point goes in by itself: it does if your past
messages usually mention condition. If they don't, the draft leaves it out and
asks you. (When a draft is made longer, the draft on screen decides instead.)
Either way the check holds the message to the listing: it talks about the
condition only when it's meant to, says only what the listing says, and then
must say the point, not ask it. Asking about the condition is otherwise fine
("any scratches?"), but not to bring up the point the draft leaves out.
"""

import re

from flip.catalogue import contains, words
from flip.checks import (FAULTS, LEVELS, MARKS, NEGATIONS, NEW_SEALED, NOT_A_FLAW, PROBLEM, answered, clauses, has_fault,
                         prices_in, promises_in, stated_parts)

# the seller says the price already allows for the flaw: a lower offer mustn't use it again
PRICED_IN = re.compile(r"\b(?:hence (?:the |why )?(?:the |low |cheap )?price|priced accordingly|priced to reflect|"
                       r"price reflects|reflected in (?:the )?price|taken into account in (?:the )?price|"
                       r"why it (?:is |s )?(?:so )?(?:cheap|priced low)|hence (?:so )?cheap|price (?:is )?reduced|"
                       r"reduced (?:price|to reflect|for)|priced (?:it )?(?:low|lower|cheap|cheaper|to sell)|"
                       r"(?:selling|sold|going|letting it go) (?:it )?(?:for )?cheap(?:er|ly)?|"
                       r"cheap(?:er)? (?:than (?:others|usual|most) )?(?:due to|because of|cos|as)|"
                       r"(?:low|cheap) price (?:due to|because of|cos|as))\b")
# good condition in so many words: below "excellent" and "flawless", which the checks already read
GOOD = re.compile(r"\b(?:good|great|nice|lovely|decent|fab|fantastic|brilliant|top) condition\b"
                  r"|\bcondition (?:is )?(?:very |really )?(?:good|great|nice|lovely)\b"
                  r"|\b(?:good|great|decent|lovely|nice|mint) nick\b|\b(?:great|good) shape\b|\bwell looked after\b"
                  r"|\b(?:barely|hardly) used\b|\b(?:not|isn t) a (?:mark|scratch|scuff|dent) on it\b"
                  r"|\b(?:hardly|barely) (?:a|an|any) (?:mark|scratch|scuff|dent|chip)\w*")
# damage the checks' mark words don't cover: "cosmetic damage", "smashed screen"
DAMAGE = re.compile(r"\b(?:damage|damaged|smashed|shattered|bent|torn|ripped|stained|faded|peeling)\b")
GOOD_LEVELS = ["good", "excellent", "flawless"]  # each one backs the ones before it
FLAWS = MARKS | {"fault", "damage"}
# faults sellers write that a reseller's notes rarely do: read in a listing for a message, never for a
# listing's own condition (flip.checks.has_fault, where "battery needs replacing" isn't "for parts")
SELLER_FAULTS = re.compile(r"\b(?:no (?:picture|signal|service|display|image|face id|touch id)|blacklisted|"
                           r"needs? (?:replacing|a new \w+|repair\w*|fixing)|drains? (?:fast|quickly|really fast)|"
                           r"swollen|lifting|crackl\w*|buzz\w*|rattl\w*|distort\w*|"
                           r"(?:left|right|one) (?:airpod|earbud|bud|joy ?con|controller|pad)s? "
                           r"(?:is |are )?missing)\b")
# a listing's parts: its sentences and clauses, and what follows "apart from", "except" or "bar"
PARTS = re.compile(r"[,.;!?\n()|•►▪→\U0001F300-\U0001FAFF☀-➿]|\s[-–—]\s|\b(?:but|which|though|although|otherwise|however|hence)\b"
                   r"|\b(?:apart from|except(?: for)?|other than|save for)\b"
                   r"|\b(?:only|just)(?=\s+(?:a|an|one|some|the|few|couple|light|minor|small|tiny|slight|faint|"
                   r"hairline|odd|little)\b)"
                   r"|\bbar(?=\s+(?:a|an|one|some|the|small|tiny|minor|light|few)\b)", re.IGNORECASE)
# "I don't mind the scratch" isn't "no scratch": the "don't" is about you, not the item
ATTITUDE = re.compile(r"\b(?:don'?t|do not|doesn'?t|does not)\s+(?:mind|bother me|matter)\b"
                      r"|\bnot (?:too |that |really |at all )?(?:bothered|fussed|worried)(?: about| by)?\b"
                      r"|\bno (?:problem|bother|worries|issue) with\b", re.IGNORECASE)
# an offer at the asking price says you don't mind the flaw, not just names it
DONT_MIND = re.compile(r"\b(?:don'?t|do not) mind\b|\bnot (?:too |that |really |at all )?(?:bothered|fussed|worried)\b"
                       r"|\bno (?:problem|bother|issue|worries)\b|\b(?:fine|happy|ok|okay|alright) with\b|\beven with\b"
                       r"|\bdespite\b|\bregardless of\b"
                       # "the scratches don't bother me", "won't put me off", "aren't a problem", "I can live with"
                       r"|\b(?:doesn'?t|don'?t|does not|do not|won'?t|wouldn'?t) (?:bother|matter|put me off|worry)\b"
                       r"|\b(?:isn'?t|aren'?t|is not|are not|not) (?:a |an )?(?:problem|issue|concern|deal ?breaker)\b"
                       r"|\bcan live with\b|\bfine (?:by|for) me\b", re.IGNORECASE)
# in the offer's own question, what follows these isn't said: "would you take
# £170 IF the screen's cracked?", "would you take £170 AND IS the back broken?"
HYPOTHETICAL = re.compile(r"\b(?:if|whether|unless)\b.*|\band (?:is|are|does|do|did|has|have|any|can|could|would|will)\b.*",
                          re.IGNORECASE)
# in a statement, what follows these is a condition, not a claim: "happy to take it as listed if the
# battery is in good shape" says nothing about the battery
CONDITIONAL = re.compile(r"\b(?:if|unless|whether|as long as|provided|assuming)\b.*", re.IGNORECASE)
# "a time that works for you" isn't a claim that the item works
WORKS_FOR = re.compile(r"\bwork(?:s|ing)? (?:for|with) (?:you|me|us)\b", re.IGNORECASE)
MAX_QUOTE = 8  # words of the seller's to show: enough to recognise, short enough to read
# sayings with a flaw's word in them: "on the spot", "drop me a line"
IDIOMS = re.compile(r"\b(?:on the spot|spot on|hit the spot|drop (?:me |us )?a line|in line with|bottom line|line up|"
                    r"online|crack on|cracking on)\b", re.IGNORECASE)
JOINING = {"and", "but", "or", "so", "then", "also", "plus", "&", "+"}  # never the first word of a flaw
DANGLING = {"of", "the", "a", "an", "on", "in", "at", "to", "with", "and", "or", "near", "by", "from", "for"}  # nor the last
MAX_FAULT_QUOTE = 12  # words, when a fault phrase runs past MAX_QUOTE
# words that don't say which flaw it is: "a bit of", "on the"
SMALL_WORDS = {"a", "an", "the", "on", "in", "of", "to", "at", "it", "is", "its", "has", "have", "with", "and",
               "from", "bit", "some", "slight", "slightly", "small", "little", "very", "quite", "few", "s"}
# where a message gives its reason about the item: "given the dent", "as it's boxed", "I don't mind the scratch"
REASON_SAID = re.compile(r"\b(?:given|because|since|considering|seeing as|due to|despite|taking into account|"
                         r"in light of|bearing in mind|allowing for|to allow for|to account for|to reflect|"
                         r"as(?= (?:the|it|its|it's|there|they|they're)\b)|(?:what )?with(?= the\b)|(?:don'?t|do not) mind)"
                         r"\s+(?P<reason>[^?]*)",
                         re.IGNORECASE)
# where the reason ends: a sentence, an emoji, "so I can pay...", "as long as...", a new question
REASON_END = re.compile(r"[.!?;\n]|[\U0001F300-\U0001FAFF☀-➿]|,?\s+so\b|\bas long as\b|\bwhich\b"
                        r"|,\s*(?=(?:and |but )?(?:i|can|cash|let|thanks|happy)\b)"
                        r"|\s(?=(?:Does|Is|Are|Can|Could|Would|Will|What|How|Any|Let|Thanks|Cheers|Happy)\b)")
# words a reason may use whatever the listing says
REASON_FILLER = SMALL_WORDS | {"it", "its", "s", "is", "are", "be", "been", "in", "condition", "listing", "listed",
                               "said", "says", "mentioned", "described", "description", "you", "your", "item", "this",
                               "that", "there", "which", "why", "so", "offer", "offering", "price", "asking", "under",
                               "below", "less", "lower", "everything", "still", "all", "as", "t", "don", "doesn",
                               "isn", "know", "see", "noticed", "notice", "noting", "account", "into", "taking",
                               "allow", "for", "reflect", "photos", "pics", "pictures", "one", "being", "got",
                               "they", "re", "them", "also", "too", "though", "but", "or", "just", "really", "then",
                               "sold", "already", "mentions", "great", "hear", "fine", "by", "me", "state", "phone",
                               "console", "device", "handset", "unit", "product", "thing", "works", "working", "ok",
                               "okay", "happy", "glad", "good"}
# battery health at or under this is a reason to offer less: resellers price a phone down below 86%, and
# under 80% the iPhone itself says the battery needs a service
LOW_BATTERY = 85
ASK = {"lower": "Mention it as the reason for your offer?",
       "asking": "Say you don't mind it?",
       "more": "Give that as the reason you're paying more?"}


def unnegated(pattern, text):
    """True if the pattern is in the text without a "no" or "not" just before
    it, in the same sentence: "No box. Smashed screen." is still smashed."""
    for part in re.split(r"[.!?;\n]", text):
        joined = " ".join(words(part))
        if any(not NEGATIONS & set(joined[:m.start()].split()[-3:]) for m in pattern.finditer(joined)):
            return True
    return False


def condition_said(text, typos=False):
    """What a text says about the item's condition: kinds of flaw ("scratch",
    "crack", "fault", "damage"...) and how good it calls it ("good",
    "excellent", "flawless"). "No scratches" says neither, and nor does a
    guard against them ("scratch resistant") or a part's name ("Intel chip").
    typos: read as people type, for the seller's listing ("few scraches")."""
    text = NOT_A_FLAW.sub(" ", ATTITUDE.sub(" fine with ", re.sub(r"[’‘ʼ]", "'", text)))
    claims = promises_in(text, typos)
    said = {kind for kind in MARKS if "yes" in claims.get(kind, set())}
    said |= {key.split()[0] for key, saids in claims.items() if key.split()[0] in LEVELS and "yes" in saids}
    if has_fault(text) or unnegated(SELLER_FAULTS, text):
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
        cut = start + MAX_QUOTE
        # a fault the cut would end halfway through is said whole: "...it turns on" -> "...it turns on and off"
        plain = lambda end: " ".join(words(" ".join(tokens[start:end])))
        said, whole = plain(cut), plain(start + MAX_FAULT_QUOTE)
        reach = max((m.end() for m in FAULTS.finditer(whole) if m.start() < len(said) < m.end()), default=0)
        while reach and cut < len(tokens) and len(plain(cut)) < reach:
            cut += 1
        # ...and so is a place the cut would end on "of the": "...on the bottom left of the screen"
        while cut < min(len(tokens), start + MAX_FAULT_QUOTE) and tokens[cut - 1].lower() in DANGLING:
            cut += 1
        tokens = tokens[start:cut]
        # the word kept before the flaw is for "small crack", not "and cracked the back"
        while len(tokens) > 1 and tokens[0].lower().strip(",") in JOINING:
            tokens = tokens[1:]
        while len(tokens) > 1 and tokens[-1].lower() in DANGLING:
            tokens = tokens[:-1]
    return " ".join(tokens).strip(" *-–—:")


def read_listing(text):
    """What the listing says about the item's condition, in the seller's own
    words: {"flaws": ["Broken back"], "good": [], "priced_in": False}. A part
    with a flaw is a flaw even when it also praises: "good condition apart
    from a scratch"."""
    text = answered(re.sub(r"\bcondition\s*[:\-–—]\s*", "condition ", text, flags=re.IGNORECASE))  # "Condition: good"
    found = {"flaws": [], "good": [], "priced_in": bool(PRICED_IN.search(" ".join(words(text))))}
    for part in PARTS.split(text):
        said = condition_said(part, typos=True)
        if said & FLAWS:
            found["flaws"].append(quote(part, said & FLAWS))
        elif said & set(GOOD_LEVELS):
            found["good"].append(quote(part, said & set(GOOD_LEVELS)))
    return found


def point_for(kind, text, flaws=None, battery=None):
    """What's worth saying with this kind of offer, read from the listing
    (title and description), or None: {"about": "flaw", "condition" or
    "battery", "says": up to two parts of the listing, in the seller's words}.
    flaws: the listing's flaws as flip.reader read them, in place of code's
    own. battery: the phone's battery health the listing gives ("80", read
    by flip.numbers): with no flaw, LOW_BATTERY or under is the reason for a
    lower offer, as AlertFlip gives it ("the battery health is 80%")."""
    read = read_listing(text)
    if flaws is not None:
        read["flaws"] = list(flaws)
    if read["flaws"] and (kind == "asking" or (kind == "lower" and not read["priced_in"])):
        about, says = "flaw", read["flaws"]
    elif kind == "lower" and battery and float(battery) <= LOW_BATTERY and not read["priced_in"]:
        return {"about": "battery", "says": [f"battery health {battery}%"], "battery": battery}
    elif kind == "more" and read["good"] and not read["flaws"]:
        about, says = "condition", read["good"]
    else:
        return None
    return {"about": about, "says": once_each(says)[:2]}


def once_each(says):
    """Each flaw once: the title and the description often say the same one
    ("iPhone 13 128GB cracked back" and "Cracked back", "Cracked Screen" and
    "Small crack on the screen"). Of two that say the same, the later
    (the description's) stays, unless only it has the model's numbers."""
    kept = []
    for quote in says:
        same = next((k for k in kept if k.lower() == quote.lower() or same_flaw(k, quote)), None)
        if same is None:
            kept.append(quote)
        elif not (re.search(r"\d", quote) and not re.search(r"\d", same)):
            kept[kept.index(same)] = quote
    return kept


def same_flaw(a, b):
    """Whether two quotes say the same flaw: the same kinds of it, and the key
    words of one all in the other, or sharing the part ("screen cracked" and
    "The screen is cracked")."""
    keys_a, keys_b = key_words(a), key_words(b)
    if not keys_a or not keys_b or condition_said(a) != condition_said(b):
        return False
    return keys_a <= keys_b or keys_b <= keys_a or len(keys_a & keys_b) >= 2


def quoted(point):
    """'"Broken back" and "scratch on the screen"'"""
    return " and ".join(f'"{s}"' for s in point["says"])


def question_for(kind, point):
    """What the app asks you when a draft leaves the point out."""
    return f"The listing says {quoted(point)}. {ASK[kind]}"


# ── checking a message ──────────────────────────────────────────────────────

def said_in(message, offer=None):
    """The clauses of a message that say something: its statements up to a
    condition ("…if the battery is in good shape"), and the question that
    makes the offer, where the reason often sits ("would you take £170 to
    allow for the broken back?"), up to an "if" or a second question."""
    found = []
    for clause, asks in clauses(message):
        if asks and offer is not None and offer in prices_in(clause):
            clause = HYPOTHETICAL.sub("", clause)
        elif asks:
            continue
        else:
            clause = CONDITIONAL.sub("", clause)
        if len(words(clause)) > 1:
            found.append(clause)
    return found


def says_point(text, point):
    """Whether a text says the point, in the listing's words or a general word
    for them ("the damage" for "broken back"). A flaw code has no word for
    ("black dot on the screen", read by flip.reader) is said when most of its
    words are: "the black dot"."""
    point_kinds = condition_said(". ".join(point["says"]))
    if any(backed(kind, point_kinds) for kind in condition_said(text)):
        return True
    return any(not condition_said(part) and mostly_said(part, text) for part in point["says"])


def key_words(text):
    """The words that carry a phrase's meaning, cut to 5 letters so "drifts"
    and "drift", "crackles" and "crackling" match."""
    return {w[:5] for w in words(text) if w not in SMALL_WORDS and not w.isdigit()}


def key_sequence(text):
    """A text's key words in order (key_words, kept as a list)."""
    return [w[:5] for w in words(text) if w not in SMALL_WORDS and not w.isdigit()]


def mostly_said(part, text):
    """A part is said when two of its key words that sit next to each other
    in it sit next to each other in the text too ("the black dot" says "Black
    dot on the screen", "the black screen" doesn't), or, for a part of one
    key word, when that word is there."""
    keys, said = key_sequence(part), key_sequence(text)
    if len(keys) == 1:
        return keys[0] in said
    pairs = set(zip(said, said[1:]))
    return any(pair in pairs for pair in zip(keys, keys[1:]))


# a problem word said not to be one: "no problem", "the scratches aren't a problem", "can't see any issue"
NEGATED_BEFORE = re.compile(r"\b(?:no|not|never|without|zero|cannot|(?:is|are|was|were|does|do|did|wo|would|has|have|ca)"
                            r"n'?t)\s+(?:\w+\s+){0,2}$", re.IGNORECASE)


def check_reasons(message, listing_text, point=None):
    """What a message says about the item uses only the listing's words for
    what's wrong with it: "given the stiff hinge" or "Shame about the stiff
    hinge." fails on a listing that doesn't say "stiff". Only words that say
    something's wrong count (flip.checks.PROBLEM), so a reason about you or
    the sale ("as it's cash", "because it's over my budget") is fine, and
    questions are fine. Words code knows ("scratched") are
    check_condition_talk's, reported there. A message also never copies the
    seller's own story ("I dropped it and cracked the back")."""
    listed = {w[:5] for w in words(listing_text)}
    message = IDIOMS.sub(" ", re.sub(r"[’‘ʼ]", "'", message))  # "pay cash on the spot" names no spot
    said = stated_parts(message) + [m.group("reason") for m in REASON_SAID.finditer(message)]
    unbacked = [m.group() for part in said for m in PROBLEM.finditer(part)
                if not condition_said(m.group()) and not {w[:5] for w in words(m.group())} <= listed
                and not NEGATED_BEFORE.search(part[:m.start()])]
    problems = [f"the message says what's wrong with it in words the listing doesn't: "
                f"{', '.join(dict.fromkeys(w.lower() for w in unbacked))}"] if unbacked else []
    story = copied_story(message, listing_text, allowed=point["says"] if point else ())
    if story:
        problems.append(f"the message copies the seller's own story: \"{story}\"")
    return problems


def copied_question(message, questions, allowed_text, run=4):
    """Words a message repeats, at least run in a row, from a question you
    asked about another listing ("does it still work perfectly fine"), unless
    this listing (or code's own question) says them too. "" if none."""
    said, allowed = words(message), words(allowed_text)
    for question in questions:
        told = words(question)
        for start in range(len(told) - run + 1):
            piece = told[start:start + run]
            meaningful = [w for w in piece if w not in SMALL_WORDS and not w.isdigit()]
            if len(meaningful) >= 2 and contains(said, piece) and not contains(allowed, piece):  # not "for it given the"
                return " ".join(piece)
    return ""


def copied_story(message, listing_text, run=4, allowed=()):
    """Words the seller wrote about themselves ("I dropped it and cracked the
    back") that a message repeats, at least run words of it in a row. The
    flaw the message is meant to say is allowed (allowed: its quotes), even
    from a sentence with "my" in it ("selling my iphone, small crack on back")."""
    message_words = words(message)
    said = [words(quote) for quote in allowed]
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", listing_text):
        if not re.search(r"\b(?:I|I'?ve|I'?m|[Mm]y|[Ww]e|[Oo]ur)\b", sentence):
            continue
        told = words(sentence)
        for start in range(len(told) - run + 1):
            piece = told[start:start + run]
            if contains(message_words, piece) and not any(contains(quote, piece) for quote in said):
                return " ".join(piece)
    return ""


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


def check_condition_talk(message, listing_text, point, mention, kind="lower", offer=None):
    """A message talks about the item's condition only when this draft is
    meant to (there's a point, and it's mentioned), says only what the listing
    does, and then must say the point, not ask it ("does it have a broken
    back?" reads as if you hadn't read the listing): at the asking price, that
    you don't mind it. It never calls a faulty item working, or anything new
    or sealed that the listing doesn't. Questions don't count as talking about
    it ("any scratches?" claims nothing), but the question that makes the offer
    (offer, in pence) does: "would you take £170 for the scratched one?". A
    one-word clause ("Perfect,") isn't about the item."""
    if not isinstance(message, str) or not message.strip():
        return []  # check_message reports that
    message = re.sub(r"[’‘ʼ]", "'", message)
    statements = said_in(message, offer)
    stated = set().union(*map(condition_said, statements))
    said_point = bool(point) and says_point(message, point)
    problems = []
    if point and mention:
        if not said_point:
            problems.append(f"the message leaves out what the listing says: {quoted(point)}")
        elif not says_point(". ".join(statements), point):
            problems.append(f"the message asks about {quoted(point)} instead of saying it")
        elif kind == "asking" and not DONT_MIND.search(message):
            problems.append(f"the message names {quoted(point)} but doesn't say you don't mind it")
    elif stated or said_point:
        problems.append("the message talks about the condition, but this draft leaves that out")
    listed = condition_said(listing_text)
    unbacked = {claim for claim in stated if not backed(claim, listed)}
    said = WORKS_FOR.sub(" ", ". ".join(statements))
    if "yes" in promises_in(said).get("working", set()) and has_fault(listing_text) \
            and "yes" not in promises_in(listing_text).get("working", set()):
        unbacked.add("working")
    if NEW_SEALED.search(" ".join(words(said))) and not NEW_SEALED.search(" ".join(words(listing_text))):
        unbacked.add("new")
    unbacked = sorted(unbacked)
    if unbacked:
        problems.append(f"the message says things about the condition the listing doesn't: {', '.join(unbacked)}")
    return problems + check_reasons(message, listing_text, point if mention else None)
