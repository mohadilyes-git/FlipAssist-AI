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
PAY_FIRST = re.compile(
    r"\b(?:deposit|up[- ]?front|(?<!thanks )(?<!thank you )in advance|before (?:i |we )?(?:collect|collection|meet|see)\w*)\b"
    r"|\bpay(?:ing)? (?:you |it )?(?:now|first(?! thing)|straight ?away|right away|asap)\b"
    r"(?! (?:on|at|when|in person|in cash on|once))"
    r"|\b(?:transfer|bacs|paypal|send|sending|ping)\s+(?:it |you |over |the )?(?:money |payment |cash |funds |it )?"
    r"(?:now|today|tonight|over|first|asap|straight ?away|right away|in advance)\b"
    r"|\bsend (?:you )?(?:the )?(?:money|payment)\b", re.IGNORECASE)
COMPLIMENT = re.compile(
    r"\blooks (?:really |very |so |absolutely |super )?(?:nice|lovely|great|perfect|brilliant|amazing|mint|immaculate|"
    r"gorgeous|stunning|beautiful|cracking|smart|clean|class)\b(?! (?:for|to) me)|\bwell (?:looked|cared)\b"
    r"|\b(?:nice|lovely|cracking|beautiful|gorgeous|stunning|smart|cool|great|brilliant|amazing|mint) (?:looking )?"
    r"(?:console|phone|item|one|bit of kit|piece|laptop|watch|bike|set|headphones|earbuds|camera|tv|machine|unit|device|"
    r"tablet|ipad|iphone|kit)\b|(?<!not in )(?<!not )\bgreat condition\b|\bbeautiful\b|\bstunning\b|\bgorgeous\b",
    re.IGNORECASE)
# a listing that won't take cash: then no message offers it (the user, 14 Sep: "mention cash unless the listing
# description says no cash")
NO_CASH = re.compile(r"\bno cash(?: payments?)?\b|\bcash (?:is )?not (?:accepted|taken)\b|\bnot (?:accepting|taking) cash\b|"
                     r"\b(?:bank transfer|transfer|pay ?pal|card|bacs)(?: payments?)? only\b|"
                     r"\bonly (?:accept(?:ing)? )?(?:bank transfer|transfer|pay ?pal|card|bacs)\b", re.IGNORECASE)
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
# why an offer over asking is made: so they'll hold it for you, or take the listing down
HOLD = re.compile(r"\b(?:hold|reserve|keep it for|put it aside|set it aside|take (?:it|the (?:ad|advert|listing|post)) "
                  r"down|off the market|end (?:the |your )?listing)\b", re.IGNORECASE)
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
# ...unless it ends first (denied_by): an exception ("no marks APART from a scratch", "no cracks ONLY light
# scratches"), a thing of its own the "no" was about ("no OFFERS small crack", "no BOX just a scratch"), or a
# new statement ("no box, screen HAS a crack", though not "doesn't HAVE any scratches")
NEGATION_ENDS = {"only", "just", "apart", "except", "bar", "other", "but", "though", "although", "however", "selling",
                 "sold"}
NEW_STATEMENT = {"has", "have", "got", "is", "are", "was"}
NEGATED_THINGS = {"offers", "offer", "swaps", "swap", "returns", "refunds", "timewasters", "time", "box", "charger",
                  "cable", "plug", "case", "lowballers", "messers", "scams", "pets", "smoke", "smoking"}
# a label and its answer, as sellers list them: "Faults: none", "Scratches – no", "Any damage? Nope",
# "Dents: not that I know of", "Scratches ❌", "0 dents" (answered)
NO_ANSWER = r"(?:no|none|nope|nil|n/?a|zero|0|nothing|never|missing|not included|not that i(?:'?m| am)? (?:know|aware) of)"
ANSWERS = [
    (re.compile(rf"\b(?:any\s+)?([a-z]+(?:\s+(?:or|and|&)\s+[a-z]+)?(?:\s+[a-z]+)?)\s*(?:[:=?]|\s[-–—])\s*{NO_ANSWER}"
                r"\s*(?=[,.;!\n)]|$)", re.IGNORECASE), r"no \1"),
    (re.compile(r"\b([a-z]+)[ \t]*[❌✖✗]", re.IGNORECASE), r"no \1"),  # on its own line: "❌ Small crack" is a flaw
    (re.compile(r"(?<![\w.£$€])0\s+(?=[a-z])", re.IGNORECASE), "no "),
]
# what has a claim word but isn't a flaw or a claim: a guard against one, a part's name, a cover
NOT_A_FLAW = re.compile(
    r"\b(?:scratch[- ]?resist\w*|anti[- ]?scratch|(?:to )?prevent(?:s|ing)? (?:any )?(?:scratch\w*|damage)|"
    r"protect\w* (?:it )?(?:from|against) (?:any )?(?:scratch\w*|damage|drops?)|water damage indicators?(?: \w+)?|"
    r"accidental damage(?: cover| protection| insurance)?|damage (?:cover|protection|insurance)|"
    r"(?:intel|apple|amd|m[1-4](?: pro| max)?|a\d{1,2}(?: bionic| pro)?|bionic|snapdragon|exynos|tensor|kirin|"
    r"mediatek|qualcomm) chips?|wear ?os|(?:hardly|barely) (?:a|an|any) (?:\w+ )?(?:mark|scratch|scuff|dent|chip)\w*)\b",
    re.IGNORECASE)


def denied_by(lead, negations=NEGATIONS):
    """Whether the words leading up to a claim word deny it: a negation word
    among them that nothing ends first (NEGATION_ENDS, NEGATED_THINGS, or a
    verb with a word of its own before it: NEW_STATEMENT). "doesn t have any"
    denies; "no box screen has small" and "no cracks only light" don't."""
    for n, word in enumerate(lead):
        if word not in negations:
            continue
        rest = lead[n + 1:]
        ends = set(rest) & (NEGATION_ENDS | NEGATED_THINGS)
        if "other" in ends and not any(w == "other" and after == "than" for w, after in zip(rest, rest[1:])):
            ends.discard("other")  # "no OTHER marks" denies more of them; "no marks OTHER THAN a scratch" excepts one
        ended = ends or any(verb in NEW_STATEMENT and set(rest[:k]) - {"t"} for k, verb in enumerate(rest))
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
FAULTS = re.compile(r"\b(?:not working|broken|drift|drifts|drifting|faulty|fault|faults|glitch\w*|for parts|spares|"
                    r"dead pixels?|(?:is|totally|completely|went|now) dead|dead (?:battery|phone|console|unit|on arrival)|"
                    r"battery (?:is )?dead|"
                    r"won t (?:turn on|switch on|charge|connect|pair|boot)|doesn t (?:turn on|charge|connect|pair)|"
                    r"not charging|no sound|no power|"
                    # a part with an issue, and a fault that comes and goes: "one issue with the screen it
                    # turns on and off sometimes", "keeps restarting", "cuts out" (but not "issues with collection")
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
                          r"transfer (?:you )?the money)\b", re.IGNORECASE)

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
# words that say something is wrong with an item, whatever the words around them: a flaw the AI reads must
# have one (flip.reader), and a message may use one only if the listing does (flip.offers.check_reasons)
PROBLEM = re.compile(
    r"\b(?:crack\w*|scratch\w*|scuff\w*|dent\w*|chip|chips|chipped|marks?|marked|broke|broken|smash\w*|shatter\w*|"
    r"damage\w*|fault\w*|dead|burn|burns|burnt|burned|burn-in|dot|dots|spots?|lines?|pixels?|stiff|loose|wobbl\w*|"
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
    r"no (?:sound|power|picture|signal|display|image|wifi|charge|charging|service|audio|video|bluetooth)|"
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
                          r"couldn'?t)\s+(?:\w+\s+){0,3}$", re.IGNORECASE)
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
CLAUSES = re.compile(r"[,;:]|\b(?:as|because|since|given|considering|seeing|with|due|though|although|now that|"
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
                parts = sorted(CONDITION_PARTS & set(part_words[max(0, i - 4):i + 2]))
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
            negated = denied_by(part_words[max(0, i - 5):i]) or bool(NEGATED_AFTER & set(after[:2])) \
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


def check_no_invented_numbers(what, text, sources):
    extra = numbers_in(text) - numbers_in(sources)
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
            if said not in backing or (promise == "working" and said == "yes" and faulty):
                (unbacked_condition if condition else unbacked).append(promise if said == "yes" else f"no {promise}")
    problems = []
    if unbacked:
        problems.append(f"{what} says things your inputs don't: {', '.join(unbacked)}")
    if unbacked_condition:
        problems.append(f"{what} says things about the condition your notes don't: {', '.join(unbacked_condition)}")
    return problems


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
    for part in re.split(r"[,.;:!?\n()]|\b(?:but|while|whereas|except)\b", text.lower()):
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


def check_message_manner(message, greeting=None, usual=True, short=False, must=(), cash=True, emoji=False,
                         praise=False, locks=False, no_cash=False):
    """AlertFlip's rules for a message to a seller (its seller-message
    function), on top of check_message's: no asking about iCloud or locks
    (that's for once the seller replies), no paying before collecting, no
    compliments about the item, no talk of a conversation there hasn't been
    ("as you've said": it's the first message), and a usual message asks at
    most two questions (a longer one asks what the listing leaves open).
    "I'll pay" twice is fine (the user, 14 Sep).

    greeting: "Hi" when it must open with that, True for any greeting (yours),
    None when your messages don't open with one. short: AlertFlip's 250
    characters, for a usual message before you have past messages. must: how
    it has to say you'll buy ("collecting", "cash": on Facebook and Gumtree
    with no past messages). cash: False on eBay and Vinted, where you pay
    through the site. emoji: whether your messages use them. praise: whether
    this draft gives the listing's good condition as its reason. locks: the
    listing talks about iCloud or locks, so the message may say what it says.
    no_cash: the listing says no cash (NO_CASH), so the message mustn't offer it.
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
    if short and len(message) > SHORT_MESSAGE:
        problems.append(f"the message is {len(message)} characters: a usual one is under {SHORT_MESSAGE}")
    asked = questions_asked(message)
    if usual and asked > MAX_QUESTIONS:
        problems.append(f"the message asks {asked} questions: at most {MAX_QUESTIONS}")
    for pattern, what in (*(() if locks else ((LOCK_TALK, "asks about iCloud or locks, which is for once the "
                                                          "seller replies"),)),
                          (PAY_FIRST, "offers to pay before collecting"),
                          (PRIOR_TALK, "says the seller said or agreed something, but it's the first message"),
                          *(() if praise else ((COMPLIMENT, "compliments the item"),))):
        found = pattern.search(message)
        if found:
            problems.append(f"the message {what}: \"{found.group()}\"")
    if not emoji and EMOJI.search(message):
        problems.append("the message has an emoji, which your messages don't use")
    missing = [habit for habit in must if habit not in promised_in(message)]
    if missing:
        problems.append(f"the message doesn't say {' and '.join(SAYS[m] for m in missing)}: on Facebook and Gumtree it does")
    if not cash and "cash" in promised_in(message):  # "the Johnny Cash LP" offers none
        problems.append("the message offers cash, but on eBay and Vinted you pay through the site")
    elif no_cash and "cash" in promised_in(message):
        problems.append("the message offers cash, but the listing says no cash")
    return problems


def questions_asked(message):
    """How many sentences of a message ask something: a question mark, or
    two ("available??"), counts once, and a question asked without one
    counts too ("Hi is it still available", "Are you about Saturday")."""
    return sum(1 for sentence in re.split(r"(?<=[.!?])\s+|\n+", message.strip()) if sentence.strip() and
               (ends_asking(sentence) or QUESTION_START.match(sentence.strip()) and not sentence.rstrip().endswith((".", "!"))))


def check_message(message, offer, sources, asking=None, kind="lower", min_words=0, ebay=True):
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
    problems += check_no_invented_numbers("message", message, f"{sources} {pounds(offer)}")
    problems += check_no_off_platform("message", message, ebay)
    problems += check_no_contact_details("message", message)
    problems += check_no_story("message", message, sources)
    problems += check_message_claims(message, sources)
    return problems
