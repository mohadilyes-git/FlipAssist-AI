"""Draft listings for your test items and print what happened.

    .venv/bin/python -m flip.draft                                # your real items, local model first
    .venv/bin/python -m flip.draft --mode local --limit 3          # first 3 items, local model only
    .venv/bin/python -m flip.draft testset/items.example.json --mode api

Photo paths in the items file are read from the file's own folder. Every
attempt and outcome goes into the audit log (private/audit.sqlite3).
"""

import argparse
import json
import os
from decimal import Decimal
from pathlib import Path

from flip.ai import ApiModel, LocalModel, backup_model
from flip.attempts import MODES
from flip.audit import AuditLog
from flip.catalogue import load_catalogue, load_conditions
from flip.drafter import draft_listing
from flip.photos import photo_base64

ROOT = Path(__file__).resolve().parent.parent


def load_env(path=ROOT / ".env"):
    """Read KEY=value lines from .env into the environment, never overwriting what's set."""
    if Path(path).is_file():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def load_photos(entry, folder):
    photos, problems = [], []
    for name in entry.get("photos", []):
        try:
            photos.append(photo_base64(folder / name))
        except (OSError, ValueError) as e:
            problems.append(str(e))
    return photos, problems


def show(result, photo_problems):
    item, answer = result["item"], result["answer"] or {}
    print(f"\n{result['item_id']}  {result['status'].upper()}  {result['title'] or '(no title)'}")
    for line in [*photo_problems, *result["warnings"], *result["reasons"]]:
        print(f"  ! {line}")
    if answer:
        print(f"  condition {answer['condition_id']}: {answer['condition_note'] or '(no note)'}")
        print(f"  {answer['description']}")
    for a in result["attempts"]:
        verdict = "passed" if not a["problems"] else "failed: " + " | ".join(a["problems"])
        cost = "free" if not a["cost_pence"] else f"{a['cost_pence']:.3f}p"
        print(f"  - {a['model']} {verdict} ({a['seconds']:.1f}s, {a['tokens_in']} in / {a['tokens_out']} out, {cost})")
    if item.get("model_id") and not answer:
        print(f"  (code filled: {item['model']}, {item.get('storage') or 'storage ?'})")


def main():
    parser = argparse.ArgumentParser(description="Draft eBay listings for your test items.")
    parser.add_argument("items", nargs="?", default=str(ROOT / "testset" / "private" / "items.json"))
    parser.add_argument("--mode", choices=list(MODES), default="auto")
    parser.add_argument("--limit", type=int, help="only the first N items")
    args = parser.parse_args()
    load_env()

    path = Path(args.items)
    entries = json.loads(path.read_text(encoding="utf-8"))[:args.limit]
    catalogue, conditions = load_catalogue(), load_conditions()
    local = LocalModel()
    api = ApiModel(backup_model()) if os.environ.get("ANTHROPIC_API_KEY") else None  # as the app's
    log = AuditLog()

    results = []
    for entry in entries:
        photos, photo_problems = load_photos(entry, path.parent)
        result = draft_listing(entry, catalogue, conditions, local, api, args.mode, photos, log)
        show(result, photo_problems)
        results.append(result)

    attempts = [a for r in results for a in r["attempts"]]
    ready = sum(r["status"] == "ready" for r in results)
    local_ok = sum(bool(r["attempts"]) and not r["attempts"][0]["problems"] and r["attempts"][0]["model"] == local.name
                   for r in results)
    print(f"\n{len(results)} items: {ready} ready, {len(results) - ready} need you")
    print(f"answered by the local model: {local_ok} of {len(results)}"
          f" | API calls: {sum(a['model'] != local.name for a in attempts)}"
          f" | cost: {sum((a['cost_pence'] for a in attempts), Decimal(0)):.3f}p"
          f" | AI time: {sum(a['seconds'] for a in attempts):.1f}s")
    print("audit log: private/audit.sqlite3 (never uploaded)")


if __name__ == "__main__":
    main()
