"""The safety checks. Every AI answer goes through these before you see it.

A failed check means: throw the answer away and let the paid model try; if
that fails too, the item is marked "needs you". Each check is plain code, so it
gives the same result every time and costs nothing to run. The checks can
catch an answer that's broken or made up; they can't tell whether a believable
answer is true. That's why you approve every draft.
"""

import re
from decimal import Decimal

from flip.catalogue import (COMMON_COLOURS, PLUS_MEANS_AND, colours_named, find_phrase, item_colour_mentioned,
                            options_named, sizes_in, words)
from flip.money import pounds, to_pence

MAX_CONDITION_NOTE = 1000  # eBay's limit for the condition description
MAX_DESCRIPTION = 1500     # our own limit: short listings read better and cost fewer tokens
MAX_MESSAGE = 500
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
    "mark": ["mark", "marking", "wear"],
}
# each kind of mark is its own claim: "no dents" doesn't back "no scratches".
# "mark" is the general word: your "no marks" backs a draft's "no scratches"
MARKS = {"scratch", "scuff", "dent", "crack", "chip", "mark"}
# a draft's "excellent" is backed by your "excellent" or "flawless"; its
# "flawless" only by your "flawless"
LEVELS = {"excellent": ["excellent", "flawless"], "flawless": ["flawless"]}
# "chip" after one of these is the processor, not damage: "A15 Bionic chip"
PROCESSOR_WORDS = {"bionic", "pro", "fusion", "tensor", "exynos", "snapdragon", "gen", "processor", "silicon"}
KEYWORDS = {word: promise for promise, keywords in {**PROMISES, **CONDITION_PROMISES}.items() for word in keywords}
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
HARMLESS = ["perfect for", "perfect gift", "new owner", "new home", "since new", "from new",
            "works with", "working with", "compatible with", "games console", "games consoles", "game console",
            "stand out", "stands out"]
# a claim word with one of these shortly before it, in the same part of the
# sentence, is a "no": "no box", "doesn't come with a charger", "can't find the box"
NEGATIONS = {"no", "not", "without", "missing", "never", "none", "nor", "isn", "doesn", "don", "hasn", "wasn",
             "lost", "t"}
# ...and so is one of these shortly after it: "charger MISSING", "box LOST"
NEGATED_AFTER = {"missing", "lost", "none", "excluded"}
# ...or "not" and one of these: "charger NOT INCLUDED"
INCLUDED = {"included", "supplied", "provided", "present"}
# words that join a list a "no" after it covers: "box AND charger not included"
LIST_WORDS = {"and", "or", "nor", "the", "original", "its", "a"}
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
FAULTS = re.compile(r"\b(?:not working|broken|drift|drifts|drifting|faulty|fault|faults|glitch\w*|for parts|spares|"
                    r"dead pixels?|(?:is|totally|completely|went|now) dead|dead (?:battery|phone|console|unit|on arrival)|"
                    r"battery (?:is )?dead|"
                    r"won t (?:turn on|switch on|charge|connect|pair|boot)|doesn t (?:turn on|charge|connect|pair)|"
                    r"not charging|no sound|no power)\b")
NOT_A_FAULT = re.compile(r"\b(?:no|not|never|without)\s+(?:been\s+)?(?:any\s+)?(?:\w+\s+)?"
                         r"(?:broken|drift\w*|faults?|faulty|glitch\w*|dead pixels?|issues?|problems?)\b"
                         r"|\bnot\s+(?:for\s+)?(?:spares|repairs|parts)\b")
FOR_PARTS = "7000"
PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s?(?:%|per ?cent\b)", re.IGNORECASE)
# a battery health written without a % sign: "battery health 86"
BATTERY_FIGURE = re.compile(r"\b(?:battery|health|capacity)\b(?:\s+[a-z]+){0,2}\s+(\d{2,3}(?:\.\d+)?)\b"
                            r"(?!\s?(?:gb|tb|mah|hours?|hrs?|mins?|minutes?|days?))", re.IGNORECASE)

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
OFF_PLATFORM = re.compile(r"\b(?:outside (?:of )?ebay|off ebay|end (?:the |your )?listing|friends (?:and|&) family|"
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
    r"bubbl\w*|weak|noisy|noise|smell\w*|locked|blacklisted|bad|poor|cracking|"
    r"(?:isn'?t|is not|not) (?:perfect|great|good|the best|mint|working properly)|"
    r"no (?:sound|power|picture|signal|display|image|wifi|charge|charging|service|audio|video|bluetooth))\b",
    re.IGNORECASE)

# how you'll buy: a message may promise it only the way your own messages do (check_no_unasked_promises).
# Collecting is something you'll do ("can collect today", "come and get it"), not a word in a name
# ("Collector's Edition", "your games collection")
PROMISES_ABOUT_YOU = {
    "collecting": re.compile(
        r"\b(?:(?:can|could|will|i'?ll|happy to|able to|ready to|free to|want to|like to|gladly)\s+"
        r"(?:come\s+(?:and\s+)?)?(?:collect|pick)\w*"
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
    r"|meet (?:you |me )?(?:in the )?middle|split the difference"
    r"|if not,? i(?:'d| could| can| would| will|'ll)?\s+(?:do|pay|go|offer|take|meet|stretch|split)"
    r"|if not,? (?:would you (?:take|do|accept|consider)|how about|what about))\b", re.IGNORECASE)
# "can't collect" isn't a promise
NOT_PROMISED = re.compile(r"\b(?:can'?t|cannot|can not|won'?t|wouldn'?t|shouldn'?t|unable to|not|no|never|"
                          r"couldn'?t)\s+(?:\w+\s+){0,3}$", re.IGNORECASE)
# a question tagged onto a promise doesn't make it a question: "I can collect today, does that work?"
TAG_QUESTION = re.compile(r",?\s*(?:does that (?:work|suit(?: you)?|sound (?:ok|okay|good|alright))|"
                          r"is that (?:ok|okay|alright|fine|good)|if that'?s (?:ok|okay|alright|fine)|"
                          r"would that (?:work|be (?:ok|okay|alright|fine))|ok|okay|alright|yeah)"
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


def promises_in(text):
    """Each claim the text makes, and whether it says yes or no to it.

    "Boxed, no charger" -> {"box": {"yes"}, "charger": {"no"}}
    "box: no", "charger not included" and "free from scratches" are all a no.
    A condition word next to a part is about that part only: "screen perfect"
    -> {"flawless screen": {"yes"}}, not a flawless item.
    """
    found = {}
    text = text.lower()
    # "box: no", "charger - none" -> "no box", "no charger"; "box: yes" -> "box"
    text = re.sub(r"\b([a-z]+(?: [a-z]+)?)\s*[:=\-–—]\s*(?:no|none|nope|missing|not included)\s*(?=[,.;\n]|$)",
                  r"no \1", text)
    text = re.sub(r"\b([a-z]+(?: [a-z]+)?)\s*[:=\-–—]\s*(?:yes|yep|included)\s*(?=[,.;\n]|$)", r"\1", text)
    # read one part of a sentence at a time, so "no scratches, comes with box"
    # or "no scratches and comes with box" doesn't turn into "no box"
    for part in re.split(r"[,.;:!?\n()]|\bbut\b|\band\b(?= (?:comes|has|includes|included|with|is|boxed))", text):
        part = " " + " ".join(words(part)) + " "
        for phrase, same in SAME_AS:
            part = part.replace(f" {phrase} ", f" {same} ")
        for phrase in HARMLESS:
            part = part.replace(f" {phrase} ", " ")
        part_words = part.split()
        for i, word in enumerate(part_words):
            promise = KEYWORDS.get(singular(word))
            if not promise:
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
            # doesn / t / come / with / a, so "doesn" is 5 words before
            negated = bool(NEGATIONS & set(part_words[max(0, i - 5):i])) or bool(NEGATED_AFTER & set(after[:2])) \
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
    """Every battery-health style figure, written one way: "87%", "87 per cent"
    and "battery health 87" are all "87"."""
    found = PERCENT.findall(text) + BATTERY_FIGURE.findall(text)
    return {f"{Decimal(n).normalize():f}" for n in found}


def new_conditions_allowed(notes):
    """Which of New (1000) and Opened - never used (1500) your notes back.

    New: "sealed", "brand new", "unopened", with no sign it was used or opened
    ("in brand new condition", "used twice", "box opened" all rule it out).
    Opened - never used: "never used" or "unused" (or sealed), with no sign of use.
    """
    text = " ".join(words(notes))
    claims = promises_in(notes)
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


def check_no_invented_percentages(what, text, notes, sources):
    """A percentage, like battery health, is about this item's condition: it
    must come from your notes, not the seller's words, with or without the %
    sign. (One that isn't in any input at all is already reported by the
    numbers check.)"""
    extra = (condition_figures(text) - condition_figures(notes)) & numbers_in(sources)
    if extra:
        return [f"{what} has a percentage your notes don't: {', '.join(f'{p}%' for p in sorted(extra))}"]
    return []


def check_no_invented_promises(what, text, sources, notes):
    """Every claim in the text must be backed, with the same yes or no.
    Condition claims only by your notes. Anything else by your notes if they
    mention it ("no box" beats the seller's "boxed"), otherwise by any input.
    And nothing is "working" when your notes mention a fault."""
    from_inputs, from_notes = promises_in(sources), promises_in(notes)
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


def check_no_off_platform(what, text):
    """Nothing about paying or dealing outside the platform: bank transfer,
    PayPal friends and family, "outside eBay", ending the listing early."""
    if OFF_PLATFORM.search(text):
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
    listed = promises_in(sources)
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
            if any(not NOT_PROMISED.search(sentence[:m.start()]) for m in pattern.finditer(sentence)):
                found.add(habit)
    return found


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
            problems += check_no_invented_percentages(what, text, notes or "", sources)
            problems += check_no_invented_promises(what, text, sources, notes or "")
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


def offer_asked(message, offer):
    """True if the offer is in a question: "would you take £210?", and also
    "would you be happy with £210?", where "with" starts a new clause of the
    same question."""
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", message.strip()):
        asking = False
        for clause, asks in clauses(sentence):
            asking = asking or asks
            if asking and offer in prices_in(clause):
                return True
    return False


def check_message(message, offer, sources, asking=None, kind="lower", min_words=0):
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
    problems += check_no_off_platform("message", message)
    problems += check_no_contact_details("message", message)
    problems += check_no_story("message", message, sources)
    problems += check_message_claims(message, sources)
    return problems
