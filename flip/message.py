"""Draft an offer message to a seller, in your style.

    .venv/bin/python -m flip.message --learn                       # store your past messages for search
    .venv/bin/python -m flip.message "iPhone 13 128GB Midnight" --asking 220 --marketplace facebook
    .venv/bin/python -m flip.message "PS5 Slim disc" --asking 300 --mode local

Your past messages live in testset/private/messages.csv (testset/messages.example.csv
shows the columns). --learn reads them into private/chroma; both stay on this Mac.
"""

import argparse
import os
from pathlib import Path

from flip.ai import ApiModel, LocalModel
from flip.attempts import MODES
from flip.audit import AuditLog
from flip.draft import load_env
from flip.message_drafter import draft_message
from flip.retrieval import MessageIndex
from flip.style import describe, load_messages, style_card

ROOT = Path(__file__).resolve().parent.parent
MESSAGES = ROOT / "testset" / "private" / "messages.csv"


def main():
    parser = argparse.ArgumentParser(description="Draft an offer message to a seller, in your style.")
    parser.add_argument("title", nargs="?", help="the listing's title")
    parser.add_argument("--asking", help="the asking price in pounds, e.g. 220")
    parser.add_argument("--description", default="", help="the listing's description")
    parser.add_argument("--marketplace", default="", help="facebook, ebay, vinted, gumtree...")
    parser.add_argument("--discount", type=float, default=15, help="percent under the asking price (default 15)")
    parser.add_argument("--mode", choices=list(MODES), default="auto")
    parser.add_argument("--messages", default=str(MESSAGES), help="your past messages (CSV)")
    parser.add_argument("--learn", action="store_true", help="store your past messages for search, then stop")
    args = parser.parse_args()
    load_env()

    messages = load_messages(args.messages) if Path(args.messages).is_file() else []
    card = describe(style_card(messages))
    index = MessageIndex()
    if args.learn:
        index.add(messages)
        print(f"{len(messages)} past messages stored for search (private/chroma, never uploaded)")
        print("your style card:", *(f"  - {line}" for line in card or ["(no messages yet)"]), sep="\n")
        return
    if not args.title or not args.asking:
        parser.error("give the listing's title and --asking price (or --learn)")

    listing = {"id": "cli", "title": args.title, "description": args.description, "asking_price": args.asking,
               "marketplace": args.marketplace}
    api = ApiModel() if os.environ.get("ANTHROPIC_API_KEY") else None
    result = draft_message(listing, card, index, LocalModel(), api, args.mode, AuditLog(), args.discount)

    print(f"\n{result['status'].upper()}  offer {result['offer'] // 100:,} pounds"
          f"  (examples: {', '.join(result['examples']) or 'none yet'})")
    if result["answer"]:
        print(f"  {result['answer']['message']}")
    for line in result["reasons"]:
        print(f"  ! {line}")
    for a in result["attempts"]:
        verdict = "passed" if not a["problems"] else "failed: " + " | ".join(a["problems"])
        cost = "free" if not a["cost_pence"] else f"{a['cost_pence']:.3f}p"
        print(f"  - {a['model']} {verdict} ({a['seconds']:.1f}s, {cost})")


if __name__ == "__main__":
    main()
