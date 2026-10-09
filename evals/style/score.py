"""The hard style test: 40 made-up buyers, scored per kind of habit (6 Oct 2026). See README.md here.

From the repo's root:
  .venv/bin/python evals/style/score.py                         code alone, and the app (code + the AI's checked sign-off)
  .venv/bin/python evals/style/score.py --ask gemma3:4b          also asks that model in your Ollama, saves its answers
  .venv/bin/python evals/style/score.py --answers FILE.json      scores answers saved before
  .venv/bin/python evals/style/score.py --check-key              checks every habit in the answer key really repeats
  .venv/bin/python evals/style/score.py --writers OTHER.json      the same on another set of buyers, in this format
"""
import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from flip.catalogue import contains, words  # noqa: E402
from flip.style import said_tail, style_card  # noqa: E402
from flip.style_ai import checked, merged, propose, tidy  # noqa: E402

PRICE, ITEM = "\x00price", "\x00item"
SINGLE = ("greeting", "offer", "likes", "sign_off")
FIELDS = ("greeting", "offer", "after", "likes", "sign_off", "short")


def pattern(habit):
    """A habit as words, with {price} and {item} as blanks."""
    h = (habit or "").replace("{price}", " pricexx ").replace("{item}", " itemxx ")
    return [PRICE if w == "pricexx" else ITEM if w == "itemxx" else w for w in words(h)]


def match(tokens, pat, i=0, k=0):
    """Whether pat matches tokens from i on: a {price} blank takes 1-3 words with a figure, an {item} 1-4 words."""
    if k == len(pat):
        return True
    if pat[k] in (PRICE, ITEM):
        for take in range(1, (3 if pat[k] == PRICE else 4) + 1):
            part = tokens[i:i + take]
            if len(part) < take:
                break
            if pat[k] == PRICE and not any(ch.isdigit() for w in part for ch in w):
                continue
            if match(tokens, pat, i + take, k + 1):
                return True
        return False
    return i < len(tokens) and tokens[i] == pat[k] and match(tokens, pat, i + 1, k + 1)


def in_message(field, habit, text):
    if field == "sign_off":
        want = said_tail(habit).split()
        return bool(want) and said_tail(text).split()[-len(want):] == want
    pat, tokens = pattern(habit), words(text)
    if not pat:
        return False
    if field == "greeting":
        return match(tokens, pat, 0, 0)
    return any(match(tokens, pat, i, 0) for i in range(len(tokens)))


def need(n):
    """A habit is in at least 2 of a buyer's messages and at least 40% of them (FlipAssist's HABIT and SHARE)."""
    return max(2, math.ceil(0.4 * n))


def plain(text):
    """Words as typed, for shortcuts: "2day" stays one word."""
    return set(re.findall(r"[a-z0-9']+", (text or "").lower()))


def repeats(field, habit, messages):
    texts = [m["my_message"] for m in messages]
    if field == "short":
        word, written = habit
        said = [plain(t) for t in texts]
        return sum(written in s for s in said) >= need(len(texts)) and not any(word in s for s in said)
    if field != "sign_off" and not any(t not in (PRICE, ITEM) for t in pattern(habit)):
        return False  # blanks alone ("{price}") aren't a habit
    return bool(habit) and sum(in_message(field, habit, t) for t in texts) >= need(len(texts))


def same(field, a, b):
    if field == "sign_off":
        return said_tail(a or "") == said_tail(b or "") and bool(said_tail(a or ""))
    return pattern(a) == pattern(b) and bool(pattern(a))


def norm(t):
    return words((t or "").replace("[OFFER]", " price ").replace("{price}", " price ").replace("{item}", " item "))


def found_in_card(card, key):
    """Which of the key's habits a FlipAssist style card has."""
    ph = card.get("phrases") or {}
    hits = {}
    if key.get("greeting"):
        hits["greeting"] = pattern(card.get("greeting") or "") == pattern(key["greeting"])
    if key.get("offer"):
        hits["offer"] = any(contains(norm(ph.get(s)), norm(key["offer"])) for s in ("offer", "offer_lower") if ph.get(s))
    for part in key.get("after", []):
        closings = [ph.get(s) for s in ("closing", "closing_lower", "closing_asking", "closing_more") if ph.get(s)]
        hits[f"after:{part}"] = any(contains(norm(c), norm(part)) for c in closings)
    if key.get("likes"):
        hits["likes"] = norm(card.get("likes")) == norm(key["likes"])
    if key.get("sign_off"):
        hits["sign_off"] = said_tail(card.get("signature") or ph.get("sign_off") or "") == said_tail(key["sign_off"])
    for word, short in key.get("short", []):
        hits[f"short:{word}"] = (card.get("shortcuts") or {}).get(word) == short
    return hits


def ai_raw(proposals, key, messages):
    """The AI's own answer against the key, field by field: found, missed, wrong (a phrase that does repeat but isn't
    the key's habit there) or invented (its words don't repeat in the messages at all)."""
    p = tidy(proposals) if proposals else {}
    out = []

    def hit(field, said, want):
        return same(field, said, want) or (field == "offer" and contains(norm(said), norm(want)))
    for field in SINGLE:
        said, want = (p.get(field) or "").strip(), key.get(field) or ""
        if want:
            out.append((field, "found" if said and hit(field, said, want) else "missed"))
        if said and not (want and hit(field, said, want)):
            out.append((field, "invented" if not repeats(field, said, messages) else "wrong"))
    wanted = list(key.get("after", []))
    for said in p.get("after_offer") or []:
        got = next((w for w in wanted if contains(norm(said), norm(w)) or contains(norm(w), norm(said))), None)
        if got:
            wanted.remove(got)
            out.append(("after", "found"))
        else:
            out.append(("after", "invented" if not repeats("after", said, messages) else "wrong"))
    out += [("after", "missed")] * len(wanted)
    shorts = {(s.get("word") or "").lower(): (s.get("written") or "").lower() for s in p.get("short_words") or []}
    for word, short in key.get("short", []):
        out.append(("short", "found" if shorts.get(word) == short else "missed"))
    for word, short in shorts.items():
        if [word, short] not in key.get("short", []):
            out.append(("short", "invented" if not repeats("short", (word, short), messages) else "wrong"))
    return out


def score(writers, answers):
    table = {}
    for w in writers:
        msgs, key = w["messages"], w["key"]
        code = style_card(msgs)
        proposals = (answers.get(w["id"]) or {}).get("proposals") or {}
        app = merged(code, checked(proposals, msgs), msgs)
        for habit, got in found_in_card(code, key).items():
            row = table.setdefault(habit.split(":")[0], {})
            row["habits"] = row.get("habits", 0) + 1
            row["code"] = row.get("code", 0) + int(got)
        for habit, got in found_in_card(app, key).items():
            row = table.setdefault(habit.split(":")[0], {})
            row["app"] = row.get("app", 0) + int(got)
        if answers:
            for field, what in ai_raw(proposals, key, msgs):
                row = table.setdefault(field, {})
                row[f"ai {what}"] = row.get(f"ai {what}", 0) + 1
    cols = ["habits", "code", "app"] + (["ai found", "ai missed", "ai wrong", "ai invented"] if answers else [])
    print(f"{'habit':10}" + "".join(f"{c:>12}" for c in cols))
    for field in FIELDS + ("ALL",):
        row = table.get(field, {}) if field != "ALL" else {c: sum(table.get(f, {}).get(c, 0) for f in FIELDS) for c in cols}
        print(f"{field:10}" + "".join(f"{row.get(c, 0):>12}" for c in cols))


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--ask", help="a model in your Ollama to ask, like gemma3:4b")
    args.add_argument("--answers", help="answers saved before (writer id -> {proposals})")
    args.add_argument("--check-key", action="store_true")
    args.add_argument("--writers", default=str(HERE / "writers.json"), help="buyers and their key (default: this test's 40)")
    a = args.parse_args()
    writers = json.load(open(a.writers))
    if a.check_key:
        bad = [(w["id"], f, h) for w in writers for f in SINGLE if (h := w["key"].get(f)) and not repeats(f, h, w["messages"])]
        bad += [(w["id"], "after", h) for w in writers for h in w["key"]["after"] if not repeats("after", h, w["messages"])]
        bad += [(w["id"], "short", h) for w in writers for h in w["key"]["short"] if not repeats("short", h, w["messages"])]
        print(f"{len(bad)} key habits that don't repeat" + "".join(f"\n  {b}" for b in bad))
        return
    answers = json.load(open(a.answers)) if a.answers else {}
    if a.ask:
        from flip.ai import LocalModel
        model = LocalModel(a.ask, timeout=180, max_tokens=700)  # the app's settings
        for w in writers:
            started = time.time()
            answers[w["id"]] = {"proposals": propose(w["messages"], model), "secs": round(time.time() - started, 2)}
        out = Path(a.writers).with_name(f"answers-{a.ask.replace(':', '-')}.json")  # beside the buyers asked
        json.dump(answers, open(out, "w"), indent=1, ensure_ascii=False)
        print(f"saved {out.name}")
    score(writers, answers)


if __name__ == "__main__":
    main()
