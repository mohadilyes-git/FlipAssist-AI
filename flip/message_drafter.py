"""The message drafter: an offer to a seller, in your own style.

1. Code sets the offer price (flip.money.offer_price). The AI never picks it.
2. Your messages for the most similar listings are found by meaning
   (flip.retrieval) and shown to the AI as examples, with their old prices
   hidden, next to your style card (flip.style).
3. The AI writes the wording. The message checks decide (the exact offer and no
   other price, no invented numbers, no contact details, nothing off the
   platform), model by model as for listings (flip.attempts).
"""

from flip.attempts import try_models
from flip.checks import check_message
from flip.money import offer_price, to_pence
from flip.prompts import MESSAGE_SCHEMA, message_prompt
from flip.retrieval import listing_text


def draft_message(listing, style_lines=(), index=None, local=None, api=None, mode="auto", log=None,
                  discount_percent=15, leave_out=None):
    """Draft one offer message. listing has a title, description, asking_price
    (pounds, as written) and marketplace. index is a MessageIndex of your past
    messages, or None before you have any."""
    asking = to_pence(listing["asking_price"])
    offer = offer_price(asking, discount_percent)
    query = listing_text(listing.get("title") or "", listing.get("marketplace") or "")
    examples = index.similar(query, leave_out=leave_out) if index else []
    system, user = message_prompt(listing, offer, style_lines, examples)
    sources = f"{listing.get('title') or ''} {listing.get('description') or ''}"
    result = {"item_id": listing.get("id"), "status": "needs you", "reasons": [], "offer": offer,
              "examples": [e["id"] for e in examples], "answer": None, "title": None, "attempts": []}
    result["answer"] = try_models(
        mode, {"local": local, "api": api},
        ask=lambda ai: ai.ask(system, user, [], MESSAGE_SCHEMA),
        check=lambda answer: check_message(answer.get("message"), offer, sources, asking),
        result=result, log=log)
    if result["answer"] is not None:
        result["status"] = "ready"
    if log:
        log.draft(result)
    return result
