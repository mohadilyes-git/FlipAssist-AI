"""The listing drafter: one item in, one draft out.

1. Code fills every fact it can from the catalogue.
2. The AI is asked only for what's left: colour (when code couldn't fill it),
   condition, condition note and description.
3. The checks decide, model by model (flip.attempts): local first, one try on
   the paid model if a check fails, and never the API in place of a local
   model that can't be reached.
4. A draft is "ready" only when nothing is missing. Anything the AI was unsure
   of, or code couldn't fill, is listed for you to fill in. If no answer
   passes, code's title and that list still stand.
"""

from flip.attempts import try_models
from flip.catalogue import fill_from_catalogue
from flip.checks import UNSURE, canonical, check_listing_answer, sources_text
from flip.prompts import answer_schema, listing_prompt
from flip.title import build_title


def draft_listing(entry, catalogue, conditions, local=None, api=None, mode="auto", photos=(), log=None):
    """Draft one listing. entry is one item in the test set's format; photos
    are base64 JPEGs (flip.photos). Returns what happened, attempt by attempt."""
    title, description, notes = (entry.get(k) or "" for k in ("original_title", "original_description", "my_notes"))
    item = fill_from_catalogue(title, notes, catalogue, description)
    result = {"item_id": entry.get("id"), "status": "needs you", "reasons": [], "warnings": item["warnings"],
              "item": item, "answer": None, "title": None, "attempts": [],
              "colour_from": "listing" if item.get("colour") else None}
    if not item["model_id"]:
        result["reasons"].append("the model isn't in the catalogue")
        return finish(result, log)

    model = next(m for m in catalogue if m["id"] == item["model_id"])
    allowed = conditions[item["category"]]
    schema = answer_schema(item, model, allowed)
    system, user = listing_prompt(item, model, entry, len(photos))
    sources = sources_text(title, description, notes, item)
    result["answer"] = try_models(
        mode, {"local": local, "api": api},
        ask=lambda ai: ai.ask(system, user, list(photos), schema),
        check=lambda answer: check_listing_answer(answer, item, catalogue, allowed, sources, notes),
        result=result, log=log)

    # a colour the AI picked from the photos, once checked, completes the item; one code read stays.
    # With no photos it had nothing to look at, so its pick is a guess: the colour stays for you
    colour = (result["answer"] or {}).get("colour")
    if photos and not item.get("colour") and colour and str(colour).strip().lower() != UNSURE:
        item = {**item, "colour": canonical(colour, model["colours"], model.get("colour_aliases")),
                "missing": [field for field in item["missing"] if field != "colour"]}
        result["colour_from"] = "photos"
    # code's title and what's left to fill in stand even when no answer passed
    result["item"] = item
    result["title"] = build_title(item)
    if item["missing"]:
        result["reasons"].append(f"fill in: {', '.join(item['missing'])}")
    elif result["answer"] is not None:
        result["status"] = "ready"
    return finish(result, log)


def finish(result, log):
    if log:
        log.draft(result)
    return result
