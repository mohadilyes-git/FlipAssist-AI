"""The message drafter: an offer to a seller, in your own style.

1. You pick the kind of offer: lower than asking, the asking price, or more.
   Code sets the price (flip.money.offer_for). The AI never picks it.
2. The listing is read for its flaws, where to collect and whether the
   seller takes offers: by AI with code checking every word (flip.reader),
   or by code alone. "No offers" never changes your offer: the result
   carries a note with the seller's words, to show under the message.
3. Code picks what's worth saying with that offer: the flaw for a lower
   offer or the asking price, good condition for paying more (flip.offers).
   Your style decides whether that goes in; if it doesn't, the result asks you.
4. Who writes: if your past messages repeat, or there are none yet, your own
   sentences with no AI (flip.writer), which beat the AI in a blind test; the
   AI writes only if that fails a check. If they vary, the AI writes, shown
   your messages for the most similar listings (flip.retrieval) with their
   old prices hidden, next to your style card (flip.style).
5. A longer message is about twice your usual length, and says more only with
   your usual points and questions the listing doesn't answer
   (flip.questions). It can start from the draft on screen.
6. The checks decide, whoever wrote it: the exact offer and no other price,
   the condition only as the listing says it, enough words for a longer one,
   no promise about collecting or paying that your messages don't make, no
   invented numbers or stories, no contact details, nothing off the
   platform. Models are tried in turn as for listings (flip.attempts).
"""

import math
import re
import time

from flip.ai import Reply
from flip.attempts import try_models
from flip.catalogue import fill_from_catalogue, load_catalogue, words
from flip.checks import check_message, check_no_unasked_promises, names_other_model, promised_in
from flip.money import offer_for, to_pence
from flip.offers import check_condition_talk, point_for, question_for, says_point
from flip.prompts import MESSAGE_SCHEMA, message_prompt
from flip.questions import check_no_answered_questions, open_questions
from flip.reader import code_reading
from flip.retrieval import listing_text
from flip.style import describe
from flip.writer import make_longer, repeats, write_offer

USUAL_WORDS = 15  # how long a message is before you have past messages to go by
LONGER_AT_LEAST = 30
LONGEST = 70  # still well inside the 500-character limit
# a message is at most 500 characters, about 150 tokens: with this budget a
# local model that runs on stops in seconds, not half a minute
MESSAGE_TOKENS = 300
WRITERS = ("auto", "template", "ai")
# what a raw listing title adds that isn't the item: "*BARGAIN*", "FREE DELIVERY", "excellent condition boxed"
TITLE_CUT = re.compile(r"\s+[-–|]\s+|[*|(\[,]")
TITLE_NOISE = re.compile(r"(?:excellent|good|great|mint|perfect|immaculate|used|new|boxed|unboxed|condition|bargain|"
                         r"cheap|free|delivery|postage|p&p|collection|collect|only|sale|rare|genuine|original|working|"
                         r"fully|tested|wow|look|ono|ovno|quick|must|go|bnib|bnwt|sealed)", re.IGNORECASE)


def longer_words(base):
    """How long a longer message is: about twice base, at least 30 words, at most 70."""
    return min(max(2 * base, LONGER_AT_LEAST), LONGEST)


def item_name(model_id, title):
    """What to call the item: its catalogue name without brackets ("AirPods
    Pro"), or for an item the catalogue doesn't know, its title without the
    selling words ("Bose QC45 headphones *BARGAIN*" -> "Bose QC45 headphones")."""
    model = next((m for m in load_catalogue() if m["id"] == model_id), None)
    if model:
        return re.sub(r"\s*\(.*?\)", "", model["model"]).strip()
    kept = [w for w in TITLE_CUT.split(title.strip())[0].split() if not TITLE_NOISE.fullmatch(w.strip("!.*"))]
    return " ".join(kept[:5]) or "item"


def habits(card, examples):
    """How you buy, in your own words: what your messages promise (collecting,
    cash, postage), as your style card records it and your example messages
    show it. The same words the promise check reads (flip.checks.promised_in)."""
    return set(card.get("promises", [])).union(*(promised_in(e["my_message"]) for e in examples))


def draft_message(listing, card=None, index=None, local=None, api=None, mode="auto", log=None,
                  discount_percent=15, leave_out=None, kind="lower", mention=None, length="usual", previous=None,
                  reading=None, writer="auto"):
    """Draft one offer message. listing has a title, description, asking_price
    (pounds, as written) and marketplace. card is your style card
    (flip.style.style_card) and index a MessageIndex of your past messages;
    both are None before you have any. kind: "lower", "asking" or "more".
    mention: whether to say what the listing gives this offer (a flaw, or good
    condition). None lets your style decide, and a draft that leaves it out
    then asks you in result["ask"]. length: "usual" or "longer". previous: the
    draft on screen to make longer, as the drafter wrote it; it's kept and
    added to, and it settles the mention the way it was drafted. reading: the
    listing as flip.reader read it; None reads it with code alone. writer:
    "auto" (your past messages decide), "template" (no AI) or "ai"."""
    if length not in ("usual", "longer"):
        raise ValueError(f"not a length: {length!r} (usual or longer)")
    if writer not in WRITERS:
        raise ValueError(f"not a writer: {writer!r} (auto, template or ai)")
    card = card or {}
    previous = (previous or "").strip() if length == "longer" else ""
    asking = to_pence(listing["asking_price"])
    offer = offer_for(kind, asking, discount_percent)
    title = listing.get("title") or ""
    sources = f"{title}. {listing.get('description') or ''}"
    reading = reading or code_reading(sources)
    point = point_for(kind, sources, reading["flaws"])
    style_decides = mention is None
    if style_decides:
        mention = says_point(previous, point) if previous and point else "condition" in card.get("mentions", [])
    mention = bool(point and mention)
    found = fill_from_catalogue(title, "", load_catalogue(), listing.get("description") or "")
    longer = None
    if length == "longer":
        base = len(previous.split()) if previous else card.get("words") or USUAL_WORDS
        longer = {"words": longer_words(base),
                  "questions": open_questions(sources, found.get("category"), flaws=reading["flaws"]),
                  "previous": previous or None}
    query = listing_text(title, listing.get("marketplace") or "")
    examples = index.similar(query, leave_out=leave_out) if index else []
    allowed = habits(card, examples)
    pickup = reading["pickup"] if "collecting" in allowed else ""  # only if you'd say you'll collect
    result = {"item_id": listing.get("id"), "status": "needs you", "reasons": [], "kind": kind, "offer": offer,
              "point": point["says"] if point else [], "mentioned": mention,
              "ask": question_for(kind, point) if point and not mention and style_decides else None,
              "note": f"The seller says: \"{reading['no_offers']}\"" if reading["no_offers"] else None,
              "reading": {k: reading[k] for k in ("flaws", "pickup", "no_offers", "read_by")},
              "length": length, "words": longer["words"] if longer else None,
              "questions": longer["questions"] if longer else [],
              "examples": [e["id"] for e in examples], "writer": None, "answer": None, "title": None,
              "attempts": []}
    at_least = math.ceil(longer["words"] * 3 / 4) if longer else 0  # a little short of the aim still counts
    if previous:
        at_least = max(at_least, len(previous.split()) + 1)  # longer than the draft on screen, never shorter
        if at_least > LONGEST:
            result["reasons"].append(f"the draft is already as long as a message goes ({LONGEST} words)")
            if log:
                log.draft(result)
            return result

    catalogue = load_catalogue()
    model = next((m for m in catalogue if m["id"] == found.get("model_id")), None)

    def check(answer):
        message = answer.get("message")
        problems = check_message(message, offer, sources, asking, kind, at_least) + \
            check_condition_talk(message, sources, point, mention, kind, offer)
        if isinstance(message, str):
            problems += check_no_answered_questions(message, sources) + check_no_unasked_promises(message, allowed)
            if model and names_other_model(words(message), model, catalogue):
                problems.append("the message names a different item from the listing's")
        return problems

    if writer == "template" or writer == "auto" and (not card or repeats(card)):
        ready = written_without_ai(result, check, card, kind, offer, point if mention else None, longer, at_least,
                                   item_name(found.get("model_id"), title), pickup, previous, log)
        if ready or writer == "template":
            if not ready:
                result["reasons"].append("the message written without AI didn't pass the checks")
            if log:
                log.draft(result)
            return result

    system, user = message_prompt(listing, offer, describe(card, longer["words"] if longer else None), examples,
                                  kind, point if mention else None, longer, pickup or None)
    result["answer"] = try_models(
        mode, {"local": local, "api": api},
        ask=lambda ai: ai.ask(system, user, [], MESSAGE_SCHEMA),
        check=check, result=result, log=log)
    if result["answer"] is not None:
        result["status"], result["writer"] = "ready", result["attempts"][-1]["model"]
    if log:
        log.draft(result)
    return result


def written_without_ai(result, check, card, kind, offer, point, longer, at_least, item, pickup, previous, log):
    """flip.writer's message, through the same checks as the AI's: True and
    the result is ready if it passes. If not, its problems are in the
    attempts and the AI gets its turn (or, with writer="template", you do)."""
    started = time.monotonic()
    questions = longer["questions"] if longer else []
    text = make_longer(previous, questions, at_least, item) if previous else \
        write_offer(card, kind, offer, point, questions, at_least, item, pickup)
    answer = {"message": text} if text is not None else None
    problems = check(answer) if answer else [f"there's no plain wording for what the listing says: "
                                             f"{' / '.join(point['says'])}"]
    reply = Reply("template", answer=answer, seconds=time.monotonic() - started)
    result["attempts"].append({"model": "template", "problems": problems, "seconds": reply.seconds,
                               "tokens_in": 0, "tokens_out": 0, "cost_pence": 0})
    if log:
        log.attempt(result["item_id"], reply, problems, 0)
    if problems:
        return False
    result.update(answer=answer, status="ready", writer="template")
    return True
