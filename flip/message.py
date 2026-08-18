"""Draft an offer message to a seller, in your style.

    .venv/bin/python -m flip.message --learn                       # store your past messages for search
    .venv/bin/python -m flip.message "iPhone 13 128GB Midnight" --asking 220 --marketplace facebook
    .venv/bin/python -m flip.message "iPhone 13 128GB" --asking 220 --description "Broken back" --mention yes
    .venv/bin/python -m flip.message "PS5 Slim disc" --asking 300 --offer more --mode local
    .venv/bin/python -m flip.message "iPhone 13 128GB" --asking 220 --longer
    .venv/bin/python -m flip.message "iPhone 13 128GB" --asking 220 --description "Black dot on the screen" --writer ai

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
from flip.message_drafter import MESSAGE_TOKENS, WRITERS, draft_message
from flip.reader import read_listing_with_ai
from flip.money import OFFER_KINDS
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
    parser.add_argument("--offer", choices=OFFER_KINDS, default="lower",
                        help="lower than asking (the default), the asking price, or more")
    parser.add_argument("--mention", choices=["yes", "no"],
                        help="say what the listing gives this offer: its flaw, or its good condition "
                             "(default: your style decides)")
    parser.add_argument("--longer", action="store_true",
                        help="aim for about twice your usual length, 30 to 70 words (three quarters of the aim passes)")
    parser.add_argument("--previous", help="the draft to make longer, as it was drafted (implies --longer)")
    parser.add_argument("--discount", type=float, default=15, help="percent under the asking price (default 15)")
    parser.add_argument("--writer", choices=WRITERS, default="auto",
                        help="who writes: your past messages decide (auto, the default), template (no AI) or ai")
    parser.add_argument("--mode", choices=list(MODES), default="auto")
    parser.add_argument("--messages", default=str(MESSAGES), help="your past messages (CSV)")
    parser.add_argument("--learn", action="store_true", help="store your past messages for search, then stop")
    args = parser.parse_args()
    load_env()

    messages = load_messages(args.messages) if Path(args.messages).is_file() else []
    card = style_card(messages)
    index = MessageIndex()
    if args.learn:
        index.add(messages)
        print(f"{len(messages)} past messages stored for search (private/chroma, never uploaded)")
        print("your style card:", *(f"  - {line}" for line in describe(card) or ["(no messages yet)"]), sep="\n")
        return
    if not args.title or not args.asking:
        parser.error("give the listing's title and --asking price (or --learn)")

    listing = {"id": "cli", "title": args.title, "description": args.description, "asking_price": args.asking,
               "marketplace": args.marketplace}
    api = ApiModel() if os.environ.get("ANTHROPIC_API_KEY") else None
    local, log = LocalModel(max_tokens=MESSAGE_TOKENS), AuditLog()
    reading = read_listing_with_ai(listing, local, api, args.mode, log)
    mention = {"yes": True, "no": False}.get(args.mention)
    longer = args.longer or bool(args.previous)
    result = draft_message(listing, card, index, local, api, args.mode, log, args.discount,
                           kind=args.offer, mention=mention, length="longer" if longer else "usual",
                           previous=args.previous, reading=reading, writer=args.writer)

    tried = " then ".join(f"{a['model']} ({'passed' if not a['problems'] else 'failed: ' + ' | '.join(a['problems'])})"
                          for a in reading["attempts"])
    print(f"\nlisting read by {reading['read_by']}" + (f": {tried}" if tried else "")
          + "".join(f"\n  ! {line}" for line in reading["reasons"]))
    print(f"  flaws: {' / '.join(reading['flaws']) or 'none'}; pickup: {reading['pickup'] or 'not said'}"
          f"; no offers: {reading['no_offers'] or 'not said'}")

    print(f"\n{result['status'].upper()}  {result['kind']} offer {result['offer'] // 100:,} pounds"
          f"  (examples: {', '.join(result['examples']) or 'none yet'})")
    if result["answer"]:
        print(f"  {result['answer']['message']}")
        print(f"  (written by {result['writer']})")
    if result["note"]:
        print(f"  note: {result['note']}")
    if result["words"]:
        written = f"{len(result['answer']['message'].split())} words, " if result["answer"] else ""
        print(f"  longer: {written}aiming for {result['words']}"
              f"; questions it may ask: {' '.join(result['questions']) or 'none open'}")
    if result["point"]:
        print(f"  listing says: {' / '.join(result['point'])}"
              f" ({'in the message' if result['mentioned'] else 'left out'})")
    if result["ask"]:
        print(f"  ? {result['ask']} (--mention yes)")
    for line in result["reasons"]:
        print(f"  ! {line}")
    for a in result["attempts"]:
        verdict = "passed" if not a["problems"] else "failed: " + " | ".join(a["problems"])
        cost = "free" if not a["cost_pence"] else f"{a['cost_pence']:.3f}p"
        print(f"  - {a['model']} {verdict} ({a['seconds']:.1f}s, {cost})")


if __name__ == "__main__":
    main()
