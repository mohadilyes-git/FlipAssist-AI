"""The real words a typo is never read as (flip.checks.wider_slip): "cash" is
a real word, so it's never a typed "case", nor "mask" a "mark".

They come from macOS's dictionary (/usr/share/dict/words) with each word's
endings ("card" -> "cards", "charge" -> "charges"), the catalogue's words,
and words of listings the dictionary hasn't got ("mini", "mins"). Only the
ones wider_slip would otherwise read as a claim word are kept, in
data/real_words.json. Build it again after changing the claim words
(flip.checks KEYWORDS) or the catalogue:

    python -m flip.real_words
"""

import json
from pathlib import Path

from flip.catalogue import load_catalogue, words
from flip.checks import KEYWORDS, NEAR_KEYS, REAL_WORDS, VOWELS, claim_forms, most_slips, wider_slip

DICTIONARY = Path("/usr/share/dict/words")
# words of listings the dictionary hasn't got: short for something, newer than it, or the trade's own
LISTING_WORDS = {"mini", "mins", "esim", "pics", "pls", "msg", "dms", "oled", "ipad", "imac", "airpods", "macbook",
                 "unboxed", "selfie", "wifi", "bluetooth", "touchscreen", "earbuds", "earbud", "joycon", "joycons",
                 "smartwatch", "online", "app", "apps", "upgrade", "upgraded", "warrantied",
                 "scuf"}  # the controller maker: "SCUF Reflex Pro included" has no scuff
LETTERS = "abcdefghijklmnopqrstuvwxyz"
ENDINGS = ("s", "es", "d", "ed", "ing", "er", "ers", "est", "ly", "y", "r", "rs", "st")


def endings(word):
    """A word with the endings English gives it: "card" -> "cards",
    "carded"...; "charge" -> "charges", "charged", "charging"; "box" ->
    "boxes"; "chip" -> "chipped"; "warranty" -> "warranties". "-es" only
    after s, x, z, ch, sh or o, and "-d" only on words of 5 letters or more,
    so no "workes", "maked" or "saled": those are typos to read."""
    plural = word + "es" if word.endswith(("s", "x", "z", "ch", "sh")) else word + "s"
    found = {word, plural, word + "er", word + "ers", word + "est", word + "ly", word + "y"}
    if word.endswith("o"):
        found.add(word + "es")
    if word.endswith("e"):
        found |= {word[:-1] + "ing", word + "r", word + "rs", word + "st"} | ({word + "d"} if len(word) >= 5 else set())
    else:
        found |= {word + "ing", word + "ed"}
    if word.endswith("y") and len(word) > 2 and word[-2] not in VOWELS:
        found |= {word[:-1] + ending for ending in ("ies", "ied", "ier", "iest", "ily")}
    if len(word) >= 3 and word[-1] not in "aeiouwxy" and word[-2] in VOWELS and word[-3] not in VOWELS:
        found |= {word + word[-1] + ending for ending in ("ed", "ing", "er", "y")}  # "chip" -> "chipped"
    return found


def stems(word):
    """What a word could be without its ending: "cards" -> {"cards", "card",
    "car"...}, so a real word is found without listing every word's endings."""
    found = {word}
    for ending in (*ENDINGS, "ies", "ied", "ier", "iest", "ily"):
        if word.endswith(ending) and len(word) > len(ending) + 1:
            stem = word[:-len(ending)]
            found |= {stem, stem + "e", stem + "y", stem[:-1] if stem[-1:] == stem[-2:-1] else stem}
    return found


def one_slip_away(word):
    """Every string one slip from word, its first letter kept: a letter left
    out or one added, two swapped, or a letter typed as a key touching it or
    as another vowel (flip.checks.slips)."""
    found = {word[:i] + word[i + 1:] for i in range(1, len(word))}
    found |= {word[:i] + letter + word[i:] for i in range(1, len(word) + 1) for letter in LETTERS}
    found |= {word[:i] + word[i + 1] + word[i] + word[i + 2:] for i in range(1, len(word) - 1)}
    found |= {word[:i] + letter + word[i + 1:] for i in range(1, len(word))
              for letter in NEAR_KEYS.get(word[i], set()) | (VOWELS if word[i] in VOWELS else set())}
    found.discard(word)
    return found


def build(dictionary=DICTIONARY):
    """The sorted real words wider_slip would read as a claim word without this list."""
    known = {w.strip().lower() for w in dictionary.read_text(encoding="utf-8").split() if w.strip().isalpha()}
    known |= LISTING_WORDS | {w for model in load_catalogue() for name in (*model["aliases"], *model["colours"])
                              for w in words(name) if w.isalpha()}
    real = lambda typed: any(stem in known and typed in endings(stem) for stem in stems(typed))
    near = set()
    for keyword in KEYWORDS:
        for form in claim_forms(keyword):
            once = one_slip_away(form) if most_slips(form) else set()
            near |= {typed for typed in once if real(typed)}
            if most_slips(form) == 2:  # two slips: one more from each
                near |= {twice for typed in once for twice in one_slip_away(typed) if real(twice)}
    return sorted(w for w in near if w not in KEYWORDS and wider_slip(w, guard=False))


if __name__ == "__main__":
    found = build()
    REAL_WORDS.write_text(json.dumps(found, indent=0) + "\n", encoding="utf-8")
    print(f"{len(found)} real words written to {REAL_WORDS}")
