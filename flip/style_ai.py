"""Your style, read by our AI as well as by code (3 Oct 2026). Code (flip.style) learns what you write the same way
twice; people write differently (long sentences, typos, shortcuts, "100£", "sam x"), so our AI, on this Mac, also
reads your messages and suggests your habits as fill-in-the-blank phrases ("I can pay {price}", "I like the {item}").
Since 6 Oct our AI is flip-style-1b (MODEL): Gemma 3 4B fine-tuned on 2,833 made-up buyers to name the habits they
repeat. On the hard style test (evals/style, 40 made-up buyers it never saw) it found 182 of 189 habits, with 6 wrong
and 3 invented, where plain Gemma 3 4B found 146, with 28 wrong and 230 invented (FLIP_STYLE_AI=gemma3:4b goes back).

Every suggestion is checked by code against your messages before it's used: it's kept only when its words are in at
least HABIT of them (and SHARE), with the blanks filled by each message's own price and item. So the AI can find a
habit code missed, but never invent one. A kept one only fills a gap: what code learned stays as it is.

What it fills is your sign-off only ("sam x", "thanks so much 😊", "thx mia xx"): on 10 made-up writers that was the
one thing plain Gemma found that code didn't (code alone 39 of 46 habits, with it 41), and the 3 Oct review showed that
its offers, closings, greetings and "like" phrases could pass the check and still go wrong in a draft ("Collect
tonight." from "I can't collect tonight"), for no gain. The rest of its answer is kept, to measure again later.

1. propose(messages, model): the AI's suggestions, run when your messages change (StyleBook.learn_with_ai), never
   while drafting: free, and your messages never leave this Mac.
2. checked(proposals, messages): the suggested sign-off, when it's how enough of your messages end.
3. merged(card, found): your style card with it when code found none, marked as found by our AI.
"""

import hashlib
import json
import re
from collections import Counter

from flip.ai import Reply
from flip.catalogue import words
from flip.style import (CALLED, CLOSING_SLOTS, CORE_THANKS, HABIT, HABIT_WORDS, KINDS, NOT_A_NAME, SHARE, SMILEY, TAIL_TOKEN,
                        THANKS, WHEN_WORDS, WHOLE_EMOJI, kind_of, said_tail, tail_start, unsigned)

MODEL = "flip-style-1b"  # FlipAssist's style reader in Ollama (plain gemma3:4b before 6 Oct)
# words a sign-off has beside thanks and a name: "thanks so much", "thanks a lot", "thank you", "ta x"
SIGN_FILLER = {"so", "very", "a", "lot", "loads", "again", "you", "x", "xx", "xxx"}
SYSTEM = """You read a buyer's past messages to sellers on second-hand marketplaces (Facebook, eBay, Vinted, Gumtree) \
and write down the habits they REPEAT, copied from their own words, with blanks: {price} for the amount they offer and \
{item} for the thing they're buying.

Only write a habit that is in at least two of the messages, in the same words (ignore capitals, typos and \
punctuation). Copy their words exactly as they write them, slang and shortcuts included ("u", "pls", "2day"). Leave a \
field empty ("" or []) when there's no such habit. Never invent anything.

Fields:
- greeting: the word(s) they open with ("Hi", "hiya mate"), or "".
- offer: how they make the offer, with {price} for the amount: "I can pay {price}", "would you take {price}?", "{price} cash?".
- after_offer: other parts they repeat after the offer (collecting, paying, posting, holding it), each a short phrase \
on its own: "I can come and collect", "cash ready".
- likes: how they say they like the item, with {item} for its name: "I like the {item}", "love the {item}", or "".
- sign_off: the exact words and smileys their messages end with ("Thanks, Dan", "sam x", "ta :)"), or "".
- short_words: words they write short every time, each {"word": "you", "written": "u"} (code checks these itself).

Example. Messages:
1. (buying "PS5 Disc"): hiya, wud u take 250 for the ps5? can collect 2day. ta jo x
2. (buying "AirPods Pro"): hiya wud u take 90 for the airpods, can collect 2day. ta jo x
3. (buying "Switch OLED"): hiya, wud u take 200? love the switch. ta jo x
Answer: {"greeting": "hiya", "offer": "wud u take {price}", "after_offer": ["can collect 2day"], "likes": "", \
"sign_off": "ta jo x", "short_words": [{"word": "would", "written": "wud"}, {"word": "you", "written": "u"}, \
{"word": "today", "written": "2day"}]}"""
SCHEMA = {"type": "object", "properties": {
    "greeting": {"type": "string"}, "offer": {"type": "string"},
    "after_offer": {"type": "array", "items": {"type": "string"}}, "likes": {"type": "string"},
    "sign_off": {"type": "string"},
    "short_words": {"type": "array", "items": {"type": "object", "properties": {
        "word": {"type": "string"}, "written": {"type": "string"}}, "required": ["word", "written"]}}},
    "required": ["greeting", "offer", "after_offer", "likes", "sign_off", "short_words"]}
MOST_MESSAGES = 40  # the newest: enough to see your habits, small enough for the Mac's model
def messages_key(messages):
    """What a learning was made from, to know when it's stale: a hash of the messages' words."""
    said = json.dumps([[m.get("listing_title"), m.get("asking_price"), m.get("marketplace"), m.get("my_message")]
                       for m in messages], ensure_ascii=False)
    return hashlib.sha256(said.encode()).hexdigest()[:24]


def user_text(messages):
    return "Messages:\n" + "\n".join(
        f"{n}. (buying \"{m.get('listing_title') or ''}\", asking £{m.get('asking_price') or '?'}, on "
        f"{m.get('marketplace') or '?'}): {m['my_message']}" for n, m in enumerate(messages, 1))


def propose(messages, model, log=None):
    """Our AI's suggestions for your messages, the newest MOST_MESSAGES of them: {} when it finds no habit (or there are
    too few messages to have one), None when it couldn't answer (no model, Ollama off, a fault, an unreadable reply), so
    the reading is tried again later. 6 Oct: flip-style-1b answers all-empty for a buyer who repeats nothing, and that
    answer counts as a reading. log: the audit log, where each reading is kept as the job "style" (15 Nov review: none
    was, so Home's "who did the work" and its count of successful outputs left flip-style-1b out)."""
    if model is None:
        return None
    mine = [m for m in messages if m.get("my_message")][-MOST_MESSAGES:]
    if len(mine) < HABIT:
        return {}
    name = getattr(model, "name", "unknown")
    try:
        reply = model.ask(SYSTEM, user_text(mine), [], SCHEMA)
    except Exception as error:  # noqa: BLE001 - a learning that can't run leaves your style as code learned it
        reply = Reply(name, error=f"{name} couldn't answer ({type(error).__name__})", reachable=False)
    answered = isinstance(getattr(reply, "answer", None), dict)
    if log is not None and isinstance(reply, Reply):  # free: it's on this device
        log.attempt(None, reply, [] if answered else [reply.error or "not an answer"], 0, job="style")
    if not answered:
        return None
    return tidy(reply.answer)


def tidy(answer):
    """An answer in the agreed shape, whatever the model sent: strings where strings go, lists of strings or of
    {"word", "written"} where lists go, anything else left out (3 Oct review: one wrong type stored broke every
    draft)."""
    if not isinstance(answer, dict):
        return {}
    out = {key: answer[key].strip() for key in ("greeting", "offer", "likes", "sign_off")
           if isinstance(answer.get(key), str) and answer[key].strip()}
    parts = [part.strip() for part in answer.get("after_offer") or [] if isinstance(part, str) and part.strip()]
    if parts:
        out["after_offer"] = parts[:5]
    short = [{"word": pair["word"], "written": pair["written"]} for pair in answer.get("short_words") or []
             if isinstance(pair, dict) and isinstance(pair.get("word"), str) and isinstance(pair.get("written"), str)]
    if short:
        out["short_words"] = short[:10]
    return out


def in_enough(messages, test):
    """The messages a test holds for, when they're at least HABIT and SHARE of them; else []."""
    held = [m for m in messages if test(m)]
    return held if len(held) >= HABIT and len(held) / max(1, len(messages)) >= SHARE else []


def checked(proposals, messages):
    """The suggested sign-off when it's really how at least HABIT and SHARE of your messages end, with those
    messages: {"sign_off": ("sam x", [...])}; else {}."""
    mine = [m for m in messages if m.get("my_message")]
    found = {}
    proposals = tidy(proposals)
    if not proposals or len(mine) < HABIT:
        return found
    sign = (proposals.get("sign_off") or "").strip()
    kissed = bool(re.search(r"(?:^|\s)x{1,3}$", sign, re.IGNORECASE))  # "sam x"
    # ...made only of thanks, a name or two, smileys and kisses: never "can collect today, cheers x" (3 Oct review:
    # added after the checks, it went on eBay drafts and stayed when collecting was removed)
    signed_words = [t.group().lower() for t in TAIL_TOKEN.finditer(sign) if t.group("word")]
    others = [w for w in signed_words if w not in THANKS | SIGN_FILLER | CALLED]
    if (len(others) > 2 or any(w in NOT_A_NAME or w in WHEN_WORDS or any(h.search(w) for h in HABIT_WORDS.values())
                               for w in others) or re.search(r"\d", sign) or len(signed_words) > 6):
        sign = ""
    # your thanks, a smiley or a kiss in it: never a word that just ends your messages ("lol", "Unlocked?")
    if sign and "?" not in sign and said_tail(sign) and (set(said_tail(sign).split()) & CORE_THANKS or kissed
                                                         or re.search(SMILEY, sign) or WHOLE_EMOJI.search(sign)):
        allowed = CORE_THANKS | {t.group().lower() for t in TAIL_TOKEN.finditer(sign) if t.group("word")}
        allowed |= {"x", "xx", "xxx"} if kissed else set()

        want = said_tail(sign).split()
        ending = re.compile(r"[\s,.!~-]*".join(re.escape(t) for t in want) + r"[\s.!]*$", re.IGNORECASE)

        def signs(m):  # how the message ends: "🚗 thanks so much 😊" ends "thanks so much 😊" (3 Oct eval)
            at = tail_start(m["my_message"], allowed)
            said = said_tail(m["my_message"][at:]).split() if at is not None else []
            return said[-len(want):] == want
        if held := in_enough(mine, signs):
            written = Counter(found_end.group().strip().rstrip(" .") for m in held
                              for found_end in [ending.search(m["my_message"])] if found_end)
            found["sign_off"] = (written.most_common(1)[0][0] if written else sign, held)
    return found


def merged(card, found, messages=()):
    """Your style card with the sign-off our AI found when code found none (never over code's), listed in
    card["ai_found"], once (out of your closings) and not on a kind of offer you send without it."""
    if not card or not found or "sign_off" not in found or card.get("signature"):
        return card
    card = {**card, "phrases": dict(card.get("phrases") or {}),
            "by_market": {group: dict(book) for group, book in (card.get("by_market") or {}).items()}}
    signed, held = found["sign_off"]
    card["signature"] = signed
    for book in (card["phrases"], *card["by_market"].values()):  # once, as code's: removing it removes it
        for slot in CLOSING_SLOTS:
            if isinstance(book.get(slot), str) and book[slot]:
                left = unsigned(book[slot], signed)
                book[slot] = left if words(left) else None
    made = Counter(kind_of(m) for m in messages if m.get("my_message"))
    signed_kinds = {kind_of(m) for m in held}
    card["signature_skip"] = sorted(k for k in KINDS if made[k] >= HABIT and k not in signed_kinds)
    card["ai_found"] = ["signature"]
    return card
