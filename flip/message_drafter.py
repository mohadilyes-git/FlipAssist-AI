"""The message drafter: an offer to a seller, in your own style.

1. You pick the kind of offer: lower than asking, the asking price, or more.
   Code sets the price (flip.money.offer_for). The AI never picks it.
2. The listing is read for its flaws, where to collect and whether the
   seller takes offers: by AI with code checking every word (flip.reader),
   or by code alone. "No offers" never changes your offer: the result
   carries a note with the seller's words, to show under the message.
3. Code picks what's worth saying with that offer: the flaw for a lower
   offer or the asking price, good condition for paying more (flip.offers).
   Your style decides whether that goes in; if it doesn't, the result asks you.
4. Who writes: if your past messages repeat, or there are none yet, your own
   sentences with no AI (flip.writer), which beat the AI in a blind test; the
   AI writes only if that fails a check. If they vary, the AI writes, shown
   your messages for the most similar listings (flip.retrieval) with their
   old prices hidden, next to your style card (flip.style). With none yet,
   the message is AlertFlip's: cash and collecting on Facebook and Gumtree,
   the listing's flaw or low battery as the reason for a lower offer, "hold
   it for me" at the asking price, "take the listing down" over it.
5. A longer message is about twice your usual length, and says more only with
   your usual points and questions the listing doesn't answer
   (flip.questions). It can start from the draft on screen.
6. The checks decide, whoever wrote it: the exact offer and no other price,
   the condition only as the listing says it, enough words for a longer one,
   no promise about collecting or paying that your messages don't make, no
   invented numbers or stories, no contact details, nothing off the
   platform, AlertFlip's rules (flip.checks.check_message_manner) and
   nothing you removed from your style. Models are tried in turn as for
   listings (flip.attempts).
"""

import math
import re
import time

from flip.ai import Reply
from flip.attempts import try_models
from flip.catalogue import fill_from_catalogue, load_catalogue, model_names, models_disagree, words
from flip.checks import (HOLD, LOCK_TALK, NO_CASH, check_message, check_message_manner, check_no_unasked_promises,
                         ends_asking, names_other_model, promised_in)
from flip.money import offer_for, to_pence
from flip.numbers import read_numbers
from flip.offers import check_condition_talk, copied_question, point_for, question_for, says_point
from flip.prompts import MESSAGE_SCHEMA, RETRY, buying_line, message_prompt, offer_words
from flip.questions import check_no_answered_questions, load_questions, open_questions
from flip.reader import code_reading, in_listing
from flip.retrieval import listing_text
from flip.style import (IN_THE_OFFER, OLD_PRICE, OFFER_SLOTS, SENTENCES, check_not_removed, describe, question_words,
                        scrubbed, without_prices)
from flip.writer import make_longer, reason_sentence, repeats, write_offer

USUAL_WORDS = 15  # how long a message is before you have past messages to go by
LONGER_AT_LEAST = 30
LONGEST = 70  # still well inside the 500-character limit
# a message is at most 500 characters, about 150 tokens: with this budget a
# local model that runs on stops in seconds, not half a minute
MESSAGE_TOKENS = 300
WRITERS = ("auto", "template", "ai")
MIN_ASKING = 100  # pence: under £1 is a free listing or a typo, not a price to make an offer on
# what a raw listing title adds that isn't the item: "*BARGAIN*", "FREE DELIVERY", "excellent condition boxed".
# The title is cut where the first of these starts, so a name keeps every word of its own ("Pokemon Go Plus")
TITLE_CUT = re.compile(r"\s+[-–|]\s+|[*|(\[,]")
TITLE_NOISE = re.compile(r"\s*\b(?:brand new|like new|as new|never used|hardly used|barely used|used once|unused|"
                         r"(?:in )?(?:excellent|good|great|mint|perfect|immaculate|fab)(?: condition)?|boxed|unboxed|"
                         r"bnib|bnwt|sealed|bargain|cheap|free (?:delivery|postage|p&p)|collection only|must go|"
                         r"quick sale|ono|ovno|rare|genuine|fully working|working|tested)\b.*$", re.IGNORECASE)
LEADING_NOISE = re.compile(r"^(?:brand new|new|boxed|genuine|rare)\s+", re.IGNORECASE)
MAX_NAME = 8  # words
# where a message says it'll collect: "Can collect from Bradford today"
COLLECT_FROM = re.compile(r"\b(?:collect|pick (?:it |them )?up|meet)\s+(?:it\s+|them\s+)?(?:from|in|at|near)\s+"
                          r"((?:[A-Z][\w'-]*|[A-Z]{1,2}\d[A-Z\d]?(?:\s*\d[A-Z]{2})?)(?:\s+(?:[A-Z0-9][\w'-]*|city centre|"
                          r"town centre|upon|on|under))*)")


# where you come and collect and pay cash, and where you pay through the site and it's posted
LOCAL_MARKETS = re.compile(r"\b(?:facebook|fb|gumtree)\b", re.IGNORECASE)
POSTED_MARKETS = re.compile(r"\b(?:ebay|vinted)\b", re.IGNORECASE)
# what a message promises before you have past messages: AlertFlip's way on Facebook and Gumtree
LOCAL_HABITS = {"collecting", "cash"}
# before you have past messages, on Facebook and Gumtree: what code adds for the cash and collecting a message
# leaves out (after a lower offer, the whole sentence: "would you take £380 cash and come and collect it?" didn't read)
CASH_AND_COLLECT = {frozenset({"cash", "collecting"}): "I can pay cash and come and collect it.",
                    frozenset({"collecting"}): "I can come and collect it.", frozenset({"cash"}): "I can pay cash."}
# what code adds, as the retry tells the AI
ADDED_NAMES = {"the reason": "the reason", "cash and collecting": "the cash-and-collect sentence"}
# a message that won't collect: asking the seller to bring or post it, or saying collecting can't be done. Code
# adds no "I can come and collect it." to one of these: the checks say what's wrong instead
WONT_COLLECT = re.compile(r"\byou (?:to )?(?:drop|bring|deliver|post|send)\b|\b(?:drop|bring) (?:it|them) (?:round|over|to me)\b|"
                          r"\bdeliver(?:y|ed)?\b|\bpost (?:it|them)\b|\b(?:can'?t|cannot|can not|unable to|won'?t be able to) "
                          r"collect|\bcollect(?:ion|ing)? (?:is |isn'?t |won'?t be )?(?:not )?possible\b", re.IGNORECASE)
# a seller's battery health, for the reason of a lower offer (battery_in): health in so many words...
HEALTH_CUE = re.compile(r"\b(?:health|b/?h|max(?:imum)?\s+cap(?:acity)?|(?:battery|batt)\s+(?:capacity|condition))\b|🔋",
                        re.IGNORECASE)
# ...about the battery as it is now, and a figure, not a bound: "was 84%", "replaced at 81%", "over 85%", "85%+"
NOT_NOW = re.compile(r"\b(?:was|were|used to be|had been|replaced|replacement|new battery|fitted|old (?:one|battery)|"
                     r"over|above|more than|at least|min(?:imum)?|under|below|less than|nearly|almost|about|around|"
                     r"approx\w*)\b|\d\s*%?\s*\+|>|<", re.IGNORECASE)
CLAUSES = re.compile(r"[.;!?\n()]+|,(?!\d)")


def local_market(marketplace):
    """Facebook Marketplace or Gumtree, where you come and collect and pay cash."""
    return bool(LOCAL_MARKETS.search(marketplace or ""))


def posted_market(marketplace):
    """eBay or Vinted, where you pay through the site and the item is posted: no cash."""
    return bool(POSTED_MARKETS.search(marketplace or ""))


def battery_in(text, model):
    """The battery health a phone's listing gives ("Battery Health: 80%" ->
    "80"), or None. A seller's "battery 80%" can be how charged it is in the
    photos, so only a figure in a clause that says health in so many words
    counts (HEALTH_CUE, read by flip.numbers), and only one about the battery
    as it is now: not "was 84%", "replaced at 81%", "over 85%" (NOT_NOW).
    Two figures are none."""
    if not model or model.get("category") != "phones":
        return None
    found = set()
    for clause in CLAUSES.split(text):
        if HEALTH_CUE.search(clause) and not NOT_NOW.search(clause):
            found |= read_numbers(clause, model, model_names())["battery"]
    return next(iter(found)) if len(found) == 1 else None


def longer_words(base):
    """How long a longer message is: about twice base, at least 30 words, at most 70."""
    return min(max(2 * base, LONGER_AT_LEAST), LONGEST)


def item_name(model_id, title):
    """What to call the item: its catalogue name without brackets ("AirPods
    Pro"), or for an item the catalogue doesn't know, its title without the
    selling words ("Bose QC45 headphones *BARGAIN*" -> "Bose QC45 headphones")."""
    model = next((m for m in load_catalogue() if m["id"] == model_id), None)
    if model:
        return re.sub(r"\s*\(.*?\)", "", model["model"]).strip()
    name = TITLE_NOISE.sub("", LEADING_NOISE.sub("", TITLE_CUT.split(title.strip())[0])).strip()
    return " ".join(name.split()[:MAX_NAME]) or "item"


class Refused(ValueError):
    """A request that can't be drafted as it was asked: an asking price under
    £1, an offer that doesn't fit its kind, an unknown length or writer. The
    API answers it as the caller's mistake; any other error is a fault here."""


def picked(kind, asking, offer):
    """The price you picked, if it fits the kind of offer: under asking for
    lower, the asking price itself, or over it for more."""
    if offer <= 0 or kind == "lower" and offer >= asking or kind == "more" and offer <= asking \
            or kind == "asking" and offer != asking:
        name = {"lower": "a lower offer", "asking": "an offer of the asking price", "more": "an offer over asking"}
        raise Refused(f"£{offer / 100:,.2f} isn't {name.get(kind, 'that kind of offer')} on a £{asking / 100:,.2f} listing")
    return offer


def offer_to_draft(kind, asking, offer=None, discount_percent=15):
    """The price the message offers: the one you picked, if it fits the kind
    of offer, or the one code starts from. All in pence."""
    if asking < MIN_ASKING:
        raise Refused(f"£{asking / 100:,.2f} is under £1: not an asking price to make an offer on")
    if kind not in ("lower", "asking", "more"):
        raise Refused(f"not a kind of offer: {kind!r} (lower, asking or more)")
    return picked(kind, asking, offer) if offer is not None else offer_for(kind, asking, discount_percent)


# questions that fit any listing, whoever they were asked of before
ANY_LISTING = re.compile(r"\b(?:still (?:available|for sale|up for grabs|there|around|going)|is it (?:still )?available|"
                         r"(?:has it|is it) (?:been )?sold|sold yet)\b", re.IGNORECASE)


def asked_once(message, asks):
    """What a past message asked about its own listing only: a question
    that's neither one you ask every time (asks: in 2 or more of your
    messages) nor one that fits any listing ("still available?"). Copied into
    a message about another listing, "Does it still work perfectly fine?"
    makes no sense, so the AI never sees it, and the checks refuse it."""
    return [s.strip() for s in SENTENCES.split(message.strip()) if s.strip() and ends_asking(s)
            and not OLD_PRICE.search(s)  # "would you take £185 for it?" is how you word an offer: style
            and not ANY_LISTING.search(s) and " ".join(words(without_prices(s))) not in asks]


def habits(card, examples):
    """How you buy, in your own words: what your messages promise (collecting,
    cash, postage), as your style card records it and your example messages
    show it. The same words the promise check reads (flip.checks.promised_in)."""
    return set(card.get("promises", [])).union(*(promised_in(e["my_message"]) for e in examples))


def draft_message(listing, card=None, index=None, local=None, api=None, mode="auto", log=None,
                  discount_percent=15, leave_out=None, kind="lower", mention=None, length="usual", previous=None,
                  reading=None, writer="auto", offer=None, rewrite_of=None):
    """Draft one offer message. listing has a title, description, asking_price
    (pounds, as written) and marketplace. card is your style card
    (flip.style.style_card) and index a MessageIndex of your past messages;
    both are None before you have any. kind: "lower", "asking" or "more".
    mention: whether to say what the listing gives this offer (a flaw, or good
    condition). None lets your style decide, and a draft that leaves it out
    then asks you in result["ask"]. length: "usual" or "longer". previous: the
    draft on screen to make longer, as the drafter wrote it; it's kept and
    added to, and it settles the mention the way it was drafted. reading: the
    listing as flip.reader read it; None reads it with code alone. writer:
    "auto" (your past messages decide), "template" (no AI) or "ai". offer:
    the price you picked (pence), say on a slider, in place of the one code
    starts from; it must fit the kind: under asking for lower, the asking
    price itself, or over it for more. rewrite_of: the message on screen, for
    Rewrite: the new one must say it in other words. Your own sentences say
    it one way only, so the AI writes a rewrite (or, with writer="template",
    you get the same message back and a warning saying so)."""
    if length not in ("usual", "longer"):
        raise Refused(f"not a length: {length!r} (usual or longer)")
    if writer not in WRITERS:
        raise Refused(f"not a writer: {writer!r} (auto, template or ai)")
    card = card or {}
    previous = (previous or "").strip() if length == "longer" else ""
    rewrite_of = (rewrite_of or "").strip()
    try:
        asking = to_pence(listing["asking_price"])
    except ValueError as e:
        raise Refused(str(e)) from None
    offer = offer_to_draft(kind, asking, offer, discount_percent)
    title = listing.get("title") or ""
    sources = f"{title}. {listing.get('description') or ''}"
    reading = reading or code_reading(sources)
    catalogue = load_catalogue()
    found = fill_from_catalogue(title, "", catalogue, listing.get("description") or "")
    model = next((m for m in catalogue if m["id"] == found.get("model_id")), None)
    in_person = local_market(listing.get("marketplace"))  # Facebook or Gumtree: you collect and pay cash
    locks = bool(LOCK_TALK.search(sources))  # the listing talks about iCloud or locks: a message may say what it says
    no_cash = bool(NO_CASH.search(sources))  # the listing says no cash: no message offers it, yours included
    if no_cash and card:
        card = without_cash(card)
    point = point_for(kind, sources, reading["flaws"], battery_in(sources, model))
    style_decides = mention is None
    if style_decides:  # your style decides; before you have one, AlertFlip's: a lower offer gives its reason
        mention = says_point(previous, point) if previous and point else \
            "condition" in card.get("mentions", []) if card else kind == "lower"
    mention = bool(point and mention)
    longer = None
    if length == "longer":
        base = len(previous.split()) if previous else card.get("words") or USUAL_WORDS
        removed_asks = set((card.get("removed") or {}).get("asks", []))
        longer = {"words": longer_words(base),
                  "questions": [q for q in open_questions(sources, found.get("category"), flaws=reading["flaws"])
                                if question_words(" ".join(words(q))) not in removed_asks],
                  "previous": previous or None}
    query = listing_text(title, listing.get("marketplace") or "")
    examples = index.similar(query, leave_out=leave_out) if index else []
    # how a message may say you'll buy: as your messages do, or before you have any, AlertFlip's way
    allowed = habits(card, examples) if card else (LOCAL_HABITS - ({"cash"} if no_cash else set())) if in_person \
        else set()
    gone = card.get("removed") or {}
    allowed -= set(gone.get("habits", []))  # removed from your style: your old examples don't bring it back
    once = [q for e in examples for q in asked_once(e["my_message"], set(card.get("asks", [])))]
    # the examples as the AI sees them: without a question you asked about that listing alone, and without
    # anything you removed from your style (flip.style.scrubbed)
    shown = [{**e, "my_message": scrubbed(" ".join(s.strip() for s in SENTENCES.split(e["my_message"].strip())
                                                   if s.strip() and s.strip() not in once), card)} for e in examples]
    pool = load_questions()
    code_asks = " ".join(q["ask"] for q in [*pool.get(found.get("category"), []), *pool["any"]])
    pickup = reading["pickup"] if "collecting" in allowed else ""  # only if you'd say you'll collect
    result = {"item_id": listing.get("id"), "status": "needs you", "reasons": [], "kind": kind, "offer": offer,
              "listing": {key: listing.get(key) or "" for key in ("title", "asking_price", "marketplace")},
              "point": point["says"] if point else [], "mentioned": mention,
              "ask": question_for(kind, point) if point and not mention and style_decides else None,
              "note": f"The seller says: \"{reading['no_offers']}\"" if reading["no_offers"] else None,
              "reading": {k: reading[k] for k in ("flaws", "pickup", "no_offers", "read_by")},
              "length": length, "words": longer["words"] if longer else None,
              "questions": longer["questions"] if longer else [],
              "examples": [e["id"] for e in examples], "writer": None, "answer": None, "title": None,
              "attempts": [], "warnings": []}
    disagree = models_disagree(title, listing.get("description"), load_catalogue())
    if disagree:
        result["warnings"].append(disagree)
    at_least = math.ceil(longer["words"] * 2 / 3) if longer else 0  # a little short of the aim still counts
    if previous:
        at_least = max(at_least, len(previous.split()) + 1)  # longer than the draft on screen, never shorter
        if at_least > LONGEST:
            result["reasons"].append(f"the draft is already as long as a message goes ({LONGEST} words)")
            if log:
                log.draft(result)
            return result

    def check(answer, rewrite=True):
        message = answer.get("message")
        problems = check_message(message, offer, sources, asking, kind, at_least, ebay=not in_person) + \
            check_condition_talk(message, sources, point, mention, kind, offer)
        if isinstance(message, str) and rewrite and rewrite_of and words(message) == words(rewrite_of):
            problems.append("it's the message on screen again: a rewrite says it in other words")
        if isinstance(message, str):
            problems += check_no_answered_questions(message, sources) + check_no_unasked_promises(message, allowed)
            # AlertFlip's rules: with no past messages its "Hi", length and way of buying; yours once you have them
            problems += check_message_manner(
                message, greeting="Hi" if not card else True if card.get("greeting") else None,
                usual=length == "usual", short=not card and length == "usual",
                must=sorted(allowed) if not card and in_person else (),
                cash=not posted_market(listing.get("marketplace")), emoji=bool(card.get("emoji")),
                praise=kind == "more" and mention, locks=locks, no_cash=no_cash)
            problems += check_not_removed(message, card)
            sentences = re.split(r"(?<=[.!?])\s+|\n+", message)
            if model and any(names_other_model(words(sentence), model, catalogue) for sentence in sentences):
                problems.append("the message names a different item from the listing's")
            copied = copied_question(message, once, f"{sources} {code_asks}")
            if copied:
                problems.append(f"the message asks what you asked about another listing: \"{copied}\"")
            if kind == "more" and not HOLD.search(message) and not (point and mention):
                problems.append("an offer over asking says why: that it's if they'll hold it for you")
            made_up = [m.group(1) for m in COLLECT_FROM.finditer(message) if not in_listing(m.group(1), sources)]
            if made_up:
                problems.append(f"the message says it'll collect from a place the listing doesn't: {', '.join(made_up)}")
        return problems

    yours = None  # your own sentences' message, when it's the one on screen again
    if writer == "template" or writer == "auto" and (not card or repeats(card)):
        ready = written_without_ai(result, lambda answer: check(answer, rewrite=False), card, kind, offer,
                                   point if mention else None, longer, at_least,
                                   item_name(found.get("model_id"), title), pickup, previous, log, in_person,
                                   not no_cash)
        again = ready and rewrite_of and words(result["answer"]["message"]) == words(rewrite_of)
        if again and writer == "auto":
            yours = result["answer"]  # the AI words the rewrite; this stays if it can't
            result.update(answer=None, status="needs you", writer=None)
        elif ready or writer == "template":
            if not ready:
                result["reasons"].append("the message written without AI didn't pass the checks")
            elif again:
                result["warnings"].append("Your own sentences say this one way only: choose AI for other words")
            if log:
                log.draft(result)
            return result

    # before you have past messages, code adds after a usual lower offer the reason and the cash-and-collect
    # sentence, which the AI wrote badly (the seller's words pasted in, "£320 cash and come and collect it")
    added = ([*(["the reason"] if mention else []), *(["cash and collecting"] if in_person else [])]
             if not card and kind == "lower" and length == "usual" else [])
    system, user = message_prompt(listing, offer, describe(card, longer["words"] if longer else None), shown,
                                  kind, None if "the reason" in added else point if mention else None, longer,
                                  pickup or None, rewrite_of or None,
                                  buying_line(allowed, in_person, bool(card), offer_words(offer),
                                              "cash and collecting" in added, cash=not no_cash),
                                  local=in_person, added=added, locks=locks, cash=not no_cash)
    written = {}  # the AI's own words, before code's

    def finished(reply):
        message = reply.answer.get("message") if isinstance(reply.answer, dict) else None
        written["message"] = message
        if not card and isinstance(message, str) and message.strip():
            more = code_sentences(message, point if "the reason" in added else None, in_person, not no_cash)
            if more:
                reply.answer = {**reply.answer, "message": after_the_offer(message, more)}
        return reply

    def again(ai, answer, problems):  # one free try on this Mac, told what was turned down
        told = RETRY.format(tried=written.get("message") or answer.get("message"), problems="; ".join(problems),
                            added=f" Code adds {' and '.join(ADDED_NAMES[a] for a in added)} after yours." if added else "")
        return finished(ai.ask(system, f"{user}\n\n{told}", [], MESSAGE_SCHEMA, vary=bool(rewrite_of)))

    result["answer"] = try_models(
        mode, {"local": local, "api": api},
        ask=lambda ai: finished(ai.ask(system, user, [], MESSAGE_SCHEMA, vary=bool(rewrite_of))),
        check=check, result=result, log=log, again=again)
    if result["answer"] is not None:
        result["status"], result["writer"] = "ready", result["attempts"][-1]["model"]
    elif yours:  # no other wording passed: your own message stays, as it was
        result.update(answer=yours, status="ready", writer="template", reasons=[])
        result["warnings"].append("No other wording passed the checks: this is your usual message")
    if log:
        log.draft(result)
    return result


def code_sentences(message, point, in_person, cash=True):
    """What code adds after the AI's message before you have past messages:
    a lower offer's reason (writer.reason_sentence) when the message doesn't
    say it, and on Facebook and Gumtree the cash and collecting it leaves out
    ("I can pay cash and come and collect it.", or the half it's missing):
    no cash when the listing says no cash (cash False), and no collecting for
    a message that won't collect (WONT_COLLECT: the checks say what's wrong)."""
    more = []
    if point and not says_point(message, point):
        more.append(reason_sentence(point) or "")
    wanted = (LOCAL_HABITS - ({"cash"} if not cash else set()) - ({"collecting"} if WONT_COLLECT.search(message)
                                                                  else set())) if in_person else set()
    missing = frozenset(wanted - promised_in(message))
    if missing:
        more.append(CASH_AND_COLLECT[missing])
    return " ".join(m for m in more if m)


def after_the_offer(message, more):
    """The message with code's sentences right after the one with the offer,
    as AlertFlip writes them: "Hi, would you take £150? I'm offering that
    because ... I can pay cash and come and collect it. Let me know." At the
    end if no sentence has the price."""
    sentences = [part.strip() for part in SENTENCES.split(message.strip()) if part.strip()]
    at = next((n + 1 for n, part in enumerate(sentences) if "£" in part), len(sentences))
    if sentences and sentences[at - 1][-1:] not in ".!?":
        sentences[at - 1] += "."
    return " ".join([*sentences[:at], more, *sentences[at:]])


def without_cash(card):
    """Your style card for a listing that says no cash: cash is out of it the
    way a habit you removed is (out of your sentences too: "...£[OFFER] cash?"
    -> "...£[OFFER]?"), so neither code nor the AI offers it."""
    card = {**card, "mentions": [m for m in card.get("mentions", []) if m != "cash"],
            "promises": [p for p in card.get("promises", []) if p != "cash"],
            "phrases": {slot: IN_THE_OFFER["cash"].sub("", text) if slot in (*OFFER_SLOTS, "closing") and text else text
                        for slot, text in (card.get("phrases") or {}).items()}}
    gone = card.get("removed") or {"greetings": [], "habits": [], "phrases": [], "asks": [], "emoji": False,
                                   "flaw": False}
    return {**card, "removed": {**gone, "habits": sorted({*gone.get("habits", []), "cash"})}}


def written_without_ai(result, check, card, kind, offer, point, longer, at_least, item, pickup, previous, log,
                       in_person=False, cash=True):
    """flip.writer's message, through the same checks as the AI's: True and
    the result is ready if it passes. If not, its problems are in the
    attempts and the AI gets its turn (or, with writer="template", you do).
    in_person: a Facebook or Gumtree listing (local_market). cash: False
    when the listing says no cash."""
    started = time.monotonic()
    questions = longer["questions"] if longer else []
    text = make_longer(previous, questions, at_least, item) if previous else \
        write_offer(card, kind, offer, point, questions, at_least, item, pickup, in_person, cash)
    answer = {"message": text} if text is not None else None
    problems = check(answer) if answer else [f"there's no plain wording for what the listing says: "
                                             f"{' / '.join(point['says'])}"]
    reply = Reply("template", answer=answer, seconds=time.monotonic() - started)
    result["attempts"].append({"model": "template", "problems": problems, "seconds": reply.seconds,
                               "tokens_in": 0, "tokens_out": 0, "cost_pence": 0})
    if log:
        log.attempt(result["item_id"], reply, problems, 0)
    if problems:
        return False
    result.update(answer=answer, status="ready", writer="template")
    return True
