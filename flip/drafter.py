"""The listing drafter: one item in, one draft out.

1. Code fills every fact it can from the catalogue.
2. Code sets eBay's condition from your notes (flip.checks.condition_for).
   The AI is asked only for what's left: colour (when code couldn't fill it),
   condition note and description, held to that one condition.
3. The checks decide, model by model (flip.attempts): local first, one try on
   the paid model if a check fails, and never the API in place of a local
   model that can't be reached. When the local model's answer passes but it
   can't tell the colour from the photos, the paid model gets one look at
   the colour alone (about 0.01p).
4. eBay's category and fields ("item specifics") come from the same facts, in
   eBay's own words (flip.ebay): "Apple iPhone 13", "128 GB", "Black".
5. A draft is "ready" only when nothing is missing. Anything the AI was unsure
   of, or code couldn't fill, is listed for you to fill in. If no answer
   passes, code's title and that list still stand.

iPhones only (14 Oct 2026, the owner's call): any other item is turned away
before the AI is asked. It's written from your title and notes alone, as
AlertFlip's List on eBay is: on eBay you're the seller, so the description says
only what you checked, never the original seller's words.
"""


import re

from flip.attempts import try_models
from flip.catalogue import fill_from_catalogue
from flip.checks import UNSURE, canonical, check_listing_answer, condition_for, sources_text
from flip.ebay import item_specifics
from flip.prompts import answer_schema, colour_schema, listing_prompt
from flip.title import build_title


def draft_listing(entry, catalogue, conditions, local=None, api=None, mode="auto", photos=(), log=None):
    """Draft one listing. entry is one item in the test set's format; photos
    are base64 JPEGs (flip.photos). Returns what happened, attempt by attempt."""
    title, notes = (entry.get(k) or "" for k in ("original_title", "my_notes"))  # never the seller's description
    item = fill_from_catalogue(title, notes, catalogue)
    result = {"item_id": entry.get("id"), "status": "needs you", "reasons": [], "warnings": item["warnings"],
              "item": item, "answer": None, "title": None, "attempts": [], "ebay": None,
              "colour_from": "listing" if item.get("colour") else None, "colour_by": None}
    if not item["model_id"]:
        result["reasons"].append(f"{IPHONES_ONLY}: say which iPhone it is in the title")
        return finish(result, log)
    if not is_iphone(item):
        result["reasons"].append(IPHONES_ONLY)
        return finish(result, log)

    model = next(m for m in catalogue if m["id"] == item["model_id"])
    # the one condition your notes back: the AI's answer can't hold another
    condition = condition_for(notes)
    allowed = [c for c in conditions[item["category"]] if c["id"] == condition] or conditions[item["category"]]
    schema = answer_schema(item, model, allowed)
    system, user = listing_prompt(item, model, entry, len(photos), allowed[0] if len(allowed) == 1 else None)
    sources = sources_text(title, "", notes, item)
    result["answer"] = try_models(
        mode, {"local": local, "api": api},
        # a writer that's code (flip.listing_code: flip-reader-5 reads, code writes) is given the facts, not a prompt
        ask=lambda ai: ai.write(entry, item, model, condition, list(photos)) if hasattr(ai, "write")
        else ai.ask(system, user, list(photos), schema),
        check=lambda answer: check_listing_answer(answer, item, catalogue, allowed, sources, notes),
        result=result, log=log, job="listing")  # its own job in the audit log: Home says "writing the eBay listing"

    # the battery health figure your notes give is in the condition note, whoever wrote it: judged blind on 40 real
    # iPhones (14 Oct), a draft that passed the checks left it out 1 time in 8 (Claude Haiku 5.5) or 1 in 4 (Gemma 3 4B)
    if result["answer"] is not None:
        result["answer"] = with_battery(result["answer"], item.get("battery"))
    # a colour the AI picked from the photos, once checked, completes the item; one code read stays.
    # With no photos it had nothing to look at, so its pick is a guess: the colour stays for you
    colour = (result["answer"] or {}).get("colour")
    colour_by = result["attempts"][-1]["model"] if result["answer"] is not None else None
    # the local model's answer passed but it couldn't tell the colour: the paid model gets one look at the
    # colour alone (auto mode, where an answer from the local model is the only attempt so far)
    if photos and not item.get("colour") and unsure(colour) and mode == "auto" and api is not None \
            and len(result["attempts"]) == 1 and result["answer"] is not None:
        colour, colour_by = second_look(api, system, user, photos, model, result, log)
    if photos and not item.get("colour") and colour and not unsure(colour):
        item = {**item, "colour": canonical(colour, model["colours"], model.get("colour_aliases")),
                "missing": [field for field in item["missing"] if field != "colour"]}
        result["colour_from"], result["colour_by"] = "photos", colour_by
    # code's title and what's left to fill in stand even when no answer passed
    result["item"] = item
    result["title"] = build_title(item)
    result["ebay"] = item_specifics(item, model, result["colour_from"])  # eBay's own fields, in its words
    if item["missing"]:
        result["reasons"].append(f"fill in: {', '.join(item['missing'])}")
    if not item["missing"] and result["answer"] is not None:
        result["status"] = "ready"
    return finish(result, log)


IPHONES_ONLY = "List on eBay is for iPhones only"


def is_iphone(item):
    """Whether the catalogue's item is an iPhone: List on eBay drafts nothing else (14 Oct)."""
    return item.get("category") == "phones" and item.get("brand") == "Apple"


def with_battery(answer, battery):
    """The answer with "Battery health 87%." after its condition note when your notes give the figure and the note
    doesn't (a new item's note stays empty: eBay ignores it there)."""
    note = answer.get("condition_note") or ""
    if not battery or answer.get("condition_id") in ("1000", "1500") or re.search(rf"\b{battery}\s?%", note):
        return answer
    return {**answer, "condition_note": f"{note.rstrip()} Battery health {battery}%.".strip()}


def unsure(colour):
    return str(colour).strip().lower() == UNSURE


def second_look(api, system, user, photos, model, result, log):
    """The paid model's look at the colour alone, with the same prompt and
    photos, held to the model's colours: (colour, the model that said it), or
    (None, None) if its answer failed. It's an attempt like any other (cost,
    audit log), marked colour_only so the draft is still the local model's."""
    look = {"item_id": result["item_id"], "reasons": [], "attempts": []}
    colours = [*model["colours"], UNSURE]
    answer = try_models("api", {"api": api}, ask=lambda ai: ai.ask(system, user, list(photos), colour_schema(model)),
                        check=lambda found: [] if found.get("colour") in colours else
                        [f"the colour {found.get('colour')!r} isn't one of this model's"], result=look,
                        log=ColourLook(log) if log else None)
    result["attempts"] += [{**a, "colour_only": True} for a in look["attempts"]]
    return (answer["colour"], look["attempts"][-1]["model"]) if answer else (None, None)


class ColourLook:
    """The audit log, with each attempt kept as a look at the colour alone (job "colour")."""

    def __init__(self, log):
        self.log = log

    def attempt(self, item_id, reply, problems, cost, job=None):  # always "colour", whatever job it's handed
        self.log.attempt(item_id, reply, problems, cost, job="colour")


def finish(result, log):
    if log:
        log.draft(result)
    return result
