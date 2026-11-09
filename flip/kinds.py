"""The price flaw sorter (6 Oct 2026): which kinds of flaw each of the seller's flaw sentences gives, for the price cut.

flip-reader-5 has picked out the seller's sentences that state a flaw. The prices API cuts the price by kind of flaw
(lock, parts, network lock, not genuine, damage, fault, battery, wear), so each sentence has to be sorted into the
kinds it gives first: "small crack on the back, battery 79%" is damage and battery; "battery health 88%" is none.

flip-kinds-1, FlipAssist's flaw-sorting model (Gemma 3 4B with a LoRA trained on 4,600 sentences, each labelled by two
blind labellers and a third where they differed; merged for Ollama as "flip-kinds-1"), reads one sentence in its
listing and answers its kinds. On the sealed test, 400 flaw sentences it had never seen (about 350 from real listings,
about 50 from the reader's made-up practice listings), labelled blind by three (6 Oct), first key: 93.2% exactly
right, the price cut wrong by 3 points or more on 5.2%, where code's rules (flip.prices.kinds_of) were wrong on 23.5%
and the prices API's own sorter on 25.8% (38.0% before its 6 Oct fix). Free, on this Mac, about 1.5 s a sentence.

The carrier rule (the owner's, 6 Oct evening; buyer-safe): a carrier or network named for the phone ("Carrier: AT&T",
"for Straight Talk", "works on Verizon") is a network lock unless the listing says it's unlocked or works on any
network. flip-kinds-1 answers that way by itself (on network lock it matched a blind relabel to the rule on 158 of 161
test sentences), and with the sealed test's carrier sentences labelled again it prices 3.8% wrong. Code's rules, which
sort the title and any sentence the model can't answer, follow it too since 6 Oct evening (flip.prices.network_lock):
on the sealed test 17.5% priced wrong, 25.0% before. A second training round
(flip-kinds-2, with more Samsung and MacBook sentences) wasn't better: on the second fresh test 8.5% priced wrong
against 8.2%, and worse on iPhones. So this one stays.

Each sentence the model can't answer (no Ollama, no flip-kinds-1, a fault or a timeout) is sorted by code's rules, as
before: the model only ever replaces code, it never stops a price. The title is always sorted by code ("iPhone 12 for
parts"): the model was trained on the description's sentences.

Settings, read from the environment each time (.env):
  FLIP_KINDS_MODEL  default flip-kinds-1; empty = off (code sorts every flaw)
"""

import os
from pathlib import Path

from flip.ai import LocalModel
from flip.reader import installed

DATA = Path(__file__).resolve().parent.parent / "data"
# the prompt flip-kinds-1 was trained with, word for word: it must get exactly this
SYSTEM = (DATA / "kinds_system.txt").read_text(encoding="utf-8").strip()
KINDS = ["lock", "parts", "network lock", "not genuine", "damage", "fault", "battery", "wear"]  # the API's, in its order
# the answer's shape, exactly as in the 6 Oct test (Ollama holds flip-kinds-1 to it while it writes)
SCHEMA = {"type": "object", "properties": {"kinds": {"type": "array", "items": {"type": "string", "enum": KINDS}}},
          "required": ["kinds"]}
LONG, AROUND = 1600, 700  # a description longer than LONG is cut to AROUND characters either side of the sentence,
# as in the test (the training listings were all shorter)


def model_name():
    """flip-kinds' name: FLIP_KINDS_MODEL from the environment or .env, read at each price check; empty = off."""
    return os.environ.get("FLIP_KINDS_MODEL", "flip-kinds-1").strip()


def user_text(title, description, quote):
    """One sentence in its listing, as flip-kinds-1 was trained and tested to see it."""
    description = description or ""
    if len(description) > LONG:
        at = max(description.find(quote), 0)
        description = description[max(0, at - AROUND): at + len(quote) + AROUND]
    return f"Title: {title}\nDescription: {description}\nThe flaw sentence: {quote}"


def kinds_in(answer):
    """The kinds in flip-kinds' answer, each once, in the API's order; None when it isn't an answer."""
    found = answer.get("kinds") if isinstance(answer, dict) else None
    if not isinstance(found, list) or not all(isinstance(k, str) for k in found):
        return None
    return [k for k in KINDS if k in found]


class Sorter:
    """flip-kinds asked one sentence at a time. After a reply that says the model isn't there (Ollama stopped, the
    model gone, minutes with no answer) it isn't asked again for this listing: code sorts the rest at once."""

    def __init__(self, model):
        self.model, self.name, self.down = model, model.name, False

    def __call__(self, quote, title, description):
        """The sentence's kinds, or None for code to sort it."""
        if self.down:
            return None
        try:
            reply = self.model.ask(SYSTEM, user_text(title, description, quote), [], SCHEMA)
        except Exception:  # noqa: BLE001 - any failure here falls back to code, it never stops a price
            self.down = True
            return None
        if reply.error:
            self.down = self.down or not reply.reachable
            return None
        return kinds_in(reply.answer)


def sorter(url="http://127.0.0.1:11434"):
    """A Sorter when Ollama has flip-kinds (looked up at each price check, so one installed later is used), else None
    (code sorts)."""
    name = model_name()
    if not name or not installed(name, url):
        return None
    # short prompts: a small working memory (as in the test), so Ollama can keep it next to the reader when memory allows
    return Sorter(LocalModel(name, url=url, timeout=60, max_tokens=60, num_ctx=2048))
