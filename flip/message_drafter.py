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
4. Who writes: your own sentences with no AI (flip.writer), whatever your
   style, which beat the AI in two blind tests; the AI writes only if they
   can't say this one or fail a check. Then it's shown three of your messages
   picked by the deal (flip.retrieval: the same way of buying, kind of offer
   and reason), their old prices hidden, next to your style card (flip.style),
   and its draft passes the same checks plus how an offer is made
   (check_ai_manner). With none yet,
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
from flip.catalogue import fill_from_catalogue, load_catalogue, models_disagree, words
from flip.checks import (COLLECT_TALK, HOLD, LOCK_TALK, NO_CASH, NO_COLLECT, check_message, check_message_manner,
                         check_no_unasked_promises, ends_asking, names_other_model, offers_collection, promised_in,
                         says_no_cash)
from flip.checks import LOWBALL, UNDER_ASKING_TALK, prices_in
from flip.money import offer_for, to_pence
from flip.offers import battery_now, check_condition_talk, copied_question, point_for, question_for, says_point
from flip.picking import left_out_said, pick_flaws
from flip.offers import check_battery_reason
from flip.prompts import MESSAGE_SCHEMA, RETRY, buying_line, message_prompt, offer_words
from flip.questions import check_no_answered_questions, load_questions, open_questions
from flip.reader import code_reading, in_listing, short_flaws
from flip.retrieval import listing_text
from flip.wording import completed, worded_reason
from flip.style import (HABIT_WORDS, LOCAL_MARKETS, NOT_A_PLACE, OLD_PRICE, OFFER_SLOTS, POSTED_MARKETS, SENTENCES,
                        WHEN_BEFORE, WHEN_WORD, check_not_removed, describe, for_kind, for_market, opening, question_words,
                        item_kind, scrubbed, shortened, signed_with, unsigned, without_prices)
from flip.writer import (ASKS_OFFER, MAX_FLAW, make_longer, priced, reason_sentence, repeats, split_sign_off, the_added,
                         write_offer)
from flip.writer import NEUTRAL, collecting_from, said_once, with_reason

USUAL_WORDS = 15  # how long a message is before you have past messages to go by
CODE_SENTENCE_ROOM = 5  # of code's own sentence, still counted against the 250: it's a little over what the AI is told
# a sign-off after the AI's last sentence ("...? Thanks", "...? Let me know"): code's sentence goes before it
SIGNED_OFF = re.compile(r"(?<=[.?!])\s+((?:thanks|thank you|cheers|ta|many thanks|let me know|lmk|thx)\b[^.?!]{0,25}"
                        r"[.!]?)$", re.IGNORECASE)
# a seller who brings it and takes cash: "Delivery only, cash on delivery"
CASH_ON = re.compile(r"\bcash (?:on|upon|at) (?:delivery|drop ?off|collection|pick ?up)\b|\bcash only\b", re.IGNORECASE)
CODE_EXTRA_MOST = 100  # code's sentences let a usual message run at most this far over the 250 (not to 390)
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
# where a message says it'll collect: "Can collect from Bradford today", "Can collect today from Wakefield". The
# place ends where when starts, and when alone is none: "from Leeds LS6 Saturday", "...on Saturday", "...2nite" and
# "...ASAP" are from "Leeds LS6", "Can collect from Friday." from nowhere (26 Sep red team: each was refused as a place
# the listing doesn't give)
COLLECT_FROM = re.compile(rf"\b(?:collect|pick (?:it |them )?up|meet)\s+(?:it\s+|them\s+)?(?:{WHEN_BEFORE})?(?:from|in|at|near)\s+"
                          rf"((?!{WHEN_WORD})(?:[A-Z][\w'-]*|[A-Z]{{1,2}}\d[A-Z\d]?(?:\s*\d[A-Z]{{2}})?)"
                          rf"(?:\s+(?!{WHEN_WORD}|(?i:this|next|every)\b)(?:[A-Z0-9][\w'-]*|city centre|town centre|"
                          rf"(?:upon|on|under)(?=\s+(?!{WHEN_WORD})[A-Z])))*)")


# a message about itself or the listing, which the AI writes when told what code adds or to say what the listing does
META_TALK = re.compile(r"\barranged separately\b|\b(?:is|are|will be) (?:added|arranged|sorted|covered) (?:separately|later|after)\b|"
                       r"\bas (?:noted|described|stated|mentioned|listed|shown) (?:in|on) (?:the|your) (?:original )?"
                       r"(?:listing|description|advert|ad|post)\b|\bthe listing(?:'s description)? (?:says|states|mentions|"
                       r"describes|notes)\b|\bper (?:the|your) listing\b|\breflected in the listing|"
                       r"^\s*as noted\b|[,.]\s*as noted\b", re.IGNORECASE)
# ...but asking the seller whether it is talks to them: "Is it all as described in the ad?" (26 Sep red team)
ASKS_IF_SO = re.compile(r"^\W*(?:(?:hi|hiya|hello|hey)\b[\s,!]*(?:(?:mate|there)\b[\s,!]*)?)?(?:and |also |just |so )?"
                        r"(?:is|are|was|does|do)\s+(?:it|everything|all|they|this|that|the \w+)\b(?:\s+\w+){0,3}?\s+"
                        r"as (?:noted|described|stated|mentioned|listed|shown|advertised)\b", re.IGNORECASE)
# a quote mark the AI leaves at an end of its message: "...sell it to me.”"
STRAY_QUOTES = re.compile(r'^\s*["“”]+|["“”]+\s*$')
# who does what: you collect and you pay (26 Sep: "Can you collect?", "I'll collect cash"; red team: "Would you be able
# to pick it up?", "Could you possibly collect?"). "can collect cash in hand" is collecting and paying cash
ROLE_MIX = re.compile(r"\b(?:can|could|would|will|cud|wud) (?:you|u) (?:be able to |possibly |please )?"
                      r"(?:collect|pick (?:it |them )?up|come (?:and |& )?(?:collect|get))\b|"
                      r"\b(?:are|r) (?:you|u) able to (?:collect|pick (?:it |them )?up)\b|\bif you (?:can |could )?collect\b|"
                      r"\bfor you to collect\b|\bcollect the cash\b|\bcollect cash\b(?!\s+in\s+hand)", re.IGNORECASE)
PLACEHOLDER = re.compile(r"\[[^\]]{1,30}\]")  # "[Your Name]"
# what's asked of the offer when it's pointed back to: "would that WORK", "does that SOUND FAIR"
OK_FOR = r"(?:work|suit|be (?:ok|okay|alright|fine|possible|acceptable|any good)|sound (?:ok|okay|alright|good|fair))"
# a question that asks about the offer just made, in its sentence or any after it: "I can do £150. Would that work?",
# "Would you be happy with that?", "Would you accept that?", "Is that something you'd consider?", "...let me know if
# that works", "...Can collect today. Would that work for you?", typed "lmk if thats ok" too (26 Sep red team: only the
# next sentence was read, and only questions like "would that work"). Not one about something else: "Could you hold
# it for me?", "Is it unlocked?", "Is it ok if I collect tomorrow?", "Is the battery any good?", "Does it work with
# EE?", "Would it be possible to collect today?"
CHECK_IN = re.compile(
    rf"\b(?:would|does|is|will|can|could|wud|cud) (?:that|this) {OK_FOR}|"
    r"\b(?:would|does|will|could|wud|cud) it (?:work for (?:you|u)|suit(?: (?:you|u))?|"
    r"be (?:ok|okay|alright|fine|possible|acceptable|any good)|sound (?:ok|okay|alright|good|fair))\b"
    r"(?!\s+(?:to|if|for)\b)|\bhow does (?:that|this) sound\b|"
    r"\bis (?:that|this) (?:ok|okay|alright|fine|fair|reasonable|acceptable|doable|any good)\b|^\W*any good\b|"
    r"\b(?:happy|ok|okay|alright) with (?:that|this)\s*\?|"
    r"\b(?:would|could|will|can|wud|cud) (?:you|u) (?:be (?:happy|ok|okay|alright|willing|open|up)"
    r"(?: with| to| to accept| for)? (?:that|this|it)|(?:accept|consider) (?:that|this|it)|"
    r"(?:take|do|go for|go with) (?:that|this))\b|"
    r"\bis (?:that|this|it) something (?:you|u)(?:['’]?d| would| could| might)? (?:consider|accept|do|go for|be \w+)\b|"
    r"\bwhat do (?:you|u) (?:think|reckon)\b|^\W*(?:any )?thoughts\W*$|"
    r"\b(?:let me know|lmk)\W+(?:if|whether) (?:(?:that|this|it)(?:['’]?s| is| would be)? ?"
    r"(?:works?|suits?|ok|okay|alright|fine|any good)|(?:you|u)(?:['’]?d| would|['’]?re| are)? (?:be )?"
    r"(?:(?:happy with|ok with|okay with|accept|consider) (?:that|this|it)|interested))\b|"
    r"\b(?:let me know|lmk) (?:what (?:you|u) think|your thoughts)\b", re.IGNORECASE)
# ...or the offer's own sentence asks it as a condition: "I can do £170 cash if that works", "...if you're happy
# with that"
IF_OK = re.compile(r"\bif (?:that|this)(?:['’]?s| is)? ?(?:works?|suits?|ok|okay|alright|fine)\b|\bif (?:you['’]?re|"
                   r"you are|ur|you['’]?d be|you would be) (?:happy|ok|okay) with (?:that|this|it)\b", re.IGNORECASE)
# the asking price's words on a lower offer: "I'll pay the full £170" on a £200 listing says it's all they asked
FULL_PRICE = (r"\b(?:the full|full (?:asking|price|amount)|(?:the )?asking(?: price)?)(?: (?:asking|price|amount))*"
              r"(?: of)? ?£? ?")


def your_sentences(card, offer, pickup=""):
    """Your phrasebook's sentences (flip.style.phrasebook) with the price in,
    as a draft says them: "Can collect after 6pm.", "Is it all as described in
    the ad?". One of these in a draft, word for word, is yours, whoever put it
    there: the checks written for the AI's slips don't read it (26 Sep red team:
    they refused your own sentences). So is one the way the writer puts it,
    with the listing's place in (pickup: writer.collecting_from) and a time
    your offer already gives taken out (writer.said_once): "Can collect
    tonight, 10 mins away." is "Can collect, 10 mins away." after "...cash
    tonight?" (26 Sep red team: its "10" was refused there)."""
    phrases = (card or {}).get("phrases") or {}  # every sentence slot, a closing learned for one kind of offer too
    said = [priced(s.strip(), offer) for slot, text in phrases.items() if slot != "emoji" and isinstance(text, str)
            for s in SENTENCES.split(text) if words(s)]
    placed = [collecting_from(s, pickup) for s in said]
    return list(dict.fromkeys([*said, *placed, *(once for s in placed for once in said_once(s))]))


def not_yours(message, own=()):
    """A message's sentences that aren't one of yours word for word (own:
    your_sentences): the words the AI wrote itself."""
    mine = {tuple(words(s)) for s in own}
    return [s for s in SENTENCES.split(message.strip()) if s.strip() and tuple(words(s)) not in mine]


def full_price(sentence, offer):
    """The words that call a lower offer the full price, or None: "the full
    £170", "the asking price of 170 quid"."""
    pounds, pence = divmod(offer, 100)
    amount = rf"(?:{pounds:,}|{pounds})" + (rf"\.{pence:02d}" if pence else r"(?:\.00)?")
    return re.search(rf"{FULL_PRICE}{amount}(?!\d|[.,]\d)", sentence, re.IGNORECASE)


def check_ai_manner(message, kind, offer, posted, asks_lower=True, own=()):
    """How an offer is made, whoever wrote it: under asking it's asked ("would
    you take £150?", or said and asked about: "I can do £150, would that
    work?"), never with a hold (that's the deal for paying more); on eBay and
    Vinted no hold at the asking price (you'd just buy it); you collect and
    you pay ("Can you collect?" is the seller's job); and no placeholder left
    in ("[Your Name]"). 26 Sep: the AI's drafts broke each of these.
    asks_lower: you ask your lower offers (your messages under asking do, or
    with no style AlertFlip's do); someone who writes "I can do £170 cash" may say it.
    26 Sep red team: the offer is found written any way ("£170", "170 quid",
    "£170.00"), a lower one is never called the full price ("the full £170"),
    and own (your_sentences) is yours: who does what isn't read in one of
    them word for word ("can collect cash in hand")."""
    problems = []
    parts = [s for s in SENTENCES.split(message.strip()) if s.strip()]
    at = next((n for n, s in enumerate(parts) if offer in prices_in(s)), None)
    if kind == "lower" and at is not None:
        said = parts[at]
        asked = ends_asking(said) or bool(ASKS_OFFER.search(said) or IF_OK.search(said)) or \
            any(CHECK_IN.search(s) for s in parts[at:])
        if not asked and asks_lower:
            problems.append(f"a lower offer is said, not asked: \"{said.strip()}\" (under asking it's a question)")
        if any(HOLD.search(part) for part in parts):  # in any sentence: "...£170 cash? If so could you hold it for me?"
            problems.append("a lower offer asks them to hold it: holding it is the deal for paying more")
        full = full_price(said, offer)
        if full:
            problems.append(f"a lower offer is called the full price: \"{full.group().strip()}\" "
                            "(it's under what they ask)")
    if kind in ("asking", "more"):  # paying the asking price or more, never "Hope a bit less is ok." (26 Sep)
        low = next((p for p in parts if LOWBALL.search(p) or UNDER_ASKING_TALK.search(p)), None)
        if low:
            problems.append(f"the message says the offer is less, at or over the asking price: \"{low.strip()}\"")
    if kind == "asking" and posted and HOLD.search(message):
        problems.append("the message asks them to hold it, but on eBay and Vinted you'd just buy it at the asking price")
    mix = next((m for s in not_yours(message, own) for m in [ROLE_MIX.search(s)] if m), None)
    if mix:
        problems.append(f"the message mixes up who does what: \"{mix.group()}\" (you collect and you pay)")
    hole = PLACEHOLDER.search(message)
    if hole:
        problems.append(f"the message leaves a placeholder in: \"{hole.group()}\"")
    return problems


# the seller's own door, never said back to them: a house number, with its street or alone where the reading cut it
# at its comma ("78 Example Lane", "78", "12-14 High Street", "No. 5"), or a flat, unit or floor ("Flat 2", "Unit 4",
# "Ground floor flat"). 26 Sep red team: AlertFlip's message said "I can come and collect from 78."
STREET_ADDRESS = re.compile(r"^\s*(?:\d+[A-Za-z]?(?:\s*[-–/]\s*\d+[A-Za-z]?)?(?=[\s,]|$)|(?:no\.?|number)\s*\d)|"
                            r"\b(?:flats?|apartments?|apt|unit|block|suite|floor|maisonette)\b", re.IGNORECASE)
# ...nor their street with its full postcode, which together are a few doors: only the postcode's area ("Example Lane
# IG1 2AC" is "IG1"). A street name alone is said as the listing gives it: many are areas and stations ("Liverpool
# Street station", "Ladbroke Grove", "Brick Lane E1"; 26 Sep red team: each was left out). "St Albans" is a town
STREET_NAME = re.compile(r"\b[A-Za-z][\w'’-]*\s+(?:(?i:street|road|rd|lane|ln|avenue|ave|drive|close|crescent|cres|"
                         r"terrace|mews|way|grove|gardens|gdns|walk|row)\b|(?:St|Dr)\b(?!\.?\s+[A-Z]))")
# ...nor a full postcode, which is a few doors: only its area, "IG1 2AC" is "IG1"
FULL_POSTCODE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*\d[A-Z]{2}\b", re.IGNORECASE)
# a place to collect from in any case: "collect from rotherham", which COLLECT_FROM (capitals) can't see; not one of
# flip.style's NOT_A_PLACE ("collect in person", "at half 6", "from urs", "at lunch"), the list names_places uses
PLACE_IN_LOWER = re.compile(rf"\b(?:collect|pick (?:it |them )?up|meet)\s+(?:it\s+|them\s+)?(?:{WHEN_BEFORE})?(?:from|in|at|near)\s+"
                            r"([A-Za-z][\w'-]*)")
# a listing that won't be posted ("Collection only, no postage", "will not post"): your messages asking for postage
# aren't shown as its examples (flip.retrieval.deal_rank)
NO_POSTING = re.compile(r"\b(?:collection only|collect(?:ed)? only|no (?:postage|posting|delivery|shipping)|(?:will not|won['’]?t|"
                        r"can['’]?t|cannot|don['’]?t|do not|not able to|unable to) (?:post|ship|deliver)|not (?:posting|shipping))\b",
                        re.IGNORECASE)
# where you come and collect and pay cash (LOCAL_MARKETS), and where you pay through the site and it's posted
# (POSTED_MARKETS): flip.style's, which learns your sentences for each
# what a message promises before you have past messages: AlertFlip's way on Facebook and Gumtree
LOCAL_HABITS = {"collecting", "cash"}
# before you have past messages, on Facebook and Gumtree: what code adds for the cash and collecting a message
# leaves out (after a lower offer, the whole sentence: "would you take £380 cash and come and collect it?" didn't read)
CASH_AND_COLLECT = {frozenset({"cash", "collecting"}): "I can pay cash and come and collect it.",
                    frozenset({"collecting"}): "I can come and collect it.", frozenset({"cash"}): "I can pay cash."}
# what code adds, as the retry tells the AI
# a message that won't collect: asking the seller to bring or post it, or saying collecting can't be done. Code
# adds no "I can come and collect it." to one of these: the checks say what's wrong instead
WONT_COLLECT = re.compile(r"\byou (?:to )?(?:drop|bring|deliver|post|send)\b|\b(?:drop|bring) (?:it|them) (?:round|over|to me)\b|"
                          r"\bdeliver(?:y|ed)?\b|\bpost (?:it|them)\b|\b(?:can'?t|cannot|can not|unable to|won'?t be able to) "
                          r"collect|\bcollect(?:ion|ing)? (?:is |isn'?t |won'?t be )?(?:not )?possible\b", re.IGNORECASE)
# a listing's clauses, for its battery health (battery_in): a decimal point isn't a full stop ("84.5%")
CLAUSES = re.compile(r"(?:(?<!\d)\.|\.(?!\d)|[;!?\n()])+|,(?!\d)")


def local_market(marketplace):
    """Facebook Marketplace or Gumtree, where you come and collect and pay cash."""
    return bool(LOCAL_MARKETS.search(marketplace or ""))


def posted_market(marketplace):
    """eBay or Vinted, where you pay through the site and the item is posted: no cash."""
    return bool(POSTED_MARKETS.search(marketplace or ""))


def said_place(place):
    """The listing's pickup as a message says it back: the area, never the
    seller's door. "Leeds LS6 4AK" -> "Leeds LS6", "Example Lane IG1 2AC" ->
    "IG1", "Brick Lane E1" and "Liverpool Street station" as they are, and
    "78" (a house number the reading cut at its comma), "Flat 2", "Unit 4"
    or "12-14 High Street" -> ""."""
    full = FULL_POSTCODE.search(place)
    if STREET_ADDRESS.search(place) or full and STREET_NAME.search(place):
        return full.group(1) if full else ""
    return FULL_POSTCODE.sub(lambda found: found.group(1), place)


def battery_in(text, model):
    """The battery health a phone's listing gives as it is now ("Battery
    Health: 80%" -> "80"), or None: read one clause at a time the way the
    listing's flaws read it (flip.offers.battery_now), so not a charge level
    ("battery level 60% in the photos"), the past ("was 84%", "replaced at
    81%") or a bound ("over 85%"). A figure given only roughly ("under 80%")
    isn't one to quote, and two figures are none."""
    if not model or model.get("category") != "phones":
        return None
    found = {said[0] for clause in CLAUSES.split(text) for said in [battery_now(clause)] if said and not said[3]}
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


# a word of a title that isn't the item's short name: a brand before its family, or selling words
NOT_THE_NAME = {"apple", "samsung", "sony", "nintendo", "microsoft", "google", "selling", "sale", "my", "for", "genuine",
                "boxed", "new", "used", "brand", "the", "a", "an", "unlocked", "official", "original"}
# what a kind of item is called in general ("I like the phone"): the catalogue's category, else the title's (item_kind)
GENERIC_NAMES = {"phones": "phone", "consoles": "console", "headphones": "headphones"}


def liked_name(card, model, title):
    """What to call the item when you say you like it, the way you do for this kind of item, else for all
    (flip.style.item_naming): "phone" ("generic"), the title's short name, "PS5", "iPhone", "Dyson" ("family"), or None
    for its model name, as before."""
    naming = (card or {}).get("item_naming") or {}
    kind = item_kind(title) or {"phones": "phone", "consoles": "console"}.get((model or {}).get("category"))
    way = naming.get(kind) or naming.get("all")
    if way == "generic":
        found = GENERIC_NAMES.get((model or {}).get("category")) or kind
        if found:
            return found
        way = "family"  # no general word for it: its short name
    if way == "family":
        short = next((w for w in re.findall(r"[A-Za-z][\w'’-]*", TITLE_CUT.split(title.strip())[0])
                      if w.lower() not in NOT_THE_NAME and not re.fullmatch(r"\d+\w*", w)), None)
        return short or (model["model"].split()[0] if model else None)
    return None


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
                  reading=None, writer="auto", offer=None, rewrite_of=None, wording=None, check_reason_now=True,
                  reason_on_screen=None, flaws_said=None):
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
    you get the same message back and a warning saying so). flaws_said: how
    many of the listing's flaws a lower offer gives as its reason, 1, 2 or 3
    (the worst, by how much each cuts the price: flip.picking) or "all";
    None as before (every flaw the reader quoted is worded, code's own
    sentence gives up to two). result["reason_from"]: the reader's lines the
    reason is worded from, the picked ones when it picked."""
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
    market = listing.get("marketplace")
    posted = posted_market(market)  # eBay or Vinted: paid through the site and posted
    says_posted = bool(NO_COLLECT.search(sources))  # "Postage only", "No collection"
    collection = offers_collection(sources)  # "Collection from Leeds LS6", "Collection only"
    no_collect = says_posted and not collection  # on Facebook or Gumtree: posted, not collected
    in_person = local_market(market) and not no_collect  # Facebook or Gumtree: you collect and pay cash
    # why a message mustn't talk of collecting, asked or said: "" when it may (an eBay listing may be collection only)
    no_collecting = "on eBay and Vinted you pay through the site and it's posted" if posted and not \
        (collection and not says_posted) else "the listing says it's posted, not collected" if no_collect else ""
    locks = bool(LOCK_TALK.search(sources))  # the listing talks about iCloud or locks: a message may say what it says
    # the listing rules out cash: no message offers it, yours included (posted, cash is check_message_manner's own)
    no_cash = "the listing says no cash" if NO_CASH.search(sources) else \
        "the listing names another way to pay" if says_no_cash(listing.get("description") or "") else \
        "the listing says it's posted, not collected" if no_collect and not posted and not CASH_ON.search(sources) else ""
    cash_ok = not posted and not no_cash
    if card:
        card = for_market(card, market)  # your sentences for where you're buying, when you have them there
        card = for_kind(card, kind)  # ...and how you end this kind of offer, which the AI is told too (describe)
        if not cash_ok:
            card = without_cash(card)
        if no_collecting:
            card = without_collecting(card)
    # the reader's whole sentences (V8: a long one is split, never dropped; reader-5's 12-word cut gave some messages
    # no reason at all); flip-wording words the reason from these same sentences when it's on (flip/wording.py)
    point = point_for(kind, sources, reading["flaws"], battery_in(sources, model))
    # the reader's whole sentences, which flip-wording words the reason from (when it's on)
    lines = reading.get("quotes") or reading["flaws"]
    # how many flaws a lower offer gives, when you picked (14 Oct): the worst first, so flip-wording words only those,
    # Haiku checks only those, and the message may say no other (left_out); "all" lifts code's own two
    left_out = []
    if kind == "lower" and point and point["about"] == "flaw" and flaws_said is not None:
        if flaws_said == "all":
            point = point_for(kind, sources, reading["flaws"], battery_in(sources, model), most=None) or point
        else:  # code's own sentence (when flip-wording can't) gives the same number, picked the same way
            picked, left_out = pick_flaws(lines, sources, flaws_said)
            said = pick_flaws(reading["flaws"], sources, flaws_said)[0] if left_out else reading["flaws"]
            lines = picked if left_out else lines
            point = point_for(kind, sources, said, battery_in(sources, model), most=flaws_said) or point
    style_decides = mention is None
    if style_decides:  # your style decides; before you have one, AlertFlip's: a lower offer gives its reason
        mention = says_point(previous, point) if previous and point else \
            (card.get("praise", "condition" in card.get("mentions", [])) if kind == "more" else
             "condition" in card.get("mentions", [])) if card else kind == "lower"
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
    # your past messages for this kind of deal: the same way of buying, kind of offer and reason, then the item
    deal = {"posted": not in_person, "kind": kind, "reason": bool(point and mention), "market": market or "",
            "no_collecting": bool(no_collecting), "cash_ok": cash_ok, "no_posting": bool(NO_POSTING.search(sources))}
    examples = index.similar(query, leave_out=leave_out, deal=deal) if index else []
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
    # the listing's place only where you'd say it: you'd collect, and your own messages name places (26 Sep review:
    # "Can collect from SE1 9CK today" from someone who never names one read like a form); with no past messages
    # AlertFlip's message names it, but never a street address ("78 Example Lane" is the seller's own door): said_place
    place = reading["pickup"] or ""
    pickup = said_place(place) if "collecting" in allowed and (not card or card.get("names_places")) else ""
    result = {"item_id": listing.get("id"), "status": "needs you", "reasons": [], "kind": kind, "offer": offer,
              "listing": {key: listing.get(key) or "" for key in ("title", "asking_price", "marketplace")},
              "point": point["says"] if point else [], "mentioned": mention,
              "ask": question_for(kind, point) if point and not mention and style_decides else None,
              "note": f"The seller says: \"{reading['no_offers']}\"" if reading["no_offers"] else None,
              "reading": {k: reading[k] for k in ("flaws", "pickup", "no_offers", "read_by")},
              "length": length, "words": longer["words"] if longer else None,
              "questions": longer["questions"] if longer else [],
              "examples": [e["id"] for e in examples], "writer": None, "answer": None, "title": None,
              "attempts": [], "warnings": [], "reason_from": list(lines)}
    # steps 3-5 (flip.wording): the reason, worded from the reader's whole sentences by flip-wording, checked by Haiku,
    # fixed by Sonnet only when Haiku flags it, or None: code words it, as before. wording: None, off (code words every
    # reason); "settings", the models .env names (the app); or {"wording", "check", "fix"} models (tests)
    worded = None
    # Make it longer and Rewrite: the reason the message on screen gives, when it still says it, is kept as it is
    # (3 Oct review: wording it again brought back flip-wording's clause after Sonnet had fixed it, and paid for a
    # check of a reason the message didn't give)
    # ...and only when it was worded from the lines this listing reads as now: a listing changed since (a new one, or
    # a fault added to the description) gets its reason worded again (3 Oct: a kept reason left out "the phone turns
    # off and on sometimes", added after it was worded, and a new listing got the last one's)
    # the reader's sentences before code's story cut (reading["quotes"]): flip-wording was trained on them whole
    on_screen = (previous or rewrite_of).lower()
    same_lines = reason_on_screen is not None and \
        [q.strip() for q in reason_on_screen.get("quotes") or []] == [q.strip() for q in lines if q.strip()]
    kept = reason_on_screen if reason_on_screen and same_lines and on_screen and reason_on_screen.get("clause") and \
        reason_on_screen["clause"].lower() != "none" and reason_on_screen["clause"].lower() in on_screen else None
    if wording is not None and point and mention and point["about"] == "flaw" and kind in ("lower", "asking"):
        worded = {k: kept[k] for k in ("clause", "by", "checked")} if kept else \
            worded_reason(title, completed(lines, listing.get("description") or ""),
                          mode, models=None if wording == "settings" else wording, result=result, log=log,
                          check_now=check_reason_now)  # False: "pending", the app checks it after (check_reason)
    if worded and worded["clause"] == "none":
        if worded["checked"] == "ok":  # flip-wording and Haiku agree: nothing the seller says is a flaw by the rules
            point, mention = None, False
            result.update(point=[], mentioned=False, ask=None)
        worded = None  # unchecked: code words the reader's flaw, as before
    if worded:
        point = {**point, "worded": worded["clause"]}
        result["reason"] = worded
    # the condition checks read the checked reason as the listing's own words: "the battery health is 79%" for
    # "Battery 79" (only these two checks: places, cash and questions still read the listing alone)
    checked_sources = f"{sources}\n{point['worded']}" if point and point.get("worded") else sources
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

    # a greeting is wanted only when your own sentences open with one ("hi wud u take..." does; a habit of
    # starting with the price doesn't, whatever greeting your other messages have)
    phrases = card.get("phrases") or {}
    greets = bool(card.get("greeting")) and any(opening(phrases.get(slot) or "") for slot in ("opener", "offer"))

    written = {"added": 0}  # the AI's own words, before code's, and how many characters code added after them
    # whether you ask your lower offers: as your messages under asking do (flip.style.asks_lower; None, too few to
    # tell: asked, AlertFlip's way), not your offer sentence alone (26 Sep red team: a chatty writer with no offer
    # habit, whose lower offers asked 4 times in 5, had "I'll pay the full £170 cash." let through)
    usual = phrases.get("offer_lower") or phrases.get("offer")
    asks_lower = card["asks_lower"] is not False if "asks_lower" in card else \
        not usual or bool(ends_asking(usual) or ASKS_OFFER.search(usual))  # a card made by hand: as its sentence does
    own = your_sentences(card, offer, pickup)  # your phrasebook's sentences: the checks for the AI's slips don't read them

    def check(answer, rewrite=True, extra=0):  # extra: what code's own message may run over the 250 (the_added)
        message = answer.get("message")
        problems = check_message(message, offer, sources, asking, kind, at_least, ebay=not in_person, own=own) + \
            check_condition_talk(message, checked_sources, point, mention, kind, offer) + \
            check_battery_reason(message, point if mention else None, offer, checked_sources, title, kind)
        if left_out and mention and isinstance(message, str):  # the flaws you chose to leave out stay out
            gone = left_out_said(message, [*(point or {}).get("says", []), (point or {}).get("worded")], left_out, offer)
            if gone:
                problems.append(f"the message gives a flaw you chose to leave out: {', '.join(gone)}")
        signed = (card or {}).get("signature")  # the message on screen has your sign-off; the writer's doesn't yet
        if isinstance(message, str) and rewrite and rewrite_of and \
                words(unsigned(message, signed)) == words(unsigned(rewrite_of, signed)):
            problems.append("it's the message on screen again: a rewrite says it in other words")
        if isinstance(message, str):
            problems += check_no_answered_questions(message, sources) + check_no_unasked_promises(message, allowed)
            # AlertFlip's rules: with no past messages its "Hi", length and way of buying; yours once you have them
            problems += check_message_manner(
                message, greeting="Hi" if not card else True if greets else None,
                usual=length == "usual", short=not card and length == "usual",
                must=sorted(allowed) if not card and in_person else (),
                cash=not posted, emoji=bool(card.get("emoji")),
                praise=kind == "more" and mention, locks=locks, no_cash=no_cash, no_collecting=no_collecting,
                pay_first=not posted, title=title, short_extra=written.get("added", 0) + extra)
            problems += check_not_removed(message, card)
            sentences = re.split(r"(?<=[.!?])\s+|\n+", message)
            if model and any(names_other_model(words(sentence), model, catalogue) for sentence in sentences):
                problems.append("the message names a different item from the listing's")
            copied = copied_question(message, once, f"{sources} {code_asks}")
            if copied:
                problems.append(f"the message asks what you asked about another listing: \"{copied}\"")
            problems += check_ai_manner(message, kind, offer, bool(no_collecting), asks_lower, own)
            # in the AI's own words: your "Is it all as described in the ad?" is yours (26 Sep red team)
            meta = next((m for s in not_yours(message, own) if not (ends_asking(s) and ASKS_IF_SO.search(s))
                         for m in [META_TALK.search(s)] if m), None)
            if meta:  # "Cash and collecting is arranged separately.", "as noted in the listing" (26 Sep)
                problems.append(f"the message talks about the listing or itself, not to the seller: \"{meta.group()}\"")
            if kind == "more" and not HOLD.search(message) and not (point and mention):
                problems.append("an offer over asking says why: that it's if they'll hold it for you")
            made_up = [m.group(1) for m in COLLECT_FROM.finditer(message) if not in_listing(m.group(1), sources)]
            # ...and a place written in lower case ("can collect from rotherham 2nite"), as a lower-case writer's is
            made_up += [m.group(1) for m in PLACE_IN_LOWER.finditer(message) if m.group(1)[:1].islower()
                        and m.group(1).lower() not in NOT_A_PLACE and not in_listing(m.group(1), sources)]
            if made_up:
                problems.append(f"the message says it'll collect from a place the listing doesn't: {', '.join(made_up)}")
        return problems

    yours = None  # your own sentences' message, when it's the one on screen again
    # your own sentences first, for every style (26 Sep: 94 of 98 fresh drafts sendable, against 86 when only styles
    # that repeat went first); the AI writes only when they can't say this one
    if writer in ("template", "auto"):
        ready = written_without_ai(result, lambda answer, extra=0: check(answer, rewrite=False, extra=extra), card,
                                   kind, offer, point if mention else None, longer, at_least,
                                   item_name(found.get("model_id"), title), pickup, previous, log, in_person,
                                   cash_ok, posted=bool(no_collecting), liked=liked_name(card, model, title))
        again = ready and rewrite_of and words(result["answer"]["message"]) == words(rewrite_of)
        if again and writer == "auto":
            yours = result["answer"]  # the AI words the rewrite; this stays if it can't
            result.update(answer=None, status="needs you", writer=None)
        elif ready or writer == "template":
            if not ready:
                result["reasons"].append("No AI writing's message didn't pass the checks")
            elif again:
                result["warnings"].append("No AI writing says this one way only: pick the AI writer (Gemma 3 4B) for "
                                          "other words")
            if log:
                log.draft(result)
            return result

    # before you have past messages, code adds after a usual lower offer the reason and the cash-and-collect
    # sentence, which the AI wrote badly (the seller's words pasted in, "£320 cash and come and collect it")
    # the reason only when code can word it: else the AI is given it to write ("The back is cracked and it has bent
    # the frame at the top" is longer than code says back, and with the AI told code adds it, nothing passed: 26 Sep)
    code_reason = reason_sentence(point) if mention and point else None
    # ...and only one that says the listing's point once written: "it's screen" doesn't say "Its screen is cracked"
    # ...but a reason flip.wording worded is the AI's to place, as [REASON], which code fills in (14 Oct)
    added = ([*(["the reason"] if code_reason and says_point(code_reason, point) and not point.get("worded") else []),
              *(["cash and collecting"] if in_person else [])]
             if not card and kind == "lower" and length == "usual" else [])
    system, user = message_prompt(listing, offer, describe(card, longer["words"] if longer else None), shown,
                                  kind, None if "the reason" in added else point if mention else None, longer,
                                  pickup or None, rewrite_of or None,
                                  buying_line(allowed, in_person, bool(card), offer_words(offer),
                                              "cash and collecting" in added, cash=cash_ok),
                                  local=in_person, added=added, locks=locks, cash=cash_ok)

    def finished(reply):
        message = reply.answer.get("message") if isinstance(reply.answer, dict) else None
        if isinstance(message, str) and point and point.get("worded") and REASON_MARKED.search(message):
            # [REASON] where the AI put it: the reason flip.wording worded and Haiku checks, word for word
            message = REASON_MARKED.sub(lambda _: point["worded"], message)
            reply.answer = {**reply.answer, "message": message}
        if isinstance(message, str) and STRAY_QUOTES.search(message):  # "...sell it to me.”": a quote mark left over
            message = STRAY_QUOTES.sub("", message).strip()
            reply.answer = {**reply.answer, "message": message}
        written["message"] = message
        if not card and isinstance(message, str) and message.strip():
            more = code_sentences(message, point if "the reason" in added else None, in_person, cash_ok)
            if more and "the reason" not in added and mention:  # the AI gave the reason: code's sentence goes last,
                body, sign = split_sign_off(message.rstrip())  # before a sign-off: "...? I can pay cash... Thanks"
                signed = SIGNED_OFF.search(body)
                if signed:
                    body, sign = body[:signed.start()], f"{signed.group(1)} {sign}".strip()
                body = body.rstrip() + ("" if body.rstrip()[-1:] in ".?!" else ".")  # "...so that's my offer. I can..."
                reply.answer = {**reply.answer, "message": f"{body} {more} {sign}".strip()}
            elif more:
                reply.answer = {**reply.answer, "message": after_the_offer(message, more)}
            # the AI's own words keep to its limit; code's sentence after them isn't held against it (26 Sep: 216 of
            # the AI's with 40 of code's failed the 250 check)
            written["added"] = min(CODE_EXTRA_MOST, max(0, len(reply.answer["message"]) - len(message.strip())
                                                        - CODE_SENTENCE_ROOM)) if more else 0
        return reply

    def again(ai, answer, problems):  # one free try on this Mac, told what was turned down
        told = RETRY.format(tried=written.get("message") or answer.get("message"), problems="; ".join(problems),
                            added="")  # not what code adds: Gemma wrote that into its message (14 Oct)
        return finished(ai.ask(system, f"{user}\n\n{told}", [], MESSAGE_SCHEMA, vary=bool(rewrite_of)))

    def ai_check(answer, *more, **options):
        """The AI's message (14 Oct: Gemma pasted the seller's "It's a good condition overall, screen is burnt and
        there's some small scratches" over the checked reason): it gives the reason flip-wording worded and Haiku
        checks word for word, and a lower offer never praises the condition."""
        problems = check(answer, *more, **options)
        message = answer.get("message") if isinstance(answer, dict) else None
        if not isinstance(message, str):
            return problems
        worded = point.get("worded") if mention and point else None
        if worded and not gives_word_for_word(message, worded):
            problems.append("the message doesn't give the checked reason: write [REASON] where it goes, and code puts "
                            "it in")
        if kind == "lower" and praises_condition(message, offer):
            problems.append("a lower offer praises the condition")
        return problems

    result["answer"] = try_models(
        mode, {"local": local, "api": api},
        ask=lambda ai: finished(ai.ask(system, user, [], MESSAGE_SCHEMA, vary=bool(rewrite_of))),
        check=ai_check, result=result, log=log, again=again)
    if result["answer"] is not None:
        result["status"], result["writer"] = "ready", result["attempts"][-1]["model"]
        result["answer"] = in_your_case(result["answer"], card, offer, kind,
                                        ((result.get("reason") or {}).get("clause"), item_name(found.get("model_id"), title)))
    elif yours:  # no other wording passed: your own message stays, as it was
        result.update(answer=yours, status="ready", writer="template", reasons=[])
        result["warnings"].append("No other wording passed the checks: this is your usual message")
    if log:
        log.draft(result)
    return result


# the AI's mark for the reason, however it typed it: "[REASON]", "[reason]", "{REASON}", "[ the reason ]"
REASON_MARKED = re.compile(r"[\[{(]\s*(?:the\s+)?reason\s*[\]})]", re.IGNORECASE)


def gives_word_for_word(message, clause):
    """Whether a message gives a reason's clause as it was worded (case, curly apostrophes and spaces aside)."""
    plain = lambda text: re.sub(r"\s+", " ", re.sub(r"[’‘ʼ]", "'", text)).strip(" .").lower()
    return plain(clause) in plain(message)


def praises_condition(message, offer=None):
    """Whether a message states the item is in good condition ("It's a good condition overall"): a lower offer that
    does argues against itself. Not minding it ("happy with the condition") and questions ("Is it in good condition?")
    are fine."""
    from flip.offers import GOOD_LEVELS, NOT_MINDING, condition_said, said_in
    return any(set(condition_said(part, typos=True)) & set(GOOD_LEVELS) and not NOT_MINDING.search(part)
               for part in said_in(message, offer))


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


# cash said right after the price, the one place it can be taken out of a sentence: "£[OFFER] cash?", "£[OFFER],
# cash in hand?" -> "£[OFFER]?"
CASH_AFTER_PRICE = re.compile(r"(£\[OFFER\]|\[OFFER\])\s*,?\s*(?:(?:in|with|for)\s+)?cash(?:\s+(?:in (?:your |ya |the )?hand|"
                              r"on collection|money|ready(?: today| now| tonight)?|today|now|tonight))?", re.IGNORECASE)
# ...and what's left when it can't: "£[OFFER],?", "£[OFFER] or card?"
LEFT_OVER = re.compile(r",\s*[?.!]|\bor\s+\w+\s*[?.!]?\s*$", re.IGNORECASE)


def sentences_without(text, talks):
    """Your sentences (an opener or a closing) without the ones that talk of
    it (talks: a search): "Can collect today." goes whole, "I'm happy to
    collect at a time that suits you. Kind regards, Sam" keeps "Kind regards, Sam"."""
    return " ".join(s.strip() for s in SENTENCES.split(text) if s.strip() and not talks(s)) if text else text


def for_this_listing(card, habit):
    """The card with a habit out for this listing (cash, collecting): out the
    way a habit you removed is (the AI is told never to say it, and it's taken
    out of the examples it's shown), but marked as the listing's, so the item's
    own name ("the Pokemon Collection box", "the Johnny Cash LP") isn't refused
    as something you removed: check_message_manner, which reads the listing, says."""
    gone = card.get("removed") or {"greetings": [], "habits": [], "phrases": [], "asks": [], "emoji": False,
                                   "flaw": False}
    return {**card, "mentions": [m for m in card.get("mentions", []) if m != habit],
            "promises": [p for p in card.get("promises", []) if p != habit],
            "removed": {**gone, "habits": sorted({*gone.get("habits", []), habit}),
                        "listing_habits": sorted({*gone.get("listing_habits", []), habit})}}


def without_cash(card):
    """Your style card for a listing where cash is out (it says no cash, names
    another way to pay, or is on eBay or Vinted): an opener or closing that
    says cash goes whole ("Cash ready." didn't read as "Ready."), the offer
    sentence keeps itself with only the cash after the price taken out, or is
    none of yours here when that doesn't read ("£[OFFER] cash or card?"), so
    neither code nor the AI offers it."""
    talks = HABIT_WORDS["cash"].search

    def offer_sentence(text):
        if not text or not talks(text):
            return text
        cut = CASH_AFTER_PRICE.sub(r"\1", text)
        return None if talks(cut) or LEFT_OVER.search(cut) else cut

    phrases = {slot: offer_sentence(text) if slot in OFFER_SLOTS else
               sentences_without(text, talks) if slot in ("opener", "closing") else text
               for slot, text in (card.get("phrases") or {}).items()}
    return for_this_listing({**card, "phrases": phrases}, "cash")


def without_collecting(card):
    """Your style card for a listing that won't be collected (posted on eBay
    or Vinted, or "Postage only"): your sentences that talk of collecting go
    ("Can collect today."; "I'm happy to collect at a time that suits you.
    Kind regards, Sam" keeps "Kind regards, Sam"), an offer sentence that
    does is none of yours here, and collecting is out of what your messages
    promise, as a habit you removed is, so neither code nor the AI says it."""
    def talks(sentence):  # the checks' own test: "Can be there tonight." goes as "Can collect today." does
        return bool(COLLECT_TALK.search(sentence) or HABIT_WORDS["collecting"].search(sentence)
                    or "collecting" in promised_in(sentence))

    phrases = {slot: (None if text and talks(text) else text) if slot in OFFER_SLOTS else
               sentences_without(text, talks) if slot in ("opener", "closing") else text
               for slot, text in (card.get("phrases") or {}).items()}
    return for_this_listing({**card, "phrases": phrases}, "collecting")


def written_without_ai(result, check, card, kind, offer, point, longer, at_least, item, pickup, previous, log,
                       in_person=False, cash=True, posted=False, liked=None):
    """flip.writer's message, through the same checks as the AI's: True and
    the result is ready if it passes. If not, its problems are in the
    attempts and the AI gets its turn (or, with writer="template", you do).
    in_person: a Facebook or Gumtree listing (local_market). cash: False
    when the listing says no cash."""
    started = time.monotonic()
    questions = longer["questions"] if longer else []
    text = make_longer(previous, questions, at_least, item) if previous else \
        write_offer(card, kind, offer, point, questions, at_least, item, pickup, in_person, cash, posted, liked)
    answer = {"message": text} if text is not None else None
    # AlertFlip's 250 characters (no past messages, a usual length) are for the seller's words as written: the "the"s
    # code adds to them ("on the back") don't count (the third red team, 26 Sep)
    extra = the_added(text, lambda: write_offer(card, kind, offer, point, questions, at_least, item, pickup, in_person,
                                                cash, posted)) if text and not (card or longer) else 0
    problems = check(answer, extra) if answer else [f"there's no plain wording for what the listing says: "
                                                    f"{' / '.join(point['says'])}" if point and
                                                    with_reason(NEUTRAL[kind], kind, point) is None else
                                                    # ...else your own words are why (26 Sep red team: "given the
                                                    # condition tbh?" was put down to "Small crack on the back")
                                                    "your own sentence talks about the condition in words code can't "
                                                    f"put the listing's in: {' / '.join(point['says'])}" if point else
                                                    "your offer sentence gives a reason about the condition this draft "
                                                    "leaves out"]
    reply = Reply("template", answer=answer, seconds=time.monotonic() - started)
    result["attempts"].append({"model": "template", "problems": problems, "seconds": reply.seconds,
                               "tokens_in": 0, "tokens_out": 0, "cost_pence": 0})
    if log:
        log.attempt(result["item_id"], reply, problems, 0)
    if problems:
        return False
    result.update(answer=in_your_case(answer, card, offer, kind, ((result.get("reason") or {}).get("clause"), item)),
                  status="ready", writer="template")
    return True


def in_your_case(answer, card, offer=None, kind=None, keep=()):
    """A draft that passed, ending with your sign-off as you write it ("...I can come and collect. remi :),
    cheers", flip.style.signature: whoever wrote the rest, 3 Oct), and in lower case if you write all in lower case
    ("hi wud u take £125?"). Both only after the checks: your sign-off is your own words, and the checks read names
    and places by their capitals ("the Johnny Cash LP", "collect from Manchester")."""
    if not isinstance((answer or {}).get("message"), str):
        return answer
    # the words you write short ("Could u hold it?"), not in the checked reason or the item's name (keep), then your
    # sign-off as you write it, after them
    message = shortened(answer["message"], (card or {}).get("shortcuts"), keep)
    signs = kind not in ((card or {}).get("signature_skip") or ())  # not on a kind you send without it
    message = signed_with(message, (card or {}).get("signature")) if signs else message
    style = (card or {}).get("price_style")  # your offer written your way: "170£", "170" (3 Oct), after the checks
    if offer and style in ("after", "bare", "word"):
        said, pounds = offer_words(offer), offer_words(offer).lstrip("£")
        message = message.replace(said, {"after": f"{pounds}£", "bare": pounds, "word": f"{pounds} quid"}[style])
    return {**answer, "message": message.lower() if (card or {}).get("lowercase") else message}
