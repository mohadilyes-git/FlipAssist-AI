"""Find the model in a messy listing title and fill in every fact the catalogue
knows, so the AI only does what code can't. Anything code isn't sure about is
left empty and listed under "missing": a gap is better than a wrong guess."""

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from flip.numbers import read_numbers

DATA = Path(__file__).resolve().parent.parent / "data"

# a listing that's about parts or accessories, or isn't selling anything
NOT_THE_ITEM = ["box only", "case only", "dock only", "charger only", "screen only", "left earbud",
                "right earbud", "left airpod", "right airpod", "ear pads", "earpads", "replacement",
                "no earbuds", "without earbuds", "faceplate", "faceplates", "skin", "skins", "sticker",
                "stickers", "housing", "wanted", "swap"]
# a word right before a model's name means the listing is for something else:
# "case FOR iPhone 13", "screen PROTECTOR iPhone 15"
ACCESSORY_BEFORE = {"for", "fits", "compatible", "protector", "protectors", "glass"}
# a word right after it means the same: "iPhone 13 CASE", "PS5 CONTROLLER"
ACCESSORY_AFTER = {"case", "cases", "cover", "covers", "controller", "controllers", "dualsense", "pad", "pads",
                   "headset", "game", "games", "charger", "cable", "stand", "dock", "remote",
                   "camera", "box", "strap", "mount", "holder", "grip", "grips", "stylus"}
# ...and so do these parts: "PS5 Slim DISC DRIVE", "AirPods Pro 2 CHARGING CASE"
ACCESSORY_AFTER_PHRASES = [["disc", "drive"], ["charging", "case"], ["joy", "con"], ["joy", "cons"], ["joycon"],
                           ["joycons"], ["screen", "protector"], ["screen", "oled"], ["screen", "lcd"],
                           ["screen", "replacement"], ["screen", "assembly"], ["oled", "screen"], ["lcd"],
                           ["logic", "board"], ["motherboard"], ["back", "glass"]]
# words that can follow a name before what's being sold: "AirPods Pro 2ND GEN charging case"
NAME_DESCRIPTORS = {"nd", "rd", "th", "st", "gen", "generation", "usb", "c", "lightning", "magsafe"}
# "iPhone 13 PLUS a charger" is an iPhone 13 and a charger, not an iPhone 13 Plus
PLUS_MEANS_AND = {"a", "an", "the", "case", "cases", "charger", "box", "cable", "free", "original", "postage",
                  "screen", "protector", "earphones", "headphones", "lead", "accessories", "extras", "games",
                  "controller", "controllers", "dock"}
# "a MINI scratch on the back" is a small scratch on an iPhone 13, not an iPhone 13 mini. Only where it can't be
# the name: at the start, after a comma or full stop, or after a word like "a" or "few"; right before a mark,
# with nothing but a space between ("Mini - scratch on back" is the Mini, then the scratch); and not "mini
# scratch free". Read on the text itself, before its dashes and brackets are lost to words()
MARK_NAMES = (r"(?:scratch(?:es|ed|y)?|scratchs|scraches|scracth|scuff(?:s|ed|ing)?|dent(?:s|ed)?|dints?|crack(?:s|ed)?|"
              r"chip(?:s|ped)?|marks?|marked|marking|scrapes?|nicks?|dings?|blemish(?:es)?|imperfections?|wear)")
SMALL_MINI = re.compile(
    r"(^|[,.;:!?\n(]\s*|\b(?:a|an|one|few|couple of|some|small|tiny|minor|light|slight|very|super|two|three|several|"
    r"with|has|have|had|got|and|plus|also)\s+)mini(?=(?:[ \t]+|-)(?:(?:hairline|light|micro|paint|wear|small|tiny|minor|"
    rf"faint|surface)[ \t]+)?{MARK_NAMES}\b(?![ \t-]*free))", re.IGNORECASE | re.MULTILINE)
# letters that aren't a model's: a London postcode ("collection E14"), "E.U.", "U.K.", "U.S.". Read on the
# text itself: "16e" is a name, "16 E14" a postcode, and words() can't tell them apart
NOT_A_LETTER = [(re.compile(r"(?<![a-z0-9])e(?=\d{1,2}(?:\s?\d[a-z]{2})?\b)", re.IGNORECASE), "postcode "),
                (re.compile(r"\b([eu])\.\s?([uks])\.?(?![a-z])", re.IGNORECASE), r"\1\2")]
# single letters that name another model ("iPhone 17e", "S23 U", "it's the e", "U model"), unless they're the
# everyday letter: by the word after ("e-sim", "e-mail", "e.g.", "U.K.", "U/L"), or, away from the model's own
# number, a number after ("London E17") or the word before ("can post to u")
LETTER_NAMES = {"e", "u"}
EVERYDAY_AFTER = {"e": {"sim", "sims", "simcard", "mail", "mails", "bay", "g", "commerce", "book", "books", "reader",
                        "ink"},
                  "u": {"k", "l", "s", "can", "could", "will", "would", "want", "wanna", "need", "are", "r", "know",
                        "get", "like", "have", "may", "might", "should", "must", "just", "pls", "please", "too",
                        "interested"}}
EVERYDAY_BEFORE = {"u": {"to", "for", "with", "thank", "thanks", "ty", "see", "send", "sent", "message", "msg", "let",
                         "ask", "call", "text", "dm", "tell", "give", "show", "if", "when", "do", "can", "will", "are",
                         "did", "got", "c", "cu", "love"}}
# a colour right before one of these is describing something else: "blue CASE",
# "pink LINE", "black COVERS", "natural WEAR"
NOT_ITEM_COLOUR = {"case", "cases", "cover", "covers", "bumper", "skin", "strap", "line", "lines", "spot",
                   "spots", "tint", "mark", "marks", "screen", "display", "light", "cable", "cables",
                   "charger", "lead", "box", "controller", "controllers", "pad", "pads", "dock", "stand",
                   "sleeve", "pouch", "bag", "faceplate", "faceplates", "plates", "shell", "shells", "panels",
                   "wear", "signs", "use"}
# words that can sit between a colour and what it describes: "pink SILICONE case"
DESCRIBING_WORDS = {"silicone", "leather", "clear", "protective", "phone", "rubber", "magsafe", "plastic",
                    "hard", "soft", "glitter", "wallet", "flip", "official", "apple", "genuine", "original",
                    "matching", "carry", "carrying", "travel", "usb", "c", "charging", "lightning", "braided",
                    "spare", "extra"}
# an option word right before one of these is about something else: "disc GAMES",
# "USB-C CABLE", "digital DOWNLOADS", "USB-C TO Lightning"
NOT_AN_OPTION = {"game", "games", "code", "codes", "film", "films", "movie", "movies", "copy", "copies",
                 "cable", "cables", "lead", "leads", "charger", "chargers", "adapter", "adaptor", "plug", "wire",
                 "download", "downloads", "store", "version", "versions", "to"}
# an option word shortly after one of these isn't there: "NO disc drive",
# "it DOESN'T have a disc drive"
NOT_THERE = {"no", "not", "without", "non", "doesn", "t", "lacks", "lacking"}
COMMON_COLOURS = {"black", "white", "grey", "gray", "silver", "gold", "blue", "red", "pink", "green",
                  "purple", "yellow", "orange", "midnight", "starlight", "graphite", "cream", "lavender"}
# worth a warning: the listing may be locked or faulty
FAULT_WORDS = ["icloud", "activation lock", "blacklisted", "barred", "for parts", "spares",
               "faulty", "not working", "doesn't work", "won't turn on", "water damage", "broken"]
# near "unlocked", these mean nobody has checked: "not SURE IF it's unlocked", "seller SAYS unlocked"
DOUBT_WORDS = {"sure", "unsure", "if", "whether", "might", "maybe", "may", "should", "says", "said", "apparently",
               "supposedly", "tbc", "check", "checking", "unconfirmed", "think", "thinks", "probably", "possibly",
               "hopefully", "claims", "claimed"}
BREAK = "|"  # where one part of a sentence ends: no rule reads across it


def load_catalogue():
    return json.loads((DATA / "catalogue.json").read_text(encoding="utf-8"))["models"]


@lru_cache(maxsize=1)
def model_names():
    """Every model name in the catalogue: a size right after another model's name is that model's."""
    return tuple(alias for model in load_catalogue() for alias in model["aliases"])


def load_conditions():
    data = json.loads((DATA / "conditions.json").read_text(encoding="utf-8"))
    del data["about"]
    return data


def words(text, breaks=False):
    """Cut text into lowercase words, splitting letters from numbers.

    "iPhone13 128GB" -> ["iphone", "13", "128", "gb"], so "iphone13",
    "iPhone 13" and "IPHONE-13" all look the same. Accents are dropped
    ("Pokémon" -> "pokemon"). A "+" stuck to a name ("S23+") becomes "plus";
    a "+" on its own ("phone + case") or between numbers ("8GB+256GB") is
    dropped. "'s" is dropped, so
    "it's 23 months" can't read as an S23. With breaks, a comma or full stop
    becomes BREAK, so "Blue, screen perfect" keeps "blue" apart from "screen".
    Brackets aren't breaks: "AirPods Pro (2nd Generation)" is one name.
    """
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"(?<=[a-z0-9])['’ʼ]s\b", "", text)
    text = re.sub(r"(?<=[a-z0-9])\+(?!\d)", " plus ", text)
    if not breaks:
        return re.findall(r"[a-z]+|\d+", text)
    return [BREAK if word in ",.;:!?\n" else word for word in re.findall(r"[a-z]+|\d+|[,.;:!?\n]", text)]


def find_phrase(text_words, phrase_words):
    """Every position where phrase_words appear side by side, in order, in text_words."""
    n = len(phrase_words)
    return [i for i in range(len(text_words) - n + 1) if text_words[i:i + n] == phrase_words]


def contains(text_words, phrase_words):
    return bool(find_phrase(text_words, phrase_words))


def counts(text_words, start, end, not_followed_by=(), skipping=(), not_after=()):
    """True if the phrase at start:end counts:
    - it isn't describing something else: the next word isn't one of
      not_followed_by ("blue CASE"), even with up to 3 skipping words in
      between ("pink silicone CASE");
    - it isn't ruled out by one of the 4 words before it, in the same part of
      the sentence ("NO disc drive", "it DOESN'T have a disc drive")."""
    skipped = 0
    while end < len(text_words) and text_words[end] in skipping and skipped < 3:
        end, skipped = end + 1, skipped + 1
    if end < len(text_words) and text_words[end] in not_followed_by:
        return False
    before = text_words[max(0, start - 4):start]
    if BREAK in before:
        before = before[len(before) - before[::-1].index(BREAK):]
    return not set(before) & set(not_after)


def mentioned(text_words, phrase, not_followed_by=(), skipping=(), not_after=()):
    """True if phrase appears at least once in a way that counts (see counts)."""
    phrase_words = words(phrase)
    return any(counts(text_words, start, start + len(phrase_words), not_followed_by, skipping, not_after)
               for start in find_phrase(text_words, phrase_words))


def rules_out(text_words, not_if, numbers=()):
    """True if a word that means a different model appears: "pro" rules out the
    iPhone 13. Not "plus" meaning "and" ("plus a charger", "plus 2 cases"), not
    "max" in "battery max capacity" or "86% max cap", not "pm" in "after 5pm"
    ("mini" meaning small is written "small" first: as_named). A single
    letter (LETTER_NAMES) is another model unless it's the everyday letter;
    numbers are the model's own ("17" for the iPhone 17): "17e" is always a name."""
    for i, word in enumerate(text_words):
        if word not in not_if:
            continue
        after = text_words[i + 1] if i + 1 < len(text_words) else ""
        before = text_words[i - 1] if i > 0 else ""
        if word == "plus" and (after in PLUS_MEANS_AND or (after.isdigit() and int(after) < 10)):
            continue  # "plus a charger", "plus 2 cases"
        if word == "max" and (after in ("capacity", "cap") or before in ("battery", "health")):
            continue  # "max capacity 86%", "86% max cap"
        if word == "pm" and before.isdigit():
            continue  # "collect after 5pm" isn't a Pro Max
        if word in LETTER_NAMES:
            following = next((w for w in text_words[i + 1:] if w != BREAK), "")
            if following in EVERYDAY_AFTER[word]:
                continue  # "16 e-sim only", "e.g.", "U.K. stock"
            if before not in numbers and ((word == "e" and following.isdigit()) or
                                          before in EVERYDAY_BEFORE.get(word, set())):
                continue  # "collection E17", "can post to u"
        return True
    return False


def as_named(text):
    """The text with what can't be part of a name written plainly: each
    "mini" that means small as "small" (SMALL_MINI: "few mini scratches" ->
    "few small scratches"; "13 mini scratches" stays), and letters that are
    something else (NOT_A_LETTER: "collection E14", "E.U. model")."""
    text = SMALL_MINI.sub(lambda m: m.group(1) + "small", text or "")
    for pattern, plain in NOT_A_LETTER:
        text = pattern.sub(plain, text)
    return text


def name_words(text):
    """The words a model's name is looked for in: words(), breaks kept, after as_named."""
    return words(as_named(text), breaks=True)


def name_numbers(model):
    """The numbers in a model's names: {"17"} for the iPhone 17, {"23"} for the Galaxy S23."""
    return {word for alias in model["aliases"] for word in words(alias) if word.isdigit()}


def is_accessory(text_words, start, end):
    """True if the name at start:end belongs to an accessory or part listing:
    "case FOR iPhone 13", "iPhone 13 CASE", "AirPods Pro 2nd Gen CHARGING CASE"."""
    if start > 0 and text_words[start - 1] in ACCESSORY_BEFORE:
        return True
    while end < len(text_words) and text_words[end] in NAME_DESCRIPTORS:
        end += 1
    after = text_words[end:]
    return bool(after) and (after[0] in ACCESSORY_AFTER or any(after[:len(p)] == p for p in ACCESSORY_AFTER_PHRASES))


def name_matches(text_words, catalogue):
    """Every place a model's name appears and isn't an accessory listing, as
    (start, end, model, ruled_out). Where names overlap only the longest stays:
    "ps 5 slim" beats the "ps 5" inside it."""
    matches = []
    for model in catalogue:
        ruled_out = rules_out(text_words, model["not_if"], name_numbers(model))
        for alias in model["aliases"]:
            alias_words = words(alias)
            for start in find_phrase(text_words, alias_words):
                end = start + len(alias_words)
                if alias_words[-1] in LETTER_NAMES and text_words[end:end + 1] and \
                        text_words[end] in EVERYDAY_AFTER[alias_words[-1]]:
                    continue  # "iPhone 16 e-sim" isn't the 16e
                if not is_accessory(text_words, start, end):
                    matches.append((start, end, model, ruled_out))
    return [m for m in matches
            if not any(o[0] <= m[0] and m[1] <= o[1] and o[1] - o[0] > m[1] - m[0] for o in matches)]


def find_model(text, catalogue):
    """The catalogue model the text is about, or None if unsure.

    1. A listing for parts or accessories, or a wanted/swap post, isn't the item.
    2. A name with "for" right before it, or "case" right after it, is an
       accessory listing, so that match doesn't count.
    3. A longer name beats a shorter one only where they overlap ("ps 5 slim"
       beats the "ps 5" inside it).
    4. A model is ruled out if any of its not_if words appear ("pro" rules out
       the iPhone 13), but its name still counts as "something was named here":
       "iPhone 13 Pro Max" is a product we don't have, not nothing.
    5. The answer is a model only if it's the one thing left. Two products
       named in different places, or one we ruled out, means we can't tell.
    """
    text_words = name_words(text)
    if any(contains(text_words, words(phrase)) for phrase in NOT_THE_ITEM):
        return None
    kept = name_matches(text_words, catalogue)
    if any(ruled_out for *_, ruled_out in kept) or len({m[2]["id"] for m in kept}) != 1:
        return None
    return kept[0][2]


def models_named(text, catalogue):
    """The ids of every model the text names, even one it rules out: "an iPhone
    15, not the pro" names the iPhone 15."""
    return {m[2]["id"] for m in name_matches(name_words(text), catalogue)}


def models_disagree(title, description, catalogue):
    """A warning when the title and the description name different models, and
    neither names the other's ("iphone 15 pro max" over "iPhone 14 for sale"),
    or None. A listing like that may be a mistake, or bait: worth asking about
    before offering on it. Accessories don't count ("fits iPhone 13 cases")."""
    in_title, in_description = models_named(title or "", catalogue), models_named(description or "", catalogue)
    if not in_title or not in_description or in_title & in_description:
        return None
    named = {m["id"]: m["model"] for m in catalogue}
    says = lambda ids: " or ".join(sorted(named[i] for i in ids))
    return f"The title says {says(in_title)} but the description says {says(in_description)}: check which it is"


def sizes_in(text_words):
    """Every '<number> gb/tb' in the text: "128 gb" -> "128GB". For text that
    writes sizes properly, like an AI's description; a listing's own numbers
    are read by flip.numbers."""
    return {number + unit.upper() for number, unit in zip(text_words, text_words[1:])
            if unit in ("gb", "tb") and number.isdigit()}


def find_storage(read, model):
    """The storage size, if the model only comes in one or the title and your
    notes name exactly one real size for it. read: flip.numbers' reading of
    each ("128", "128g" and "128GB" all name 128GB on an iPhone 13)."""
    allowed = model["storage"]
    if len(allowed) == 1:
        # only one size exists. If the text names a different one too ("+ 128GB
        # SD card"), something's off: leave it for you
        stated = set().union(*(r["stated"] for r in read))
        return allowed[0] if stated <= set(allowed) else None
    named = set().union(*(r["storage"] for r in read))  # the model's sizes only: "8GB RAM 256GB" is 256GB
    return named.pop() if len(named) == 1 else None


def find_battery(read):
    """Battery health from your notes (flip.numbers), if they give exactly one figure."""
    return next(iter(read["battery"])) if len(read["battery"]) == 1 else None


def item_colour_mentioned(text_words, name):
    """True if the text uses this colour name for the item itself, not for a
    case, cable or mark ("blue case", "pink silicone case", "pink line")."""
    return mentioned(text_words, name, NOT_ITEM_COLOUR, DESCRIBING_WORDS)


def colours_named(text_words, model):
    """The model's colours the text names, by full or short name. Where one
    name sits inside a longer one ("black" in "jet black"), only the longer counts."""
    aliases = model.get("colour_aliases", {})
    spans = []  # (start, end, colour)
    for colour in model["colours"]:
        for name in [colour, *aliases.get(colour, [])]:
            name_words = words(name)
            for start in find_phrase(text_words, name_words):
                end = start + len(name_words)
                if counts(text_words, start, end, NOT_ITEM_COLOUR, DESCRIBING_WORDS):
                    spans.append((start, end, colour))
    return {colour for start, end, colour in spans
            if not any(o[0] <= start and end <= o[1] and o[1] - o[0] > end - start for o in spans)}


def find_colour(text_words, model):
    """The colour, if the model only comes in one or the text names exactly one."""
    allowed = model["colours"]
    if len(allowed) == 1:
        # only one colour exists. If the text names another, leave it for you
        own = set(words(allowed[0]))
        others = [c for c in COMMON_COLOURS - own if item_colour_mentioned(text_words, c)]
        return None if others else allowed[0]
    named = colours_named(text_words, model)
    return named.pop() if len(named) == 1 else None


def options_named(text_words, model):
    """For each option (Edition, Connector), every value the text names."""
    return {name: {value for value, keywords in values.items()
                   if any(mentioned(text_words, k, NOT_AN_OPTION, not_after=NOT_THERE) for k in keywords)}
            for name, values in model["options"].items()}


def find_options(text_words, model):
    """Each option (Disc/Digital, Lightning/USB-C) the text clearly names."""
    return {name: next(iter(named)) if len(named) == 1 else None
            for name, named in options_named(text_words, model).items()}


# a network named with its lock: "locked to EE", "locked to 02" (a zero for the O), "Vodafone locked". The
# names are eBay's (flip.ebay UK_NETWORKS)
NETWORK_NAMES = {"ee": "EE", "o2": "O2", "02": "O2", "three": "Three", "vodafone": "Vodafone", "voda": "Vodafone",
                 "virgin": "Virgin Mobile", "giffgaff": "giffgaff", "tesco": "Tesco Mobile", "sky": "Sky Mobile",
                 "bt": "BT Mobile", "lebara": "Lebara", "lyca": "Lycamobile", "lycamobile": "Lycamobile",
                 "smarty": "SMARTY", "voxi": "VOXI"}
NETWORK = r"(ee|o2|02|three|vodafone|voda|virgin|giffgaff|tesco|sky|bt|lebara|lyca(?:mobile)?|smarty|voxi)"
LOCKED_TO = re.compile(rf"\b(?:network\s+)?locked\s+(?:to|on(?:to)?)\s+(?:the\s+)?{NETWORK}(?:\s+(?:mobile|network))?\b"
                       rf"|\b{NETWORK}\s+(?:network\s+)?locked\b")


def find_network(text):
    """'Unlocked' only when the text plainly says so, and the network a lock
    names ("locked to EE", "locked to 02": "EE", "O2"). "Not unlocked",
    "never been unlocked", "can be unlocked", "not sure if it's unlocked",
    "seller says unlocked", "unlocked?", a lock with no network named, iCloud
    anywhere, or a network lock and "unlocked" both: that's for you to check.
    Curly apostrophes (iPhone keyboards type "isn’t") count as straight."""
    text = re.sub(r"[’‘ʼ]", "'", text.lower())
    if re.search(r"\b(?:not|never|isn'?t|hasn'?t|wasn'?t|cannot|can'?t|could|be)\s+(?:been\s+|be\s+)?unlocked\b",
                 text):
        return None
    if re.search(r"\b(icloud|blacklisted|barred|activation)\b", text):
        return None
    locked_to = LOCKED_TO.search(text)
    if locked_to and not re.search(r"\bunlocked\b", text):
        before = re.findall(r"[a-z']+", text[max(0, locked_to.start() - 40):locked_to.start()])[-6:]
        return None if set(before) & DOUBT_WORDS else NETWORK_NAMES[next(g for g in locked_to.groups() if g)]
    if re.search(r"\blocked\b", text):
        return None
    tokens = re.findall(r"[a-z']+|[?.]", text)
    for i, token in enumerate(tokens):
        if token != "unlocked":
            continue
        before = tokens[max(0, i - 6):i]
        after = tokens[i + 1:i + 4]
        before = before[len(before) - before[::-1].index("."):] if "." in before else before
        after = after[:after.index(".")] if "." in after else after
        if set(before + after) & DOUBT_WORDS or after[:1] == ["?"]:
            return None
    if re.search(r"\bunlocked\b|\bsim[ -]?free\b", text):
        return "Unlocked"
    return None


def family_of(general, specific):
    """True if one of general's names starts one of specific's: "PS5" is the
    family name of the "PS5 Slim", "iPhone 13" of the "iPhone 13 Pro"."""
    return any(words(long)[:len(words(short))] == words(short)
               for short in general["aliases"] for long in specific["aliases"])


def edition_value(found, only, edition, what, warnings):
    """An edition that only comes one way: fill that value, or leave it for you
    if the text says something else."""
    if found in (None, only):
        return only
    warnings.append(f"the {edition} only comes as {only}: check the {what}")
    return None


def warnings_for(text_words):
    found = [phrase for phrase in FAULT_WORDS if contains(text_words, words(phrase))]
    return [f"mentions {', '.join(found)}: check the condition before listing"] if found else []


def fill_from_catalogue(title, notes, catalogue, description=""):
    """Everything code can fill for one item, plus what it couldn't ("missing")
    and anything you should look at ("warnings").

    The model comes from the title, or your notes if the title doesn't say. If
    your notes name a different model, or rule the model out ("it's the pro"),
    it's left for you. The one exception: a family name in the title and an
    exact name in your notes ("PS5" and "PS5 Slim") mean the exact one. A name
    that fits two models needs a word that settles it ("PS5" alone could be the
    Slim). Everything else is read from both together, numbers by what this
    model's answers can be (flip.numbers: "iPhone 13 128" is 128GB). A phone's
    battery health comes from your notes only: they're the truth about the item.
    The seller's description is read for warnings only ("faulty", "iCloud"):
    it's too chatty to fill facts from.
    """
    title, notes = title or "", notes or ""
    text = f"{title} {notes}"
    text_words = [*name_words(title), BREAK, *name_words(notes)]
    warnings = warnings_for(words(f"{text} {description or ''}"))

    from_title = find_model(title, catalogue)
    from_notes = find_model(notes, catalogue)
    named = models_named(notes, catalogue)
    model = from_title or from_notes
    if from_title and named and named != {from_title["id"]}:
        if from_notes and family_of(from_title, from_notes):
            model = from_notes  # "PS5" in the title, "PS5 Slim" in your notes: the Slim
        else:
            model = None
            warnings.append("the title and your notes name different models")
    if model and rules_out(text_words, model["not_if"], name_numbers(model)):
        model = None
    if model and model.get("confirm_with") and \
            not any(contains(text_words, words(phrase)) for phrase in model["confirm_with"]):
        warnings.append(model["confirm_why"])  # "PS5" alone could be the Slim
        model = None
    if model is None:
        return {"model_id": None, "missing": ["model"], "warnings": warnings}

    # numbers in any model's name ("iPhone 13", "S23") are names, not sizes or figures.
    # In your notes a number on its own can be battery health: "78, few scratches"
    names = [alias for m in catalogue for alias in m["aliases"]]
    read = [read_numbers(title, model, names), read_numbers(notes, model, names, alone=True)]
    filled = {
        "model_id": model["id"],
        "category": model["category"],
        "brand": model["brand"],
        "model": model["model"],
        "storage": find_storage(read, model) if model["storage"] else None,
        "colour": find_colour(text_words, model),
        "options": find_options(text_words, model),
        "network": find_network(text) if model["category"] == "phones" else None,
        "specs": dict(model["specs"]),
    }
    if model["category"] == "phones":
        filled["battery"] = find_battery(read[1])
    # some editions only come one way: the Wolverine PS5 is Digital Edition, 825GB
    rule = model.get("colour_rules", {}).get(filled["colour"])
    if rule:
        filled["storage"] = edition_value(filled["storage"], rule["storage"], filled["colour"], "storage", warnings)
        for name, value in rule["options"].items():
            filled["options"][name] = edition_value(filled["options"][name], value, filled["colour"],
                                                    name.lower(), warnings)
    missing = []
    if model["storage"] and filled["storage"] is None:
        missing.append("storage")
    if filled["colour"] is None:
        missing.append("colour")  # the AI looks at the photo for this one
    missing += [name for name, value in filled["options"].items() if value is None]
    if model["category"] == "phones" and filled["network"] is None:
        missing.append("network")
    filled["missing"] = missing
    filled["warnings"] = warnings
    return filled
