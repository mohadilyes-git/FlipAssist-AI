"""40 writer briefs for the hard style test (6 Oct 2026): code picks who each made-up writer is and which habits
they repeat, so every kind of writer and habit is covered; Claude agents then write the messages to the brief."""
import json, random
from pathlib import Path

random.seed(20261112)
VOICES = [
    "texts in lowercase with shortcuts (u, pls, cud, wud, 2day, 2nite, thx), hardly any punctuation",
    "WRITES EVERYTHING IN CAPITALS, older man, blunt",
    "polite and formal, full sentences, signs off with regards and their name",
    "emoji-heavy young buyer, several emojis per message",
    "eBay-style one-liners: very short, just the price and a few words",
    "chatty run-on sentences with no full stops, explains why they want it",
    "non-native English speaker: simple grammar mistakes ('I can give 150 pound, is ok?'), polite",
    "Scottish, uses 'aye', 'wee', 'pal', 'cheers'",
    "American buyer on Mercari/OfferUp/Craigslist, dollars, 'meet up', 'Venmo/cash'",
    "fast typer who makes typos ('yuo', 'thnaks', 'woudl'), but the SAME typo in their repeated habits",
    "says 'hun' and ends with kisses (x, xx)",
    "trader / reseller: businesslike, 'cash buyer', 'can collect today', short",
    "lowercase with ':)' smileys, signs off with their name and a smiley then 'cheers' (like 'sam :), cheers')",
    "teenager with slang ('bro', 'fr', 'ngl', 'lmk')",
    "puts the price in odd formats ('150£', '150 quid', '£150.00', '150 pounds') but each writer keeps ONE format",
    "very long, careful messages asking questions about the item before offering",
]
ITEMS = [("iPhone 13 128GB Blue", 220), ("iPhone 12 64GB", 150), ("Samsung Galaxy S23 256GB", 330), ("Galaxy S21 Ultra", 260),
         ("MacBook Air M1 8GB 256GB", 450), ("MacBook Pro 14 M1 Pro", 950), ("PS5 Disc Edition", 300), ("Xbox Series X", 280),
         ("Nintendo Switch OLED", 220), ("AirPods Pro 2", 120), ("Apple Watch Series 8", 180), ("iPad Air 5th gen", 380),
         ("Dyson V11 cordless", 200), ("Sony WH-1000XM4", 140), ("Canon EOS 250D", 320), ("DJI Mini 3", 300),
         ("North Face puffer jacket", 90), ("Nike Air Max 90 size 9", 60), ("Ikea Kallax shelf", 35), ("Grey fabric 3 seater sofa", 150),
         ("Mountain bike 27.5in", 180), ("Garmin Forerunner 255", 160), ("Bose SoundLink speaker", 70), ("Ninja air fryer", 60),
         ("Lego Millennium Falcon", 400), ("GoPro Hero 10", 200), ("Kindle Paperwhite", 70), ("Steam Deck 512GB", 340)]
HARD = [
    # a habit only for a buyer with 5 messages (2 of 6 or more is under 40%): of the 9 it was planned for, only w36
    "one habit appears in exactly 2 of the messages (still a habit)",
    "two closings that look alike but use different words (neither is a habit)",
    "the greeting changes capital letters and punctuation between messages but is the same word(s)",
    "one sentence appears in only ONE message but sounds like a habit (it is not one)",
    "the 'I like the item' habit names each item differently (its own short name each time)",
    "the sign-off has their name and a smiley, written the same way each time",
    "some messages skip some of the habits",
    "one message is very short and has almost no habits",
]


def brief(n):
    voice = VOICES[n % len(VOICES)]
    count = random.choice([5, 6, 6, 7, 8, 8, 10])
    has = {"greeting": random.random() < 0.8, "offer": random.random() < 0.95,
           "after": random.choice([0, 1, 1, 1, 2]), "likes": random.random() < 0.45,
           "sign_off": random.random() < 0.7 or "signs off" in voice or "sam :)" in voice,
           "short": ("shortcuts" in voice or "teen" in voice or random.random() < 0.15)}
    items = random.sample(ITEMS, count)
    return {"id": f"w{n + 1:02d}", "voice": voice, "messages": count,
            "habits": {k: v for k, v in has.items() if v}, "hard": random.sample(HARD, 2),
            "items": [{"listing_title": t, "asking_price": p} for t, p in items],
            "marketplace": "craigslist/offerup/mercari" if "American" in voice else random.choice(
                ["facebook", "facebook", "vinted", "gumtree", "ebay"])}


BRIEFS = [brief(n) for n in range(40)]
# a hard case brings the habit it needs: a sign-off case a sign-off, an "I like the item" case a likes habit (6 Oct,
# once the plan was drawn: 6 sign-offs and 2 likes habits, all of them written into the buyers' messages)
for b in BRIEFS:
    for case in b["hard"]:
        if "sign-off" in case:
            b["habits"].setdefault("sign_off", True)
        if "'I like the item'" in case:
            b["habits"].setdefault("likes", True)
json.dump(BRIEFS, open(Path(__file__).with_name("briefs.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
from collections import Counter
print(len(BRIEFS), "briefs;", Counter(len(b["habits"]) for b in BRIEFS), "habits each;",
      sum("likes" in b["habits"] for b in BRIEFS), "with likes,", sum("short" in b["habits"] for b in BRIEFS), "with shortcuts,",
      sum("sign_off" in b["habits"] for b in BRIEFS), "with sign-offs,", sum(b["messages"] for b in BRIEFS), "messages")
