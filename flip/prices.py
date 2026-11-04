"""What a listing would sell for in the UK, from the same prices API as the AlertFlip app (4 Oct 2026).

The prices API (AlertFlip's Supabase function "prices") keeps recent UK sales of
iPhones, Samsung phones and MacBooks, sorted by Claude Haiku 5.5 into model, storage, a MacBook's RAM, condition and
flaws. Given a listing's title it works out the model (Claude reads the title), and it cuts the clean price once for
each kind of flaw ("damage", "fault"...), never under the for-parts price. FlipAssist asks it as a server, with the key
in .env:
  PRICES_URL  the function's address (https://<project>.supabase.co/functions/v1/prices)
  PRICES_KEY  the PRICES_CLIENT_KEY secret it checks (sent as x-prices-key)

What FlipAssist sends, after the 4 Oct review (each one fixes a wrong price the API's own handling gave):
- kinds, sorted here (kinds_of): the API's own sorter takes the first rule that matches a whole sentence and reads no
  "no" or "not", so "small scratch, no repairs" was priced for parts and "cracked screen and Face ID not working" lost
  its fault. Here each clause is judged by the reader's own denial check (flip.reader.judge) and every kind counts.
  The 6 Oct recheck: what the judge has no word for ("rear camera is blurry", "grade C") is judged with one in its
  place, and the title is read as what's sold ("iPhone 12 Pro repairs", "iPhone 12 dead": for parts). Its second
  check: "untested for parts" and a repair that failed are still for parts, a repair done isn't (in a title too:
  "had screen repair"), a torch that won't come on is a fault, and a line of labels is read label by label
  ("Cracks: no Scratches: yes": wear).
- bucket "good" for a locked or for-parts listing: the API, left to read "for parts" from the title itself, looks for
  for-parts sales among clean ones and finds none (NO_SALES); as "good" with the kind "parts" it gives the for-parts
  price.
- the size from the description when the title has none (sizes_in): otherwise the API prices the size that sells most
  and says nothing. A spec list's labels ("Storage: 128GB\nRAM: 6GB") and "128 gig" are read; a memory card's, the
  graphics card's or another model's size isn't.
- strict: a title naming no one model ("iPhone 128GB") is refused rather than averaged over every iPhone.
The API's refusals are said in FlipAssist's words (REFUSED), its monthly cap ("paused until next month") as that, not
as a moment's wait.

Only iPhones, Samsung phones and MacBooks are asked about (MacBooks added 4 Oct), and never a case, a
charger, a box or a Samsung TV (kind_of): anything else would spend calls on a keyword search (the FlipAssist API's credits
and its rate limit) and price the wrong thing.
"""

import json
import os
import re
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path

from flip.severity import damage_cut, severity
from flip.checks import NEGATED_THINGS, NOT_A_FLAW, PROBLEM, denied_by, slipped
from flip.offers import battery_now, figures_joined
from flip.reader import (CLAUSE_WORDS, HOW_BAD, ITEM_OPENERS, MAX_BEFORE, MAX_FLAW, NEGATORS, OTHER_ITEM, judge,
                         parts_of, plain_words, problems_at, without_neutral_nots)

TIMEOUT = 30  # seconds: a title Claude hasn't read yet, or a sales check, takes a few
_seen = {}  # the request -> the answer: the same listing checked again isn't asked again

SKIPPED = "Estimates are for iPhones, Samsung phones and MacBooks only"
FLAWED_BATTERY = 80  # under this a battery is a flaw: the line the API's reader sorted the sales by

I, X = re.IGNORECASE, re.IGNORECASE | re.VERBOSE

# ── what's asked about: iPhones, Samsung phones and MacBooks, not what goes with them ─────────────────────────────

IPHONE = re.compile(r"\bi[\s-]?phone", I)  # "iPhone13", "iPhoneX", "i phone 12", "I-phone 13"
SAMSUNG = re.compile(r"\b(?:samsung|galaxy)", I)  # "GalaxyS23"
# a Samsung phone named without the brand ("S23 Ultra 256GB", "Z Flip 5"), when something says it's a phone
SAMSUNG_MODEL = re.compile(r"\b(?:s\s?(?:2[0-6]|1\d|[789])|z\s?(?:flip|fold)\s?\d|note\s?(?:[89]|1\d|20))"
                           r"(?:\s?(?:ultra|plus|fe|edge)\b|\+|\b)", I)
PHONE_WORDS = re.compile(r"\b(?:\d{2,4}\s?gb|[12]\s?tb|unlocked|ultra|plus|fe|edge|5g|smartphone|phone|mobile|"
                         r"sim[\s-]?free)\b", I)
MACBOOK = re.compile(r"\bmac[\s-]*book|\bmb[ap]\b", I)  # "MacBookPro16,1", "Mac Book Air", "Mac-Book", "MBP"
DEVICE = re.compile(rf"{IPHONE.pattern}|{SAMSUNG.pattern}|{MACBOOK.pattern}", I)
SIZE = re.compile(r"\b\d{2,4}\s?gb\b|\b[124]\s?tb\b", I)
ACCESSORY = re.compile(r"""\b(?:cases?|covers?|chargers?|charging\s(?:cable|lead|brick|block|dock)|cables?|leads?|
    adapters?|plugs?|(?:screen\s|lens\s|camera\s)?protectors?|tempered\sglass|sleeves?|skins?|stands?|docks?|straps?|
    keyboard\scovers?|stylus|replacement\s(?:screen|battery|parts?)|logic\s?board|motherboard|housing|digiti[sz]er|
    lcd|(?:screen|display)\sassembly|mount|holder|wallet|pouch|bag)\b""", X)
# what goes with the device when it's said to be included or fitted, with a word or two of its own and in a list:
# "charger included", "wallet case included", "Case & Screen Protector Included", "screen protector fitted since
# new", "included case" (6 Oct recheck: each refused a real phone, as only the one word before "included" went)
WITH_THINGS = (r"(?:cases?|chargers?|box|boxes|cables?|leads?|plugs?|protectors?|accessories|sleeves?|covers?|"
               r"earphones|headphones|earpods|stylus|pen|manual|disc|disk|adapters?)")
NOT_DEVICE_WORD = r"(?!(?:i[\s-]?phone|mac[\s-]*book|galaxy|samsung)\b)[a-z][a-z-]*\s"  # a word of its, not the device
INCLUDED = re.compile(rf"\b(?:(?:{NOT_DEVICE_WORD}){{0,2}}?{WITH_THINGS}\s?(?:,|&|and|\+|/)\s?)*"
                      rf"(?:{NOT_DEVICE_WORD}){{0,3}}?{WITH_THINGS}\s(?:included|inc|incl|fitted|applied)\b\.?"
                      rf"|\bincluded\s(?:an?\s|the\s|its\s)?{WITH_THINGS}\b", I)
# ...but a charger with its own cable or plug, named right after the device, is what's sold: "MacBook Pro charger and
# cable included", "iPhone 13 charger cable included" (6 Oct second check: each was priced as the device), not
# "MacBook Air M1, charger included" or "iPhone 12 charger and case included"
CHARGING = re.compile(r"(?:chargers?|cables?|leads?|plugs?|adapters?)", I)
SEPARATED = re.compile(r"(?:[,.;:(|/+&–—-]|\b(?:with|and|inc|incl|including|plus))\s*$", I)
# a MacBook's screen in inches: "MacBook Air 13 in case" is a 13-inch case, not a MacBook kept in one
INCHES = re.compile(r"\b(1[1-7](?:\.\d)?)[\s-]?(?:in|inch|inches)\b", I)
# not "/": "iPhone 13/14 case" is one thing. "in": "iPhone 11 in Otterbox case", "always in a case", "kept in case"
CONNECTOR = re.compile(r"\s(?:with|w/|inc\.?|incl\.?|including|plus|and|&|\+|comes\swith|bundle|in)\s|[,(|]\s?|\s-\s",
                       I)
FOR_DEVICE = re.compile(r"\b(?:for|fits?|compatible\swith|suitable\sfor|to\sfit)\s+(?:an?\s+|the\s+|apple\s+|"
                        r"samsung\s+)?(?:i[\s-]?phone|galaxy|samsung|mac[\s-]*book)", I)  # "Case for iPhone 13"
BOX_ONLY = re.compile(r"\b(?:box\sonly|empty\sbox|just\sthe\sbox|box\sand\s(?:manual|paperwork)\sonly)\b", I)
NOT_A_PHONE = re.compile(r"\b(?:tab|tablet|watch|buds|book\s?\d*|chromebook|tv|television|monitor|fridge|freezer|"
                         r"washing|washer|dryer|microwave|soundbar|projector|ssd|hdd|evo|qled|ring|fit\s?\d?|"
                         r"smart\s?tag|odyssey)\b", I)
# Samsung's The Frame TV, but not a phone's frame: a title naming a phone model ("Galaxy S21 Ultra cracked frame",
# "S20 FE bent frame", "Samsung A52 cracked frame") is the phone's
FRAME = re.compile(r"\bframe\b", I)
PHONE_MODEL = re.compile(rf"\bgalaxy\b|{SAMSUNG_MODEL.pattern}|\b[am]\s?\d{{2}}[a-z]?\b", I)


def without_extras(title):
    """The title without what it says comes with the device (INCLUDED), unless that's a charger's own cable or plug
    (CHARGING), and with a MacBook's "13 in" as "13-inch"."""
    if MACBOOK.search(title) and not IPHONE.search(title):
        title = INCHES.sub(r"\1-inch", title)

    def extra(m):
        things = re.findall(rf"\b{WITH_THINGS}\b", m.group(), I)
        charger = len(things) > 1 and all(CHARGING.fullmatch(thing) for thing in things) and \
            any(thing.lower().startswith("charger") for thing in things)
        return m.group() if charger and not SEPARATED.search(title[:m.start()]) else " "
    return INCLUDED.sub(extra, title)


def accessory(title):
    """Whether the title sells something for an iPhone, a Samsung or a MacBook rather than the device: "iPhone 13
    case", "Charger for MacBook", "iPhone 14 box only", "MacBook Pro charger and cable included". A storage size says
    it's the device ("iPhone 13 128GB with case"), as does anything after "with" ("MacBook Air M1 with charger")."""
    t = without_extras(title)
    for_it, device = FOR_DEVICE.search(t), DEVICE.search(t)
    if BOX_ONLY.search(t) or (for_it and device and device.start() > for_it.start()):
        return True  # the device it's for comes only after "for": "Case for iPhone 13", not "iPhone 12 swap for 13"
    if SIZE.search(t):
        return False
    return bool(ACCESSORY.search(CONNECTOR.split(t, maxsplit=1)[0]))


def kind_of(title):
    """"iphone", "samsung", "macbook" or None: what the prices API prices from its saved sales (and nothing that
    goes with one: a case, a charger, a box, a Galaxy Watch, a Samsung TV)."""
    title = title or ""
    if accessory(title):
        return None
    head = CONNECTOR.split(without_extras(title), maxsplit=1)[0]
    if IPHONE.search(title):
        return "iphone"
    if MACBOOK.search(title):
        return "macbook"
    if (SAMSUNG.search(title) or (SAMSUNG_MODEL.search(title) and PHONE_WORDS.search(title))) \
            and not NOT_A_PHONE.search(head) and not (FRAME.search(head) and not PHONE_MODEL.search(title)):
        return "samsung"
    return None


# ── each flaw's kind, as the API cuts for them ─────────────────────────────────────────────────────────────────────
# The API's kinds (index.ts CUTS): its sorter's rules, fixed after the 4 Oct review (every match counts, "unlocked
# to" isn't "locked to", "crackles" isn't a crack, "Find My is off" isn't a lock, more faults named). In this order: a
# later rule's match inside an earlier one's ("broken screen" is damage, not damage and a fault) doesn't count.
# The 6 Oct recheck added the ways UK sellers write each kind that the rules missed ("EE locked", "its dead", "won't
# come on", "screen is broke", "battery says Service", "volume button is stuck"), their slips ("craked screen", "face id
# dosent work") and the words that only look like one ("dead mint", "went to Apple for repair last year"). Its second
# check put back what those broke: "untested for parts" and a repair that failed are still for parts, a torch that
# won't come on is a fault, "Cracks: no Scratches: yes" is wear.

NETWORKS = (r"(?:ee|o2|02|vodafone|voda|three|virgin(?:\smobile)?|giff\s?gaff|tesco(?:\smobile)?|sky(?:\smobile)?|"
            r"bt(?:\smobile)?|id\smobile|smarty|lebara|lyca(?:\s?mobile)?|asda(?:\smobile)?|voxi|verizon|verizion|vzw|"
            r"at\s?&\s?t|at&amp;t|att|t-?\s?mobile|tmobile|tmo|sprint|cricket|metro(?:\s?pcs)?|straight\s?talk|tracfone|"
            r"boost(?:\s?mobile)?|visible|mint(?:\smobile)?|xfinity|spectrum|us\s?cellular|rogers|telus|fido|koodo|chatr|"
            r"vid[ée]otron|freedom(?:\smobile)?|bell(?:\smobility)?|fizz|eastlink|telstra|optus)")
DOESNT = r"(?:doesn'?t|does\snot|dosen'?t|dosent|dosnt|doesent|doesen'?t|dose\snot)"  # as typed: "face id dosent work"
# one part or feature of the phone, for what's said of it alone: "Face ID untested", "works except the speaker"
FEATURES = (r"(?:face\s?id|touch\s?id|true\s?tone|e-?sims?|sim(?:\scard)?(?:\s(?:tray|reader|slot))?|(?:(?:front|rear|"
            r"back|selfie|main|wide|ultra[\s-]?wide|telephoto)\s)?cameras?|(?:loud\s?|ear\s?)?speakers?|earpiece|mic|"
            r"microphones?|wi-?fi|bluetooth|nfc|gps|5g|4g|networks?|signal|calls?|wireless\scharging|magsafe|"
            r"apple\spay|fingerprint(?:\ssensor)?|lidar|(?:lightning|usb-?c|charging)\sport|charging|(?:home|power|"
            r"volume|side|mute|action)\s?buttons?|buttons?|vibrat(?:e|ion|or)|haptics?|flash(?:light)?|torch|"
            r"keyboard|trackpad|backlight|facetime|siri|proximity\ssensor|headphone\sjack|auto[\s-]?rotate)")
# a light of its own: "torch", "keyboard backlight", "charging light"
LIGHTS = (r"(?:(?:charging|keyboard|camera|screen|status|power|indicator|notification|front|rear)\s)?"
          r"(?:lights?|leds?|backlights?|torch|flash(?:light)?)")
# what comes with it, for "no charger", "box missing"
ACCESSORIES = (r"(?:chargers?|charging\s(?:cable|lead|brick|block|plug)|cables?|leads?|box|boxes|packaging|accessories|"
               r"cases?|earphones|earpods|headphones|plugs?|adapters?|manual|paperwork|sim\s(?:tool|ejector|pin)|"
               r"stylus|s\s?pen|(?:screen\s)?protectors?)")
# what's between "no" and the thing that doesn't come ("no ORIGINAL box", "without A case"), never a flaw of its own
NOT_A_FLAW_WORD = r"(?!(?:crack|scratch|scuff|dent|chip|smash|shatter|broke|damage|mark|fault|scrape|ding|no|not)\w*\b)"
# "dead" said of a part, a fault ("dead pixel", "iPhone 12 dead pixels on screen") or the battery ("dead battery"), not
# of the whole phone
NOT_DEAD_PART = r"(?!\s(?:pixels?|spots?|zones?|keys?|lines?|batter(?:y|ies))\b)"
# "dead" as UK slang for very ("dead mint", "dead easy to use"), not a battery that goes dead ("battery goes dead
# quick") or a phone that's dead with a clean IMEI ("Phone dead clean IMEI")
DEAD_SLANG = (r"(?<!goes\s)(?<!go\s)(?<!going\s)(?<!gone\s)(?<!went\s)(?<!runs\s)(?<!run\s)\bdead\s(?:mint|good|nice|"
              r"easy|clean(?!\s(?:imei|esn|icloud|history|check|record))|cheap|fast|quick|smooth|simple|handy|happy|"
              r"chuffed|pleased|proud|lush|gorgeous|pretty|posh|solid|reliable|comfy|comfortable|popular|lucky|cool|"
              r"snappy|tidy|neat|immaculate|perfect|pristine|lovely|sleek)\b")
# a repair done and gone: "went to Apple for repair last year", "been in for repairs before", "previously looked at
# for repair"...
PAST_REPAIR = re.compile(r"""
    \b(?:(?:went|gone|sent|taken|took|brought|had\s(?:it|them)|looked\sat|checked|opened(?:\sup)?|examined|
    inspected)\s(?:[\w']+\s){0,3}?|(?:was|were|been)\s(?:in|away|off|back)\s)for\s(?:a\s|its\s|some\s)?repairs?\b""",
                         X)  # not "booked in for repair": that's one it still needs
# ...but not one that didn't work or didn't happen: "taken to a shop for repair but they couldn't fix it", "sent off for
# repair, Apple said it is not worth fixing", "went in for repair but the repair failed" (6 Oct second check: each was
# priced as clean). Then it's one for repairs
FAILED_REPAIR = re.compile(r"""
    \b(?:couldn'?t|could\snot|can'?t|cannot|can\snot|unable\sto|wasn'?t\sable\sto|weren'?t\sable\sto|not\sable\sto|
    failed\sto|didn'?t|did\snot|won'?t|wouldn'?t|would\snot)\s(?:be\s)?(?:fix|fixed|repair|repaired|sort|sorted|mend|
    mended)\b
  | \bnot\s(?:worth\s(?:fixing|repairing|it|the\s(?:cost|money))|fixable|repairable|economical)\b
  | \b(?:unfixable|unrepairable|irreparable|beyond\s(?:economic(?:al)?\s)?repair|uneconomical|too\sexpensive|
    cost\stoo\smuch|changed\smy\smind|cancel+ed|didn'?t\sgo\sahead|never\s(?:went\sahead|got\s(?:it\s)?(?:done|fixed|
    repaired)|collected|picked\sup))\b
  | \b(?:still|now)\s(?:broken|faulty|dead|not\sworking|doesn'?t\swork|won'?t\s(?:turn|switch|power)\son)\b
  | \b(?:repair|fix)\s(?:has\s|was\s)?(?:failed|didn'?t\swork|did\snot\swork|was\sunsuccessful|unsuccessful)\b
  | \b(?:logic|mother)\s?board\s(?:is\s|was\s|has\s)?(?:dead|died|fried|gone|faulty|broken|damaged|failed)\b""", X)
# ...when it's the phone's: one part that couldn't be fixed ("they couldn't fix the Face ID") is that part's fault
PART_BEFORE = re.compile(rf"\b{FEATURES}\s(?:(?:is|was|are|were|still)\s)?$", I)
PART_AFTER = re.compile(rf"\s(?:the\s|its\s|my\s)?{FEATURES}\b", I)
# a network lock that's gone: "previously EE locked", "originally locked to O2"
PAST_LOCK = re.compile(rf"""\b(?:previously|originally|formerly|used\sto\sbe|once)\s(?:been\s)?(?:{NETWORKS}[\s-]locked|
    locked\s(?:to|on)\s(?:the\s)?{NETWORKS}|(?:network|carrier|sim)[\s-]?locked)\b""", X)
# The owner's carrier rule (6 Oct 2026, buyer-safe): a carrier or network named for the phone ("Carrier: AT&T", "Galaxy
# S21 EE", "for Straight Talk", "works on Verizon") is a network lock unless the listing says it's unlocked or works on
# any network: a locked phone bought as unlocked costs more than an offer 5-10% lower. flip-kinds-1 answers that way by
# itself (it matched a blind relabel to the rule on 158 of 161 test sentences); these let code's rules do the same for
# the title and for any flaw the model can't answer (network_lock, in kinds_of). Two independent reviews tried 350+ ways
# sellers write it (6 Oct evening); tests/test_carrier_rule.py keeps them.
# names that are only ever a carrier (but a colour or a model before "Mobile Phone" isn't: "Galaxy S24 Ultra Mobile
# Phone", "Cosmic Orange Mobile Phone", "Mint Mobile Phone")
CARRIERS = r"""(?:
    at\s?&\s?t | at&amp;t | at\sand\st | atandt | att | verizon | verizion | verzion | vzw | t-?\s?mobile | t-?\s?moblie |
    tmobile | tmo | sprint | cricket(?:\swireless)? | metro\s?pcs | metro\sby\st-?\s?mobile | straight\s?talk | tracfone |
    total\s(?:wireless|by\sverizon) | spectrum(?:\smobile)? | xfinity(?:\smobile)? | u\.?\s?s\.?\s?cellular |
    visible\swireless | mint\smobile(?!\s?phones?\b) | simple\smobile(?!\s?phones?\b) | h2o\swireless | tello | net10 |
    page\splus | consumer\scellular | google\sfi | ultra\smobile(?!\s?phones?\b) | red\spocket | safelink |
    assurance\swireless | boost\s?mobile | boost\sinfinite |
    ee | o2 | vodafone | voda | three\s(?:network(?!\sbars?)|uk|mobile) | giff\s?gaff |
    tesco\smobile | sky\smobile | virgin\smobile | virgin\splus | bt\smobile | id\smobile | smarty | lebara | lyca\s?mobile | lyca | asda\smobile |
    voxi | talkmobile | orange\s(?:network|mobile)(?!\s?phones?\b) |
    rogers | telus | fido | koodo | freedom\smobile | chatr | vid[ée]otron | public\smobile |
    lucky\smobile | bell\smobility | sasktel | eastlink | fizz | telstra | optus | amaysim)"""
# names that are plain words too ("three scratches", "Cosmic Orange", "on the metro", "visible marks", "mint
# condition", "02 March"): a carrier only where nothing else fits (NAMED_NETWORK)
PLAIN = r"(?:three|orange|bell|boost|metro|visible|virgin|sky|tesco|bt|mint|freedom|simple|total|ultra|h2o|h20|02)"
TITLE_PLAIN = r"(?:three|bell|boost|metro|visible|virgin|freedom|tesco)"  # a title's last word: "iPhone 13 128GB Bell"
NAMED_NETWORK = re.compile(rf"""\b{CARRIERS}\b
  | \b(?:carrier|network|provider|operator|fournisseur|operador|compa[ñn][ií]a)\s*(?:[:=–-]\s*)?{CARRIERS}\b
  | \b(?:carrier|network|provider|operator|fournisseur|operador|compa[ñn][ií]a)\s*(?:[:=–-]|is(?:\son)?)\s*(?:the\s)?
    {PLAIN}\b
  | \b(?:on|with|from|for|via|chez|avec|con|de|para|sur)\s{PLAIN}\b
    (?=\s*$|\s*(?![/.:-]\s?\d)[^\w\s]|\s(?:network|mobile|uk|sims?|contract|plan|service|carrier|phone|only|or|and|so|
    but|since|until|before|for|now)\b)                     # (not a date: "on 02/03/2025")
  | \bon\s3\snetwork\b | \b(?:02|o2)\ssim\b""", X)
TITLE_NETWORK = re.compile(rf"(?:^|[\s(/-]){TITLE_PLAIN}\s*\)?\s*$|\(\s?(?:three|3)\s?\)", I)  # titles only
# ...but not a network that isn't the phone's: a test caveat ("untested on EE", "never tried an O2 sim in it", "not
# tested on EE or O2"), one the seller is moving to ("switching to Vodafone", "ported my number to Mint Mobile"), "not
# a Verizon phone", cricket the sport
ANY_CARRIER = rf"(?:{CARRIERS}|{PLAIN})"
CARRIER_LIST = rf"{ANY_CARRIER}(?:\s?(?:,|/|&|\bor\b|\band\b)\s?(?:the\s)?{ANY_CARRIER})*"
NOT_ITS_NETWORK = re.compile(rf"""
    \b(?:untested|(?:not|never|haven'?t|havent|hasn'?t|hasnt|wasn'?t|wasnt|isn'?t|isnt|didn'?t|didnt|can'?t|cant|
    cannot|couldn'?t|couldnt|unable\sto)\s(?:been\s|yet\s)?(?:tested|tried|checked|used|test|try|check|use))\s
    (?:it\s)?(?:(?:on|with|in)\s)?(?:an?\s|the\s|any\s)?{CARRIER_LIST}(?:\s(?:sims?|networks?|cards?))?
  | \b(?:switch(?:ed|ing)?|mov(?:ed|ing|e)|chang(?:ed|ing|e)|going|gone|went|join(?:ed|ing)?|port(?:ed|ing)?)\s
    (?:over\s)?(?:my\s(?:number|line|contract|plan|sim)\s)?(?:(?:networks?|carriers?|providers?)\s)?(?:over\s)?to\s
    (?:the\s)?{CARRIER_LIST}
  | \b(?:not|isn'?t|isnt|never\sbeen)\s(?:an?\s)?{ANY_CARRIER}\s(?:phone|model|device|branded|version|handset)
  | \bplay(?:ing|ed|s)?\s(?:\w+\s)?cricket\b | \bcricket\s(?:bat|ball|match|game|pitch|club|team|season|world)""", X)
# the listing saying the phone works on any network: "Unlocked", "factory unlock", "SIM-free", "S/F", "open line",
# "works on all 3 major carriers", "not network locked", "Network locked: No", "No SIM restrictions", "liberado"...
UNLOCK_WORDS = re.compile(rf"""\bun-?locked\b | \bunlkd\b | \bfactory[\s-]?unlock(?:ed)?\b | \bsim[\s-]?free\b | \bs/f\b
  | \bopen\sline\b | \b(?:liberad[oa]|desbloquead[oa]|d[ée]bloqu[ée]e?|d[ée]verrouill[ée]e?|d[ée]barr[ée]e?)\b
  | \bunlock(?=\s(?:{CARRIERS}\b|\d{{1,4}}\s?(?:gb|tb)\b))  # "iPhone 12 Unlock Telus 128GB": a title's word for it""", X)
ANY_NETWORK = re.compile(r"""\b(?:any|all|every|cualquier|todas?\slas?|tous\sles|toutes\sles)\s(?:[\w&/+-]+\s){0,3}?
    (?:networks?|carriers?|sims?|sim\scards?|providers?|operators?|compa[ñn][ií]as?|fournisseurs?|r[ée]seaux|
    op[ée]rateurs?)\b""", X)
NOT_LOCKED = re.compile(rf"""
    \b(?:not|never|isn'?t|isnt|wasn'?t|wasnt|hasn'?t|hasnt|haven'?t|havent|is\snot|was\snot|has\snot|have\snot)\s
    (?:been\s|ever\s(?:been\s)?)?(?:(?:network|carrier|sim|{ANY_CARRIER})[\s-])?locked\b
    (?!\s(?:to|on|with|by)\s(?:(?:the|an?|my|any|your|previous|old|someone'?s?)\s)*(?:owner|i\s?cloud|apple|google|
    account|samsung|activation|frp))
  | \bno\s(?:(?:network|carrier|sim|{CARRIERS})[\s-]?)lock(?:ed)?\b
  | \b(?:doesn'?t|doesnt|does\snot|don'?t|dont|do\snot)\shave\s(?:an?\s|any\s)?(?:network|carrier|sim)[\s-]?lock\b
  | \b(?:network|carrier|sim)[\s-]?lock(?:ed)?\s*[:=–-]\s*(?:no|none|n/?a|nope|unlocked|off)\b
  | \bno\ssim\srestrictions?\b""", X)
# ...undone by what's around it in its clause: a "no"/"not"/"never" right before ("not unlocked", "hasnt been
# unlocked", "never got round to getting it unlocked"), a promise ("can be unlocked", "will work on all networks once
# unlocked", "easily unlocked"), a doubt ("I think", "as far as I know", "idk if", "was told"), or another lock than the
# network's ("unlocked from my iCloud", "iCloud unlocked", "OEM unlocked", "unlocked bootloader")
FILLER = (r"(?:\s(?:been|yet|be|it|is|it'?s|its|got|get|getting|round|around|to|fully|officially|properly|network|"
          r"carrier|sim|actually|even|ever|still|have|tried|tested|used|work|works|working|take|takes|accept|on|with|"
          r"in|unlocked))*")
NOT_BEFORE = re.compile(rf"""\b(?:not|never|no|isn'?t|isnt|wasn'?t|wasnt|hasn'?t|hasnt|haven'?t|havent|hadn'?t|hadnt|
    doesn'?t|doesnt|didn'?t|didnt|aren'?t|arent|can'?t|cant|cannot|won'?t|wont|pas|non|no\sest[aá]|nunca|jamais)\b
    {FILLER}\s*$""", X)
LATER_BEFORE = re.compile(rf"""\b(?:can|could|will|would|should|must|may|might|to|need|needs|once|until|till|when|if|unless|
    after|eligible|pending|easily|able|going|gonna|wants?|yet|awaiting|waiting|requested)\b{FILLER}\s*$""", X)
LATER_AFTER = re.compile(r"^[^.!?\n]{0,30}?\b(?:once|when|after|if|unless|until)\s(?:it'?s\s|it\sis\s|it\sgets\s|i\s)?"
                         r"(?:unlocked|paid\s(?:off|for)|unlocking)\b|^\s(?:other\sthan|except|apart\sfrom|but)\b", I)
DOUBT = re.compile(r"""\b(?:think|thinks|believe|believes|guess|assume|assuming|reckon|apparently|supposedly|probably|
    possibly|maybe|might|hopefully|unconfirmed|tbc|unsure|idk|dunno|afaik|said|says|should|presumably|allegedly)\b
  | \bnot\s(?:100%|sure|certain|positive) | \bdon'?t\sknow | \bdont\sknow | \bas\sfar\sas\si\s(?:know|can\stell|am\saware)
  | (?<!\bfor\s)(?<!\bmake\s)\bsure\b                   # "I'm pretty sure it's unlocked" (not "unlocked for sure")
  | \b(?:was|been|were|i'?ve\sbeen|i\swas)\stold""", X)
PROMISED = re.compile(r"\b(?:can|could|will|would|should|must|may|might|to|once|when|if|after|unless|until|yet)\b"
                      r"(?:\s[\w']+){0,3}\sunlock(?:ed)?\s(?:for|to|on|with|onto)\s*$", I)
OTHER_LOCK = re.compile(r"(?:i\s?cloud|bootloader|oem|activation|frp|google|account|apple\sid|screen|bios|firmware|mdm)"
                        r"[\s-]*$", I)
OTHER_LOCK_AFTER = re.compile(r"""^\s*(?:(?:from|on|with|by|of|to)\s(?:(?:my|the|your|their|his|her|previous|old|
    owner'?s?|an?|any)\s)*(?:i\s?cloud|apple(?:\sid)?|account|google|samsung\saccount|activation|owner|frp)|bootloader)""",
                              X)
SENTENCES = re.compile(r"[.!?\n;|•]+")
CLAUSE_BREAK = re.compile(r",|\s(?:but|and|&|plus|though|although|however|except|so)\s|\s[-–—]\s", I)


def says_unlocked(text):
    """Whether the listing plainly says the phone works on any network: UNLOCK_WORDS, ANY_NETWORK or NOT_LOCKED with
    nothing in its own clause undoing, deferring or doubting it (NOT_BEFORE, LATER_BEFORE, LATER_AFTER, DOUBT) and not
    about another lock (OTHER_LOCK). A doubt in a short clause right after counts too ("Unlocked, I think")."""
    for sentence in SENTENCES.split(re.sub(r"[’‘ʼ]", "'", text or "")):
        breaks = [b.span() for b in CLAUSE_BREAK.finditer(sentence)]
        for words, kind in ((NOT_LOCKED, "not locked"), (UNLOCK_WORDS, "unlocked"), (ANY_NETWORK, "any network")):
            for m in words.finditer(sentence):
                start = max([e for s, e in breaks if e <= m.start()], default=0)
                end = min([s for s, e in breaks if s >= m.end()], default=len(sentence))
                after_next = min([s for s, e in breaks if s > end], default=len(sentence))
                before, after, nxt = sentence[start:m.start()], sentence[m.end():end], sentence[end:after_next]
                nxt = nxt if len(nxt.split()) <= 5 else ""
                if DOUBT.search(before) or DOUBT.search(after) or DOUBT.search(nxt):
                    continue
                if kind == "not locked":
                    return True  # "not network locked", "Network locked: No"
                if NOT_BEFORE.search(before) or LATER_AFTER.search(after):
                    continue
                if kind == "any network" and PROMISED.search(before):
                    continue  # "can be unlocked for any SIM card worldwide": a promise, not what it is
                if kind == "unlocked" and (LATER_BEFORE.search(before) or OTHER_LOCK.search(before)
                                           or OTHER_LOCK_AFTER.search(after)):
                    continue
                return True
    return False


# a lock said in words the reader's judge doesn't read as one (it reads "never" as a denial): sure ones ("won't take
# other networks' SIMs", "barré", "solo funciona con Boost")...
NOT_A_COUNT = (r"(?!\s(?:out\sof|of|times?|tries|attempts?|occasions?|days?|weeks?|months?|years?|hours?|minutes?|%|"
               r"percent|spots?|keys?|sides?|corners?|edges?|lenses|cameras?|scratch\w*|marks?|dents?|chips?|"
               r"cracks?)\b)")
WONT_OTHERS = rf"""(?<!wi-fi\s)(?<!wifi\s)(?<!\bwi\sfi\s)\b(?:won'?t|wont|{DOESNT}|will\snot|can'?t|cant|cannot|
    isn'?t\sable\sto|not\sable\sto|unable\sto)\s(?:work|be\sused|take|accept|read|recogni[sz]e)\s(?:on\s|with\s|in\s)?
    (?:(?:sims?|sim\scards?)\sfrom\s)?(?:any\s)?other\s(?:networks?'?|carriers?'?|providers?|sims?|sim\scards?)
  | \bother\s(?:(?:networks?'?|carriers?'?)\s)?(?:sims?|sim\scards?)\s(?:won'?t|wont|don'?t|dont|do\snot|will\snot|
    can'?t|cannot|doesn'?t)\s(?:work|be\sused|connect|register|read)"""
LOCK_SAID_SURE = re.compile(rf"""{WONT_OTHERS}
  | \b(?:network|sim|carrier)[\s-]lock(?:ed)?\s*[:=–-]\s*(?:yes|y|on|active)\b
  | \b(?:no\sest[aá]|not)\s(?:liberad[oa]|desbloquead[oa])\b | \bpas\s(?:d[ée]barr[ée]|d[ée]bloqu[ée]|d[ée]verrouill[ée])
  | \bbarr[ée]e?\b | \bbloquead[oa]\s(?:con|a|para|por|en)\s
  | \b(?:solo|s[oó]lo|solamente|[uú]nicamente)\s(?:sirve|funciona|trabaja)\s(?:con|en|para)\s
  | \b(?:sirve|funciona|trabaja)\s(?:solo|s[oó]lo|solamente|[uú]nicamente)\s(?:con|en|para)\s
  | \b(?:fonctionne|marche)\s(?:seulement|uniquement)\s(?:avec|sur|chez)\s | \bseulement\s(?:avec|sur|chez)\s""", X)
# ...and ones about unlocking, which could be the screen or an account ("needs unlocking, forgot the passcode", "can
# only be unlocked with the passcode", "not unlocked from iCloud yet"): only with nothing of that around (OTHER_UNLOCK)
NO_ACCOUNT = (r"(?!\s(?:from|on|with|using|via|by|to)\s(?:(?:the|an?|my|your|their|his|her|previous|old|owner'?s?)\s)*"
              r"(?:i\s?cloud|apple(?:\sid)?|account|google|owner|activation|pass(?:code|word)|pin|code|face\s?id|"
              r"touch\s?id|fingerprint|pattern|watch|frp))")
LOCK_SAID_UNLOCK = re.compile(rf"""
    \b(?:not|never|isn'?t|isnt|wasn'?t|wasnt|hasn'?t|hasnt|haven'?t|havent|hadn'?t|hadnt)\s(?:yet\s)?(?:been\s)?
    (?:yet\s)?(?:(?:officially|fully|properly|actually|network|carrier|sim)\s)*unlocked\b{NO_ACCOUNT}
  | \bnever\sgot\s(?:a)?round\sto\s(?:getting\s(?:it\s)?)?unlock(?:ed|ing)\b
  | \b(?:can|could|will|would)\s(?:(?:easily|still|only|soon)\s)?be\s(?:(?:easily|still|only|soon)\s)?
    (?:(?:network|carrier|sim)\s)?unlocked\b{NO_ACCOUNT}
  | \b(?:can|could)\s(?:easily\s)?get\s(?:it\s)?unlocked\b{NO_ACCOUNT}
  | \byet\sto\sbe\s(?:(?:network|carrier|sim)\s)?unlocked\b
  | \beasily\sunlocked\sby\s(?:calling|contacting|asking|phoning|ringing)\b
  | \bunlock(?:ing)?\s(?:is\s)?(?:pending|requested|in\sprogress|underway)\b
  | \b(?:awaiting|waiting\s(?:on|for))\s(?:the\s|an?\s)?(?:(?:network|carrier|sim)\s)?unlock(?:\scode)?\b
  | \beligible\s(?:for\s(?:an?\s)?unlock|to\sbe\sunlocked)\b
  | \bneeds?\s(?:to\sbe\s)?(?:(?:network|carrier|sim)\s)?unlock(?:ed|ing)\b{NO_ACCOUNT}""", X)
OTHER_UNLOCK = re.compile(r"\b(?:pass\s?code|password|pin|i\s?cloud|activation|apple\s?id|account|google|frp|face\s?id|"
                          r"touch\s?id|fingerprint|screen\s?lock|forgot|forgotten|previous\sowner)\b", I)
# what turns a lock back on or keeps it: "Originally EE locked and still is", "still on Vodafone"; and a lock said in
# the past ("Was locked to EE"), which an unlock anywhere in the listing undoes
STILL_LOCKED = re.compile(r"\bstill\s(?:is|locked|on|tied|stuck|with|network\slocked|carrier\slocked|sim\slocked)\b",
                          I)
PAST_TENSE = re.compile(r"\b(?:was|were|used\sto\sbe|previously|originally|formerly|once|had\sbeen)\b|\bex[\s-]", I)


def network_named(said, title=False):
    """Whether these words name a carrier or network for the phone (NAMED_NETWORK; in a title also TITLE_NETWORK),
    leaving out NOT_ITS_NETWORK."""
    said = NOT_ITS_NETWORK.sub(" ", re.sub(r"[’‘ʼ]", "'", said or ""))
    return bool(NAMED_NETWORK.search(said) or (title and TITLE_NETWORK.search(said)))


def lock_said(flaw, around):
    """Whether the flaw says the phone is network locked in words no rule reads (LOCK_SAID_SURE, LOCK_SAID_UNLOCK)."""
    if LOCK_SAID_SURE.search(flaw):
        return True
    return bool(LOCK_SAID_UNLOCK.search(flaw)) and not OTHER_UNLOCK.search(around)


def network_lock(flaw, around, listing, found, title=False):
    """Whether a flaw sentence (or the title) gives a network lock, the owner's carrier rule: a lock its words state
    (found: the rules read one; or lock_said), unless the same sentence undoes it or it was in the past and the listing
    says it's unlocked; else a carrier named for the phone (network_named) unless the listing says it's unlocked. Never
    for a MacBook, and never a lock that's gone ("Previously EE locked", PAST_LOCK)."""
    head = listing[:150]
    if MACBOOK.search(head) and not IPHONE.search(head) and not SAMSUNG.search(head):
        return False  # a MacBook has no network to be locked to ("Wi-Fi won't connect to other networks": a fault)
    flaw, around = (re.sub(r"[’‘ʼ]", "'", said) for said in (flaw, around))
    if PAST_LOCK.search(flaw) and not STILL_LOCKED.search(around):
        return False
    if found or lock_said(flaw, around):
        if STILL_LOCKED.search(around):
            return True  # "Originally EE locked and still is", "Not unlocked, still on Vodafone"
        if says_unlocked(around):
            return False  # "EE locked but I got it unlocked last year", "Was locked to O2 but unlocked now"
        return not (PAST_TENSE.search(flaw) and says_unlocked(listing))  # "Was locked to EE. Unlocked by EE in May"
    return network_named(flaw, title) and not says_unlocked(listing)


# a black screen that's a fault ("black screen", "black screen on boot"), not its colour ("Midnight black screen and
# back perfect", "Black Screen Perfect")
BLACK_SCREEN = (r"(?<!midnight\s)(?<!phantom\s)(?<!jet\s)(?<!space\s)(?<!onyx\s)(?<!cosmic\s)(?<!prism\s)"
                r"(?<!mystic\s)(?<!titanium\s)(?<!matte\s)(?<!matt\s)(?<!piano\s)(?<!glossy\s)(?<!gloss\s)\bblack\s"
                r"(?:screen|display)\b(?=\s*$|\s*[.,;:!?)/]|\s(?:issues?|problems?|of\sdeath|on|when|after|with|"
                r"sometimes|randomly)\b|\sand\s(?!(?:the\s)?(?:back|rear|frame|body|case|sides?|edges?|bezels?)\b))")
NOT_DONE = r"(?!\s(?:done|completed|carried\sout|history|centre|center|record|receipt|by\b|at\s(?:apple|an?|the)\b))"

KIND_RULES = [
    # words that read as a flaw but name nothing the price is cut for, so no later rule counts them (and the reader's
    # judge calling them a flaw doesn't make them wear): a thing that doesn't come with it ("no charger", "box
    # missing": the rest of the clause still counts, "screen cracked no box"), UK praise that sounds like a flaw
    # ("dead mint", "dead easy to use", "cracking condition", "can't fault it"), a repair done and gone (PAST_REPAIR)
    # or cover for one (AppleCare's "peace of mind for repairs", "covered for repairs"), a network lock that's gone
    # (PAST_LOCK)
    ("none", re.compile(rf"""
        \b(?:no|missing|without|not\sincluded|not\sinc|doesn'?t\scome\swith|does\snot\scome\swith|comes\swithout|
        lost\sthe)\s(?:{NOT_A_FLAW_WORD}[\w&+/-]+\s){{0,4}}?{ACCESSORIES}\b
      | \b{ACCESSORIES}\s(?:is\s|are\s|was\s|has\sbeen\s|have\sbeen\s)?(?:missing|not\sincluded|lost)\b
      | {DEAD_SLANG} | \b(?:can'?t|cannot|can\snot|couldn'?t|could\snot)\sfault\s(?:it|them|this|the\s\w+)\b
      | \bcracking\s(?:condition|phone|little|deal|price|value|bargain|nick|order|shape|example|device|laptop|handset|
        mobile|buy|one)\b
      | \b(?:covered|cover|covers|insured|peace\sof\smind)\sfor\srepairs?\b""",
                        X)),
    ("none", PAST_REPAIR),
    ("none", PAST_LOCK),
    # one label over two flaws, answered once: "Cracks or chips: none", "Any cracks or chips: no" (6 Oct second check:
    # read as damage). The answer denies both
    ("none", re.compile(r"""\b(?:any\s)?(?:\w+\s)?(?:crack\w*|chip\w*|dent\w*|scratch\w*|scuff\w*|marks?|damage)
        \s?(?:or|and|&|/)\s?(?:crack\w*|chip\w*|dent\w*|scratch\w*|scuff\w*|marks?|damage)\s?[:=-]\s?
        (?:none|no|nope|nil|n/a)\b""", X)),
    # one part left untested, not the whole phone ("Face ID untested", "untested on other networks"): a warning, as
    # the API cuts "sold as seen", not a phone sold for parts. The phone itself untested is ("Untested by me",
    # "untested for parts", "Untested with a sim": 6 Oct second check)
    ("hint", re.compile(rf"""\b{FEATURES}\s(?:is\s|are\s|was\s|has\sbeen\s)?untested\b
      | \buntested\s(?:on|with|in|across)\s(?!an?\ssim(?:\scard)?s?\b)(?:(?:the|a|an)\s)?(?:(?:any|all|other|different|another|foreign|international|5g|4g|
        {NETWORKS})\s)*(?:networks?|carriers?|sims?|sim\scards?|5g|4g|{NETWORKS})\b
      | \buntested\s(?:abroad|overseas)\b""", X)),
    ("lock", re.compile(r"""
        \b(?:i\s?cloud|activation|apple\s?id|account|google|frp|bios|firmware|mdm|efi|kg|knox(?:\sguard)?)[\s-]*
        lock(?:ed)?\b
      | \blocked\s(?:to|on|with)\s(?:an?\s|the\s|my\s|someone(?:'s|s)?\s|(?:the\s)?previous\s)?(?:owner(?:'s|s)?\s)?
        (?:i\s?cloud|apple\s?id|account|google)
      | \blocked\sto\s(?:the\s|its\s|an?\s)?(?:previous\s|old\s|original\s|last\s|first\s|former\s)?owner(?:'?s)?\b
      | \bi\s?cloud\s(?:is\s)?(?:still\s)?(?:on|attached|active|logged\sin|signed\sin|enabled)\b
      | \b(?:can'?t|cannot|unable\sto|could\snot|couldn'?t)\s(?:remove|sign\sout\sof|log\sout\sof|turn\soff|disable|
        get\spast|bypass)\s(?:the\s|my\s)?(?:i\s?cloud|apple\s?id|find\smy|activation|google|frp|mdm)
      | \bfind\smy(?:\s(?:iphone|mac|device|phone))?\s(?:is\s)?(?:still\s)?(?:on|enabled|active)\b
      | \b(?:firmware|efi|bios)\s(?:password|passcode|pin)\b(?!\s(?:is\s|has\sbeen\s)?(?:removed|off|disabled|cleared|
        reset)\b)
      | \b(?:passcode|password)[\s-]locked\b | \bknox\sguard\b
      | \bmdm\b | \bblacklist(?:ed)?\b | \bbad\s(?:imei|esn)\b | \b(?:barred|blocked)\simei\b
      | \bimei\s(?:is\s)?(?:blocked|barred|blacklisted)\b | \bbarred\b | \breported\s(?:lost|stolen)\b""", X)),
    # a part that won't come on is that part's fault, not a dead phone: "torch won't come on", "keyboard backlight
    # doesn't come on", "wifi won't turn on" (6 Oct second check: priced for parts). Named so plainly that the judge
    # isn't asked, as the dead phone's words weren't
    ("part fault", re.compile(rf"""\b(?:{FEATURES}|{LIGHTS})\s(?:(?:still|just|sometimes|ever|also)\s)?(?:won'?t|
        {DOESNT}|will\snot|isn'?t|is\snot|not|never|wouldn'?t|would\snot)\s(?:turn(?:s|ing)?|switch(?:es|ing)?|
        power(?:s|ing)?|com(?:e|es|ing))\son\b
      | \b(?:couldn'?t|could\snot|can'?t|cannot|can\snot|unable\sto|failed\sto|didn'?t|did\snot)\s(?:be\s)?(?:fix|
        fixed|repair|repaired|sort|sorted)\s(?:the\s|its\s|my\s)?{FEATURES}\b
      | \b{FEATURES}\s(?:(?:is|was)\s)?(?:(?:can'?t|cannot|can\snot|couldn'?t|could\snot)\sbe\s(?:fixed|repaired)|
        unfixable|beyond\srepair)\b""", X)),
    ("parts", re.compile(rf"""
        \bfor\sparts\b | \bparts\sonly\b | \bspares\b | \bfor\srepairs?\b | \bneeds?\s(?:a\s)?repair(?:ing|s)?\b
      | \brepair\sjob\b
      | \b(?:won'?t|{DOESNT}|will\snot|can'?t|cannot|isn'?t|is\snot)\s(?:turn(?:ing)?|power(?:ing)?|switch(?:ing)?|
        boot(?:ing)?)\s(?:on|up)\b
      | \bnot\s(?:turning|powering|switching|booting)\s(?:on|up)\b | \bno\spower\b
      | \b(?:won'?t|{DOESNT}|will\snot|isn'?t|is\snot|not)\scom(?:e|ing)\son\b
        (?!\s(?:its|it'?s|the|an?|with|in|my|your)\b)
      | \bno\slonger\s(?:turns?|turning|switch(?:es|ing)?|powers?|powering|boots?|booting|comes?|coming)\s(?:on|up)\b
      | \b(?:i?phone|laptop|mac\s?book|it|device|unit|handset|mobile)(?:'?s)?\s(?:is\s|was\s|has\sgone\s|went\s)?
        (?:(?:now|completely|totally|fully|just|basically|literally|unfortunately|sadly)\s){{0,2}}dead\b
        (?!\s(?:at\sthe\smoment|right\snow|atm|currently)\b){NOT_DEAD_PART}
      | \bdead\s(?:i\s?phone|phone|samsung|galaxy|mac\s?book|laptop|handset|device|unit|mobile)\b
      | \buntested\b | \b(?:sold|selling|sell)\s(?:it\s|this\s|them\s)?as\s(?:a\s)?(?:spares|repairs?|faulty|broken|
        not\sworking|untested|parts)\b""", X)),
    # a network lock in so many words ("locked to EE", "VZW locked", "Network: Locked", "has a network lock on it",
    # "won't take other networks' SIMs"); a carrier just named is read by the carrier rule (network_lock), and so is
    # the seller's own network ("I only use EE", a lock under the carrier rule)
    ("network lock", re.compile(rf"""
        \blocked\s(?:to|on|with)\s(?:the\s)?(?:{NETWORKS}|3)\b{NOT_A_COUNT}
      | \blocked\s(?:to|on)\s(?:(?:its|the|an?|one|some)\s)?(?:(?:original|first|home|old|previous|own)\s)?
        (?:network|carrier|provider)\b
      | \bnetwork[\s-]?locked\b | \bcarrier[\s-]?locked\b | \bsim[\s-]?locked\b | \bnetwrok[\s-]?locked\b
      | \b(?:network|carrier|sim)\s*:\s*locked\b
      | \b{NETWORKS}[\s-]locked\b | \blocked\s{NETWORKS}\b{NOT_A_COUNT}
      | \b{NETWORKS}(?:\snetwork)?\sonly\b
      | \bonly\s(?:works?\s|working\s)?(?:on|with)\s(?:the\s)?{NETWORKS}\b{NOT_A_COUNT}
      | (?<!\bi\s)(?<!\bwe\s)\bonly\s(?:takes?|accepts?|uses?|works?\s(?:with|on))\s(?:an?\s|the\s)?{NETWORKS}
        (?:\s(?:sims?|sim\scards?))?\b{NOT_A_COUNT}
      | \b(?:only\s(?:works?|work|working)|will\sonly\swork|works\sonly)\s(?:on|with)\s(?:one|its\s(?:original|own)|
        the\soriginal|a\ssingle)\s(?:network|carrier|provider)\b
      | \b(?:has|have|with|got|there'?s|there\sis)\s(?:an?\s|the\s)?(?:network|sim|carrier)[\s-]lock\b
      | \b(?:network|sim|carrier)[\s-]lock\s(?:is\s)?(?:still\s)?on\b
      | \b(?:network|sim|carrier)[\s-]lock(?:ed)?\s*[:=–-]\s*(?:yes|y|on|active)\b
      | {WONT_OTHERS}
        """, X)),
    ("not genuine", re.compile(r"""
        \bnon[\s-]?genuine\b | \bnon[\s-]?original\b
      | \bnot\s(?:genuine|original|oem|official)\s(?:apple\s)?(?:screen|battery|display|lcd|parts?|camera|back\sglass|
        housing)\b
      | \b(?:screen|battery|display|lcd|parts?|camera)\s(?:is\s|are\s|was\s|were\s|has\sbeen\s)?(?:not\s(?:genuine|
        original|oem)|non[\s-]?genuine|aftermarket|third[\s-]?party|a\scopy|copy|generic|replica)\b
      | \baftermarket\b | \bthird[\s-]?party\s(?:screen|battery|parts?|display|lcd|camera)\b | \bunknown\spart\b
      | \b(?:copy|generic|replica|fake)\s(?:screen|battery|display|lcd)\b | \bincell\b | \bnot\sgenuine\b""", X)),
    ("damage", re.compile(r"""
        \b(?:cracked|smashed|shattered|chipped)\s?(?:and|&|/|or)\s?broken\b
      | \bbroken\s?(?:and|&|/|or)\s?(?:cracked|smashed|shattered|chipped)\b
      | \bcrack(?:ed|s)?\b | \bsmash(?:ed|es|d)?\b | \bshatter(?:ed|s|d|red)?\b | \bdent(?:s|ed)?\b | \bchipped\b
      | \bchips?\s(?:on|in|to|at|off)\s(?:the\s)?(?:screen|corner|edge|glass|back|frame|body|casing|lid|side|display|
        bezel)\b
      | \bbent\b
      | \bbroken\s(?:screen|back|glass|lcd|display|hinge|lid|frame|lens|camera\slens|corner|casing|case)\b
      | \b(?:screen|back|glass|lcd|display|hinge|lid|frame|lens)\s(?:is\s|was\s)?(?:broken|broke)\b
      | \bbroke\s(?:the\s|my\s|its\s)?(?:screen|back\sglass|back|glass|lcd|display|lens)\b
      | \bneeds?\s(?:a\s)?new\s(?:front\s|rear\s)?(?:screen|display|lcd|back(?:\sglass)?|glass|lens|housing)\b
        (?!\s?protector)
      | \bburn[\s-]?in\b | \bscreen\sburn\b | \b(?:water|liquid)\s(?:damage(?:d)?|spill)\b | \bdamaged?\b""", X)),
    ("fault", re.compile(rf"""
        \bnot\sworking\b
      | \b(?:{DOESNT}|don'?t|do\snot|won'?t|will\snot|isn'?t|is\snot|aren'?t|are\snot|can'?t|cannot)\s
        (?:work(?:ing)?|charge|charging|connect(?:ing)?|pair(?:ing)?|read|register|respond(?:ing)?|
        hold\s(?:a\s)?charge|recogni[sz]e|detect|click(?:ing)?|focus(?:ing)?|vibrate)\b
      | \bstopped\sworking\b | \bfault(?:y|s)?\b | \bdead\s(?:pixels?|spots?|zones?|keys?)\b
      | \b(?:green|pink|purple|white|black|blue|red|yellow|vertical|horizontal)\slines?\b
      | \blines?\s(?:on|across|down|in)\s(?:the\s)?(?:screen|display|lcd)\b
      | \b(?:screen|display|lcd)\s(?:has|have|with|got|shows?)\s(?:an?\s|one\s|some\s|two\s|2\s)?(?:(?:thin|faint|
        small|tiny|little|slight|visible)\s)?lines?\b(?!\s(?:of|scratch\w*)\b)
      | \b(?:dots?|spots?|patch(?:es)?|shadows?|blotch(?:es)?|pressure\smarks?)\s(?:on|in)\s(?:the\s)?
        (?:screen|display|lcd)\b
      | \b(?:screen|display)\s(?:randomly\s|sometimes\s|keeps\s)?(?:goes|going|went|turns|turning|turned)\s
        (?:black|blank)\b
      | {BLACK_SCREEN}
      | \bghost(?:ing)?\stouch\b | \bboot\s?loop\w*
      | \bstuck\son\s(?:the\s)?(?:apple\s|samsung\s)?(?:logo|boot\s?screen|loading\sscreen)\b
      | \bno\s(?:sound|signal|service|audio|wi-?fi|bluetooth|face\s?id|touch\s?id|display|picture|backlight)\b
        (?!\s(?:issues?|problems?|faults?))
      | \b(?:face|touch)\s?id\s(?:is\s)?(?:not|{DOESNT}|isn'?t|won'?t|unavailable|disabled|broken|faulty)\b
        (?!\s(?:tested|checked|set\sup|setup|sure|known)\b)
      | \bcamera(?:\s|\s?[:=]\s?)(?:is\s)?(?:broken|blurry|not|{DOESNT}|won'?t|faulty|shak(?:es|ing|y)|rattl\w*|black)\b
      | \b(?:blurry|broken|faulty|shaky|rattling)\s(?:rear\s|front\s|back\s|main\s)?camera\b
      | \bspeaker(?:\s|\s?[:=]\s?)(?:is\s)?(?:crackl\w*|distorted|broken|not|{DOESNT}|quiet|muffled|blown)\b
      | \bcrackl(?:es|ing|e)\b
      | \b(?:wi-?fi|bluetooth)\s(?:is\s)?(?:greyed|grayed)\s?out\b
      | \b(?:can'?t|cannot|can\snot)\shear\s(?:anyone|anything|people|callers?|calls?|them|you)\b
      | \b(?:people|they|callers?|others?)\s(?:can'?t|cannot|can\snot)\shear\s(?:me|you)\b
      | \bsticky\skeys?\b | \bkeys?\s(?:not|don'?t|{DOESNT}|isn'?t)\s(?:work|working)\b
      | \bmissing\s(?:keys?|keycaps?|buttons?)\b | \bwon'?t\scharge\b | \bnot\scharging\b | \bflicker(?:s|ing)?\b
      | (?<!\bi\s)(?<!\bwe\s)\bonly\s(?:charges?|charging|charge)\b[^.,;!?]{{0,25}}?\b(?:wireless\w*|magsafe)\b
      | \b(?:charges?|charging)\s(?:wireless(?:ly)?|(?:via|with|on|using)\s(?:an?\s|the\s)?(?:wireless|magsafe)\w*)\s
        only\b
      | \boverheat(?:s|ing)?\b | \brestart(?:s|ing)?\s(?:on\sits\sown|randomly|by\sitself)\b
      | \brandom(?:ly)?\s(?:restart|shut|turn)\w* | \bshuts?\s(?:down|off)\s(?:randomly|on\sits\sown|by\sitself)\b
      | \bglitch\w* | \blag(?:gy|s|ging)\b | \bfreez(?:es|ing)\b | \bdrift\w* | \bstuck\spixels?\b
      | \bunresponsive\b | \bswollen\b
      | \b(?:buttons?|keys?|trackpad|crown|switch|slider)\s(?:is\s|are\s|gets\s|keeps\s|getting\s)?(?:(?:a\sbit|
        a\slittle|slightly|sometimes)\s)?stuck\b | \bstuck\s(?:buttons?|keys?)\b
      | \b(?:loose|stiff|wobbly|rattl\w*|noisy|grinding|squeak\w*|buzz\w*)\s(?:hinge|button|key|fan|port|frame|
        screen|lid|trackpad|speaker)s?\b
      | \b(?:hinge|button|key|fan|port|lid|trackpad)s?\s(?:is\s|are\s)?(?:(?:a\sbit|a\slittle|slightly|quite|very|
        really|abit|bit|kinda|somewhat)\s)?(?:loose|stiff|wobbly|rattl\w*|noisy|squeak\w*)\b
      | \b(?:charging|lightning|usb-?c)\sport\s(?:is\s)?(?:(?:a\sbit|a\slittle|slightly|quite|very|really|abit|bit|
        kinda|somewhat)\s)?(?:loose|broken|faulty|damaged)\b | \bbroken\b""", X)),
    # (a service done is none: "Battery service done at Apple")
    ("battery", re.compile(rf"""
        \bbattery\s(?:needs?\s(?:replacing|replacement|a\sservice|service|servicing|changing)|
        service(?:\srecommended)?{NOT_DONE}|is\s(?:weak|poor|bad|degraded|dying)|drains?|draining|
        life\sis\s(?:poor|bad|short|not\sgreat))\b
      | \bbattery(?:\s(?:health|condition|status|state))?\s*[:=\-–]?\s*(?:(?:is|says|shows|showing|reads|reading|
        displays|now)\s)?(?:on\s|at\s)?["'“”]?service(?:\srecommended)?\b{NOT_DONE}
      | \bservice\srecommended\b | \bbattery(?:\s(?:health|condition|status))?\s?[:=\-–]?\s?replace\s(?:soon|now)\b
      | \bbattery\s(?:dies|drains|goes\s(?:flat|dead)|runs\s(?:out|down)|goes\sdown)\s(?:(?:very|really|pretty|quite|
        super|so|a\sbit)\s)?(?:quick(?:ly)?|fast|faster|quicker)\b
      | \bservice\s(?:the\s)?battery\b | \bneeds?\s(?:a\s)?new\sbattery\b
      | \b(?:poor|bad|weak|degraded|dying|dead)\sbattery(?:\slife)?\b | \bbattery\s(?:drain|issues?|problems?)\b
      | \bhigh\scycle\scount\b | \bcycle\scount\s(?:of\s|is\s)?(?:1\d{{3}}|[2-9]\d{{3}})\b""", X)),
    ("wear", re.compile(r"""
        \bscratch\w* | \bscuff\w* | \bwear\b | \bworn\b | \bsigns?\sof\s(?:use|wear|usage|life)\b | \bmarks?\b
      | \bmarked\b | \bblemish\w* | \bscrape[sd]?\b | \bdiscolou?r\w* | \bpeel\w* | \bcosmetic\b
      | \bgrade\s?[:\-]?\s?[cd]\b | \b[cd][\s-]grade\b | \b(?:fair|average)\scondition\b
      | \bcondition\s?(?::|-|is)?\s?(?:fair|average)\b | \bimperfection\w* | \bdings?\b | \bdinged\b | \bnicks?\b
      | \bstain\w* | \byellow(?:ed|ing)\b | \bbubbl\w*""", X)),
    # a warning with no flaw named ("sold as seen"): the API's sales with one were kept out of the clean ones, and
    # it cuts as wear; named so plainly that the judge isn't asked
    ("hint", re.compile(r"\bsold\sas\s(?:seen|is)\b | \bas\sis\b | \bread\s(?:the\s)?description\b"
                        r" | \bsee\s(?:description|below|photos)\b", X)),
]
# kinds the reader's judge must call a flaw first ("Original box, slightly damaged" is the box's); the others are
# named so plainly that a "no"/"not" before them is the only thing that undoes them
JUDGED = {"damage", "fault", "wear"}
# what a title says of the whole device, though a description says it of a part ("screen repair done", "speaker not
# working"): sold for repairs ("iPhone 12 Pro repairs", "iPhone XR repair job", "iPhone 8 needs screen repair"), dead
# or not working with only its model's words between ("iPhone 12 dead", "MacBook Air not working", "Dead iPhone 12"),
# or a part of the title saying only that ("iPhone 12 Pro Max - dead", "iPhone 11 (not working)"). A repair done isn't
# one ("screen repair done", TITLE_REPAIRED), one working badly is a fault ("MacBook Air M1 not working properly"), and
# "Faulty iPhone 12" stays a fault, as the 4 Oct tests have it
MODEL_WORD = (r"(?:\d{1,4}(?:\s?(?:gb|tb))?|pro|max|plus|mini|ultra|se|xr|xs|x|air|fe|lite|edge|note|flip|fold|5g|4g|"
              r"[a-z]\d{1,3}[a-z]?\+?|intel|inch|in|unlocked|sim[\s-]?free|black|white|blue|red|green|purple|pink|"
              r"gold|silver|grey|gray|graphite|midnight|starlight|space|rose|coral|yellow|titanium|natural|sierra|"
              r"alpine|pacific|deep|product)")
WORKS_BADLY = r"(?!\s(?:properly|correctly|right|fully|well|100|as\s(?:it\s)?should|all\sthe\stime|sometimes|" \
              r"intermittently)\b)"
NOT_WORKING = rf"(?:(?:completely|totally|fully)\s)?(?:dead{NOT_DEAD_PART}|(?:not\sworking|{DOESNT}\swork)" \
              rf"{WORKS_BADLY}|not\sturning\son)"
DEVICE_WORD = r"(?:i\s?phone|galaxy|samsung|mac\s?book|phone|laptop|handset|mobile)"
TITLE_PARTS = re.compile(rf"""
    \brepairs?\b(?!\s(?:done|completed|fixed|history|receipt|record|by|at|from|last|recently|previously|already)\b)
  | ^{NOT_WORKING}$
  | \b{DEVICE_WORD}\b(?:\s{MODEL_WORD}){{0,6}}\s(?:is\s)?{NOT_WORKING}\b
  | ^{NOT_WORKING}\s{DEVICE_WORD}\b""", X)
# ...nor a repair it's had: "iPhone 12 Pro Max (had screen repair)", "iPhone 13 - professional screen repair",
# "iPhone XR after battery repair", "iPhone 13 Pro 256GB, Apple repair" (6 Oct second check: each was priced for
# parts), though one it needs still is ("needs genuine Apple screen repair")
REPAIR_WORDS = r"(?:(?:an?|the|its|full|new|genuine|apple|official|professional|screen|battery|back(?:\sglass)?|" \
               r"glass|display|camera|port|charging|front|rear|lcd)\s){0,3}"
TITLE_REPAIRED = re.compile(rf"""
    \b(?:had|has\shad|after|new|recent|recently|previous|previously|professional(?:ly)?|apple|genuine|official|
    authori[sz]ed|certified|with)\s{REPAIR_WORDS}repair(?:ed|s)?\b(?!\s(?:needed|required|wanted|job|due))""", X)
TITLE_NEEDS_REPAIR = re.compile(rf"\b(?:needs?|needing|requires?|wants|for|in\sneed\sof)\s{REPAIR_WORDS}repairs?\b", X)
TITLE_RULES = [("parts", TITLE_NEEDS_REPAIR), ("none", TITLE_REPAIRED)] + [
    rule for kind, pattern in KIND_RULES
    for rule in ([(kind, pattern), ("parts", TITLE_PARTS)] if kind == "parts" else [(kind, pattern)])]
REPAIRS_DONE = (PAST_REPAIR, TITLE_REPAIRED)  # for parts when the repair failed (FAILED_REPAIR)
# what's wrong in words the reader's judge has no word for, though a rule above names them ("rear camera is blurry",
# "speaker blown", "boot loop", "small scrape", "grade C", "minuscule nick"): such a clause is judged again with a word
# the judge knows in their place (each kind's own: "faulty", "damaged", "scratch"), so a "no", another phone's or the
# box's still undoes it (6 Oct recheck: each was priced as clean)
SYMPTOMS = [
    ("faulty", re.compile(rf"""\bblurr?y\b | \bblurred\b | \bshak(?:y|es|ing)\b | \bunresponsive\b | \bblown\b
      | \bboot\s?loop\w* | \bshut(?:s|ting)?\s(?:down|off)\b | \bshutdowns?\b | \bpatch(?:es)?\b | \bshadows?\b
      | \bblotch(?:es)?\b | \bno\sbacklight\b | \bgr[ae]yed\s?out\b | \b(?:can'?t|cannot|can\snot)\shear\b
      | \b(?:dosen'?t|dosent|dosnt|doesent|doesen'?t|dose\snot)\s\w+ | {BLACK_SCREEN}""", X)),
    ("damaged", re.compile(r"\bburn[\s-]?in\b | \bliquid\sspill\b | \bspill(?:ed|age)?\b", X)),
    ("scratch", re.compile(r"""\bscrape[sd]?\b | \bding(?:s|ed)?\b | \bgrade\s?[:\-]?\s?[cd]\b | \b[cd][\s-]grade\b
      | \b(?:fair|average)\scondition\b | \bcondition\s?(?::|-|is)?\s?(?:fair|average)\b | \bnicks\b(?=\s*$)
      | \b(?:a|an|one|single|small|tiny|little|minor|minuscule|miniscule|slight|light|faint|wee|teeny|odd|few|some|
        couple(?:\sof)?|two|three|2|3)\s(?:\w+\s)?nicks?\b
      | \bnicks?\b(?=\s(?:on|in|to|at|near|by|along|around)\b)""", X)),
]
# a flaw word typed with a slip that the reader reads all the same (flip.checks.slipped: "craked", "chiped", "crqck")
TYPED_KINDS = {"crack": "damage", "cracked": "damage", "chipped": "damage", "dent": "damage", "dented": "damage",
               "scratch": "wear", "scratched": "wear", "scuff": "wear", "scuffed": "wear"}
SAID_AS = {"hint": "wear", "part fault": "fault"}  # the kinds a rule's own name stands for
# what a whole sentence says that its clauses don't: one part the only thing that doesn't work ("Everything works
# except Face ID", "all works apart from the speaker", "No issues other than the camera", "works fine but not face id
# scan"), unless what's wrong with it is said and is only wear ("apart from the camera, WHICH HAS A SCRATCH on the
# lens"); one crossed out in a list ("Face ID ❌", where "Scratches ❌" says there are none, and "Sim card ❌" beside
# "Box ✅ Charger ❌" says what comes with it); a battery's health as a label's answer ("battery health - service", where
# the " - " makes two clauses)
WORKS_EXCEPT = re.compile(rf"\b(?:works?|working|functional|functioning|functions|fine|no\s(?:other\s)?(?:issues?|"
                          rf"problems?|faults?)|nothing\swrong)\b[^.!?\n]{{0,30}}?\b(?:except(?:\sfor)?|apart\sfrom|"
                          rf"other\sthan|besides|bar|save\sfor|excluding|but\snot)\s(?:the\s|its\s|for\s|that\sthe\s)?"
                          rf"{FEATURES}(?:\s(?:scan|scanner|sensor|function|feature|unlock))?"
                          rf"(?=\s*$|\s*[.,;:!?)]|\s(?:and|&|or|which|that|is|isn'?t|does|doesn'?t|not)\b)", I)
SAID_OF_IT = re.compile(r"\s*,?\s*(?:which|that|as|because|since|due\sto|with|where|it\s(?:has|is)|it'?s|its|has|is|"
                        r"was)\b[^.!?\n]*", I)
ONLY_WEAR = {"wear", "not genuine"}
CROSSED_OUT = re.compile(rf"\b(?P<part>{FEATURES})\s*[:=\-–]?\s*[❌✖✗]", I)
COMES_WITH_IT = re.compile(r"(?:e-?)?sims?(?:\scards?)?|magsafe", I)  # a part that's also a thing that comes with it
WITH_IT = re.compile(rf"\b{ACCESSORIES}\s*[:=\-–]?\s*[✅❌✔✓✖✗☑]", I)  # "Box ✅", "Charger ❌": a list of what comes
BATTERY_LABEL = re.compile(rf"""\bbattery(?:\s(?:health|condition|status|state))?\s*[:=\-–]+\s*["'“”]?
    service(?:\srecommended)?\b{NOT_DONE}""", X)
REPLACED = re.compile(r"\b(?:replaced|repaired|refurbished|new\s(?:screen|battery|back|housing|display)|fitted)\b", I)
# a "no" about something wrong with a part: "no face id issues", "no signal problems" (not a fault's "no Face ID")
NO_ISSUES = re.compile(r"\bno\s(?:(?!(?:has|have|had|is|are|was|were|but|and)\b)[\w-]+\s){0,2}?(?:issues?|problems?|"
                       r"faults?)\b", I)  # not "no charger, screen HAS issues"
# a clause that only says what the flaw before it in its sentence needs ("Dead battery, NEEDS REPLACING", "No signal at
# all, MAYBE NEEDS A NEW ANTENNA"): no flaw of its own (6 Oct second check: each added wear)
NEEDS_ONLY = re.compile(r"^(?:(?:so|and|it|which|that|maybe|probably|possibly|prob|might|may|will|would|just|"
                        r"i\s(?:think|reckon|guess))\s)*(?:needs?|requires?|needing)\s(?:(?:a|an|the|to\sbe)\s)?(?:new|"
                        r"replacing|replacement|replaced|changing|changed|fixing|fixed|servicing|a\sservice|"
                        r"repair(?:ing|ed)?|looking\sat)\b(?:\s[\w'-]+){0,4}$", I)
# where a label starts in a line of them, each with its answer: "Scratches: light| Cracks: no"
NEXT_LABEL = re.compile(r"[ \t]+(?=[A-Za-z]+[ \t]*[:=])")
JOINED_LABEL = re.compile(r"(?:\b(?:or|and|nor|plus)|[&/+])[ \t]*$", I)


def labels_of(clause):
    """The labels in a line of them, each with its answer (NEXT_LABEL). One label over two flaws stays one: "Cracks or
    chips: none" is not "Cracks or" and "chips: none" (6 Oct second check: read as damage)."""
    labels = []
    for piece in NEXT_LABEL.split(clause):
        if labels and not re.search(r"[:=]", labels[-1]) and JOINED_LABEL.search(labels[-1]):
            labels[-1] += " " + piece
        else:
            labels.append(piece)
    return labels
# a label and its answer with a dash, in a line of two labels or more ("Cracks - no Scratches - light"): the " - " cuts
# a clause, so they're read as with a colon
ANSWER_WORD = r"(?:no|none|nil|nope|yes|minor|light|slight|few|some|small|tiny|faint|heavy|lots|loads|a\sfew|" \
              r"a\scouple)\b"
DASHED_LABELS = re.compile(rf"(?<=[A-Za-z])[ \t]+[-–—][ \t]+(?={ANSWER_WORD})", I)
# ...the line's other labels: "Dents: no", or "Dents no" with no colon
OTHER_LABELS = re.compile(rf"\b[A-Za-z]+[ \t]*[:=][ \t]*{ANSWER_WORD}"
                          r"|\b(?:cracks?|scratch(?:es)?|dents?|scuffs?|chips?|marks?)[ \t]+(?:no|none|nil|yes)\b", I)
DENIED_AFTER = {"free", "none", "no", "nil"}  # "scratch free", "screen burn: none", "Cracks: no"
# a label's answer, as a list of them gives it: "Cracks no Scratches MINOR", "Cracks: no Scratches: YES"
LABEL_ANSWERS = {"yes", "y", "no", "none", "nil", "nope", "minor", "light", "slight", "few", "some", "small", "little",
                 "faint", "tiny", "heavy", "lots", "loads", "many", "several", "one", "two", "three", "1", "2", "3",
                 "barely", "hardly", "very", "visible"}
ANSWER = re.compile(r"[^\w%']*(?:a\s+)?[\w%']+")  # the word after a label: ": no", " a few", " / no"
# a flaw said with how much of it there is is no label: "SMALL dent no scratches", "LIGHT scratches: no cracks"
DESCRIBED = ITEM_OPENERS | HOW_BAD | {"several", "two", "three", "2", "3", "lots", "loads", "many", "multiple", "heavy",
                                      "big", "large"}
# a "no" that's about a thing of its own or nothing else being wrong, never a label's answer: "screen cracked NO
# OFFERS", "NO BOX no charger", "screen cracked NO OTHER issues"
OWN_THINGS = NEGATED_THINGS | {"low", "lowball", "ballers", "silly", "wasters", "chancers", "scammers", "trades",
                               "trade", "exchanges", "px", "holds", "reserves", "postage", "delivery", "posting",
                               "chargers", "cables", "lead", "leads", "earphones", "headphones", "earpods", "adapter",
                               "accessories", "manual", "sim", "stylus", "pen", "warranty", "receipt", "other", "more",
                               "further", "additional", "extra", "else", "issues", "issue", "problems", "problem",
                               "faults"}
# "doesn't" typed with a slip, as a denial all the same: "Dosent have any scratches"
TYPED_DOESNT = {"dosent", "dosnt", "doesent", "dosen", "doesen", "doesn", "dsnt"}


def listed(gap):
    """Whether the words between two kinds' words go on with a list a "no" began: none ("no cracks/chips"), "or" or
    "nor" ("no cracks or chips"), "and" ("no cracks and dents", not "and a dent", "and minor dents"), or "or" and a
    word for how bad ("no cracks or visible dents", "no dents or major cracks")."""
    return gap in ([], ["or"], ["nor"], ["and"]) or \
        (len(gap) == 2 and gap[0] in ("or", "nor") and gap[1] in HOW_BAD | {"any", "other"})


def answered(words):
    """Whether these words start with an answer to a label (LABEL_ANSWERS, "a few", "a couple")."""
    return bool(words) and (words[0] in LABEL_ANSWERS or words[:2] in (["a", "few"], ["a", "couple"], ["a", "little"],
                                                                         ["a", "bit"], ["a", "lot"]))


def label_run(clause, at, later):
    """Whether the kinds' words after a "no" (from at on; later, their spans) each have an answer of their own, as in
    a list of labels: "Cracks no Scratches no", "Cracks: no Scratches: minor", "Screen cracks no back scratches yes".
    Then the "no" is the label's before it. Not "light scratches no dents" or "Scratches no cracks no dents": there it
    starts a denial of its own, as the last one has no answer."""
    run = 0
    for start, stop in later:
        if start < at:
            continue  # the "no" is its own ("Cracks no signal")
        if len(plain_words(clause[at:start])) > 2:
            break  # what follows is a part of its own
        answer = ANSWER.match(clause, stop)
        if not answer or not answered(plain_words(answer.group())):
            return False
        run, at = run + 1, answer.end()
    return run > 0


def denied_at(clause, start, stop, after, before_denied, later=()):
    """Whether the words around a kind's words (clause[start:stop]) deny them, where the next kind's own part of the
    clause starts and whether a denied list goes on to it: (denied, end, goes on). Denied by a "no"/"not" in their own
    part of the clause, from the end of the last thing matched before them (after) on ("Scratched and no cracks"
    denies the crack, not the scratch), a list a "no" goes on with ("no cracks or visible dents"), "free"/"none" right
    after ("scratch free"), or a "no" after them that's a label's answer: where the clause ends ("Cracks: no"), in a
    list of labels each with its answer (label_run: "Cracks no Scratches minor", the "no" used up so it doesn't deny
    the scratches too), or after a label's colon ("Damage: no cracks", where it goes on to deny the cracks). Not a
    "no" that starts a denial of its own ("light scratches NO DENTS") or is about a thing of its own ("screen cracked
    NO OFFERS"). later: the spans of the kinds' words after these."""
    gap = plain_words(clause[after:start])
    if before_denied and listed(gap):
        return True, stop, True
    lead = gap[max((k + 1 for k, w in enumerate(gap) if w in CLAUSE_WORDS), default=0):][-MAX_BEFORE:]
    if denied_by(without_neutral_nots(["doesnt" if w in TYPED_DOESNT else w for w in lead], False), NEGATORS):
        return True, stop, True
    answer, following = ANSWER.match(clause, stop), plain_words(clause[stop:])
    if not (answer and following[:1] and following[0] in DENIED_AFTER):
        return False, stop, False
    label = not gap[-1:] or gap[-1] not in DESCRIBED
    if following[0] != "no" or len(following) == 1 or (label and label_run(clause, answer.end(), later)):
        return True, answer.end(), False
    if label and re.match(r"[ \t]*[:=]", clause[stop:]) and following[1] not in OWN_THINGS and \
            not any(at < answer.end() for at, _ in later):
        return True, stop, True
    return False, stop, False


def overlaps(span, spans):
    return any(span[0] < stop and start < span[1] for start, stop in spans)


def clause_kinds(clause, verdict, rules=KIND_RULES):
    """The kinds one clause of a flaw sentence gives, each not denied, and the clause with what a rule names blanked
    out (so what's left is a flaw no rule names, if any: not "no charger", "dead mint" or "Cracks no Scratches no").
    verdict, the reader's judge's: "flaw" counts every kind, "symptom" the judged kinds only in the symptom's own words
    (SYMPTOMS), anything else only the kinds named so plainly that the judge isn't asked."""
    symptoms = [m.span() for _, words in SYMPTOMS for m in words.finditer(clause)] if verdict == "symptom" else []
    found = []
    for kind, rule in rules:
        if kind in JUDGED and verdict != "flaw" and not symptoms:
            continue
        for m in rule.finditer(clause):
            if kind in JUDGED and verdict != "flaw" and not overlaps(m.span(), symptoms):
                continue  # "grade C" isn't what would make "face id not set up" a fault
            if not overlaps(m.span(), [(start, end) for _, start, end in found]):
                found.append((kind, m.start(), m.end()))
    if verdict == "flaw":  # "craked screen", "few scrathes": as the judge read them
        for m in re.finditer(r"[A-Za-z]+", clause):
            kind = TYPED_KINDS.get(slipped(m.group().lower()))
            if kind and not overlaps(m.span(), [(start, end) for _, start, end in found]):
                found.append((kind, m.start(), m.end()))
    figure = battery_now(clause)
    if figure and float(figure[0]) < FLAWED_BATTERY and not any(k == "battery" for k, _, _ in found):
        found.append(("battery", figure[1], figure[2]))
    found.sort(key=lambda f: f[1])
    kinds, end, goes_on, rest = [], 0, False, clause
    for n, (kind, start, stop) in enumerate(found):
        rest = rest[:start] + " " * (stop - start) + rest[stop:]
        if kind == "none":  # a thing of its own: no list of denied flaws goes on past it ("no scratches no box CRACKED")
            end, goes_on = stop, False
            continue
        denied, end, goes_on = denied_at(clause, start, stop, end, goes_on,
                                         [(s, e) for k, s, e in found[n + 1:] if k != "none"])
        kind = SAID_AS.get(kind, kind)
        if not denied and kind not in kinds:
            kinds.append(kind)
    return kinds, rest


def unnamed_flaw(clause):
    """Whether a clause too long for the reader's judge says something's wrong in words no rule names: a word for it
    (flip.checks.PROBLEM) with no "no" of its own ("it has an issue where it gets hot", not "has never had any issues
    or problems at all since I bought it")."""
    clean = NOT_A_FLAW.sub(lambda m: " " * len(m.group()), clause)
    end, goes_on = 0, False
    for m in PROBLEM.finditer(clean):
        denied, end, goes_on = denied_at(clean, m.start(), m.end(), end, goes_on)
        if not denied:
            return True
    return False


def stood_in(text):
    """The text with each symptom (SYMPTOMS) put as a word the reader's judge knows: "camera is blurry" -> "camera is
    faulty", "small scrape" -> "small scratch"."""
    for word, symptoms in SYMPTOMS:
        text = symptoms.sub(word, text)
    return text


def judged_kinds(clause, text, rules, more=False):
    """The kinds one clause gives, as the reader's judge reads it in the listing (text). more: a clause before it in
    its sentence gave a kind, so one that only says what that needs ("needs replacing", NEEDS_ONLY) is no flaw."""
    verdict = judge(clause, text)
    if verdict == "denied":
        return []
    long = verdict == "no" and len(clause.split()) > MAX_FLAW
    labels = labels_of(clause) if verdict == "no" else []
    if long:
        # the reader's judge reads a flaw sentence of up to MAX_FLAW words; a longer clause ("There is a small crack
        # on the bottom left of the front screen and it is also cracked on the back") is still one, each kind's own
        # words checked for a "no" (6 Oct test: such clauses were dropped)
        verdict = "flaw"
    elif len(labels) > 1 and any(re.search(r"[:=]", label) for label in labels) and not OTHER_ITEM.search(clause):
        # a line of labels each with its answer ("Scratches: light Cracks: no"): the judge reads the last answer as the
        # whole line's, so each label is judged with its own (6 Oct second check: priced as clean)
        said = []
        for label in labels:
            said += [k for k in judged_kinds(label, label, rules) if k not in said]
        return said
    elif verdict == "no" and not problems_at(clause) and any(words.search(clause) for _, words in SYMPTOMS) and \
            judge(stood_in(clause), stood_in(text)) == "flaw":
        verdict = "symptom"
    said, rest = clause_kinds(clause, verdict, rules)
    if not said and verdict == "flaw" and (unnamed_flaw(rest) if long else problems_at(rest)) and \
            not battery_now(clause) and not REPLACED.search(clause) and not NO_ISSUES.search(clause) and \
            not (more and NEEDS_ONLY.match(clause)):
        said = ["wear"]  # a flaw no rule names, as the API counts it (but not what's no kind, "Charger missing", "dead
        # mint"; a battery of 80% or more; a part replaced or repaired without saying it isn't original; "no face id
        # issues"; what the flaw before it needs; nor a clause too long for the judge whose every word for a flaw has a
        # "no": not a kind the price has)
    return said


def repair_failed(text):
    """Whether a repair the text names didn't work or didn't happen for the phone (FAILED_REPAIR): "they couldn't fix
    it", "not worth fixing", not "they couldn't fix the Face ID" or "Face ID can't be fixed" (that part's fault)."""
    return any(not PART_BEFORE.search(text[:m.start()]) and not PART_AFTER.match(text, m.end())
               for m in FAILED_REPAIR.finditer(text))


def sentence_of(flaw, text):
    """The listing's sentence a quote is from (the quote itself when it isn't found there): what's said around it,
    "...for repair BUT THEY COULDN'T FIX IT"."""
    quoted = " ".join(flaw.lower().split())
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        if quoted and quoted in " ".join(sentence.lower().split()):
            return sentence
    return flaw


def sentence_kinds(flaw):
    """The kinds a whole sentence gives that its clauses don't (WORKS_EXCEPT, CROSSED_OUT, BATTERY_LABEL): not when
    it's about another phone ("my old phone worked except...")."""
    found = []
    works = WORKS_EXCEPT.search(flaw)
    about = works and SAID_OF_IT.match(flaw, works.end())
    told = clause_kinds(about.group(), "flaw")[0] if about else []  # what's wrong with it, each kind not denied
    if works and not (told and set(told) <= ONLY_WEAR):
        found.append(("fault", works))
    for crossed in CROSSED_OUT.finditer(flaw):
        if not (COMES_WITH_IT.fullmatch(crossed.group("part")) and WITH_IT.search(flaw)):
            found.append(("fault", crossed))
            break
    battery = BATTERY_LABEL.search(flaw)
    if battery:
        found.append(("battery", battery))
    return [kind for kind, m in found if not OTHER_ITEM.search(flaw[:m.start()])]


def kinds_of(flaws, text, title=False):
    """The kinds of flaw the price is cut for, from the reader's sentences (its quotes) and the listing they're from
    (title and description): each sentence split into clauses, each clause judged by the reader's own denial check,
    every kind in it counted ("Cracked screen and Face ID not working": damage and a fault), and what the whole
    sentence says ("Everything works except Face ID": a fault). A clause the reader's judge calls a flaw that no rule
    names counts as wear, as the API counts it. A battery at 80% or more, a missing charger or box, a repair done
    and gone, a network lock since undone ("now unlocked"), and anything denied ("no repairs", "not iCloud locked",
    "Find My is off") count for nothing. A carrier or network named for the phone ("Carrier: AT&T", "iPhone 13 EE") is
    a network lock unless the listing says it's unlocked (the owner's carrier rule, network_lock). title: the flaws are
    the listing's title, whose words say what's sold (TITLE_PARTS: "iPhone 12 Pro repairs" is for parts)."""
    straight = lambda said: re.sub(r"[’‘ʼ]", "'", said)  # "doesn’t" as "doesn't": the rules' apostrophe
    kinds, text = [], straight(text)
    # a battery figure apart from its label is read with it: "Battery health - 76%", "(76%)" (14 Oct review)
    for flaw in (figures_joined(straight(f)) for f in flaws):
        listing = text
        if DASHED_LABELS.search(flaw) and len(DASHED_LABELS.findall(flaw)) + len(OTHER_LABELS.findall(flaw)) > 1:
            # "Cracks - no Scratches - light", "Dents: no Cracks - minor": a line of labels, read as with colons
            labelled = DASHED_LABELS.sub(": ", flaw)
            flaw, listing = labelled, text.replace(flaw, labelled)
        around = f"{flaw} {sentence_of(flaw, listing)}"  # the quote and the listing's sentence it's from
        rules = TITLE_RULES if title else KIND_RULES
        if repair_failed(around):  # "taken for repair but they couldn't fix it": one for repairs
            rules = [("parts", rule[1]) if rule[1] in REPAIRS_DONE else rule for rule in rules]
        said = []
        for clause in parts_of(flaw):
            said += [k for k in judged_kinds(clause, listing, rules, bool(said)) if k not in said]
        said += [k for k in sentence_kinds(flaw) if k not in said]
        # the owner's carrier rule (network_lock): "Carrier: AT&T" and "iPhone 13 EE" are locks, "Was EE locked, now
        # unlocked" isn't, nor a MacBook's "Wi-Fi won't connect to other networks"
        locked = network_lock(flaw, around, listing, "network lock" in said, title)
        if locked and "network lock" not in said:
            said.append("network lock")
        elif not locked and "network lock" in said:
            said.remove("network lock")
        kinds += [k for k in said if k not in kinds]
    return kinds


# the title's own words for a for-parts or locked listing (the API's PARTS_WORDS): the API, left to read the condition
# from such a title, prices it as "parts" and finds no sales; FlipAssist asks for "good" with the parts cut instead
PARTS_WORDS = re.compile(r"\b(?:for\sparts|spares|repairs?|faulty|not\sworking|icloud\slock(?:ed)?|"
                         r"activation\slock(?:ed)?|blacklisted|bad\s(?:imei|esn))\b", I)


# ── the size, when the title doesn't give it ──────────────────────────────────────────────────────────────────────

PHONE_SIZES = {16, 32, 64, 128, 256, 512, 1024, 2048}
SSD_SIZES = {128, 256, 512, 1024, 2048, 4096, 8192}
NAMED_SSD_SIZES = SSD_SIZES | {64}  # with its word: a 2010-12 MacBook Air's "64GB SSD" ("M1 Max 64GB 2TB" is its RAM)
RAM_SIZES = {4, 8, 16, 18, 24, 32, 36, 48, 64, 96, 128}
PHONE_RAM = {"iphone": 8, "samsung": 16}  # GB, the most a phone's RAM is: its "128GB memory" is its storage, as an
# iPhone 6's "16GB memory" is
UNITS = r"(?:ram|memory|unified(?:\smemory)?|ssd|storage|flash|hdd|hard\sdrive|drive|rom|capacity|internal(?:\sstorage)?)"
# a size ("128GB", "128 gig", "256g", "1TB"), or a number a word says is one ("storage 512", "8 ram 256 ssd"); not a
# percentage. No phone weighs 128g, and "5G" is no size
NUMBER = re.compile(rf"\b(\d{{1,4}})(?:[ \t]?(gb|gigs?|gigabytes?|g|tb|terabytes?)\b|(?=[ \t]?(?:of[ \t])?{UNITS}\b)|"
                    r"\b(?![.,]\d|[ \t]?%))", I)
# a size's own word, after it on its line ("8GB RAM", "64GB of storage") or before it as a label ("Storage: 128GB",
# "RAM 8"): a spec list's next label is the next size's ("Storage: 128GB\nRAM: 6GB", 6 Oct recheck)
WORD_AFTER = re.compile(rf"[ \t]?(?:of[ \t])?({UNITS})\b", I)
WORD_BEFORE = re.compile(rf"\b({UNITS})[ \t]*(?:[:=\-–]|\bis\b|\bof\b)?[ \t]*$", I)
# "capacity" is a size's own word ("Capacity 256", "Storage capacity 128"), but not a battery's ("battery capacity 88")
BATTERY_CAPACITY = re.compile(r"\b(?:battery|batt|max(?:imum)?|health)[ \t:\-]*$", I)
MODEL_BEFORE = re.compile(r"(?:phone|\bpro|\bmax|\bair|book|\bplus|\bultra|\bmini|\bnote|\bgalaxy|\bgen|\bgeneration|"
                          r"\bseries)\s*$", I)  # the model's number: "iPhone 16 storage 128GB", "MacBook Pro 16 RAM 32GB"
PAIR = re.compile(r"\b(\d{1,4})[ \t]?(?:gb|gigs?|g)?[ \t]?/[ \t]?(?:(\d{2,4})[ \t]?(?:gb|gigs?|g|ssd)?|([1248])[ \t]?tb)\b",
                  I)  # "8/256", "16GB/1TB", "64/128GB"
# what isn't its size: a data plan's, iCloud's ("iCloud 50GB", "iCloud storage 2TB", "2TB Google Drive"), a memory
# card's ("256GB microSD", "64GB SanDisk card"), the graphics card's ("Radeon Pro 5300M 4GB", "8GB GDDR6"), or another
# model's ("Open to swaps for an iPhone 14 Pro 256GB", "Upgraded to the 15 Pro 256GB": not "Will consider part
# exchange 128GB", where no other model is named)
NOT_ITS_SIZE = re.compile(r"(?:icloud|cloud|data|plan|allowance|sd\s?card|micro\s?sd|memory\s?card|usb|stick|download|"
                          r"update|backup|photos?|google\s(?:one|drive)|dropbox|one\s?drive)(?:\s(?:storage|plan|space|"
                          r"subscription|account))?[\s:]*$", I)  # right before it: "iCloud 50GB", not "plan, 256GB"
AFTER_NOT_ITS = re.compile(r"\s*(?:of\s)?(?:data|plan|icloud|cloud|sd|sdxc|sdhc|micro|micro-?sd|card|sandisk|usb|"
                           r"download|photos?|google\s(?:one|drive)|dropbox|one\s?drive|memory\s?card|flash\s?drive|"
                           r"pen\s?drive|stick)\b", I)
# the graphics card's memory comes right after its name ("Radeon Pro 5300M 4GB", "GPU: 4GB"), never after an Apple
# chip's cores or Intel's own graphics ("7-core GPU 8GB RAM", "Intel UHD Graphics 617 8GB RAM": 6 Oct second check)
GPU_NAME = r"(?:pro|vega|rx|r9|xt|xtx|max|mobile|gt|gtx|rtx|mx|ti|geforce|radeon|quadro|" \
           r"(?!\d{1,4}\s?[gt]b\b)[a-z]{0,3}\d{2,5}[a-z]{0,2})"
BUILT_IN = r"(?<!core\s)(?<!core-)(?<!intel\s)(?<!uhd\s)(?<!iris\s)(?<!plus\s)(?<!hd\s)(?<!xe\s)(?<!integrated\s)" \
           r"(?<!apple\s)(?<!m1\s)(?<!m2\s)(?<!m3\s)(?<!m4\s)"
GPU_BEFORE = re.compile(rf"\b(?:radeon|amd|nvidia|geforce|gtx|rtx|quadro|vram|video\s(?:card|memory)|{BUILT_IN}"
                        rf"(?:gpu|graphics))\b(?:[\s-]+{GPU_NAME}\b)*[\s:(–-]*$", I)
GPU_AFTER = re.compile(r"[ \t]?(?:of[ \t])?(?:gddr\d*x?|vram|graphics|video|gpu|dedicated)\b", I)
OTHER_MODEL = re.compile(r"(?<!\bno\s)(?<!\bnot\s)\b(?:swaps?|swapping|trades?|trading|exchanges?|exchanging|px|"
                         r"part[\s-]?ex\w*)\b(?=[^.!?\n,;]*?\b(?:i\s?phone|galaxy|samsung|pixel|s\d{2}|"
                         r"z\s?(?:flip|fold)|note|mac\s?book|ipad|ps\d|playstation|xbox|switch|"
                         r"\d{1,2}\s?(?:pro|max|plus|mini|ultra|fe)\b))[^.!?\n,;]{0,40}$"
                         r"|\b(?:upgrad\w*|switch\w*|mov(?:ed|ing))\s(?:to|for)\s"
                         r"(?:the\s|an?\s|my\s|a\snew\s)?(?:i\s?phone|galaxy|samsung|pixel|s\d{2}|z\s?(?:flip|fold)|"
                         r"note|\d{1,2}\s?(?:pro|max|plus|mini|ultra|fe)?\b)[^.!?\n,;]{0,25}$", I)


def its_own(text, m):
    """Whether a size the text gives is the listing's own (NOT_ITS_SIZE, AFTER_NOT_ITS, GPU_*, OTHER_MODEL): one with
    its own word for RAM or storage after it never is the graphics card's ("Radeon Pro 560X 16GB RAM")."""
    before = text[max(0, m.start() - 40):m.start()]
    after = WORD_AFTER.match(text, m.end())
    named = after and after.group(1).lower().startswith(("ram", "unified", "ssd", "storage", "hdd", "flash", "rom"))
    return not (NOT_ITS_SIZE.search(before[-30:]) or AFTER_NOT_ITS.match(text, m.end()) or
                (GPU_BEFORE.search(before) and not named) or GPU_AFTER.match(text, m.end()) or
                OTHER_MODEL.search(before))


def sizes_in(text, kind):
    """(storage_gb, ram_gb) the text gives for this kind, each None when it gives none or more than one: a phone's
    storage ("256GB", "1TB", "128 gig", "64GB memory"; a phone's "8GB RAM" isn't it), a MacBook's SSD and RAM ("16GB
    512GB", "8/256", "16GB RAM 1TB SSD", "Memory: 16GB\nStorage: 512GB"). Not a data plan's, iCloud's, a memory card's,
    the graphics card's or another model's (its_own); "64/128GB" offers two."""
    text = text or ""
    figures = []
    for m in NUMBER.finditer(text):
        unit = (m.group(2) or "").lower()
        line = text.rfind("\n", 0, m.start()) + 1
        before = WORD_BEFORE.search(text[line:m.start()])
        after = WORD_AFTER.match(text, m.end())
        if not unit and (not (before or after) or MODEL_BEFORE.search(text[max(0, m.start() - 12):m.start()])):
            continue  # a number with no word for it: a model's ("iPhone 16 storage"), a price, a battery figure
        if its_own(text, m):
            figures.append({"n": int(m.group(1)) * (1024 if unit.startswith("t") else 1), "bare": not unit,
                            "before": (line + before.start(1), before.group(1).lower()) if before else None,
                            "after": (after.start(1), after.group(1).lower()) if after else None})
    # a word between two sizes is the first's ("8GB RAM 256GB SSD"), unless the first has a label of its own: then it's
    # the next one's label ("Storage 128GB RAM 6GB"). A size's own word after it beats a label ("RAM - 128GB SSD")
    for this, following in zip(figures, figures[1:]):
        if this["after"] and this["after"] == following["before"]:
            if this["before"]:
                this["after"] = None
            else:
                following["before"] = None
    storage, named_ram, bare_ram, either = set(), set(), set(), set()
    for figure in figures:
        n, (at, word) = figure["n"], (figure["after"] or figure["before"] or (0, ""))
        battery = word == "capacity" and BATTERY_CAPACITY.search(text[max(0, at - 20):at])
        if figure["bare"] and (not word or battery):
            continue  # a number needs a size's own word, and a battery's capacity isn't one ("battery capacity 88")
        if word.startswith(("ram", "memory", "unified")):
            if kind == "macbook" and n in RAM_SIZES:
                named_ram.add(n)
            elif kind != "macbook" and word.startswith("memory") and n > PHONE_RAM.get(kind, 16) and n in PHONE_SIZES:
                storage.add(n)  # "128GB memory": no phone has that much RAM
        elif word:
            if n in (NAMED_SSD_SIZES if kind == "macbook" else PHONE_SIZES):
                storage.add(n)
        elif kind == "macbook":
            if n in RAM_SIZES and n not in SSD_SIZES:
                bare_ram.add(n)
            elif n in RAM_SIZES:
                either.add(n)  # 128: the RAM of a MacBook whose SSD is 1TB or more ("M3 Max 128GB 2TB"), else its SSD
            elif n in SSD_SIZES:
                storage.add(n)
        elif n in PHONE_SIZES:
            storage.add(n)
    for m in PAIR.finditer(text):
        first, second = int(m.group(1)), int(m.group(2)) if m.group(2) else int(m.group(3)) * 1024
        if kind == "macbook" and first in RAM_SIZES and second in SSD_SIZES:
            named_ram.add(first)
            storage.add(second)
        elif kind != "macbook" and second in PHONE_SIZES:
            # "64/128GB", "16/32GB": two sizes on offer, so neither; "8/256", "16/512": its RAM and its storage
            storage |= {first, second} if first in PHONE_SIZES and second <= 4 * first else {second}
    for n in either:
        (bare_ram if any(size >= 1024 for size in storage) else storage).add(n)
    one = lambda found: next(iter(found)) if len(found) == 1 else None
    # the RAM named as RAM, over a figure with no word ("16GB RAM ... 8GB": 16)
    return one(storage), (one(named_ram or bare_ram) if kind == "macbook" else None)


# ── asking the prices API ─────────────────────────────────────────────────────────────────────────────────────────

# the API's refusals in FlipAssist's words: its own messages name eBay and its sites
REFUSED = {
    "NO_SALES": "Not enough recent UK sales of this model and size to price it",
    "TOO_VAGUE": "The title doesn't say which model it is: add it (like iPhone 13, Galaxy S23 or MacBook Air M1)",
    "UNAVAILABLE": "Price checks are busy or paused for a moment: try again shortly",
    "DAILY_LIMIT": "Today's price checks are used up: try again tomorrow",
    "CAP": "This month's price checks are used up",
    "UNAUTHORIZED": "The AlertFlip API refused the key (PRICES_KEY in .env)",
    "BAD_REQUEST": "The AlertFlip API couldn't use this request",
}
# the API's monthly cap is an UNAVAILABLE too, said in its message ("New price checks are paused until next month."):
# not a moment's wait, and what it saved still prices the models checked before
MONTHLY_CAP = "New price checks are paused until next month: models checked before can still be priced"


def settings():
    return (os.environ.get("PRICES_URL", "").strip(), os.environ.get("PRICES_KEY", "").strip())


def refused(code, status=None, message=None):
    """The API's refusal (its code, the HTTP status and its own message) in FlipAssist's words."""
    if code == "UNAVAILABLE" and isinstance(message, str) and "next month" in message.lower():
        return {"error": MONTHLY_CAP}
    return {"error": REFUSED.get(code) or (f"The AlertFlip API couldn't price it ({code})" if code
                                           else f"The AlertFlip API answered {status}")}


def sorted_each(flaws, text, title, description, sorter=None):
    """Each flaw with its kinds and who sorted it: [(flaw, kinds, "flip-kinds-1" or "code")], flip-kinds (sorter)
    each flaw it answers, code's rules (kinds_of) the rest."""
    each, name = [], getattr(sorter, "name", "code")
    for flaw in flaws:
        said = sorter(flaw, title, description if description is not None else ". ".join(flaws)) if sorter else None
        each.append((flaw, kinds_of([flaw], text), "code") if said is None else (flaw, said, name))
    return each


def kinds_and_by(each):
    """The kinds of every flaw (sorted_each's) and who sorted them: the model's kinds first, then code's; "code" when
    code sorted every one (no sorter, or none answered), the model's name when it sorted every one, "<model> and code"
    when both did. No flaws: None."""
    if not each:
        return [], None
    kinds = []
    for _, said, _ in sorted(each, key=lambda e: e[2] == "code"):  # stable: each one's order kept
        kinds += [k for k in said if k not in kinds]
    models = {by for _, _, by in each if by != "code"}
    model = next(iter(models), None)
    by = "code" if model is None else model if all(b != "code" for _, _, b in each) else f"{model} and code"
    return kinds, by


def sorted_kinds(flaws, text, title, description, sorter=None):
    """The flaws' kinds and who sorted them: flip-kinds (sorter) each flaw it answers, code's rules (kinds_of) the
    rest; "code" when code sorted every one (no sorter, or none answered), the model's name when it sorted every one,
    "<model> and code" when both did. No flaws: None."""
    return kinds_and_by(sorted_each(flaws, text, title, description, sorter))


def estimate(title, flaws=(), country="uk", opener=None, description=None, sorter=None, judge=None):
    """The UK price of this listing with its flaws, as the prices API answers it, trimmed to what the screen shows:
    {"price", "middle", "low", "high", "currency", "sales", "model", "item", "storage_gb", "ram_gb",
    "asked_storage_gb", "asked_ram_gb", "kind", "kinds", "cuts", "parts_price", "rough", "exact", "mode"} — or
    {"skipped": why} for a listing that isn't an iPhone, a Samsung or a MacBook, or with no API set, or {"error": what}.
    flaws: the reader's sentences (quotes); description: the seller's, for the flaws' context and the size when the
    title has none. storage_gb/ram_gb are the size it priced, asked_* the size the listing gives (None: it gives
    none). sorter: flip-kinds (flip.kinds.Sorter), asked each flaw's kinds; a flaw it can't answer, and the title,
    code sorts (kinds_of). sorted_by says which did. opener: urllib.request.urlopen's stand-in (tests)."""
    kind = kind_of(title)
    if kind is None:
        return {"skipped": SKIPPED}
    url, key = settings()
    if not url or not key:
        return {"skipped": "The AlertFlip API isn't set: add PRICES_URL and PRICES_KEY to .env"}
    title = title.strip()
    flaws = [f.strip() for f in flaws or [] if isinstance(f, str) and f.strip()]
    # the listing the flaws are judged in: the title and the description, as the reader read them
    text = f"{title}. {description if description is not None else '. '.join(flaws)}"
    each = sorted_each(flaws, text, title, description, sorter)
    kinds, by = kinds_and_by(each)
    # the title's own, read as what's sold: "Faulty iPhone 12 for parts", "iPhone 12 Pro repairs", "iPhone 12 dead"
    titled = [k for k in kinds_of([title], text, title=True) if k not in kinds]
    kinds += titled
    # fix 1 (14 Oct): damage is cut by how bad it is and the model's price tier, from FlipAssist's own measured table
    # (flip.severity), in place of the prices API's one damage cut: the API is asked without "damage", so every
    # other cut stays the API's. Not for a locked or for-parts one, which the API prices as that alone
    whole = bool(PARTS_WORDS.search(title) or {"lock", "parts"} & set(kinds))  # priced as locked or for parts alone
    own_damage = "damage" in kinds and not whole
    # the owner's battery rule (14 Oct): a battery under 80% is cut by how low it is (battery_cut), in place of the
    # prices API's one small battery cut, so the API is asked without "battery" too; not for a locked or for-parts one
    own_battery = "battery" in kinds and not whole
    # a Samsung's or a MacBook's own cuts (4 Nov): the API is asked for the clean price, and they come off it
    table = kind_table(kind, country)
    own_kinds = [k for k in kinds if k in OWN_KINDS] if table and not whole else []
    body = {"action": "price", "country": country, "title": title, "strict": True,
            "kinds": [k for k in kinds if not (own_damage and k == "damage") and not (own_battery and k == "battery")
                      and k not in own_kinds]}
    if whole:
        body["bucket"] = "good"
    in_title = sizes_in(title, kind)
    in_description = sizes_in(description or "", kind)
    if in_title[0] is None and in_description[0] is not None:
        body["storage_gb"] = in_description[0]
    if kind == "macbook" and in_title[1] is None and in_description[1] is not None:
        body["ram_gb"] = in_description[1]
    remembered = json.dumps([url, body], sort_keys=True)

    def priced(found):
        """The API's answer with a Samsung's or a MacBook's own cuts, FlipAssist's battery and damage cuts, and each
        flaw's own cut for the screen (cut_rows)."""
        start = {**found, "sorted_by": by}
        start = with_own_whole(start, table) if whole else with_own_kinds(start, own_kinds, table, own_damage)
        done = with_damage(with_battery(start, own_battery, flaws, description, title), own_damage,
                           kinds, flaws, title, judge, description)
        if (own_battery or own_kinds) and done.get("price") is not None:
            done = {**done, "price": round(done["price"])}
        rows = cut_rows(done, found.get("price"), flaw_items(each, titled, text, title, description, sorter),
                        found.get("api_factor"))
        return {**{k: v for k, v in done.items() if k not in ("api_factor", "own_parts")}, **rows}

    if remembered in _seen:
        return priced(_seen[remembered])
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "x-prices-key": key})
    try:
        with (opener or urllib.request.urlopen)(request, timeout=TIMEOUT) as response:
            answer = json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            said = json.loads(e.read().decode() or "{}").get("error") or {}
        except (ValueError, AttributeError):
            said = {}
        said = said if isinstance(said, dict) else {}
        return refused(said.get("code"), e.code, said.get("message"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        return {"error": f"Couldn't reach the AlertFlip API ({type(e).__name__})"}
    if not isinstance(answer, dict) or "price" not in answer:
        said = answer.get("error") if isinstance(answer, dict) else None
        said = said if isinstance(said, dict) else {}
        return refused(said.get("code"), "with no price", said.get("message"))
    plan = answer.get("plan")
    plan = plan if isinstance(plan, dict) else {}  # what the API read from the title (none when it didn't)
    used = answer.get("used") or []
    found = {"price": answer.get("price"), "middle": answer.get("middle"), "low": answer.get("low"),
             "high": answer.get("high"), "currency": answer.get("currency") or "GBP", "sales": answer.get("sales"),
             "model": answer.get("model"), "item": answer.get("item") if not answer.get("model") else None,
             "storage_gb": answer.get("storage_gb"), "ram_gb": answer.get("ram_gb"),
             "asked_storage_gb": body.get("storage_gb", plan.get("storage_gb")),
             "asked_ram_gb": body.get("ram_gb", plan.get("ram_gb")) if kind == "macbook" else None,
             "kind": kind, "kinds": kinds, "cuts": [c for c in used if c not in ("no flaw", "for-parts price")],
             "parts_price": "for-parts price" in used, "rough": bool(answer.get("rough")),
             "exact": bool(answer.get("exact_match")), "mode": answer.get("mode"),
             "api_factor": answer.get("factor") if isinstance(answer.get("factor"), (int, float)) else None}
    _seen[remembered] = found
    return priced(found)


def with_damage(found, own, kinds, flaws, title, judge=None, description=None):
    """The estimate with the damage cut FlipAssist measured (fix 1, 14 Oct): how bad the damage is (flip.severity: minor,
    moderate or severe; moderate when no word says) and the model's price tier, by its clean middle price, take the
    cut from data/damage_cuts.json off the API's price for its other flaws. "damage" says which: {"level", "tier",
    "cut", "rough", "from", "n", "by"}. judge(flaws, title, description, category) -> (level, by): the hybrid
    (flip.severity.judged, 14 Oct: code and Claude Haiku 5.5, Claude Sonnet 5.5 when they disagree); None: code alone.
    Not own (no damage, or locked or for parts): the API's estimate as it is."""
    found = {**found, "kinds": kinds}
    if not own or found.get("price") is None:
        return found
    level, by = judge(flaws, title, description or "", found.get("kind") or "") if judge else \
        (severity(flaws, title) or "moderate", "code")
    cut = damage_cut(found.get("kind"), "uk", found.get("middle") or found["price"], level)
    if cut is None:
        return found
    return {**found, "price": round(found["price"] * (1 + cut["cut"])),
            "cuts": [*(c for c in found.get("cuts", []) if c != "damage"), "damage"],
            "damage": {"level": level, **cut, "by": by}}


# ── a battery under 80%: the owner's cut (14 Oct) ───────────────────────────────────────────────────────────────────
# The owner: "make the battery cut bigger for under 80%", by how low it is. The prices API's own cut was about 5% (UK
# asking prices barely move for a worn battery), but a reseller buying one has to replace it.
BATTERY_CUTS = ((75, -0.10), (70, -0.15), (0, -0.20))  # a figure at or over the first number: the cut
BATTERY_NO_FIGURE = -0.15  # "battery needs a service", "drains fast": no figure under 80% given
# a range of figures ("battery 70-75%"): battery_now reads its top, the price goes by its bottom
BATTERY_RANGE = re.compile(r"\b(\d{2})\s?%?\s?(?:-|–|to)\s?(\d{2})\s?%", I)


def battery_cut(flaws, description=None, title=None):
    """FlipAssist's cut for a battery under 80% (the owner's rule, 14 Oct), by the lowest figure under 80% the flaws
    give (the description's when they give none, then the title's: "iPhone 13 128GB Battery 68%"): 75-79% -10%, 70-74%
    -15%, under 70% -20%; no figure ("battery needs a service", "drains fast"): -15%. A figure set apart from its label
    counts ("Battery health - 76%", "(76%)", on the next line). {"figure": 76 or None, "cut": -0.1}."""
    def figures_in(texts):
        found = []
        for text in texts:
            for clause in parts_of(figures_joined(text)) if text else []:
                said = battery_now(clause)
                if not said:
                    continue
                value = float(said[0])
                for low, high in BATTERY_RANGE.findall(clause):
                    if float(high) == value and float(low) < value:
                        value = float(low)
                if value < FLAWED_BATTERY:
                    found.append(value)
        return found

    figures = figures_in(flaws) or figures_in([description or ""]) or figures_in([title or ""])
    if not figures:
        return {"figure": None, "cut": BATTERY_NO_FIGURE}
    low = min(figures)
    return {"figure": int(low) if low == int(low) else low, "cut": next(c for at, c in BATTERY_CUTS if low >= at)}


def with_battery(found, own, flaws, description=None, title=None):
    """The estimate with FlipAssist's battery cut (battery_cut) off the API's price for its other flaws, unrounded
    (the damage cut, if any, comes off it next): "battery" says which, {"figure", "cut"}. Not own (no battery under
    80%, or locked or for parts): as it is."""
    if not own or found.get("price") is None:
        return found
    cut = battery_cut(flaws, description, title)
    return {**found, "price": found["price"] * (1 + cut["cut"]),
            "cuts": [*(c for c in found.get("cuts", []) if c != "battery"), "battery"], "battery": cut}


# ── a Samsung's or a MacBook's own cuts (4 Nov) ─────────────────────────────────────────────────────────────────────
# The owner, 4 Nov ("MacBook cuts are rough: the flaw percentages were measured on phones. yh do them for sumsungs and
# macbook"): every kind but damage and battery was cut by the prices API's UK table, measured on iPhones. A Samsung or a
# MacBook now has its own, measured on 3,375 UK Samsung and 3,044 UK MacBook listings against the flawless used ones of
# the same model, as the damage table is (data/kind_cuts.json): the API is asked for the clean price, and these come off
# it. Held out, a Samsung's own cuts priced its listings closer than the phones' did (wear and faults, p < 0.01); a
# MacBook's wear is the phones' -5% anyway, and its fault cut (-25%, the phones' -17%) is neither closer nor further.
KIND_CUTS_FILE = Path(__file__).resolve().parent.parent / "data" / "kind_cuts.json"
OWN_KINDS = ("fault", "network lock", "not genuine", "wear")  # the prices API's kinds a category's own table replaces


@lru_cache(maxsize=1)
def kind_tables():
    return json.loads(KIND_CUTS_FILE.read_text())["tables"]


def kind_table(category, market="uk"):
    """A category's own cuts, {"kinds": {kind: {"cut", "n", "rough", "from", ...}}}, or None: an iPhone (the prices API's
    table), or a market it has none for."""
    return kind_tables().get(f"{category}/{market}") if category else None


def own_parts(kinds, table, damaged=False):
    """What each of a Samsung's or a MacBook's kinds takes off by its own table (4 Nov), the way the prices API takes
    its table: the cut any flaw takes (wear's) counted once. {kind: the share off the price before it, or None for
    nothing more}: the worst kind its whole cut, every other kind its part on top (its cut over wear's, never a rise),
    wear nothing more beside another kind. damaged: FlipAssist's damage cut comes off too, and it has the any-flaw cut
    in it (measured against flawless ones), so every kind is just its part on top."""
    cuts = table["kinds"]
    wear = 1 + cuts["wear"]["cut"]
    serious = [k for k in kinds if k != "wear"]
    holder = None if damaged or not serious else min(serious, key=lambda k: cuts[k]["cut"])
    each = {}
    for k in serious:
        share = 1 + cuts[k]["cut"]
        each[k] = share - 1 if k == holder else min(share / wear, 1.0) - 1
    if "wear" in kinds:
        each["wear"] = None if damaged or serious else wear - 1
    return each


def with_own_kinds(found, kinds, table, damaged=False):
    """The estimate with a Samsung's or a MacBook's own cuts (own_parts) off the prices API's clean price, unrounded (the
    battery and damage cuts come off it next): "own_cuts" gives each kind's measured cut ({"cut", "n", "rough", "from"}),
    "own_parts" what each took. No kinds, no table or no price: as it is."""
    if not kinds or not table or found.get("price") is None:
        return found
    each = own_parts(kinds, table, damaged)
    factor = 1.0
    for share in each.values():
        factor *= 1 + (share or 0)
    measured = {k: {f: table["kinds"][k].get(f) for f in ("cut", "n", "rough", "from")} for k in kinds}
    return {**found, "price": found["price"] * factor, "cuts": [*found.get("cuts", []), *kinds],
            "own_cuts": measured, "own_parts": each}


def with_own_whole(found, table):
    """A locked or for-parts Samsung or MacBook with too few for-parts sales of its model to go on: the prices API's
    rough cut is replaced by the category's own measured one (4 Nov), off the clean middle price; "own_whole" says
    which, {"kind", "cut", "n", "rough", "from"}. Priced at what for-parts ones sell for, or no table: as it is."""
    used = [k for k in ("lock", "parts") if k in (found.get("cuts") or [])]
    cell = table["kinds"].get(used[0]) if table and used else None
    if not cell or found.get("parts_price") or not found.get("middle"):
        return found
    return {**found, "price": round(found["middle"] * (1 + cell["cut"])), "rough": bool(cell["rough"]),
            "own_whole": {"kind": used[0], **{f: cell.get(f) for f in ("cut", "n", "rough", "from")}}}


# ── each flaw with its own cut, for the screen (14 Oct) ──────────────────────────────────────────────────────────────
# The owner, 14 Oct ("give real description like here we had 2 flaws"): the screen gave only the damage's cut, so "cracked
# back and the balck dot in the front screen" said "Damage counted as moderate: −30%" by a price cut 42%, the black
# dot's fault cut (−17%) said nowhere. Each flaw now has its own row, its words, its kind and its cut, and the rows,
# taken in turn, make the price.

# The prices API's own UK cuts (supabase/functions/prices CUTS["co.uk"], measured on the owner's labelled listings'
# asking prices, 3 Oct), each taken as its number over clean's (the API's base "clean"). Only to split the API's one
# answer between two or more of its kinds, and only when they multiply to that answer (api_cuts).
API_CUTS_UK = {"clean": 1.05, "damage": 0.91, "fault": 0.87, "network lock": 0.95, "not genuine": 0.99,
               "battery": 1.0, "wear": 1.0, "lock": 0.65, "parts": 0.76}
# the words that join two flaws in one sentence: "cracked back and the battery is 75%", "scratches & a dent"
JOINS = re.compile(r"\s+(?:and|&|but|plus|also|as\swell\sas)\s+(?!tear\b)", I)  # "wear and tear" is one


def flaw_spans(quote):
    """Where each part of a flaw sentence is, [(start, end, clause, join)] in it: cut where the kinds are read
    (parts_of: commas, sentences, "except"; clause counts them) and at the words that join two flaws (JOINS); join is
    the word that joined the part to the one before it in its clause ("and", "but"), None for a clause's first."""
    spans, at = [], 0
    for n, clause in enumerate(parts_of(quote)):
        start = quote.find(clause, at)
        if start < 0:
            return [(0, len(quote), 0, None)]
        last, join = start, None
        for m in JOINS.finditer(clause):
            spans.append((last, start + m.start(), n, join))
            last, join = start + m.end(), " ".join(m.group().lower().split())
        at = start + len(clause)
        spans.append((last, at, n, join))
    return spans or [(0, len(quote), 0, None)]


# a part with no flaw of its own joined to the flaw before it by one of these goes on with it ("scratches top AND
# bottom", "wear on the edges AND back"); joined by "but" or "also" it's something else ("...but everything works")
GOES_ON = {"and", "&", "plus", "as well as"}


def tidy(words):
    """A flaw's words as the screen gives them: no stray comma or joining word at either end, a capital to start (not
    for a word with its own capitals: "iCloud locked", "eSIM")."""
    words = words.strip(" \t\n.,;:!-–—&")
    words = re.sub(r"^(?:(?:and|but|plus|also)\s+)+", "", words, flags=I)
    first = words.split(" ", 1)[0]
    return words if first[1:] != first[1:].lower() else words[:1].upper() + words[1:]


# the seller's words for why the price is what it is, before the flaw itself: "The price reflects the cracked back"
# is the cracked back (14 Oct, the owner's screenshot)
FRAMING = re.compile(r"^(?:(?:the\s+|my\s+|this\s+)?price\s+(?:reflects|includes|accounts\s+for|takes\s+(?:into\s+account|"
                     r"account\s+of)|is\s+(?:low(?:er)?|reduced|cheap(?:er)?)\s+(?:because\s+of|due\s+to|for)|has\s+been\s+"
                     r"(?:lowered|reduced|dropped)\s+(?:because\s+of|due\s+to|for))|(?:priced|reduced|discounted)\s+"
                     r"(?:to\s+reflect|because\s+of|due\s+to|for)|due\s+to|because\s+of)\s+", I)


def flaw_words(words):
    """A flaw's words as the screen gives them: tidied, without the seller's framing ("The price reflects the cracked
    back" -> "The cracked back")."""
    said = tidy(words)
    plain = FRAMING.sub("", said)
    return tidy(plain) if len(plain.split()) >= 2 else said  # "price reflects it" stays as said


def shown(words, kinds):
    """A flaw's words for its row: a battery flaw with its figure is just that ("78% battery health lasts all day" ->
    "78% battery health"), any other as flaw_words gives it."""
    figure = battery_now(words) if list(kinds) == ["battery"] else None
    return tidy(words[figure[1]:figure[2]]) if figure else flaw_words(words)


def split_flaw(quote, kinds, by_code, by_model=None):
    """A flaw sentence as the flaws in it, each with its kinds: "cracked back and the battery is 75%" ->
    [("Cracked back", ["damage"]), ("The battery is 75%", ["battery"])], "No charger, small scratch on the back" ->
    [("Small scratch on the back", ["wear"])]. Its parts are sorted by code's rules (by_code(words) -> kinds) and, when
    flip-kinds sorted the sentence (by_model), by it where code finds none of the sentence's kinds ("the balck dot in
    the front screen"), then by it alone, until the parts give every one of the sentence's kinds; only the sentence's
    own kinds are kept (it's what the price was cut for). A part with none joined to the flaw before it by "and" goes on
    with it ("scratches top and bottom"); otherwise it goes with the part after it in its clause ("black and white
    lines"), and with no flaw after it in its clause it's left out ("...but everything works", "No charger"). When the
    parts never give every kind, the sentence stays whole with all of them."""
    whole = [(shown(quote, kinds), list(kinds))]
    spans = flaw_spans(quote) if kinds else []
    if len(spans) < 2:
        return whole
    own = lambda said: [k for k in said if k in kinds]  # noqa: E731
    passes = [lambda words: own(by_code(words))]
    if by_model is not None:
        passes += [lambda words: own(by_code(words)) or own(by_model(words)), lambda words: own(by_model(words))]
    for classify in passes:
        said = [(span, classify(quote[span[0]:span[1]])) for span in spans]
        if {k for _, ks in said for k in ks} != set(kinds):
            continue
        out, held = [], None  # out: [start, end, kinds, clause]; held: where words waiting for a flaw start
        for (a, b, clause, join), ks in said:
            if held is not None and held[1] != clause:
                held = None  # the words with no flaw ended their clause: left out
            if ks:
                out.append([held[0] if held else a, b, ks, clause])
                held = None
            elif join in GOES_ON and held is None and out and out[-1][3] == clause:
                out[-1][1] = b  # "...top and bottom": the flaw before it goes on
            elif held is None:
                held = (a, clause)  # "black and white lines": the flaw after it starts here
        return [(shown(quote[a:b], ks), ks) for a, b, ks, _ in out]
    return whole


def flaw_items(each, titled, text, title, description, sorter=None):
    """Every flaw the price was read from, [(words, kinds, from_title)]: each sentence the reader quoted (sorted_each's)
    split into its flaws (split_flaw: code's rules first, flip-kinds for a sentence it sorted and code can't split,
    each part asked as the sentence was); then the title's own kinds (titled), with the title as their words."""
    context = description if description is not None else ". ".join(flaw for flaw, _, _ in each)
    coded, asked = {}, {}

    def by_code(words):
        if words not in coded:
            coded[words] = kinds_of([words], text)
        return coded[words]

    def by_model(words):
        if words not in asked:
            asked[words] = sorter(words, title, context) if sorter else None
        return by_code(words) if asked[words] is None else asked[words]

    items = []
    plain = lambda words: " ".join(words.lower().split()).strip(" .,;:!")  # noqa: E731
    for flaw, kinds, by in each:
        # the reader can quote the title itself ("iPhone 15 128 GB unlocked 82% BH": a battery figure): no flaw in it is
        # no flaw to list as not cut, and one that is is the title's (14 Oct, the owner's screenshot)
        is_title = plain(flaw) == plain(title)
        if is_title and not kinds:
            continue
        # flip-kinds only for two or more kinds: a sentence of one kind is cut for it whichever words say it
        model = None if by == "code" or sorter is None or len(kinds) < 2 else by_model
        items += [(words, ks, is_title) for words, ks in split_flaw(flaw, kinds, by_code, model)]
    if titled:
        items.append((title, list(titled), True))
    return items


def api_cuts(kinds, factor):
    """Each of the API's kinds with its own cut, {kind: -0.17, or None for nothing on top}, as the API takes them
    (applyCuts, base "clean": the clean premium off once, then each kind's own number; here the premium goes with the
    kind cut most, so a kind whose number is 1, wear in the UK, adds nothing on top of it). One kind has the API's whole
    answer (factor: its own, unrounded); two or more are split by its table (API_CUTS_UK) when the table makes its
    answer, to within rounding. None when it doesn't (a kind the table hasn't, a table since changed, the for-parts
    floor): the screen gives them as one cut together."""
    if len(kinds) == 1:
        return {kinds[0]: factor - 1}
    if any(k not in API_CUTS_UK for k in kinds):
        return None
    # the clean premium goes with the kind cut most, whatever order the listing gives them: "scratches and Face ID not
    # working" splits as "Face ID not working and scratches" does (14 Oct, the biggest cut first)
    holder = min(kinds, key=lambda k: API_CUTS_UK[k])
    own = {k: API_CUTS_UK[k] / (API_CUTS_UK["clean"] if k == holder else 1) - 1 for k in kinds}
    together = 1.0
    for cut in own.values():
        together *= 1 + cut
    if abs(together - factor) > 0.015:
        return None
    return {k: None if k != holder and abs(cut) < 1e-9 else cut for k, cut in own.items()}


def cut_rows(done, api_price, items, api_factor=None):
    """The price's cuts as the screen gives them: {"breakdown": [{"kinds", "words", "title", "cut", "by"}], "not_cut":
    [words]}, a row for each kind of flaw, the biggest cut first, with the flaws' own words (title: they're the
    title's). cut: the share taken off the price before it (-0.3), the rows' cuts taken in turn making the price
    (by rounding); None for no cut. by: "damage" (FlipAssist's damage cut, done["damage"] says how bad), "battery"
    (FlipAssist's battery cut, done["battery"] gives the figure), "api" (the prices API's cut for that kind), "api
    none" (one of its kinds that adds nothing on top of the one before: wear after a fault), "api together" (two or
    more of its kinds its table can't split: one cut for all; api_factor: the API's own factor, unrounded),
    "parts price" (priced at what for-parts ones sell for), "lock" (the API's rough cut for a locked or for-parts one
    with no for-parts sales), "not on top" (a locked or for-parts one's other flaws, not cut on top), "own" (a Samsung's
    or a MacBook's own measured cut, 4 Nov: done["own_cuts"] says from how many listings), "own none" (wear beside its
    other flaw: counted in that cut), "own lock" (its own measured cut for a locked or for-parts one with no for-parts
    sales), None (a kind nothing was cut for). not_cut: the words of flaws with no kind ("Charger missing")."""
    not_cut = [words for words, kinds, _ in items if not kinds]
    middle, price = done.get("middle"), done.get("price")
    if not middle or price is None:
        return {"breakdown": [], "not_cut": not_cut}
    order, said, title_only = [], {}, {}
    for words, kinds, from_title in items:
        for k in kinds:
            if k not in said:
                order.append(k)
                said[k], title_only[k] = [], True
            if words not in said[k]:
                said[k].append(words)
            title_only[k] = title_only[k] and from_title
    row = lambda k: {"kinds": [k], "words": said[k], "title": title_only[k]}  # noqa: E731
    whole = next((k for k in ("lock", "parts") if k in order), None)
    if done.get("parts_price") or whole:  # priced as for parts: one cut, first, and nothing on top of it
        first = whole or (order[0] if order else None)
        own_whole = done.get("own_whole")  # a Samsung's or a MacBook's own cut for it (4 Nov)
        by = "parts price" if done.get("parts_price") else "own lock" if own_whole else "lock"
        whole_cut = own_whole["cut"] if own_whole and not done.get("parts_price") else \
            price / middle - 1 if done.get("parts_price") or not api_factor else api_factor - 1
        return {"breakdown": [{**row(k), "cut": whole_cut, "by": by} for k in order if k == first]
                + [{**row(k), "cut": None, "by": "not on top"} for k in order if k != first], "not_cut": not_cut}
    damage, battery = done.get("damage"), done.get("battery")
    mine = done.get("own_parts") or {}  # a Samsung's or a MacBook's own cuts (4 Nov), each kind's part
    from_api = [k for k in order if k in (done.get("cuts") or []) and not (damage and k == "damage")
                and not (battery and k == "battery") and k not in mine]
    # the API's own factor, unrounded: its prices are rounded up to £5, which on a cheap phone hides a cut or doubles it
    factor = api_factor or (api_price or price) / middle
    own = api_cuts(from_api, factor) if from_api else {}
    rows = []
    for k in order:
        if damage and k == "damage":
            rows.append({**row(k), "cut": damage["cut"], "by": "damage"})
        elif battery and k == "battery":
            rows.append({**row(k), "cut": battery["cut"], "by": "battery"})
        elif k in mine:
            rows.append({**row(k), "cut": mine[k], "by": "own" if mine[k] is not None else "own none"})
        elif k in from_api and own is not None:
            rows.append({**row(k), "cut": own[k], "by": "api" if own[k] is not None else "api none"})
        elif k in from_api:
            if not any(r["by"] == "api together" for r in rows):
                rows.append({"kinds": from_api, "words": list(dict.fromkeys(w for x in from_api for w in said[x])),
                             "title": all(title_only[x] for x in from_api), "cut": factor - 1, "by": "api together"})
        else:
            rows.append({**row(k), "cut": None, "by": None})
    # the biggest cut first (14 Oct, the owner): each cut comes off what the one before left, so the main flaw shows its
    # whole amount (a cracked back is -£73 of £310 with or without a worn battery) and a smaller one what it takes after
    # it; the price is the same in any order. An API kind that adds nothing on top goes right after the API's cut it's
    # counted in, wear beside a Samsung's or a MacBook's other flaw right after the cut that has the any-flaw part in
    # it (its worst kind's, or the damage's), and a kind not cut for at all goes last
    nothing_on_top = [r for r in rows if r["by"] in ("api none", "own none")]
    goes_after = {"api none": ("api",), "own none": ("own", "damage")}
    ordered = []
    for row in sorted((r for r in rows if r["cut"] is not None), key=lambda r: r["cut"]):
        ordered.append(row)
        here = [r for r in nothing_on_top if row["by"] in goes_after[r["by"]]]
        if here:
            ordered += here
            nothing_on_top = [r for r in nothing_on_top if r not in here]
    rows = ordered + nothing_on_top + [r for r in rows if r["cut"] is None and r["by"] not in ("api none", "own none")]
    return {"breakdown": rows, "not_cut": not_cut}
