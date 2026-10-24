"""The safety checks. Every AI answer goes through these before you see it.

A failed check means: throw the answer away and let the paid model try; if
that fails too, the item is marked "needs you". Each check is plain code, so it
gives the same result every time and costs nothing to run. The checks can
catch an answer that's broken or made up; they can't tell whether a believable
answer is true. That's why you approve every draft.
"""

import json
import re
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from flip.catalogue import (COMMON_COLOURS, PLUS_MEANS_AND, colours_named, find_phrase, item_colour_mentioned,
                            options_named, sizes_in, words)
from flip.money import pounds, to_pence
from flip.numbers import TYPED_BATTERY, battery_worded

MAX_CONDITION_NOTE = 1000  # eBay's limit for the condition description
MAX_DESCRIPTION = 1500     # our own limit: short listings read better and cost fewer tokens
MAX_MESSAGE = 500
SHORT_MESSAGE = 250  # characters: a usual message in AlertFlip's style
MAX_QUESTIONS = 2  # in a usual message
GREETING_WORDS = {"hi", "hiya", "hello", "hey", "alright", "morning", "afternoon", "evening", "yo"}
EMOJI = re.compile("[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF☀-➿⬀-⯿‼⁉]")  # flags, stars and "‼️" too
# AlertFlip's rules for a message to a seller (check_message_manner): iCloud and locks are asked once the
# seller replies; nothing is paid before you collect; no compliments, which read as softening them up
LOCK_TALK = re.compile(r"\b(?:i ?cloud|find my(?! (?:way|feet|bearings|house|place|address|keys))|fmi|activation|"
                       r"apple[- ]?id|apple account|google account|frp|account lock)\b", re.IGNORECASE)
# a price said between paying and when: "pay £200 now", "pay you the full £200 for it straight away", "pay 200 quid
# now", and a phrasebook's "pay £[OFFER] now" (26 Sep red team: an AI's "I can pay £200 now" got past PAY_FIRST, and so
# did the template's). Not "£200 cash now": cash is paid when you meet
PAID_PRICE = r"(?:the )?(?:full )?(?:£\s?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?|£?\[OFFER\]|\d+ ?(?:quid|pounds)) " \
             r"(?:for (?:it|this|them|that) )?"
# ...unless the words right after the time tie paying to meeting: "pay £200 now on collection", "straight away in cash
# when I collect", "now, cash on collection", "asap - cash in hand", "right away after I've had a look" (26 Sep red team:
# only the next word was read, so these were refused); never with another way of paying after it ("now, cash or PayPal")
# (26 Sep final recheck: "upon confirmation", "after I hear back", "after we agree", "by cash app" and "cash or card"
# were let through as meeting: only words that say you meet count)
MEETING = r"(?:collect\w*|pick\w*(?: (?:it|them|the phone))? ?up|pickup|meet\w*|come|coming|arriv\w*|get there|" \
          r"see (?:it|you|the phone)|seen (?:it|them|the phone)|seeing it|(?:have|had|having) a look|" \
          r"check(?:ed|ing)? it|look(?:ed)? at it|" \
          r"hand ?over|handing over)"
WHEN_YOU_MEET = r"(?!\s*[,\-–—]?\s*(?:(?:on|upon|at) (?:the )?(?:collection|collecting|pick ?up|pickup|meeting|arrival|" \
                r"handover|hand over|the door)|(?:when|whenever|once|after) (?:i|we|u|you)(?:['’]ve| have| had)? " \
                rf"{MEETING}|after (?:seeing|having a look|checking)|in person|" \
                r"(?:in |with |by )?cash(?! ?app\b)(?!\s*(?:or|/|&)\s))\b(?![^.?!]*\b(?:transfer|bank|bacs|pay ?pal|cash ?app|card)))"
PAY_FIRST = re.compile(
    r"\b(?:deposit|up[- ]?front|(?<!thanks )(?<!thank you )(?<!thank u )(?<!thanks u )(?<!thankyou )(?<!ty )(?<!thx )"
    r"(?<!cheers )(?<!much )in advance|"
    r"(?:pay|paying|transfer|transferring)\b[^.?!]{0,30}\bbefore (?:i |we )?(?:collect|collection|meet|see)\w*)\b"
    rf"|\bpay(?:ing)? (?:you |it )?(?:{PAID_PRICE})?(?:right )?(?:now|first(?! thing)|straight ?away|right away|asap|"
    rf"immediately|instantly)\b{WHEN_YOU_MEET}"
    # sending it, the price said too: "transfer £200 now", "send you £200 over now", "paypal you 200 quid tonight" (26 Sep
    # red team: only paying took a price, so "I can transfer £210 now if you can hold it" went out on Facebook)
    rf"|\b(?:transfer|bacs|paypal|send|sending|ping)\s+(?:it |you |over |the )?(?:{PAID_PRICE})?(?:over |across )?"
    r"(?:money |payment |cash |funds |it )?"
    r"(?:now|today|tonight|over|first|asap|straight ?away|right away|immediately|instantly|in advance)\b"
    r"|\bsend (?:you )?(?:the )?(?:money|payment)\b", re.IGNORECASE)
COMPLIMENT = re.compile(
    r"\blooks (?:really |very |so |absolutely |super )?(?:nice|lovely|great|perfect|brilliant|amazing|mint|immaculate|"
    r"gorgeous|stunning|beautiful|cracking|smart|clean|class)\b(?! (?:for|to) me)|\bwell (?:looked|cared)\b"
    r"|\b(?:nice|lovely|cracking|beautiful|gorgeous|stunning|smart|cool|great|brilliant|amazing|mint) (?:looking )?"
    r"(?:console|phone|item|one|bit of kit|piece|laptop|watch|bike|set|headphones|earbuds|camera|tv|machine|unit|device|"
    r"tablet|ipad|iphone|kit)\b|(?<!not in )(?<!not )\bgreat condition\b|\bbeautiful\b|\bstunning\b|\bgorgeous\b",
    re.IGNORECASE)
# a listing that won't take cash: then no message offers it (decided 14 Sep: "mention cash unless the listing
# description says no cash")
NO_CASH = re.compile(r"\bno cash(?: payments?)?\b|\bcash (?:is |are )?(?:not|never) (?:accepted|taken)\b|"
                     r"\bcash isn'?t (?:accepted|taken)\b|\bnot (?:accepting|taking) cash\b|\bnot cash\b|\bcashless\b|"
                     r"\b(?:do not|don'?t|won'?t|can'?t|cannot|no longer) (?:take|accept) cash\b|"
                     r"\b(?:no longer|not) (?:taking|accepting) cash\b|\b(?:don'?t|do not|can'?t|cannot|won'?t|will not) "
                     r"(?:do|take|accept) cash\b|\bcash payments? (?:are |is )?not accepted\b|"
                     r"\bcash (?:will|would|can|is) not be (?:accepted|taken)\b|\bcash won'?t be (?:accepted|taken)\b|"
                     r"\b(?:prefer(?:red)?|would rather|rather) not (?:to )?(?:take|accept|have|do) cash\b|"
                     # a card only with a word of paying: "Graphics card only" isn't a way to pay (26 Sep)
                     r"\b(?:bank transfers?|transfer|pay ?pal|card payments?|bacs)(?: payments?)? only\b|"
                     r"\bonly (?:accept(?:ing)? )?(?:bank transfers?|transfer|pay ?pal|card payments?|bacs)\b",
                     re.IGNORECASE)
# ...and one that names another way to pay and offers no cash: "Bank transfer upon collection" (decided 26 Sep: a
# listing that names another way to pay gets no cash offer). "Cash or bank transfer" takes cash; "No PayPal or bank
# transfer" names no other way (offered)
OTHER_PAYMENT = re.compile(r"\bbank transfers?\b|\bbacs\b|\bpay ?pal\b|\b(?:card|contactless) payments?\b|"
                           r"\bpay(?:ment)? (?:by|via|with) (?:card|(?:bank )?transfer|bank|bacs)\b|"
                           r"\bby (?:bank )?transfer\b|\bfaster payments?\b|\brevolut\b|\bmonzo\b|"
                           r"\btransfer (?:on|upon|at|before|when) (?:collection|collecting|pick ?up)\b", re.IGNORECASE)
# what a listing says isn't so, in the clause of what it names: "No PayPal or bank transfer", "bank transfer not
# accepted", "Beware of scams asking for PayPal"
CLAUSE_END = re.compile(r"[.!?;\n]")
NEGATED_BEFORE = re.compile(r"\b(?:no|not|never|without|won'?t|can'?t|cannot|don'?t|doesn'?t|refuse|avoid)\b"
                            r"(?! sure| idea| problem| worries| bother| returns?| refunds?| offers?| swaps?| trades?|"
                            r" time ?wasters?| silly| low ?ball| messing| chancers)", re.IGNORECASE)
# a word that starts a new thought in a clause: "Can't post so collection only"
JOINS = re.compile(r"\b(?:so|because|cos|as|and|but|therefore|hence|which|then|thus)\b", re.IGNORECASE)
NOT_SO_AFTER = re.compile(r"^\s*(?:[\w']+\s+){0,2}(?:(?:is|are|will be)\s+)?(?:not|never)\b|"
                          r"^\s*(?:[\w']+\s+){0,2}(?:isn'?t|aren'?t|won'?t be)\b", re.IGNORECASE)  # "...in person not available"
# a warning about a way to pay ("Beware of scammers asking for PayPal"), not the reason for one ("Due to scammers,
# bank transfer on collection", "Collection only due to scammers"); not "fake notes" either
WARNING = re.compile(r"\bbeware\b|\bwatch out\b|\bscam (?:alert|warning)s?\b|\bscammers? (?:asking|who ask|ask)\b",
                     re.IGNORECASE)
# a phone's or watch's own payment feature, not the seller's way of being paid: "NFC working, card payments fine"
PAYMENT_FEATURE = re.compile(r"^\s*(?:are |is )?(?:all )?(?:fine|work\w*|ok|okay|tested|enabled|set up)\b", re.IGNORECASE)
FEATURE_BEFORE = re.compile(r"\b(?:nfc|apple pay|google pay|samsung pay|wallet|takes|accepts|reader|terminal)\b"
                            r"[^.,;]{0,15}$", re.IGNORECASE)
# cash a listing names that isn't a way to pay: "Selling as I need the cash"
CASH_NOT_PAYING = re.compile(r"\b(?:need|needing|want|wanting|raise|raising|spare)\s+(?:the\s+|some\s+)?cash\b",
                             re.IGNORECASE)
# a listing that's posted only: no collecting, so no cash either ("Postage only", "No collection", "Can only post").
# Not "Collection or delivery only", "postage only £4.50 extra", "No collections on Sundays" or "no meet ups"
# (you come to them), and a listing that also offers collection (offers_collection) is collected (26 Sep)
NO_COLLECT = re.compile(
    r"(?<!\bor )(?<!/)(?<!& local )(?<!and local )(?<!& )(?<!and )\b(?:postage|post(?:ed)?|postal|posting|delivery|"
    r"shipping|courier)\s+only\b(?!\s*(?:£|\d|extra|costs?))|"
    r"\b(?:can |will )?only\s+(?:be\s+)?(?:posted|post(?:ing)?|send(?:ing)?|ship(?:ped|ping)?)\b"
    r"(?!\s+(?:tracked|recorded|signed|special|insured|first class|second class|1st|2nd|to (?:the )?uk|to uk|within|"
    r"in the uk|uk|with|via|by|abroad|overseas|to the|to mainland))|"
    r"\bno\s+(?:collections?|collecting|pick[- ]?ups?)\b(?!\s+(?:on|before|after|until|till|at|between|during|from|"
    r"tomorrow|today|tonight|weekends?|(?:mon|tues|wednes|thurs|fri|satur|sun)days?|evenings?|mornings?|nights?)\b)|"
    r"\bcollections?(?:\s+in person)?\s+(?:is not|isn'?t|are not|aren'?t|not)\s+(?:possible|available|an option)\b"
    r"(?!\s+(?:before|after|until|till|on|at|between|during|tomorrow|today|tonight)\b)|"
    r"\\bcollections?\\s+(?:is\\s+)?unavailable\\b(?!\\s+(?:on|before|after|until|till|til|at|between|during|in the|this|next|over the|tomorrow|today|tonight|weekends?|"
    r"(?:mon|tues|wednes|thurs|fri|satur|sun)days?|evenings?|mornings?|nights?)\\b)|\\bnot available for collection\\b"
    r"(?!\\s+(?:on|before|after|until|till|til|at|between|during|in the|this|next|over the|tomorrow|today|tonight|weekends?|"
    r"(?:mon|tues|wednes|thurs|fri|satur|sun)days?|evenings?|mornings?|nights?)\\b)|"
    r"\b(?:cannot|can'?t|won'?t) be collected\b(?!\s+(?:before|after|until|till|on|at|between|during|tomorrow|today)\b)|"
    # "If you can't collect I can post": the buyer's, collection is the default
    r"(?<!if you )(?<!if u )(?<!if you're )(?<!if youre )(?<!if you are )\\b(?:can(?:'|no)?t|cannot|unable to|won'?t|"
    r"don'?t|not doing)\\s+(?:do\\s+|offer\\s+)?collect(?:ion|ions)?\\b(?!\\s+(?:on|before|after|until|till|til|at|between|during|in the|this|next|over the|tomorrow|today|tonight|weekends?|"
    r"(?:mon|tues|wednes|thurs|fri|satur|sun)days?|evenings?|mornings?|nights?)\\b)",
    re.IGNORECASE)
# a listing that offers collection: "Collection only", "Collection from Leeds", "collection or post", "Local pickup"
COLLECTION_OFFERED = re.compile(
    r"\bcollection (?:only|from|at|or|available|preferred|welcome|possible|is fine|in person)\b|\blocal collection\b|"
    r"\bcollect (?:only|from|in)\b|\bor collect(?:ion)?\b|"
    r"\bpick[- ]?up (?:only|from|in|available)\b|\blocal pick ?up\b|\bcan be collected\b|\bbuyer (?:to )?collects?\b|"
    r"\b(?:to|for) collection\b|\bcollect(?:ion)? in person\b|\bcan be picked up\b|"
    r"\b(?:happy|ok|okay|fine) for (?:you|the buyer|buyer) to collect\b|\b(?:you're |you are )?welcome to collect\b|"
    r"\byou can collect\b|\bbuyer can collect\b|\bcollection (?:&|and|/) (?:local )?(?:delivery|post(?:age)?)\b",
    re.IGNORECASE)
COLLECTION_ONLY = COLLECTION_OFFERED  # what an eBay or Vinted listing says when you may collect
# talk of coming to the seller or of cash, asked or said ("Can collect it today?", "can come 2day", "would you prefer
# cash?"): on a listing that's posted, neither fits. One pattern for the checks and for taking it out of your
# sentences (flip.message_drafter.without_collecting). Not "collector's edition", "collectable", nor "meet you
# halfway" on a price
COLLECT_TALK = re.compile(r"\b(?:collect(?:ing|ion|ed)?|pick(?:ing)? (?:it |them |this )?up|pick ?up|"
                          r"come (?:and |& )?(?:get|grab|see|collect|pick)|come (?:round|over|by|straight over|to yours|"
                          r"today|tonight|tomorrow|tmrw|2day|2nite|later|now|this (?:evening|afternoon|morning))|"
                          r"can come (?:today|tonight|tomorrow|tmrw|2day|2nite|later|now|round|over|by|this \w+)|"
                          r"be round|pop (?:round|over|by)|swing (?:by|round)|drop by|nip (?:round|over)|"
                          r"meet-?up|meet up|meet (?:you )?(?:today|tonight|tomorrow|later|this \w+|in|at|somewhere|"
                          r"anywhere)|come (?:and |& )?view|come to (?:you|yours|your (?:place|house|address))|"
                          r"drop (?:round|over|in)|get (?:it|them) (?:today|tonight|tomorrow|tmrw|2day|now|later|this \w+)|"
                          r"where(?: ?abouts)? (?:can|could|shall|should) we meet|"
                          r"drive over|head over|be there|grab (?:it|them))\b", re.IGNORECASE)
CASH_TALK = re.compile(r"\bcash\b", re.IGNORECASE)
# a word of the title that names a set, not a pickup: "the whole collection", "my record collection"
SET_OF = re.compile(r"\b(?:the|whole|full|entire|new|my|your|his|her|their|this|that|our|record|card|game|summer|"
                    r"winter|autumn|spring)\s+(?:\w+\s+)?$", re.IGNORECASE)


def clause_around(text, start, end):
    """What comes before a match in its clause, and what after: the clause runs
    between a full stop, ! ? ; or line break and the next."""
    left = max((m.end() for m in CLAUSE_END.finditer(text, 0, start)), default=0)
    right = CLAUSE_END.search(text, end)
    return text[left:start], text[end:right.start() if right else len(text)]


def just_before(before, n=4):
    """The last few words before a match in its part of the clause: "No time
    wasters, bank transfer" puts no "no" before "bank transfer", "No PayPal or
    bank transfer" does."""
    return " ".join(JOINS.split(before.split(",")[-1])[-1].split()[-n:])


def offered(pattern, text, warnings=True):
    """The matches of a pattern (a way to pay, cash, collection) the text
    offers: not one it says isn't so ("No PayPal or bank transfer", "bank
    transfer not accepted", "Bank transfer upon collection, not cash"), nor
    one in a warning about scams."""
    found = []
    for match in pattern.finditer(text):
        before, after = clause_around(text, match.start(), match.end())
        only = match.group().lower().endswith("only")  # "Collection only not posting": the "not" is the post's
        if NEGATED_BEFORE.search(just_before(before)) or (NOT_SO_AFTER.match(after) and not only) or \
                warnings and WARNING.search(before + after):
            continue
        found.append(match)
    return found


def says_no_cash(text):
    """Whether a listing's description rules out cash: it says so (NO_CASH),
    or it names another way to pay and offers no cash ("Bank transfer upon
    collection"). "Cash or bank transfer" takes cash, and "No PayPal or bank
    transfer" names no other way. The title is no part of it: a "SumUp card
    reader" names no way to pay."""
    if NO_CASH.search(text):
        return True
    paying_cash = [m for m in offered(CASH_TALK, text)
                   if not CASH_NOT_PAYING.search(text[max(0, m.start() - 20):m.end()])]
    ways = [m for m in offered(OTHER_PAYMENT, text) if not PAYMENT_FEATURE.match(text[m.end():])
            and not FEATURE_BEFORE.search(text[max(0, m.start() - 30):m.start()])]
    return bool(ways) and not paying_cash


def offers_collection(text):
    """Whether a listing offers collection ("Collection from Leeds LS6", "Collection
    or post"), and doesn't say it isn't so ("Collection in person not available")."""
    return bool(offered(COLLECTION_OFFERED, text, warnings=False))  # "Collection only due to scammers" offers it


def talks_of(pattern, message, title=""):
    """Whether a message talks of coming to the seller or of cash (COLLECT_TALK,
    CASH_TALK), asked or said. Not the item's own name, as the title has it
    ("the Pokemon Collection box", "the Johnny Cash LP"), a set of things
    ("the whole collection"), or the seller's rule said back ("I see it's no
    collection", "I know you don't take cash")."""
    named = {w.lower() for w in re.findall(r"[A-Za-z]+", title)}
    for found in pattern.finditer(message):
        word = found.group().split()[0].lower()
        before, _ = clause_around(message, found.start(), found.end())
        said_before = (before.split() or [""])[-1].lower()
        if word in named and (found.group()[:1].isupper() or SET_OF.search(before)
                              or f"{said_before} {word}" in title.lower()):
            continue  # the title's own words, as a name ("the ultra premium collection" too, in lower case)
        if word.startswith("collection") and SET_OF.search(before):
            continue  # "my record collection"
        if found.group()[:1].isupper() and re.search(r"\b[A-Z][a-z]+ $", message[:found.start()]):
            continue  # "Johnny Cash"
        if NEGATED_BEFORE.search(just_before(before, 3)):
            continue  # "no collection", "don't take cash": what isn't so offers nothing
        return True
    return False
# a sentence about other items, not this one: "cheaper alternatives often come with damage or visible wear"
OTHER_ITEMS = re.compile(r"\b(?:(?:cheaper|other|similar)\s+)?alternatives?\b|\bother (?:phones?|ones|listings?|sellers?|"
                         r"devices?|people)\b|\bcheaper ones\b|\bmost (?:phones|listings|sellers|people)\b|"
                         r"\bunlike (?:other|most|many|some)\b|\b(?:often|usually|normally|typically) comes? with\b|"
                         # the seller's other phone: "my previous iPhone had suffered water damage"
                         r"\bmy (?:previous|old|older|last|other|former|first|broken)\s+(?:\w+\s+)?(?:i?phones?|ones?|"
                         r"handsets?|devices?|mobiles?|models?)\b",
                         re.IGNORECASE)
# back to this item after other items in the same sentence: "...from my old phone, THIS ONE has a small crack"
THIS_ITEM = re.compile(r"^\W*(?:(?:but|and|however|though|whereas|while)\s+)?(?:this (?:one|phone|iphone|handset|item|"
                       r"console)|it|the (?:phone|iphone|screen|back|battery|case|frame|camera|body))\b", re.IGNORECASE)
# a conversation there hasn't been: the first message can't say "as you've said" or "as agreed" (it may
# point to the listing: "as you said in the listing")
PRIOR_TALK = re.compile(r"\b(?:as|like) (?:you(?:'ve| have)? (?:said|mentioned|agreed|offered|discussed|told me)|"
                        r"we (?:said|agreed|discussed))\b(?! (?:in|on) (?:the|your) (?:listing|ad|advert|post|"
                        r"description))|\bas (?:agreed|discussed|promised)\b", re.IGNORECASE)
# ending a listing: dealing outside eBay, but on Facebook just taking it down
ENDING = re.compile(r"end (?:the |your )?listing", re.IGNORECASE)
# a sentence asking without a question mark: "Are you about Saturday", "Hi is it still available"
QUESTION_START = re.compile(r"^(?:(?:hi|hello|hey|hiya|mate|there)[,!]?\s+)*(?:is|are|was|were|do|does|did|any|has|have|"
                            r"what|when|where|how|why)\b", re.IGNORECASE)
SAYS = {"collecting": "you'll come and collect", "cash": "you'll pay cash", "postage": "postage"}
NEW_CONDITIONS = {"1000", "1500"}  # New, Opened - never used: eBay ignores a condition note on these
UNSURE = "unsure"  # the AI may answer this for colour when the photo doesn't show it: then it's for you

# things a draft must not mention unless your inputs (title, description,
# notes, catalogue) do too. Each line is one thing; any of its words counts.
# If your notes mention it, only your notes count: your "no box" beats the
# seller's "boxed"
PROMISES = {
    "box": ["box", "boxed", "packaging"],
    "charger": ["charger", "adapter", "adaptor"],
    "cable": ["cable", "lead", "cord", "hdmi", "aux"],
    "case": ["case"],
    "controller": ["controller", "dualsense"],
    "dock": ["dock"],
    "stand": ["stand"],
    "headset": ["headset"],
    "pouch": ["pouch", "sleeve", "bag"],
    "game": ["game"],
    "screen protector": ["protector"],
    "accessories": ["accessory", "extras"],
    "ear tips": ["tips", "eartips"],
    "manual": ["manual", "instructions", "paperwork"],
    "receipt": ["receipt", "invoice"],
    "warranty": ["warranty", "guarantee", "guaranteed", "applecare"],
    "unlocked": ["unlocked", "simfree"],
}
# claims about the item's condition: only your own notes can back these,
# never the seller's old description
CONDITION_PROMISES = {
    "new": ["new", "bnib", "unused", "unopened"],
    "sealed": ["sealed"],
    "battery": ["battery"],
    "working": ["working", "works", "functional", "functioning"],
    "flawless": ["mint", "flawless", "perfect", "perfectly", "pristine", "immaculate", "spotless"],
    "excellent": ["excellent"],
    "scratch": ["scratch", "scratched"],
    "scuff": ["scuff", "scuffed"],
    "dent": ["dent", "dented"],
    "crack": ["crack", "cracked"],
    "chip": ["chip", "chipped"],
    "mark": ["mark", "marked", "marking", "wear", "worn"],
}
# each kind of mark is its own claim: "no dents" doesn't back "no scratches".
# "mark" is the general word: your "no marks" backs a draft's "no scratches"
MARKS = {"scratch", "scuff", "dent", "crack", "chip", "mark"}
# a draft's "excellent" is backed by your "excellent" or "flawless"; its
# "flawless" only by your "flawless"
LEVELS = {"excellent": ["excellent", "flawless"], "flawless": ["flawless"]}
# "chip" after one of these is the processor, not damage: "A15 Bionic chip"
PROCESSOR_WORDS = {"bionic", "pro", "fusion", "tensor", "exynos", "snapdragon", "gen", "processor", "silicon", "intel",
                   "amd", "m1", "m2", "m3", "m4", "kirin", "mediatek", "qualcomm"}
KEYWORDS = {word: promise for promise, keywords in {**PROMISES, **CONDITION_PROMISES}.items() for word in keywords}
# what people type is read with one slip allowed ("few scraches" is scratches), for
# claim words of 6 letters or more: shorter ones have too many real neighbours
SLIP_LENGTH = 6
# real words one slip from a claim word, read as themselves: "holds charge" has no
# charger, "making calls" no marks. Found by checking every word in macOS's dictionary
NOT_SLIPS = {"charge", "making", "scratchy", "crackled", "unblocked"}
# phrases rewritten before reading claims: same meaning, one way of writing it.
# Applied in this order, so longer phrases go first
SAME_AS = [
    ("perfect working order", "working"), ("full working order", "working"), ("good working order", "working"),
    ("works perfectly", "works"), ("working perfectly", "working"), ("perfectly working", "working"),
    ("fully working", "working"), ("fully functional", "working"),
    ("no faults", "working"), ("no fault", "working"), ("no issues", "working"), ("no problems", "working"),
    ("doesn t work", "not working"), ("does not work", "not working"), ("won t turn on", "not working"),
    ("stopped working", "not working"), ("faulty", "not working"),
    ("joy cons drift", "drift"), ("joy con drift", "drift"), ("joycons drift", "drift"), ("joycon drift", "drift"),
    ("controllers drift", "drift"), ("controller drift", "drift"), ("stick drift", "drift"), ("no drift", "working"),
    ("not locked", "unlocked"), ("isn t locked", "unlocked"), ("locked", "not unlocked"),
    ("out of warranty", "no warranty"), ("warranty has expired", "no warranty"),
    ("warranty expired", "no warranty"), ("warranty ended", "no warranty"),
    ("never used", "unused"), ("never opened", "unopened"),
    ("sim free", "simfree"), ("apple care", "applecare"), ("proof of purchase", "receipt"),
    ("like new", "mint"), ("as new", "mint"),
    ("joy cons", "controllers"), ("joy con", "controller"), ("joycons", "controllers"), ("joycon", "controller"),
    ("scratch free", "no scratch"), ("mark free", "no mark"), ("dent free", "no dent"),
    ("scuff free", "no scuff"), ("crack free", "no crack"), ("free from", "no"), ("free of", "no"),
]
# phrases that contain a claim word but aren't a claim
# why an offer over asking is made: so they'll hold it for you, or take the listing down. One vocabulary with the
# writer's (writer.HELD), in the ways people say it: "keep it till Saturday", "keep it back for me", "save me it",
# "hang onto it", "holding it" (26 Sep red team: "I'll do £210 if you can keep it back for me" read as giving no reason).
# Not a battery that holds its charge ("hold a good charge", "holding ok") or "how's it holding up", nor "hold on, is
# it unlocked?". Round 2 (26 Sep red team): nor asking whether it's held for someone already ("is it on hold?", "still
# available or reserved?", "has it been reserved?": a lower offer that asked it was refused), but "keep the phone for
# me" and "can you keep it?" ask for it
ASKED_IF_HELD = "".join(rf"(?<!\b{said} )" for said in ("or", "is", "are", "is it", "is this", "is that", "this one",
                                                         "been", "it's", "it’s", "its", "it is", "they", "not",
                                                         "already", "still"))
HOLD = re.compile(r"\b(?:(?<!\bon )hold(?:ing)?(?! (?:[\w']+ ){0,3}?charge\b| (?:its |a |the |it'?s |any |much )?"
                  r"(?:up|well|out)\b| (?:ok|okay|alright|fine)\b| on\b(?! ?to\b))|"
                  rf"reserv(?:e|ing)|{ASKED_IF_HELD}(?:reserved|on hold)|"
                  r"(?:put|pop|stick|keep|place) (?:it |them )?(?:aside|by|to one side|on hold)|set (?:it |them )?aside|"
                  r"(?:keep|keeping) (?:it|them|this|that)(?: one)? (?:for|till|til|until|back|aside|by|to one side)|"
                  r"(?:keep|keeping|save|saving) (?:the|this|that) \w+ (?:for (?:me|us)|till|til|until|back|aside)|"
                  r"(?:can|could|would|will|cud|wud) (?:you|u) (?:please |possibly |just )?keep (?:it|them)(?=\s*(?:[?.!,]|$))|"
                  r"keep hold of|(?:save|saving) (?:it|them|this|that|one)|(?:save|keep) (?:me|us) (?:it|them|one)|"
                  r"hang (?:on ?to|onto) (?:it|them)|mark (?:it |them )?(?:as )?(?:sold|reserved|pending)|"
                  r"take (?:it|the (?:ad|advert|listing|post)) down|off the market|end (?:the |your )?listing)\b",
                  re.IGNORECASE)
# for an offer at or over asking, nothing that calls it low: "I know it's a bit cheeky", "sorry it's under asking",
# nor an apology that compares it with what they want for it (26 Sep red team: "I know it's a bit less than you're
# after", "I appreciate it's lower than you wanted", "I know it's not quite what you're asking" went out on an offer of
# the asking price). The writer leaves these out at or over asking (flip.writer), and so does your style
# (flip.style.for_kind), with an emoji that only ever came with them ("Cheeky I know 😂"). Round 2 (26 Sep red team):
# "a bit under" said of the offer, where its clause ends or the price talk goes on ("a bit lower for cash?", "a bit
# under but...", "a bit under the asking"), not "a bit less hassle than posting" or "a little under 20 mins away";
# and "I know it's not much", not "...not much notice"
# at or over the asking price, any sentence that says the offer is less: "Hope a bit less is ok.", "A bit under list
# price I know.", "It's a little less than listed but cash is ready." (26 Sep final recheck: LOWBALL alone let these back
# on offers of the full price); not "in less than an hour" or "less hassle than posting": only about the price
UNDER_ASKING_TALK = re.compile(r"\b(?:a )?(?:bit|little|tad|touch|slightly) (?:less|lower|under|below|cheaper)\b"
                               r"(?!\s+(?:hassle|faff|work|effort|bother|stress|trouble|time|messing))|"
                               r"\b(?:less|lower|under|below|cheaper)\b[^.?!]{0,20}?\b(?:than )?(?:you(?:'re| are| r)? "
                               r"(?:after|asking|wanted|want)|what(?:'s| is| you| u)|the (?:asking|price|list(?:ed| price)?|ad|"
                               r"advert\w*)|(?:list(?:ed)?|asking|advertised)(?: price)?\b)", re.IGNORECASE)
LOWBALL = re.compile(r"\b(?:cheeky|cheek|lowball|low ball|low offer|lowest|sorry|(?:under|below) (?:the |your |ur )?asking|"
                     r"go lower|wiggle|cheap|bit low|too low|insult\w*|"
                     r"(?:a )?(?:bit|little|tad) (?:under|less|lower)(?=\s*(?:[^\w\s£]|$|(?:but|though|tho|for|if|on|i know|"
                     r"sorry|x{1,3})\b|(?:the |your |ur )?(?:asking|price)\b))|"
                     r"worth a (?:shot|try)|hope (?:that'?s|it'?s|this is) ok|"
                     r"i know (?:it'?s|that'?s|this is) (?:a (?:bit|little|tad) |slightly |quite a bit )?(?:less|lower|low|under|"
                     r"below)|i know (?:it'?s|that'?s|this is) not (?:much|a lot|loads)(?! (?:of )?(?:notice|time|warning)\b)|"
                     # ...against what they want for it: "less than you're after", "lower than your asking", "under
                     # what you wanted", "not quite what u r after", "not the full asking price"
                     r"(?:less|lower|cheaper)\b[^.?!]{0,20}?\bthan (?:you|u|your|ur|what|the (?:asking|price|listed)|asking)|"
                     r"(?:under|below) what (?:you|u)|"
                     r"not (?:quite |exactly |really )?what (?:you|u)(?:'?re| are| r|'?d| would)?\s*(?:after|asking|ask|"
                     r"want\w*|hoping|looking|like|expect\w*)|"
                     r"not (?:the |your |ur )?(?:full )?asking price|not (?:the |your |ur )?full (?:asking|price))\b",
                     re.IGNORECASE)
# a seller who isn't sure claims nothing, yes or no: "not sure if locked or not" leaves
# "is it unlocked?" open. Read on the part's words, so "don't" is "don t"
NOT_SURE = re.compile(r" (?:not sure|unsure|don t know|dont know|do not know|no idea|not certain|can t confirm|"
                    r"cannot confirm|can t say|unknown) ")
# a case or screen protector it was always kept in says how it was looked after, not that it comes
# with it: "Always had screen protector and phone case on it" leaves "does it come with the case?" open
LOOKED_AFTER = re.compile(r" (?:always (?:had|been|kept|used|in)|kept in|been in a|used with a) ")
HARMLESS = ["perfect for", "perfect gift", "new owner", "new home", "since new", "from new",
            "works with", "working with", "compatible with", "games console", "games consoles", "game console",
            "stand out", "stands out"]
# a claim word with one of these shortly before it, in the same part of the
# sentence, is a "no": "no box", "doesn't come with a charger", "can't find the box",
# "neither scratched nor dented"
NEGATIONS = {"no", "not", "without", "missing", "never", "none", "nor", "isn", "doesn", "don", "hasn", "wasn",
             "lost", "t", "neither",
             # typed without the apostrophe: "doesnt come with charger", "dont have the box"
             "isnt", "doesnt", "dont", "hasnt", "wasnt", "arent", "werent", "havent", "hadnt", "didnt", "cant", "wont",
             "aint"}
# a lone "t" is a "not" ("don t", "can t", and "doesn't" typed or mangled any way), but not in a carrier's name or a
# key's: "at t locked" (AT&T), "t mobile locked" (T Mobile) and "the t key sticks" deny nothing


def negation_at(words, n, negations=NEGATIONS):
    """Whether words[n] is a "no": one of the negations, but not the "t" of
    "at t" (AT&T), "t mobile" (T Mobile) or "the t key"."""
    word = words[n]
    before = words[n - 1] if n > 0 else ""
    named = word == "t" and (before == "at" or words[n + 1:n + 2] == ["mobile"] or
                             (words[n + 1:n + 2] in (["key"], ["keys"]) and before not in CONTRACTED))
    return word in negations and not named


# the first half of a "n't" whose apostrophe went missing: "aren t keys sticking" denies, "the t key sticks" doesn't
CONTRACTED = {"aren", "isn", "don", "doesn", "didn", "can", "won", "wasn", "weren", "hasn", "haven", "hadn", "couldn",
              "wouldn", "shouldn", "ain", "mustn", "needn"}


# ...unless it ends first (denied_by): an exception ("no marks APART from a scratch", "no cracks ONLY light
# scratches", "no marks BESIDES a small dent"), a thing of its own the "no" was about ("no OFFERS small crack", "no BOX just a scratch"), or a
# new statement ("no box, screen HAS a crack", "never repaired THERE'S a scratch", though not "doesn't HAVE any
# scratches")
NEGATION_ENDS = {"only", "just", "apart", "except", "bar", "other", "but", "though", "although", "however", "selling",
                 "sold", "aside", "besides", "excluding", "excepting", "beyond", "save", "barring", "minus"}
# ...and a "no" that denies an effect ends there (14 Oct): "doesn't AFFECT how it works", "no EFFECT on use"
NEGATION_ENDS |= {"affect", "affects", "affected", "affecting", "effect", "effects", "impact", "impacts", "impacting"}
# words a "no" can have before what it denies without denying anything of its own: "never BEEN repaired"
NEGATION_FILLER = {"t", "been", "ever", "even", "yet", "really", "any", "a", "an", "the", "it", "its", "was", "is", "be"}
NEW_STATEMENT = {"has", "have", "got", "is", "are", "was", "theres", "shows"}  # "never dropped, SHOWS signs of wear"
# ...but not after only a "think" or an "it": "I don't THINK there's any scratches", "Don't think IT shows any wear"
NOT_THEIR_OWN = {"think", "believe", "reckon", "sure", "guess", "feel", "see", "notice", "noticed", "know", "remember",
                 "seem", "seems", "appear", "appears", "it", "there", "this", "that", "honestly", "really", "even"}
NEGATED_THINGS = {"offers", "offer", "swaps", "swap", "returns", "refunds", "timewasters", "time", "box", "charger",
                  "cable", "plug", "case", "lowballers", "messers", "scams", "pets", "smoke", "smoking"}
# a label and its answer, as sellers list them: "Faults: none", "Scratches – no", "Any damage? Nope",
# "Dents: not that I know of", "Scratches ❌", "0 dents" (answered)
NO_ANSWER = r"(?:no|none|nope|nil|n/?a|zero|0|nothing|never|missing|not included|not that i(?:'?m| am)? (?:know|aware) of)"
ANSWERS = [
    (re.compile(rf"\b(?:any[ \t]+)?([a-z]+(?:[ \t]+(?:or|and|&)[ \t]+[a-z]+)?(?:[ \t]+[a-z]+)?)[ \t]*(?:[:=?]|[ \t][-–—])"
                rf"[ \t]*{NO_ANSWER}"
                r"\s*(?=[,.;!\n)]|$)", re.IGNORECASE), r"no \1"),
    (re.compile(r"\b([a-z]+)[ \t]*[❌✖✗]", re.IGNORECASE), r"no \1"),  # on its own line: "❌ Small crack" is a flaw
    (re.compile(r"(?<![\w.£$€])0\s+(?=[a-z])", re.IGNORECASE), "no "),
]
# what has a claim word but isn't a flaw or a claim: a guard against one, a part's name, a cover
# "doesn't affect how the phone works", "no effect on phone function": said of a mark, not a claim that it works
NO_EFFECT = re.compile(r"\b(?:no|not|t|nt|without)\s+(?:any\s+)?(?:affect|effect|impact)(?:s|ed|ing)?\b"
                       r"(?:\s+(?:on|how|the|its|it|s|phone|iphone|works?|working|functions?|functioning|functionality|use|"
                       r"usage|performance))*")
NOT_A_FLAW = re.compile(
    r"\b(?:scratch[- ]?resist\w*|scratch[- ]?proof|anti[- ]?scratch|(?:to )?prevent(?:s|ing)? (?:any )?(?:scratch\w*|damage)|"
    r"protect\w* (?:it )?(?:from|against) (?:any )?(?:scratch\w*|damage|drops?)|water damage indicators?(?: \w+)?|"
    r"accidental damage(?: cover| protection| insurance)?|damage (?:cover|protection|insurance)|"
    r"(?:intel|apple|amd|m[1-4](?: pro| max)?|a\d{1,2}(?: bionic| pro)?|bionic|snapdragon|exynos|tensor|kirin|"
    r"mediatek|qualcomm) chips?|snapdragon(?: \w+){1,3} chips?|(?:ultra[- ]?wideband|uwb|nfc|wireless|networking|"
    r"bluetooth|wi-?fi|neural|security|h[12]|u[12]|n[12]|w[123]|t2)(?: \w+){0,2} chips?|wear ?os|"
    r"(?:hardly|barely) (?:a|an|any) (?:\w+ )?(?:mark|scratch|scuff|dent|chip|sign|nick)\w*|"
    # a part you could have changed if you liked ("lens can be replaced if desired", "if u want"): no flaw. "Can
    # easily be replaced with a new battery" still is: no "if" makes it a choice
    r"(?:(?:can|could|may|might) (?:easily |always |also |just )?be |(?:can|could|happy to|willing to|able to) "
    r"(?:have|get) (?:the |it |them )?(?:(?!crack|scratch|dent|chip|scuff|broken|smash|damage|faulty)\w+ ){0,2}?)(?:replaced|"
    r"repaired|fixed|swapped|changed|removed)(?: or (?:replaced|repaired|fixed|swapped|changed|removed))?(?: [\w£$€]+){0,5}? "
    r"if (?:desired|wanted|needed|preferred|required|necessary|(?:you|u|ur)(?: d| would| so)?\b|you['’]?d)|"
    r"if (?:you|u) (?:want|like|prefer|wish|would like)\b,? (?:the |it )?(?:(?!crack|scratch|dent|chip|scuff|broken|smash|"
    r"damage|faulty)\w+ ){0,2}(?:can|could) (?:easily )?be "
    r"(?:replaced|repaired|fixed|swapped|changed)|"
    # a mark that's only in the photos: "the blacked out mark in the photo is photo edited", "the spot in the pic is a reflection"
    r"(?:blacked|blanked|blurred|scribbled|covered|greyed|grayed) out (?:\w+ )?(?:marks?|bits?|areas?|parts?|sections?|spots?)|"
    r"(?:marks?|spots?|lines?|dots?) (?:in|on) (?:the |this |my )?(?:photos?|pics?|pictures?|images?) (?:is|are) (?:a |just a |"
    r"just )?(?:reflections?|glare|light|photo[- ]?edit\w*|edited|dust)|"
    # a repair denied in a sentence of its own: "No parts have ever been replaced", "None of the parts have been
    # replaced", "Nothing's been repaired" ("no scratches has been dented" still has its dent)
    r"(?:no|none(?: of (?:it|them|the))?|not a single|not one|no original|no other)(?: [\w-]+){0,4}? (?:has|have|had) "
    r"(?:ever )?been "
    r"(?:replaced|repaired|changed|swapped|opened|fixed)|nothing(?:['’]?s| has| have)?(?: on it| on the phone)?"
    r"(?: has| have)? (?:ever )?been (?:replaced|repaired|changed|swapped|opened|fixed)|there (?:are|is|were|was) no "
    r"(?:[\w-]+ ){1,3}(?:that|which) (?:have|has|had) (?:ever )?been (?:replaced|repaired|changed|swapped))\b",
    re.IGNORECASE)


def denied_by(lead, negations=NEGATIONS):
    """Whether the words leading up to a claim word deny it: a negation word
    among them that nothing ends first (NEGATION_ENDS, NEGATED_THINGS, or a
    verb with a word of its own before it: NEW_STATEMENT). "doesn t have any"
    denies; "no box screen has small" and "no cracks only light" don't, and
    nor does the "t" of "at t locked" (negation_at)."""
    for n in range(len(lead)):
        if not negation_at(lead, n, negations):
            continue
        rest = lead[n + 1:]
        ends = set(rest) & (NEGATION_ENDS | NEGATED_THINGS)
        # a thing a "no" covers on its own ends it, unless the list goes on: "no charger OR box" (14 Oct)
        ends -= {w for w, after in zip(rest, rest[1:]) if w in NEGATED_THINGS and after in ("or", "nor")}
        if "other" in ends and not any(w == "other" and after in ("than", "then") for w, after in zip(rest, rest[1:])):
            ends.discard("other")  # "no OTHER marks" denies more of them; "no marks OTHER THAN a scratch" excepts one
        ended = ends or any(verb in NEW_STATEMENT and set(rest[:k]) - {"t"} - NOT_THEIR_OWN for k, verb in enumerate(rest))
        # ...or by not turning on or working, in a run-on: "wont turn on screen cracked" ("won't turn on" is "not
        # working" by now: SAME_AS) says the screen is cracked (26 Sep)
        ended = ended or bool(re.match(r"(?:t )?(?:(?:turn|switch|power|boot|come|start)s? (?:on|up)|work(?:s|ing)?) \S",
                                       " ".join(rest)))
        # ...or at the next "and" when what it denies is no claim of its own, a verb: "never REPAIRED and fully
        # working", "not been DROPPED and in great condition" (14 Oct). A claim word before the "and" keeps it going:
        # "no scratches and dents", "doesn't have a charger and box"
        if not ended and "and" in rest:
            before = [w for w in rest[:rest.index("and")] if w not in NEGATION_FILLER]
            ended = bool(before) and not any(KEYWORDS.get(singular(w)) for w in before)
        if not ended:
            return True
    return False


def answered(text):
    """A listing's labels with their answers turned into plain words: "Faults:
    none" -> "no Faults", "Any damage? Nope" -> "no damage", "Scratches ❌" ->
    "no Scratches", "0 dents" -> "no dents"."""
    for pattern, plain in ANSWERS:
        text = pattern.sub(plain, text)
    return text
# ...and so is one of these shortly after it: "charger MISSING", "box LOST"
NEGATED_AFTER = {"missing", "lost", "none", "excluded"}
# ...or "not" and one of these: "charger NOT INCLUDED"
INCLUDED = {"included", "supplied", "provided", "present"}
# words that join a list a "no" after it covers: "box AND charger not included"
LIST_WORDS = {"and", "or", "nor", "the", "original", "its", "a"}
# where a mark can be, one name each ("display" and "front" are the screen). A draft may say
# where a mark is only where your notes do: "few scratches" isn't "on the screen"
PLACES = {"screen": "screen", "display": "screen", "front": "screen", "back": "back", "rear": "back",
          "side": "side", "frame": "frame", "edge": "edge", "corner": "corner",
          "camera": "camera", "lens": "camera", "bezel": "bezel", "housing": "housing", "case": "case",
          "box": "box", "controller": "controller", "headband": "headband", "cushion": "cushion", "pad": "cushion",
          "stem": "stem", "port": "port", "button": "button"}
# "scratches on the screen, BACK AND SIDES": a part of only these goes on with the marks before it
PLACE_LIST_WORDS = LIST_WORDS | {"on", "of", "in", "at", "to", "around", "both", "all"}
# a draft's place counts as a mark's when it's this many words from the mark or fewer:
# "the screen is in great condition with a light scratch on the back" puts it on the back only
MARK_REACH = 5
# "new" right before one of these is about a part, not the item: "new battery fitted"
PARTS = {"battery", "screen", "display", "glass", "back", "housing", "camera", "lens", "port", "speaker",
         "speakers", "case", "charger", "cable", "strap", "pads", "cushions", "tips", "box", "protector",
         "controller", "controllers", "dock", "stand", "fan", "ssd", "drive", "seal", "seals", "sim",
         "firmware", "software", "update", "buttons", "button", "sound", "headband"}
# a condition word next to one of these is about that part only: "screen perfect"
CONDITION_PARTS = {"screen", "display", "glass", "back", "housing", "camera", "lens", "speaker", "speakers",
                   "sound", "buttons", "battery", "case", "box", "controller", "controllers", "pads",
                   "cushions", "headband"}
# a condition word right before one of these describes the model, not this
# one: "excellent noise cancelling"
FEATURES = {"noise", "cancelling", "canceling", "anc", "bass", "graphics", "performance", "value"}
# New (1000) needs your notes to say one of these, with no sign of use or opening.
# Opened - never used (1500) needs "never used" or "unused" (or one of these)
NEW_SEALED = re.compile(r"\b(?:brand new|bnib|bnwt|new in box|new sealed|still sealed|factory sealed|sealed|"
                        r"unopened|never opened)\b")
UNUSED = re.compile(r"\bnever (?:been )?used\b|\bunused\b")
USED_SIGNS = re.compile(r"\b(?:used|worn|refurbished|refurb|new condition|bought new|bought brand new|"
                        r"like new|as new|basically new|basically brand new)\b")
OPENED_SIGNS = re.compile(r"\b(?:opened|open box|box open|seal broken|unsealed)\b")
# new, unused, unopened or sealed said of what comes with it isn't the item's own condition (14 Oct: "two unused phone
# cases" and "unopened pack of two tempered screen protectors" made a used iPhone 11 New). Not across a comma: "sealed,
# comes with a charger" is still sealed. The box isn't one of these: "unopened box" is the item unopened
ACCESSORY = (r"(?:cases?|covers?|protectors?|guards?|tempered|chargers?|cables?|leads?|plugs?|earphones|earpods|"
             r"headphones|adapters?|accessories|packs?|packets?|straps?|stands?|sims?)")
NEW_WORD = r"(?:brand new|new|unused|unopened|sealed|never (?:been )?(?:used|opened))"
ITS_THINGS_NEW = re.compile(rf"\b{NEW_WORD}(?: [a-z0-9]+){{0,3}}? {ACCESSORY}\b|\b{ACCESSORY}(?: [a-z0-9]+){{0,2}}? {NEW_WORD}\b")
NEW_PROBLEMS = {"1000": "condition is New, but your notes don't say it's brand new and unopened",
                "1500": "condition is Opened - never used, but your notes don't say it's unused"}
# a fault in your notes means the item is "For parts or not working", and no
# draft may call it fully working. "No faults", "no drift" aren't faults
# what a part does when it works, for "doesn't FOCUS", "won't READ discs", "not RESPONDING". Not
# "not connected to iCloud", "not played much", "not ready", "not unlocked": those aren't faults
JOBS = (r"(?:focus\w*|work|works|charge|charges|charging|turn on|turning on|switch on|power on|connect|connects|"
        r"connecting|pair|pairs|pairing|boot|boots|booting|load|loads|loading|respond\w*|register|registers|"
        r"registering|detect|detects|detecting|recogni[sz]e|recogni[sz]es|recogni[sz]ing|read|reads|reading|"
        r"ring|rings|ringing|vibrate|vibrates|vibrating|play|plays|playing|click|clicks|clicking|"
        r"hold (?:a |its )?charge|holding (?:a |its )?charge)")
NOT_DOING = rf"(?:always |properly |really |even |sometimes |fully |seem to |seems to )?{JOBS}"
# a part that worked and doesn't now: "it would no longer turn on". Not every job: "I no longer play it" isn't a fault
NO_LONGER = (r"no longer (?:turns? on|turning on|comes? on|coming on|switch(?:es)? on|powers? (?:on|up)|boots?(?: up)?|"
             r"starts? up|lights? up|holds? (?:a |its )?charge|holding (?:a |its )?charge)|"
             r"(?<!\bi )(?<!\bi m )(?<!\bi['’]m )(?<!\bim )(?<!\bwe )(?<!\bwill )no longer (?:works?|working|charges?|"
             r"charging|responds?|functions?)(?! (?:for|from|in|at|away|as|with|to|after|on|since|because|there|here)\b)")
FAULTS = re.compile(r"\b(?:not working|broken|drift|drifts|drifting|faulty|fault|faults|glitch\w*|for parts|spares|"
                    r"spare parts|(?:parts|spares) or repairs?|for repairs?|(?:ideal|perfect|good|great) for (?:someone|anyone|a) "
                    r"(?:looking to |wanting to |who can |who wants to )?(?:repair|fix)|"
                    r"dead pixels?|(?:is|totally|completely|went|now) dead|dead (?:battery|phone|console|unit|on arrival)|"
                    r"battery (?:is )?dead|"
                    r"won t (?:turn on|switch on|charge|connect|pair|boot)|doesn t (?:turn on|charge|connect|pair)|"
                    r"not charging|no sound|no power|"
                    # a part with an issue, and a fault that comes and goes: "one issue with the screen it
                    # turns on and off sometimes", "keeps restarting", "cuts out" (but not "issues with collection")
                    rf"{NO_LONGER}|"
                    r"(?:issues?|problems?|faults?) with (?:the |its |my )?(?:screen|display|battery|charging|charger port|"
                    r"camera|cameras|speakers?|mic|microphone|buttons?|face id|touch id|wifi|bluetooth|signal|sound|audio|"
                    r"power|port|sim|network|touch ?screen|keyboard|trackpad|joycons?|sticks?|controllers?|disc drive)|"
                    r"turns? (?:itself )?(?:on and off|off and on|off by itself|off on its own|off randomly)|"
                    r"turning (?:on and off|off and on|itself off)|"
                    r"(?:switch|switches|shuts?) (?:itself )?(?:off|down) (?:by itself|on its own|randomly)|"
                    r"keeps? (?:turning|switching|shutting) (?:off|down)|keeps? restarting|restarts? (?:by itself|on its own|randomly)|"
                    r"randomly (?:restarts|shuts down|turns off|switches off)|cuts? out|intermittent\w*|stops? working|"
                    # a part that doesn't do its job: "sometimes it does not focus", "won't read discs"
                    rf"(?:does not|doesn t|doesnt|do not|don t|dont|did not|didn t|didnt|will not|won t|wont|can not|"
                    rf"cannot|can t|cant|isn t|isnt|is not|not|never) {NOT_DOING})\b")
NOT_A_FAULT = re.compile(r"\b(?:no|not|never|without|zero|(?:hasn|haven|hadn|didn|doesn|isn|wasn) t)\s+(?:been\s+)?(?:\w+\s+){0,3}"
                         r"(?:broken|drift\w*|faults?|faulty|glitch\w*|dead pixels?|issues?|problems?)\b"
                         r"|\bnot\s+(?:for\s+)?(?:spares|repairs|parts)\b")
FOR_PARTS = "7000"
PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s?(?:%|per ?cent\b)", re.IGNORECASE)
# "battery" typed any way is TYPED_BATTERY (flip.numbers). And "bh", but only on its
# own: "bh 88%" is battery health, "collection from BH21" a postcode
BH = re.compile(r"\bbh\b")

NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
# number words count as numbers. Not "one": "this one", "one of the best"
NUMBER_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30,
                "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
                "hundred": 100}

AMOUNT = r"(\d[\d,]*(?:\.\d{2})?)"
# a number that counts something isn't a price: "do 2 CONTROLLERS come with it", "take 2 MORE photos"
COUNTED = (r"(?!\s?(?:gb|tb|%|x\b|more\b|controllers?|pads?|games?|photos?|pics?|pictures?|items?|days?|weeks?|"
           r"months?|years?|hours?|mins?|minutes?|of\b))")
# words that put a price on the table: "take 170", "stretch to 200", "let it go for 170", "£170, or 200"
OFFER_WORDS = (r"let it go for|go for|stretch to|stretch|go up to|go to|up to|settle for|settle on|meet you at|"
               r"meet at|accept|consider|take|do|offer|pay|or|max")
PRICES = [re.compile(r"£\s?" + AMOUNT),
          re.compile(AMOUNT + r"\s?(?:quid|pounds|gbp)\b", re.IGNORECASE),
          re.compile(r"\b(?:" + OFFER_WORDS + r")\s+" + AMOUNT + r"\b" + COUNTED, re.IGNORECASE),
          re.compile(r"£\s?\d[\d,]*(?:\.\d{2})?\s?(?:-|–|to)\s?£?\s?" + AMOUNT + r"\b" + COUNTED, re.IGNORECASE)]
# the asking price may come up, but only as a reference: "I know it's listed at £200",
# "the asking price is £200", "I see it's £200 ono". "Happy to pay the asking £200" is an offer
ASKING_MENTION = re.compile(
    r"\b(?:listed (?:at|for)|asking price (?:is|of)|you(?:'re| are) asking)\s+£?\s?(?P<a>\d[\d,]*(?:\.\d{2})?)"
    r"|\b(?:it'?s|it is|price is|priced at)\s+£\s?(?P<b>\d[\d,]*(?:\.\d{2})?)"
    r"|£\s?(?P<c>\d[\d,]*(?:\.\d{2})?)\s+(?:on the listing|ono|or nearest offer)\b", re.IGNORECASE)
# ...unless one of these comes just before it: "I'd PAY the asking price of £200"
OFFER_VERBS = {"pay", "paying", "offer", "offering", "give", "do", "take", "go", "accept", "happy", "could", "would",
               "can", "will", "i'd", "id"}
# a price in a listing, in words: "Paid 300 at Currys", "RRP 349", "was GBP 120"
LISTING_PRICE = re.compile(r"\b(?:paid|rrp|retail|retails|retailed|cost|costs|bought (?:it )?for|worth|valued at|was)"
                           r"\s+(?:at\s+)?(?:£|gbp\s?)?\s?\d[\d,]*(?:\.\d{2})?\b" + COUNTED + r"|\bgbp\s?\d", re.IGNORECASE)
# paying or dealing outside the platform: no buyer protection, and against eBay's rules
OFF_PLATFORM = re.compile(r"\b(?:outside (?:of )?(?:ebay|vinted|the app|the site|the platform)|off (?:the )?(?:ebay|vinted|"
                          r"app|site|platform)|(?:save|avoid|skip|dodge|without) (?:the |on |paying )?(?:the )?(?:fees?|"
                          r"buyer protection)|end (?:the |your )?listing|friends (?:and|&) family|bacs|"
                          r"f ?& ?f|bank transfer|direct transfer|pay(?:ment)? by transfer|revolut|monzo|crypto|"
                          r"bitcoin|western union|gift cards?|"
                          # ending an auction early to sell outside it
                          r"end (?:it|the auction|your auction|the listing|your listing) (?:early|now)|"
                          r"ending (?:it|the auction|your auction|the listing|your listing)(?: early| now)?|"
                          r"transfer (?:you )?the money|pay ?pal(?:ing)? (?:you|it|the money|over)|"
                          r"(?:pay|paying|payment|send it) (?:by|via|through|with|on|over) (?:pay ?pal|my bank(?:ing app)?|"
                          r"banking app|bank app|bank)|banking app|bank app)\b", re.IGNORECASE)

LINK = re.compile(r"https?://|www\.|\b[\w-]+\.(?:com|co\.uk|uk|net|org|io)\b"
                  r"|\b[\w-]+\.(?:ly|gl|me|link|to|app|page|co)/\S*", re.IGNORECASE)  # short links: "bit.ly/..."
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.\w+")
HANDLE = re.compile(r"(?<![\w.])@\w{3,}")
CONTACT_WORDS = re.compile(
    r"\b(?:whats ?app|snapchat|telegram|gmail|hotmail|outlook|yahoo)\b"
    r"|\bdot (?:com|co|uk|net)\b"
    r"|\b(?:snap|sc|ig|fb|wa|tiktok|discord|kik)\s*(?::|@|me\b)"  # "Snap: name", "WA me"
    r"|\bmy (?:snap(?:chat)?|sc|ig|insta(?:gram)?|fb|facebook|tiktok|discord|kik|number|mobile|email)\b"  # "my snap is"
    r"|\b(?:message|msg|text|dm|add|contact|find|reach|follow|hit)\s+(?:me\s+)?(?:up\s+)?(?:on|via|at)\s+"  # "add me on"
    r"(?:snap(?:chat)?|ig|insta(?:gram)?|fb|facebook|messenger|tiktok|discord|kik|whats ?app|telegram|signal)\b",
    re.IGNORECASE)
# checked with the spaces, dashes and brackets between digits removed
PHONE = re.compile(r"(?:\+|00)44\d{9,11}|\b0[1-37]\d{8,9}\b")  # UK mobiles and landlines
LONG_NUMBER = re.compile(r"\b\d{10,}\b")  # 10+ digits in a row: a phone number or an IMEI
# a story about you that only you could know: who it's for, why you want it,
# where you are, that you don't resell. Read on words(), so "I'm" is "i m" and
# "it's" is "it". It catches the common shapes, not every story: a place name
# ("I'm in Leeds") gets through, one more reason you approve every draft
PEOPLE = (r"son|sons|daughter|daughters|wife|husband|hubby|partner|missus|girlfriend|boyfriend|fiance|fiancee|"
          r"kids?|children|child|boy|girl|lad|lads|brother|sister|mum|mam|mom|dad|nan|nana|gran|granny|grandma|"
          r"grandad|grandson|granddaughter|nephew|niece|cousin|auntie|aunt|uncle|eldest|youngest|little one|"
          r"other half|family")
STORY = re.compile(
    r"\bfor (?:my|our)(?: \w+){0,2} (?:" + PEOPLE + r")\b|\bfor (?:my|our) (?:best |good )?(?:mate|friend|pal)s?\b"
    r"|\bfor the (?:missus|wife|kids|little one|other half|family)\b"
    r"|\b(?:my|our) (?:\w+ )?(?:" + PEOPLE + r"|mate|friend|pal) (?:has |is |s )?(?:been )?(?:asking|wanting|after)\b"
    r"|\b(?:my|our|his|her) (?:\w+ ){0,2}(?:birthday|bday|anniversary)\b"
    r"|\b(?:birthday|christmas|xmas|anniversary|wedding|graduation) (?:present|gift|pressie)\b"
    r"|\bas a (?:present|gift)\b|\b(?:present|gift) for (?:her|him|my|our|the)\b"
    r"|\bfor (?:christmas|xmas|uni|university|college|school|work)\b"
    r"|\b(?:been|was|am|m) (?:looking|searching) for (?:one|this)\b"
    r"|\b(?:been|was|am|m|ve) (?:looking|searching|after|wanting|wanted|hunting)(?: \w+){0,6} "
    r"(?:ages|a while|weeks|months|years)\b"
    r"|\bmine (?:\w+ )?(?:broke|broken|died|was stolen|got stolen|got nicked|was nicked|stopped working)\b"
    # "my old PS5 Slim broke", but never "my OFFER as it stopped working"
    r"|\bmy (?:old |last |current )?(?:(?!(?:offer|price|bid|best|final|as|it|that|this|the|a|and|but|so|for|with|"
    r"given)\b)\w+ ){1,4}(?:s |is |was |has |got |just |has just )?"
    r"(?:broke|broken|died|nicked|stolen|stopped working|packed in|packed up)\b"
    r"|\b(?:i m|i am|im|we re|we are)(?: only| just| literally| really)? (?:local|nearby|close by|near you|"
    r"close to you|(?:a)?round the corner|up the road|down the road|in the area|not far (?:from you|away)|"
    r"based (?:in|near|locally)|\d+ (?:mins?|minutes?) (?:away|from you))\b"
    r"|\bi (?:live|work)(?: \w+){0,2} (?:locally|nearby|near|close|round|around|in|down|up)\b"
    r"|\bnot (?:a )?(?:reseller|dealer|trader|flipper)\b|\bnot (?:for |to )?(?:resell|reselling|resale|flip|flipping)\b"
    r"|\b(?:personal|own) use\b|\bfor myself\b|\b(?:it|this) (?:is )?(?:just |only |purely )for me\b"
    r"|\bmoney (?:is |s )?tight\b|\bon a (?:tight )?budget\b|\b(?:i m|i am) (?:a )?(?:student|skint|broke)\b"
    r"|\bi (?:really )?need (?:it|one|this) for\b|\b(?:i m|i am|we re|we are) moving\b")
# a message's sentences cut into clauses: "Would you take £170, AS the back is
# cracked?" asks one thing and states another
# what's wrong without a mark or a fault, in a seller's listing: a part the iPhone can't verify ("Unable to verify
# this iPhone has a genuine Apple battery", "camera unknown", "non-Apple battery"), eSIM only (a US model), no more
# iOS updates ("runs up to iOS 15"), untested. A kind of flaw of its own (flip.offers.condition_said: "issue"), so a
# message can't call an untested phone faulty. Read in a seller's text only, never your notes
ESIM_ONLY = (r"e[- ]?sim[- ]only|(?:only|just) (?:(?:has|takes|uses?|supports?|works (?:with|on)|accepts?|an?|one|with) )*"
             r"e[- ]?sims?|uses only an? e[- ]?sim|no physical sim(?! card)|"
             r"no sim (?:card )?(?:tray|slot)(?! (?:tool|ejector|pin|remover|key|opener|issues?|problems?|damage|faults?))|"
             r"(?:doesn['’ ]?t|does not|won['’ ]?t|will not|can['’ ]?t|cannot) (?:have|fit) (?:a |an |any )?(?:physical sim|"
             r"sim (?:card )?(?:tray|slot))|(?:doesn['’ ]?t|does not|won['’ ]?t|will not|can['’ ]?t|cannot) "
             r"(?:take|use|support|accept) (?:a |an |any )?(?:physical )?sim(?: cards?)?|physical sim (?:is )?not supported")
# a battery that's been replaced, by Apple or anyone ("Battery changed 4 months ago", "New battery", "replacement
# battery"): a rule set on 23 Sep, a flaw whoever did it. Not "original battery", "battery like new", nor one it
# still needs, said before it ("Needs a new battery", "Could do with a new battery", "due a new battery") or after it
# ("Battery replacement needed"): 26 Sep, each was said "the battery has been replaced". That's a weak one (BATTERY_WEAK)
# "Due" is a need only when it isn't "due to", which says why one was fitted: "Had a new battery due to the old one
# swelling" is replaced, and so is one the seller needed and then had ("Needed new battery so got it done", "Was due a
# new battery so had one fitted"): the fourth red team, 26 Sep (each was read as one it needs)
NEEDED_BEFORE = "".join(rf"(?<!{need} )" for need in (
    "need", "needs", "needing", "need a", "needs a", "needing a", "need a brand", "needs a brand", "do with a",
    "do with", "could use a", "need of a", "require", "requires", "require a", "requires a", "due", "due a", "due for a",
    "ready for a", "time for a", "never had a", "never had"))
NEEDED_AFTER = r"(?!\s+(?:is\s+|will\s+be\s+|would\s+be\s+|may\s+be\s+|might\s+be\s+)?(?:needed|required|due(?!\s+to\b)|" \
               r"recommended))"
HAD_AFTER_NEED = (rf"{TYPED_BATTERY}s?\b[^.?!]{{0,20}}?\bso (?:i |we )?(?:had|got) (?:(?:a new )?one (?:fitted|done|put in|"
                  r"installed|replaced)|it (?:done|replaced|changed|swapped|fitted))\b")  # "...battery so had one fitted"
BATTERY_REPLACED = (rf"{NEEDED_BEFORE}(?:new|replacement|replaced|changed|swapped|fresh) {TYPED_BATTERY}s?\b{NEEDED_AFTER}|"
                    rf"{NEEDED_BEFORE}{TYPED_BATTERY}s? (?:replacement\b{NEEDED_AFTER}|(?:(?:was|were|is|has|have|had|been|"
                    rf"just|recently|got|being|already) ){{0,3}}(?:replaced|changed|swapped|renewed|(?:brand )?new)\b)|"
                    rf"replaced (?:[\w-]+ ){{0,4}}with an? (?:[\w-]+ ){{0,2}}{TYPED_BATTERY}|{HAD_AFTER_NEED}")
# what the iPhone itself reports about a part ("Unable to verify this iPhone has a genuine Apple battery", "camera
# unknown", "important battery message"), or a part that isn't Apple's ("non-Apple screen", "aftermarket screen")
PART_NOT_APPLES = (r"unable to verify (?:this iphone has a genuine apple (?:battery|display|screen|camera|part)|(?:the |its |if the "
                   r"|that the )?(?:battery|display|screen|camera|parts?))|(?:couldn['’ ]?t|could not|can['’ ]?t|cannot|can not) "
                   r"(?:be )?verif(?:y|ied) (?:the |its |as |that the |if the )?(?:battery|display|screen|camera|parts?)|"
                   r"important (?:battery|display|screen|camera|parts?) message|"
                   r"unknown (?:part|parts|battery|screen|display|camera)(?! cycles?| cycle count| health| capacity| age)|"
                   r"(?:battery|screen|display|camera|parts?)(?: (?:as|is|shows?|showing|comes? up as|says|listed as|part|"
                   r"parts|displays?|now))* (?:an? )?unknown(?! colou?r)|(?:non[- ]?(?:apple|genuine|original|oem)|aftermarket|after-market|"
                   r"third[- ]party|not (?:an? )?(?:genuine|original))(?: apple)? (?:battery|screen|display|lcd|oled|camera|"
                   r"back glass|glass|housing|parts?)|(?:battery|screen|display|camera|back glass|parts?) (?:is |are )?"
                   r"(?:non[- ]?(?:genuine|original|apple)|not (?:genuine|original)|aftermarket|third[- ]party)|soft[- ]?oled|"
                   r"in-?cell|(?:screen|display) (?:has |have )?(?:been |was |were )?(?:changed|replaced|swapped)(?: (?:with|to|"
                   r"for) [\w-]+)?|(?:brand )?new (?:screen|display|lcd|oled) (?:installed|fitted|put in)")
# untested, in so many ways: "Not fully tested", "Unable to test as I don't have a charger", "Can't confirm it charges"
# (not "can't confirm collection times": what can't be confirmed is the phone working)
UNTESTED = (r"un[- ]?tested|not (?:been |fully |properly )?tested|(?:haven|hasn)['’ ]?t (?:been |fully |properly )?tested|"
            r"(?:unable|not able|not been able) to (?:fully |properly )?test|(?:can['’ ]?t|cannot|can not|couldn['’ ]?t|"
            r"could not) (?:fully |properly )?test|haven['’ ]?t had (?:a |the )?chance to test|(?:can['’ ]?t|cannot|can not|"
            r"couldn['’ ]?t|could not|unable to|not able to) (?:be )?confirm(?:ed)?(?: (?:if|whether|that))?(?: (?:it|the "
            r"phone|this|the \w+))? (?:\w+ )?(?:works?|working|charges?|charging|turns? on|powers? on|boots?|functions?|"
            r"holds? (?:a )?charge)|(?:don['’ ]?t|do not|dont) know (?:if|whether|weather) (?:it|they|this|the \w+) (?:still )?"
            r"(?:works?|is working|are working|turns? on|charges?)|not sure if (?:it['’ ]?s |it is |its )?(?:still )?(?:working|"
            r"works|it works)(?: anymore| any more)?")
# no more updates: "Runs up to iOS 15", "can't update past iOS 16", "(the last version for this model)". Not
# "updated it up to iOS 26" or "supports up to iOS 26": those are the latest
IOS_LIMIT = (r"(?:runs?|running|goes|go|works?|only(?: (?:runs?|goes|works?))?) up ?to i ?os ?\d+|up ?to i ?os ?\d+ "
             r"(?:only|max(?:imum)?)\b|max(?:imum)? i ?os ?\d+|(?:can['’ ]?t|cannot|can not|won['’ ]?t|will not|doesn['’ ]?t|"
             r"does not) (?:be )?(?:update[ds]?|upgrade[ds]?|go) (?:past|beyond|above|higher than|further than) i ?os ?\d+|"
             r"(?:can )?only (?:be )?(?:update[ds]?|upgrade[ds]?|go) (?:up )?to i ?os ?\d+|(?:the )?last (?:i ?os |software )?"
             r"(?:version|update) (?:for|available for|supported on|on) (?:this|the|that|it)|no longer (?:gets?|getting|"
             r"receives?|receiving) (?:i ?os |software )?updates|no longer (?:supported|updated)|i ?os ?(?:[1-9]|1[0-5])(?:\.\d+)*(?![.\d])(?!\s*(?:in\b|inch|\x22|\u201d))")
# dust inside, where no cloth can reach: "the front camera needs cleaning, as dust has gotten inside"
DUST = (r"dust (?:has |have |had |is |s )?(?:(?:got|gotten|gone|come|crept|trapped|stuck) )?(?:inside|into|"
        r"in (?:the |its )?(?:camera|lens|screen|phone)|under (?:the )?(?:screen|glass|lens)|"
        r"behind (?:the )?(?:lens|glass|screen|camera))|(?:camera|cameras|lens|lenses) needs? (?:a )?clean\w*")
# a battery that's weak, said without a figure: "battery low", "struggles to hold charge", "may need a replacement",
# "probably won't last as long" (not "battery lasts all day")
BATTERY_WEAK = (r"(?:battery|batt) (?:is |s )?(?:very |quite |a bit |really |pretty )?low\b(?! (?:in|on) (?:the )?(?:photos?|"
                r"pics?|pictures?))|struggl\w* (?:to )?(?:hold|keep)(?:ing)? (?:a |its |the )?charge|takes? (?:a )?(?:long|while)"
                r"(?: time)? to charge|slow to charge|charges? (?:very |really |quite )?slow(?:ly)?|(?:may|might|will|would) need "
                r"(?:a )?(?:new battery|battery replacement|replac\w*)|could do with (?:a )?(?:servic\w*|replac\w*|new battery|"
                r"repair\w*)|(?:won['’ ]?t|doesn['’ ]?t|does not|will not|wouldn['’ ]?t) last (?:as long|long|all day|a full day)|"
                r"battery (?:isn['’ ]?t|is not|s not) (?:as )?(?:great|good)|"
                # ...or one it needs, which BATTERY_REPLACED read as replaced until 26 Sep: "Needs a new battery", "Due a
                # new battery", "Battery replacement needed"
                rf"(?:needs?|needing|requires?|in need of|due(?: for)?|could use) (?:a )?(?:brand )?(?:new|replacement) "
                rf"{TYPED_BATTERY}s?\b|(?:needs?|needing|requires?|in need of|due(?: for)?) (?:a )?{TYPED_BATTERY} "
                rf"(?:replacement|change|swap)\b|(?:(?:new|replacement) )?{TYPED_BATTERY}s? (?:replacement )?(?:is |will be )?"
                r"(?:needed|required|due(?!\s+to\b)|recommended)\b")  # not "new battery due to the old one swelling"
# each a kind of flaw of its own (flip.offers.condition_said: "issue: esim"...), so a message names only the listing's
ISSUE_KINDS = {"esim": ESIM_ONLY, "battery replaced": BATTERY_REPLACED, "battery weak": BATTERY_WEAK,
               "part": PART_NOT_APPLES, "untested": UNTESTED, "ios": IOS_LIMIT, "dust": DUST}
ISSUE_WORDS = "|".join(ISSUE_KINDS.values())
ISSUES = re.compile(rf"\b(?:{ISSUE_WORDS})\b", re.IGNORECASE)
ESIM = re.compile(rf"\b(?:{ESIM_ONLY})\b", re.IGNORECASE)
# faults a seller writes their way: read in a listing (flip.offers.SELLER_FAULTS), never your notes
SELLER_FAULT_WORDS = (r"(?:face ?id|touch ?id) (?:is |has been |s )?(?:disabled|unavailable|not available|deactivated)|"
                      r"(?:loud ?speaker|speakers?|earpiece|mic|microphone) (?:is |are |sounds? )?(?:very |quite |a bit |really |"
                      r"pretty )?(?:low|quiet|muffled|crackly|distorted|faint)\b|(?:speaker|port|mic|microphone|camera|lens)(?: \w+){0,3} "
                      r"(?:could do with|needs?) (?:a )?(?:good )?clean|"
                      r"only (?:charges?|charging)(?: (?:via|with|on|using|by))?(?: an?| the)? (?:wireless\w*|magsafe)|"
                      r"(?:charges?|charging) (?:wireless(?:ly)?|(?:via|with|on|using) (?:an? |the )?(?:wireless|magsafe)\w*) "
                      r"only|wireless charging only|(?:will|can|would) only charge (?:on|with|via|using|by) (?:an? |the )?"
                      r"(?:wireless|magsafe)\w*|"
                      # a blank screen or camera ("Screen has gone blank"), never "my mind went blank"
                      r"(?:screen|display|cameras?)(?: (?:is|are|has|have|goes|went|going|turns|turned|gone|just|now|"
                      r"completely|totally|sometimes|stays?|stayed|shows?|showing|keeps|keep))*? blank|"
                      r"blank (?:screen|display)(?! protector)|"
                      # a camera that shows black (not "black titanium"), a screen that goes black
                      r"(?:camera|cameras) (?:is |goes |went |just |shows? |showing |stays? )?black(?! titanium| colou?r)|"
                      r"(?:screen|display) (?:goes|went|turns|turned|stays|stayed|going|turning) black|"
                      # what's wrong with it, not with the buyers or Facebook (words() reads "what's" as "what")
                      r"(?:not (?:too |really |entirely |100%? |quite )?sure|unsure|no idea|no clue|dunno|don['’ ]?t know|"
                      r"dont know|do not know|not certain) (?:what(?:['’ ]?s| is| was)? (?:wrong|up)(?! with (?!(?:it|the "
                      r"phone|this|this one|the (?:screen|camera|battery|port|charging port|speaker|mic|microphone|board|"
                      r"face id))\b))|what the (?:problem|issue|fault)(?: is| was)?|why it (?:won['’ ]?t|doesn['’ ]?t|"
                      r"isn['’ ]?t|keeps|stopped))")
# a nick is a small chip, but "Nick" can be the seller: only "a nick", "one small nick", "nicks" ("in good nick" is fine)
NICK = (r"(?:a|an|one|1|small|tiny|minor|slight|little|light|faint|deep|wee|odd|another|single|few|some|couple of|two|2|"
        r"three|3) nick|(?:a few|few|some|several|two|three|2|3|minor|small|tiny|light|little|couple of|odd|faint) nicks|"
        r"nicks (?:on|in|to|around|and|&|here)\b")  # never "my son Nicks old iPhone"
# damage said as what it needs: "A new screen may be required", "needs new front screen", "Needs to get fixed", "water
# affected the screen", "the camera cover came off" (a kind of damage)
NEEDS_REPAIR = (r"new (?:front |back |rear )?(?:screen|back glass|glass|battery|camera|lens|charging port|port|display) (?:may be |"
                r"is |will be |might be |would be )?(?:required|needed)|needs? new (?:front |back |rear )?(?:screen|glass|back|battery|"
                r"camera|lens|display|port)|needing (?:a )?(?:replacement|replacing|repair\w*|fixing)|needs? to (?:get |be )"
                r"(?:fixed|repaired|replaced|sorted)|water (?:affected|got in|got into|ingress|exposure|got inside)|"
                r"(?:cover|glass|lens|button|back|bezel|trim)s? (?:has |have )?(?:came|come|coming|fell|falling|fallen) (?:off|out)")
# a small bump is a dent ("a really small bump in one of the top corners"), but never the camera bump
BUMP = r"(?:a|one|small|tiny|little|slight|minor)\s+(?:(?!camera\b)\w+\s+){0,2}?bumps?\b"
# wear said other ways: "well used", "slight paint gone"
WELL_USED = r"well[- ]used|heavily used|(?:paint|coating|finish) (?:has )?(?:gone|missing|chipped|coming off|worn|wearing|" \
            r"peeling|rubbed off)"
# wear in other words: "only light signs of use" (a mark of the general kind; "no signs of use" is a denial)
# "wears" only after a word for how much: "minor WEARS on the surfaces", not "always WEARS a case"
WEARS = r"(?:minor|light|slight|small|some|few|little|general|normal|heavy|visible) wears"
# ...also with a word or two for how much ("signs of NORMAL use", "signs of LIGHT, GENTLE use") and typed "ware"
SIGNS_OF_USE = r"signs? of (?:(?:normal|general|light|minor|slight|some|everyday|daily|regular|previous|gentle|small|" \
               r"little|heavy|moderate|obvious|visible|cosmetic|age),?\s+){0,2}(?:use|usage|wear|ware|being used)"
# words that say something is wrong with an item, whatever the words around them: a flaw the AI reads must
# have one (flip.reader), and a message may use one only if the listing does (flip.offers.check_reasons)
PROBLEM = re.compile(
    r"\b(?:crack\w*|scratch\w*|scuff\w*|dent\w*|chip|chips|chipped|marks?|marked|broke|broken|smash\w*|shatter\w*|"
    r"damage\w*|fault\w*|dead|burn|burns|burnt|burned|burn-in|dot|dots|spots?|lines?|stiff|loose|wobbl\w*|"
    r"rattl\w*|crackl\w*|buzz\w*|squeak\w*|drift\w*|drain\w*|laggy|lags|lagging|freez\w*|overheat\w*|"
    r"glitch\w*|flicker\w*|ghost\w*|stuck|sticky|sticks|bent|warp\w*|torn|rip|ripped|stain\w*|faded|fading|"
    r"yellow(?:ed|ing)|discolou?r\w*|worn|wear|tear|tears|peel\w*|missing|issues?|problems?|not working|"
    r"doesn'?t (?:work|charge|turn|connect|hold|stay)|won'?t (?:work|charge|turn|connect|hold|stay)|"
    r"not (?:charging|holding|turning|connecting|pairing)|needs? (?:replacing|a new|repair\w*|fixing)|"
    r"replaced|replacement|repaired|spares|for parts|cosmetic|blemish\w*|imperfection\w*|cloudy|hazy|bleed\w*|"
    r"bubbl\w*|weak|noisy|noise|smell\w*|locked|blacklisted|bad|poor|cracking|swollen|lifting|"
    r"stop(?:s|ped) working|cuts? out|cutting out|restart\w*|intermittent\w*|"
    r"turns? (?:itself )?(?:on and off|off and on|off by itself|off on its own|off randomly)|"
    r"keeps? (?:turning|switching|shutting) (?:off|down)|no (?:face|touch) id|"
    r"(?:isn'?t|is not|not) (?:perfect|great|good|the best|mint|working properly)|"
    rf"{NO_LONGER}|{ISSUE_WORDS}|{SELLER_FAULT_WORDS}|{NICK}|{SIGNS_OF_USE}|{WEARS}|{NEEDS_REPAIR}|{BUMP}|{WELL_USED}|"
    r"spare parts|(?:parts|spares) or repairs?|for repairs?|(?:ideal|perfect|good|great) for (?:someone|anyone|a) (?:looking to |"
    r"wanting to |who can |who wants to )?(?:repair|fix)|"
    # a pixel that's wrong, not "pixel" alone: "2868x1320-pixel resolution", "Google Pixel 8"
    r"(?:dead|stuck|missing|bad|hot|bright|broken|faulty|lit) pixels?|pixels? (?:are |is )?(?:out|missing|dead|stuck|gone|lit)|"
    r"no (?:sound|power|picture|signal|display|image|wifi|charge|charging|service|audio|video|bluetooth)"
    r"(?! (?:cables?|leads?|plugs?|bricks?|blocks?|adapters?|adaptors?|wires?|cords?|case|dock|pads?|station))|"
    rf"(?:does not|doesn['’]?t|do not|don['’]?t|did not|didn['’]?t|will not|won['’]?t|can ?not|can['’]?t|isn['’]?t|"
    rf"is not|not|never) {NOT_DOING})\b",
    re.IGNORECASE)

# how you'll buy: a message may promise it only the way your own messages do (check_no_unasked_promises).
# Collecting is something you'll do ("can collect today", "come and get it"), not a word in a name
# ("Collector's Edition", "your games collection")
PROMISES_ABOUT_YOU = {
    "collecting": re.compile(
        r"\b(?:(?:can|could|will|i'?ll|happy to|able to|ready to|free to|want to|like to|gladly)\s+"
        r"(?:come\s+(?:(?:and|&)\s+)?)?(?:collect|pick)\w*|when (?:i|we) (?:come (?:to |and |& )?)?(?:collect|pick)\w*"
        r"|collect(?:ing|ed)?\s+(?:it|them|this|these|today|tonight|tomorrow|whenever|asap|later|now|any ?time|"
        r"this (?:week|weekend|evening|morning|afternoon)|at|from|in person)"
        r"|on collection|arrange (?:a |the )?collection|collection (?:is|would be|today|tonight|tomorrow|whenever|asap)"
        r"|pick(?:ing)?\s+(?:it|them|this|these)\s+up|pick ?up\s+(?:today|tonight|tomorrow|whenever|asap|later|at|from)"
        r"|come\s+(?:and\s+)?(?:get|grab|collect)|grab\s+(?:it|them)|swing\s+by|(?:drop|nip|pop|come)\s+(?:by|over|round)"
        r"|come to you|travel to you|be there|i'?d (?:be )?collect\w*|be collecting|(?:do|does|doing) collection"
        r"|collection (?:works|suits|is fine|is no problem|is easy|is ok)|collecting (?:is|works|would be)"
        r"|on (?:pick ?up|pickup)|(?:mind|happy|fine|okay|ok|glad)\s+(?:with\s+)?(?:collecting|collection))\b",
        re.IGNORECASE),
    "cash": re.compile(r"\bcash\b|\bpay in person\b", re.IGNORECASE),
    "postage": re.compile(r"\b(?:postage|post(?:ed)?\s+(?:it|them|out|to me)|posting it|ship(?:ping|ped)?|"
                          r"deliver(?:y|ed)?|courier|posted|sen[dt] (?:it )?(?:tracked|recorded|signed)|"
                          r"send it)\b", re.IGNORECASE)}
# a question even without its question mark: "would you take £210 x"
ASKS_YOU = re.compile(r"\b(?:would|could|will|can)\s+(?:you|u)\b", re.IGNORECASE)
# a second, higher offer in words: "if not I can pay the full asking price", "could go a bit higher"
SECOND_OFFER = re.compile(
    r"\b(?:(?:the |your )?full asking(?: price)?|pay (?:the |your )?asking(?: price)?"
    r"|(?:go|pay|offer|stretch|come up)\s+(?:a (?:bit|little) |slightly )?(?:higher|more)\b(?! than)"
    r"|meet (?:you |me )?(?:in the )?middle|split the difference|could do (?:a (?:bit|little) |slightly )?more"
    r"|add (?:a tenner|a fiver|a few quid|\w+ quid|a bit|a little)|(?:a few|couple of|a couple of) quid (?:higher|more)"
    r"|wiggle room|bit of room|flexible on (?:the )?price|price is flexible|go (?:up|higher) (?:a bit|a little|if)"
    r"|if not,? i(?:'d| could| can| would| will|'ll)?\s+(?:do|pay|go|offer|take|meet|stretch|split)"
    r"|if not,? (?:would you (?:take|do|accept|consider)|how about|what about))\b", re.IGNORECASE)
# ...said not to happen after it: "Collection is NOT possible", "collection would be IMPOSSIBLE"
NOT_AFTER = re.compile(r"\s*(?:\w+\s+){0,2}?(?:not|n't|isn't|isnt|impossible|never|unlikely|tricky|difficult|hard|a problem)\b",
                       re.IGNORECASE)
# ...someone else travelling: "happy for YOU to drop round"
SOMEONE_ELSE = re.compile(r"\byou(?:'re| are)? (?:welcome |free |happy )?(?:to|could|can|might)\b(?:\s+\w+){0,2}\s*$",
                          re.IGNORECASE)
# a "no" that isn't one: "no problem collecting", "can't wait to collect"
HARMLESS_NO = re.compile(r"\b(?:no (?:problem|bother|worries|issue)|not a problem|can'?t wait)\b", re.IGNORECASE)
# "can't collect" isn't a promise
NOT_PROMISED = re.compile(r"\b(?:can'?t|cannot|can not|won'?t|wouldn'?t|shouldn'?t|unable to|not|no|never|"
                          r"couldn'?t|(?:don'?t|doesn'?t) (?:take|accept|do|want))\s+(?:\w+\s+){0,3}$",
                          re.IGNORECASE)  # "I see you don't take cash" says it back (not "I don't mind collecting")
# a question tagged onto a promise doesn't make it a question: "I can collect today, does that work?"
TAG_QUESTION = re.compile(r",?\s*(?:does that (?:work|suit(?: you)?|sound (?:ok|okay|good|alright))|"
                          r"is that (?:ok|okay|alright|fine|good)|if that'?s (?:ok|okay|alright|fine)|"
                          r"would that (?:work|be (?:ok|okay|alright|fine))|ok|okay|alright|yeah|fine|good)"
                          r"(?: (?:for|with) you)?\s*\?$", re.IGNORECASE)
# "would you take £170, or is it postage only?" asks about the sale, it doesn't promise
ONLY_QUESTION = re.compile(r",?\s+or is (?:it|that)\b.*$", re.IGNORECASE)
# what can come after a sentence's own end: an emoji, a kiss, "...". Possessive (*+, ++): a run of
# emojis is taken whole, never split up and retried, so emojis mid-sentence ("cracked ❤️❤️❤️ still
# works") can't make it try every way of splitting them, which doubled the time with each emoji
SIGN_OFF = re.compile(r"(?:\s*+(?:[\U0001F300-\U0001FAFF☀-➿\U0001F3FB-\U0001F3FF\ufe0f\u200d]++|\bx{1,3}\b|\.{2,}+|…))++\s*$",
                      re.IGNORECASE)
# (not the "with" of "could do with a new battery": it isn't a reason's, 26 Sep; nor a "due" that isn't "due to": "it's
# due a new battery" is one clause, the fourth red team, 26 Sep)
CLAUSES = re.compile(r"[,;:]|\b(?:as|because|since|given|considering|seeing|(?<!\bdo )with|due(?=\s+to\b)|though|"
                     r"although|now that|"
                     r"knowing|bearing in mind|in light of|in view of|despite|to allow for|to account for|"
                     r"to reflect)\b", re.IGNORECASE)
# a clause that starts with one of these, in a sentence that ends in "?", asks
QUESTION_WORDS = {"any", "anything", "is", "are", "has", "have", "does", "do", "did", "how", "hows", "what",
                  "whats", "was", "were", "can", "could", "would", "will", "and", "or"}
# ...and so does one that asks in a roundabout way: "just wondering IF there are any marks"
INDIRECT = re.compile(r"\b(?:wonder(?:ing)?|let me know|know|ask(?:ing)?|tell me|check(?:ing)?)\s+(?:if|whether)\b"
                      r"|^\s*(?:if|whether)\b|\bwhether\b", re.IGNORECASE)
# in a question, what follows one of these is said, not asked: "would you take £170 AS it comes boxed?"
REASON = re.compile(r"\b(?:as|because|since|given|considering|seeing|due)\b", re.IGNORECASE)
# ...and what follows one of these isn't said at all: "happy to pay it IF it comes with the box"
IF_PART = re.compile(r"\b(?:if|whether|unless)\b[^,.;!?]*", re.IGNORECASE)

ANSWER_FIELDS = {"colour", "condition_id", "condition_note", "description"}


# ── reading text ────────────────────────────────────────────────────────────

def numbers_in(text):
    """Every number in the text, written one way: "£1,200.00" and "1200" are
    both "1200", and "two" is "2"."""
    found = {f"{Decimal(n.replace(',', '')).normalize():f}" for n in NUMBER.findall(text)}
    found |= {str(NUMBER_WORDS[word]) for word in words(text) if word in NUMBER_WORDS}
    return found


def singular(word):
    """"chargers" -> "charger", "boxes" -> "box", "batteries" -> "battery", for claim words only."""
    for ending, replacement in (("ies", "y"), ("es", ""), ("s", "")):
        if word.endswith(ending) and word[:-len(ending)] + replacement in KEYWORDS:
            return word[:-len(ending)] + replacement
    return word


KEY_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
VOWELS = frozenset("aeiou")
SHORTEST_TYPO = 4  # letters: "crk" or "dnt" could be anything
REAL_WORDS = Path(__file__).resolve().parent.parent / "data" / "real_words.json"


def keys_near(row, column):
    """The keys touching one on a UK keyboard: either side, and two above and
    two below. Each row sits half a key right of the one above it, so "g"
    touches "f", "h", "t", "y", "v" and "b"."""
    near = {(row, column - 1), (row, column + 1), (row - 1, column), (row - 1, column + 1),
            (row + 1, column - 1), (row + 1, column)}
    return {KEY_ROWS[r][c] for r, c in near if 0 <= r < len(KEY_ROWS) and 0 <= c < len(KEY_ROWS[r])}


NEAR_KEYS = {key: keys_near(r, c) for r, keys in enumerate(KEY_ROWS) for c, key in enumerate(keys)}


def wrong_letter(typed, meant):
    """What typing one letter for another costs in slips: 1 for a key next
    to it or another vowel, else 2 (as good as one left out and one added)."""
    return 1 if typed in NEAR_KEYS.get(meant, ()) or (typed in VOWELS and meant in VOWELS) else 2


def slips(typed, word, most):
    """How many slips typed is from word, or most + 1 if it's more: a letter
    left out, one too many or two next to each other swapped is one slip,
    and a wrong letter is wrong_letter's. Edit distance (optimal string
    alignment), counting only the slips people make."""
    if abs(len(typed) - len(word)) > most:
        return most + 1
    before, row = None, list(range(len(word) + 1))
    for i in range(1, len(typed) + 1):
        now = [i] + [0] * len(word)
        for j in range(1, len(word) + 1):
            same = typed[i - 1] == word[j - 1]
            now[j] = min(row[j] + 1, now[j - 1] + 1, row[j - 1] + (0 if same else wrong_letter(typed[i - 1], word[j - 1])))
            if i > 1 and j > 1 and typed[i - 1] == word[j - 2] and typed[i - 2] == word[j - 1]:
                now[j] = min(now[j], before[j - 2] + 1)
        before, row = row, now
    return min(row[-1], most + 1)


def most_slips(form):
    """How many slips a claim word can take and still be read: none under 4
    letters, one up to 8, two from 9 ("scratches" typed "scarches")."""
    return 0 if len(form) < SHORTEST_TYPO else 1 if len(form) <= 8 else 2


def claim_forms(keyword):
    """A claim word and its plurals: "battery", "batterys", "batteries"."""
    return {keyword, keyword + "s", keyword + "es"} | ({keyword[:-1] + "ies"} if keyword.endswith("y") else set())


@lru_cache(maxsize=1)
def real_words():
    """The real words a typo is never read as: every word within wider_slip's
    reach of a claim word that's in macOS's dictionary (with its endings:
    "cards", "charges") or in the catalogue and listings ("mini", "mins").
    Built by flip.real_words."""
    return frozenset(json.loads(REAL_WORDS.read_text(encoding="utf-8")))


# everyday words of listings and notes a few slips from a claim word: a typo as close to one of these as to
# the claim word could be either, so it's read as neither ("minr" is as close to minor as to mint)
COMMON_WORDS = frozenset("""
    base bugs buds cage came card cards care cash caused charge charged charges cheap close cold could cross deal
    decent does dont doesnt done extra function functions gate goes gone guess just less load loaded loads loud main
    make made makes many mask mind mine mini mins minor minus minutes model month months more most near need needs
    newer sale sales star start this tops touch unlock used warm west word words work worked working wrong year
""".split())
# words reading needs spelt right, though they aren't claims: "witout box" says no box
READING_WORDS = ("without",)
TYPED_WORD = re.compile(r"[a-z]{4,}")


def fewest_slips(word, targets):
    """The targets a typed word is fewest slips from, within each one's
    most_slips and with the first letter right: (slips, {targets}), or (None, set())."""
    best, closest = None, set()
    for target in targets:
        most = most_slips(target)
        if not most or target[0] != word[0] or abs(len(target) - len(word)) > most:
            continue
        n = slips(word[1:], target[1:], most)
        if n <= most and (best is None or n <= best):
            closest = closest | {target} if n == best else {target}
            best = n
    return best, closest


@lru_cache(maxsize=None)
def wider_slip(word, guard=True):
    """Rule 3 of slipped: the claim word a typed word is fewest slips from
    (most_slips for that word, the first letter right), unless it's a real
    word (guard), an everyday word is as close (COMMON_WORDS), or claim words
    that say different things are as close: then it could be either. "dentd"
    is as close to "dent" as to "dented": a dent either way."""
    if len(word) < SHORTEST_TYPO or word in KEYWORDS or (guard and (word in real_words() or word in COMMON_WORDS)):
        return None
    forms = {form: keyword for keyword in KEYWORDS for form in claim_forms(keyword)}
    best, closest = fewest_slips(word, forms)
    everyday, _ = fewest_slips(word, COMMON_WORDS) if guard else (None, set())
    if best is None or (everyday is not None and everyday <= best):
        return None
    keywords = {forms[form] for form in closest}
    return min(keywords) if len({KEYWORDS[k] for k in keywords}) == 1 else None


@lru_cache(maxsize=None)
def as_meant(word):
    """A word as it was meant to be: a claim word typed with a slip ("crak"
    -> "crack"), or a word reading needs ("witout" -> "without"); else as typed."""
    if word in KEYWORDS or singular(word) in KEYWORDS:
        return word
    if slipped(word):
        return slipped(word)
    _, meant = fewest_slips(word, READING_WORDS) if word not in real_words() and word not in READING_WORDS else (0, ())
    return next(iter(meant), word)


def one_slip(typed, word):
    """True if typed is word with one slip: a letter left out ("scrach"), one
    too many ("chargerr") or two next to each other swapped ("chrager")."""
    if len(typed) == len(word):
        at = [i for i, (a, b) in enumerate(zip(typed, word)) if a != b]
        return len(at) == 2 and at[1] == at[0] + 1 and typed[at[0]] == word[at[1]] and typed[at[1]] == word[at[0]]
    short, long = sorted((typed, word), key=len)
    return len(long) - len(short) == 1 and any(long[:i] + long[i + 1:] == short for i in range(len(long)))


@lru_cache(maxsize=None)
def slipped(word):
    """The claim word a typed word misses, plural or not, or None:
    1. "battery" is typed so many ways it has its own pattern ("baterray", "batt");
    2. one slip in a claim word of 6 letters or more that starts with the same
       letter: a letter left out, one too many or two swapped ("scraches" ->
       "scratch"), never one of NOT_SLIPS;
    3. else the other slips people make in a hurry (wider_slip): a key next
       to the right one ("scrstch"), another vowel ("excellant"), a slip in a
       shorter word ("crak", "dnet") or two in a long one ("scarches"), never
       a real word ("cash" isn't a case, nor "mask" a mark)."""
    if re.fullmatch(TYPED_BATTERY, word):
        return "battery"
    return one_slip_claim(word) or wider_slip(word)


def one_slip_claim(word):
    """Rule 2 of slipped: what a typed word with one slip says, the way it was read before 14 Sep 2026."""
    if len(word) < SLIP_LENGTH:
        return None
    for ending, replacement in (("", ""), ("ies", "y"), ("es", ""), ("s", "")):
        if not word.endswith(ending):
            continue
        typed = word[:len(word) - len(ending)] + replacement
        if typed in NOT_SLIPS:
            return None
        for keyword in KEYWORDS:
            if len(keyword) >= SLIP_LENGTH and keyword[0] == typed[0] and one_slip(typed, keyword):
                return keyword
    return None


# "no" (or "without") over a list of things that come with it, or of marks, with commas in it and ending "or" or "nor"
# one: "no box, charger or cable", "no scratches, dents or cracks". Each item is one of those things, with up to two
# words before it ("original box"), so a list never runs over "unlocked" or "works" ("no screen protector, unlocked,
# works, no box, charger or cable" has its own "no box, charger or cable")
LISTED = (r"(?:box(?:es)?|boxed|chargers?|adapt[eo]rs?|plugs?|cables?|leads?|cords?|cases?|covers?|protectors?|manuals?|"
          r"instructions|paperwork|receipts?|invoices?|accessor(?:y|ies)|extras|earphones|headphones|tips|pouch(?:es)?|"
          r"sleeves?|bags?|headsets?|scratch(?:es)?|scuffs?|dents?|cracks?|chips?|marks?|stickers?)")
LIST_ITEM = rf"(?:(?!(?:no|not|or|nor|and)\b)[a-z]+ ){{0,2}}{LISTED}"
NO_LIST = re.compile(rf"\b(?:no|without)\s+({LIST_ITEM}(?:\s*,\s*{LIST_ITEM})+\s*,?\s+(?:or|nor)\s+{LIST_ITEM})\b")


def promises_in(text, typos=False):
    """Each claim the text makes, and whether it says yes or no to it.

    "Boxed, no charger" -> {"box": {"yes"}, "charger": {"no"}}
    "box: no", "charger not included" and "free from scratches" are all a no.
    A condition word next to a part is about that part only: "screen perfect"
    -> {"flawless screen": {"yes"}}, not a flawless item. With typos (for what
    people type: your notes, the seller's listing) a claim word with one slip
    counts: "few scraches" says scratches. The AI's own words are read as written.
    """
    found = {}
    text = answered(text).lower()
    if typos:
        text = BH.sub("battery", text)
        # each word typed with a slip, as the word it was meant to be, before anything reads the text: then
        # "crak free" is "crack free" and "out of warrenty" is "out of warranty", read as no like any other
        text = TYPED_WORD.sub(lambda m: as_meant(m.group()), text)
    # "box: yes" -> "box" ("box: no" is answered's)
    text = re.sub(r"\b([a-z]+(?: [a-z]+)?)\s*[:=\-–—]\s*(?:yes|yep|included)\s*(?=[,.;\n]|$)", r"\1", text)
    # a "no" over a list with commas in it is a no to each: "no box, charger or cable" (14 Oct: read as a charger and a
    # cable that come with it), "no scratches, dents or cracks"
    text = NO_LIST.sub(lambda m: ", ".join(f"no {item}" for item in re.split(r"\s*,\s*(?:(?:or|nor)\s+)?|\s+(?:or|nor)\s+",
                                                                         m.group(1)) if item), text)
    # read one part of a sentence at a time, so "no scratches, comes with box"
    # or "no scratches and comes with box" doesn't turn into "no box"
    for part in re.split(r"[,.;:!?\n()]|\bbut\b|\band\b(?= (?:comes|has|includes|included|with|is|boxed))", text):
        part = " " + " ".join(words(part)) + " "
        if NOT_SURE.search(part):
            continue
        for phrase, same in SAME_AS:
            part = part.replace(f" {phrase} ", f" {same} ")
        for phrase in HARMLESS:
            part = part.replace(f" {phrase} ", " ")
        part = NOT_A_FLAW.sub(" ", part)
        part = NO_EFFECT.sub(" ", part)
        part_words = part.split()
        for i, word in enumerate(part_words):
            promise = KEYWORDS.get(singular(word)) or (typos and KEYWORDS.get(slipped(word)))
            if not promise:
                continue
            if promise in ("case", "screen protector") and LOOKED_AFTER.search(part):
                continue
            if promise == "new" and set(part_words[i + 1:i + 3]) & PARTS:
                continue  # "new battery fitted": the battery is new, not the item
            if promise == "chip" and i > 0 and (part_words[i - 1].isdigit() or part_words[i - 1] in PROCESSOR_WORDS):
                continue  # "A15 Bionic chip" is the processor
            if promise in LEVELS:
                if set(part_words[i + 1:i + 2]) & FEATURES:
                    continue  # "excellent noise cancelling" describes the model
                # the part can come a few words before: "the SCREEN is in perfect condition"
                start = max(0, i - 4)
                if "and" in part_words[start:i]:  # "cracked screen AND not in perfect condition" is the item (14 Oct)
                    start = i - part_words[start:i][::-1].index("and")
                parts = sorted(CONDITION_PARTS & set(part_words[start:i + 2]))
                if parts:
                    promise = f"{promise} {parts[0]}"
            # a "no" after the claim may cover a whole list: "box and charger not included"
            j = i + 1
            while j < len(part_words) and (part_words[j] in LIST_WORDS or KEYWORDS.get(singular(part_words[j]))):
                j += 1
            after = part_words[j:j + 3]
            # up to 5 words back: "doesn't come with a charger" splits into
            # doesn / t / come / with / a, so "doesn" is 5 words before. A "no" stops
            # where its own thing ends: "no offers small crack", "no cracks only light scratches"
            lead = part_words[max(0, i - 5):i]
            if promise == "working" and "and" in lead:  # "no cracks AND no faults" isn't "not working" (14 Oct)
                lead = lead[len(lead) - lead[::-1].index("and"):]
            negated = denied_by(lead) or bool(NEGATED_AFTER & set(after[:2])) \
                or any(w in ("not", "t") and nxt in INCLUDED for w, nxt in zip(after, after[1:]))
            found.setdefault(promise, set()).add("no" if negated else "yes")
    return found


def ends_asking(sentence):
    """Whether a sentence asks: it ends in a question mark once a sign-off
    after it is set aside ("Would you take £210?😊"), or it's a "would you"
    question left without one ("Would you take £210 x", "...£210...")."""
    sentence = SIGN_OFF.sub("", sentence).rstrip()
    return sentence.endswith("?") or not sentence.endswith((".", "!")) and bool(ASKS_YOU.search(sentence))


def clauses(message):
    """A message's clauses, each with whether it asks: "Would you take £170,
    as the back is cracked?" -> [("Would you take £170", True),
    (" the back is cracked?", False)]."""
    found = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", message.strip()):
        question = ends_asking(sentence)
        for clause in CLAUSES.split(sentence):
            clause_words = words(clause)
            if clause_words:
                found.append((clause, (question and clause_words[0] in QUESTION_WORDS) or bool(INDIRECT.search(clause))))
    return found


def stated_parts(message):
    """What a message states about the item, for its claims: the sentences that
    don't ask, and in a question only the reason after "as", "because"...
    Nothing after "if" or "whether" is stated: "happy to pay it if it comes
    with the box". Unlike clauses(), "with" doesn't start a statement: "does it
    come WITH a charger?" asks about the charger."""
    text = re.sub(r"\b(?:just )?in case\b", " ", IF_PART.sub(" ", message.strip()), flags=re.IGNORECASE)
    parts = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        parts += REASON.split(sentence)[1:] if ends_asking(sentence) else [sentence]
    return parts


def condition_figures(text):
    """Every battery-health style figure, written one way: "87%", "87 per cent",
    "battery health 87", "87 battery health", "battery %87" and "87🔋" are all "87"."""
    return {f"{Decimal(n).normalize():f}" for n in PERCENT.findall(text)} | battery_worded(text)


def new_conditions_allowed(notes):
    """Which of New (1000) and Opened - never used (1500) your notes back.

    New: "sealed", "brand new", "unopened", with no sign it was used or opened
    ("in brand new condition", "used twice", "box opened" all rule it out).
    Opened - never used: "never used" or "unused" (or sealed), with no sign of use.
    """
    notes = ITS_THINGS_NEW.sub(" , ", (notes or "").lower())
    text = " ".join(words(notes))
    claims = promises_in(notes, typos=True)
    if "no" in claims.get("new", set()) | claims.get("sealed", set()):
        return set()
    if USED_SIGNS.search(UNUSED.sub(" ", text)):  # "never used" isn't a sign of use
        return set()
    allowed = set()
    if UNUSED.search(text) or NEW_SEALED.search(text):
        allowed.add("1500")
    if NEW_SEALED.search(text) and not OPENED_SIGNS.search(re.sub(r"\bnever (?:been )?opened\b", " ", text)):
        allowed.add("1000")
    return allowed


def condition_for(notes):
    """eBay's condition, decided by code from your notes: For parts or not
    working (7000) if they mention a fault, New (1000) or Opened - never used
    (1500) if they back it, otherwise Used (3000). A crack or scratch on its own
    is wear, not a fault. The AI writes the note and description to match."""
    if has_fault(notes or ""):
        return FOR_PARTS
    allowed = new_conditions_allowed(notes or "")
    return "1000" if "1000" in allowed else "1500" if "1500" in allowed else "3000"


def has_fault(notes):
    """True if your notes mention a fault: "face id broken", "stopped working",
    "left joycon drift", "won't charge". "No faults" and "no drift" don't count,
    and a "no" counts only in its own sentence: "No box. Broken screen." is a fault."""
    if "no" in promises_in(notes).get("working", set()):
        return True
    return any(FAULTS.search(NOT_A_FAULT.sub(" ", " ".join(words(part)))) for part in re.split(r"[.!?;\n]", notes))


def mark_backing(promise, from_notes):
    """What your notes back for one kind of mark. Your "no marks" backs "no
    scratches"; your "scratch on the screen" never backs "no scratches" or "no marks"."""
    said = {kind: from_notes.get(kind, set()) for kind in MARKS}
    any_yes = any("yes" in s for s in said.values())
    if promise == "mark":
        any_no = any("no" in s for s in said.values())
        return ({"yes"} if any_yes else set()) | ({"no"} if any_no and not any_yes else set())
    backing = set(said[promise]) | ({"yes"} if "yes" in said["mark"] else set())
    if "no" in said["mark"] and "yes" not in said[promise]:
        backing.add("no")
    return backing


def level_backing(promise, from_notes):
    """What your notes back for "excellent" or "flawless", on the whole item or
    a part ("flawless screen"). A higher level backs a lower one, and the whole
    item's backs a part's."""
    level, _, part = promise.partition(" ")
    backing = set(from_notes.get(promise, set()))
    for higher in LEVELS[level]:
        for key in {f"{higher} {part}".strip(), higher}:
            if "yes" in from_notes.get(key, set()):
                backing.add("yes")
    return backing


def contact_details_in(text):
    text = re.sub(r"(?<=\d)[oO]|[oO](?=\d)", "0", text)  # a letter O typed for a zero: "O7700 900123"
    joined = re.sub(r"(?<=\d)[\s().\-]+(?=\d)", "", text)  # "07700 900-123" -> "07700900123"
    return any(pattern.search(text) for pattern in (LINK, EMAIL, HANDLE, CONTACT_WORDS)) or \
        any(pattern.search(joined) for pattern in (PHONE, LONG_NUMBER))


def canonical(value, allowed, aliases=None):
    """The allowed spelling of a value, ignoring case and punctuation, or None
    if it isn't allowed: "midnight" -> "Midnight", 3000 -> "3000", and with the
    model's short colour names "red" -> "(PRODUCT)RED"."""
    aliases = aliases or {}
    for option in allowed:
        if any(words(str(value)) == words(name) for name in [option, *aliases.get(option, [])]):
            return option
    return None


def names_a_version(text_words, end, not_if):
    """True if the word right after a name makes it a different version:
    "iPhone 13 MINI", "PS5 PRO". Not "plus" meaning "and" ("plus a case")."""
    after = text_words[end:end + 2]
    if not after or after[0] not in not_if:
        return False
    return not (after[0] == "plus" and after[1:] and after[1] in PLUS_MEANS_AND)


def names_other_model(text_words, model, catalogue):
    """True if the text names a model other than this one: another catalogue
    model ("iPhone 14"), or a name next to a word for a different version
    ("iPhone 13 mini", "PS5 Pro" on a PS5 Slim, "WF-1000XM4"). A shorter family
    name on its own is fine: "PS5" on a PS5 Slim."""
    own = [words(alias) for alias in model["aliases"]]
    for other in catalogue:
        if other is model:
            continue
        for alias in other["aliases"]:
            alias_words = words(alias)
            family = any(name[:len(alias_words)] == alias_words for name in own)
            for start in find_phrase(text_words, alias_words):
                if not family or names_a_version(text_words, start + len(alias_words), model["not_if"]):
                    return True
    for name in own:
        for start in find_phrase(text_words, name):
            before = text_words[max(0, start - 1):start]
            if set(before) & set(model["not_if"]) or names_a_version(text_words, start + len(name), model["not_if"]):
                return True
    return False


def sources_text(title, description, notes, item):
    """Everything the AI may state: your inputs plus the catalogue's facts."""
    facts = [item.get("brand"), item.get("model"), item.get("storage"), item.get("colour"),
             item.get("network"), *item.get("options", {}).values(), *item.get("specs", {}).values()]
    return " ".join([title or "", description or "", notes or "", *[fact for fact in facts if fact]])


# ── single checks: each returns a list of problems, empty = passed ──────────

def check_allowed(what, value, allowed, aliases=None):
    if canonical(value, allowed, aliases) is None:
        return [f"{what} {value!r} isn't one of the allowed values"]
    return []


def check_length(what, text, limit, required=True):
    if not isinstance(text, str):
        return [f"{what} isn't text"]
    if required and not text.strip():
        return [f"{what} is empty"]
    if len(text) > limit:
        return [f"{what} is {len(text)} characters, over the {limit} limit"]
    return []


# texting words with a digit in them aren't numbers: "can collect 2day", "cheers m8" (26 Sep)
TEXT_SPEAK = re.compile(r"\b(?:2day|2nite|2night|2moro|2morrow|2mrw|2mro|2morow|2mora|2u|4u|4ever|b4|gr8|m8s?|l8r|l8|w8|"
                        r"any1|some1|no1|every1)\b", re.IGNORECASE)


# a clock time, as you'd say when you'll come: "after 6pm", "any time after 6", "before 9 tomorrow", "half 6",
# "at 7:30", "6.30pm", "5-7pm" (26 Sep). A bare number is one only after a word that gives a time, never one that
# counts ("in 10 mins", "2 days")
CLOCK_TIME = re.compile(r"\b(?:(?P<lead>after|before|at|around|about|from|by|till|until|til|half(?: past)?|between|and|"
                        r"or|to)\s+)?(?P<hour>\d{1,2})(?!\d)(?:[:.](?P<minute>[0-5]\d)(?!\d))?"
                        r"(?:\s?(?P<mark>am|pm|o'?clock|ish)\b"
                        r"|(?=(?P<range>\s?[-–]\s?\d{1,2}(?:[:.][0-5]\d)?\s?(?:am|pm)\b)))?"
                        r"(?!\s?(?:mins?|minutes?|hours?|hrs?|days?|weeks?|months?|years?|miles?|%|gb|tb)\b)",
                        re.IGNORECASE)


def clock_times(text):
    """The clock times a text gives, each with where it is in the text and
    its time on a 12-hour clock: "after 6pm" and "after 6" are both (6, 0),
    "half 6" and "at 6.30" (6, 30). "in 10 mins" and "2 of them" are none."""
    found = []
    for m in CLOCK_TIME.finditer(text):
        lead, hour, minute, mark = (m.group("lead") or "").lower(), int(m.group("hour")), m.group("minute"), \
            (m.group("mark") or "").lower()
        if not (lead or minute or mark or m.group("range")) or hour > (12 if mark in ("am", "pm") else 23):
            continue
        found.append((m.span(), (hour % 12, int(minute) if minute else 30 if lead.startswith("half") else 0)))
    return found


def check_no_invented_numbers(what, text, sources, own=()):
    """No number that's in none of the inputs. own: your own sentences (the
    message drafter's phrasebook, flip.style). One of them in the text word
    for word keeps its numbers ("Only 10 mins away."), and a clock time you
    give in them is yours in any sentence about collecting ("Can collect from
    Leeds LS6 after 6pm." from your "Can collect after 6pm."; 26 Sep red team:
    refused every time, so the AI told to end with it was too). A time you
    never give is still made up ("Can collect after 7pm")."""
    if own:
        mine = {tuple(words(sentence)) for sentence in own}
        times = {clock for sentence in own for _, clock in clock_times(sentence)}
        kept = []  # cut as flip.style cuts your sentences: "£170?😊 Can collect" is two
        for sentence in re.split(r"(?<=[.!?])\s+|(?<=[.!?][\U0001F300-\U0001FAFF☀-➿])\s+|\n+", text):
            if tuple(words(sentence)) in mine:
                continue  # yours, word for word
            if COLLECT_TALK.search(sentence):
                for (start, end), clock in reversed(clock_times(sentence)):
                    if clock in times:
                        sentence = f"{sentence[:start]} {sentence[end:]}"
            kept.append(sentence)
        text = " ".join(kept)
    extra = numbers_in(TEXT_SPEAK.sub(" ", text)) - numbers_in(sources)
    if extra:
        return [f"{what} has numbers that aren't in your inputs: {', '.join(sorted(extra))}"]
    return []


def check_no_invented_percentages(what, text, notes, sources, battery=None):
    """A percentage, like battery health, is about this item's condition: it
    must come from your notes, not the seller's words, with or without the %
    sign. battery: the battery health code read from your notes, which may be
    a number on its own there ("78, few scratches"). (One that isn't in any
    input at all is already reported by the numbers check.)"""
    noted = condition_figures(notes) | ({battery} if battery else set())
    extra = (condition_figures(text) - noted) & numbers_in(sources)
    if extra:
        return [f"{what} has a percentage your notes don't: {', '.join(f'{p}%' for p in sorted(extra))}"]
    return []


def check_no_invented_promises(what, text, sources, notes, battery=None):
    """Every claim in the text must be backed, with the same yes or no.
    Condition claims only by your notes. Anything else by your notes if they
    mention it ("no box" beats the seller's "boxed"), otherwise by any input.
    And nothing is "working" when your notes mention a fault. battery: the
    battery health code read from your notes ("78" on its own, "84🔋"): then
    your notes speak about the battery without the word."""
    from_inputs, from_notes = promises_in(sources, typos=True), promises_in(notes, typos=True)
    if battery:
        from_notes = {**from_notes, "battery": from_notes.get("battery", set()) | {"yes"}}
    faulty = has_fault(notes)
    unbacked, unbacked_condition = [], []
    for promise, saids in sorted(promises_in(text).items()):
        condition = promise.split()[0] in CONDITION_PROMISES
        if promise in MARKS:
            backing = mark_backing(promise, from_notes)
        elif promise.split()[0] in LEVELS:
            backing = level_backing(promise, from_notes)
        else:
            backing = from_notes.get(promise) or (set() if condition else from_inputs.get(promise, set()))
        for said in sorted(saids, reverse=True):
            if said not in backing or (promise == "working" and said == "yes" and faulty
                                       and not works_as_noted(text, notes)):
                (unbacked_condition if condition else unbacked).append(promise if said == "yes" else f"no {promise}")
    problems = []
    if unbacked:
        problems.append(f"{what} says things your inputs don't: {', '.join(unbacked)}")
    if unbacked_condition:
        problems.append(f"{what} says things about the condition your notes don't: {', '.join(unbacked_condition)}")
    return problems


# what a phone has that can work or not: "the TOUCHSCREEN works", "cameras and FLASH work"
WORKING_PARTS = {"touchscreen", "touch", "screen", "display", "camera", "flash", "speaker", "mic", "microphone", "face",
                 "id", "faceid", "touchid", "button", "port", "charging", "wifi", "bluetooth", "signal", "sim", "volume",
                 "power", "lens", "sensor", "nfc", "gps", "earpiece", "vibration", "haptic", "sound", "audio", "network",
                 "data", "keyboard", "trackpad"}
# said of the rest: "everything ELSE works", "works fine OTHERWISE"
RESTS = re.compile(r"\b(?:else|otherwise|rest|apart from|other than|besides|aside from)\b")


def works_said(text, typos=False):
    """Each part of a text that says something works: (the parts it names, whether it's said of the rest)."""
    found = []
    for part in re.split(r"[,.;:!?\n()]|\bbut\b", text.lower()):
        if "yes" in promises_in(part, typos=typos).get("working", set()):
            found.append(({singular(w) for w in words(part)} & WORKING_PARTS, bool(RESTS.search(part))))
    return found


def works_as_noted(text, notes):
    """Whether each "works" in the text is said only of parts your notes say work ("the touchscreen works"), or of
    the rest when your notes say the rest works ("everything else is working"): then a fault in your notes doesn't
    make it false (14 Oct). A plain "fully working", or a part your notes don't say works, still is."""
    noted = works_said(notes, typos=True)
    theirs = set().union(*(named for named, _ in noted)) if noted else set()
    for named, rest in works_said(text):
        if named and named <= theirs:
            continue
        if rest and not named and any(r for _, r in noted):
            continue
        return False
    return True


def place_of(word):
    """The place a word names, plural or not ("sides" -> "side"), or None."""
    for ending in ("", "s", "es"):
        if word.endswith(ending) and word[:len(word) - len(ending)] in PLACES:
            return PLACES[word[:len(word) - len(ending)]]
    return None


def is_mark(word, typos=False):
    promise = KEYWORDS.get(singular(word)) or (typos and KEYWORDS.get(slipped(word)))
    return promise in MARKS


def mark_places(text, typos=False, reach=None):
    """Where a text says there are marks: the places in each part of a sentence
    that says there is one ("no scratches on the screen" says none). With
    reach, only places that close to a mark word. "Light scratch on the back,
    corners and sides" -> {"back", "corner", "side"}."""
    found, marked = set(), False
    # a screen protector's marks aren't the screen's (14 Oct: "the screen protector is scratched")
    text = re.sub(r"\bscreen\s+(?:protector|guard)s?\b", "protector", text.lower())
    # "...is cracked AND THE bottom left corner is loose": the corner isn't where the crack is (14 Oct)
    for part in re.split(r"[,.;:!?\n()]|\b(?:but|while|whereas|except)\b|\band\b(?=\s+(?:the|it|its|there|a|an|some|minor|"
                         r"light|small|slight|few|couple|tiny|deep|large|big)\b)", text):
        part_words = words(part)
        places = [place_of(word) for word in part_words]
        if part_words and all(place or word in PLACE_LIST_WORDS for word, place in zip(part_words, places)):
            if marked:  # the list of places goes on
                found |= {place for place in places if place}
            continue
        claims = promises_in(part, typos=typos)
        marked = any("yes" in claims.get(mark, set()) for mark in MARKS)
        if not marked:
            continue
        at = [i for i, word in enumerate(part_words) if is_mark(word, typos)]
        # marks said of the screen protector are its own: "the screen is perfect under a SCRATCHED PROTECTOR" (14 Oct)
        if at and all(any(w.startswith("protector") for w in part_words[max(0, i - 2):i + 3]) for i in at):
            continue
        found |= {place for i, place in enumerate(places)
                  if place and (reach is None or any(abs(i - j) <= reach for j in at))}
    return found


# calling the battery good: a judgement only your notes can make. "78%" is a figure, and below
# 80% an iPhone itself says the battery needs service. Within a few words, in one sentence
PRAISE = r"(?:good|great|healthy|excellent|strong|decent|solid|perfect|amazing|fantastic|brilliant)"
BATTERY_PRAISE = re.compile(rf"\bbatter(?:y|ies)\b[^.!?\n]{{0,20}}?\b{PRAISE}\b|\b{PRAISE}\b[^.!?\n]{{0,12}}?\bbatter(?:y|ies)\b",
                            re.IGNORECASE)


def check_battery_praise(what, text, notes):
    """Only your notes can call the battery good: "battery 78" doesn't make
    "the battery is in good condition at 78%"."""
    if BATTERY_PRAISE.search(text) and not BATTERY_PRAISE.search(notes):
        return [f"{what} calls the battery good, and your notes only give its figure"]
    return []


def check_mark_places(what, text, notes):
    """Where a mark is comes from your notes too: your "few scratches" doesn't
    say they're on the screen and back."""
    extra = mark_places(text, reach=MARK_REACH) - mark_places(notes, typos=True)
    if extra:
        return [f"{what} says where marks are when your notes don't: {', '.join(sorted(extra))}"]
    return []


def check_matches_item(what, text, item, catalogue, colour, sources=""):
    """The text mustn't contradict the item: a different model or version, or a
    colour, storage size or edition it doesn't have. colour is the one settled
    for this item; if nobody knows it (None), no colour may be named. A plain
    colour word your inputs already use isn't counted: "Call of Duty: Black Ops"
    is a game, not the console's colour."""
    model = next(m for m in catalogue if m["id"] == item["model_id"])
    text_words = words(text, breaks=True)
    problems = []
    if names_other_model(text_words, model, catalogue):
        problems.append(f"{what} names a different model from the {model['model']}")
    named = colours_named(text_words, model)
    own = [colour, *model.get("colour_aliases", {}).get(colour, []), *model.get("colour_words", {}).get(colour, [])] \
        if colour else []
    covered = {word for name in [*own, *named] for word in words(name)} | set(words(sources))
    wrong = sorted(named - {colour}) + sorted(c for c in COMMON_COLOURS - covered if item_colour_mentioned(text_words, c))
    if wrong:
        problems.append(f"{what} names a colour that isn't the item's: {', '.join(wrong)}")
    sizes = sizes_in(text_words) & set(model["storage"])
    if sizes - {item.get("storage")}:
        problems.append(f"{what} names a storage size that isn't the item's: {', '.join(sorted(sizes - {item.get('storage')}))}")
    for name, values in options_named(text_words, model).items():
        mine = item.get("options", {}).get(name)
        if values - {mine}:
            problems.append(f"{what} says {', '.join(sorted(values - {mine}))}, "
                            f"but the item's {name.lower()} is {mine or 'not known'}")
    return problems


def check_no_prices(what, text):
    """A listing never states a price: not what you paid, not the seller's
    asking price, not the RRP."""
    if any(pattern.search(text) for pattern in (*PRICES[:2], LISTING_PRICE)):
        return [f"{what} mentions a price"]
    return []


def check_no_off_platform(what, text, ebay=True):
    """Nothing about paying or dealing outside the platform: bank transfer,
    PayPal friends and family, "outside eBay" or "off the app", ending the
    listing early. On Facebook or Gumtree (ebay=False) there's no sale to go
    round, so ending the listing is only what "take it down" says."""
    found = OFF_PLATFORM.search(text)
    if found and (ebay or not ENDING.fullmatch(found.group())):
        return [f"{what} suggests paying or dealing outside the platform"]
    return []


def check_no_contact_details(what, text):
    if contact_details_in(text):
        return [f"{what} contains a link, email, phone number, handle or long ID number"]
    return []


def check_no_story(what, text, sources=""):
    """Nothing made up about you: who it's for ("for my son"), why you want it
    ("my old one broke"), where you are ("I'm round the corner"), that you
    don't resell. Only you know those. Echoing the listing is fine: "I see it
    was an unwanted Christmas present"."""
    listed = words(sources)
    for found in STORY.finditer(" ".join(words(text))):
        if not find_phrase(listed, found.group().split()):
            return [f"{what} makes up something about you: \"{found.group()}\""]
    return []


def check_message_claims(message, sources):
    """A message may say the item comes with a box, charger, warranty... or is
    unlocked only when the listing says so. Asking is fine: "does it come with
    the box?"."""
    listed = promises_in(sources, typos=True)
    made_up = sorted({promise for part in stated_parts(message) for promise, saids in promises_in(part).items()
                      if promise in PROMISES and "yes" in saids and "yes" not in listed.get(promise, set())})
    if made_up:
        return [f"the message says things the listing doesn't: {', '.join(made_up)}"]
    return []


def promised_in(text):
    """How a text says you'll buy: the habits ("collecting", "cash",
    "postage") it promises in a sentence that isn't a plain question. The
    offer's own sentence counts even as a question ("would you take £185
    cash?" offers cash), and so does a promise with a question tagged on ("I
    can collect today, does that work?"). "Could I collect?" asks, and "can't
    collect" doesn't promise."""
    found = set()
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text.strip()):
        sentence = TAG_QUESTION.sub(".", SIGN_OFF.sub("", sentence))
        if sentence.endswith("?") and not prices_in(sentence):
            continue
        sentence = ONLY_QUESTION.sub("", sentence)
        for habit, pattern in PROMISES_ABOUT_YOU.items():
            if any(promised(sentence, m, habit) for m in pattern.finditer(sentence)):
                found.add(habit)
    return found


def promised(sentence, found, habit):
    """Whether one match of a habit in a sentence is a promise of yours: not
    "can't collect" (with "no problem collecting" and "can't wait to
    collect" still promises), not one said not to happen after it
    ("Collection is not possible"), not the seller travelling ("happy for
    you to drop round"), and not a name ("the Johnny Cash LP")."""
    before = HARMLESS_NO.sub(" ", sentence[:found.start()])
    if NOT_PROMISED.search(before) or NOT_AFTER.match(sentence[found.end():]):
        return False
    if habit == "collecting" and SOMEONE_ELSE.search(before):
        return False
    return not (habit == "cash" and found.group()[:1] == "C" and re.search(r"\b[A-Z][a-z]+ $", before))


def check_no_unasked_promises(message, allowed):
    """A message says how you'll buy (collecting, cash, posting) only the way
    your own messages do. allowed: what your messages promise (promised_in on
    them), from your style card and the example messages. With no past
    messages nothing is: "I can arrange collection quickly" would be the AI's
    promise, not yours."""
    promised = sorted(promised_in(message) - set(allowed))
    if promised:
        return [f"the message promises {', '.join(promised)}, which your own messages don't"]
    return []


# ── all checks for one AI answer ────────────────────────────────────────────

# a listing is the seller talking about the phone, never about the notes or who wrote them (14 Oct: "the reseller
# describes it as in like-new condition", "No battery health figure is given")
META_TALK = re.compile(r"\b(?:re)?sellers?\b|\b(?:the|your|my)\s+notes?\b|\bnotes?\s+(?:says?|describes?|mentions?|states?|"
                       r"gives?)\b|\bdescribed\s+as\b|\bdescribes?\s+(?:it|the|this)\b|\bnot\s+(?:stated|mentioned|specified)\b|"
                       r"\bno\s+(?:\w+\s+){0,3}(?:figure|percentage|reading|info|information|details?)\s+(?:is\s+|was\s+)?"
                       r"(?:given|stated|available|provided)\b", re.IGNORECASE)


def check_no_meta_talk(what, text):
    """The listing speaks for the phone, as its seller: never about the notes, the reseller or what isn't said."""
    found = META_TALK.search(text or "")
    return [f"{what} talks about the notes, not the phone: \"{found.group().strip()}\""] if found else []


def check_listing_answer(answer, item, catalogue, conditions, sources, notes):
    """Every check on the AI's part of a listing. An empty list means it passed.

    answer: what the AI sent back. It has a colour only when code couldn't
        fill one, and that colour may be "unsure": then the colour is for you
    item: what code already filled (fill_from_catalogue)
    catalogue: the models (load_catalogue); conditions: eBay's list for the category
    sources: sources_text(...) for this item; notes: your notes on their own
    """
    required = ANSWER_FIELDS - {"colour"} if item.get("colour") else ANSWER_FIELDS
    if not isinstance(answer, dict) or not required <= set(answer) <= ANSWER_FIELDS:
        return ["the answer isn't in the agreed shape"]
    model = next(m for m in catalogue if m["id"] == item["model_id"])
    aliases = model.get("colour_aliases", {})

    problems = []
    colour = item.get("colour")
    if "colour" in answer and str(answer["colour"]).strip().lower() != UNSURE:
        problems += check_allowed("colour", answer["colour"], model["colours"], aliases)
        picked = canonical(answer["colour"], model["colours"], aliases)
        if colour and picked and picked != colour:
            problems.append(f"colour {picked!r} disagrees with the listing text ({colour!r})")
        colour = colour or picked
    problems += check_allowed("condition", answer["condition_id"], [c["id"] for c in conditions])

    condition = canonical(answer["condition_id"], [c["id"] for c in conditions])
    faulty = has_fault(notes or "")
    if condition and condition != FOR_PARTS and faulty:
        problems.append("your notes mention a fault, so the condition must be For parts or not working")
    if condition == FOR_PARTS and not faulty:
        problems.append("condition is For parts or not working, but your notes don't mention a fault")
    if condition in NEW_CONDITIONS:
        if condition not in new_conditions_allowed(notes or ""):
            problems.append(NEW_PROBLEMS[condition])
        if isinstance(answer["condition_note"], str) and answer["condition_note"].strip():
            problems.append("condition_note must be empty on a new item: eBay ignores it")

    # once checked, the chosen colour is a fact the description may repeat
    sources = f"{sources} {colour or ''}"
    for what, limit, required in (("condition_note", MAX_CONDITION_NOTE, False),
                                  ("description", MAX_DESCRIPTION, True)):
        text = answer[what]
        length_problems = check_length(what, text, limit, required)
        problems += length_problems
        if not length_problems:
            problems += check_no_invented_numbers(what, text, sources)
            problems += check_no_invented_percentages(what, text, notes or "", sources, item.get("battery"))
            problems += check_no_invented_promises(what, text, sources, notes or "", item.get("battery"))
            problems += check_mark_places(what, text, notes or "")
            problems += check_battery_praise(what, text, notes or "")
            problems += check_matches_item(what, text, item, catalogue, colour, sources)
            problems += check_no_prices(what, text)
            problems += check_no_off_platform(what, text)
            problems += check_no_contact_details(what, text)
            problems += check_no_meta_talk(what, text)
    return problems


def pence_or_none(amount):
    """to_pence, or None for an amount that can't be a real price."""
    try:
        return to_pence(amount)
    except ValueError:
        return None


def prices_in(text):
    """Every price the text states, in pence: "£170", "170 quid", "take 170"."""
    return {pence_or_none(amount) for pattern in PRICES for amount in pattern.findall(text)}


def offer_stated(sentence):
    """Whether a sentence says the offer as yours: "I'll pay £360", "I can do £360"."""
    return bool(re.search(r"\b(?:i'?ll|i will|i can|i could|happy to|i'?d|i would)\s+(?:\w+ly\s+)?(?:pay|do|offer|give)\b",
                          sentence, re.IGNORECASE))


def offer_asked(message, offer):
    """True if the offer is in a question: "would you take £210?", and also
    "would you be happy with £210?", where "with" starts a new clause of the
    same question, or "£210 if you take the listing down?", a question with
    no question word. A question tagged on ("..., is that ok?") asks nothing."""
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", message.strip()):
        asking = False
        for clause, asks in clauses(sentence):
            asking = asking or asks
            if asking and offer in prices_in(clause):
                return True
        bare = TAG_QUESTION.sub(".", SIGN_OFF.sub("", sentence)).rstrip()
        if bare.endswith("?") and offer in prices_in(bare) and not offer_stated(bare):
            return True
    return False


# ...unless the sentence names a way of paying off the site: "pay now, send me your sort code" (26 Sep red team)
BANK_WORDS = re.compile(r"\bbank\b|\bsort code\b|\baccount (?:number|details)\b|\bpay ?pal\b|\bbacs\b|\btransfer\b|"
                        r"\bemail\b|\bdetails\b|\brevolut\b|\bmonzo\b", re.IGNORECASE)


def sentence_of(text, match):
    """The sentence a match sits in."""
    before, after = clause_around(text, match.start(), match.end())
    return before + match.group() + after


# paying straight away, the one way of paying first that's fine where it's bought through the site ("I'll pay the full
# £400 straight away" too)
PAY_NOW = re.compile(rf"pay(?:ing)? (?:you |it )?(?:{PAID_PRICE})?(?:right )?(?:now|straight ?away|right away|asap|"
                     rf"immediately|instantly)$", re.IGNORECASE)


def check_message_manner(message, greeting=None, usual=True, short=False, must=(), cash=True, emoji=False,
                         praise=False, locks=False, no_cash=False, no_collecting="", pay_first=True, title="",
                         short_extra=0):
    """AlertFlip's rules for a message to a seller (its seller-message
    function), on top of check_message's: no asking about iCloud or locks
    (that's for once the seller replies), no paying before collecting, no
    compliments about the item, no talk of a conversation there hasn't been
    ("as you've said": it's the first message), and a usual message asks at
    most two questions (a longer one asks what the listing leaves open).
    "I'll pay" twice is fine (decided 14 Sep).

    greeting: "Hi" when it must open with that, True for any greeting (yours),
    None when your messages don't open with one. short: AlertFlip's 250
    characters, for a usual message before you have past messages. must: how
    it has to say you'll buy ("collecting", "cash": on Facebook and Gumtree
    with no past messages). cash: False on eBay and Vinted, where you pay
    through the site. emoji: whether your messages use them. praise: whether
    this draft gives the listing's good condition as its reason. locks: the
    listing talks about iCloud or locks, so the message may say what it says.
    no_cash: the listing says no cash (says_no_cash), so the message mustn't
    offer it; True, or the reason in words. Cash is refused asked as well as
    said ("would you prefer cash?"). no_collecting: why the listing won't be
    collected ("on eBay and Vinted you pay through the site and it's
    posted"), so the message mustn't talk of collecting, asked or said; ""
    when it may. pay_first: False on eBay and Vinted, where paying straight
    away is how it's bought: there only sending money, a deposit or paying
    upfront is refused. title: the listing's title, whose words aren't
    talk of collecting or cash ("the Pokemon Collection box").
    """
    if not isinstance(message, str) or not message.strip():
        return []  # check_message reports that
    message = re.sub(r"[’‘ʼ]", "'", message.strip())
    problems = []
    first = re.match(r"[A-Za-z]+", message)
    if isinstance(greeting, str) and not re.match(rf"{re.escape(greeting)}\b", message, re.IGNORECASE):
        problems.append(f"the message doesn't open with \"{greeting}\"")
    elif greeting is True and not (first and first.group().lower() in GREETING_WORDS):
        problems.append("the message doesn't open with a greeting")
    if short and len(message) > SHORT_MESSAGE + short_extra:  # short_extra: what code added after the AI's words
        problems.append(f"the message is {len(message)} characters: a usual one is under {SHORT_MESSAGE + short_extra}")
    asked = questions_asked(message)
    if usual and asked > MAX_QUESTIONS:
        problems.append(f"the message asks {asked} questions: at most {MAX_QUESTIONS}")
    for pattern, what in (*(() if locks else ((LOCK_TALK, "asks about iCloud or locks, which is for once the "
                                                          "seller replies"),)),
                          (PAY_FIRST, "offers to pay before collecting"),
                          (PRIOR_TALK, "says the seller said or agreed something, but it's the first message"),
                          *(() if praise else ((COMPLIMENT, "compliments the item"),))):
        # on eBay and Vinted "can pay straight away" is how it's bought; sending money, a deposit, PayPal isn't
        found = next((m for m in pattern.finditer(message) if pay_first or pattern is not PAY_FIRST
                      or not PAY_NOW.match(m.group()) or BANK_WORDS.search(sentence_of(message, m))), None)
        if found:
            problems.append(f"the message {what}: \"{found.group()}\"")
    if not emoji and EMOJI.search(message):
        problems.append("the message has an emoji, which your messages don't use")
    missing = [habit for habit in must if habit not in promised_in(message)]
    if missing:
        problems.append(f"the message doesn't say {' and '.join(SAYS[m] for m in missing)}: on Facebook and Gumtree it does")
    # cash asked as well as said: "Can you collect, or would you prefer cash?" offers it too ("the Johnny Cash LP" doesn't)
    cash_said = "cash" in promised_in(message) or talks_of(CASH_TALK, message, title)
    if not cash and cash_said:
        problems.append("the message offers cash, but on eBay and Vinted you pay through the site")
    elif no_cash and cash_said:
        problems.append(f"the message offers cash, but {no_cash if isinstance(no_cash, str) else 'the listing says no cash'}")
    if no_collecting and ("collecting" in promised_in(message) or talks_of(COLLECT_TALK, message, title)):
        problems.append(f"the message talks of collecting, but {no_collecting}")
    return problems


def questions_asked(message):
    """How many sentences of a message ask something: a question mark, or
    two ("available??"), counts once, and a question asked without one
    counts too ("Hi is it still available", "Are you about Saturday")."""
    return sum(1 for sentence in re.split(r"(?<=[.!?])\s+|\n+", message.strip()) if sentence.strip() and
               (ends_asking(sentence) or QUESTION_START.match(sentence.strip()) and not sentence.rstrip().endswith((".", "!"))))


def check_message(message, offer, sources, asking=None, kind="lower", min_words=0, ebay=True, own=()):
    """Every check on a drafted message to a seller. offer and asking are in pence.

    The only price it may state is the offer. The asking price may come up as
    a reference ("it's listed at £200", "the asking price is £200"); that's
    taken out before the prices are read, so a second "£200" can't hide behind
    it, and the asking price can't come back as a bare "200". An offer of
    "more" than asking is said, never asked: "would you take £210?" reads like
    asking for a discount. A longer message has a minimum number of words, and
    no message makes up a story about you. What it says comes with the item
    (box, charger, unlocked...) must be in the listing; asking is fine ("does
    it come with the box?"). flip.offers checks what it says about condition.
    own: your own sentences, whose numbers are yours (check_no_invented_numbers).
    """
    problems = check_length("message", message, MAX_MESSAGE)
    if problems:
        return problems
    if len(message.split()) < min_words:
        problems.append(f"the message is {len(message.split())} words, but a longer one needs at least {min_words}")
    message = re.sub(r"[’‘ʼ]", "'", message)
    rest = message
    if asking is not None:
        # an offer verb counts only in the same sentence: "Would you take £170? It's £200 on the listing"
        refs = [m for m in ASKING_MENTION.finditer(message)
                if not set(re.split(r"[.?!]", message[:m.start()])[-1].lower().split()[-3:]) & OFFER_VERBS]
        said = [pence_or_none(m.group("a") or m.group("b") or m.group("c")) for m in refs]
        wrong = [amount for amount in said if amount != asking]
        if wrong:  # "I know you're asking £170" on a £200 listing
            problems.append(f"the message gives the asking price as {pounds(wrong[0]) if wrong[0] else 'a price'}, "
                            f"but it's {pounds(asking)}")
        elif refs:
            for m in reversed(refs):
                rest = rest[:m.start()] + " " + rest[m.end():]
    if prices_in(rest) != {offer}:
        problems.append(f"the message must offer exactly {pounds(offer)} and no other price")
    elif asking is not None and asking != offer and f"{(Decimal(asking) / 100).normalize():f}" in numbers_in(rest):
        problems.append("the message mentions the asking price again, as if offering it")
    if kind == "more" and offer_asked(message, offer):
        problems.append("an offer over the asking price must be said, not asked: "
                        "\"would you take\" reads like asking for a discount")
    second = SECOND_OFFER.search(message)
    if kind == "lower" and second and not NOT_PROMISED.search(message[:second.start()]):
        said = re.split(r"(?<=[.!?])\s", message[second.start():])[0]
        problems.append(f"a lower offer can't offer more as well: \"{said.strip()}\"")
    problems += check_no_invented_numbers("message", message, f"{sources} {pounds(offer)}", own)
    problems += check_no_off_platform("message", message, ebay)
    problems += check_no_contact_details("message", message)
    problems += check_no_story("message", message, sources)
    problems += check_message_claims(message, sources)
    return problems
