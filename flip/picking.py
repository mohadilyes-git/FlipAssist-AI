"""Which of a listing's flaws a lower offer gives as its reason when you pick how many: "1 flaw only", "2 flaws
only" or "3 flaws only" on the AI message screen (14 Oct 2026). "All flaws" gives every one, as before.

The worst go first, by how much each cuts a phone's price, in the prices API's order (its UK cuts: an iCloud lock 0.65,
for parts 0.76, a fault 0.87, damage 0.91, a network lock 0.95, not genuine 0.99, then a low battery and wear, which
cut least). Each flaw's kinds come from code's price rules (flip.prices.kinds_of). Between two flaws of a kind, the one
the seller says first goes first. A flaw code's rules can't sort ("sound is a little muffled") comes after those, but
it still counts: the reader quoted it.

FlipAssist's reader quotes whole sentences, and one sentence can hold more than one flaw ("Light scratches on the
screen and a small dent on the corner"). So each sentence is cut first:
1. at its clauses (flip.reader.parts_of);
2. then at "and", "&", "plus", "also" or "with", but only where both sides say something's wrong about a part of
   their own. "Screen cracked and scratched" stays whole: "scratched" alone wouldn't say where.

The picked flaws keep the seller's words and order. The wording model words only them, Haiku's check reads only
them, and a message that gives one you left out is refused (left_out_said)."""

import re

from flip.offers import BATTERY_TALK, battery_now, condition_said, once_each, said_in
from flip.prices import kinds_of
from flip.reader import judge, parts_of

# worst first: the prices API's kinds by how much each cuts the price (index.ts CUTS, UK)
WORST_FIRST = ("lock", "parts", "fault", "damage", "network lock", "not genuine", "battery", "wear")
CHOICES = (1, 2, 3)
# where one clause of a seller's sentence can join two flaws: "...on the screen and a small dent on the corner"
JOINED = re.compile(r"\s*,?\s*\b(?:and also|and|plus|also|with)\b\s*|\s*&\s*", re.IGNORECASE)
LEADING = re.compile(r"^(?:and also|and|plus|also|with|but|&)\s+", re.IGNORECASE)
# a part or a place on the item that a flaw is about: what each side of "and" needs to stand alone
THING = re.compile(r"\b(?:screen|display|glass|back|front|rear|frame|corners?|edges?|sides?|top|bottom|camera|"
                   r"cameras|lens|lenses|port|speakers?|earpiece|mic|microphone|buttons?|housing|case|casing|body|"
                   r"bezel|rim|chassis|keyboard|keys?|trackpad|touchpad|lid|hinges?|charger|cable|logo|base|"
                   r"batter(?:y|ies)|face ?id|touch ?id|sim|tray|power|volume|vibrat\w*|wi-?fi|bluetooth)\b",
                   re.IGNORECASE)
# a battery the wording rules call a flaw (85% or under, said roughly too) when the price rules leave it out
BATTERY_NEED = re.compile(r"\b(?:needs?|needing|replace\w*|low|poor|weak|worn|degraded|dying|drains?|draining|bad|"
                          r"service|doesn'?t last|won'?t hold)\b", re.IGNORECASE)
BATTERY_FIGURE = re.compile(r"\b(?:batter(?:y|ies)|batt|bh|b/h|health|capacity)\b[^.;\n]{0,25}?(?<![\d.])"
                            r"(\d{2})(?:\.\d+)?\s?%?(?![\d.])", re.IGNORECASE)
BATTERY_GOOD = re.compile(r"\b(?:great|good|fine|excellent|perfect|healthy|strong|brilliant|amazing|mint)\b",
                          re.IGNORECASE)
WORDING_BATTERY_FLAW = 85  # the wording rules: a battery health above 85% isn't a flaw


def rank(kinds):
    """Where a flaw goes, worst first: the place of its worst kind in WORST_FIRST, after them all with none."""
    return min((WORST_FIRST.index(k) for k in kinds if k in WORST_FIRST), default=len(WORST_FIRST))


def battery_flaw(piece):
    """Whether a piece of a seller's words gives the battery as a flaw: a health of 85% or under ("Battery 79%",
    "battery is under 80"), or what it needs ("needs a new battery"), not a battery praised ("battery health 90%,
    great")."""
    if not BATTERY_TALK.search(piece) or BATTERY_GOOD.search(piece):
        return False
    said = battery_now(piece)
    figure = float(said[0]) if said else None
    if figure is None and (found := BATTERY_FIGURE.search(piece)):
        figure = float(found.group(1))
    return figure <= WORDING_BATTERY_FLAW if figure is not None else bool(BATTERY_NEED.search(piece))


def kinds_in(piece, text):
    """The price kinds one flaw says, as code's price rules sort it in the listing (text), with "battery" for a
    battery the wording rules call a flaw that the price rules leave out (they start at 80%)."""
    kinds = kinds_of([piece], text)
    return [*kinds, "battery"] if "battery" not in kinds and battery_flaw(piece) else kinds


def is_flaw(piece, text):
    """Whether a piece of a seller's sentence says something's wrong with the item: a kind code's price rules know,
    or what the reader's own check calls a flaw ("flaw", not "denied": "no cracks" isn't one)."""
    return bool(piece.strip()) and (bool(kinds_in(piece, text)) or judge(piece, text) == "flaw")


def stands_alone(piece, text):
    """A side of an "and" that's a flaw of its own: it says what's wrong and which part of the item it's on."""
    return bool(THING.search(piece)) and is_flaw(piece, text)


def split_joined(part, text):
    """One clause cut at each "and", "&", "plus", "also" or "with" that has a flaw on a part of its own on both
    sides: "Light scratches on the screen and a small dent on the corner" is two."""
    pieces, start = [], 0
    for joiner in JOINED.finditer(part):
        if joiner.start() <= start:
            continue
        after = JOINED.search(part, joiner.end())
        left, right = part[start:joiner.start()], part[joiner.end():after.start() if after else len(part)]
        if stands_alone(left, text) and stands_alone(right, text):
            pieces.append(left)
            start = joiner.end()
    return [*pieces, part[start:]]


def pieces_of(line, text):
    """One of the reader's sentences cut into its flaws, in the seller's words, without a joining word to start."""
    out = []
    for part in parts_of(line):
        out += split_joined(part, text)
    return [cut for cut in (LEADING.sub("", piece.strip(" ,;:.")).strip(" ,;:.") for piece in out) if cut]


def pick_flaws(lines, text, most):
    """The flaws a lower offer gives when you pick how many, and the ones it leaves out: (picked, left_out), each a
    list in the seller's words and order. lines: the reader's sentences; text: the listing (title and description).
    most: 1, 2 or 3. Anything else ("all", None), or no more flaws than that, gives the sentences as they are and
    nothing left out, so the reason is worded from them as it always was."""
    lines = [line.strip() for line in lines or [] if line and line.strip()]
    if most not in CHOICES:
        return lines, []
    found = []
    for line in lines:
        # a sentence the reader quoted, with no piece code's rules see a flaw in, is still a flaw: the whole of it
        found += [piece for piece in pieces_of(line, text) if is_flaw(piece, text)] or [line]
    found = once_each(found)  # the title and the description often give the same flaw
    if len(found) <= most:
        return lines, []
    worst = sorted(range(len(found)), key=lambda n: (rank(kinds_in(found[n], text)), n))[:most]
    return [found[n] for n in sorted(worst)], [found[n] for n in range(len(found)) if n not in worst]


def left_out_said(message, picked, left_out, offer=None):
    """What a message says of the flaws you chose to leave out, as condition words ("scratch") or "battery": [] when
    it says none. Only what the message states counts (flip.offers.said_in: the offer's own question too), not a
    question of its own ("What's the battery health?"). A word the picked flaws say too isn't counted."""
    stated = said_in(message or "", offer)
    if not left_out or not stated:
        return []
    said_of = lambda pieces: set().union(*(condition_said(p, typos=True) for p in pieces if p))
    found = sorted(said_of(stated) & (said_of(left_out) - said_of(picked)))
    battery_left = any(battery_flaw(p) for p in left_out) and not any(battery_flaw(p) for p in picked if p)
    if battery_left and any(BATTERY_TALK.search(s) for s in stated):
        found.append("battery")
    return found
