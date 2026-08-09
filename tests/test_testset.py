"""The test-set spreadsheet turns into exactly the items the tools read, and a
typo stops it with the row it's on."""

import csv
import json
import re
from pathlib import Path

import pytest

from flip.catalogue import load_catalogue
from flip.testset import convert

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_CSV = ROOT / "testset" / "items.example.csv"
CATALOGUE = load_catalogue()


def write_rows(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def example_rows():
    with open(EXAMPLE_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_the_example_spreadsheet_matches_the_example_items():
    from_json = json.loads((ROOT / "testset" / "items.example.json").read_text(encoding="utf-8"))
    for item in from_json:
        item.pop("note")
    assert convert(EXAMPLE_CSV, CATALOGUE) == from_json


@pytest.mark.parametrize("column, value, error", [
    ("right_model", "iPhone 13 Pro Ultra", "model 'iPhone 13 Pro Ultra' isn't in the catalogue"),
    ("right_colour", "Space Black", "colour 'Space Black' doesn't exist for this model"),
    ("right_storage", "64GB", "storage '64GB' doesn't exist for this model"),
    ("right_condition", "Good", "condition 'Good'"),
])
def test_a_typo_is_caught_with_its_row(tmp_path, column, value, error):
    rows = example_rows()
    rows[0][column] = value
    write_rows(tmp_path / "items.csv", rows)
    with pytest.raises(ValueError, match=re.escape(f"row 2 (example-1): {error}")):
        convert(tmp_path / "items.csv", CATALOGUE)


def test_a_model_not_in_the_catalogue_is_allowed_on_purpose(tmp_path):
    rows = example_rows()
    rows[0].update(right_model="not in catalogue", original_title="Samsung Galaxy S24 128GB")
    write_rows(tmp_path / "items.csv", rows)
    answer = convert(tmp_path / "items.csv", CATALOGUE)[0]["answer"]
    assert answer == {"model_id": None, "storage": None, "colour": None, "network": None, "options": {},
                      "condition_id": "3000"}
