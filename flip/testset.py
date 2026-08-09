"""Your test set as a spreadsheet. Fill testset/private/items.csv (one row per
item; it opens in Numbers or Excel; testset/items.example.csv shows the
columns), then turn it into the items.json the other tools read:

    .venv/bin/python -m flip.testset

Typos are caught here, with the row they're on: a model that isn't in the
catalogue, or a storage size, colour, option or condition that doesn't exist.
"""

import csv
import json
import sys
from pathlib import Path

from flip.catalogue import load_catalogue, words
from flip.checks import canonical

ROOT = Path(__file__).resolve().parent.parent
CONDITIONS = {"new": "1000", "opened - never used": "1500", "opened never used": "1500", "used": "3000",
              "for parts or not working": "7000", "for parts": "7000"}
NOT_IN_CATALOGUE = "not in catalogue"


def model_for(name, catalogue):
    """The catalogue model for a name written the usual way ("iPhone 13 Pro"),
    or None for "not in catalogue"."""
    if name.strip().lower() == NOT_IN_CATALOGUE:
        return None
    for model in catalogue:
        if any(words(name) == words(known) for known in [model["model"], *model["aliases"]]):
            return model
    raise ValueError(f"model {name!r} isn't in the catalogue: write it like 'iPhone 13 Pro', "
                     f"or '{NOT_IN_CATALOGUE}'")


def exact(what, value, allowed, aliases=None):
    """The catalogue's spelling of a value, or an error naming what's allowed."""
    if not value.strip():
        return None
    found = canonical(value, allowed, aliases)
    if found is None:
        raise ValueError(f"{what} {value!r} doesn't exist for this model: {', '.join(allowed)}")
    return found


def row_to_item(row, catalogue):
    model = model_for(row["right_model"], catalogue)
    answer = {"model_id": model["id"] if model else None, "storage": None, "colour": None, "network": None,
              "options": {}, "condition_id": CONDITIONS.get(row["right_condition"].strip().lower())}
    if answer["condition_id"] is None:
        raise ValueError(f"condition {row['right_condition']!r}: write New, Opened - never used, Used "
                         f"or For parts or not working")
    if model:
        answer["storage"] = exact("storage", row["right_storage"], model["storage"])
        answer["colour"] = exact("colour", row["right_colour"], model["colours"], model.get("colour_aliases"))
        answer["network"] = row["right_network"].strip() or None
        for name, values in model["options"].items():
            answer["options"][name] = exact(name.lower(), row["right_option"], list(values))
    listing = None
    if row["my_listing_title"].strip():
        listing = {"title": row["my_listing_title"].strip(), "description": row["my_listing_description"].strip(),
                   "minutes_it_took": int(row["minutes_it_took"]) if row["minutes_it_took"].strip() else None}
    return {
        "id": row["id"].strip(),
        "category": model["category"] if model else row["category"].strip(),
        "original_title": row["original_title"].strip(),
        "original_description": row["original_description"].strip(),
        "my_notes": row["my_notes"].strip(),
        "photos": [f"photos/{name.strip()}" for name in row["photos"].split(";") if name.strip()],
        "asking_price": row["asking_price"].strip(),
        "paid": row["paid"].strip(),
        "answer": answer,
        "my_listing": listing,
    }


def convert(csv_path, catalogue):
    """Every row as a test item, or ValueError naming the row with a typo."""
    with open(csv_path, newline="", encoding="utf-8-sig") as f:  # -sig: Excel's UTF-8 marker
        rows = list(csv.DictReader(f))
    items = []
    for number, row in enumerate(rows, start=2):  # row 1 is the column names
        try:
            items.append(row_to_item(row, catalogue))
        except ValueError as e:
            raise ValueError(f"row {number} ({row.get('id') or 'no id'}): {e}") from None
    return items


def main():
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "testset" / "private" / "items.csv"
    target = source.with_suffix(".json")
    try:
        items = convert(source, load_catalogue())
    except ValueError as e:
        sys.exit(f"Fix this in {source.name}, then run it again:\n  {e}")
    target.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(items)} items written to {target}")


if __name__ == "__main__":
    main()
