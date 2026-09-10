"""eBay's own fields for a listing, filled from what code knows, in eBay's words.

eBay UK asks for different fields ("item specifics") in each category. For
Mobile & Smart Phones it won't list without Brand, Model, Storage Capacity and
Colour, and it suggests more (Network, Screen Size...). data/ebay_fields.json is
what eBay's API said, per category: every field, whether eBay needs it, and the
values eBay knows. `python -m flip.ebay --refresh` asks again (read-only calls,
with EBAY_CLIENT_ID and EBAY_CLIENT_SECRET from .env).

data/ebay_map.json turns the catalogue's names into eBay's: most models are the
brand and the model on eBay ("Apple iPhone 13"), a few aren't ("iPhone Air" is
"Apple iPhone 17 Air"), and every colour has one of eBay's 16 plain colours
(Midnight is Black, Rose Gold is Pink: what UK sellers pick for it).

Phones only so far: other categories get no fields yet (None).
"""

import base64
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import date
from functools import lru_cache
from pathlib import Path

from flip.catalogue import load_catalogue
from flip.numbers import read_numbers

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ROOT / "data" / "ebay_fields.json"
MAP = ROOT / "data" / "ebay_map.json"
API = "https://api.ebay.com"
MARKETPLACE = "EBAY_GB"
# eBay UK's category for each of the catalogue's categories
CATEGORIES = {"phones": "9355", "consoles": "139971", "headphones": "112529"}
FILLED = {"phones"}  # the categories whose fields are filled in so far
# where a field's value came from, as the screen says it
CATALOGUE, TEXT, PHOTOS = "the catalogue", "your title or notes", "the photos"
# the networks a UK phone is sold on, offered for Network: eBay's list has 415, worldwide
UK_NETWORKS = ["Unlocked", "EE", "O2", "Three", "Vodafone", "Virgin Mobile", "giffgaff", "Tesco Mobile",
               "Sky Mobile", "BT Mobile", "iD Mobile", "Lebara", "Lycamobile", "SMARTY", "VOXI"]


@lru_cache(maxsize=1)
def load_fields(path=FIELDS):
    return json.loads(Path(path).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_map(path=MAP):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def ebay_size(size):
    """The catalogue's "128GB" as eBay writes it: "128 GB"."""
    return re.sub(r"(?<=\d)\s*(?=[KMGT]B$)", " ", size) if size else None


def spelt(values, wanted):
    """eBay's spelling of a value its list has, whatever the case, or None:
    "apple iphone se (2nd generation)" -> "Apple iPhone SE (2nd Generation)"."""
    lower = (wanted or "").lower()
    return next((value for value in values if value.lower() == lower), None)


@lru_cache(maxsize=1)
def model_names():
    """Every model name in the catalogue: a size right after another model's name is that model's."""
    return tuple(alias for model in load_catalogue() for alias in model["aliases"])


def seller_sizes(description, model):
    """The model's storage sizes the seller's description names, in eBay's
    words: "128 also when i..." -> ["128 GB"]. Read like your title and notes
    (flip.numbers): "GB" typed any way or, from 64 GB up, not at all; never a
    price ("£128"), a time ("128 days"), an address ("128 High Street") or
    another model's size ("upgraded to an iPhone 15 Pro 256GB")."""
    named = read_numbers(description or "", model or {}, model_names())["storage"]
    return [ebay_size(size) for size in (model or {}).get("storage", []) if size in named]


def model_value(item, values, models):
    """eBay's name for the catalogue's model: the map's, or the brand and the model."""
    return models.get(item["model"]) or spelt(values, f"{item['brand']} {item['model']}") \
        or f"{item['brand']} {item['model']}"


def chipset_value(brand, chip, values):
    """eBay's name for a chip: "A15 Bionic" -> "Apple A15 Bionic", "Snapdragon 8
    Gen 2" -> "Qualcomm Snapdragon 8 Gen 2". One eBay doesn't list yet ("A19
    Pro") goes in as the brand and the chip: eBay takes typed values here."""
    if not chip:
        return None
    return spelt(values, f"{brand} {chip}") or next((v for v in values if v.lower().endswith(f" {chip.lower()}")), None) \
        or f"{brand} {chip}"


def item_specifics(item, model=None, colour_from=None, description="", fields=None, emap=None):
    """eBay's category and fields for one item (fill_from_catalogue's), filled
    from what code knows, or None for a category not done yet. model is its
    catalogue entry. Each field: {"name", "value" (None if nobody knows it),
    "required", "source", "options" (eBay's values to pick from), "hint" (for
    an empty one, what the seller's description says)}, in eBay's order: the
    ones eBay needs, then the ones filled. description: the seller's, read
    only for hints: your title and notes fill the fields."""
    if not item.get("model_id") or item.get("category") not in FILLED:
        return None
    fields, emap = fields or load_fields(), emap or load_map()
    category = fields["categories"][item["category"]]
    known = {field["name"]: field for field in category["fields"]}
    specs = item.get("specs", {})
    sizes = [ebay_size(size) for size in (model or {}).get("storage", [])]
    colour = item.get("colour")
    plain = emap["colours"].get(colour) if colour else None
    said = seller_sizes(description, model) if not item.get("storage") else []
    hints = {"Storage Capacity": f"the seller says {said[0]}"} if len(said) == 1 else {}
    if hints:
        sizes = [said[0], *[size for size in sizes if size != said[0]]]
    filled = {
        "Brand": (item["brand"], CATALOGUE, [item["brand"]]),
        "Model": (model_value(item, known["Model"]["values"], emap["models"]), CATALOGUE,
                  [v for v in known["Model"]["values"] if v.startswith(f"{item['brand']} ")]),
        "Storage Capacity": (ebay_size(item.get("storage")), TEXT, sizes),
        "Colour": (plain, (PHOTOS if colour_from == "photos" else TEXT) + (f": {colour}" if colour != plain else "")
                   if colour else None, known["Colour"]["values"]),
        "Network": (item.get("network"), TEXT, [v for v in UK_NETWORKS if spelt(known["Network"]["values"], v)]),
        "Connectivity": (specs.get("Connectivity"), CATALOGUE, []),
        "Operating System": (specs.get("Operating System"), CATALOGUE, []),
        "Screen Size": (specs.get("Screen Size"), CATALOGUE, []),
        "Chipset Model": (chipset_value(item["brand"], specs.get("Processor"), known["Chipset Model"]["values"]),
                          CATALOGUE, []),
    }
    specifics = []
    for field in category["fields"]:
        value, source, options = filled.get(field["name"], (None, None, []))
        if field["required"] or value:
            specifics.append({"name": field["name"], "value": value, "required": field["required"],
                              "source": source if value else None, "options": options,
                              "hint": None if value else hints.get(field["name"])})
    return {"category": {key: category[key] for key in ("id", "name", "path")}, "specifics": specifics}


# ── asking eBay again: python -m flip.ebay --refresh ─────────────────────────

def app_token():
    key, secret = os.environ.get("EBAY_CLIENT_ID"), os.environ.get("EBAY_CLIENT_SECRET")
    if not key or not secret:
        sys.exit("Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET in .env: they're needed only to ask eBay again")
    basic = base64.b64encode(f"{key}:{secret}".encode()).decode()
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": f"{API}/oauth/api_scope"}).encode()
    request = urllib.request.Request(f"{API}/identity/v1/oauth2/token", data=body, headers={
        "Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)["access_token"]


def ask_ebay(path, token):
    request = urllib.request.Request(f"{API}{path}", headers={
        "Authorization": f"Bearer {token}", "Accept-Language": "en-GB", "X-EBAY-C-MARKETPLACE-ID": MARKETPLACE})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def field_from(aspect):
    rule = aspect.get("aspectConstraint", {})
    return {"name": aspect["localizedAspectName"],
            "required": bool(rule.get("aspectRequired")),  # aspectUsage says RECOMMENDED even for these
            "usage": rule.get("aspectUsage", "OPTIONAL").lower(),
            "typed": rule.get("aspectMode") == "FREE_TEXT",  # eBay takes values that aren't on its list
            "multiple": rule.get("itemToAspectCardinality") == "MULTI",
            "values": [value["localizedValue"] for value in aspect.get("aspectValues", [])]}


def refresh(path=FIELDS):
    """Ask eBay UK for each category's fields and save them."""
    token = app_token()
    tree = ask_ebay(f"/commerce/taxonomy/v1/get_default_category_tree_id?marketplace_id={MARKETPLACE}",
                    token)["categoryTreeId"]
    categories = {}
    for kind, category_id in CATEGORIES.items():
        base = f"/commerce/taxonomy/v1/category_tree/{tree}"
        aspects = ask_ebay(f"{base}/get_item_aspects_for_category?category_id={category_id}", token)["aspects"]
        name = ask_ebay(f"{base}/get_category_subtree?category_id={category_id}",
                        token)["categorySubtreeNode"]["category"]["categoryName"]
        found = ask_ebay(f"{base}/get_category_suggestions?q={urllib.parse.quote(name)}", token)
        match = next((s for s in found.get("categorySuggestions", []) if s["category"]["categoryId"] == category_id), {})
        path_names = [a["categoryName"] for a in reversed(match.get("categoryTreeNodeAncestors", []))]
        categories[kind] = {"id": category_id, "name": name, "path": " > ".join(path_names),
                            "fields": [field_from(aspect) for aspect in aspects]}
    saved = {"about": "eBay UK's fields for each of the catalogue's categories, as eBay's API gave them "
                      "(python -m flip.ebay --refresh). Not edited by hand.",
             "marketplace": MARKETPLACE, "asked": date.today().isoformat(), "categories": categories}
    Path(path).write_text(json.dumps(saved, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return saved


if __name__ == "__main__":
    from flip.draft import load_env

    load_env()
    if sys.argv[1:] != ["--refresh"]:
        sys.exit("python -m flip.ebay --refresh: ask eBay UK for each category's fields again")
    for kind, category in refresh()["categories"].items():
        needed = [field["name"] for field in category["fields"] if field["required"]]
        print(f"{kind}: {category['name']} ({category['id']}), {len(category['fields'])} fields, needs {', '.join(needed)}")
