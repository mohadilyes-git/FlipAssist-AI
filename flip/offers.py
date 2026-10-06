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
from functools import lru_cache

from flip.catalogue import contains, load_catalogue, model_names, models_named, words
from flip.checks import (BUMP, ESIM, FAULTS, ISSUE_KINDS, ISSUES, LEVELS, MARKS, NEEDS_REPAIR, NEGATIONS, NEW_SEALED, NICK,
                         NO_LONGER, WELL_USED, negation_at,
                         NOT_A_FLAW, OTHER_ITEMS,
                         PROBLEM, SELLER_FAULT_WORDS, SIGNS_OF_USE, THIS_ITEM, answered, clauses, ends_asking, has_fault,
                         prices_in, promises_in, stated_parts)
from flip.numbers import CUE as BATTERY_CUE, TYPED_BATTERY, battery_worded, figure, read_numbers

# good condition in so many words: below "excellent" and "flawless", which the checks already read
GOOD = re.compile(r"\b(?:good|great|nice|lovely|decent|fab|fantastic|brilliant|top) condition\b"
                  r"|\bcondition (?:is )?(?:very |really )?(?:good|great|nice|lovely)\b"
                  r"|\b(?:good|great|decent|lovely|nice|mint) nick\b|\b(?:great|good) shape\b|\bwell looked after\b"
                  r"|\b(?:barely|hardly) used\b|\b(?:not|isn t) a (?:mark|scratch|scuff|dent) on it\b"
                  r"|\b(?:hardly|barely) (?:a|an|any) (?:mark|scratch|scuff|dent|chip)\w*")
# damage the checks' mark words don't cover: "cosmetic damage", "smashed screen"
DAMAGE = re.compile(r"\b(?:damage|damaged|smashed|shattered|bent|torn|ripped|stained|faded|peeling)\b")
GOOD_LEVELS = ["good", "excellent", "flawless"]  # each one backs the ones before it
# what's wrong without a mark or a fault, each its own kind (flip.checks.ISSUE_KINDS): "issue: esim", "issue: untested"
ISSUE_PATTERNS = {f"issue: {kind}": re.compile(rf"\b(?:{said})\b", re.IGNORECASE) for kind, said in ISSUE_KINDS.items()}
FLAWS = MARKS | {"fault", "damage"} | set(ISSUE_PATTERNS)
# a denial of what's wrong, for the kinds read by pattern: "free from nicks", "zero signs of use"
DENIALS = NEGATIONS | {"free", "zero", "nothing"}
NICKS = re.compile(rf"\b(?:{NICK})\b")  # a mark of the chip kind
USED_SIGNS = re.compile(rf"\b(?:{SIGNS_OF_USE}|{WELL_USED})\b")  # a mark of the general kind
BUMPS = re.compile(rf"\b(?:{BUMP})")  # a dent
NEEDS_FIXING = re.compile(rf"\b(?:{NEEDS_REPAIR})\b")  # damage
# faults sellers write that a reseller's notes rarely do: read in a listing for a message, never for a
# listing's own condition (flip.checks.has_fault, where "battery needs replacing" isn't "for parts")
SELLER_FAULTS = re.compile(r"\b(?:no (?:picture|signal|service|display|image|face id|touch id)|blacklisted|"
                           r"needs? (?:replacing|a new \w+|repair\w*|fixing)|drains? (?:fast|quickly|really fast)|"
                           r"swollen|lifting|crackl\w*|buzz\w*|rattl\w*|distort\w*|"
                           r"(?:left|right|one) (?:airpod|earbud|bud|joy ?con|controller|pad)s? "
                           rf"(?:is |are )?missing|{SELLER_FAULT_WORDS})\b")
# a listing's parts: its sentences and clauses, and what follows "apart from", "except" or "bar"
PARTS = re.compile(r"[,;!?\n()|•►▪→\U0001F300-\U0001F50A\U0001F50C-\U0001FAFF☀-➿]|(?<!\d)\.|\.(?!\d)|\s[-–—]\s|"
                   r"\b(?:but|which|though|although|otherwise|however|hence)\b"
                   r"|\b(?:apart from|except(?: for)?|other than|save for)\b"
                   r"|\b(?:only|just)(?=\s+(?:a|an|one|some|the|few|couple|light|minor|small|tiny|slight|faint|"
                   r"hairline|odd|little)\b)(?!\s+an?\s+e[- ]?sim)"
                   r"|\bbar(?=\s+(?:a|an|one|some|the|small|tiny|minor|light|few)\b)", re.IGNORECASE)
# "I don't mind the scratch" isn't "no scratch": the "don't" is about you, not the item ("don't care about the
# scratch" too, as the writer says it: 26 Sep)
ATTITUDE = re.compile(r"\b(?:don'?t|do not|doesn'?t|does not)\s+(?:mind|care(?: about)?|bother me|matter)\b"
                      r"|\bnot (?:too |that |really |at all )?(?:bothered|fussed|worried)(?: about| by)?\b"
                      r"|\bno (?:problem|bother|worries|issue) with\b", re.IGNORECASE)
# an offer at the asking price says you don't mind the flaw, not just names it
DONT_MIND = re.compile(r"\b(?:don'?t|do not) (?:mind|care)\b"
                       r"|\bnot (?:too |that |really |at all )?(?:bothered|fussed|worried)\b"
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
# battery health at or under this is a reason to offer less, and a flaw of the listing's: resellers price a phone
# down below 86% (the line read from the labels: every figure of 85 or under a flaw, 86 and up not), and
# under 80% the iPhone itself says the battery needs a service
LOW_BATTERY = 85
# a battery figure apart from its label, put next to it before the listing is cut into parts: on the line under
# it, after a dash, a bar, an arrow or ":-" ("Battery health\n79%", "Battery health - 82%", "Battery health:-\n79%"),
# or in brackets ("Battery health (82%)")
FIGURE_APART = re.compile(rf"(?<![a-z])((?:{TYPED_BATTERY}(?:\s+(?:health|life|capacity|condition))?|b/?h|health|capacity|"
                          r"🔋)[ \t\u00a0]*)(?:[:\-–—|=>→➡\ufe0f()•][ \t\u00a0]*|\r?\n[ \t\u00a0]*)+"
                          r"(?=~?\d{1,3}(?:\.\d+)?[ \t]*(?:%|per ?cent))", re.IGNORECASE)
# ...only where the parts would be cut between them: "Battery Health: 80%" and "Battery health -78%" stay as written
SPLITS = re.compile(r"[\n–—|→➡()•]|\s-\s|\s-$|^-\s")
BRACKETED_FIGURE = re.compile(r"\(\s*(~?\d{1,3}(?:\.\d+)?\s*(?:%|per ?cent))\s*\)", re.IGNORECASE)
# a figure in a seller's text, with its % if it has one ("84.5%", "80 percent", "81")
FIGURE = re.compile(r"(?<![\d.£$€])(\d{1,3}(?:\.\d+)?)(\s*(?:%|per ?cent\b))?(?!\d)", re.IGNORECASE)
# a figure with no % is the battery's only right after a word for its health: "BH 81", "Battery health: 79"
HEALTH_WORD_BEFORE = re.compile(r"(?:health|\bbh|\bb/h|capacity|max(?:imum)? cap(?:acity)?|🔋)\s*(?:(?:is|at|of|on|now|"
                                r"currently|still)\s+|[:=~-]\s*)*$", re.IGNORECASE)
HEALTH_WORD = re.compile(r"health|\bbh\b|\bb/h\b|capacity|max(?:imum)? cap|🔋", re.IGNORECASE)
# what makes a figure something other than the battery's health now, said right before it: a charge level or limit
# ("Battery level 60%", "Battery charges to 80%"), the past ("was 84%", "replaced at 81%") or a bound upwards ("over
# 85%", "at least 80%")...
NOT_HEALTH_BEFORE = re.compile(r"\b(?:level|charged?|charging|charges|limit(?:ed)?|set (?:to|at)|percentage|showing|shows|"
                               r"holds?|holding|lasts?|still on|down to|drops? to|"
                               r"was|were|used to be|had been|replaced|replacement|new battery|fitted|"
                               r"(?<!years )(?<!year )(?<!months )(?<!month )old (?:one|battery)|"
                               r"before|previously|originally|over|above|more than|at least|min(?:imum)?|greater than)"
                               r"(?:\s+\w+)?\s*[:=~-]*\s*$|(?<![-=])[<>]=?\s*$", re.IGNORECASE)  # "->" is an arrow
# ...or right after it: "85%+", "80% charged", "60% left", "20% off", "80% condition", "80% or more", "10/10", "25 March",
# "100% when I bought it"
NOT_HEALTH_AFTER = re.compile(r"^\+|^\s*(?:\w+\s+)?(?:charged?|charging|limit|left|remaining)\b|^\s*(?:off|cheaper|discount|"
                              r"condition|grade|cosmetic\w*|less than|more than|or (?:more|higher|above|better|over)|upwards|"
                              r"and (?:above|up)|plus|deposit|upfront|when (?:i |we )?(?:bought|got) it|at purchase|"
                              r"by (?:bedtime|the end of the "
                              r"day|the evening|night)|after (?:a |an )?(?:full |whole )?(?:day|night|hours?))\b|"
                              r"^\s*(?:/|out of)\s*\d|"
                              r"^(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", re.IGNORECASE)
# a figure "in the photos" with no word for health is the charge the photos show: "Battery good on 50% in pics"
IN_PHOTOS_AFTER = re.compile(r"^\s*(?:\w+\s+)?in (?:the )?(?:photos?|pics?|pictures?|images?)\b", re.IGNORECASE)
# a figure the seller only gives roughly, or as a ceiling: still 85% or under ("under 80%", "around 80%", "~80%")
ROUGHLY_BEFORE = re.compile(r"\b(just under|under|below|less than|about|around|approx\w*|roughly|nearly|almost|circa)\s*$|"
                            r"(~)\s*$", re.IGNORECASE)
PHONE = {"category": "phones"}
ASK = {"lower": "Mention it as the reason for your offer?",
       "asking": "Say you don't mind it?",
       "more": "Give that as the reason you're paying more?"}


def unnegated(pattern, text, negations=NEGATIONS):
    """True if the pattern is in the text without a "no" or "not" just before
    it, in the same sentence: "No box. Smashed screen." is still smashed, and
    so is "AT&T locked" (its "t" is no "not": negation_at)."""
    for part in re.split(r"[.!?;\n]", text):
        joined = " ".join(words(part))
        for m in pattern.finditer(joined):
            before = joined[:m.start()].split()
            if not any(negation_at(before, n, negations) for n in range(max(0, len(before) - 3), len(before))):
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
    said |= {kind for kind, pattern in ISSUE_PATTERNS.items() if unnegated(pattern, text, DENIALS)}
    if unnegated(NICKS, text, DENIALS):
        said.add("chip")
    if unnegated(USED_SIGNS, text, DENIALS):
        said.add("mark")
    if unnegated(BUMPS, text, DENIALS):
        said.add("dent")
    if unnegated(NEEDS_FIXING, text, DENIALS):
        said.add("damage")
    if unnegated(GOOD, text):
        said.add("good")
    return said


# ── reading the listing ─────────────────────────────────────────────────────

def quote(part, kinds, typos=False):
    """The seller's own words for one part of the listing. A long part is cut
    to the few words around what it says: "...battery health 86% small crack
    on the back camera lens" -> "small crack on the back camera lens". typos:
    read as condition_said read it ("one small crak near the camera")."""
    tokens = part.split()
    says = lambda start, end: condition_said(" ".join(tokens[start:end]), typos) & kinds
    end = next((e for e in range(1, len(tokens) + 1) if says(0, e)), None) if len(tokens) > MAX_QUOTE else None
    if end is not None:  # else it's short, or said only by the whole part: kept whole
        start = max(0, next(s for s in range(end - 1, -1, -1) if says(s, end)) - 1)
        cut = start + MAX_QUOTE
        # a fault the cut would end halfway through is said whole: "...it turns on" -> "...it turns on and off"
        plain = lambda end: " ".join(words(" ".join(tokens[start:end])))
        said, whole = plain(cut), plain(start + MAX_FAULT_QUOTE)
        reach = max((m.end() for pattern in (FAULTS, ISSUES) for m in pattern.finditer(whole)
                     if m.start() < len(said) < m.end()), default=0)
        while reach and cut < len(tokens) and len(plain(cut)) < reach:
            cut += 1
        # ...and so is a place the cut would end on "of the": "...on the bottom left of the screen"
        while cut < min(len(tokens), start + MAX_FAULT_QUOTE) and tokens[cut - 1].lower() in DANGLING:
            cut += 1
        tokens = tokens[start:cut]
        # the word kept before the flaw is for "small crack", not "and cracked the back"
        while len(tokens) > 1 and tokens[0].lower().strip(",") in JOINING:
            tokens = tokens[1:]
        while len(tokens) > 1 and tokens[-1].lower() in DANGLING and not ENDS_A_FAULT.search(" ".join(words(" ".join(tokens)))):
            tokens = tokens[:-1]
    return " ".join(tokens).strip(" *-–—:")


# a fault that ends on a word a quote otherwise wouldn't: "it no longer turns ON", "won't switch ON"
ENDS_A_FAULT = re.compile(rf"(?:{FAULTS.pattern})\s*$|(?:{NO_LONGER})\s*$")


def sentence_parts(sentence):
    """A sentence's parts (PARTS), each with whether it's about other items:
    from a mention of them on (OTHER_ITEMS: "Mint, unlike most phones at this
    price which have scratches", "my previous iPhone had suffered water
    damage and stopped working"), until a part comes back to this item
    (THIS_ITEM: "..., this one has a small crack"). What comes before the
    mention is about this item: "Small crack on the back, unlike most listings"."""
    found, other = [], False
    for part in PARTS.split(sentence):
        if OTHER_ITEMS.search(part):
            other = True
        elif other and THIS_ITEM.match(part):
            other = False
        found.append((part, other))
    return found


def this_items_parts(text):
    """The listing's parts that are about this item (sentence_parts)."""
    return [part for sentence in re.split(r"(?<=[.!?])\s+|\n+", text)
            for part, other in sentence_parts(sentence) if not other]


def figures_joined(text):
    """A battery figure apart from its label put next to it, to be read as one
    part: "Battery health\n79%", "Battery health - 82%" and "Battery health
    (82%)" are all "Battery health 82%"."""
    joined = lambda m: m.group(1).rstrip() + " " if SPLITS.search(m.group()[len(m.group(1)):]) else m.group()
    return FIGURE_APART.sub(joined, BRACKETED_FIGURE.sub(lambda m: f" {m.group(1)} ", text)).replace("  ", " ")


@lru_cache(maxsize=4096)
def battery_now(part):
    """The battery health one part of a seller's listing gives as it is now,
    or None: (the figure as code writes it, "84.5"; where the seller's words
    for it start and end in the part, from the battery word to the figure;
    a word that makes it rough, "under" or "around", or ""). A model's name
    or its storage is never the figure ("iPhone 13 battery is good", "64
    battery"), and a figure with no % is one only right after a word for its
    health ("BH 81"). Not a charge level, a limit, the past, a bound upwards,
    a rating, a date or a discount (NOT_HEALTH_BEFORE, NOT_HEALTH_AFTER), and
    two figures are none."""
    figures = read_numbers(part, PHONE, model_names())["battery"]
    lower = part.lower()
    cues = list(BATTERY_CUE.finditer(lower))
    if not figures or not cues:
        return None
    found = []
    for at in FIGURE.finditer(lower):
        value = figure(at.group(1))
        before, after = lower[:at.start()], lower[at.end():]
        if value not in figures or (not at.group(2) and not HEALTH_WORD_BEFORE.search(before)):
            continue
        if NOT_HEALTH_BEFORE.search(before) or NOT_HEALTH_AFTER.search(after) or \
                (IN_PHOTOS_AFTER.search(after) and not HEALTH_WORD.search(lower)):
            continue
        rough = ROUGHLY_BEFORE.search(before)
        start = [cue.start() for cue in cues if cue.end() <= at.start()]
        end = [cue.end() for cue in cues if cue.start() >= at.end()  # "79% Maximum Battery Capacity", "87% original battery"
               and lower[at.end():cue.start()].strip(" %") in ("", "max", "maximum", "original", "genuine", "apple", "oem")]
        if not start and not end:
            continue  # its battery word is somewhere else
        found.append((value, start[-1] if start else at.start(), at.end() if start else end[0],
                      (rough.group(1) or rough.group(2)).lower() if rough else ""))
    return found[0] if len({value for value, *_ in found}) == 1 else None


def esim_read(text):
    """How to read a part of this listing: as it is, or on a phone that only
    comes with eSIM (esim_everywhere) without saying so: "eSIM only" is no flaw
    of an iPhone Air, though the seller's words around it stay as they are."""
    if not esim_everywhere(text):
        return lambda part: part
    return lambda part: ESIM.sub(lambda m: " " * len(m.group()), part)


def low_battery(part):
    """A battery health of LOW_BATTERY or under that one part of the listing
    gives as it is now (battery_now), in the seller's words from its battery
    word to the figure ("Battery health is at 75%", "81% BH", "Battery is
    77%"), or None."""
    said = battery_now(part)
    if not said or float(said[0]) > LOW_BATTERY:
        return None
    return part[said[1]:said[2]].strip(" :=~-–—")


def battery_apart(piece):
    """A piece that gives a low battery, cut into what comes before its words,
    the battery's own words and what comes after: "Battery health 79% small
    crack on back" -> ("", "Battery health 79%", "small crack on back"). None
    for a piece with no low battery."""
    said = battery_now(piece)
    if not said or float(said[0]) > LOW_BATTERY:
        return None
    before = re.sub(r"(?:\s+(?:and|&|plus|with|but|the|a|an|its|his|her|my|is|at|on|of))+\s*$", "", piece[:said[1]])
    return before.strip(" ,;:-–—&+"), piece[said[1]:said[2]].strip(" :=~-–—"), piece[said[2]:].strip(" ,;:-–—&+%")


@lru_cache(maxsize=1)
def models_by_id():
    return {model["id"]: model for model in load_catalogue()}


@lru_cache(maxsize=256)
def esim_everywhere(text):
    """Whether the phone a listing sells comes with eSIM only wherever it's
    sold (the catalogue's "esim_only": the iPhone Air): then saying so is no
    flaw. The phone is the one its title names, else every one the listing
    names: an Air listing that mentions the seller's old iPhone 13 is still
    an Air's."""
    models = models_by_id()
    catalogue = list(models.values())
    named = models_named(re.split(r"\n|(?<=\S)\.\s", text, maxsplit=1)[0], catalogue) or models_named(text, catalogue)
    return bool(named) and all(models[model].get("esim_only") for model in named)


def battery_figure(flaw):
    """The figure of a flaw that's only a low battery, as a reason says it
    ("Battery Health: 80%" -> "80", "Battery health under 80%" -> "under
    80"), or None: "Battery health 79% small crack" says more."""
    apart = battery_apart(flaw)
    if apart is None or PROBLEM.search(f"{apart[0]} {apart[2]}"):
        return None
    value, _, _, rough = battery_now(flaw)
    return f"{rough} {value}".strip()


def read_listing(text):
    """What the listing says about the item's condition, in the seller's own
    words: {"flaws": ["Broken back"], "good": []}. A part
    with a flaw is a flaw even when it also praises: "good condition apart
    from a scratch". A battery health of LOW_BATTERY or under is a flaw too
    ("Battery health 79%"), and "eSIM only" isn't one where every one of the
    model is (esim_everywhere)."""
    text = answered(re.sub(r"\bcondition\s*[:\-–—]\s*", "condition ", text, flags=re.IGNORECASE))  # "Condition: good"
    text = figures_joined(text)
    read_as = esim_read(text)
    found = {"flaws": [], "good": []}
    for part in this_items_parts(text):
        apart = battery_apart(part)  # "Battery health 79% small crack on back": two flaws, each in its own words
        for n, piece in enumerate(apart if apart else (part,)):
            if apart and n == 1:
                found["flaws"].append(piece)
                continue
            said = condition_said(read_as(piece), typos=True)
            if said & FLAWS:
                found["flaws"].append(quote(piece, said & FLAWS, typos=True))
            elif said & set(GOOD_LEVELS):
                found["good"].append(quote(piece, said & set(GOOD_LEVELS), typos=True))
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
    # every flaw is a lower offer's reason, even one the seller says the price allows for ("priced accordingly"): the
    # user chose that on 3 Oct 2026, over leaving such flaws out
    said = read["flaws"]
    if said and kind in ("asking", "lower"):
        figures = {battery_figure(flaw) for flaw in said}
        if kind == "lower" and len(figures) == 1 and None not in figures:  # only the battery: said as AlertFlip says it
            battery = figures.pop()
            return {"about": "battery", "says": [f"battery health {battery}%"], "battery": battery}
        says = said
        if len(figures - {None}) > 1:  # two figures for one battery are none
            says = [flaw for flaw in says if battery_figure(flaw) is None]
        if not says:
            return None
        about = "flaw"
    elif kind == "lower" and battery and float(battery) <= LOW_BATTERY:
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
    if battery_figure(a) or battery_figure(b):  # "81% BH" in the title, "Battery health 81%" below
        return battery_figure(a) == battery_figure(b)
    keys_a, keys_b = key_words(a), key_words(b)
    if not keys_a or not keys_b or condition_said(a) != condition_said(b):
        return False
    return keys_a <= keys_b or keys_b <= keys_a or len(keys_a & keys_b) >= 2


def quoted(point):
    """'"Broken back" and "scratch on the screen"'"""
    return " and ".join(f'"{s}"' for s in point["says"])


def reason_for_ai(point):
    """What the AI is told to give as the reason: the reason flip.wording worded and checked, to use as it is, or the
    listing's own words (quoted)."""
    return f'"{point["worded"]}" (use this reason as it is)' if point.get("worded") else quoted(point)


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
    words are: "the black dot"; a battery figure ("81% BH") when the text
    gives the same one ("the battery health is 81%")."""
    worded = point.get("worded")
    if worded and re.sub(r"\W+", " ", worded.lower()).strip() in re.sub(r"\W+", " ", text.lower().replace("\u2019", "'")):
        return True  # the reason flip.wording worded, said as it is
    point_kinds = condition_said(". ".join([*point["says"], *([worded] if worded else [])]))
    if any(backed(kind, point_kinds) for kind in condition_said(text)):
        return True
    figures = battery_worded(text)
    # a battery figure is said only by the same figure: "the battery health is fine" doesn't say 80%
    return any(not condition_said(part) and (bool(battery_worded(part) & figures) if battery_worded(part)
                                             else mostly_said(part, text)) for part in point["says"])


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


# how the damage happened: a message says it only when the listing does ("dropped once, back cracked"), never
# as a guess ("I know you dropped it", "looks like water damage"), and "never been dropped" is made up too. A
# price that's been dropped, an extra thrown in, someone running over to collect, or the weather isn't damage.
# Each kind: the ways a message says it, then any word of the listing that backs it, typos and all
DROPPED = r"(?:dropp?ed|dropt|knocked|banged|bumped|bashed|crushed|thrown|chucked|smacked|whacked|hit)" \
          r"\b(?!\s+(?:off|round|by|over|me|us)\b)"
CAUSES = {
    "dropped or knocked": (
        re.compile(
            # "it's been dropped", "after being dropped", "it was quite obviously dropped"
            rf"\b(?:been|being|was|were|got|gets|get|is|it'?s)\s+(?:\w+\s+){{0,2}}{DROPPED}"
            # "from dropping it", "clearly dropped at some point": not "drop round", "drop me a line"
            r"|\b(?:dropp?ed|dropt|dropping)\b(?!\s+(?:off|round|by|over|in to|me|us)\b)"
            r"|\b(?:knocked|banged|bumped|bashed|crushed|chucked|thrown|threw)\s+(?:it|them|on|onto|into|down|from|"
            r"against|across|at|off\s+(?:the|a|its|my))\b"
            # "when it fell", "it fell and cracked": not a deal that fell through
            r"|\b(?:fell|fallen)\b(?!\s+(?:through|for|in love)\b)"
            # "had a fall", "a few knocks", "took a nasty tumble", "drop damage", "an accident"
            r"|\b(?:had|took|taken|after|from|in|a|an|few|some|any|of)\s+(?:(?:a|few|couple|of|nasty|bad|big|little|"
            r"small|hard|good)\s+)*(?:drops?|falls?|knocks?|bumps?|tumbles?|bash(?:es)?|accidents?)\b"
            r"|\b(?:had|took|taken)\s+(?:a\s+)?(?:\w+\s+)?(?:hits?|beating|battering|bashing)\b|\bthrough the wars\b"
            r"|\b(?:drop|impact|accident(?:al)?)[\s-]*damage\w*"
            # "it's been sat on" (not "sat on here a while"), "it's been run over" (not "I can run over tonight")
            r"|\bsat on\b(?!\s+(?:here|there|this|the|marketplace|ebay|vinted|gumtree|facebook|for|a|ages|long|my|"
            r"it)\b)|\b(?:been|was|got|being)\s+run over\b|\bran over it\b|\b(?:stood|stepped|trodden|trod) on\b",
            re.IGNORECASE),
        re.compile(r"\b(?:drop\w*|fel{1,2}|fall\w*|knock\w*|knok\w*|bang\w*|bump\w*|bash\w*|hit\w*|crush\w*|chuck\w*|"
                   r"thr[eo]w\w*|tumbl\w*|accident\w*|impact\w*|smack\w*|whack\w*|slip\w*|wars|sat on|stood on|"
                   r"stepped on|trod\w* on|run over|ran over)\b", re.IGNORECASE)),
    "water": (
        re.compile(
            r"\b(?:water|liquid|moisture|sweat|rain|sea|salt\s?water)[\s-]*damage\w*"
            r"|\b(?:underwater|under water|waterlogged|water[\s-]logged)\b"
            r"|\b(?:been|being|was|were|got|gets|get|is|it'?s)\s+(?:\w+\s+){0,2}(?:wet|soaked|submerged|flooded|"
            r"rained on|dunked|drenched|drowned)\b"
            r"|\brained on\b|\b(?:had|took|taken)\s+a\s+(?:swim|dunk|dip|bath)\b"
            r"|\b(?:in|into|through|down|under)\s+(?:the|a)\s+(?:wash|washing machine|bath|toilet|loo|sink|pool|sea|"
            r"puddle|river|lake|drink|pint)\b|\b(?:in|into)\s+water\b"
            r"|\b(?:spill(?:ed|s)?|spilt|moisture|damp)\b|\bliquid\b(?![\s-]+retina)",
            re.IGNORECASE),
        re.compile(r"water|\b(?:liquid|moist\w*|damp\w*|wet|soak\w*|submerg\w*|spill\w*|spilt|wash\w*|bath|toilet|"
                   r"loo|sink|pool|sea|rain\w*|swim\w*|dunk\w*|drench\w*|flood\w*|sweat\w*|puddle\w*|river|lake)\b",
                   re.IGNORECASE)),
}
# a drop or a knock in its clause with the price: "you've dropped your asking price", "knocked it down a bit"
PRICE_TALK = re.compile(r"\b(?:price|prices|asking|reduc\w*|discount\w*|cheaper|(?:down|off|by) a bit|by £|to £|"
                        r"quid)\b|£\d", re.IGNORECASE)
# "in case it's wet" is about what might happen: the rest of the sentence after it says nothing happened
IN_CASE = re.compile(r"\b(?:just )?in case\b[^.?!]*", re.IGNORECASE)
# a cause that might happen, not one that did: "in case it gets wet", "if it's been dropped"
MIGHT_BE = re.compile(r"\b(?:in case|if|unless|whether|so (?:it|they) (?:doesn'?t|don'?t|won'?t)|to (?:keep|stop) it)\b",
                      re.IGNORECASE)


def made_up_causes(said, listing_text):
    """For each way of saying how damage happened that the statements make and
    the listing doesn't back: (kind, the words). [] if none."""
    found = []
    for kind, (in_message, in_listing) in CAUSES.items():
        if in_listing.search(listing_text):
            continue
        words_said = next((m.group() for part in said for m in in_message.finditer(part) if happened(kind, part, m)),
                          None)
        if words_said:
            found.append((kind, words_said))
    return found


def happened(kind, part, match):
    """Whether a cause a statement names is said to have happened to the item:
    not about the price ("dropped your asking price") and not what might ("in case it gets wet")."""
    begins = max(part.rfind(stop, 0, match.start()) for stop in ",.;!?") + 1
    stops = [at for at in (part.find(stop, match.end()) for stop in ",.;!?") if at != -1]
    clause = part[begins:min(stops, default=len(part))]
    if kind == "dropped or knocked" and PRICE_TALK.search(clause):
        return False
    return not MIGHT_BE.search(part[begins:match.start()])


def check_reasons(message, listing_text, point=None):
    """What a message says about the item uses only the listing's words for
    what's wrong with it: "given the stiff hinge" or "Shame about the stiff
    hinge." fails on a listing that doesn't say "stiff". Only words that say
    something's wrong count (flip.checks.PROBLEM), so a reason about you or
    the sale ("as it's cash", "because it's over my budget") is fine, and
    questions are fine. Words code knows ("scratched") are
    check_condition_talk's, reported there. A message also never copies the
    seller's own story ("I dropped it and cracked the back"), nor says how the
    damage happened when the listing doesn't (CAUSES: "I know you dropped it")."""
    # each word cut to 5 letters, its "s" first ("needs" is the listing's "need": the fourth red team, 26 Sep, "because it
    # needs a new battery" was refused on "Need a new battery")
    key = lambda w: (w[:-1] if len(w) > 3 and w.endswith("s") else w)[:5]
    listed = {key(w) for w in words(listing_text)}
    message = IDIOMS.sub(" ", re.sub(r"[’‘ʼ]", "'", message))  # "pay cash on the spot" names no spot
    said = stated_parts(message) + [m.group("reason") for m in REASON_SAID.finditer(message)]
    unbacked = [m.group() for part in said for m in PROBLEM.finditer(part)
                if not condition_said(m.group()) and not {key(w) for w in words(m.group())} <= listed
                and not NEGATED_BEFORE.search(part[:m.start()])]
    problems = [f"the message says what's wrong with it in words the listing doesn't: "
                f"{', '.join(dict.fromkeys(w.lower() for w in unbacked))}"] if unbacked else []
    # the reason flip.wording worded is the listing's own words too, as says_point and the condition checks take it:
    # it keeps what the story cut leaves off ("the screen is quite scratched" from "I will say that the screen is
    # quite scratched", 3 Oct review), and Haiku's check holds it to the rules on stories
    allowed = ([*point["says"], point["worded"]] if point.get("worded") else point["says"]) if point else ()
    story = copied_story(message, listing_text, allowed=allowed)
    if story:
        problems.append(f"the message copies the seller's own story: \"{story}\"")
    # how it happened, as said: the sentences that don't ask, and the reason in the offer's own question (a
    # question of its own, "did it crack because it was dropped?", only asks)
    sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n+", IN_CASE.sub(" ", message)) if s.strip()]
    cause_said = [s for s in sentences if not ends_asking(s)] + \
        [m.group("reason") for s in sentences if "£" in s for m in REASON_SAID.finditer(s)]
    for kind, words_said in made_up_causes(cause_said, listing_text):
        problems.append(f"the message says how it happened ({kind}), which the listing doesn't: \"{words_said}\"")
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
    if kind == "damage":  # what's wrong with the item itself: not "eSIM only" or "untested"
        return bool(listed & (MARKS | {"fault", "damage"}))
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
    listed = condition_said(esim_read(listing_text)(listing_text))
    if point and mention:  # the reason's words are the listing's own (flip.reader checked them): what they say, it says
        listed = listed | set().union(*map(condition_said, point.get("says") or []))  # "no cracks A COUPLE SCRATCHES"
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


# the battery, as a message gives it for a reason: "As the battery is 91% health I'd need to replace it", "BH 91%"
BATTERY_TALK = re.compile(r"\b(?:batter(?:y|ies)|batt|bh|b/h|max(?:imum)? cap(?:acity)?)\b|🔋|"
                          r"\b(?:health|capacity)\b(?=[^.?!]{0,20}?\d{2,3}\s?%)|"  # "the health is 91%"
                          r"\d{2,3}\s?%\s?(?:health|capacity)\b", re.IGNORECASE)  # "it's only at 91% health"
# ...a fault of it, which makes a battery flaw one whatever its figure: "Battery changed last year", "Battery faulty"
BATTERY_FAULT = re.compile(r"\b(?:replac\w*|low|weak|worn|degrad\w*|needs?|dying|drain\w*|poor|bad|struggl\w*|"
                           r"fault\w*|dead|swollen|bulg\w*|service|changed|fitted|swapped)\b|"
                           r"\b(?:(?:doesn|won|isn)[’']?t|not) (?:last|hold)\w*", re.IGNORECASE)
# ...and what makes it a reason, not a word in passing: a figure, or what it needs or does
BATTERY_REASON = re.compile(rf"\d{{2,3}}\s?%|\b(?:health|capacity)\b|{BATTERY_FAULT.pattern}", re.IGNORECASE)
BATTERY_DONT_MIND = re.compile(r"\b(?:doesn|don|won)[’']?t (?:bother|matter|mind)\b|\bnot (?:fussed|bothered|worried)\b|"
                               r"(?<!have to )(?<!need to )(?<!needs to )\b(?:sort|fix|replace) it myself\b|"
                               r"\bno (?:problem|worries|issue)\b|\b(?:isn[’']?t|not) (?:an? )?(?:issue|problem)\b|"
                               r"\bcheck(?:ing)? (?:the |its )?batter", re.IGNORECASE)
# the buyer's own battery, not the listing's: "Need one as my battery keeps dying"
BATTERY_MINE = re.compile(r"\b(?:my|mine)\b[^.?!]{0,15}\bbatter|\bbatter\w*[^.?!]{0,10}\bmine\b", re.IGNORECASE)
# a battery praised, not a reason to pay less: "the battery health is 91% which is great"
BATTERY_GOOD = re.compile(r"(?<!not )(?<!n't )(?<!n’t )(?<!not in )(?<!n't in )\b(?:great|good|fine|excellent|perfect|"
                          r"healthy|strong|brilliant|amazing|mint)\b", re.IGNORECASE)
# the label right before a flaw that names it a battery's: "Battery: needs replacing", "Battery health - poor"
BATTERY_LABEL = re.compile(r"\b(?:batter(?:y|ies)|batt|bh|b/h)(?:\s+(?:health|life|capacity|condition|status))?"
                           r"\s*[:\-–—(=]?\s*$", re.IGNORECASE)
# a listing's battery read a clause at a time, as the drafter reads it (battery_in): not a charge level or the past
BATTERY_CLAUSES = re.compile(r"(?:(?<!\d)\.|\.(?!\d)|[;!?\n()])+|,(?!\d)")
BATTERY_SENTENCES = re.compile(r"(?:(?<!\d)\.|\.(?!\d)|[!?\n])+")
GOOD_FOR_MORE = 86  # a battery at or over this is good condition, a reason to pay more


def battery_figures_now(text):
    """Every battery health a listing gives as it is now ("Battery health 92%,
    phone at 60% battery in the photos" -> {92.0}), from battery_now one
    clause at a time: not a charge level or the past."""
    found = set()
    for sentence in BATTERY_SENTENCES.split(text or ""):
        for clause in BATTERY_CLAUSES.split(sentence):
            said = battery_now(clause) if clause.strip() else None
            if said:
                found.add(float(said[0]))
    return found


def check_battery_reason(message, point, offer=None, listing_text="", title="", kind="lower"):
    """A message gives the battery as a reason only when it is one the
    listing gives (26 Sep: "As the battery is 91% health I'd need to replace
    it" passed on a listing whose flaw is "Face ID not working"). It is one
    when the draft's point is the battery or a flaw of it ("Battery changed
    last year", "Battery: needs replacing" read as "needs replacing"), the
    listing's battery is low (LOW_BATTERY or under) on a lower offer or at
    asking, or, paying more, a good one (GOOD_FOR_MORE or over) said with good
    condition. Talk that isn't a reason is fine: an item that is a battery
    ("the MagSafe Battery Pack", a title with no battery figure), don't-mind
    wording ("battery health doesn't bother me"), praise on a lower offer, and
    questions; the offer's own question counts (offer, in pence). point: the
    point this draft says (None when it says none)."""
    if not isinstance(message, str):
        return []
    # the title's battery words are the item's name only for an item that is one: not "iPhone 12 Pro - Battery 91%"
    named = {w for w in words(title)} if title and not battery_worded(title) and not re.search(r"\d\s?%", title) else set()
    reasons = [part for part in said_in(message, offer)
               if any(m.group().lower() not in named for m in BATTERY_TALK.finditer(part))
               and BATTERY_REASON.search(part) and not BATTERY_DONT_MIND.search(part)
               and not BATTERY_MINE.search(part) and not (kind != "more" and BATTERY_GOOD.search(part))]
    if not reasons:
        return []
    # the point's own battery excuses it when it's a flaw: a fault, or no figure over LOW_BATTERY (not "91%")
    low_or_fault = lambda part: BATTERY_FAULT.search(part) or all(float(f) <= LOW_BATTERY for f in battery_worded(part))
    if point and (point["about"] == "battery" or any((BATTERY_TALK.search(part) or battery_worded(part))
                                                     and low_or_fault(part) for part in point["says"])):
        return []
    if point and any(BATTERY_LABEL.search(listing_text[max(0, at - 40):at])  # the flaw's own label names the battery
                     for part in point["says"] for at in [listing_text.lower().find(part.lower())] if at >= 0):
        return []
    figures = battery_figures_now(listing_text) if listing_text else set()
    said = {float(f) for part in reasons for f in battery_worded(part)}
    if kind in ("lower", "asking") and any(f <= LOW_BATTERY for f in figures) and (not said or said <= figures):
        return []  # the listing's own low battery, a third flaw the point left out
    if kind == "more" and figures and all(f >= GOOD_FOR_MORE for f in figures) and \
            (said <= figures if said else all(BATTERY_GOOD.search(part) for part in reasons)):
        return []  # "...as it's mint, 100% battery", "...with great battery health"
    return ["the message gives the battery as a reason, but it isn't the listing's: its battery isn't one"]
