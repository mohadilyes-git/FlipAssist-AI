"""The numbers in a listing, read by what this product's answers can be.

Once code knows the model, it knows what a number could be. An iPhone 13 comes
in 128, 256 or 512 GB, so the 128 in "iPhone 13 128" is its storage, "GB" or
not; and a phone's battery health is a figure up to 100. Every number gets one
job at most:

1. Numbers that belong to something else are taken out first: a model's name
   (the 13 in "iPhone 13"), a size right after another model's name ("upgraded
   to an iPhone 15 Pro 256GB"), prices ("£128", "128 ono", "bought 128", "sell
   85"), time ("90 days"), distances ("75 miles"), addresses ("77 High Street",
   "128 Elm Close"), codes stuck to letters ("BH21", "A2482"), numbers with a
   leading zero ("imei ends 0512"), ratings ("9/10"), specs ("5G", "120Hz",
   "20W"), charge cycles ("256 cycles") and phone numbers.
2. Each battery word is paired with one figure: the one after it if that can be
   a battery health ("battery 84", "B/H: 100%", "max cap 86%"), otherwise the
   one right before it ("84 battery health", "87🔋"). So in "iPhone 13 128
   Battery 87%" the battery is 87 and the 128 is still free to be the storage.
   A word about the battery's state ("64 battery replaced") pairs with nothing.
3. What's left is matched to this product's fields by their possible answers:
   - storage: one of this model's sizes, with "GB" typed any way ("128g",
     "256 gig", "512bg", "128 go"), or from 64 GB up with nothing at all
     ("16" on its own could be anything);
   - battery health, phones only: a figure with a % sign ("87%"), but not
     "95% condition", "charged to 80%" or "100% working"; and, in your own
     notes only, when they say nothing else about the battery, a number from
     60 to 99 on its own ("78, few scratches"). In a seller's text a number
     on its own stays unread: in real listings those were shop addresses.
4. A number on its own that could be either (64 on a phone that comes in
   64 GB) is neither: a gap beats a wrong guess.
"""

import re
import unicodedata
from decimal import Decimal
from functools import lru_cache

# "battery" the ways people type it: "batery", "battry", "baterray", "batt", "bettery"
TYPED_BATTERY = r"(?:bat{1,2}[aeiouy]?r{1,2}[aeiouy]{0,2}|batt|bett?ery|bettry)"
# a word that points at the battery's health figure: "battery health 84", "84 bh",
# "B/H 100%", "max cap 86%", "87🔋"
CUE = re.compile(rf"(?<![a-z])(?:{TYPED_BATTERY}\.?(?:\s+(?:health|life|capacity|cap))?|b/h|bh|health|"
                 r"max(?:imum)?\s+cap(?:acity)?|capacity)(?![a-z])|🔋")
# between a battery word and its figure after it: a few words ("battery health is
# still at 100%") and separators (":-"), but none that make it a different number:
# "battery charged to 80%", "battery cycle count 87", "battery replaced for 85"
NOT_HEALTH = (r"(?:charged?|charging|limit|dies|died|drains?|drained|lasts?|level|cycles?|count|replaced|"
              r"replacement|changed|for|cost|costs|paid|price|warranty|quote)")
CUE_TO_FIGURE = re.compile(rf"(?:\s+(?!{NOT_HEALTH}(?![a-z]))[a-z]+){{0,4}}\s*[:=~-]{{0,2}}\s*%?\s*\Z")
# between a figure and the battery word after it: "84 battery", "84% bh", "87% original battery"
FIGURE_TO_CUE = re.compile(r"\s*(?:%|per\s?cent)?\s*(?:(?:original|genuine|apple|oem)\s+)?\Z")
# a battery word followed by what was done to it has no figure before it: "64 battery
# replaced". Praise doesn't count: "87🔋 great condition" is about the whole phone
STATE = re.compile(r"\s*(?:is\s+|was\s+|has\s+been\s+|been\s+)?(?:replaced|replacement|changed|swapped|new|"
                   r"service|serviced|dead)(?![a-z])")
# "storage 64", "64 storage": a size, never the battery
STORAGE_BEFORE = re.compile(r"(?<![a-z])(?:storage|memory|rom)(?:\s+capacity)?(?:\s+is)?\s*[:=~-]?\s*\Z")
STORAGE_AFTER = re.compile(r"^\s*(?:storage|memory|rom)(?![a-z])")
GB = re.compile(r"^\s?(?:gb|gbs|gigabytes?)(?![a-z])")
TB = re.compile(r"^\s?(?:tb|tbs|terabytes?)(?![a-z])")
# a size that isn't the phone's own storage: "2tb icloud", "128gb sd card", "8gb ram"
NOT_ITS_STORAGE = re.compile(r"^\s?(?:gb|gbs|gigabytes?|tb|tbs|terabytes?)\s*(?:of\s+)?(?:icloud|cloud|sd|micro\s?sd|"
                             r"card|ram|data|plan)(?![a-z])")
# "GB" typed in a hurry ("128g", "256gGB", "256 gig", "512bg", "256gh", "128 go"):
# counted only for one of the model's own sizes. Stuck to another number it's the
# network ("5g"); apart from one it's something else ("bh 88 g/c", "88 go for 300")
TYPED_GB = re.compile(r"^\s?(?:g{1,2}b?|gigs?|bg|gh|go|gn)(?![a-z/])")
PERCENT_AFTER = re.compile(r"^[ \t]?(?:%|per\s?cent(?![a-z]))")
# "%84": the % before the figure, not the end of the last one ("bh 87% 256")
PERCENT_BEFORE = re.compile(r"(?<!\d)%[ \t]?\Z")
# short units only when stuck to the number: "20w", "3x", "4k", "2nd"; "128 w box" is "with"
SPEC = re.compile(r"^(?:\s?(?:hz|ghz|mhz|mah|mp|megapixels?|fps|inch(?:es)?|cm|mm|kg|nits|ppi|mbps|watts?|volts?|"
                  r"cores?|pm|am)|(?:w|x|k|p|v|nd|rd|th|st)|\")(?![a-z])")
TIME = re.compile(r"^[\s-]?(?:days?|weeks?|wks?|months?|mths?|mnths?|years?|yrs?|yr|hours?|hrs?|hr|mins?|minutes?|"
                  r"secs?|seconds?|nights?)(?![a-z])")
DISTANCE = re.compile(r"^\s?(?:miles?|mi|kms?|kilomet(?:er|re)s?)(?![a-z])")
CYCLE_BEFORE = re.compile(r"(?<![a-z])(?:cycles?|cycle count|cc)(?:\s+(?:is|of|at))?\s*[:=~-]{0,2}\s*\Z")
# "87 cycles", "87 charge cycles", "77 battery cycles": a count, not the battery
CYCLE_AFTER = re.compile(rf"^\s?(?:{TYPED_BATTERY}\s+)?(?:charge\s+)?cycles?(?![a-z])")
# a £ after a number only when stuck to it ("128£"): in "128 £300" it's the next number's
PRICE_AFTER = re.compile(r"^(?:[£$€]|\s?(?:o\.?n\.?o|ovno|quid|pounds?|gbp|each|pcm|firm|obo|no offers|"
                         r"or (?:near(?:est)?|best) offer|posted|delivered|shipped|cash|collected|paid|neg|"
                         r"negotiable|inc|incl|including|\+\s?postage|plus postage)(?![a-z]))")
# the words a reseller's notes put before a price: "bought 128", "sell 85", "cex 95",
# "list at 95", "price: 128". "no offers" says the price is firm: "NO OFFERS iPhone 17 Pro 256GB"
PRICE_WORD = (r"(?:gbp|price[ds]?|paid|pay|paying|asking|ask|costs?|rrp|worth|valued?|(?<!no )(?<!no-)offers?|offered|"
              r"take|accept|quote[ds]?|cex|avg|average|bought|buy|bp|sell|selling|sold|listed|list|listing|priced|"
              r"retails?|retailed|won|marketplace|for)")
PRICE_BEFORE = re.compile(rf"(?:[£$€]|(?<![a-z]){PRICE_WORD}(?:\s+(?:it|this|them|mine|me|at|for|avg|is|of|was|over|"
                          rf"around)){{0,2}})\s*[:=~-]{{0,2}}\s*\Z")
ADDRESS_AFTER = re.compile(r"^(?:\s+[a-z']+){0,2}\s+(?:street|st|road|rd|lane|ln|avenue|ave|crescent|cres|gardens|"
                           r"gdns|grove|terrace|parade|mews|court|square|hill|drive|place|park|rise|walk|row|view|"
                           r"close(?!\s+to(?![a-z]))|way(?!\s+(?:better|more|too|less|faster|bigger|cheaper)(?![a-z])))"
                           r"(?![a-z])")
ADDRESS_BEFORE = re.compile(r"(?<![a-z])(?:unit|flat|apartment|apt|suite|house)\s*\Z")
RATING_AFTER = re.compile(r"^\s?(?:/\s?|out of\s)(10|100)(?!\d)")
RATING_BEFORE = re.compile(r"(\d+)\s?/\s?\Z")  # the 10 in "9/10"
# a % next to one of these is about something else: "95% condition", "charged to 80%",
# "99% sure", "screen 95%", "80% limit"
NOT_BATTERY = (r"(?:condition|mint|working|works|genuine|original|fine|functional|functioning|perfect|legit|authentic|"
               r"sure|positive|certain|off|discount|cheaper|charged|charge|charging|limit|full|used|storage|done|"
               r"complete|cpu|brightness|volume|signal|tested|screen|body|clean|cosmetic|cosmetically|grade|looks?|"
               r"dies|died|drains?|drained)")
NOT_BATTERY_BEFORE = re.compile(rf"(?<![a-z]){NOT_BATTERY}(?:\s+[a-z]+)?\s*\Z")
NOT_BATTERY_AFTER = re.compile(rf"^\s*(?:[a-z]+\s+)?{NOT_BATTERY}(?![a-z])")
# a UK phone number: "07700 900123", "+44 7700 900123", "0161 496 0000" (not a date: "01-10-2025")
PHONE = re.compile(r"(?<![\d+])(?:\+\s?44\s?|0044\s?|0)\d{3,4}\s?\d{3}\s?\d{3,4}(?!\d)")
# a number, but not the 50 in "128.50". A comma splits ("bh 87,128gb"), except in a price ("£1,200")
NUMBER = re.compile(r"(?<!\d)(?<!\d\.)(\d+(?:\.\d+)?)(?!\d)")
OWN, OTHER = "#", "@"  # what this model's names and other models' names become
# every "before the number" pattern ends in \Z, not $: $ also matches before a final line
# break, so "factory reset\n128gb" would read "reset" as letters stuck to the 128
CLAUSE = re.compile(r"[,.;!?\n]")
BARE_SIZE_FROM = 64
BH_FROM = 32  # "bh87" is battery health, "BH21" a Bournemouth postcode: those stop at 31
ALONE = (60, 99)  # a number on its own in your notes: 100 on its own is "100% working"
WITH_PERCENT = (50, 99)  # "87%" with no battery word: low ones are discounts, 100 is "100% genuine"
WITH_WORD = (10, 100)


def normal(text):
    """Lowercase, accents and odd symbols gone, 🔋 kept: "256￼GB" -> "256 gb",
    "£1,200" -> "£1200"."""
    text = unicodedata.normalize("NFKD", (text or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s.,%£$€/:+'\"=~\-🔋]", " ", re.sub(r"[’‘ʼ]", "'", text))
    return re.sub(r"(?<=[£$€]\d)(\d{0,2}),(?=\d{3}(?!\d))", r"\1", text)


@lru_cache(maxsize=128)
def name_pattern(names):
    """One pattern for every model name ("iphone 13" also as "iPhone13", "iphone-13"), longest first."""
    parts = {r"[\s\-_]*".join(re.findall(r"[a-z]+|\d+", normal(name))) for name in names}
    parts = sorted((p for p in parts if p), key=len, reverse=True)
    return re.compile(rf"(?<![a-z0-9])(?:{'|'.join(parts)})(?![a-z0-9])") if parts else None


def blanked(text, own=(), others=()):
    """The text with model names and phone numbers marked out, so their digits can't be
    read as anything, and the words either side of them stay apart: in "NO OFFERS iPhone
    17 Pro 256GB", "offers" doesn't end up next to 256. This model's names become #,
    other models' @, so a size right after another model's name is that model's."""
    text = normal(text)
    for names, mark in ((own, OWN), (others, OTHER)):
        pattern = name_pattern(tuple(sorted(set(names))))
        if pattern:
            text = pattern.sub(lambda m: mark * len(m.group()), text)
    for m in PHONE.finditer(text):
        if 10 <= sum(ch.isdigit() for ch in m.group()) <= 13:
            text = text[:m.start()] + OTHER * len(m.group()) + text[m.end():]
    return text


def figure(token):
    """"84" -> "84", "84.50" -> "84.5": figures written one way."""
    return f"{Decimal(token).normalize():f}"


def clause(before, after):
    """The part of the sentence the number is in, before and after it."""
    cuts = list(CLAUSE.finditer(before))
    end = CLAUSE.search(after)
    return before[cuts[-1].end():] if cuts else before, after[:end.start()] if end else after


def stuck_cue(letters, value):
    """True if letters stuck to a number are a battery word: "batt84", "bh87" (not "BH21")."""
    if letters == "bh":
        return value is not None and value >= BH_FROM
    return bool(re.fullmatch(rf"{TYPED_BATTERY}|health|capacity", letters))


def taken(before, after, token, value):
    """True if the number belongs to something else: a code, another model, a price,
    a time, a distance, a spec, an address or a charge-cycle count."""
    if len(token) > 4 or (token[0] == "0" and len(token.split(".")[0]) > 1):
        return True  # an IMEI or its last digits ("0512"), a long code
    if re.search(rf"{OTHER}\s*\Z", before):
        return True  # "upgraded to an iPhone 15 Pro 256GB": that model's
    sized = GB.match(after) or TB.match(after)
    stuck_before = re.search(r"[a-z]+\Z", before)
    if stuck_before and not sized and not stuck_cue(stuck_before.group(), value):
        return True  # "A2482", "BH21", "M60": a code, not a figure
    stuck_after = re.match(r"[a-z]+", after)
    if stuck_after and not any(p.match(after) for p in (GB, TB, TYPED_GB, SPEC, TIME, PERCENT_AFTER, PRICE_AFTER,
                                                        CUE_AFTER, STORAGE_AFTER, CYCLE_AFTER, DISTANCE)):
        return True  # "64abc": not a figure we know
    if sized:
        return False  # "256GB" is a size whatever comes before it: "£250 256GB", "selling 256gb"
    return bool(PRICE_BEFORE.search(before) or PRICE_AFTER.match(after) or TIME.match(after)
                or DISTANCE.match(after) or SPEC.match(after) or ADDRESS_AFTER.match(after)
                or ADDRESS_BEFORE.search(before) or CYCLE_BEFORE.search(before) or CYCLE_AFTER.match(after))


CUE_AFTER = re.compile(rf"^\s*(?:%|per\s?cent)?\s*(?:{CUE.pattern})")


def rating(before, after, value):
    """True for a score: the 9 and the 10 in "9/10". "128 / 100%" isn't one: 128 is over 100."""
    out_of = RATING_AFTER.match(after)
    if out_of and value is not None and value <= int(out_of.group(1)):
        return True
    score = RATING_BEFORE.search(before)
    return value in (10, 100) and bool(score) and int(score.group(1)) <= value


def read_numbers(text, model, names=(), alone=False):
    """What the numbers in text say about this model (a catalogue entry):
    - "storage": the model's sizes it names, as the catalogue writes them ("128GB");
    - "stated": every size written with GB or TB, the model's or not ("8GB" of
      RAM too): a model that only comes in one size is in doubt if another is named;
    - "battery": battery-health figures ("84"), phones only.
    names: every model name in the catalogue, taken out first. alone: a number on
    its own counts as battery health (60 to 99): for your own notes only."""
    own = model.get("aliases", [])
    text = blanked(text, own, [name for name in names if name not in own])
    sizes = {int(size[:-2]): size for size in model.get("storage", []) if size.endswith("GB")}
    terabytes = {int(size[:-2]): size for size in model.get("storage", []) if size.endswith("TB")}
    phone = model.get("category") == "phones"
    found = {"storage": set(), "stated": set(), "battery": set()}
    numbers = []
    for match in NUMBER.finditer(text):
        token = match.group(1)
        value = int(token) if token.isdigit() else None
        before, after = text[:match.start()], text[match.end():]
        numbers.append({"token": token, "value": value, "start": match.start(), "end": match.end(),
                        "free": not taken(before, after, token, value), "before": before, "after": after})

    def can_be_battery(number, stuck_bh=False):
        after = number["after"]
        if not number["free"] or GB.match(after) or TB.match(after) or \
                (re.match(r"[a-z]", after) and not CUE_AFTER.match(after)):
            return False  # "128gb", "88g": a size; "84bh" is still the battery
        if stuck_bh and (number["value"] or 0) < BH_FROM:
            return False
        return WITH_WORD[0] <= float(number["token"]) <= WITH_WORD[1]

    # each battery word gets one figure: the nearest one after it, else the one right before it
    paired, cues = set(), [cue for cue in CUE.finditer(text)
                           if not re.search(r"(?:storage|memory|rom)\s*\Z", text[:cue.start()])]  # "storage capacity"
    for cue in cues:
        after = next((i for i, n in enumerate(numbers) if n["start"] >= cue.end()), None)
        before = next((i for i in range(len(numbers) - 1, -1, -1) if numbers[i]["end"] <= cue.start()), None)
        if after is not None and not CUE_TO_FIGURE.fullmatch(text[cue.end():numbers[after]["start"]]):
            after = None
        if before is not None and (not FIGURE_TO_CUE.fullmatch(text[numbers[before]["end"]:cue.start()])
                                   or STATE.match(text[cue.end():])):
            before = None  # "64 battery replaced": the word says the battery's state, not this figure
        stuck = cue.group() == "bh" and after is not None and numbers[after]["start"] == cue.end()
        for i, stuck_bh in ((after, stuck), (before, False)):
            if i is not None and i not in paired and can_be_battery(numbers[i], stuck_bh):
                paired.add(i)
                break

    alone_ones = []
    for i, number in enumerate(numbers):
        token, value, before, after = number["token"], number["value"], number["before"], number["after"]
        if i in paired:
            if phone:
                found["battery"].add(figure(token))
            continue
        if not number["free"] or rating(before, after, value):
            continue
        if value is not None and (GB.match(after) or TB.match(after)):
            unit = "TB" if TB.match(after) else "GB"
            found["stated"].add(f"{value}{unit}")
            if f"{value}{unit}" in (terabytes if unit == "TB" else sizes).values() and not NOT_ITS_STORAGE.match(after):
                found["storage"].add(f"{value}{unit}")
            continue
        typed = TYPED_GB.match(after)
        if value in sizes and (typed or STORAGE_BEFORE.search(before) or STORAGE_AFTER.match(after)):
            found["storage"].add(sizes[value])
            continue
        if typed and not after[:1].isspace():
            continue  # "5g": the network
        near_before, near_after = clause(before, re.sub(r"^[ \t]?(?:%|per\s?cent)", "", after))
        about_else = NOT_BATTERY_BEFORE.search(near_before) or NOT_BATTERY_AFTER.match(near_after)
        if PERCENT_AFTER.match(after) or PERCENT_BEFORE.search(before):
            if phone and not about_else and WITH_PERCENT[0] <= float(token) <= WITH_PERCENT[1]:
                found["battery"].add(figure(token))
            continue
        if value is None:
            continue  # "6.1": a screen size or a price, not a figure on its own
        storage = value in sizes and value >= BARE_SIZE_FROM
        battery = alone and phone and not about_else and ALONE[0] <= value <= ALONE[1]
        alone_ones.append((value, storage, battery))

    # on its own, a number counts as the battery only when nothing else in the text speaks
    # for the battery: no battery word, no figure. One that could be either is neither
    quiet = not cues and not found["battery"]
    for value, storage, battery in alone_ones:
        battery = battery and quiet
        if storage and not battery:
            found["storage"].add(sizes[value])
        elif battery and not storage:
            found["battery"].add(str(value))
    return found


def battery_worded(text):
    """Every battery-health figure the text gives, for the checks: "battery health 87",
    "87 battery health", "battery %87", "B/H: 87" and "87🔋" are all "87". No model is
    needed: it reads as a phone with no sizes."""
    return read_numbers(text, {"category": "phones"})["battery"]
