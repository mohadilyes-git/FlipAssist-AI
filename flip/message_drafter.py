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
4. The AI writes the wording. The message checks decide (the exact offer and
   no other price, the condition only as the listing says it, no invented
   numbers, no contact details, nothing off the platform), model by model as
   for listings (flip.attempts).
"""

from flip.attempts import try_models
from flip.checks import check_message
from flip.money import offer_for, to_pence
from flip.offers import check_condition_talk, point_for, question_for
from flip.prompts import MESSAGE_SCHEMA, message_prompt
from flip.retrieval import listing_text
from flip.style import describe


def draft_message(listing, card=None, index=None, local=None, api=None, mode="auto", log=None,
                  discount_percent=15, leave_out=None, kind="lower", mention=None):
    """Draft one offer message. listing has a title, description, asking_price
    (pounds, as written) and marketplace. card is your style card
    (flip.style.style_card) and index a MessageIndex of your past messages;
    both are None before you have any. kind: "lower", "asking" or "more".
    mention: whether to say what the listing gives this offer (a flaw, or good
    condition). None lets your style decide, and a draft that leaves it out
    then asks you in result["ask"]."""
    card = card or {}
    asking = to_pence(listing["asking_price"])
    offer = offer_for(kind, asking, discount_percent)
    sources = f"{listing.get('title') or ''}. {listing.get('description') or ''}"
    point = point_for(kind, sources)
    style_decides = mention is None
    if style_decides:
        mention = "condition" in card.get("mentions", [])
    mention = bool(point and mention)
    query = listing_text(listing.get("title") or "", listing.get("marketplace") or "")
    examples = index.similar(query, leave_out=leave_out) if index else []
    system, user = message_prompt(listing, offer, describe(card), examples, kind, point if mention else None)
    result = {"item_id": listing.get("id"), "status": "needs you", "reasons": [], "kind": kind, "offer": offer,
              "point": point["says"] if point else [], "mentioned": mention,
              "ask": question_for(kind, point) if point and not mention and style_decides else None,
              "examples": [e["id"] for e in examples], "answer": None, "title": None, "attempts": []}

    def check(answer):
        message = answer.get("message")
        return check_message(message, offer, sources, asking, kind) + \
            check_condition_talk(message, sources, point, mention, kind)

    result["answer"] = try_models(
        mode, {"local": local, "api": api},
        ask=lambda ai: ai.ask(system, user, [], MESSAGE_SCHEMA),
        check=check, result=result, log=log)
    if result["answer"] is not None:
        result["status"] = "ready"
    if log:
        log.draft(result)
    return result
