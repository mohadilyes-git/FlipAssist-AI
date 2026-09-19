"""Writing an offer message with no AI: your own sentences (the phrasebook
in your style card), the price code set, the listing's flaw or good condition
in the seller's words, and the questions the listing leaves open.

Before you have any past messages it writes AlertFlip's messages (the
app's seller-message function): "Hi, would you take £235 cash for it? I'm
offering that because the battery health is 80%. I can come and collect."
Cash and collecting only on Facebook and Gumtree; on eBay and Vinted you pay
through the site and it's posted.

In a blind test on 18 Aug 2026 (252 drafts, 3 judges each) this beat the AI
drafter for a reseller with no past messages (judged best 97% of the time)
and for one whose messages repeat (88%). For a chatty reseller whose
messages all differ it was a coin flip, so the AI writes for them
(flip.message_drafter decides). Nothing here can make anything up: every
word is yours, the seller's or one of the fixed phrases below, and once you
have past messages it never offers to collect unless they do. When the seller's words
don't fit a sentence it knows how to write ("I dropped it and cracked the
back"), it writes nothing and the AI gets its turn.
"""

import re
from functools import lru_cache

from flip.catalogue import load_catalogue, model_names
from flip.checks import ASKS_YOU, HOLD, SIGN_OFF, ends_asking
from flip.prompts import offer_words
from flip.style import opening

# the offer in plain words, for when your messages have no habit for it
NEUTRAL = {"lower": "would you take £[OFFER] for it?", "asking": "I can pay £[OFFER] for it.",
           "more": "I can pay £[OFFER] if you can hold it for me."}
GREETING = "Hi"
# with no past messages: AlertFlip's opener, offer sentence and closing. On Facebook and Gumtree you come
# and collect and pay cash...
LOCAL = {"lower": ("Hi,", "would you take £[OFFER] cash for it?", "I can come and collect."),
         "asking": ("Hi, is this still available?", "I'll pay the full £[OFFER] cash and can come and collect.",
                    "Could you hold it for me?"),
         "more": ("Hi,", "I'll pay £[OFFER] cash if you take the listing down and sell it to me.",
                  "I can come and collect.")}
# ...and on eBay, Vinted or anywhere else it's paid through the site and posted: neither is said
POSTED = {"lower": ("Hi,", "would you take £[OFFER] for it?", ""),
          "asking": ("Hi, is this still available?", "I'm happy to pay the full £[OFFER].", "Could you hold it for me?"),
          "more": ("Hi,", "I'll pay £[OFFER] if you take the listing down and sell it to me.", "")}
FILLER = "Let me know what you think."
MAX_FLAW = 12  # words of the seller's to say back
# a flaw quoted from the listing that starts with a verb goes after "that it": "that it doesn't charge"
VERB_START = re.compile(r"^(?:(?:randomly|sometimes|often|occasionally|constantly|keeps?) )?"
                        r"(?:has|have|had|is|isn'?t|was|wasn'?t|does|doesn'?t|did|didn'?t|won'?t|can'?t|cannot|"
                        r"needs?|comes|works|turns|only|stopped|stops|restarts|crashes|freezes|cuts|shuts|switches|"
                        r"dies|drains|overheats)\b", re.IGNORECASE)
ARTICLE = re.compile(r"^(?:a|an|some|the|one|two|2)\b", re.IGNORECASE)
# ...and one with a verb in it goes after "that the": "that the left joycon drifts", "that the hinge is stiff"
VERB_INSIDE = re.compile(r"\b(?:is|are|was|were|has|have|doesn'?t|don'?t|won'?t|can'?t|needs?|keeps|drifts|"
                         r"crackles|rattles|flickers|sticks|buzzes|squeaks|wobbles|lags|freezes|overheats|drains|cuts|"
                         r"stops|restarts|crashes|shuts|switches|dies|skips|leaks|hisses)\b", re.IGNORECASE)
# a part and what's wrong with it, the seller's short way: "Screen cracked", "Back glass smashed", "Ear
# cushions worn", "Face ID not working" -> "the screen is cracked"
STATES = (r"(?:slightly |a bit |very |quite |badly |really )?(?:cracked|smashed|shattered|damaged|broken|faded|worn|"
          r"scratched|chipped|dented|marked|scuffed|bent|stuck|loose|stiff|missing|faulty|dead|swollen|lifting|"
          r"peeling|discoloured|discolored|yellowed|not working|not charging|not turning on)")
PART_STATE = re.compile(rf"^(?P<part>(?:[\w-]+ ){{0,3}}[\w-]+?) (?P<state>{STATES})$", re.IGNORECASE)
# "Screen: cracked", "Back: small crack": a seller's label and what's wrong
LABELLED = re.compile(r"^(?P<label>[A-Za-z][A-Za-z ]{1,24}?)\s*[:=]\s*(?P<value>\S.*)$")
# labels that only say a flaw follows: "Condition: cracked screen", "Damage: small dent"
GENERAL_LABELS = {"condition", "damage", "fault", "faults", "issue", "issues", "problem", "problems", "defect",
                  "defects", "cosmetic", "cosmetics", "note", "notes", "flaw", "flaws", "marks", "wear"}
# what isn't the flaw in a seller's quote (clean_flaw): emojis and bullets anywhere...
NOT_WORDS = re.compile("[\U0001F300-\U0001FAFF☀-➿•►▪→|*#~]+")
# ...a lead-in: "Good condition with light scratches", "Only issue: small scratch", "The only issue is a scratch"
LEAD_IN = re.compile(r"^(?:(?:in )?(?:very |really )?(?:good|great|lovely|excellent|decent|nice|fair|ok|okay|reasonable|"
                     r"used|average|working)(?: used)? (?:condition|nick|shape|order)\s*(?:with|but|apart from|"
                     r"except|just)?|(?:the )?only (?:real )?(?:issues?|problems?|faults?|things?|flaws?|downsides?|"
                     r"damage)(?:\s+(?:is|are|being))?|only|just|condition)\s*[:\-–,]?\s+", re.IGNORECASE)
# ...what comes after it: how it still works, an aside, a price, the next thing in a run-on ("cracked screen
# works perfect collection only leeds", "scratch on screen not noticeable when on", "costs £80 to fix")
AFTER_FLAW = re.compile(
    r"\s(?:[£$€]\s?\d|\d+\s?(?:quid|pounds)\b)|\s[-–—]\s|\s(?<!not )(?<!isn't )(?<!isnt )(?<!doesn't )(?<!doesnt )"
    r"(?<!stopped )(?<!stops )(?<!keeps )(?:still |fully |all )?(?:works?|working|functions?|functional)\b"
    r"|\s(?:doesn'?t|does not|won'?t|will not) (?:affect|effect|impact)\b|\s(?:not|hardly|barely) (?:noticeable|visible)\b"
    r"|\s(?:nothing (?:major|serious|bad)|see (?:pics?|photos?|pictures?|images?)|selling|collection|collect|"
    r"pick ?up|no offers|unlocked|battery(?: health)? \d+|otherwise|but|so (?:price|selling|cheap|priced)|hence|which|"
    r"that|when|where|you can|costs?|would cost|to fix|to repair|price|reduced|ono|ovno|firm|everything)\b",
    re.IGNORECASE)
KISSES = re.compile(r"\s+x{1,3}$", re.IGNORECASE)
# a quote never ends on one of these: "...on the bottom left of the"
DANGLING = {"of", "the", "a", "an", "on", "in", "at", "to", "with", "and", "or", "near", "by", "from", "for", "is", "are",
            "has", "have", "but", "so", "its", "it", "my", "your", "very", "quite", "slightly", "&"}
# names keep their capitals when a shouted or Title Case quote is lowered
CAPITALS = {"face id": "Face ID", "touch id": "Touch ID", "hdmi": "HDMI", "usb": "USB", "usb-c": "USB-C", "sim": "SIM",
            "oled": "OLED", "lcd": "LCD", "ios": "iOS", "iphone": "iPhone", "ipad": "iPad", "airpods": "AirPods",
            "airpod": "AirPod", "macbook": "MacBook", "ps5": "PS5", "ps4": "PS4", "joy-con": "Joy-Con", "joy-cons": "Joy-Cons"}
# words a listing's title has before the flaw that aren't the flaw: "iPhone 11 64GB Unlocked back glass cracked"
# a title word with one of these after it is the flaw's own: "locked TO EE", "used WITH care"
TIED_ON = {"to", "on", "with", "by", "for", "from", "in", "at"}
TITLE_WORDS = {"unlocked", "locked", "used", "boxed", "new", "sim", "free", "simfree", "grade", "refurbished",
               "smartphone", "phone", "mobile", "apple", "samsung", "google", "sony", "nintendo", "microsoft",
               "console", "network", "ee", "o2", "vodafone", "three", "gb", "tb", "edition", "disc", "digital"}
# a part whose first word is also a model's: "disc drive", "back glass"
PART_NAMES = {"disc drive", "back glass", "home button", "power button", "side button", "charging port", "charge port",
              "face id", "touch id", "screen protector", "pro controller"}
# "It's cracked", "There's a crack": the subject the sentence gets from the seller
SUBJECT = re.compile(r"^(?:(it'?s|it is)|(it has|it'?s got|has got)|(there'?s|there is|there are))\s+", re.IGNORECASE)
# a seller's run-on: a second clause with no full stop, "the screen it turns on and off" -> "the screen – it turns..."
RUN_ON = re.compile(r"(?<=\w) (it|which) (?=(?:turns|keeps|won'?t|doesn'?t|can'?t|goes|stops|cuts|switches|shuts|"
                    r"restarts|freezes|lags|flickers|drains|dies|has|had|needs)\b)", re.IGNORECASE)
# "one issue with the screen" says "the issue": "given one issue..." doesn't read
ONE_ISSUE = re.compile(r"^(?:one|1)\s+(issue|problem|fault)\b", re.IGNORECASE)
# a seller's own story ("I dropped it", "my son cracked it") isn't yours to say
FIRST_PERSON = re.compile(r"\b(?:I|I'?ve|I'?m|I'?d|[Mm]y|[Mm]e|[Mm]ine|[Ww]e|[Ww]e'?ve|[Oo]ur|us)\b")
SPARES = re.compile(r"\bfor parts\b|\bspares(?:\s*(?:or|and|/|&)\s*repairs?)?\b|\brepairs?\b", re.IGNORECASE)
NEGATED_SPARES = re.compile(r"\b(?:not|no|never|isn'?t)\s+(?:sold\s+)?(?:as\s+|for\s+)?(?:spares|repairs|parts)\b",
                            re.IGNORECASE)
# adjectives on their own: "Faulty", "Slightly scratched", "Cracked and scratched", "Bent"
JUST_SAYS = re.compile(r"^(?:(?:slightly|lightly|a bit|bit|very|quite|heavily|badly|really)\s+)?"
                       r"(?:cracked|scratched|scuffed|dented|chipped|faulty|bent|broken|damaged|worn|marked|stained|"
                       r"smashed|shattered|loose|stiff|dead|unlocked|locked|blacklisted|swollen)"
                       r"(?:\s+(?:and|&)\s+(?:cracked|scratched|scuffed|dented|chipped|faulty|bent|broken|damaged|worn|"
                       r"marked|stained))?$"
                       r"|^(?:network\s+)?locked\s+to\s+\S+$", re.IGNORECASE)  # "that it's locked to EE"
NO_FAULT = re.compile(r"^no\s+(?:sound|power|picture|signal|display|image|wifi|charge|charging|service|audio|video|"
                      r"face id|touch id)\b", re.IGNORECASE)
# good condition in a shape this can say: "as it's in excellent condition"
GOOD_CONDITION = re.compile(r"\b((?:very |really )?(?:good|great|excellent|mint|perfect|lovely|immaculate|flawless|"
                            r"pristine|fab|fantastic|brilliant|top|decent|nice|amazing|superb|like new))\s+"
                            r"(?:condition|nick|shape)\b"
                            r"|\bcondition\s*(?:is\s*|:\s*)?(?:very |really )?(good|great|excellent|mint|perfect|"
                            r"lovely|immaculate|flawless|pristine)\b", re.IGNORECASE)
GOOD_AS_IS = re.compile(r"^(?:barely|hardly) used$|^well looked after$|^not a (?:mark|scratch) on it$", re.IGNORECASE)
# good condition in one word: "Mint", "Like new", "Immaculate, boxed"
GOOD_WORD = re.compile(r"^(?:in )?(mint|immaculate|pristine|flawless|perfect|like new|as new)(?: condition)?$", re.IGNORECASE)
# for an offer at or over asking, nothing that calls it low: "I know it's a bit cheeky"
LOWBALL = re.compile(r"\b(?:cheeky|cheek|lowball|low ball|low offer|lowest|sorry|under (?:the |your )?asking|go lower|"
                     r"wiggle|cheap|bit low|too low|less than (?:you'?re |your )?asking|(?:a )?bit under|"
                     r"insult\w*|worth a (?:shot|try)|hope (?:that'?s|it'?s|this is) ok|i know it'?s (?:less|lower|under))\b",
                     re.IGNORECASE)
# what may follow the price in "I can pay £X ...": nothing else from a question makes sense there
SAFE_TAIL = re.compile(r"^(?:\s*(?:cash(?: on collection| in hand)?|for (?:it|this|them|these)|on collection))?\s*$",
                       re.IGNORECASE)
SENTENCES = re.compile(r"(?<=[.!?])\s+|(?<=[.!?][\U0001F300-\U0001FAFF☀-➿])\s+")  # "£170?😊 Can collect" is two
# a greeting at the start of a sentence, as typed, with or without a comma: "Hi mate, ", "Hi mate ", "Hiya 👋 "
LEADING_GREETING = re.compile(r"(?:hi|hiya|hello|hey|alright|morning|afternoon|evening|yo)\b(?:\s+(?:mate|there|bro|"
                              r"pal|buddy|m8|hun|all))?(?:\s*[,!.?\-–—]+\s*|\s*[\U0001F300-\U0001FAFF☀-➿]+\s*|\s+)",
                              re.IGNORECASE)
# an offer asked without its "?": "would you take £170 cash.", "how about £220 cash"
ASKS_OFFER = re.compile(r"(?:would|could|will|can|do|does)\s+(?:you|u|ya)\b|(?:how|what) about\b|any chance\b|"
                        r"would\s+£", re.IGNORECASE)
# the asking price named in an offer sentence: "I'll pay the full asking of £[OFFER]", "the full £[OFFER]"
FULL_ASKING = re.compile(r"\b(?:the\s+)?full(?:\s+asking)?(?:\s+price)?(?:\s+of)?(?=\s+£)|\basking(?:\s+price)?"
                         r"(?:\s+of)?(?=\s+£)", re.IGNORECASE)
# an over-asking offer that already says why: "if you can save it for me"
HELD = re.compile(r"\b(?:hold|save|keep|reserve|put (?:it )?aside|set (?:it )?aside)\b|take (?:it|the (?:ad|advert|"
                  r"listing|post)) down|end (?:the |your )?listing|off the market", re.IGNORECASE)
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


@lru_cache(maxsize=1)
def model_words():
    """Every word of a model's name in the catalogue, and the words titles add (TITLE_WORDS)."""
    return {word for name in model_names() for word in name.split()} | TITLE_WORDS


@lru_cache(maxsize=1)
def colour_words():
    """Every word of a colour in the catalogue: "Midnight", "Space Grey"."""
    return {word.lower() for model in load_catalogue() for colour in model.get("colours", []) for word in colour.split()}


def calmed(part):
    """A shouted or Title Case quote in lower case, names kept: "SCREEN CRACKED" -> "screen cracked",
    "Small Crack On Back" -> "small crack on back", "FACE ID BROKEN" -> "Face ID broken"."""
    letters = [w for w in re.findall(r"[A-Za-z][A-Za-z-]*", part)]
    shouted = len(letters) > 1 and all(w.isupper() for w in letters if len(w) > 1)
    titled = len(letters) > 1 and all(w[0].isupper() for w in letters) and not shouted
    if not (shouted or titled):
        return part
    lowered = " ".join(w if titled and len(w) > 1 and w.isupper() else w.lower() for w in part.split())
    for name, written in CAPITALS.items():
        lowered = re.sub(rf"\b{re.escape(name)}\b", written, lowered, flags=re.IGNORECASE)
    return lowered


def untitled(part):
    """A flaw from a listing's title without the model, its specs and its colour before it, or its storage
    after it: "iPhone 11 64GB back glass cracked" -> "back glass cracked", "iPhone 13 cracked back 128GB" ->
    "cracked back". A flaw that starts with its own part ("Screen cracked") keeps every word."""
    tokens = part.split()
    known, title = model_words(), False
    while len(tokens) > 1 and (re.search(r"\d", tokens[0]) or tokens[0].lower().strip(",-–") in known) \
            and " ".join(tokens[:2]).lower() not in PART_NAMES \
            and tokens[1].lower() not in TIED_ON:  # "PS5 disc drive not working": the drive's; "locked to EE" stays
        tokens, title = tokens[1:], True
    while title and len(tokens) > 1 and tokens[0].lower().strip(",-–") in colour_words():  # "iPhone 13 Midnight ..."
        tokens = tokens[1:]
    while len(tokens) > 1 and re.fullmatch(r"\d+\s?(?:gb|tb)|[£$€]?\d+(?:\.\d+)?", tokens[-1], re.IGNORECASE):
        tokens = tokens[:-1]
    return " ".join(tokens)


def clean_flaw(part):
    """A seller's quote cut to the flaw, every word kept as it was written:
    no emojis, bullets or kisses, no lead-in ("Good condition with", "Only
    issue:"), no model before it or aside after it ("...still works fine",
    "...see pics", "...costs £80 to fix", "...that you can only see"), a
    label put in order ("Screen: cracked" -> "Screen cracked", "Back: small
    crack" -> "small crack on the back"), and shouting or Title Case lowered."""
    part = re.sub(r"\s+", " ", NOT_WORDS.sub(" ", part)).strip(" .,!;:-–—")
    labelled = LABELLED.match(part)
    if labelled:
        label, value = labelled.group("label").strip(), labelled.group("value").strip()
        part = value if set(label.lower().split()) & GENERAL_LABELS else \
            f"{label} {value}" if re.fullmatch(STATES, value, re.IGNORECASE) else f"{value} on the {label.lower()}"
    for _ in range(2):  # "In used condition with marks", "Only issue: small scratch"
        part = LEAD_IN.sub("", part, count=1)
    aside = AFTER_FLAW.search(part, 1)  # after the flaw starts: "Selling for parts" is one
    part = (part[:aside.start()] if aside else part).strip()
    part = KISSES.sub("", untitled(calmed(part))).strip(" .,!;:-–—")
    tokens = part.split()
    while tokens and tokens[-1].lower() in DANGLING:
        tokens = tokens[:-1]
    return " ".join(tokens)


def flaw_phrase(part):
    """One flaw in the seller's words, to go after "given", "because" or "I
    don't mind": 'the broken back', 'that it doesn't charge', 'that the
    hinge is stiff', "that it's cracked", 'that the screen is cracked'. The
    quote is cleaned first (clean_flaw). None when the words don't fit a
    sentence: the seller's own story ("I dropped it"), a denied fault ("not
    spares or repairs"), nothing left that says what's wrong, or more words
    than a reason should have."""
    part = clean_flaw(part)
    if not part or FIRST_PERSON.search(part) or len(part.split()) > MAX_FLAW:
        return None
    part = RUN_ON.sub(r" – \1 ", ONE_ISSUE.sub(r"the \1", part))
    spares = SPARES.search(part)
    if spares:  # in the seller's own words: "for parts", "spares or repairs"
        return None if NEGATED_SPARES.search(part) else \
            "that it's sold for parts" if "part" in spares.group().lower() else f"that it's sold as {spares.group().lower()}"
    if JUST_SAYS.match(part):
        return f"that it's {lower_first(part)}"  # "that it's faulty", "that it's slightly scratched"
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
    if re.match(r"got\b", part, re.IGNORECASE):
        return f"that it's {part}"  # "that it's got a small crack"
    if VERB_START.match(part):
        return f"that it {part}"
    if VERB_INSIDE.search(part):
        return f"that {part}" if ARTICLE.match(part) else f"that the {part}"
    state = PART_STATE.match(part)
    if state and not ARTICLE.match(part):  # "Screen cracked" -> "that the screen is cracked"
        thing = state.group("part")
        plural = re.search(r"[^su]s$", thing) and not re.search(r"\b(?:glass|chassis|series|lens)$", thing, re.IGNORECASE)
        return f"that the {thing} {'are' if plural else 'is'} {state.group('state')}"
    if re.match(r"\w+(?:ed|en|s)\s+(?:the|a|an|its|his|her)\b", part, re.IGNORECASE):
        return None  # "cracked the back": a deed, not a flaw this can name; the AI words it
    if len(part.split()) == 1 and re.search(r"(?:ed|en)$", part):
        return f"that it's {part}"  # "cracked"
    if re.match(r"(?:few|couple)\b", part, re.IGNORECASE):
        return f"a {part}"  # "a few scratches on the back"
    return part if ARTICLE.match(part) else f"the {part}"


def flaw_words(says):
    """The listing's flaws together: 'the broken back and the cracked screen',
    or None if one of them can't be said (flaw_phrase)."""
    phrases = [flaw_phrase(part) for part in says]
    return None if None in phrases else " and ".join(phrases)


def reason_sentence(point):
    """A lower offer's reason in a sentence of its own, as AlertFlip gives it:
    "I'm offering that because the battery health is 80%.", "...because of
    the broken back.", "...because it doesn't charge." None if the listing's
    words can't be said (flaw_phrase)."""
    if point["about"] == "battery":
        return f"I'm offering that because the battery health is {point['battery']}%."
    phrases = [flaw_phrase(part) for part in point["says"]]
    if None in phrases:
        return None
    things = [p for p in phrases if not p.startswith("that ")]  # "the broken back"
    facts = [p[len("that "):] for p in phrases if p.startswith("that ")]  # "it doesn't charge"
    said = ([f"of {' and '.join(things)}"] if things else []) + ([" and ".join(facts)] if facts else [])
    return f"I'm offering that because {' and because '.join(said)}."


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
    word = GOOD_WORD.match(part)
    if word:
        said = word.group(1).lower()
        return f"it's in {said} condition" if said == "mint" else f"it's {said}"
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


def split_greeting(sentence):
    """A sentence's greeting, as typed with what follows it, and the rest:
    ("Hi mate, ", "would you take £[OFFER]?"), ("Hi mate ", "I can pay..."),
    ("Hi mate 👋 ", ...); ("", sentence) when it doesn't open with one."""
    found = LEADING_GREETING.match(sentence)
    return (found.group(), sentence[found.end():]) if found and found.end() < len(sentence) else ("", sentence)


def asks(sentence):
    """Whether a sentence asks, with or without its "?": "would you take £170 cash." does."""
    core = split_greeting(split_sign_off(sentence)[0])[1]
    return ends_asking(core) or bool(ASKS_OFFER.match(core))


def as_statement(sentence):
    """At or over the asking price the offer is said, not asked:
    'Would you take £[OFFER] cash?' -> 'I can pay £[OFFER] cash.' Only a safe
    ending is kept after the price ("cash", "for it"), and your greeting as
    you type it and the sign-off: "...£[OFFER]?😊" -> "...£[OFFER]. 😊"."""
    core, sign = split_sign_off(sentence)
    if not asks(core) or "[OFFER]" not in core:
        return sentence
    greeting, _ = split_greeting(core)
    tail = re.sub(r"^\s*(?:quid|pounds)\b", "", core[core.index("[OFFER]") + len("[OFFER]"):].rstrip(" ?.!"))
    tail = tail if SAFE_TAIL.match(tail) else ""
    return f"{greeting}I can pay £[OFFER]{tail}.{' ' + sign if sign else ''}"


def as_question(sentence):
    """Under the asking price the offer is asked, not said: 'I can pay
    £[OFFER] cash.' -> 'Would you take £[OFFER] cash?', for when your usual
    sentence is one you write paying asking. Only a safe ending is kept after
    the price, and your greeting and sign-off: 'Hi mate, I can pay £[OFFER]. 👍'
    -> 'Hi mate, would you take £[OFFER]? 👍'."""
    core, sign = split_sign_off(sentence)
    if asks(core) or "[OFFER]" not in core:
        return sentence
    greeting, _ = split_greeting(core)
    tail = re.sub(r"^\s*(?:quid|pounds)\b", "", core[core.index("[OFFER]") + len("[OFFER]"):].rstrip(" .!"))
    tail = tail if SAFE_TAIL.match(tail) else ""
    ask = f"would you take £[OFFER]{tail}?"
    return f"{greeting + ask if greeting else ask[:1].upper() + ask[1:]}{' ' + sign if sign else ''}"


def held(sentence):
    """Over asking, the reason to pay more: "I can pay £[OFFER] cash." -> "I can
    pay £[OFFER] cash if you can hold it for me.", before any sign-off. Once:
    your own reason stays ("if you can save it for me"), and a condition of
    another kind gives way to it ("£[OFFER] if that's ok" -> "£[OFFER] if you can hold it for me")."""
    core, sign = split_sign_off(sentence)
    if HELD.search(core):
        return sentence
    core = re.sub(r"\s+if\b.*$", "", core.rstrip(" .!?"), flags=re.IGNORECASE)
    return f"{core} if you can hold it for me.{' ' + sign if sign else ''}"


def with_reason(sentence, kind, point):
    """The listing's point in the offer sentence (lower, more) or after it
    (asking), before any sign-off the sentence ends with. None if the
    listing's words can't be said (flaw_words, good_words)."""
    if not point:
        return sentence
    said = good_words(point["says"]) if kind == "more" else \
        f"that the battery health is {point['battery']}%" if point["about"] == "battery" else flaw_words(point["says"])
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
    # after "collect it" if it says so: "Can collect it from Leeds LS6 today."
    return re.sub(r"\bcollect(?:\s+(?:it|them|this))?\b", lambda m: f"{m.group()} from {pickup}", closing, count=1,
                  flags=re.IGNORECASE)


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
    return text[:1].upper() + text[1:]  # a message starts with a capital, whatever its first sentence


def priced(text, offer):
    return text.replace("£[OFFER]", offer_words(offer)).replace("[OFFER]", f"{offer // 100:,}")


def default_offer(kind, offer, point=None, questions=(), at_least=0, item="item", pickup="", in_person=False,
                  cash=True):
    """With no past messages, the message AlertFlip writes (LOCAL, POSTED):
    the reason for a lower offer in a sentence of its own, and at or over
    asking after the offer as with your own sentences. in_person: on Facebook or
    Gumtree, where you come and collect (from the listing's pickup place)
    and pay cash. cash: False when the listing says no cash ("would you take
    £[OFFER] for it?"). None if the listing's point can't be said."""
    opener, offer_sentence, closing = (LOCAL if in_person else POSTED)[kind]
    if not cash:
        offer_sentence = re.sub(r"\s+cash\b", "", offer_sentence)
    offer_sentence, closing = collecting_from(offer_sentence, pickup), collecting_from(closing, pickup)
    if kind == "lower" and point:
        reason = reason_sentence(point)
        middle = [offer_sentence, reason]
    else:
        reason = with_reason(offer_sentence, kind, point)
        middle = [reason]
    if reason is None:
        return None
    return priced(fit(opener, [*middle, *merge_questions(questions)], closing, at_least, item), offer)


def write_offer(card, kind, offer, point=None, questions=(), at_least=0, item="item", pickup="", in_person=False,
                cash=True):
    """One offer message from your phrasebook (card["phrases"]), or, if you
    have no past messages, AlertFlip's (default_offer); None if the listing's
    point can't be said in a sentence this knows (then the AI writes).
    point: the listing's flaw, low battery or good condition to give as the
    reason (flip.offers), only when it's to be said. questions: the open
    ones, for a longer message. at_least: the words a longer message needs.
    item: what to call the item. pickup: where the listing says to collect.
    in_person: a Facebook or Gumtree listing (local_market). cash: False when
    the listing says no cash (your own sentences then come without it: the drafter's without_cash)."""
    if not card:
        return default_offer(kind, offer, point, questions, at_least, item, pickup, in_person, cash)
    phrases = card.get("phrases") or {}
    opener = phrases.get("opener")
    # your greeting sat in your offer sentence ("Hi mate, would you take..."): with that sentence gone, it opens
    opener = opener if opener is not None and (opener or phrases.get("offer")) else f"{card.get('greeting') or GREETING},"
    # how you word this kind of offer, else your usual offer sentence made to fit it, else a neutral one
    offer_sentence = phrases.get(f"offer_{kind}") or phrases.get("offer") or NEUTRAL[kind]
    if kind == "lower":  # under asking it's asked: "I can pay £70" from your asking-price habit would tell them
        offer_sentence = as_question(offer_sentence)
    if kind == "more" and not phrases.get("offer_more"):  # over asking isn't "the full asking of £235"
        offer_sentence = re.sub(r"\s{2,}", " ", FULL_ASKING.sub("", offer_sentence))
    closing = collecting_from(phrases["closing"], pickup) if phrases.get("closing") else ""
    if kind != "lower":  # at or over asking: said, and never called low
        offer_sentence = as_statement(offer_sentence)
        if LOWBALL.search(offer_sentence):
            offer_sentence = NEUTRAL[kind]
        opener = opener if not LOWBALL.search(opener) else f"{card.get('greeting') or GREETING},"
        closing = closing if not LOWBALL.search(closing) else ""
    if kind == "more" and not point and not HOLD.search(offer_sentence):
        offer_sentence = held(offer_sentence)  # paying over asking says why
    greeting, rest = split_greeting(offer_sentence)
    if opener and LEADING_GREETING.match(opener) and greeting:  # one greeting: the opener's ("Hi mate, hi mate, would...")
        offer_sentence = rest[:1].upper() + rest[1:]
    elif not opener and not greeting and card.get("greeting"):  # your greeting sits in your other kinds' sentence
        opener = f"{card['greeting']},"
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
    new = merge_questions([q for q in questions if not asked_already(q, previous)])  # each one on its own first
    return fit(opener, [*body, *new], closing, at_least, item, already=previous)
