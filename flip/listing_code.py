"""List on eBay written by FlipAssist's own reader and code, with no writing model (14 Oct 2026, the owner: "make it
flip-reader 5 just read it and then we will make the ebay description using that and code ... cos we will only do
phones for this"; short sentences, blind-tested against Claude Haiku 5.5 before the app uses it).

1. flip-reader-5 reads your title and notes for the phone's flaws, as it reads a listing for the price tab (code's
   reading when its reading fails the checks), and each flaw sentence is split into its flaws (flip.prices.split_flaw:
   "cracked back and the balck dot in the front screen" is two). Code's own flaw rules (flip.prices.kinds_of) read the
   rest of your notes too, for a flaw the reader didn't quote ("one small chip on right side").
2. Code sorts the rest of your notes a piece at a time (flip.checks.promises_in and works_said): what works, what comes
   with it, the network, the condition, repairs and anything else about the phone, each in your own words. The specs
   code already filled ("iphone 13 pink 128gb"), the battery figure (said once, as your notes give it) and anything
   not about the phone ("no network info") are left out.
3. Code writes them as short sentences: the phone from the catalogue's facts ("Apple iPhone 13, 128GB, in Pink."), its
   condition with its flaws ("It's used: cracked back and the balck dot in the front screen."), its battery health,
   your other notes, the network, and what comes with it ("Comes with box and original charging cable."). The
   condition note is the flaws, the condition words and the battery health. Nothing is said that your title, notes or
   the catalogue don't say, and the same checks as any writer's hold it to them (flip.checks.check_listing_answer).
"""

import re
import time

from flip.ai import Reply
from flip.checks import (FOR_PARTS, MAX_CONDITION_NOTE, MAX_DESCRIPTION, NO_LIST, WORKING_PARTS, check_mark_places,
                         promises_in, works_said)
from flip.offers import battery_now
from flip.prices import flaw_items, kinds_of, sorted_each, tidy
from flip.reader import parts_of, read_listing_with_ai

NAME = "flip-reader-5 + code"
I = re.IGNORECASE

# names as their makers write them: what's typed quickly ("face id", "icloud") as a listing says it. Only the case
# changes, never a word
CASING = [(re.compile(rf"\b{typed}\b", I), shown) for typed, shown in (
    (r"face\s?id", "Face ID"), (r"touch\s?id", "Touch ID"), (r"true\s?tone", "True Tone"), (r"icloud", "iCloud"),
    (r"imei", "IMEI"), (r"iphone", "iPhone"), (r"magsafe", "MagSafe"), (r"find\s?my", "Find My"), (r"ios", "iOS"),
    (r"usb-c", "USB-C"), (r"usb", "USB"), (r"apple", "Apple"), (r"airpods", "AirPods"), (r"esim", "eSIM"),
    (r"sim", "SIM"), (r"ee", "EE"), (r"o2", "O2"), (r"vodafone", "Vodafone"), (r"tesco", "Tesco"),
    (r"applecare", "AppleCare"), (r"lcd", "LCD"), (r"oled", "OLED"), (r"uk", "UK"), (r"lightning", "Lightning"),
    (r"gsm", "GSM"))]
# first words that keep their capital inside a sentence ("It's used: Face ID not working")
PROPER = {"face", "touch", "true", "apple", "find", "magsafe", "vodafone", "tesco", "airpods", "applecare", "lightning"}
# what comes with the phone, as promises_in names it
ACCESSORIES = {"box", "charger", "cable", "case", "screen protector", "manual", "receipt", "accessories", "ear tips",
               "pouch", "headset"}
# a piece about the phone that no claim names: its repairs, parts, lock, reset, condition
ABOUT_IT = re.compile(r"\b(?:repair\w*|replaced|original|genuine|icloud|imei|find\s?my|reset|wiped|restored|"
                      r"unlocked|unlinked|locked|network|sim|esim|warranty|apple\s?care|tested|checked|condition|grade|"
                      r"refurb\w*|mint|good|great|excellent|perfect|pristine|fair|decent|clean|scratch\w*|scuff\w*|"
                      r"dent\w*|crack\w*|chip\w*|marks?|wear|worn|signs?\s+of\s+use|used|works?|working|fine|"
                      r"peak\s+performance|cycles?|phone\s+only|handset\s+only)\b", I)
# a piece about what the listing says or leaves out, not the phone: "no network info", "no box mentioned"
ABOUT_THE_LISTING = re.compile(r"\b(?:mentioned|info|information|described|stated|specified|listed|given)\b", I)
# a piece about the sale, not the phone: "second phone", "upgraded", "collection only", "price firm"
ABOUT_THE_SALE = re.compile(r"\b(?:second\s+phone|spare\s+phone|upgrad\w*|selling|sale|price|ono|offers?|collect\w*|"
                            r"post(?:age|ed)?|deliver\w*|swap\w*|cash|pick\s?up|paypal|bank)\b", I)
# a colour that starts with a condition word ("mint green"): its colour, not "mint" condition
MINT_COLOUR = re.compile(r"\bmint(?=\s+(?:green|blue)\b)", I)
# a piece that's only the phone's own name, size or colour ("iphone 13 pink 128gb"): code has those already
SPEC_WORDS = {"apple", "iphone", "pro", "max", "plus", "mini", "se", "gb", "tb", "the", "a", "an", "in", "and", "with",
              "colour", "color", "storage", "black", "white", "blue", "red", "green", "pink", "purple", "yellow", "gold",
              "silver", "grey", "gray", "graphite", "midnight", "starlight", "space", "rose", "coral", "sierra",
              "alpine", "pacific", "titanium", "natural", "desert", "ultramarine", "teal", "lavender", "sage", "mist",
              "orange", "deep", "cosmic", "jet", "navy", "product"}
# a piece that only names parts ("face id", "cameras", "speakers"): the "working" after them is theirs too
BARE_PART_WORDS = WORKING_PARTS | {"and", "the", "all", "front", "back", "rear", "cameras", "speakers", "buttons",
                                   "ports", "sensors", "mics", "microphones", "lenses", "true", "tone", "truetone",
                                   "wi", "fi", "wifi"}
# the words that open or close a piece about what's included: "comes with box", "case included"
INCLUDED_WORDS = re.compile(r"^(?:comes?\s+with|with|includes?|including|incl\.?|plus)\s+|\s+(?:included|incl\.?)$", I)
# the words a piece left over around a flaw can start with: "...but touch and display work"
LEAD = re.compile(r"^(?:(?:and|but|plus|also|&|though|although|however|otherwise)\s+)+", I)
CONDITION_SAID = {"1000": "It's new", "1500": "It's opened but never used", "3000": "It's used",
                  FOR_PARTS: "It's for parts or not working"}
NEW = ("1000", "1500")
MARK_CLAIMS = ("scratch", "scuff", "dent", "crack", "chip", "mark")
GAP = " ⁣ "  # where a flaw or the battery figure was taken out of a clause
# the battery's charge cycles, said with its health ("battery 90% 264 cycles")
CYCLES = re.compile(r"\b(\d{1,4})\s*(?:charge\s+)?cycles?\b", I)
# what "It's used" already says: "used", "in used condition"
JUST_USED = re.compile(r"^(?:in\s+)?(?:used|pre-?owned|second[\s-]?hand)(?:\s+condition)?$", I)


class ReaderCodeWriter:
    """The List on eBay writer that's flip-reader-5 and code (module docstring): the drafter calls write() in place of
    a model's ask(). reader: the model that reads listings (flip-reader-5, Setup.reading_model); sorter: flip-kinds
    (flip.kinds.Sorter, or what makes one), or None for code's rules; log: the audit log, where its reading is kept
    (job "read")."""

    name = NAME

    def __init__(self, reader, sorter=None, log=None):
        self.reader, self.sorter, self.log = reader, sorter, log

    def write(self, entry, item, model, condition):
        """The Reply a writing model would give: the condition note and description from your title and notes, the
        colour "unsure" when code couldn't fill it (the photos are for a model to look at)."""
        started = time.monotonic()
        flaws, notes, text = read_flaws(entry, self.reader, self.sorter, self.log)
        answer = written(item, model, condition, flaws, notes, text)
        if not item.get("colour"):
            answer["colour"] = "unsure"
        return Reply(model=NAME, answer=answer, seconds=round(time.monotonic() - started, 2))


def read_flaws(entry, reader, sorter=None, log=None):
    """flip-reader-5's reading of your title and notes, each flaw sentence split into its flaws: (flaws, notes, text)."""
    title, notes = entry.get("original_title") or "", entry.get("my_notes") or ""
    reading = read_listing_with_ai({"id": entry.get("id"), "title": title, "description": notes}, reader, None,
                                   "local", log)
    quotes = reading.get("quotes") or reading["flaws"]
    text = f"{title}. {notes}"
    sorter = sorter() if callable(sorter) and not hasattr(sorter, "name") else sorter
    each = sorted_each(quotes, text, title, notes, sorter)
    return [words for words, kinds, _ in flaw_items(each, [], text, title, notes, sorter) if kinds], notes, text


def cased(words):
    for typed, shown in CASING:
        words = typed.sub(shown, words)
    return words


def sentence(words):
    """A piece as a sentence of its own: "face id works" -> "Face ID works."."""
    said = tidy(cased(words))
    return said if not said or said[-1] in ".!?" else f"{said}."


def in_line(words):
    """A piece inside a sentence: its first letter small, unless it's a name ("Face ID not working", "iCloud on")."""
    said = tidy(cased(words))
    first = said.split(" ", 1)[0]
    if first[:1].isupper() and first[1:] == first[1:].lower() and first.lower() not in PROPER:
        return said[:1].lower() + said[1:]
    return said


def joined(pieces):
    """["a", "b", "c"] -> "a, b and c"."""
    return pieces[0] if len(pieces) == 1 else f"{', '.join(pieces[:-1])} and {pieces[-1]}"


def spec_only(piece, colours=()):
    """Whether a piece only names the phone, its size or its colour: code has those from the catalogue."""
    extra = {w for colour in colours for w in re.findall(r"[a-z]+", colour.lower())}
    words = re.findall(r"[a-z0-9]+", piece.lower())
    return bool(words) and all(w in SPEC_WORDS or w in extra or re.fullmatch(r"\d+(?:gb|tb|g)?", w) for w in words)


def bare_parts(piece):
    """Whether a piece only names parts ("face id", "cameras"): a "working" after it is said of them too."""
    words = re.findall(r"[a-z]+", piece.lower())
    return bool(words) and all(w in BARE_PART_WORDS or w.rstrip("s") in BARE_PART_WORDS for w in words)


def clauses(notes):
    """Your notes' clauses (parts_of), with a "no" over a list kept whole: "no box, charger or cable" is one clause, not
    "no box" and "charger or cable" (a charger and a cable that come with it)."""
    protected = notes
    for m in re.finditer(NO_LIST.pattern, notes, I):
        protected = protected[:m.start()] + m.group().replace(",", "\u2064") + protected[m.end():]
    return [clause.replace("\u2064", ",") for clause in parts_of(protected)]


def pieces(notes, flaws):
    """Your notes, a piece at a time, without the flaws' own words (they're said with the condition) or the battery
    figure (said once, as code reads it): each clause, cut where a flaw or the battery figure was."""
    out = []
    for clause in clauses(notes):
        rest = clause
        for words in flaws:
            at = rest.lower().find(words.lower())
            if at >= 0:
                rest = f"{rest[:at]}{GAP}{rest[at + len(words):]}"
        for part in rest.split(GAP.strip()):
            figure = battery_now(part)
            if figure:
                part = f"{part[:figure[1]]}{GAP}{part[figure[2]:]}"
            for piece in part.split(GAP.strip()):
                piece = LEAD.sub("", piece.strip(" \t\n.,;:!-–—&")).strip(" \t\n.,;:!-–—&")
                if piece:
                    out.append(piece)
    return out


def included_item(piece):
    """What comes with it, as a piece says it: "comes with box" -> "box", "boxed" -> "box", "case included" -> "case"."""
    said = INCLUDED_WORDS.sub("", piece.strip()).strip()
    return "box" if said.lower() == "boxed" else said


def sorted_pieces(notes, flaws, text, colours=(), keep_all=False):
    """The rest of your notes, sorted: (more flaws, the sentences in your notes' order, what comes with it, its
    condition words). A flaw code's rules find that the reader didn't quote is a flaw ("one small chip on right side");
    the specs, what's about the listing and what isn't about the phone are left out (keep_all: everything else is kept,
    "new screen fitted", "charges wirelessly", for a model to phrase); parts named on their own go with the "working"
    after them ("face id, cameras, speakers, charging working")."""
    more, said, included, condition, waiting = [], [], [], [], []
    for piece in pieces(notes, flaws):
        plain = MINT_COLOUR.sub("", piece)  # "mint green" is the colour: read without "mint"
        if spec_only(plain, colours) or ABOUT_THE_LISTING.search(piece):
            continue
        claims = promises_in(plain, typos=True)
        claims.pop("battery", None)
        if (claims and set(claims) <= ACCESSORIES and all(v == {"yes"} for v in claims.values())) or \
                (not claims and INCLUDED_WORDS.search(piece)):  # "comes with covers": a thing no claim names
            included.append(cased(included_item(piece)))
            continue
        if JUST_USED.match(piece) or CYCLES.fullmatch(piece):
            continue  # "used" is in "It's used"; the cycles are said with the battery
        if not claims and bare_parts(piece):
            waiting.append(piece)  # "face id": its "working" may come next
            continue
        if kinds_of([piece], text) and not any(v == {"no"} for v in claims.values()):
            more.append(piece)  # a flaw the reader didn't quote ("one small chip on right side")
            continue
        works = works_said(piece, typos=True)
        if not (claims or works or ABOUT_IT.search(piece) or (keep_all and not ABOUT_THE_SALE.search(piece))):
            continue
        if waiting and works:
            piece, waiting = ", ".join([*waiting, piece]), []
        said += [sentence(w) for w in waiting]
        waiting = []
        if any(k.split()[0] in ("flawless", "excellent") for k in claims) or \
                any(claims.get(k) == {"no"} for k in MARK_CLAIMS):
            condition.append(sentence(piece))
        said.append(sentence(piece))
    said += [sentence(w) for w in waiting]
    return more, said, included, condition


def battery_said(notes, figure):
    """The battery health as your notes give it, with its charge cycles: "Battery health is 75%.", "Battery health is
    under 80%.", "Battery health is 90%, 264 cycles."."""
    cycles = CYCLES.search(notes)
    with_cycles = f", {cycles.group(1)} cycles" if cycles else ""
    for clause in clauses(notes):
        found = battery_now(clause)
        if found:
            rough = f"{found[3]} " if found[3] else ""
            return f"Battery health is {rough}{found[0]}%{with_cycles}."
    return f"Battery health is {figure}%{with_cycles}." if figure else ""


def written(item, model, condition, flaws, notes, text=None):
    """The answer, written by code: {"condition_id", "condition_note", "description"}. flaws: each flaw's words, in
    order (flip.prices.flaw_items)."""
    text = text if text is not None else notes
    colours = (model or {}).get("colours", [])
    battery = battery_said(notes, item.get("battery"))
    # the battery figure is said once, as your notes give it, not in a flaw's own words
    flaws = [f for f in flaws if not (battery and battery_now(f))]
    more, said, included, condition_words = sorted_pieces(notes, flaws, text, colours)
    flaws = sorted([*flaws, *more], key=lambda f: (notes.lower().find(f.lower()) % (len(notes) + 1)))
    what = f"{item.get('brand') or 'Apple'} {item['model']}"
    if item.get("storage"):
        what += f", {item['storage']}" + (f", in {item['colour']}" if item.get("colour") else "")
    elif item.get("colour"):
        what += f" in {item['colour']}"
    lines = [f"{what}."]
    opening = CONDITION_SAID.get(condition, "It's used")
    together = f"{opening}: {joined([in_line(f) for f in flaws])}." if flaws else ""
    if not flaws or condition in NEW:
        lines.append(f"{opening}.")
    elif not check_mark_places("description", together, notes):
        lines.append(together)
    else:  # "...rear camera lens and cracks are on the protector": a crack on the camera, read joined
        lines += [f"{opening}.", *(sentence(f) for f in flaws)]
    if battery:
        lines.append(battery)
    lines += said
    network = item.get("network")
    told = " ".join([*said, *flaws]).lower()
    if network == "Unlocked" and "unlock" not in told:
        lines.append("Unlocked.")
    elif network and network != "Unlocked" and network.lower() not in told:
        lines.append(f"Network: {network}.")
    if included:
        lines.append(f"Comes with {joined(included)}.")
    note = [] if condition in NEW else [*(sentence(f) for f in flaws), *condition_words, *([battery] if battery else [])]
    return {"condition_id": condition, "condition_note": fitted(note, MAX_CONDITION_NOTE),
            "description": fitted(lines, MAX_DESCRIPTION)}


def fitted(lines, limit):
    """The sentences that fit in limit characters, from the first."""
    out = ""
    for line in lines:
        if len(f"{out} {line}".strip()) > limit:
            break
        out = f"{out} {line}".strip()
    return out


# ── a model phrases the facts (14 Oct 2026, the owner: "what if we make gemma 4b make the ebay description") ─────────
# flip-reader-5 and code pull the facts out of your notes (as above, keeping more of them); a model only turns that
# list into sentences, and code checks every fact made it in (facts_missing), as the checks hold it to your notes.

FACTS_SYSTEM = """You write the condition note and description of an eBay UK listing for a second-hand iPhone, from facts
the seller checked. Write as the seller, in plain UK English, in short natural sentences.

Rules:
1. Use every fact given, and nothing else. Never add a mark, a place, a fault, a repair, a number, an accessory, a
   condition word or a claim (like "fully working", "excellent", "tested") the facts don't give. Fix only spelling and
   capital letters.
2. condition_note: the flaws (each with where it is, as given), then the battery health, then any condition words. Empty
   for a new phone.
3. description: the phone, its condition with its flaws, the battery health, the other facts, the network, what comes
   with it and what doesn't.
4. Never mention the seller, notes, facts, a checklist or photos. No prices, no contact details, no specs such as screen
   size or chip.

Answer with JSON only: {"condition_note": "...", "description": "..."}"""
FACTS_SCHEMA = {"type": "object", "properties": {"condition_note": {"type": "string"}, "description": {"type": "string"}},
                "required": ["condition_note", "description"], "additionalProperties": False}
CONDITION_NAMES = {"1000": "New", "1500": "Opened - never used", "3000": "Used", FOR_PARTS: "For parts or not working"}


def facts_of(item, model, condition, flaws, notes, text=None):
    """What a model is told to phrase: {"phone", "condition", "flaws", "battery", "other", "network", "included"}, each
    from the catalogue's facts or your notes' own words (flip-reader-5's flaws and code's rules, as written() has
    them, keeping every piece about the phone)."""
    text = text if text is not None else notes
    battery = battery_said(notes, item.get("battery"))
    flaws = [f for f in flaws if not (battery and battery_now(f))]
    more, said, included, _ = sorted_pieces(notes, flaws, text, (model or {}).get("colours", []), keep_all=True)
    flaws = sorted([*flaws, *more], key=lambda f: (notes.lower().find(f.lower()) % (len(notes) + 1)))
    told = " ".join([*said, *flaws]).lower()
    network = item.get("network") or ""
    return {"phone": ", ".join(x for x in (f"{item.get('brand') or 'Apple'} {item['model']}", item.get("storage"),
                                           item.get("colour")) if x),
            "condition": CONDITION_NAMES.get(condition, "Used"),
            "flaws": [in_line(f) for f in flaws], "battery": battery.rstrip("."),
            "other": [s.rstrip(".") for s in said],
            "network": "" if not network or network.lower().split()[0] in told or
            (network == "Unlocked" and "unlock" in told) else network,
            "included": included}


def facts_text(facts):
    """The facts as the model reads them: one labelled line each."""
    lines = [f"Phone: {facts['phone']}", f"eBay condition: {facts['condition']}"]
    if facts["flaws"]:  # none: no line (a model copied "none given" into the note)
        lines.append(f"Flaws: {'; '.join(facts['flaws'])}")
    if facts["battery"]:
        lines.append(f"Battery: {facts['battery']}")
    if facts["other"]:
        lines.append(f"Other facts: {'; '.join(facts['other'])}")
    if facts["network"]:
        lines.append(f"Network: {facts['network']}")
    if facts["included"]:
        lines.append(f"Comes with: {'; '.join(facts['included'])}")
    return "\n".join(lines)


# the words a fact can't be said without: its marks, parts, states and things (a word starting with one counts)
ANCHORS = ("crack", "scratch", "scuff", "dent", "chip", "mark", "line", "dot", "spot", "blemish", "damage", "smash",
           "shatter", "broke", "fault", "back", "front", "screen", "display", "frame", "edge", "corner", "side", "top",
           "bottom", "left", "right", "camera", "lens", "face", "touch", "battery", "port", "charg", "speaker", "mic",
           "button", "wireless", "reset", "icloud", "unlock", "lock", "repair", "replac", "original", "genuine", "new",
           "work", "box", "cable", "case", "protector", "sim", "warranty", "cycle", "wear", "usb", "lightning")


def anchors_in(words):
    return {a for w in re.findall(r"[a-z0-9]+", words.lower()) for a in ANCHORS if w.startswith(a)} | \
        set(re.findall(r"\d+", words))


def facts_missing(answer, facts):
    """Each fact a draft leaves out, by the words it can't be said without ("cracked back": crack and back; "Battery
    health is 75%": battery and 75), [] when every one is in its condition note or description."""
    said = anchors_in(f"{answer.get('condition_note') or ''} {answer.get('description') or ''}")
    wanted = [*facts["flaws"], facts["battery"], *facts["other"], *facts["included"],
              *([facts["network"]] if facts["network"] else [])]
    return [fact for fact in wanted if fact and not anchors_in(fact) <= said]


class PhrasingWriter:
    """List on eBay's writer when a model only phrases the facts flip-reader-5 and code pulled out (facts_of): the
    drafter calls write() as for ReaderCodeWriter. phraser: the model that phrases them (Gemma 3 4B, Claude Haiku
    5.5). strict: a draft that leaves a fact out fails, as one that fails the checks does, so the paid backup writes
    it (the app's way; the 14 Oct test kept such drafts to judge them). last_facts, last_missing: the facts it was
    given and those its draft left out (facts_missing)."""

    def __init__(self, phraser, reader, sorter=None, log=None, strict=True):
        self.phraser, self.reader, self.sorter, self.log, self.strict = phraser, reader, sorter, log, strict
        self.name = f"{phraser.name} + facts"
        self.last_facts, self.last_missing = None, []

    def write(self, entry, item, model, condition):
        started = time.monotonic()
        flaws, notes, text = read_flaws(entry, self.reader, self.sorter, self.log)
        facts = facts_of(item, model, condition, flaws, notes, text)
        reply = self.phraser.ask(FACTS_SYSTEM, facts_text(facts), [], FACTS_SCHEMA)
        self.last_facts, self.last_missing = facts, []
        if reply.answer is None:
            return reply
        answer = {"condition_id": condition, "condition_note": "" if condition in NEW else
                  str(reply.answer.get("condition_note") or "").strip(),
                  "description": str(reply.answer.get("description") or "").strip()}
        self.last_missing = facts_missing(answer, facts)
        if self.strict and self.last_missing:
            return Reply(model=reply.model, error=f"it left out what your notes say: {', '.join(self.last_missing)}",
                         tokens_in=reply.tokens_in, tokens_out=reply.tokens_out, tokens_cached=reply.tokens_cached,
                         tokens_cache_write=reply.tokens_cache_write, seconds=round(time.monotonic() - started, 2))
        if not item.get("colour"):
            answer["colour"] = "unsure"
        return Reply(model=reply.model, answer=answer, tokens_in=reply.tokens_in, tokens_out=reply.tokens_out,
                     seconds=round(time.monotonic() - started, 2), tokens_cached=reply.tokens_cached,
                     tokens_cache_write=reply.tokens_cache_write)
