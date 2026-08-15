"""The message drafter: an offer to a seller, in your own style.

1. You pick the kind of offer: lower than asking, the asking price, or more.
   Code sets the price (flip.money.offer_for). The AI never picks it.
2. Code reads the listing for what's worth saying with that offer: its flaw
   for a lower offer or the asking price, its good condition for paying more
   (flip.offers). Your style decides whether that goes in; if it doesn't, the
   result asks you.
3. Your messages for the most similar listings are found by meaning
   (flip.retrieval) and shown to the AI as examples, with their old prices
   hidden, next to your style card (flip.style).
4. A longer message is about twice your usual length, and says more only with
   your usual points and questions the listing doesn't answer
   (flip.questions). It can start from the draft on screen.
5. The AI writes the wording. The message checks decide (the exact offer and
   no other price, the condition only as the listing says it, enough words for
   a longer one, no invented numbers or stories, no contact details, nothing
   off the platform), model by model as for listings (flip.attempts).
"""

import math

from flip.attempts import try_models
from flip.catalogue import fill_from_catalogue, load_catalogue
from flip.checks import check_message
from flip.money import offer_for, to_pence
from flip.offers import check_condition_talk, point_for, question_for, says_point
from flip.prompts import MESSAGE_SCHEMA, message_prompt
from flip.questions import check_no_answered_questions, open_questions
from flip.retrieval import listing_text
from flip.style import describe

USUAL_WORDS = 15  # how long a message is before you have past messages to go by
LONGER_AT_LEAST = 30
LONGEST = 70  # still well inside the 500-character limit
# a message is at most 500 characters, about 150 tokens: with this budget a
# local model that runs on stops in seconds, not half a minute
MESSAGE_TOKENS = 300


def longer_words(base):
    """How long a longer message is: about twice base, at least 30 words, at most 70."""
    return min(max(2 * base, LONGER_AT_LEAST), LONGEST)


def draft_message(listing, card=None, index=None, local=None, api=None, mode="auto", log=None,
                  discount_percent=15, leave_out=None, kind="lower", mention=None, length="usual", previous=None):
    """Draft one offer message. listing has a title, description, asking_price
    (pounds, as written) and marketplace. card is your style card
    (flip.style.style_card) and index a MessageIndex of your past messages;
    both are None before you have any. kind: "lower", "asking" or "more".
    mention: whether to say what the listing gives this offer (a flaw, or good
    condition). None lets your style decide, and a draft that leaves it out
    then asks you in result["ask"]. length: "usual" or "longer". previous: the
    draft on screen to make longer, as the drafter wrote it; it's kept and
    added to, and it settles the mention the way it was drafted."""
    if length not in ("usual", "longer"):
        raise ValueError(f"not a length: {length!r} (usual or longer)")
    card = card or {}
    previous = (previous or "").strip() if length == "longer" else ""
    asking = to_pence(listing["asking_price"])
    offer = offer_for(kind, asking, discount_percent)
    sources = f"{listing.get('title') or ''}. {listing.get('description') or ''}"
    point = point_for(kind, sources)
    style_decides = mention is None
    if style_decides:
        mention = says_point(previous, point) if previous and point else "condition" in card.get("mentions", [])
    mention = bool(point and mention)
    longer = None
    if length == "longer":
        category = fill_from_catalogue(listing.get("title") or "", "", load_catalogue(),
                                       listing.get("description") or "").get("category")  # None: not in the catalogue
        base = len(previous.split()) if previous else card.get("words") or USUAL_WORDS
        longer = {"words": longer_words(base), "questions": open_questions(sources, category),
                  "previous": previous or None}
    query = listing_text(listing.get("title") or "", listing.get("marketplace") or "")
    examples = index.similar(query, leave_out=leave_out) if index else []
    system, user = message_prompt(listing, offer, describe(card, longer["words"] if longer else None), examples,
                                  kind, point if mention else None, longer)
    result = {"item_id": listing.get("id"), "status": "needs you", "reasons": [], "kind": kind, "offer": offer,
              "point": point["says"] if point else [], "mentioned": mention,
              "ask": question_for(kind, point) if point and not mention and style_decides else None,
              "length": length, "words": longer["words"] if longer else None,
              "questions": longer["questions"] if longer else [],
              "examples": [e["id"] for e in examples], "answer": None, "title": None, "attempts": []}
    at_least = math.ceil(longer["words"] * 3 / 4) if longer else 0  # a little short of the aim still counts
    if previous:
        at_least = max(at_least, len(previous.split()) + 1)  # longer than the draft on screen, never shorter
        if at_least > LONGEST:
            result["reasons"].append(f"the draft is already as long as a message goes ({LONGEST} words)")
            if log:
                log.draft(result)
            return result

    def check(answer):
        message = answer.get("message")
        problems = check_message(message, offer, sources, asking, kind, at_least) + \
            check_condition_talk(message, sources, point, mention, kind, offer)
        return problems + check_no_answered_questions(message, sources) if isinstance(message, str) else problems

    result["answer"] = try_models(
        mode, {"local": local, "api": api},
        ask=lambda ai: ai.ask(system, user, [], MESSAGE_SCHEMA),
        check=check, result=result, log=log)
    if result["answer"] is not None:
        result["status"] = "ready"
    if log:
        log.draft(result)
    return result
