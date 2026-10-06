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
   of, or code couldn't fill, is listed for you to fill in, and so is a fault
   the seller mentions that your notes don't. If no answer passes, code's
   title and that list still stand.
"""

import re

from flip.attempts import try_models
from flip.catalogue import fill_from_catalogue, words
from flip.checks import UNSURE, canonical, check_listing_answer, condition_for, has_fault, sources_text
from flip.ebay import item_specifics
from flip.prompts import answer_schema, colour_schema, listing_prompt
from flip.title import build_title


def draft_listing(entry, catalogue, conditions, local=None, api=None, mode="auto", photos=(), log=None):
    """Draft one listing. entry is one item in the test set's format; photos
    are base64 JPEGs (flip.photos). Returns what happened, attempt by attempt."""
    title, description, notes = (entry.get(k) or "" for k in ("original_title", "original_description", "my_notes"))
    item = fill_from_catalogue(title, notes, catalogue, description)
    result = {"item_id": entry.get("id"), "status": "needs you", "reasons": [], "warnings": item["warnings"],
              "item": item, "answer": None, "title": None, "attempts": [], "ebay": None,
              "colour_from": "listing" if item.get("colour") else None, "colour_by": None}
    if not item["model_id"]:
        result["reasons"].append("the model isn't in the catalogue")
        return finish(result, log)

    model = next(m for m in catalogue if m["id"] == item["model_id"])
    # the one condition your notes back: the AI's answer can't hold another
    condition = condition_for(notes)
    allowed = [c for c in conditions[item["category"]] if c["id"] == condition] or conditions[item["category"]]
    schema = answer_schema(item, model, allowed)
    system, user = listing_prompt(item, model, entry, len(photos), allowed[0] if len(allowed) == 1 else None)
    sources = sources_text(title, description, notes, item)
    result["answer"] = try_models(
        mode, {"local": local, "api": api},
        ask=lambda ai: ai.ask(system, user, list(photos), schema),
        check=lambda answer: check_listing_answer(answer, item, catalogue, allowed, sources, notes),
        result=result, log=log)

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
    result["ebay"] = item_specifics(item, model, result["colour_from"], description)  # eBay's own fields, in its words
    checks = seller_faults(description, notes)
    if item["missing"]:
        result["reasons"].append(f"fill in: {', '.join(item['missing'])}")
    result["reasons"] += checks
    if not item["missing"] and not checks and result["answer"] is not None:
        result["status"] = "ready"
    return finish(result, log)


# the parts a fault can be about: your notes naming one means you've looked at it
FAULT_PARTS = {"camera", "cameras", "lens", "screen", "display", "touch", "battery", "charging", "charger", "port",
               "speaker", "speakers", "mic", "microphone", "face", "button", "buttons", "wifi", "bluetooth", "signal",
               "sim", "network", "sound", "audio", "volume", "power", "keyboard", "trackpad", "controller", "controllers",
               "joycon", "joycons", "stick", "sticks", "disc", "drive", "fan", "hdmi", "earbud", "earbuds", "buds"}
MAX_QUOTE = 25  # words of the seller's sentence to quote


def seller_faults(description, notes):
    """What to check: each fault the seller's description mentions and your
    notes don't, in the seller's own sentence. The draft follows your notes
    (they beat the seller's words), but an untested camera is a return waiting
    to happen. Your notes naming the part ("camera fine") means you've looked."""
    noted = set(words(notes or ""))
    found = []
    for sentence in re.split(r"[.!?;\n]+", description or ""):
        if not sentence.strip() or not has_fault(sentence):
            continue
        parts = set(words(sentence)) & FAULT_PARTS
        if (parts & noted) or (not parts and has_fault(notes or "")):
            continue
        said = sentence.split()
        quote = " ".join(said[:MAX_QUOTE]) + ("…" if len(said) > MAX_QUOTE else "")
        found.append(f'The seller says "{quote}": your notes don\'t mention it. Check it before you list it.')
    return found


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
