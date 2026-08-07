"""The listing drafter: one item in, one draft out.

1. Code fills every fact it can from the catalogue.
2. The AI is asked only for what's left: colour (when code couldn't fill it),
   condition, condition note and description.
3. The checks decide. In "auto" mode the local model goes first and a failed
   check gets one try on the paid model; "local" and "api" use one model only.
4. If the local model can't be reached, nothing is sent to the API instead:
   an item only leaves this Mac when a local answer has failed the checks.
5. A draft is "ready" only when nothing is missing. Anything the AI was unsure
   of, or code couldn't fill, is listed for you to fill in.
"""

from flip.catalogue import fill_from_catalogue
from flip.checks import UNSURE, canonical, check_listing_answer, sources_text
from flip.costs import cost_pence
from flip.prompts import answer_schema, listing_prompt
from flip.title import build_title

MODES = {"local": ["local"], "api": ["api"], "auto": ["local", "api"]}


def draft_listing(entry, catalogue, conditions, local=None, api=None, mode="auto", photos=(), log=None):
    """Draft one listing. entry is one item in the test set's format; photos
    are base64 JPEGs (flip.photos). Returns what happened, attempt by attempt."""
    title, description, notes = (entry.get(k) or "" for k in ("original_title", "original_description", "my_notes"))
    item = fill_from_catalogue(title, notes, catalogue, description)
    result = {"item_id": entry.get("id"), "status": "needs you", "reasons": [], "warnings": item["warnings"],
              "item": item, "answer": None, "title": None, "attempts": []}
    if not item["model_id"]:
        result["reasons"].append("the model isn't in the catalogue")
        return finish(result, log)

    model = next(m for m in catalogue if m["id"] == item["model_id"])
    allowed = conditions[item["category"]]
    schema = answer_schema(item, model, allowed)
    system, user = listing_prompt(item, model, entry, len(photos))
    sources = sources_text(title, description, notes, item)
    models = {"local": local, "api": api}
    for name in MODES[mode]:
        ai = models[name]
        if ai is None:
            result["reasons"].append(f"no {name} model is set up")
            if name == "local":
                return finish(result, log)  # never the API in place of a missing local model
            continue
        reply = ai.ask(system, user, list(photos), schema)
        if reply.answer is None:
            problems = [reply.error]
        else:
            problems = check_listing_answer(reply.answer, item, catalogue, allowed, sources, notes)
        cost = cost_pence(reply.model, reply.tokens_in, reply.tokens_out)
        result["attempts"].append({"model": reply.model, "problems": problems, "seconds": reply.seconds,
                                   "tokens_in": reply.tokens_in, "tokens_out": reply.tokens_out, "cost_pence": cost})
        if log:
            log.attempt(result["item_id"], reply, problems, cost)
        if not problems:
            result["answer"] = reply.answer
            break
        if name == "local" and not reply.reachable:
            result["reasons"].append(f"{reply.error}, and nothing was sent to the API instead")
            return finish(result, log)

    if result["answer"] is None:
        result["reasons"].append("no answer passed the checks")
        return finish(result, log)

    # a colour the AI picked, once checked, completes the item
    colour = result["answer"].get("colour")
    if colour and str(colour).strip().lower() != UNSURE:
        item = {**item, "colour": canonical(colour, model["colours"], model.get("colour_aliases")),
                "missing": [field for field in item["missing"] if field != "colour"]}
    result["item"] = item
    result["title"] = build_title(item)
    if item["missing"]:
        result["reasons"].append(f"fill in: {', '.join(item['missing'])}")
    else:
        result["status"] = "ready"
    return finish(result, log)


def finish(result, log):
    if log:
        log.draft(result)
    return result
