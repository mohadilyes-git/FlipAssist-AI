"""Writing an offer message with no AI: your own sentences (the phrasebook
in your style card), the price code set, the listing's flaw or good condition
in the seller's words, and the questions the listing leaves open.

Before you have any past messages it writes AlertFlip's messages (the
app's seller-message function): "Hi, would you take £235 cash for it? I'm
offering that because the battery health is 80%. I can come and collect."
Cash and collecting only on Facebook and Gumtree; on eBay and Vinted you pay
through the site and it's posted.

In a blind test on 18 Aug 2026 (252 drafts, 3 judges each) this beat the AI
drafter for a reseller with no past messages (judged best 97% of the time)
and for one whose messages repeat (88%). For a chatty reseller whose
messages all differ it was a coin flip, so the AI writes for them
(flip.message_drafter decides). Nothing here can make anything up: every
word is yours, the seller's or one of the fixed phrases below, and once you
have past messages it never offers to collect unless they do. When the seller's words
don't fit a sentence it knows how to write ("I dropped it and cracked the
back"), it writes nothing and the AI gets its turn.
"""

import re
from contextvars import ContextVar
from functools import lru_cache

from flip.catalogue import load_catalogue, model_names, words
from flip.checks import (ASKS_YOU, BATTERY_REPLACED, EMOJI, ESIM, HAD_AFTER_NEED, HOLD, LOWBALL, NO_LONGER, PAY_FIRST,
                         PROBLEM, SIGN_OFF, ends_asking)
from flip.numbers import TYPED_BATTERY, battery_worded
from flip.offers import FLAWS, LOW_BATTERY, battery_figure, condition_said
from flip.prompts import offer_words
from flip.style import HABIT_WORDS, LIKES, MENTIONS, NOT_A_PLACE, TIMES, WHEN_WORD, for_kind, opening

# the offer in plain words, for when your messages have no habit for it
NEUTRAL = {"lower": "would you take £[OFFER] for it?", "asking": "I can pay £[OFFER] for it.",
           "more": "I can pay £[OFFER] if you can hold it for me."}
GREETING = "Hi"
# with no past messages: AlertFlip's opener, offer sentence and closing. On Facebook and Gumtree you come
# and collect and pay cash...
LOCAL = {"lower": ("Hi,", "would you take £[OFFER] cash for it?", "I can come and collect."),
         "asking": ("Hi, is this still available?", "I'll pay the full £[OFFER] cash and can come and collect.",
                    "Could you hold it for me?"),
         "more": ("Hi,", "I'll pay £[OFFER] cash if you take the listing down and sell it to me.",
                  "I can come and collect.")}
# ...and on eBay, Vinted or anywhere else it's paid through the site and posted: neither is said, nor holding it
# at the asking price, which you'd just buy (26 Sep)
POSTED = {"lower": ("Hi,", "would you take £[OFFER] for it?", ""),
          "asking": ("Hi, is this still available?", "I'm happy to pay the full £[OFFER].", ""),
          "more": ("Hi,", "I'll pay £[OFFER] if you take the listing down and sell it to me.", "")}
FILLER = "Let me know what you think."
MAX_FLAW = 12  # words of the seller's to say back
# a flaw quoted from the listing that starts with a verb goes after "that it": "that it doesn't charge"
VERB_START = re.compile(r"^(?:(?:randomly|sometimes|often|occasionally|constantly|keeps?) )?"
                        r"(?:has|have|had|is|isn'?t|was|wasn'?t|does|doesn'?t|did|didn'?t|won'?t|can'?t|cannot|"
                        r"needs?|requires?|comes|works|turns|only|stopped|stops|restarts|crashes|freezes|cuts|shuts|switches|"
                        r"dies|drains|overheats|drifts|crackles|rattles|flickers|buzzes|squeaks|wobbles|lags|skips|"
                        r"sticks|leaks|hisses|clicks|beeps|hums|vibrates|struggles|slows|loses|fails)\b", re.IGNORECASE)
ARTICLE = re.compile(r"^(?:a|an|some|the|one|two|2|lots|loads|plenty|quite|both|all|several|many|multiple|"
                     r"various)\b", re.IGNORECASE)  # "given lots of scratches", not "given the lots of scratches"
# "Both cameras cracked" -> "that both cameras are cracked"; "Bit of wear" -> "a bit of wear"
QUANTITY = re.compile(r"^(?:both|all(?: (?:two|three|four|\d))?|several|many|multiple)\s+", re.IGNORECASE)
A_BIT = re.compile(r"^a?bit of\b", re.IGNORECASE)
PLURAL_FAULT = re.compile(r"^(?:[\w-]+ ){0,2}[\w-]+s (?:drift|crackle|rattle|flicker|stick|buzz|squeak|wobble|lag|leak|"
                          r"don'?t|do not|need|have|are)\b", re.IGNORECASE)  # "Both joycons drift"
# ...and one with a verb in it goes after "that the": "that the left joycon drifts", "that the hinge is stiff", "that
# the speaker could do with a clean", "that the battery might be dead" (26 Sep)
VERB_INSIDE = re.compile(r"\b(?:is|are|was|were|has|have|doesn'?t|don'?t|won'?t|can'?t|needs?|keeps|drifts|"
                         r"crackles|rattles|flickers|sticks|buzzes|squeaks|wobbles|lags|freezes|overheats|drains|cuts|"
                         r"stops|restarts|crashes|shuts|switches|dies|skips|leaks|hisses|could do with|"
                         r"(?:might|may|could|must) be)\b", re.IGNORECASE)
# a part and what's wrong with it, the seller's short way: "Screen cracked", "Back glass smashed", "Ear
# cushions worn", "Face ID not working" -> "the screen is cracked"
STATES = (r"(?:slightly |a bit |very |quite |badly |really )?(?:cracked|smashed|shattered|damaged|broken|faded|worn|"
          r"scratched|chipped|dented|marked|scuffed|bent|stuck|loose|stiff|missing|faulty|dead|swollen|lifting|"
          r"peeling|discoloured|discolored|yellowed|blank|not working|not charging|not turning on|no good)")  # (26 Sep)
# ...the part never ending on a verb of its own: "both cameras are scratched" is said as written, not "are are" (the
# fourth red team, 26 Sep), and "battery might be dead" not "might be is"
PART_STATE = re.compile(rf"^(?P<part>(?:[\w-]+ ){{0,3}}(?!(?:is|are|was|were|be|been) )[\w-]+?) (?P<state>{STATES})$",
                        re.IGNORECASE)
# ...but not a cause or how much: "Water damaged", "Slightly faded" -> "that it's water damaged"
NOT_A_PART = re.compile(r"^(?:water|liquid|sun|heat|smoke|rain|moisture|fire|slightly|very|quite|badly|lightly|heavily|"
                        r"really|somewhat|fairly|partly|partially|totally|completely|a bit|bit)$", re.IGNORECASE)
# a state first, then where or what: "Faded from washing", "Missing a few keys" -> "that it's faded from washing"
STATE_THEN = re.compile(rf"^{STATES}\s+(?:from|by|in|on|at|around|along|across|near|due|after|with|because)\b|"
                        r"^missing\s+(?:the|a|an|some|all|both|few|several|two|three|its)\b", re.IGNORECASE)  # not a deed:
# "cracked the back" (the seller's story; the AI words it)
# a lock, said as the seller says it: "iCloud locked", "Blacklisted on EE" -> "that it's iCloud locked"
LOCKED = re.compile(r"^(?:(?:icloud|activation|google|frp|network|carrier|sim) locked|locked to \w+(?: \w+)?|"
                    r"blacklisted\b.*|barred\b.*)$", re.IGNORECASE)
# "Screen: cracked", "Back: small crack": a seller's label and what's wrong
LABELLED = re.compile(r"^(?P<label>[A-Za-z][A-Za-z ]{1,24}?)\s*[:=]\s*(?P<value>\S.*)$")
# labels that only say a flaw follows: "Condition: cracked screen", "Damage: small dent"
GENERAL_LABELS = {"condition", "damage", "fault", "faults", "issue", "issues", "problem", "problems", "defect",
                  "defects", "cosmetic", "cosmetics", "note", "notes", "flaw", "flaws", "marks", "wear"}
# what isn't the flaw in a seller's quote (clean_flaw): emojis and bullets anywhere...
NOT_WORDS = re.compile("[\U0001F300-\U0001FAFF☀-➿•►▪→|*#~]+")
# the photos a seller points to: "the photos", "pic 3", "the last picture"
PHOTO_WORDS = r"(?:the |my |your )?(?:(?:last|first|second|third|fourth|final|\d+(?:st|nd|rd|th)?) )?" \
              r"(?:pictures?|photographs?|photos?|pics?|images?)\b(?:\s*\d+)?"
# ...a lead-in: "Good condition with light scratches", "Only issue: small scratch", "The only issue is a scratch"
LEAD_IN = re.compile(r"^(?:(?:in )?(?:very |really )?(?:good|great|lovely|excellent|decent|nice|fair|ok|okay|reasonable|"
                     r"used|average|working|mint|perfect|immaculate|pristine|flawless|spotless)(?: used| cosmetic)? "
                     r"(?:condition|nick|shape|order)\s*(?:with|but|apart from|except|just)?|"
                     r"(?:like|as) new\s*(?:with|but|apart from|except|just)\b|(?:the )?only (?:real )?(?:issues?|problems?|faults?|things?|flaws?|downsides?|"
                     r"damage)(?:\s+(?:is|are|being))?|(?:the )?(?:main )?downsides? (?:is|are)|only|just|condition|"
                     # "As per the photos the back is smashed": the photos aren't the flaw, nor is how the seller feels
                     # ("Unfortunately the screen is cracked") or what they ask ("see pics, screen cracked")
                     rf"as (?:per|seen in|shown in|in|you can see (?:in|on|from|by)|you'?ll see (?:in|on|from|by)) "
                     rf"{PHOTO_WORDS}|(?:as )?you can (?:see|tell) (?:in|on|from|by) {PHOTO_WORDS}|as you can see|"
                     rf"you can see|in {PHOTO_WORDS}|(?:please )?(?:see|check(?: out)?) {PHOTO_WORDS}(?:\s+for)?|"
                     r"unfortunately|sadly|annoyingly)"
                     r"\s*[:\-–,]?\s+", re.IGNORECASE)
# ...and the photos said first, a label of its own: "Seen in pics: small dent on the corner", "Shown in the photos is a
# crack on the back" (taken off before labels are read, 26 Sep)
PHOTO_LEAD = re.compile(rf"^(?:(?:as )?(?:seen|shown|pictured) (?:in|on) {PHOTO_WORDS}|pictured)"
                        r"(?:\s+(?:is|are|there'?s|there is|there are))?\s*[:\-–,]?\s*", re.IGNORECASE)
# ...and in the middle: "The back, as seen in the photos, is cracked" (the aside goes) or "back cracked as seen with a
# screen protector on" (what follows is the next thing in a run-on: the quote ends there)
PHOTO_ASIDE = re.compile(r",?\s*\bas (?:seen|shown|pictured|per)(?:\s+(?:in|on))?(?:\s+(?:the|my))?"
                         r"(?:\s+(?:last|first|second|third|\d+(?:st|nd|rd|th)?))?"
                         r"(?:\s+(?:pictures?|photographs?|photos?|pics?|images?)\b)?(?:\s+\d+)?\s*,?", re.IGNORECASE)
# a phrase that still says what's wrong (flaw_phrase): "the back" and "the Face ID" alone don't
SAYS_WRONG = re.compile(r"\b(?:locked|blacklisted|swollen|swell\w*|bulg\w*|parts|spares|repairs?|untested|unknown|replaced|"
                        r"genuine|leak\w*|bleed\w*|pixels?|water|liquid|moisture|ink|shadow\w*|unresponsive|slow|"
                        r"blurr?\w*|noisy|noise|hum\w*|faint|weak|dim|crooked|uneven|gaps?|lifting|"
                        r"no (?:sound|power|picture|signal|display|image|wifi|charge|charging|service|audio|video))\b",
                        re.IGNORECASE)
# a flaw that isn't one: "worn a few times" says how much it was worn, as clothes are
WORN_TIMES = re.compile(r"^(?:only |just )?worn (?:once|twice|a few times|a couple of times|\d+ times)\b", re.IGNORECASE)
# ...what comes after it: how it still works, an aside, a price, the next thing in a run-on ("cracked screen
# works perfect collection only leeds", "scratch on screen not noticeable when on", "costs £80 to fix")
AFTER_FLAW = re.compile(
    r"\s(?:[£$€]\s?\d|\d+\s?(?:quid|pounds)\b)|\s[-–—]\s|\s(?<!not )(?<!isn't )(?<!isnt )(?<!doesn't )(?<!doesnt )"
    r"(?<!don't )(?<!dont )(?<!won't )(?<!wont )(?<!can't )(?<!cant )(?<!don’t )(?<!won’t )(?<!can’t )(?<!doesn’t )"
    r"(?<!isn’t )"  # "speakers don't work" is a fault, not how it still works (the explaining chat, 26 Sep)
    r"(?<!stopped )(?<!stops )(?<!keeps )(?:still |fully |all )?(?:works?|working|functions?|functional)\b"
    r"|\s(?:doesn'?t|does not|won'?t|will not|don'?t|do not|didn'?t) (?:affect|effect|impact)\b"
    r"|\s(?:not|hardly|barely) (?:noticeable|visible)\b"
    r"|\s(?:nothing (?:major|serious|bad)|see (?:pics?|photos?|pictures?|images?)|selling|collection|collect|"
    r"pick ?up|no offers|unlocked|battery(?: health)? \d+|otherwise|but|so (?:price|selling|cheap|priced)|hence|which|"
    r"that|when|where|you can|costs?|would cost|to fix|to repair|price|reduced|ono|ovno|firm|everything)\b"
    # how hard it is to see, not the flaw: "crack on the corner can't tell whilst screen is on" (26 Sep: the reason
    # came out "...corner can't tell whilst screen?" once the dangling words were cut; the explaining chat's fix)
    r"|\s(?:still )?(?:usable|useable)\b|\sstill (?:fine|ok|okay|perfect|good)\b"  # "Cracked screen still usable"
    r"|\s(?:(?:you |i )?(?:can['’]?t|cannot|can not|couldn['’]?t) (?:really |even )?(?:tell|see|notice)|"
    r"only (?:visible|noticeable|seen|shows?)|means|meaning)\b"
    # praise after a comma, about another part: "Light marks on the frame, screen is perfect" (not when that part has
    # its own fault: "Cracked screen, camera not working" keeps both)
    r"|,\s(?=(?:the\s)?(?:screen|display|battery|body|frame|back|camera|cameras|everything|rest|it|phone|face id|touch id|"
    r"speakers?|sound|mic|microphone|charging|charging port|port|wi-?fi|bluetooth|buttons?|keyboard|trackpad|touch ?screen|"
    r"touch|charger|cable|lead|works?)\b"
    r"(?![^,]{0,30}?(?:\bnot\b|\bno\b|\bnever\b|n['’]t\b|\b(?:dont|doesnt|isnt|wont|cant|didnt|arent)\b|\bstopped\b|"
    r"\bbroken\b|\bfaulty\b|\bcracked\b|\bissues?\b))"
    r"[^,]{0,30}?\b(?:perfect|perfectly|fine|flawless|mint|immaculate|good|great|excellent|spotless|works?|working)\b)",
    re.IGNORECASE)
# when a mark shows, said after it ("crack whilst the screen is off", "small dent unless you look closely"); after a
# fault it's the fault's own condition and stays ("Doesn't charge unless you wiggle the cable", "Mic doesn't work while
# on speaker": the second red team, 26 Sep)
SEEN_ONLY = re.compile(r"\s(?:whilst|while|unless|only when)\b", re.IGNORECASE)
# a fault said verb first, whose "when" or "unless" is part of it: "Crackles only when volume is high"
FAULT_VERB = re.compile(r"\b(?:(?:randomly|sometimes|often|occasionally|constantly|keeps?) )?(?:stopped|stops|restarts|"
                        r"crashes|freezes|cuts|shuts|switches|dies|drains|overheats|drifts|crackles|rattles|flickers|"
                        r"buzzes|squeaks|wobbles|lags|skips|sticks|leaks|hisses|clicks|beeps|hums|vibrates|struggles|"
                        r"slows|loses|fails)\b", re.IGNORECASE)


def fault_before(text):
    """Whether the words before a "when" or "unless" say a fault (so what follows is when it happens), not a mark."""
    return bool(FAULT_SAID.search(text) or FAULT_VERB.search(text.strip()))  # "Left speaker cuts out while..."
FAULT_SAID = re.compile(r"\b(?:doesn['’]?t|does not|don['’]?t|do not|won['’]?t|will not|isn['’]?t|is not|can['’]?t|cannot|not|"
                        r"never|no longer|stops?|stopped|only (?:works?|charges?|connects?)|fails?|keeps)\b", re.IGNORECASE)
# an aside in brackets: where it shows, why it's cheap ("(visible in photos)", "(Hence low price)", "(see pics)")
BRACKET_ASIDE = re.compile(r"\s*\((?=[^)]*\b(?:photos?|pics?|pictures?|images?|hence|price|priced|reflected|see|shown|"
                           r"visible|pictured)\b)[^)]*\)", re.IGNORECASE)
# a reason that doesn't read: "the as per the photos the back is smashed", "of the the screen", "the sadly the back"
# (flaw_phrase). "the A button" reads: only a small "a" is the article
BROKEN = re.compile(r"\b(?i:the|a|an)\s+(?:(?i:the|an|as|per|of|and|but|with|which|that|is|are|was|were|unfortunately|"
                    r"sadly|annoyingly|see|you|including|includes|included|from|for|in|on|at|to|lots|both|all|each|every|"
                    r"several|many|drifts|crackles|rattles|flickers|buzzes|squeaks|wobbles|lags|freezes|overheats|drains|"
                    r"stops|restarts|crashes|dies|skips|leaks)|a)\b(?!-)"  # "the in-ear tips" reads
                    r"|\b(?i:the)\s+(?i:slightly|very|quite|badly|really|bit)\s+(?i:is|are)\b|\b(?i:the missing the)\b"
                    # ...and, should a wording miss one (26 Sep), a pronoun or the seller's deed after "the": "the it
                    # flickers", "the dropped it and cracked the back", "the bent the frame", "the fell and...", "the
                    # been repaired"
                    r"|\b(?i:the)\s+(?i:it|it'?s|its|they|this|which|fell|broke|been|being)\b"
                    r"|\b(?i:the)\s+(?i:\w+ed|bent|broken)\s+(?i:it|them|the|its)\b"
                    # ...a "will", "may", "don't", "so" or "there" after "the" ("the will need a battery replacement soon",
                    # "the don't work and motherboard...", "the so a future battery replacement...", "the there may be
                    # some minor signs of use"), and what's garbled: a ">", or a double quote or comma with no space
                    # either side ("the >Works perfectly”EXCEPT FOR FACE ID ISSUE", "the SMALL SCREEN BLACK DOT,housing
                    # have...": the fourth red team, 26 Sep; 'an "Unknown Part" message' reads)
                    r"|\b(?i:the)\s+(?i:will|would|may|might|could|should|\w+n't|dont|doesnt|didnt|wont|cant|isnt|"
                    r"arent|cannot|so|there)\b|[<>]|(?<=[A-Za-z])[\"“”,](?=[A-Za-z])")
EMOJI_IN = EMOJI  # every emoji the checks count, ⭐ and flags too
KISSES = re.compile(r"\s+x{1,3}$", re.IGNORECASE)
# a quote never ends on one of these: "...on the bottom left of the"
DANGLING = {"of", "the", "a", "an", "on", "in", "at", "to", "with", "and", "or", "near", "by", "from", "for", "is", "are",
            "has", "have", "but", "so", "its", "it", "my", "your", "very", "quite", "slightly", "&", "as"}
# paying said: once in a draft ("i can pay £300. can pay now" says it twice)
PAY_SAID = re.compile(r"\b(?:i'?ll|ill|i will|i can|can|happy to|i'?m happy to) pay\b", re.IGNORECASE)
# ...and a closing that only says when you'd pay, which goes in the offer: "Can pay today.", "I'll pay straight away",
# "happy to pay 2day" (any spelling style.TIMES knows: 26 Sep)
PAID_NOW = r"(?:right )?now|straight ?away|right away|asap"  # paying first, where you meet the seller
PAY_WHEN = re.compile(rf"^(?:(?:i|we) ?(?:'?ll|will|can)|ill|can|will|happy to|i'?m happy to) pay (?:you )?"
                      rf"(?P<when>{PAID_NOW}|{TIMES})[.!]*$", re.IGNORECASE)
# a flaw word a seller gave a capital mid-sentence ("*Has Scratches on screen"); names keep theirs
SHOUTED_FLAW = re.compile(r"(?<=\s)(?:Scratch(?:es|ed)?|Cracks?|Cracked|Dents?|Dented|Chips?|Chipped|Marks?|Scuffs?|"
                          r"Screen|Back|Battery|Health|Camera|Frame|Corners?|Edges?|Lens|Damage|Damaged|Wear|Signs)\b")
# a verb whose "on" or "up" is part of it: "won't turn on", "doesn't power up"
TURNS = re.compile(r"(?:turn(?:s|ed|ing)?|switch(?:es|ed|ing)?|power(?:s|ed|ing)?|boot(?:s|ed|ing)?|comes?|coming|"
                   r"lights?|start(?:s|ed)?|fire[sd]?)$", re.IGNORECASE)
# your own offer sentence's reason for any listing ("would you take £X given the condition?"): the listing's goes in its
# place, and with no flaw to give it goes. The whole of it, as people type it ("given the state it's in", "due to wear
# and tear", "considering the damage to it", "given it's condition", "cos of the scratches"), and only when it ends
# there: "given the condition and that I can collect today" says more (26 Sep red team: "would you take £170 it's in?",
# "...given the scratches, given a few scratches on the screen?")
REASON_LEAD = (r"given|considering|due to|owing to|what with|with|bearing in mind|taking into account|"
               r"in (?:light|view) of|on account of|"  # "bearing in mind the condition", "in light of the marks" (26 Sep)
               # "cos of", typos too
               r"(?:because|becuase|beacuse|becos|becoz|bcos|bcoz|bcuz|['’]?cos|coz|cuz|cus|['’]?cause|bc) of|"
               # ...and "for", only before the condition or state ("would you take £150 for the condition it's in?",
               # "for its condition", "for the state of it"): "for the phone" isn't a reason (26 Sep)
               # ...and not the "for" of a lead of its own: "allowing for", "to account for", "to make up for" (26 Sep
               # final recheck: "would you take £170 allowing?")
               r"(?<!allowing )(?<!allow )(?<!accounting )(?<!account )(?<!up )(?<!compensate )(?<!compensating )"
               r"(?<!allowances )(?<!allowance )for(?= (?:the|its|it['’]?s) (?:cond(?:ition|iton|tion)|state)\b)|"
               # ...and a lead that starts a clause, before "it" or "there": "as it's got a few marks", "because it's
               # damaged", "since there are some scratches" (14 Oct hunt: refused as the AI's to word, on every listing,
               # and since 14 Oct the template is the only writer, so no message at all)
               r"(?:as|since|because|becuase|beacuse|becos|bcos|bcuz|['’]?cos|coz|cuz|seeing as)(?= (?:it|there)\b)")
GENERIC_WORDS = (r"(?:(?:it['’]?s got|its got|it has|there['’]?s|there is|there are) )?"  # "given it's got a few marks"
                 r"(?:(?:the|its|it['’]?s|all the|any|some|a few|a couple of|a bit of) )?"
                 r"(?:(?:general|usual|normal|overall|current|cosmetic|visible|obvious|light|minor|small|slight|"
                 r"little|few|odd|tiny|poor|bad|rough|worn|used) ){0,2}"
                 r"(?:cond(?:ition|iton|tion)|state|wear(?: (?:and|&) tear)?|signs of (?:wear|use)|damage|flaws?|"
                 r"marks?|faults?|issues?|scratch(?:es)?|cracks?|dents?|scuffs?|chips?)"
                 r"(?: (?:and|&) (?:marks|scratches|scuffs|dents|chips|cracks|wear))?"
                 # ...and what follows them: "the state it's in", "the faults its got", "the damage to it"
                 r"(?: (?:that )?(?:(?:it['’]?s|its|it is) in|(?:it['’]?s|its|it has) got|it has)| (?:of|on|to) it)?")
# ...where it ends: the sentence or a comma, after a "mate" or "please" too ("...given the condition mate?")...
MATE_OR_PLEASE = r"(?:\s+(?:mate|m8|pal|bro|buddy|bud|fella|boss|chief|lad|hun|love|please|pls|plz|then))?"
GENERIC_END = rf"{MATE_OR_PLEASE}\s*(?:[,.?!;:]|$)"
# ...or an "if" or "or is that..." after it, or an everyday word or clause that says nothing more of the condition
# ("...given the condition tbh?", "...given the condition for a quick sale?", "wud u take 150 given the condition can
# collect 2day": refused on every listing, 26 Sep red team). Never a noun phrase that carries it on ("of the screen",
# "and age", "and that I can collect today"), nor "cash" ("given that it doesn't charge cash?")
GENERIC_CLAUSE_END = (rf"(?={MATE_OR_PLEASE}(?:\s*(?:[,.?!;:]|$)"
                      r"|\s+(?:if|or (?:is|isn['’]?t|not|no|nah|would|will|do|does))\b"
                      r"|\s+(?:tbh|tbf|to be (?:fair|honest)|tho|though|lol|ha(?:ha)+|like(?=\s*(?:[,.?!;:]|$))|at all|"
                      r"instead|as is|rather than|(?:as|so) long as|for a (?:quick|fast) sale|(?:as|and) (?:i|we)|"
                      r"(?:and |i |we )?can (?:collect|come|pick))\b))")
# ...and the state said as a clause after a lead that starts one: "it's damaged", "it's a bit worn", "it's not in the
# best condition", "it isn't in perfect nick"
STATE_WORDS = (r"(?:it['’]?s|it is)\s+(?:(?:a bit|a little|abit|quite|slightly|very|pretty|fairly|rather)\s+)?"
               r"(?:damaged|marked|scratched|scuffed|worn|used|battered|tatty|rough|cracked|dented|chipped)"
               r"|(?:it['’]?s|it is|it isn['’]?t|it is not|its)\s+(?:not\s+)?in\s+(?:the\s+)?"
               r"(?:best|perfect|great|greatest|mint|top|good|amazing)\s+(?:of\s+)?(?:condition|nick|shape)")
GENERIC_WHAT = rf"(?:{STATE_WORDS}|{GENERIC_WORDS})"
GENERIC_REASON = re.compile(rf"(?:\s*[,\-–—])?(?:\s+and)?\s+(?P<lead>{REASON_LEAD}) (?P<what>{GENERIC_WHAT}){GENERIC_CLAUSE_END}",
                            re.IGNORECASE)  # its comma or "and" before it goes with it
# ...or said first, with the offer after it: "Given the condition, would you take £[OFFER]?", "given the state of it
# would you do £[OFFER]?" (with_reason checks the offer follows: ASKS_OFFER), or as a sentence of its own after your
# offer, in your closing: "Would you take £150? Given the condition." (point_in_closing, 26 Sep)
GENERIC_FIRST = re.compile(rf"(?:^|(?<=, ))(?P<lead>{REASON_LEAD}) (?P<what>{GENERIC_WHAT})(?P<comma>\s*,)?(?:\s+|$)",
                           re.IGNORECASE)
# ...and what a reason said first can't leave behind when it goes: "Given the condition, and the fact I can collect
# today, would you..." isn't "And the fact I can collect today, would you..." (26 Sep red team)
LEFT_JOINED = re.compile(r"(?:and|but|plus|though|tho)\b", re.IGNORECASE)
# at the asking price, your own "don't mind the condition" (or "don't care about...") takes the listing's flaw ("I can
# pay £[OFFER] cash, don't mind the small crack on the back."), never a second "I don't mind ..." after it; with no flaw
# to give it goes when it comes out whole, else it stays as you typed it: never "...cash and I'm." (cut_whole, 26 Sep)
DONT_MIND_LEAD = (r"(?:don['’]?t|dont|do not) (?:really )?(?:mind|care)|"
                  r"not (?:too |that |really |at all )?(?:fussed|bothered|worried)")
GENERIC_DONT_MIND = re.compile(rf"(?P<join>(?:\s*[,\-–—])?\s*(?:\band\s+)?(?:\bi\s+)?)(?P<lead>\b(?:{DONT_MIND_LEAD}))"
                               rf"(?P<prep> about| by)? (?P<what>{GENERIC_WORDS}){GENERIC_CLAUSE_END}", re.IGNORECASE)
# ...and a reason of your own about the condition in other words ("given the cracked screen", "as it's got a few marks",
# "given the condition and that I can collect today"): the listing's never goes after it, and it never stays on a
# listing with no flaw to give. No wording, so the AI words it (26 Sep)
CONDITION_WORDS = rf"(?:{MENTIONS['condition']}|\b(?:state|smash\w*|shatter\w*|worn|bent)\b)"
OWN_REASON = re.compile(rf"\b(?:{REASON_LEAD}|because|becuase|becoz|cos|coz|cuz|cus|bcuz|as|since|seeing as|"
                        rf"taking|{DONT_MIND_LEAD})\b"  # "taking the condition into account" (26 Sep)
                        rf"[^.?!]*?{CONDITION_WORDS}", re.IGNORECASE)
# names keep their capitals when a shouted or Title Case quote is lowered
CAPITALS = {"face id": "Face ID", "touch id": "Touch ID", "hdmi": "HDMI", "usb": "USB", "usb-c": "USB-C", "sim": "SIM",
            "oled": "OLED", "lcd": "LCD", "ios": "iOS", "iphone": "iPhone", "ipad": "iPad", "airpods": "AirPods",
            "airpod": "AirPod", "macbook": "MacBook", "ps5": "PS5", "ps4": "PS4", "joy-con": "Joy-Con", "joy-cons": "Joy-Cons"}
# words a listing's title has before the flaw that aren't the flaw: "iPhone 11 64GB Unlocked back glass cracked"
# a title word with one of these after it is the flaw's own: "locked TO EE", "used WITH care"
TIED_ON = {"to", "on", "with", "by", "for", "from", "in", "at"}
TITLE_WORDS = {"unlocked", "locked", "used", "boxed", "new", "sim", "free", "simfree", "grade", "refurbished",
               "smartphone", "phone", "mobile", "apple", "samsung", "google", "sony", "nintendo", "microsoft",
               "console", "network", "ee", "o2", "vodafone", "three", "gb", "tb", "edition", "disc", "digital"}
# a part whose first word is also a model's: "disc drive", "back glass"
PART_NAMES = {"disc drive", "back glass", "home button", "power button", "side button", "charging port", "charge port",
              "face id", "touch id", "screen protector", "pro controller"}
# "It's cracked", "There's a crack": the subject the sentence gets from the seller
SUBJECT = re.compile(r"^(?:(it'?s|it is)|(it has|it'?s got|has got)|(there'?s|there is|there are))\s+", re.IGNORECASE)
# a seller's run-on: a second clause with no full stop, "the screen it turns on and off" -> "the screen – it turns...";
# not after "and", which already joins them ("...and it keeps restarting": split_phrases says each, 26 Sep)
RUN_ON = re.compile(r"(?<=\w)(?<!\band) (it|which) (?=(?:turns|keeps|won'?t|doesn'?t|can'?t|goes|stops|cuts|switches|shuts|"
                    r"restarts|freezes|lags|flickers|drains|dies|has|had|needs)\b)", re.IGNORECASE)
# "one issue with the screen" says "the issue": "given one issue..." doesn't read
ONE_ISSUE = re.compile(r"^(?:one|1)\s+(issue|problem|fault)\b", re.IGNORECASE)
# a seller's own story ("I dropped it", "my son cracked it") isn't yours to say
FIRST_PERSON = re.compile(r"\b(?:I|I'?ve|I'?m|I'?d|[Mm]y|[Mm]e|[Mm]ine|[Ww]e|[Ww]e'?ve|[Oo]ur|us)\b")
SPARES = re.compile(r"\bfor parts\b|\bspares(?:\s*(?:or|and|/|&)\s*repairs?)?\b|\brepairs?\b", re.IGNORECASE)
NEGATED_SPARES = re.compile(r"\b(?:not|no|never|isn'?t)\s+(?:sold\s+)?(?:as\s+|for\s+)?(?:spares|repairs|parts)\b",
                            re.IGNORECASE)
# adjectives on their own: "Faulty", "Slightly scratched", "Cracked and scratched", "Bent". Not "unlocked": that's a
# selling point, never a flaw (26 Sep: "Unlocked and back glass cracked" said "because it's unlocked and...")
JUST_SAYS = re.compile(r"^(?:(?:slightly|lightly|a bit|bit|very|quite|heavily|badly|really)\s+)?"
                       r"(?:cracked|scratched|scuffed|dented|chipped|faulty|bent|broken|damaged|worn|marked|stained|"
                       r"smashed|shattered|loose|stiff|dead|locked|blacklisted|swollen)"
                       r"(?:\s+(?:and|&)\s+(?:cracked|scratched|scuffed|dented|chipped|faulty|bent|broken|damaged|worn|"
                       r"marked|stained))?$"
                       r"|^(?:network\s+)?locked\s+to\s+\S+$", re.IGNORECASE)  # "that it's locked to EE"
NO_FAULT = re.compile(r"^no\s+(?:sound|power|picture|signal|display|image|wifi|charge|charging|service|audio|video|"
                      r"face id|touch id)\b", re.IGNORECASE)
# good condition in a shape this can say: "as it's in excellent condition"
GOOD_CONDITION = re.compile(r"\b((?:very |really )?(?:good|great|excellent|mint|perfect|lovely|immaculate|flawless|"
                            r"pristine|fab|fantastic|brilliant|top|decent|nice|amazing|superb|like new))\s+"
                            r"(?:condition|nick|shape)\b"
                            r"|\bcondition\s*(?:is\s*|:\s*)?(?:very |really )?(good|great|excellent|mint|perfect|"
                            r"lovely|immaculate|flawless|pristine)\b", re.IGNORECASE)
GOOD_AS_IS = re.compile(r"^(?:barely|hardly) used$|^well looked after$|^not a (?:mark|scratch) on it$", re.IGNORECASE)
# good condition in one word: "Mint", "Like new", "Immaculate, boxed"
GOOD_WORD = re.compile(r"^(?:in )?(mint|immaculate|pristine|flawless|perfect|like new|as new)(?: condition)?$", re.IGNORECASE)
# what may follow the price in "I can pay £X ...": nothing else from a question makes sense there
SAFE_TAIL = re.compile(r"^(?:\s*(?:cash(?: on collection| in hand)?|for (?:it|this|them|these)|on collection))?\s*$",
                       re.IGNORECASE)
SENTENCES = re.compile(r"(?<=[.!?…])\s+|(?<=[.!?…][\U0001F300-\U0001FAFF☀-➿])\s+")  # "£170?😊 Can collect" is two
# a greeting at the start of a sentence, as typed, with or without a comma: "Hi mate, ", "Hi mate ", "Hiya 👋 "
LEADING_GREETING = re.compile(r"(?:hi|hiya|hello|hey|alright|morning|afternoon|evening|yo)\b(?:\s+(?:mate|there|bro|"
                              r"pal|buddy|m8|hun|all))?(?:\s*[,!.?\-–—]+\s*|\s*[\U0001F300-\U0001FAFF☀-➿]+\s*|\s+|$)",
                              re.IGNORECASE)  # "$": an opener that's only "Hi" is a greeting too, so not "Hi Hi I can pay"
# a hold, as it's taken out on eBay and Vinted at the asking price (you'd just buy it): "...if you can hold it for me",
# "Could you hold it for me?"
HOLD_CLAUSE = re.compile(r",?\s+if (?:you |u )?(?:can |could |would |are able to |were able to |'re able to )?(?:hold|keep|save|"
                         r"reserve|put)\b[^.?!]*", re.IGNORECASE)
# over asking on eBay and Vinted: it's why you'd pay more there, as AlertFlip says it
TAKE_IT_DOWN = "if you take the listing down and sell it to me"
# an offer asked without its "?": "would you take £170 cash.", "how about £220 cash"
ASKS_OFFER = re.compile(r"(?:would|could|will|can|do|does|wud|wld|cud|cld|wil)\s+(?:you|u|ya|yu)\b|(?:how|what) about\b|"
                        r"any chance\b|"
                        r"would\s+£", re.IGNORECASE)
# the asking price named in an offer sentence: "I'll pay the full asking of £[OFFER]", "the full £[OFFER]"
FULL_ASKING = re.compile(r"\b(?:the\s+)?full(?:\s+asking)?(?:\s+price)?(?:\s+of)?(?=\s+£)|\basking(?:\s+price)?"
                         r"(?:\s+of)?(?=\s+£)", re.IGNORECASE)
# an over-asking offer that already says why: "if you can save it for me", "if you can keep it back for me". The
# checks' own words for it (flip.checks.HOLD), so the writer and the checks agree on what a hold is (26 Sep red team:
# "keep it till" and "save me it" were a hold here but not there; "keep in touch" was one here)
HELD = HOLD
EMOJI_END = re.compile("[\U0001F300-\U0001FAFF☀-➿]+$")
QUESTION_FILLER = {"does", "it", "come", "with", "a", "an", "the", "what", "whats", "s", "is", "any", "how", "hows",
                   "are", "all", "included", "or", "and", "original"}


def repeats(card):
    """Whether your messages repeat: you have a habit for how you open and
    how you word the offer. Then this writes them; if not, the AI does."""
    phrases = (card or {}).get("phrases") or {}
    return phrases.get("opener") is not None and phrases.get("offer") is not None


def lower_first(text):
    """'Broken back' -> 'broken back'; 'HDMI port', 'Face ID' and 'I' keep their capitals."""
    first = text.split()
    if not first or re.match(r"I\b|(?:Face|Touch) ID\b", text) or len(first[0]) > 1 and first[0].isupper():
        return text
    return text[:1].lower() + text[1:]


@lru_cache(maxsize=1)
def model_words():
    """Every word of a model's name in the catalogue, and the words titles add (TITLE_WORDS)."""
    return {word for name in model_names() for word in name.split()} | TITLE_WORDS


@lru_cache(maxsize=1)
def colour_words():
    """Every word of a colour in the catalogue: "Midnight", "Space Grey"."""
    return {word.lower() for model in load_catalogue() for colour in model.get("colours", []) for word in colour.split()}


def calmed(part):
    """A shouted or Title Case quote in lower case, names kept: "SCREEN CRACKED" -> "screen cracked",
    "Small Crack On Back" -> "small crack on back", "FACE ID BROKEN" -> "Face ID broken"."""
    letters = [w for w in re.findall(r"[A-Za-z][A-Za-z-]*", part)]
    shouted = len(letters) > 1 and all(w.isupper() for w in letters if len(w) > 1)
    titled = len(letters) > 1 and all(w[0].isupper() for w in letters) and not shouted
    if not (shouted or titled):
        return part
    lowered = " ".join(w if titled and len(w) > 1 and w.isupper() else w.lower() for w in part.split())
    for name, written in CAPITALS.items():
        lowered = re.sub(rf"\b{re.escape(name)}\b", written, lowered, flags=re.IGNORECASE)
    return lowered


def untitled(part):
    """A flaw from a listing's title without the model, its specs and its colour before it, or its storage
    after it: "iPhone 11 64GB back glass cracked" -> "back glass cracked", "iPhone 13 cracked back 128GB" ->
    "cracked back". A flaw that starts with its own part ("Screen cracked") keeps every word."""
    tokens = part.split()
    known, title = model_words(), False
    while len(tokens) > 1 and (re.search(r"\d", tokens[0]) or tokens[0].lower().strip(",-–") in known) \
            and " ".join(tokens[:2]).lower() not in PART_NAMES \
            and tokens[1].lower() not in TIED_ON:  # "PS5 disc drive not working": the drive's; "locked to EE" stays
        tokens, title = tokens[1:], True
    while title and len(tokens) > 1 and tokens[0].lower().strip(",-–") in colour_words():  # "iPhone 13 Midnight ..."
        tokens = tokens[1:]
    while len(tokens) > 1 and re.fullmatch(r"\d+\s?(?:gb|tb)|[£$€]?\d+(?:\.\d+)?", tokens[-1], re.IGNORECASE):
        tokens = tokens[:-1]
    return " ".join(tokens)


def clean_flaw(part):
    """A seller's quote cut to the flaw, every word kept as it was written:
    no emojis, bullets or kisses, no lead-in ("Good condition with", "Only
    issue:"), no model before it or aside after it ("...still works fine",
    "...see pics", "...costs £80 to fix", "...that you can only see"), a
    label put in order ("Screen: cracked" -> "Screen cracked", "Back: small
    crack" -> "small crack on the back"), and shouting or Title Case lowered."""
    part = BRACKET_ASIDE.sub("", part)  # "(visible in photos)", "(Hence low price)": an aside, not the flaw
    part = re.sub(r"\s+", " ", NOT_WORDS.sub(" ", part)).strip(" .,!;:-–—")
    part = PHOTO_LEAD.sub("", part, count=1)
    aside = PHOTO_ASIDE.search(part, 1)
    if aside:  # the aside goes when the flaw follows it, else the quote ends there
        rest = part[aside.end():]
        joined = ", " if aside.group().rstrip().endswith(",") and aside.group().lstrip().startswith(",") else " "
        part = f"{part[:aside.start()]}{joined}{rest}" if VERB_INSIDE.search(rest) or \
            re.search(STATES, rest, re.IGNORECASE) or PROBLEM.search(rest) else part[:aside.start()]
        part = re.sub(r"\s+", " ", part).strip(" .,!;:-–—")
    labelled = LABELLED.match(part)
    if labelled:
        label, value = labelled.group("label").strip(), labelled.group("value").strip()
        part = value if set(label.lower().split()) & GENERAL_LABELS else \
            f"{label} {value}" if re.fullmatch(STATES, value, re.IGNORECASE) else f"{value} on the {label.lower()}"
    part = untitled(part)  # "iPhone 13 as you can see it is scratched up": the lead-in after the model, before the cut
    for _ in range(2):  # "In used condition with marks", "Only issue: small scratch"
        part = LEAD_IN.sub("", part, count=1)
    aside = AFTER_FLAW.search(part, 1)  # after the flaw starts: "Selling for parts" is one
    while aside and re.match(r"\swhen\b", aside.group(), re.IGNORECASE) and fault_before(part[:aside.start()]):
        aside = AFTER_FLAW.search(part, aside.end())  # a fault's own "when": "Crackles only when volume is high"
    part = (part[:aside.start()] if aside else part).strip()
    if aside and part.lower().endswith(" only") and not fault_before(part):  # "crack on the back only [when ...]"
        part = part[:-len(" only")].rstrip()
    seen = SEEN_ONLY.search(part, 1)  # when it shows, after a mark: "dent on the corner unless you look closely"
    if seen and not fault_before(part[:seen.start()]):  # not a fault's condition: "Doesn't charge unless you wiggle it"
        part = part[:seen.start()].strip()
    part = KISSES.sub("", untitled(calmed(part))).strip(" .,!;:-–—")
    part = LEAD_IN.sub("", part, count=1)  # "iPhone 14 Pro Max just back cracked": the lead-in after the model
    tokens = part.split()
    while tokens and tokens[-1].lower() in DANGLING and not (  # "Won't turn on": the "on" is the fault
            tokens[-1].lower() in ("on", "off", "up") and len(tokens) > 1 and TURNS.match(tokens[-2])):
        tokens = tokens[:-1]
    return " ".join(tokens)


# dust inside a part, said one way: "small bit of dust under camera lens", "Dust inside back camera x" -> "that there's
# dust under the camera lens", "that there's dust inside the back camera" (the third red team, 26 Sep: "because dust
# under the camera lens" had no verb, and the seller's capital, kiss and aside came with it). The place ends on a
# part's name, before any comma or what comes next; dust in anything else ("Camera has dust in it") is said as written.
# The verbs are the ones the checks read as dust (flip.checks.DUST), so the message says no more than the listing
DUST_VERBS = r"(?:shows?|affects?|causes?|stops?|blocks?|blurs?|ruins?|spoils?|makes?)"  # what it does (DUST_DOES)
DUST_IN = re.compile(r"\b(?P<what>dust(?:\s+(?:spot|particle|speck)(?P<many>s)?)?)(?:\s+(?:has|have|had|is))?"
                     r"(?:\s+(?:got|gotten|gone|come|crept|trapped|stuck))?\s+(?P<prep>inside|into|in|underneath|under|"
                     r"behind)\s+(?:(?:the|a|an|its|my|his|her|their|your)\s+)?(?P<place>(?:(?!(?:and|but|or|so|which|"
                     r"that|when|where|while|whilst|of|on|at|to|from|with|by|between|is|are|was|has|have|"
                     rf"{DUST_VERBS})\b)"  # no verb in the place: "dust in lens makes camera blurry" is in the lens
                     r"[a-z][\w-]*\s+){0,3}(?:cameras?|lens(?:es)?|screen|display|port|speakers?|grill|grille|mesh|mic|"
                     r"microphone|earpiece|module|sensor|bump|glass|housing|flash|protector|keyboard|trackpad|vents?|"
                     r"phone))\b", re.IGNORECASE)
# ...and what the dust does, said straight after the place and to the end of its clause: "dust in lens shows on photos",
# "dust in charging port stops it charging" -> "that dust in the lens shows on photos" (red team 4, 26 Sep: "because
# there's dust in the charging port" lost it). Not "makes no difference", nor a clause with more in it ("...and",
# "...but", "...when"), which said_as reads as before
DUST_DOES = re.compile(rf"\s+({DUST_VERBS}(?:\s+(?!(?:no|not|nothing|never|and|but|or|so|which|that|when|where|while|"
                       r"whilst|if|unless|otherwise|though|although|still|x{1,3})\b)[\w'’%-]+)+)"
                       r"(?=\s*(?:[^\w\s]|$)|\s+x{1,3}\s*$)", re.IGNORECASE)


def dust_inside(found):
    """DUST_IN's wording, in lower case whatever the seller's capitals (names kept: "Face ID"), "into" said as
    "inside": "Dust has got into the back camera" -> "that there's dust inside the back camera", "dust spots in
    camera" -> "that there are dust spots in the camera" (the seller's own word for it stays). What it does stays
    too (DUST_DOES): "Dust in lens shows on photos" -> "that dust in the lens shows on photos"; "makes" only with
    what it makes them, as code's own 8-word quote may stop short: "dust in camera makes selfies blurry", not "...makes
    photos a bit" (red team 4, 26 Sep)."""
    def lowered(words):  # "Face ID camera", not "face id camera"
        words = " ".join(words.lower().split())
        for name, written in CAPITALS.items():
            words = re.sub(rf"\b{re.escape(name)}\b", written, words, flags=re.IGNORECASE)
        return words
    what = " ".join(found.group("what").lower().split())
    there = "there are" if found.group("many") else "there's a" if what != "dust" else "there's"
    prep = found.group("prep").lower()
    where = f"{'inside' if prep == 'into' else prep} the {lowered(found.group('place'))}"
    does = DUST_DOES.match(found.string, found.end())
    said = lowered(does.group(1)) if does else ""
    last = said.split()[-1] if said else ""
    if said and last not in DANGLING and (not said.startswith("make") or SAYS_WRONG.search(last)):
        subject = f"a {what}" if there == "there's a" else what  # "that a dust particle in the lens shows..."
        return f"that {subject} {where} {said}"
    return f"that {there} {what} {where}"


# a battery it needs, not one it's had (26 Sep: "Needs a new battery" was said "the battery has been replaced"), in the
# seller's words with its "will" or "may" and how sure kept, and its verb agreeing with "it" (the fourth red team, 26 Sep:
# "because it need a new battery soon", "because the will need a battery replacement soon"): "Needs a new battery" ->
# "that it needs a new battery", "need new battery" -> "that it needs new battery", "it'll need a new battery soon" ->
# "that it'll need a new battery soon", "will most likely need a battery replacement" -> "that it will most likely need a
# battery replacement", "definitely need a battery replacement" (the reader's quote, its "will" cut off) -> "that it
# definitely needs a battery replacement", "Due a new battery" -> "that it's due a new battery"
BATTERY_NEEDED = re.compile(rf"\b(?P<will>(?:it['’]?ll|itll|it will|will|would|may|might|could|should)\s+)?"
                            r"(?P<how>(?:(?:most|more than)\s+)?(?:\w+ly|soon|also|still)\s+)?"
                            r"(?P<need>needs?|requires?|could do with|could use|needing|"
                            rf"in need of|due(?: for)?)\s+(?P<what>(?:a\s+)?(?:brand\s+)?(?:new|replacement)\s+"
                            rf"{TYPED_BATTERY}s?|(?:a\s+)?{TYPED_BATTERY}\s+(?:replacement|change|swap))"
                            r"(?P<when>\s+(?:soon|shortly|at some point|eventually|in (?:the )?(?:near )?future))?\b",
                            re.IGNORECASE)


def battery_needed(found):
    """BATTERY_NEEDED's wording, lowered, with "it" before it (see there). No word is added but "it": the checks read
    "needs a new" as more than the listing's "need new battery" says."""
    will, how, need, what, when = (" ".join((found.group(name) or "").lower().split())
                                   for name in ("will", "how", "need", "what", "when"))
    rest = f"{what} {when}".strip()
    if need.startswith(("needing", "in need", "due")):
        return f"that it's {need} {rest}"  # "that it's due a new battery"
    if not will and need in ("need", "require"):
        need += "s"  # "need new battery" -> "that it needs new battery"
    will = re.sub(r"^(?:it['’]?ll|itll)\b", "it'll", will)
    said = " ".join(word for word in (will, how, need, rest) if word)  # "it'll need...", "will soon need..."
    return f"that {said}" if said.startswith("it") else f"that it {said}"


# a replaced battery, said "the battery has been replaced", but not after a need in the same clause, nor before a "may"
# or "would": "Just needs screen or battery replaced", "it needs reparing and a battery replacement", "a battery
# replacement may be worth considering" (the fourth red team, 26 Sep: each was said "the battery has been replaced"; the
# seller's own words say it, "that it needs screen or battery replaced")
REPLACED = re.compile(rf"\b(?:{BATTERY_REPLACED})", re.IGNORECASE)
NEED_BEFORE = re.compile(r"\b(?:needs?|needing|requires?|in need of|could do with|due(?!\s+to\b))\b[^.?!,;]*$",
                         re.IGNORECASE)
MAYBE_AFTER = re.compile(r"\s+(?:(?:is|will be)\s+)?(?:would|may|might|could|should)\b", re.IGNORECASE)
# flaws said one way, whatever the seller's words (23 Sep): what the iPhone itself reports, a replaced battery,
# eSIM only, an iOS limit, untested. Each is (what it says, how it's said); {0} is the first group the pattern takes
PART = r"(battery|screen|display|camera)"
SAID_AS = [
    (re.compile(rf"\bunable to verify\b.*\bgenuine (?:apple )?{PART}", re.IGNORECASE), "that the iPhone can't verify the {0} is genuine"),
    (re.compile(r"(?:\breplaced\b.*\bwith an? )?\bnon[- ]?(?:apple|genuine|original) batter(?:y|ies)\b", re.IGNORECASE),
     "that the battery has been replaced with a non-Apple one"),
    (re.compile(rf"\bnon[- ]?(?:apple|genuine|original) {PART}", re.IGNORECASE), "that it has a non-Apple {0}"),
    # a battery the seller needed and then had: "Was due a new battery so had one fitted" (the fourth red team, 26 Sep)
    (re.compile(rf"\b(?:{HAD_AFTER_NEED})", re.IGNORECASE), "that the battery has been replaced"),
    # a battery it needs (BATTERY_NEEDED), or "Battery replacement needed" -> "that a battery replacement is needed" (not
    # "due to", which says why one was fitted: "a battery replacement due to low battery health")
    (BATTERY_NEEDED, battery_needed),
    (re.compile(rf"\b{TYPED_BATTERY}s? replacement (?:is |will be )?(needed|required|due(?!\s+to\b)|recommended)\b",
                re.IGNORECASE), "that a battery replacement is {0}"),
    (re.compile(rf"\b(?:new|replacement) {TYPED_BATTERY}s? (?:is |will be )?(needed|required|due(?!\s+to\b)|recommended)\b",
                re.IGNORECASE), "that a new battery is {0}"),
    (REPLACED, "that the battery has been replaced"),  # not after a need in its clause (said_as): NEED_BEFORE
    (re.compile(rf"\b{PART}\b.*\bunknown\b|\bunknown {PART}", re.IGNORECASE), "that the {0} shows as an unknown part"),
    (ESIM, "that it's eSIM only"),
    (re.compile(r"\bup to i ?os ?(\d+)", re.IGNORECASE), "that it only runs up to iOS {0}"),
    (re.compile(r"\blast (?:i ?os |software )?(?:version|update)\b|\bno longer (?:gets?|getting|receives?|receiving|supported|"
                r"updated)\b", re.IGNORECASE), "that it doesn't get iOS updates any more"),
    (re.compile(r"\buntested\b|\bnot (?:been )?tested\b|\b(?:haven|hasn)['’]?t (?:been )?tested\b", re.IGNORECASE),
     "that it's untested"),
    (re.compile(r"\b(?:can['’]?t|cannot|can not|unable to) confirm\b(.*)$", re.IGNORECASE), "that you can't confirm{0}"),
    (re.compile(r"\bonly charges? (?:wireless|on (?:an? |the )?wireless|with (?:an? |the )?wireless)", re.IGNORECASE),
     "that it only charges wirelessly"),
    (re.compile(r"\b(?:not sure|unsure|no idea|don['’]?t know|do not know)\b.*\bwrong\b", re.IGNORECASE),
     "that you're not sure what's wrong with it"),
    (re.compile(rf"\b(?:(?:would|will) )?{NO_LONGER}", re.IGNORECASE), "that it {whole}"),
    (DUST_IN, dust_inside),
    (re.compile(r"\b((?:front |back |rear |selfie |main |wide |ultra wide )?cameras?) (?:is |goes |went |just |shows? |"
                r"showing |stays? )?black\b", re.IGNORECASE), "that the {0} shows black"),
    (re.compile(r"\b(screen|display) (?:goes|went|turns|turned|stays|stayed|going|turning) black\b", re.IGNORECASE),
     "that the {0} goes black"),
]


MIXED = "mixed"  # one of SAID_AS with something else wrong: no plain wording, so the AI (or you) words it


def said_as(part):
    """One of the flaws said one way (SAID_AS), when it's all the quote says:
    "Battery changed 4 months ago" -> "that the battery has been replaced",
    "eSIM only" -> "that it's eSIM only". MIXED for one that says more
    ("eSIM only and a small scratch"), None for any other quote."""
    for pattern, said in SAID_AS:
        found = pattern.search(part)
        if not found or pattern is REPLACED and (NEED_BEFORE.search(part[:found.start()]) or
                                                 MAYBE_AFTER.match(part, found.end())):
            continue  # "Only need screen replacement and battery replacement": needed, so in the seller's words
        rest = part[:found.start()] + " " + part[found.end():]
        if PROBLEM.search(rest):
            return MIXED
        if callable(said):  # worded from what it found: dust_inside
            return said(found)
        whole = re.sub(r"^(?:as|because|since|so)\s+", "", found.group().strip(" .,;:!"), flags=re.IGNORECASE)
        group = next((g for g in found.groups() if g), "") if found.groups() else ""
        return said.format(group.lower().rstrip(" .,;:!") if group else "", whole=whole)
    return None


# a part the seller names with no "the": "scratches on screen", "a crack at bottom right corner", "damage to back"
# -> "on the screen", "at the bottom right corner", "to the back" (26 Sep blind review: "on screen" read as copied);
# not "speaker": "doesn't work while on speaker" is the phone on speakerphone. Also "all over back", "chip by camera",
# "line down screen", "crack in middle of screen", "dent on power button", "back of phone" (the third red team, 26 Sep:
# the bare parts it missed); not "round": "has round corners". Not "inside" either: a listing's "inside screen" is a
# foldable's inner screen, "inside lid" a laptop's ("inside screen cracked" was said "the inside the screen is
# cracked": red team 4, 26 Sep)
BARE_PART = re.compile(r"\b(?P<prep>on|at|to|in|near|around|across|along|of|under|underneath|behind|over|by|down|"
                       r"beside|between)\s+(?P<part>(?:home|power|side|volume)\s+buttons?|charg(?:ing|e)\s+(?:port|case)|"
                       r"(?:cover|inner|outer|main)\s+(?:screen|display)|top|bottom|left|right|middle|centre|center|"
                       r"back|front|rear|screen|display|frame|lens|lenses|camera|cameras|corner|corners|side|sides|edge|"
                       r"edges|bezel|bezels|case|casing|housing|glass|port|button|buttons|rim|keyboard|"
                       r"trackpad|lid|hinge|headband|stem|stems|bud|buds|earcup|earcups|phone)\b(?P<of>(?=\s+of\b))?",
                       re.IGNORECASE)
# where the seller's bare words are right, and "the" would break them (keeps_bare; the third red team, 26 Sep):
# ...the far end of a span: "from corner to corner", "top to bottom", "top left to bottom right", "side by side"
# (not "on the corner to the left of the camera", which says where)
PLACE_WORD = re.compile(r"(?:top|bottom|left|right|sides?|corners?|edges?|front|back)$", re.IGNORECASE)
OPPOSITE_ENDS = [{"top", "bottom"}, {"left", "right"}, {"front", "back"}]
# ...but no span starts at a place a preposition already puts somewhere: "small mark on back to right side", "chip on
# edge to bottom" say which way, "to the right side" (red team 4, 26 Sep)
PLACED_BEFORE = re.compile(r"\b(?:on|at|in|near|by|across|along|around|over|under|behind)\s+(?:the\s+)?\w+\s+$",
                           re.IGNORECASE)
# ...a feature's own name: "built in camera", "built-in camera", "under display camera", "on screen keyboard", "always
# on display" ("the under the display camera" is no name). "Always" names the display only: "line always at bottom of
# screen" and "black spot always on screen" say when (red team 4, 26 Sep)
NAME_BEFORE = re.compile(r"\bbuilt[\s-]*$", re.IGNORECASE)
ALWAYS_BEFORE = re.compile(r"\balways[\s-]*$", re.IGNORECASE)
NAMED_AFTER = re.compile(r"\s+(?:camera|cam|fingerprint|sensor|scanner|reader|keyboard|keys)\b", re.IGNORECASE)
# ...a shop's display, not the screen: "from being on display in store", "has been on display" (not "left": "small
# scratch top left on display" is the side, red team 4, 26 Sep)
SHOWN_BEFORE = re.compile(r"\b(?:being|been|was|were|put|kept|sat|sitting)\s*$", re.IGNORECASE)
SHOWN_AFTER = re.compile(r"\s+(?:in|at)\s+(?:an?\s+|the\s+|our\s+|my\s+)?(?:store|shop|showroom|window)\b", re.IGNORECASE)
# ...after "of", a part that says what kind of flaw follows, or glass that a piece is of: "signs of screen burn", "a bit of
# case wear", "lots of back glass cracks", "a piece of glass missing" ("the screen burn" reads as one named before)
DESCRIBES_AFTER = re.compile(r"\s+(?:(?:back|front|rear|camera|screen|display)\s+)?(?:glass\s+)?(?:burn(?:-?in)?|"
                             r"bleed(?:ing)?|wear|scratch(?:es)?|cracks?|marks?|scuffs?|damage|dents?|chips?|lines?|"
                             r"ghosting|yellowing|discolou?ration|peeling)\b", re.IGNORECASE)
MATERIAL_BEFORE = re.compile(r"\b(?:pieces?|bits?|chips?|shards?|slivers?|made)\s+$", re.IGNORECASE)
# ...the "on" of a verb, and the "down" of one or of a name: "wont turn on screen cracked" is two faults run on, not
# "turn on the screen"; "power on button", "shuts down screen goes black", "volume down button", "upside down" (a
# "mute switch on side" is a part, so "switch" counts only as a verb: "won't switch on"; and "comes on" only when it's
# the phone's, "it comes on screen flickers": a "green line comes on screen" is on the screen, red team 4, 26 Sep)
TURNED_ON = re.compile(r"\b(?:turn(?:s|ed|ing)?|switch(?:es|ed|ing)|power(?:s|ed|ing)?|boot(?:s|ed|ing)?|"
                       r"(?:it|won['’]?t|wont|doesn['’]?t|doesnt|don['’]?t|dont|can['’]?t|cant|cannot|not|never)"
                       r"\s+(?:comes?|coming)|"
                       r"(?:won['’]?t|wont|doesn['’]?t|doesnt|don['’]?t|dont|can['’]?t|cant|cannot|not|never|to|will)"
                       r"\s+switch)\s*$", re.IGNORECASE)
TURNED_DOWN = re.compile(r"\b(?:shut(?:s|ting)?|slow(?:s|ed|ing)?|power(?:s|ed|ing)?|turn(?:s|ed|ing)?|volume|upside|"
                         r"face)\s*$", re.IGNORECASE)
# ...and a downside said in two words, "the only down side is a small chip" (red team 4, 26 Sep)
DOWNSIDE_AFTER = re.compile(r"\s+(?:is|are|was|were|being|to)\b", re.IGNORECASE)
# ...and "in case" ("kept in case", "just in case"), but not for what goes in its case: "won't charge in the case"
IN_CASE_BEFORE = re.compile(r"\b(?:charg(?:e|es|ed|ing)|sits?|sitting|fits?|fitting)\s*$", re.IGNORECASE)
# "phone" is a part only after "of", "on the back of the phone": "Mic doesn't work on phone calls" stays as it is
PHONE_THING = re.compile(r"\s+(?:calls?|number|case|cases|contract)\b", re.IGNORECASE)
# a part said with what was done to it: "it has bent the frame at the top", "Cracked the back glass" -> "that the frame
# is bent at the top" (26 Sep: "it has bent the frame" went to the AI, which pasted it back as if the buyer bent it)
DONE_TO_PART = re.compile(r"^(?:it\s+)?(?:has\s+|'s\s+|have\s+)?(?P<state>bent|cracked|chipped|dented|smashed|scratched|"
                          r"scuffed|broken|snapped|warped)\s+(?:the|its)\s+(?P<part>(?:(?:back|front|rear|left|right|top|"
                          r"bottom|camera|side|corner|screen)\s+)?(?:frame|screen|back|glass|corner|corners|edge|edges|"
                          r"side|sides|lens|camera|housing|case|casing|rim|bezel|hinge|lid|chassis|port|button|buttons|"
                          r"protector))"  # "Has cracked the screen protector" (26 Sep)
                          # only where on it may follow ("at the top"): anything more ("...and the lens is") isn't
                          # this one flaw, so it goes on to the other wordings (or the AI)
                          r"\b(?P<rest>\s+(?:at|on|in|near|by|around|along|across)\s+(?:the\s+)?(?:(?:top|bottom|"
                          r"left|right|back|front|side|corner|edge|middle|centre|center)\b\s*){1,3}"
                          r"(?:corner|edge|side|of the (?:screen|back|frame|phone))?)?[\s.,!;:]*$", re.IGNORECASE)
# how the seller says it happened, at the end of a flaw: "scuffs on the charging case from keys" -> "scuffs on the
# charging case" (26 Sep blind review: clunky from the buyer; the reason is the flaw, not its story). The hedge, denial
# or comma before it goes with it: "Few marks probably from the case", "Crack on the back isn't from a drop", "Few
# scuffs on the corners, from the case" -> "Few marks", "Crack on the back", "Few scuffs on the corners" (the third red
# team, 26 Sep: "because of a few marks probably."). So does its subject: "scuffs on frame they are from the case",
# "small scratch on screen it was from keys", "Scratches on back, all from the case" (red team 4, 26 Sep: "because of
# the scuffs on the frame they."). "Through" only for use or wear: "Crack running through the case" says where,
# "Wireless charging doesn't work through the case" when. A case goes "from", "caused by" or "due to" it after a mark
# ("Marks on frame due to the case", red team 4); after a fault it stays, as it says when (without_cause)
CAUSES = r"(?:(?:normal|general|everyday|daily|regular)\s+)?(?:keys|use|usage|wear(?:\s+and\s+tear)?|" \
         r"being in (?:a |my |the )?(?:pocket|bag)|(?:a |my |the )?(?:pocket|bag)|(?:a |the )?drop|dropping(?: it)?)"
CAUSE_TAIL = re.compile(r"(?:\s*[,;:(]\s*|\s+)(?:(?:and|but)\s+)?(?:(?:(?:it|they|these|those|this)\s+)?(?:is|are|was|"
                        r"were|isn['’]?t|aren['’]?t|wasn['’]?t|weren['’]?t)\s+|(?:it['’]?s|its|they['’]?re|theyre)\s+)?"
                        r"(?:(?:not|never|probably|prob|probs|possibly|maybe|likely|most likely|more than likely|"
                        r"apparently|mostly|mainly|presumably|just|only|all)\s+)*"
                        rf"(?:(?:from|due to|caused by)\s+{CAUSES}|"
                        r"(?:from|caused by|due to)\s+(?P<case>(?:a |my |the )?case)|"
                        r"through\s+(?:(?:normal|general|everyday|daily|regular)\s+)?(?:use|usage|wear(?:\s+and\s+tear)?))"
                        r"[\s.!)]*$", re.IGNORECASE)


def without_cause(part):
    """A flaw without how the seller says it happened (CAUSE_TAIL): "Few marks probably from the case" -> "Few marks".
    A case after a fault stays, as it says when: "Left AirPod doesn't charge from the case" isn't "doesn't charge"."""
    cause = CAUSE_TAIL.search(part)
    if not cause or cause.group("case") and FAULT_SAID.search(part[:cause.start()]):
        return part
    return part[:cause.start()].rstrip(" ,;:(")


def keeps_bare(found, before, after):
    """Whether a part with_the found (BARE_PART) reads right as the seller wrote it, so it gets no "the": a span
    ("corner to corner"), a feature's name ("always on display"), a shop's display, what a part describes after "of"
    ("signs of screen burn"), a verb's "on" ("wont turn on screen cracked"), "in front of", "kept in case", a name
    after "the" ("the underneath screen protector": red team 4, 26 Sep).
    before and after: the phrase's words either side of the match (the third red team, 26 Sep)."""
    prep, part = found.group("prep").lower(), found.group("part").lower()
    last = (re.findall(r"[\w'’]+", before) or [""])[-1].lower()  # the word before the preposition
    if last in ("the", "a", "an"):
        return True  # no preposition follows "the": "the underneath screen protector", "the near side" (red team 4)
    if found.group("of") is not None and (prep, part) in {("in", "front"), ("on", "top")}:
        return True  # "in front of the camera", "on top of the screen"
    if (prep, part) == ("in", "case"):
        return not IN_CASE_BEFORE.search(before)  # "kept in case since new"; "won't charge in the case"
    if part == "phone":
        return prep != "of" or bool(PHONE_THING.match(after))
    if prep in ("to", "by") and PLACE_WORD.match(last) and PLACE_WORD.match(part):
        ends = {last.rstrip("s"), part.rstrip("s")}
        # the same place either side ("corner to corner", "side by side"); after "to", opposites ("top to bottom of
        # the screen") or a far end that isn't of something ("top left to bottom right", not "corner to left of", nor
        # "on back to right side")
        if len(ends) == 1 or prep == "to" and (ends in OPPOSITE_ENDS or found.group("of") is None and
                                                not PLACED_BEFORE.search(before)):
            return True
    if NAME_BEFORE.search(before) or part in ("display", "screen") and \
            prep in ("on", "in", "under", "underneath", "behind") and NAMED_AFTER.match(after):
        return True  # "built in camera", "under display camera", "on screen keyboard"
    if (prep, part) == ("on", "display") and (ALWAYS_BEFORE.search(before) or SHOWN_BEFORE.search(before) or
                                               SHOWN_AFTER.match(after)):
        return True  # "always on display", "from being on display in store"
    if prep == "of" and (DESCRIBES_AFTER.match(after) or part == "glass" and MATERIAL_BEFORE.search(before)):
        return True  # "signs of screen burn", "a piece of glass missing"
    if prep == "on" and TURNED_ON.search(before):
        return True  # "wont turn on screen cracked", "power on button sticks"
    return prep == "down" and (bool(TURNED_DOWN.search(before)) or part in ("button", "buttons") or
                               part in ("side", "sides") and bool(DOWNSIDE_AFTER.match(after)))  # "volume down button"


# with_the off while a message of code's is written again to be measured (the_added)
BARE = ContextVar("bare", default=False)


def with_the(phrase):
    """A part the seller named bare gets its "the": "a few scratches on screen" -> "a few scratches on the screen",
    "small chip by camera" -> "small chip by the camera". Not where the bare words read right (keeps_bare): "in
    front of", "kept in case", "from corner to corner", "always on display", "signs of screen burn"."""
    if BARE.get():  # a message measured as the seller wrote its parts (the_added)
        return phrase

    def add(found):
        if keeps_bare(found, phrase[:found.start()], phrase[found.end():]):
            return found.group()
        return f"{found.group('prep')} the {found.group('part')}"
    return BARE_PART.sub(add, phrase)


def the_added(text, write):
    """The characters with_the's "the"s add to a message of code's: text, as write() wrote it, against write() run
    again without them. AlertFlip's 250 characters are for the seller's words as written, so "...on the back at the
    bottom left corner near the camera..." counts as "...on back at bottom left corner near camera..." (the third red
    team, 26 Sep: the "the"s made a 232-character message 256, and it was refused). 0 if the two differ by more."""
    token = BARE.set(True)
    try:
        bare = write()
    finally:
        BARE.reset(token)
    if not text or not bare:
        return 0
    kept = bare.split()
    for word in text.split():  # the same words, but for the "the"s
        if kept and word == kept[0]:
            kept.pop(0)
        elif word.lower() != "the":
            return 0
    return 0 if kept else len(text) - len(bare)


def straight(part):
    """A quote with the iPhone keyboard's apostrophes (’ ‘ ʼ) typed straight, as the wordings know them: "Camera
    doesn’t work and has slight crack on back" -> "Camera doesn't work and has slight crack on back" (26 Sep, the
    fourth red team: VERB_START, VERB_INSIDE, SUBJECT and RUN_ON only know ', so that half was said "because of the
    camera doesn’t work"; 257 of 3,748 labelled flaw lines type ’). The checks read a message straightened too."""
    return re.sub(r"[’‘ʼ]", "'", part)


def flaw_phrase(part):
    """One flaw in the seller's words, to go after "given", "because" or "I
    don't mind": 'the broken back', 'that it doesn't charge', 'that the
    hinge is stiff', "that it's cracked", 'that the screen is cracked'. The
    quote is cleaned first (clean_flaw). None when the words don't fit a
    sentence: the seller's own story ("I dropped it"), a denied fault ("not
    spares or repairs"), nothing left that says what's wrong, more words
    than a reason should have, or words that don't read ("the as per the
    photos the back is smashed": BROKEN)."""
    part = straight(part)
    if WORN_TIMES.match(clean_flaw(part)):
        return None
    phrase = worded_flaw(part)
    if phrase is None or BROKEN.search(phrase):
        return None
    phrase = SHOUTED_FLAW.sub(lambda m: m.group().lower(), phrase)  # "it has Scratches on screen": a seller's capital
    phrase = with_the(phrase)  # "a few scratches on screen" -> "...on the screen"
    said_one_way = battery_figure(part) or said_as(part)
    if not said_one_way and not (PROBLEM.search(phrase) or re.search(STATES, phrase, re.IGNORECASE) or
                                 SAYS_WRONG.search(phrase) or JUST_SAYS.match(clean_flaw(part)) or
                                 condition_said(phrase, typos=True) & FLAWS):  # "a few scraches on screen" says it too
        # nothing left that says what's wrong: "the back", "the Face ID", nor praise ("that it's in good condition",
        # once an iPhone apostrophe no longer stops "It’s in good condition but I’m unable to unlock it": 26 Sep)
        return None
    return phrase


def worded_flaw(part):
    """flaw_phrase's wording, before the check that it reads."""
    figure = battery_figure(part)
    if figure:  # "Battery Health: 80%", "81% BH": as AlertFlip says it
        return f"that the battery health is {figure}%"
    said = said_as(part)
    if said:
        return None if said is MIXED else said
    part = without_cause(clean_flaw(part))  # "Small scuffs on the charging case from keys": the scuffs
    if not part or FIRST_PERSON.search(part) or len(part.split()) > MAX_FLAW:
        return None
    part = RUN_ON.sub(r" – \1 ", ONE_ISSUE.sub(r"the \1", part))
    done = DONE_TO_PART.match(part)
    if done:  # "it has bent the frame at the top" -> "that the frame is bent at the top"
        thing = done.group("part").lower()
        plural = re.search(r"[^su]s$", thing) and not re.search(r"\b(?:glass|chassis|lens)$", thing)
        return f"that the {thing} {'are' if plural else 'is'} {done.group('state').lower()}" \
               f"{(done.group('rest') or '').rstrip(' .,!;:')}"
    if STORY_OR_DEED.match(part) or turned_on_then(part) or STATE_THEN_FAULT.match(part):  # more than one flaw's words:
        # split_phrases says each: "dropped it and cracked the back", "Bent the frame and no dead pixels", "wont turn on
        # screen cracked", "Screen cracked wont turn on"
        return None
    spares = SPARES.search(part)
    if spares:  # in the seller's own words: "for parts", "spares or repairs"
        return None if NEGATED_SPARES.search(part) else \
            "that it's sold for parts" if "part" in spares.group().lower() else f"that it's sold as {spares.group().lower()}"
    if JUST_SAYS.match(part):
        return f"that it's {lower_first(part)}"  # "that it's faulty", "that it's slightly scratched"
    both = STATE_AND_DOES.match(part)
    if both:  # "Water damaged and doesn't turn on" -> "that it's water damaged and doesn't turn on" (26 Sep: "that the
        return f"that it's {lower_first(both.group('state'))} and {both.group('does')}"  # water damaged and doesn't...")
    subject = SUBJECT.match(part)
    if subject:
        rest = lower_first(part[subject.end():])  # "*Has Scratches on screen" -> "that it has scratches on screen"
        return f"that it's {rest}" if subject.group(1) else f"that it has {rest}" if subject.group(2) else \
            f"that there's {rest}" if subject.group(3).lower() != "there are" else f"that there are {rest}"
    pronoun = PRONOUN_FIRST.match(part)
    if pronoun:  # "it flickers when you scroll fast" -> "that it flickers when you scroll fast"
        return f"that {pronoun.group(1).lower()} {lower_first(part[pronoun.end():])}"
    part = lower_first(A_BIT.sub("a bit of", part))
    quantity = QUANTITY.match(part)
    state = PART_STATE.match(part[quantity.end():]) if quantity else None
    if state:  # "Both cameras cracked": many parts, so "are"
        return f"that {quantity.group().lower()}{state.group('part')} are {state.group('state')}"
    if quantity and PLURAL_FAULT.match(part[quantity.end():]):
        return f"that {part}"  # "that both joycons drift"
    if NO_FAULT.match(part):
        return f"that there's {part}"  # "that there's no picture"
    if STATE_THEN.match(part) or LOCKED.match(part):
        return f"that it's {part}"  # "that it's missing a few keys", "that it's blacklisted on EE"
    if re.match(r"not\b", part, re.IGNORECASE):
        return f"that it's {part}"  # "that it's not holding charge"
    if re.match(r"got\b", part, re.IGNORECASE):
        return f"that it's {part}"  # "that it's got a small crack"
    if VERB_START.match(part):  # its verb agreeing with "it": "need screen replacement and battery replacement" ->
        # "that it needs screen replacement and battery replacement" (the fourth red team, 26 Sep: "because it need...")
        return "that it " + re.sub(r"^(need|require)\b", r"\1s", re.sub(r"^have\b", "has", part))
    verb = VERB_INSIDE.search(part)
    if verb:  # ...but not when a flaw comes before it: "Scratches on the frame and the screen has a chip" is two (two
        # that share its plural verb are one: "that the small scratch and dent are on the back", one_subject)
        last = next(iter(joins(part[:verb.start()])), None)
        shared = last is not None and one_subject(part[:last[0]], part[last[1]:])
        return None if two_flaws(part[:verb.start()]) and not shared else \
            f"that {part}" if ARTICLE.match(part) else f"that the {part}"
    state = PART_STATE.match(part)
    if state and not ARTICLE.match(part):  # "Screen cracked" -> "that the screen is cracked"
        thing = state.group("part")
        if two_flaws(thing):  # "Back cracked and screen scratched": two (not "Screen and back cracked")
            return None
        if NOT_A_PART.match(thing):
            return f"that it's {part}"  # "that it's water damaged", "that it's slightly faded"
        said, how = state.group("state"), re.match(r"^(.+?)\s+(slightly|very|quite|badly|really)$", thing, re.IGNORECASE)
        if how:  # "Screen slightly lifting": the screen is slightly lifting, not "the screen slightly is"
            thing, said = how.group(1), f"{how.group(2).lower()} {said}"
        plural = re.search(r"[^su]s$", thing) and not re.search(r"\b(?:glass|chassis|series|lens)$", thing, re.IGNORECASE) \
            or AND_JOINS.search(thing)  # "Screen and back cracked": two parts (26 Sep)
        return f"that the {thing} {'are' if plural else 'is'} {said}"
    if re.match(r"\w+(?:ed|en|s)\s+(?:the|a|an|its|his|her|quite|some|lots|loads|several|many)\b", part, re.IGNORECASE):
        return None  # "cracked the back", "presents quite a few scratches" (the half after "It's got a cracked back and",
        # 26 Sep: "because of the presents..."): a deed or a verb, not a flaw this can name; the AI words it
    if len(part.split()) == 1 and re.search(r"(?:ed|en)$", part):
        return f"that it's {part}"  # "cracked"
    if any(own_clause(part[:start]) for start, _ in joins(part)):
        return None  # a clause, then more: "Back cracked and a dent on the corner" isn't "the back cracked and..."
    if re.search(r"\b(?:will|would|may|might|could|should)\b", part, re.IGNORECASE):
        return None  # a clause, not a thing: "because of a battery replacement would bring it back..." (26 Sep)
    if re.match(r"(?:few|couple)\b", part, re.IGNORECASE):
        return f"a {part}"  # "a few scratches on the back"
    return part if ARTICLE.match(part) else f"the {part}"


# a part of a lower offer's point that only praises: "Very good cosmetic condition" next to "Small crack on the back"
PRAISE_ONLY = re.compile(r"^(?:in )?(?:overall )?(?:very |really )?(?:good|great|lovely|excellent|mint|perfect|immaculate|"
                         r"pristine|flawless|spotless|like new|as new)(?:\s+(?:cosmetic(?:ally)?|overall|used))?"
                         r"(?:\s+(?:condition|nick|shape|order))?(?:\s+(?:overall|otherwise))?[.!]*$", re.IGNORECASE)


def flaws_only(says):
    """The point's parts without one that only praises, so praise is never the
    reason for a lower offer ("because of the very good cosmetic condition and
    the small crack"); all of them if every part praises."""
    return [part for part in says if not PRAISE_ONLY.match(part.strip())] or list(says)


# ── one quote, more than one thing (26 Sep, the third red team) ─────────────
# two words joined that are one thing, never split: "wear and tear", "turns on and off" ("because of some wear and the
# tear on the frame" split the first "and" it found); two sides too ("scratches front and back"), but not when the
# second names its own part: "Small crack on the back and front camera flickers" is two, nor when it's praised:
# "Small crack on the front and back is fine" is the crack on the front (the fourth red team, 26 Sep: "because the
# small crack on the front and back is fine"; "Front and back is cracked" stays one). "Spares and repairs" is one too
# (26 Sep: "Spares and repairs as it won't turn on" was said "that it's sold as spares and that it's sold as repairs")
FIXED_PAIRS = re.compile(r"\b(?:wear\s*(?:and|&)\s*tear|black\s*(?:and|&)\s*white|on\s+and\s+off|off\s+and\s+on|"
                         r"spares\s*(?:and|&)\s*repairs?|"
                         r"back\s+and\s+forth|hit\s+and\s+miss|up\s+and\s+down|in\s+and\s+out|"
                         r"(?:front\s+and\s+back|back\s+and\s+front|top\s+and\s+bottom|left\s+and\s+right)"
                         r"(?!\s+(?:camera|cameras|lens|lenses|speakers?|mic|microphone|sensor|screen|display|button|"
                         r"buttons|airpod|airpods|earbud|earbuds|joy-?cons?|sticks?|triggers?)\b"
                         r"|\s+(?:is|are|looks?)\s+(?:fine|perfect|mint|flawless|immaculate|spotless|pristine|good|great|"
                         r"ok|okay)\b))\b", re.IGNORECASE)
# ...and the reader's quote cut off after an "and", its last clause gone. About something else ("Small crack on the
# front and back is", the quote of "...and back is fine"; "speakers are a bit quiet and screen is") what it said is
# unknown, so no wording: the AI words it from the listing, as for "Cracked the back glass and the lens is" (26 Sep:
# "because of the small crack on the front and back", "because the speakers are a bit quiet and screen"). About the
# same thing ("Has minor scuffs and scratches and is", "...and it is") it goes, and the flaw before it is said
CUT_CLAUSE = re.compile(r"\s+(?:and|&)\s+(?:(?:the|its)\s+)?(?:(?!(?:and|or|but|it|that|this)\b)[\w-]+\s+){1,2}?"
                        r"(?:is|are|was|were|has|have)\s*$", re.IGNORECASE)
CUT_SAME = re.compile(r"\s+(?:and|&)\s+(?:(?:it|that|this)\s+)?(?:is|are|was|were|has|have)\s*$", re.IGNORECASE)
AND_JOINS = re.compile(r"\s+(?:and|&)\s+", re.IGNORECASE)  # where two flaws may join: "Back cracked & screen scratched"
# ...or run on after a fault said with "on": "wont turn on screen cracked" is two (not "it wont turn on the screen
# cracked")
# ...but not a part's own name: "power on button sticks" is the power-on button, nor a light: "The light on the back
# camera doesn't work" is where the flash is (26 Sep, the fourth red team: "light" was a verb here, so that and "flash
# light on back not working" got no wording; no seller writes "lights on the screen" for "turns on")
TURN_ON_THEN = re.compile(r"\b(?!power\s+on\s+(?:button|key|switch)s?\b)"
                          r"(?:turn|switch|power|boot|come|start)(?:s|es|ed|ing)?\s+(?:on|up)\b(?P<gap>\s+)"
                          r"(?=(?:the\s+|its\s+)?(?:screen|display|back|front|camera|cameras|lens|glass|frame|battery|"
                          r"speakers?|mic|microphone|charging|charger|port|face id|touch id|buttons?|keyboard|trackpad|"
                          r"touch ?screen|lcd|wi-?fi|bluetooth|sound|volume)\b)", re.IGNORECASE)
# ...or the other way round, a part's state and then what it won't do: "Screen cracked wont turn on" is two too (the
# fourth red team, 26 Sep: "because the screen cracked wont turn on" said the screen won't turn on)
STATE_THEN_FAULT = re.compile(rf"^(?:[\w-]+ ){{0,3}}{STATES}(?P<gap>\s+)(?=(?:won'?t|doesn'?t|don'?t|can'?t|will not|"
                              r"does not|not) (?:turn|switch|power|boot|come|start|charge|work)(?:s|ing)?\b)", re.IGNORECASE)
# a story or a deed with more after it: "dropped it and cracked the back", "Fell and...", "Bent the frame and no dead
# pixels" ("because of the dropped it and cracked the back"): two things, so not one wording (DONE_TO_PART says a deed
# alone). Not "Dropped calls", a fault
STORY_OR_DEED = re.compile(r"^(?:it\s+)?(?:(?:has|'s|have|had|was|got|been|has been|accidentally|accidently)\s+)?"
                           r"(?:(?:dropped|fell|knocked|sat on|stood on|stepped on|ran over|run over)\b(?!\s+calls?\b)|"
                           r"(?:\w+ed|bent|broke|broken|split|snapped|tore|torn)\s+(?:it|them|the|its|his|her|a|an)\b)",
                           re.IGNORECASE)
# what's wrong, then what it does: "Water damaged and doesn't turn on" -> "that it's water damaged and doesn't turn on"
STATE_AND_DOES = re.compile(rf"^(?P<state>(?:(?:water|liquid|heat|sun|rain|moisture)\s+)?(?:(?:slightly|a bit|very|"
                            rf"quite|badly|really)\s+)?(?:damaged|cracked|scratched|scuffed|dented|chipped|faulty|bent|"
                            rf"broken|smashed|shattered|swollen|marked|worn))\s+(?:and|&)\s+"
                            rf"(?P<does>{VERB_START.pattern[1:]}.*)$", re.IGNORECASE)
# a pronoun the seller starts with, and its verb: "it flickers when you scroll fast" -> "that it flickers when you
# scroll fast" (it got a "the": "because the it flickers...")
PRONOUN_FIRST = re.compile(rf"^(it|they)\s+(?=(?:(?:sometimes|randomly|often|occasionally|constantly|always|also|"
                           rf"still|now|just|only)\s+)?(?:{VERB_START.pattern[1:]}|\w+(?:s|ed)\b|"
                           rf"(?:won|don|can|isn|aren|wasn|didn|doesn)['’]?t\b|(?:drift|crackle|rattle|flicker|stick|"
                           rf"buzz|squeak|wobble|lag|leak|need|have|are|keep|cut|stop|die|disconnect)\b))", re.IGNORECASE)
# a "no", "not" or "never" a few words before a flaw word: "no other damage", "never been repaired", "hardly any marks",
# "doesn't have any scratches" (a whole word: not the "nt" of "front camera flickers")
DENIED_BEFORE = re.compile(r"\b(?:no|not|never|without|zero|nothing|none|hardly|barely|free\s+(?:from|of)|\w+n['’]t|"
                           r"(?:is|does|do|wo|ca|did|was|are|has|have|had|would|could)nt)\s+(?:[\w'’-]+\s+){0,2}$",
                           re.IGNORECASE)
# a fault in words that also praise or work ("only works on wifi", "works sometimes", "screen no good"), or in a word
# only the writer knows (SAYS_WRONG's): "front camera is blurry", "touch is unresponsive"
FAULT_TOO = re.compile(r"\b(?:only|sometimes|occasionally|rarely) (?:works?|charges?|connects?|turns? on)\b|"
                       r"\bworks? (?:sometimes|occasionally|intermittently|on and off|now and then)\b|\bno good\b|"
                       r"\b(?:blurr?y|blurred|unresponsive|slow|sluggish|faint|dim|crooked|uneven|gaps?)\b",
                       re.IGNORECASE)
# a half of a quote that says nothing's wrong (half_kind), so is never a reason to pay less: praise ("Very good
# condition", "the screen is perfect"), that it works ("Works perfectly", "phone comes on"), a selling point
# ("Unlocked", "Boxed", "original charger included") or the seller's story ("dropped it", "Fell")
PRAISE_HALF = re.compile(r"(?<!\bno )(?<!\bnot )\b(?:perfect(?:ly)?|fine|mint|flawless|immaculate|spotless|pristine|"
                         r"excellent|great|good|lovely|ok|okay|like new|as new|100\s?%)(?!\w)", re.IGNORECASE)
WORKS_HALF = re.compile(r"\b(?:works?|working|functions?|functional|fully tested|(?:turns|comes|powers|switches|boots|"
                        r"starts|lights)\s+(?:on|up))\b", re.IGNORECASE)
SELLS_HALF = re.compile(r"^(?:(?:network|fully|factory|sim)\s+)?unlocked\b|^sim[- ]?free\b|^(?:boxed|in (?:the |its )?"
                        r"box)\b|^(?:icloud|activation lock|find my(?: iphone)?|fmi)\s+(?:free|off|removed|disabled)\b|"
                        r"^clean imei\b|^(?:comes|came|sold) (?:with|boxed)\b|^(?:with|includes?|including|plus)\s+"
                        r"(?:the\s+|its\s+|a\s+)?(?:original\s+|genuine\s+)?(?:box|charger|cable|lead|plug|case|receipt|"
                        r"warranty|earphones|headphones)\b|\b(?:included|includes)\b|^(?:the\s+)?(?:original|genuine)\s+"
                        r"(?:apple\s+)?(?:box|charger|cable|lead|plug|receipt|parts?|screen|battery)\b|"
                        r"^(?:apple\s?care|warranty)\b", re.IGNORECASE)
STORY_HALF = re.compile(r"^(?:it\s+)?(?:(?:was|got|been|has been|accidentally|accidently)\s+)?(?:dropped|fell|knocked|"
                        r"sat on|stood on|stepped on|ran over|run over)\b(?!\s+(?:calls?|signal|connection|wi-?fi)\b)",
                        re.IGNORECASE)
HALF_FAULT, HALF_FINE = "fault", "not a fault"


def joins(part):
    """Where a quote's words may hold two flaws, last first, as (where the
    first ends, where the second starts): each "and" or "&" but those of
    FIXED_PAIRS ("wear and tear"), and a run-on after "turn on" (TURN_ON_THEN)
    or before it (STATE_THEN_FAULT: "Screen cracked wont turn on")."""
    masked = FIXED_PAIRS.sub(lambda pair: "_" * len(pair.group()), part)  # the same length, so places stay
    found = [(m.start(), m.end()) for m in AND_JOINS.finditer(masked)] + \
            [(m.start("gap"), m.end("gap")) for m in [*TURN_ON_THEN.finditer(masked), *STATE_THEN_FAULT.finditer(masked)]]
    return sorted(found, reverse=True)


def fault_in(text):
    """Whether words say something's wrong: a kind of flaw the listing's
    reader reads (condition_said), a low battery figure, or one of the
    writer's fault words that nothing denies ("the hinge is a bit loose now",
    "it flickers"). Not "no scratches on the screen", "not iCloud locked",
    "zero scratches" or "battery 88%"."""
    if re.match(r"\s*(?:zero|0)\s", text):  # "zero scratches", which condition_said reads as scratches
        return False
    fault_words = [*PROBLEM.finditer(text), *FAULT_TOO.finditer(text)]
    return bool(condition_said(text, typos=True) & FLAWS or battery_figure(text) or
                any(not DENIED_BEFORE.search(text[:m.start()]) for m in fault_words))


@lru_cache(maxsize=4096)
def half_kind(half):
    """What half a quote says: HALF_FAULT when it says something's wrong
    (fault_in), HALF_FINE when it clearly doesn't (a denied flaw, praise,
    that it works, a selling point, a good battery figure, the seller's
    story), None for anything else ("frame", a bare part a list carries on
    with) and for the seller's own story ("I dropped it"), which the AI words."""
    half = half.strip(" .,!;:-–—")
    if not half or FIRST_PERSON.search(half):
        return None
    if fault_in(half):
        return HALF_FAULT
    # a good battery figure, said apart from where the flaw before it is: "on the frame 93% battery health" goes on
    # from "...some scratches on the screen and" (f019, 26 Sep: the frame was left out with the battery)
    good_battery = battery_worded(half) and all(float(f) > LOW_BATTERY for f in battery_worded(half)) and \
        not BARE_PART.match(re.sub(r"^(\w+)\s+(?:the|its)\s+", r"\1 ", half))
    denied = PROBLEM.search(half) or FAULT_TOO.search(half)  # a fault word here is one denied: "no other damage"
    praised = PRAISE_ONLY.match(half) or GOOD_CONDITION.search(half) or PRAISE_HALF.search(half)
    if denied or praised or WORKS_HALF.search(half) or SELLS_HALF.search(half) or STORY_HALF.match(half) or good_battery:
        return HALF_FINE
    return None


def own_clause(text):
    """Whether words are a clause of their own, a part and what's wrong with
    it: "Back cracked", "the screen has a chip", "it flickers", "Cracked the
    back", "Battery health 79%" (not "Scratches on the frame", "Doesn't
    charge" or "Cracked")."""
    text = text.strip(" .,!;:-–—")
    return bool(PART_STATE.match(text) or SUBJECT.match(text) or PRONOUN_FIRST.match(text) or DONE_TO_PART.match(text) or
                VERB_INSIDE.search(text) and not VERB_START.match(text) or battery_figure(text))


def two_flaws(text):
    """Whether a flaw comes before an "and" in the words (joins), so what
    follows is a second one: "Scratches on the frame and the screen" (not
    "Screen and back", which is one)."""
    return any(fault_in(text[:start]) for start, _ in joins(text))


# the second of two flaws as one subject, with the plural verb they share: "dent are on the back" in "Small scratch
# and dent are on the back", "a dent are on the frame", "back are light" in "Scratches on the screen and back are
# light" (not "both lenses are scratched", "there are some marks" or "the screen has a chip": a clause of their own)
SHARED_VERB = re.compile(r"^(?:an?\s+)?(?!(?:the|both|all|its|some|several|many|my|there|they|these|those|it|which|that)\b)"
                         r"[\w-]+(?:\s+[\w-]+)?\s+(?:are|were|have)\b", re.IGNORECASE)


def one_subject(first, second):
    """Whether the words either side of an "and" are one subject of the verb after the second ("Small scratch" and
    "dent are on the back": one, so not split as "because of the small scratch and because the dent are on the back",
    the fourth red team, 26 Sep), not a clause and then a second ("Back cracked" and "cameras are scratched")."""
    return bool(SHARED_VERB.match(second.strip())) and not own_clause(first)


def turned_on_then(part):
    """Whether a seller's run-on says a second fault after "turn on": "wont
    turn on screen cracked" (not "won't turn on the screen")."""
    return any(fault_in(part[m.end("gap"):]) for m in TURN_ON_THEN.finditer(part))


def split_phrases(part):
    """One quote's flaws, each said (flaw_phrase), or None if one can't be
    said. A half that isn't a fault (half_kind: praise, a denial, a selling
    point, the seller's story) is never said, the other is: "Unlocked and
    back glass cracked" -> "that the back glass is cracked". Two clauses are
    said apart ("The back is cracked and it has bent the frame at the top" ->
    "that the back is cracked", "that the frame is bent at the top"), else the
    whole quote if it can be said ("the scratches and scuffs on the frame"),
    else its halves when each is a flaw of its own. The "and"s are tried from
    the last one back ("Light scratches on screen and frame and back glass
    has a hairline crack"), never inside "wear and tear" (joins)."""
    part = CUT_SAME.sub("", straight(part))  # "Has minor scuffs and scratches and is" -> "Has minor scuffs and scratches"
    if CUT_CLAUSE.search(part):
        return None  # "Small crack on the front and back is": the reader's quote ends where the second clause starts
    halves = [(part[:start], part[end:]) for start, end in joins(part)]
    kinds = [(half_kind(first), half_kind(second)) for first, second in halves]

    def faults_said(at):  # each half of the at-th "and" that's a fault, said (a half may hold two itself), or None
        said = [split_phrases(half) for half, kind in zip(halves[at], kinds[at]) if kind == HALF_FAULT]
        return None if None in said else [phrase for phrases in said for phrase in phrases]

    for at, kind in enumerate(kinds):  # a fault and what isn't one: the fault alone
        said = faults_said(at) if set(kind) == {HALF_FAULT, HALF_FINE} else None
        if said:
            return said
    for at, kind in enumerate(kinds):  # a fault, then a clause of its own: each said (not one subject: one_subject)
        said = faults_said(at) if kind == (HALF_FAULT, HALF_FAULT) and own_clause(halves[at][1]) and \
            not one_subject(*halves[at]) else None
        if said:
            return said
    whole = flaw_phrase(part)
    if whole is not None:
        return [whole]
    for at, kind in enumerate(kinds):  # two flaws of their own
        said = faults_said(at) if kind == (HALF_FAULT, HALF_FAULT) else None
        if said:
            return said
    return None


def flaw_list(says):
    """The listing's flaws, each said once, the things first ("the broken back")
    and then what's said of it ("that the battery health is 79%"), or None
    if one of them can't be said."""
    phrases = []
    for part in flaws_only(says):
        said = split_phrases(part)
        if said is None:
            return None
        phrases += said
    phrases = list(dict.fromkeys(phrases))  # "Back cracked and needs a new battery" next to "Needs a new battery"
    return [p for p in phrases if not p.startswith("that ")] + [p for p in phrases if p.startswith("that ")]


def point_phrases(point):
    """The point's flaws as the writer says them: the reason flip.wording worded and checked, as one fact ("that
    there's a hairline crack on the top left of the screen": "...because there's...", "given that there's..."),
    or code's own phrases from the listing's words (flaw_list)."""
    if point.get("worded"):
        return [f"that {point['worded']}"]
    return flaw_list(point["says"])


def flaw_words(says):
    """The listing's flaws together: 'the broken back and the cracked screen',
    'the light marks on the frame and that the battery health is 79%' (not
    'that the battery health is 79% and the light marks', which doesn't read
    after "given": 26 Sep), or None if one of them can't be said (flaw_list)."""
    phrases = flaw_list(says)
    return None if phrases is None else " and ".join(phrases)


def reason_sentence(point):
    """A lower offer's reason in a sentence of its own, as AlertFlip gives it:
    "I'm offering that because the battery health is 80%.", "...because of
    the broken back.", "...because it doesn't charge." None if the listing's
    words can't be said (flaw_phrase)."""
    if point["about"] == "battery":
        return f"I'm offering that because the battery health is {point['battery']}%."
    phrases = point_phrases(point)
    if phrases is None:
        return None
    things = [p for p in phrases if not p.startswith("that ")]  # "the broken back"
    facts = [p[len("that "):] for p in phrases if p.startswith("that ")]  # "it doesn't charge"
    said = ([f"of {' and '.join(things)}"] if things else []) + ([" and ".join(facts)] if facts else [])
    return f"I'm offering that because {' and because '.join(said)}."


def good_words(says):
    """The listing's good condition: "it's in excellent condition" (from
    "Excellent condition", "Phone is in excellent condition" or "Condition:
    Excellent"), "it's barely used". None for words in another shape."""
    part = says[0].strip().rstrip(".!")
    found = GOOD_CONDITION.search(part)
    if found:
        return f"it's in {(found.group(1) or found.group(2)).lower()} condition"
    if GOOD_AS_IS.match(part):
        return f"there's {part.lower()}" if part.lower().startswith("not") else f"it's {part.lower()}"
    word = GOOD_WORD.match(part)
    if word:
        said = word.group(1).lower()
        return f"it's in {said} condition" if said == "mint" else f"it's {said}"
    return None


def merge_questions(questions):
    """'Does it come with a charger?' + 'Does it come with the box?' -> 'Does it come with a charger and the box?'"""
    start = "Does it come with "
    come = [q for q in questions if q.startswith(start)]
    if len(come) < 2:
        return list(questions)
    joined = start + " and ".join(q[len(start):-1] for q in come) + "?"
    return [joined if q == come[0] else q for q in questions if q not in come[1:]]


def split_sign_off(sentence):
    """A sentence and what comes after its own end: ("Would you take £[OFFER]?", "😊")."""
    sentence = sentence.rstrip()
    core = SIGN_OFF.sub("", sentence).rstrip()
    return core, sentence[len(core):].strip()


def split_end(sentence):
    """A sentence as (what it says, the marks it ends with, what comes after them): ("Would you take £[OFFER]", "??",
    "😊"). Every mark of a run goes together ("£255??", never "£255?, given ...?" nor "£255?, given ...!"), a space
    before it too, and dots that trail off ("...", "…") end it: they're no sign-off to keep after code's own end
    (14 Oct hunt: "...on the back? ... Can collect today", "I can pay £350. ...")."""
    core, sign = split_sign_off(sentence)
    dots = re.match(r"(?:\.{2,}|…)+", sign)
    if dots:
        core, sign = core + dots.group(), sign[dots.end():].strip()
    found = re.search(r"\s*([.?!…]+)$", core)
    return (core[:found.start()], found.group(1), sign) if found else (core.rstrip(), "", sign)


def trailed(end, mark="."):
    """The end code gives a sentence it rewrote: your dots when you trail off ("I can pay £300..."), else mark."""
    return end if end and re.fullmatch(r"(?:\.{2,}|…)+", end) else mark


def split_greeting(sentence):
    """A sentence's greeting, as typed with what follows it, and the rest:
    ("Hi mate, ", "would you take £[OFFER]?"), ("Hi mate ", "I can pay..."),
    ("Hi mate 👋 ", ...); ("", sentence) when it doesn't open with one."""
    found = LEADING_GREETING.match(sentence)
    return (found.group(), sentence[found.end():]) if found and found.end() < len(sentence) else ("", sentence)


def asks(sentence):
    """Whether a sentence asks, with or without its "?": "would you take £170 cash." does."""
    core = split_greeting(split_sign_off(sentence)[0])[1]
    return ends_asking(core) or bool(ASKS_OFFER.match(core))


def as_statement(sentence):
    """At or over the asking price the offer is said, not asked:
    'Would you take £[OFFER] cash?' -> 'I can pay £[OFFER] cash.' Only a safe
    ending is kept after the price ("cash", "for it"), and your greeting as
    you type it and the sign-off: "...£[OFFER]?😊" -> "...£[OFFER]. 😊"."""
    body, end, sign = split_end(sentence)
    core = body + end
    if not asks(core) or "[OFFER]" not in core:
        return sentence
    greeting, _ = split_greeting(core)
    tail = re.sub(r"^\s*(?:quid|pounds)\b", "", body[body.index("[OFFER]") + len("[OFFER]"):].rstrip(" ?.!"))
    tail = tail if SAFE_TAIL.match(tail) else ""
    return f"{greeting}I can pay £[OFFER]{tail}{trailed(end)}{' ' + sign if sign else ''}"


def as_question(sentence):
    """Under the asking price the offer is asked, not said: 'I can pay
    £[OFFER] cash.' -> 'Would you take £[OFFER] cash?', for when your usual
    sentence is one you write paying asking. Only a safe ending is kept after
    the price, and your greeting and sign-off: 'Hi mate, I can pay £[OFFER]. 👍'
    -> 'Hi mate, would you take £[OFFER]? 👍'."""
    body, end, sign = split_end(sentence)
    core = body + end
    if asks(core) or "[OFFER]" not in core:
        return sentence
    greeting, _ = split_greeting(core)
    tail = re.sub(r"^\s*(?:quid|pounds)\b", "", body[body.index("[OFFER]") + len("[OFFER]"):].rstrip(" .!"))
    tail = tail if SAFE_TAIL.match(tail) else ""
    ask = f"would you take £[OFFER]{tail}{trailed(end, '?')}"
    return f"{greeting + ask if greeting else ask[:1].upper() + ask[1:]}{' ' + sign if sign else ''}"


def held(sentence):
    """Over asking, the reason to pay more: "I can pay £[OFFER] cash." -> "I can
    pay £[OFFER] cash if you can hold it for me.", before any sign-off. Once:
    your own reason stays ("if you can save it for me"), and a condition of
    another kind gives way to it ("£[OFFER] if that's ok" -> "£[OFFER] if you can hold it for me")."""
    body, end, sign = split_end(sentence)
    if HELD.search(body):
        return sentence
    core = re.sub(r"\s+if\b.*$", "", body.rstrip(" .!?"), flags=re.IGNORECASE)
    return f"{core} if you can hold it for me{trailed(end)}{' ' + sign if sign else ''}"


def generic_reason(body):
    """Your own reason for any listing in an offer sentence (GENERIC_REASON,
    GENERIC_FIRST), its lead and words in the groups "lead" and "what":
    "given the state it's in" in "Would you take £[OFFER] given the state
    it's in", "Given the condition" in "Given the condition, would you take
    £[OFFER]", and all of "Given the condition" in a closing (26 Sep). None
    when there's none, or it says more ("Given the condition of the screen,
    would you...")."""
    found = GENERIC_REASON.search(body)
    if found:
        return found
    first = GENERIC_FIRST.search(body)
    return first if first and (first.group("comma") or first.end() == len(body)
                               or ASKS_OFFER.match(body[first.end():])) else None


def cut_whole(body, found):
    """Whether your own words for any listing (found) come out of an offer
    sentence leaving nothing of their clause behind: "...cash, don't mind the
    condition" and "Given the condition, would you..." do; "...cash and I'm
    not fussed about the condition" ("...cash and I'm."), at asking "...cash,
    don't mind the condition tbh" ("...cash tbh.") and "Given the condition,
    and the fact I can collect today, would you..." ("And the fact...")
    don't (26 Sep red team). Under asking what follows stays: "...£[OFFER] tbh?"."""
    rest = body[found.end("what"):]
    greeted = LEADING_GREETING.match(body[:found.start()])  # said first after your greeting: "Hi mate, given the..."
    # said first: the offer then starts the sentence
    first = found.re is GENERIC_FIRST or not found.start() or bool(greeted and greeted.end() == found.start())
    if first and LEFT_JOINED.match(rest.lstrip(" ,")):
        return False
    if found.re is not GENERIC_DONT_MIND:
        return True
    # at asking its comma, dash or "and" goes with it (not "I'm", "we", "really": no list of those), and the end follows
    return bool((first or re.search(r"[,\-–—]|\band\b", found.group("join"), re.IGNORECASE))
                and re.match(GENERIC_END, rest, re.IGNORECASE))


def without_generic(body, found):
    """An offer sentence without your reason for any listing (found):
    "Would you take £[OFFER] given the state it's in" -> "Would you take
    £[OFFER]", "Given the condition, would you take £[OFFER]" -> "Would you
    take £[OFFER]", "I can pay £[OFFER] cash, don't mind the condition" ->
    "I can pay £[OFFER] cash"."""
    if found.re is not GENERIC_FIRST and found.start():  # after the offer: its comma goes with it
        return body[:found.start()] + body[found.end("what"):]
    rest = re.sub(r"^[\s,]+", "", body[found.end("what"):])  # before it: the offer starts the sentence, as you'd start it
    return body[:found.start()] + (rest[:1].upper() + rest[1:] if found.group("lead")[:1].isupper() else rest)


CLAUSE_LEADS = {"as", "since", "because", "becuase", "beacuse", "becos", "bcos", "bcuz", "coz", "cuz", "seeing as"}


def led(lead, phrases):
    """Your own lead with the listing's flaws (flaw_list), as you capitalise
    it: "given the cracked screen", "cos it doesn't charge", "because of the
    light marks on the frame and because the battery health is 79%" (never
    "because of that..."), "given that it doesn't charge" for "with". Your
    capital stays on the first word only: "Because of the light marks on the
    frame and because...", never "...and Because..." (26 Sep red team)."""
    things = [p for p in phrases if not p.startswith("that ")]
    facts = [p[len("that "):] for p in phrases if p.startswith("that ")]
    low = lead.lower()
    if low == "for":  # "for the small crack on the back" says what you'd pay for: "given ..." (26 Sep)
        lead, low = ("Given" if lead[:1].isupper() else "given"), "given"
    if facts and (low.endswith(" of") or low in ("due to", "owing to")):  # "cos of" -> "cos it doesn't charge" (26 Sep)
        # ..."because" for the rest: "in light of the marks and because it doesn't charge", never "in light it..."
        because = low[:-len(" of")] if low.endswith(" of") and " " not in low[:-len(" of")] else "because"
        reason = " and ".join([*([f"{lead} {' and '.join(things)}"] if things else []), f"{because} {' and '.join(facts)}"])
    elif facts and low in ("with", "what with"):
        reason = f"given {' and '.join(phrases)}"  # "given that it doesn't charge", not "with that it doesn't charge"
    elif low in CLAUSE_LEADS or re.fullmatch(r"['’]?cos", low):  # "as it's got a few marks": a clause after it (14 Oct)
        reason = f"{lead} {' and '.join(facts)}" if not things else f"given {' and '.join(phrases)}"
    else:
        reason = f"{lead} {' and '.join(phrases)}"
    return reason[:1].upper() + reason[1:] if lead[:1].isupper() else reason  # "Given the small crack, would you..."


def with_reason(sentence, kind, point):
    """The listing's point in the offer sentence (lower, more) or after it
    (asking), before any sign-off the sentence ends with. Your own reason for
    any listing takes the listing's in its place ("Would you take £[OFFER]
    given the state it's in?" -> "...given the small crack on the back?",
    "Given the condition, would you..." -> "Given the small crack on the back,
    would you...", at asking "...cash, don't mind the condition." -> "...cash,
    don't mind the small crack on the back."), and goes when there's no flaw
    to give ("Would you take £[OFFER]?") if it comes out whole (cut_whole):
    at asking it stays as you typed it if not ("...cash and I'm not fussed
    about the condition."). None if the listing's words can't be said
    (flaw_words, good_words), or your sentence gives a reason about the
    condition this can't swap or take out ("given the cracked screen"): the AI
    words that one, never with a second reason after it (26 Sep)."""
    if kind == "more" and point and point.get("about") != "condition":
        kind = "asking"  # a flaw you don't mind at Offer more is said as at Pay asking: "I don't mind that..." (14 Oct)
    body, end, sign = split_end(sentence)
    core = body + end
    tail = f" {sign}" if sign else ""
    if not point:  # no flaw to give: not your "given the condition" on a mint listing, nor "don't mind the condition"
        if kind == "more":
            return sentence
        found = generic_reason(body) if kind == "lower" else GENERIC_DONT_MIND.search(body)
        if found and not cut_whole(body, found):  # what's left wouldn't read: at asking it stays as you typed it,
            return sentence if kind == "asking" else None  # a reason to pay less never does (the AI words it, 26 Sep)
        bare = without_generic(body, found) if found else body
        if kind == "lower" and OWN_REASON.search(bare):
            return None  # "given the condition and that I can collect today": more than code can take out
        # ...at asking your own words stay ("don't mind the condition as long as it works"): not minding claims nothing,
        # and one that names a flaw the listing hasn't is the checks' (26 Sep red team: refused on every listing)
        return f"{bare}{end}{tail}" if found else sentence
    phrases = None if kind == "more" else [f"that the battery health is {point['battery']}%"] \
        if point["about"] == "battery" else point_phrases(point)
    said = good_words(point["says"]) if kind == "more" else None if phrases is None else " and ".join(phrases)
    if said is None:
        return None
    end = end or ("?" if ASKS_YOU.search(core) else ".")
    if kind == "lower":
        generic = generic_reason(body)
        if generic:  # your own wording, with the listing's flaw: "would you take £255 given the cracked screen?"
            if OWN_REASON.search(without_generic(body, generic)):
                return None  # a second reason of your own about the condition: not two
            reason = led(generic.group("lead"), phrases)
            return f"{body[:generic.start('lead')]}{reason}{body[generic.end('what'):]}{end}{tail}"
        if OWN_REASON.search(body):
            return None  # your own reason about the condition ("given the cracked screen"): never a second after it
        return f"{after_price(body, f', given {said}')}{end}{tail}"
    if kind == "more":
        if re.search(r"\b(?:condition|mint|immaculate|pristine|perfect|flawless|excellent|like new)\b", body, re.IGNORECASE):
            return sentence  # your own offer already praises it: once
        return f"{after_price(body, f', as {said}')}{end}{tail}"
    mind = GENERIC_DONT_MIND.search(body)
    if mind:  # your own "don't mind the condition", with the listing's flaw: "don't mind that it doesn't charge",
        facts = all(p.startswith("that ") for p in phrases)  # "not fussed that it...", not "not fussed about that it"
        return f"{body[:mind.end('lead')]}{'' if facts else mind.group('prep') or ''} {said}" \
               f"{body[mind.end('what'):]}{end}{tail}"
    if re.search(CONDITION_WORDS, body, re.IGNORECASE):  # your own words about the condition, any way round ("don't
        return None  # mind the scratches on the screen", "condition doesn't bother me"): never a second "I don't mind"
    return f"{core}{'' if core[-1:] in ('.', '?', '!', '…') else '.'} I don't mind {said}.{tail}"


def after_price(body, reason):
    """An offer sentence with the reason at the end of the price's own clause, where what's tied to the price ends
    (PAY_CLAUSE_END, as paid_at): "would you take £[OFFER] cash, given that the back glass is cracked, can collect
    tonight", "would you take £[OFFER], given ..., or is that too cheeky", never after the next clause ("...can collect
    tonight, given that...": 14 Oct hunt, it read as the reason for collecting tonight)."""
    price = re.search(r"£?\[OFFER\](?:\s*(?:quid|pounds)\b)?", body)
    found = PAY_CLAUSE_END.search(body, price.end()) if price else None
    at = found.start() if found else len(body)
    rest = body[at:]
    if rest.strip() and not re.match(r"\s*[,;:.!?…]|\s+[-–—]\s", rest):
        rest = f",{rest}"  # a clause that carries on gets its comma: ", given the small crack on the back, if I collect"
    return f"{body[:at]}{reason}{rest}"


def point_in_closing(closing, kind, point):
    """Your reason or "don't mind the condition" when it's a sentence of its
    own in your closing ("Would you take £150? Given the condition.", "I can
    pay £200 cash. Don't mind the condition."), as with_reason does it in
    your offer sentence: the listing's point goes there ("Don't mind the small
    crack on the back. Can collect today.") and is then said, so the offer
    sentence gets no second one; with none to give your reason goes (not
    your "don't mind", which claims nothing). Gives (closing, point left for
    the offer sentence), as they were when your closing has none. None when
    it can't be worded, or at asking your closing talks about the condition
    another way ("Condition doesn't bother me.") (26 Sep red team: "I can pay
    £200 cash. I don't mind the small crack on the back. Don't mind the
    condition.")."""
    if kind == "more" and point and point.get("about") != "condition":
        kind = "asking"  # a flaw at Offer more is said as at Pay asking (with_reason): your "Don't mind the condition."
        # takes it, never a second "I don't mind ..." before it (14 Oct hunt)
    if kind == "more" or (kind == "asking" and not point):
        return closing, point
    parts = [part.strip() for part in SENTENCES.split(closing) if part.strip()]
    for at, part in enumerate(parts):
        core, sign = split_sign_off(part)
        # at asking your "don't mind the condition" anywhere in it; under it a sentence that's only your reason, or
        # one that gives it after what it says ("I'm offering that because of the condition.": 14 Oct hunt, the
        # reason was said twice, and with no flaw to give no message was written)
        whole = GENERIC_FIRST.fullmatch(core.rstrip(" .!"))
        inside = kind == "lower" and not whole and GENERIC_REASON.search(core)
        if not (GENERIC_DONT_MIND.search(core) if kind == "asking" else whole or inside):
            continue
        if inside and not point:  # no flaw to give: the reason goes, and the sentence with it if it was for it
            left = without_generic(core.rstrip(" .!?"), inside).strip(" ,")
            dangling = len(words(left)) < 3 or re.search(r"\b(?:that|this|it|it['’]?s|its|just|only|offering|offer|"
                                                         r"asking|price|so|is|was|be|sorry)$", left, re.IGNORECASE)
            parts[at] = sign_left(sign) if dangling else f"{left}.{' ' + sign if sign else ''}"
            return " ".join(part for part in parts if part), None
        said = with_reason(part, kind, point)
        if said is None:
            return None
        parts[at] = said if re.search(r"\w", split_sign_off(said)[0]) else sign_left(sign)  # gone: its sign-off stays
        return " ".join(part for part in parts if part), None
    if kind == "asking" and re.search(CONDITION_WORDS, closing, re.IGNORECASE):
        return None  # "Condition doesn't bother me.": not "I don't mind the small crack on the back." before it
    return closing, point


def join(*parts):
    """Sentences into one message: after a greeting ending in a comma the next
    sentence carries on in lower case; after a full stop it starts with a capital."""
    text = ""
    for part in (p.strip() for p in parts if p and p.strip()):
        if text.endswith(",") and part[:1].isupper() and not re.match(r"I\b", part):
            part = part[:1].lower() + part[1:]
        elif text[-1:] in (".", "?", "!") and part[:1].islower() and not re.match(r"x{1,3}\b", part):
            part = part[:1].upper() + part[1:]  # ...but a kiss isn't a sentence: "...till tomorrow. x", not ". X"
        text = f"{text} {part}".strip()
    return text


def greeting_apart(sentence):
    """("Hi mate,", "would you take £185?") from "Hi mate, would you take
    £185?", so anything added goes after the greeting, as you type it: "hi
    wud u take £125?" is ("hi", "wud u take £125?"), with no comma you don't
    write. ("", sentence) when it has none, or is nothing but one ("Hi mate!")."""
    greeting = opening(sentence)
    typed = re.match(rf"\s*{re.escape(greeting)}\s*(,?)", sentence) if greeting else None
    rest = sentence[typed.end():].lstrip(" ,") if typed else ""
    if not re.search(r"\w", rest):
        return "", sentence
    if not typed.group(1) and rest[:1].isupper() and not re.match(r"I\b|I'", rest):
        # on a line of its own ("Hey⏎Would you take..."): a comma, so never "Hey Would you take"
        return f"{greeting},", rest[:1].lower() + rest[1:]
    return f"{greeting}{typed.group(1)}", rest


# what may follow "collect" (or "collect it") for the listing's place to go in there: the end of the sentence, an
# emoji, a kiss or a sign-off ("Can collect x"), when ("today", "this Saturday", "on Sat", "at half 6", "after work",
# "in the morning", "asap"), "in person", or the next part of the sentence ("and pay cash", "if that's ok"). Anything
# else says where or what, and the sentence stays as you wrote it: the place went in front of it, "collect from
# Bradford BD7 in Leeds today", "collect this from Bradford BD7 Saturday" (26 Sep red team)
PLACE_GOES = re.compile(
    rf"\s*(?:$|[.!?,;:…)~\-–—]|{EMOJI_IN.pattern})|\s+(?:x+|thanks|thank you|thx|ta|cheers|please|pls|plz|mate)\b"
    rf"|\s+(?:(?:this|next|that|every)\s+(?!(?:today|tonight|tonite|tomorrow|tmrw|2day|2nite|2moro|asap|now|later|soon)\b)"
    rf"|(?:on|at|by|till|until|before|after|from|in|around|over)\s+(?:the\s+)?)?{WHEN_WORD}"
    r"|\s+(?:at|by|after|before|around|about|from|till|until|between)\s+(?:(?:about|around|roughly|half)\s+)?\d"
    r"|\s+(?:(?:after|before) (?:work|school|uni)|any ?time|whenever|when|straight away|right away|first thing|same day|"
    r"in (?:a|an|half an?|the|\d+) ?(?:bit|mo|moment|min\w*|sec\w*|while|hours?|hrs?|couple|few)|at (?:a|any) time|"
    r"at (?:your|ur|yr) (?:earliest )?convenience|at short notice|in person|and|or|but|if|so|as|once|then|too|also|"
    r"myself)\b", re.IGNORECASE)
# what's collected, which the place goes after: "collect it today", "collect them", "the phone" ("the same day" is when)
COLLECTED = re.compile(r"\s+(?:it|them|both|these|those|this one|that one|this|that|the (?!(?:same|next|following|day|"
                       r"week|weekend|morning|afternoon|evening|night|end|latest|earliest)\b)[a-z0-9][\w'-]*)\b", re.IGNORECASE)
# ...and a place later in that part of the sentence, which the listing's would clash with: "Can collect today in
# Leeds", "Can collect tonight at yours" ("in person", "at ur convenience" and "at 6" aren't places)
PLACE_LATER = re.compile(r"\b(?:in|at|near|round|outside)\s+(?:the\s+)?(?!(?:your|ur|yr)\s+(?:earliest\s+)?convenience)"
                         r"([A-Za-z][\w'-]*)|\bto (you|yours|ur|urs|your)\b", re.IGNORECASE)
PLACE_CLAUSE_END = re.compile(r"[.!?,;]|\b(?:and|or|but|if|so|as|cos|because|when|whenever|once|then)\b", re.IGNORECASE)
YOURS = {"you", "yours", "your", "u", "ur", "urs", "yrs", "ya", "yer"}  # where the seller is: a place


def collecting_from(closing, pickup):
    """Your own collecting sentence with the place the listing gives, where
    it reads: 'Can collect today.' -> 'Can collect from Leeds LS6 today.',
    'Can collect the phone today.' -> 'Can collect the phone from Leeds LS6
    today.' A closing that already says where ('Can collect from yours',
    'Can collect at yours today', 'Can collect in Leeds today'), asks where,
    or doesn't collect stays as it is (PLACE_GOES)."""
    found = re.search(r"\bcollect\b", closing, re.IGNORECASE) if pickup else None
    if not found or re.search(r"\b(?:from|where|address|postcode|location)\b", closing, re.IGNORECASE):
        return closing  # "Can collect from yours today." already says where
    at = found.end()
    if not PLACE_GOES.match(closing, at):
        thing = COLLECTED.match(closing, at)  # after what's collected: "Can collect it from Leeds LS6 today."
        if not thing or not PLACE_GOES.match(closing, thing.end()):
            return closing
        at = thing.end()
    rest = closing[at:]
    end = PLACE_CLAUSE_END.search(rest)
    later = PLACE_LATER.findall(rest[:end.start()] if end else rest)
    if any(said.lower() in YOURS or said.lower() not in NOT_A_PLACE for pair in later for said in pair if said):
        return closing  # where comes later: "Can collect today in Leeds", "Can collect tonight at yours"
    return f"{closing[:at]} from {pickup}{rest}"


def fit(opener, middle, closing, at_least, item, already=""):
    """opener + middle (the offer and any questions) + closing. A longer
    message that's still short gets "I'm interested in your <item>.", then
    "Let me know what you think.": the only things it can add without making
    anything up, and never twice (already: what's there)."""
    interest = f"I'm interested in your {item}."
    extras = [([], [])]
    if interest.lower() not in already.lower():
        extras.append(([interest], []))
    if FILLER.lower() not in already.lower():
        extras.append((extras[-1][0], [FILLER]))
    text = ""
    for before, after in extras:
        text = join(opener, *before, *middle, *after, closing)
        if len(text.split()) >= at_least:
            break
    return text[:1].upper() + text[1:]  # a message starts with a capital, whatever its first sentence


def priced(text, offer):
    return text.replace("£[OFFER]", offer_words(offer)).replace("[OFFER]", f"{offer // 100:,}")


def default_offer(kind, offer, point=None, questions=(), at_least=0, item="item", pickup="", in_person=False,
                  cash=True):
    """With no past messages, the message AlertFlip writes (LOCAL, POSTED):
    the reason for a lower offer in a sentence of its own, and at or over
    asking after the offer as with your own sentences. in_person: on Facebook or
    Gumtree, where you come and collect (from the listing's pickup place)
    and pay cash. cash: False when the listing says no cash ("would you take
    £[OFFER] for it?"). None if the listing's point can't be said."""
    opener, offer_sentence, closing = (LOCAL if in_person else POSTED)[kind]
    if not cash:
        offer_sentence = re.sub(r"\s+cash\b", "", offer_sentence)
    offer_sentence, closing = collecting_from(offer_sentence, pickup), collecting_from(closing, pickup)
    if kind == "lower" and point:
        reason = reason_sentence(point)
        middle = [offer_sentence, reason]
    else:
        reason = with_reason(offer_sentence, kind, point)
        middle = [reason]
    if reason is None:
        return None
    return priced(fit(opener, [*middle, *merge_questions(questions)], closing, at_least, item), offer)


def greeting_opener(card):
    """Your greeting to open with, as you type it: "Hi mate," or, if you put no
    comma after it, "hi"; "Hi," when your messages have none."""
    greeting = card.get("greeting") or GREETING
    if not card.get("greeting"):
        return f"{greeting},"
    return greeting if card.get("greeting_bare") else f"{greeting}{card.get('greeting_mark') or ','}"  # "Hi mate!"


# when a sentence says you'll come, and the time it gives: a hold "till later" and a closing "Can pick up later." Each
# spelling is the time it is (26 Sep red team: "till tonight. Can collect 2nite." said it twice): every one style.TIMES
# knows, and the typos sellers write ("tonite", "tommorow")
SPELLED = {"2day": "today", "tonite": "tonight", "2nite": "tonight", "2night": "tonight", "this evening": "tonight",
           "this eve": "tonight", "tmrw": "tomorrow", "tmr": "tomorrow", "tomoz": "tomorrow", "2moro": "tomorrow",
           "2morrow": "tomorrow", "tomorow": "tomorrow", "tommorow": "tomorrow", "tommorrow": "tomorrow",
           "later on": "later", "this weekend": "the weekend", "at the weekend": "the weekend"}
WHEN_SAID = re.compile(rf"\b(?:(?P<till>until|untill|till|til|by)\s+)?(?P<time>{TIMES}|"
                       rf"{'|'.join(sorted(SPELLED, key=len, reverse=True))}|later|this week|the weekend)\b(?!['’]s)",
                       re.IGNORECASE)
# ...and what it's the time of: the last of these before it in its clause says whether you'd come then ("if you can
# hold it till later", "if I collect today") or pay ("cash today", "can pay today": no word of coming, 26 Sep red team).
# Not a price's words: "come down to £[OFFER] today", "meet me halfway", "pop it in the post"
TIME_OF = re.compile(r"\b(?:(?P<come>hold|save|keep|reserve|aside|collect\w*|pick(?:ing)?|pickup|come(?! down\b| up\b)|"
                     r"coming|pop (?:round|over|by)|swing (?:by|round)|nip (?:round|over)|be (?:there|round))|"
                     r"pay\w*|cash|transfer\w*|send\w*|bacs|post\w*)\b", re.IGNORECASE)
# a time that can't come out of a sentence and leave it reading: in a list or a range ("today or tomorrow", "from
# today till Sunday", "no later than"), first in it or what it's about ("Is tonight ok?"), or with more of when
# around it ("a bit later", "late tonight", "first thing tomorrow", "tomorrow morning", "tonight if not tomorrow"),
# a word that only went with it ("over the weekend", "as early as tomorrow", "tonight latest", "tonight too") or a
# goodbye ("speak later"): 26 Sep red team, "Can collect over.", "Can collect latest.", "Can collect, speak."
JOINED_BEFORE = re.compile(r"(?:\b(?:or|and|n|from|between|either|nor|to|than|for|on|at|in|of|next|since|after|before|"
                           r"is|was|does|do|would|will|could|should|if|whether|bit|abit|little|much|slightly|lot|late|"
                           r"early|thing|weeks?|days?|hours?|hrs|mins|minutes|no|over|during|throughout|within|as|"
                           r"around|latest|earliest|speak|talk|chat|cya|(?:see|catch|speak to|talk to) (?:you|ya|u))"
                           r"|[&/+,\-–])\s*$", re.IGNORECASE)
ANOTHER_TIME = rf"(?:{TIMES}|later|tonite|2night|(?:mon|tues?|wed(?:nes)?|thu(?:rs)?|fri|sat(?:ur)?|sun)(?:day)?s?|" \
               r"(?:the )?weekend|whenever|any ?time|next|this|morning|afternoon|evening|night|\d)\b"
JOINED_AFTER = re.compile(rf"\s*,?\s*(?:or\b|[/+\-–]|(?:to|till|until|til|than|onwards?|ish|itself|morning|afternoon|"
                          rf"evening|eve|night|lunch\w*|am|pm|is|isn't|was|would|will|works?|suits?|ok|okay|good|"
                          rf"fine|alright|better|else|otherwise|failing|latest|earliest|at the (?:very )?(?:latest|"
                          rf"earliest)|too|also|as well|even|ideally|preferably|hopefully|probably|maybe|possibly|"
                          rf"perhaps|though|tho)\b|(?:and|&|n)\s+{ANOTHER_TIME})|"
                          rf"\s*,\s*{ANOTHER_TIME}", re.IGNORECASE)
# ...nor out of one where when is the point: "Can't collect till tonight" isn't "Can't collect", nor is "Can only
# collect tonight" "Can only collect" (style.CONTRAST's words, and a few more)
WHEN_IS_THE_POINT = re.compile(r"\b(?:not|never|but|unless|except|instead|rather|only|cannot|cant|wont|dont)\b|"
                               r"n['’]t\b", re.IGNORECASE)
# a closing that says nothing but that you'll collect, once its time is out: "Can collect", "I can pick it up", "Can
# come and get it", "Happy to pop round", "Collection"
COLLECT_ONLY = re.compile(r"^(?:(?:i|we|i'?ll|ill|we'?ll|i'?m|im|can|could|will|would|happy|to|be|able|free|easily|"
                          r"def|definitely|also|just|so)\s+)*"
                          r"(?:(?:come|pop|nip)\s+(?:round\s+|over\s+)?(?:and|&|n|to)\s+)?"  # "come and get it"
                          r"(?:collect(?:\s+(?:it|them))?|collection|pick\s+(?:it\s+|them\s+)?up|pickup|"
                          r"get\s+(?:it|them)|grab\s+(?:it|them)|come(?:\s+(?:round|over|by))?|pop\s+(?:round|over|by)|"
                          r"swing\s+(?:by|round)|nip\s+(?:round|over)|drop\s+by|be\s+(?:there|round))"
                          r"(?:\s+(?:then|please|pls|plz|mate))*$", re.IGNORECASE)
# thanks typed at the end of a sentence, a sign-off of its own: "can pick up later ta x", "Can collect later, cheers"
THANKS = re.compile(r"[\s,.!]+(?:ta|thanks|thank you|thank u|thankyou|thanx|thx|ty|tia|cheers|many thanks)"
                    r"(?:\s+(?:a lot|so much|very much|again))?(?:\s+(?:mate|bud|pal|hun|love|m8))?[.!]*$",
                    re.IGNORECASE)
# where an offer's main clause ends after its price (paid_at): " if you can hold it", ", as it's in excellent
# condition", " and can come and collect", its full stop, or its end, and before a word that only rounds it off: "for
# it today mate", "today no problem", "today please" (26 Sep red team: "for it mate today"; "for my mate" is no such word)
PAY_CLAUSE_END = re.compile(r"(?:(?<!\bmy)(?<!\bour)(?<!\byour)(?<!\bthe)(?<!\ba)\s+(?:mate|m8|pal|bud|bro|buddy|hun|"
                            r"love|please|pls|plz|no (?:problem|probs?|worries|bother)|thanks|ta|cheers|then))?"
                            r"(?:\s*[,;:]|\s+[-–—]\s|\s+(?:if|as|given|because|cos|considering|due to|so|and|but|when|"
                            r"once|provided|seeing as|since|unless|or)\b|\s*[.!?…]|\s*$)", re.IGNORECASE)


def time_of(said):
    """The time a spelling says: "2nite" and "this evening" are "tonight", "Tmr" is "tomorrow"."""
    said = re.sub(r"\s+", " ", said.lower())
    return SPELLED.get(said, said)


def times_in(sentence):
    """The times a sentence gives, each with whether it's when you'd come
    (TIME_OF): "I'll pay £[OFFER] cash today if you can hold it till 2nite"
    -> {("today", False), ("tonight", True)}."""
    found = set()
    for when in WHEN_SAID.finditer(sentence):
        clause = re.split(r"[,;:.!?]|\b(?:and|but)\b", sentence[:when.start()])[-1]
        last = list(TIME_OF.finditer(clause))[-1:]
        waits = (when.group("till") or "").lower() in ("until", "untill", "till", "til")  # "wait until tonight"
        found.add((time_of(when.group("time")), waits or bool(last and last[0].group("come"))))
    return found


def collects(sentence):
    """Whether a sentence says you'll come to the seller, in any words
    (style.HABIT_WORDS): "Can collect", "Can pop round later", "I can come
    at 6"; not "Does it come with a charger?"."""
    return bool(HABIT_WORDS["collecting"].search(sentence) or
                re.search(r"\bcome\b(?!\s+with\b)", sentence, re.IGNORECASE))


def signed_off(sentence):
    """A sentence and its sign-off as typed, thanks too (split_sign_off has
    the emojis and kisses): ("can pick up later", " ta x")."""
    core = split_sign_off(sentence)[0]
    thanks = THANKS.search(core)
    if thanks and re.search(r"\w", core[:thanks.start()]):
        core = core[:thanks.start()]
    return core, sentence.rstrip()[len(core):]


def sign_left(sign):
    """What stays of a sentence that goes: its sign-off ("ta x", "👍"), not
    a lone "..."."""
    return sign.lstrip(" ,") if re.search(rf"\w|{EMOJI_IN.pattern}", sign) else ""


def without_times(sentence, found):
    """A sentence with the times found in it taken out: "Can collect
    tonight and pay cash." -> "Can collect and pay cash.". None when one
    can't come out and leave it reading ("today or tomorrow": JOINED_BEFORE,
    JOINED_AFTER), or less than two words are left ("Collection.")."""
    for when in sorted(found, key=lambda m: m.start(), reverse=True):
        before, after = sentence[:when.start()], sentence[when.end():]
        if not re.search(r"[A-Za-z]", before) or JOINED_BEFORE.search(before) or JOINED_AFTER.match(after):
            return None
        # "up until tonight" is one phrase: never "Can collect up." (26 Sep red team); "pick up tonight" is no "up until"
        if (when.group("till") or "").lower() in ("until", "untill", "till", "til") and \
                re.search(r"\bup\s*$", before, re.IGNORECASE):
            return None
        sentence = before.rstrip() + after
    sentence = re.sub(r"\s+([,.!?…])", r"\1", re.sub(r",\s*(?=[.!?…]|$)", "", sentence)).strip()
    return sentence if len(re.findall(r"[A-Za-z']+", sentence)) >= 2 else None


def time_once(closing, come, pay):
    """Your closing with a time your offer already gives said once (the 26 Sep
    review). After "...if you hold it till later", "Can pick up later." goes,
    as the hold says when you'd come; a sentence that says more keeps all but
    the time ("Can collect tonight and pay cash." -> "Can collect and pay
    cash."), and so does one after an offer that only says when you'd pay
    ("...£170 cash today?" then "Can collect today." -> "Can collect."). A
    sentence that holds never goes ("Could you hold it for me and I'll
    collect tonight?" -> "...and I'll collect?"), nor the thanks typed in one
    ("can pick up later ta x" -> "ta x"), and a time that can't come out
    and leave it reading stays ("Can collect today or tomorrow.", "Can't
    collect till tonight."). come and pay: the offer's times (times_in),
    when you'd come and when you'd pay."""
    kept = []
    for sentence in (s.strip() for s in SENTENCES.split(closing) if s.strip()):
        core, sign = signed_off(sentence)
        holds = bool(HELD.search(core) or HOLD.search(core))
        shared = [m for m in WHEN_SAID.finditer(core) if time_of(m.group("time")) in come | pay]
        if not shared or not (holds or collects(core)) or WHEN_IS_THE_POINT.search(core):
            kept.append(sentence)
            continue
        rest = core
        for when in reversed(shared):
            rest = rest[:when.start()].rstrip() + rest[when.end():]
        if not holds and {time_of(m.group("time")) for m in shared} <= come and \
                COLLECT_ONLY.match(rest.strip(" .!?…")):
            kept.append(sign_left(sign))  # nothing but collecting then: "Can pick up later." goes, its "ta x" stays
        else:
            plain = without_times(core, shared)
            kept.append(f"{plain}{sign}" if plain else sentence)
    return " ".join(k for k in kept if k)


def said_once(sentence):
    """How time_once may say one of your sentences after an offer that gives
    its time: with that time taken out ("Can collect tonight, 10 mins away."
    -> ["Can collect, 10 mins away."]), or all its times. Still your words,
    for the checks that let yours by (26 Sep red team: its "10" was refused as
    a number that isn't yours, once "tonight" was out)."""
    core, sign = signed_off(sentence)
    found = list(WHEN_SAID.finditer(core))
    times = {time_of(m.group("time")) for m in found}
    said = []
    for out in [{time} for time in sorted(times)] + ([times] if len(times) > 1 else []):
        plain = without_times(core, [m for m in found if time_of(m.group("time")) in out])
        if plain:
            said.append(f"{plain}{sign}")
    return said


def paid_at(sentence, when):
    """Your offer with when you'd pay, at the end of its main clause as
    you'd say it: "I'll pay £[OFFER] cash if you can hold it for me." ->
    "I'll pay £[OFFER] cash today if you can hold it for me.", not
    "£[OFFER] today cash" (26 Sep red team). As it is with no price in it."""
    price = re.search(r"£?\[OFFER\](?:\s*(?:quid|pounds)\b)?", sentence)
    if not price:
        return sentence
    at = PAY_CLAUSE_END.search(split_sign_off(sentence)[0], price.end()).start()
    return f"{sentence[:at]} {when}{sentence[at:]}"


def write_offer(card, kind, offer, point=None, questions=(), at_least=0, item="item", pickup="", in_person=False,
                cash=True, posted=False, liked=None):
    """One offer message from your phrasebook (card["phrases"]), or, if you
    have no past messages, AlertFlip's (default_offer); None if the listing's
    point can't be said in a sentence this knows (then the AI writes).
    point: the listing's flaw, low battery or good condition to give as the
    reason (flip.offers), only when it's to be said. questions: the open
    ones, for a longer message. at_least: the words a longer message needs.
    item: what to call the item. pickup: where the listing says to collect.
    in_person: a Facebook or Gumtree listing (local_market). cash: False when
    the listing says no cash (your own sentences then come without it: the drafter's without_cash).
    posted: a listing that won't be collected (eBay, Vinted, "Postage only"):
    no asking them to hold it at the asking price, and over it the reason is
    "if you take the listing down and sell it to me"."""
    if not card:
        return default_offer(kind, offer, point, questions, at_least, item, pickup, in_person, cash)
    # the closing you write with this kind of offer, with no hold under asking and nothing calling it low at or over
    # it (flip.style.for_kind: "Could you hold it for me?" ended a lower offer, 26 Sep red team)
    card = for_kind(card, kind)
    phrases = dict(card.get("phrases") or {})
    if not card.get("emoji"):  # your messages don't use them: one a near-repeat had ("Thanks 😊") isn't yours
        phrases = {slot: re.sub(r"\s{2,}", " ", EMOJI_IN.sub("", text)).strip()
                   if slot != "emoji" and isinstance(text, str) and EMOJI_IN.search(text) else text
                   for slot, text in phrases.items()}
    if posted:  # eBay, Vinted: you'd just buy it at the asking price, so no asking them to hold it
        phrases["closing"] = " ".join(s.strip() for s in SENTENCES.split(phrases.get("closing") or "")
                                      if s.strip() and not HELD.search(s)) if phrases.get("closing") else phrases.get("closing")
        for slot in ("offer_asking", "offer"):
            if phrases.get(slot) and kind == "asking":
                phrases[slot] = HOLD_CLAUSE.sub("", phrases[slot]).strip()
        if phrases.get("opener") and kind == "asking":
            phrases["opener"] = " ".join(s.strip() for s in SENTENCES.split(phrases["opener"])
                                         if s.strip() and not HELD.search(s))
    opener = phrases.get("opener")
    # your greeting sat in your offer sentence ("Hi mate, would you take..."): with that sentence gone, it opens. Not
    # for someone who never greets ("£150 cash? Can collect today."): it opens with the offer, as they do (26 Sep red team),
    # whatever they open with besides ("Is this still available?", "Still for sale?": round 2, no opener habit got "Hi,")
    opener = opener if opener is not None and (opener or phrases.get("offer") or card.get("no_greeting")) else \
        "" if card.get("no_greeting") else greeting_opener(card)
    # how you word this kind of offer, else your usual offer sentence made to fit it, else a neutral one; an emoji
    # that sat after your greeting ("Hey! 😊 Would you do...") isn't the offer's
    offer_sentence = re.sub(rf"^(?:{EMOJI_IN.pattern}\s*)+", "",
                            phrases.get(f"offer_{kind}") or phrases.get("offer") or NEUTRAL[kind])
    # under asking it's asked: "I can pay £70" from your asking-price habit would tell them; not when your lower offers
    # don't ask ("I can pay 185": asks_lower False, 3 Oct)
    if kind == "lower" and card.get("asks_lower") is not False:
        offer_sentence = as_question(offer_sentence)
    if kind == "more" and not phrases.get("offer_more"):  # over asking isn't "the full asking of £235"
        offer_sentence = re.sub(r"\s{2,}", " ", FULL_ASKING.sub("", offer_sentence))
    closing = collecting_from(phrases["closing"], pickup) if phrases.get("closing") else ""
    if kind != "lower":  # at or over asking: said, and never called low...
        # ...but your own way of saying they'd hold it stays yours ("I'll do £[OFFER] if you can save it for me"), when
        # it says it: one that asks ("£[OFFER] if you hold it?") is said plainly, as over asking always is
        own_hold = kind == "more" and not posted and phrases.get("offer_more") and HELD.search(offer_sentence) \
            and not asks(offer_sentence)
        offer_sentence = offer_sentence if own_hold else as_statement(offer_sentence)
        if LOWBALL.search(offer_sentence):
            offer_sentence = NEUTRAL[kind]
        opener = opener if not LOWBALL.search(opener) else greeting_opener(card)
        closing = closing if not LOWBALL.search(closing) else ""
    if kind == "more" and posted:  # eBay, Vinted: why you'd pay more there, not holding it for you
        core, sign = split_sign_off(offer_sentence)
        if not re.search(r"\btake (?:it|the (?:ad|advert|listing|post)) down\b|\bend (?:the |your )?listing\b", core,
                         re.IGNORECASE):  # your own take-down reason stays, once
            core = re.sub(r",?\s+if\b.*$", "", core.rstrip(" .!?"), flags=re.IGNORECASE)  # one "if": not "if that's ok if..."
            core = f"{core.rstrip(' .!?')} {TAKE_IT_DOWN}"
        offer_sentence = f"{core.rstrip(' .!?')}.{' ' + sign if sign else ''}"
        closing = " ".join(s.strip() for s in SENTENCES.split(closing) if s.strip() and not HELD.search(s))
    elif kind == "more" and not (point and point.get("about") == "condition") and not HOLD.search(offer_sentence) \
            and not HELD.search(closing):
        # paying over asking says why, once (not again if your closing asks it); a flaw you don't mind isn't why (14 Oct)
        offer_sentence = held(offer_sentence)
    greeting, rest = split_greeting(offer_sentence)
    if opener and LEADING_GREETING.match(opener) and greeting:  # one greeting: the opener's ("Hi mate, hi mate, would...")
        offer_sentence = rest[:1].upper() + rest[1:]
    elif not opener and not greeting and card.get("greeting"):  # your greeting sits in your other kinds' sentence
        opener = greeting_opener(card)
    if not opener:  # "Hi mate, would you take £185?": anything added goes after "Hi mate,"
        opener, offer_sentence = greeting_apart(offer_sentence)
    # your "Don't mind the condition." after your offer takes the listing's point there, once (26 Sep red team)
    closed = point_in_closing(closing, kind, point) if closing else (closing, point)
    if closed is None:
        return None
    closing, point = closed
    reasoned = with_reason(offer_sentence, kind, point)
    if reasoned is None:
        return None
    paid = None  # paying said once: "I can pay £300 straight away.", and "I'll pay the full £450." then not "I'll pay
    if closing and PAY_SAID.search(reasoned):  # as soon as you accept."; when you'd pay goes in the offer, once
        kept = []
        for part in (part.strip() for part in SENTENCES.split(closing) if part.strip()):
            core, sign = signed_off(part)
            when = PAY_WHEN.match(core)
            pays_first = PAY_FIRST.search(part) or when and re.fullmatch(PAID_NOW, when.group("when"), re.IGNORECASE)
            if in_person and pays_first:
                kept.append(part)  # "Can pay now." where you meet the seller: as it is, for the pay-first check (26 Sep)
            elif when or PAY_SAID.search(part):
                if when and not (paid or WHEN_SAID.search(offer_sentence) or
                                 re.search(rf"\b(?:{PAID_NOW})\b", offer_sentence, re.IGNORECASE)):
                    paid = when.group("when")
                    reasoned = paid_at(reasoned, paid)  # "I'll pay £[OFFER] cash today if you can hold it for me"
                kept.append(sign_left(sign))  # its own sign-off stays: "Can pay today x"
            else:
                kept.append(part)
        closing = " ".join(k for k in kept if k)
    # the time once (26 Sep review), as your own offer sentence gives it before the listing's words go in ("given the
    # screen started flickering today" is the seller's today: 26 Sep red team), and as paying put it in just now
    times = times_in(offer_sentence) | (times_in(paid) if paid else set())
    if closing and times:
        closing = time_once(closing, {time for time, come in times if come}, {time for time, come in times if not come})
    if closing and not re.search(r"\w", closing) and re.search(rf"(?:{EMOJI_IN.pattern})\s*$", reasoned):
        closing = ""  # an emoji closing after an offer that ends with one: not "...save it for me 🙏 🙏"
    # how you say you like the item, with this one's name ("I like the PS5."), after the offer as you write it (3 Oct)
    # ...once (not when your own sentence already says it: "I really like it. Can collect today."), and only with a name
    # that reads after "the" ("the ps5", not "the the ps5", "the ITEM" or "the Wanted: iPhone 14": 3 Oct review)
    # liked: the item named the way you name it ("the phone", "the ps5": flip.style.item_naming), else its model
    named = re.sub(r"^the\s+", "", liked or item or "", flags=re.IGNORECASE).strip()
    said_already = LIKES.search(" ".join(filter(None, (opener, offer_sentence, closing))))
    fits = bool(re.search(r"[A-Za-z]", named)) and named.lower() not in ("item", "items") and \
        not re.search(r"[:*]|\b(?:free|wanted|swap|collect\w*|job ?lot)\b", named, re.IGNORECASE)
    liked = [f"{card['likes'].replace('{item}', named)}."] if card.get("likes") and fits and not said_already else []
    text = fit(opener, [reasoned, *liked, *merge_questions(questions)], closing, at_least, item)
    if card.get("emoji") and phrases.get("emoji") and not EMOJI_IN.search(text):  # one is enough: not "🙏 😊"
        text = f"{text} {phrases['emoji']}"
    if card.get("greeting_bare") and card.get("greeting"):  # "hi wud u...", so never "Hi Would you take"
        text = re.sub(rf"^({re.escape(card['greeting'])}) (?!I\b|I')((?-i:[A-Z]))", lambda m: f"{m.group(1)} {m.group(2).lower()}",
                      text, flags=re.IGNORECASE)
    return priced(text, offer)


def asked_already(question, text):
    """Whether a draft already asks this question: its words ("charger",
    "battery health") are in one of the draft's questions."""
    keys = {w for w in re.findall(r"[a-z]+", question.lower()) if w not in QUESTION_FILLER}
    asked = set()
    for sentence in SENTENCES.split(text):
        if ends_asking(sentence):
            asked |= set(re.findall(r"[a-z]+", sentence.lower()))
    return bool(keys) and keys <= asked


def make_longer(previous, questions=(), at_least=0, item="item"):
    """The draft on screen with the open questions it doesn't ask yet, added
    before its closing (a last sentence with no price and no question),
    every word of it kept."""
    sentences = [s.strip() for s in SENTENCES.split(previous.strip()) if s.strip()]
    last = sentences[-1] if sentences else ""
    closing = last if len(sentences) > 1 and "£" not in last and not ends_asking(last) else ""
    body = sentences[:-1] if closing else sentences
    opener, first = greeting_apart(body[0]) if body else ("", "")
    if opener:
        body = [first, *body[1:]]
    elif len(body) > 1:
        opener, body = body[0], body[1:]
    new = merge_questions([q for q in questions if not asked_already(q, previous)])  # each one on its own first
    return fit(opener, [*body, *new], closing, at_least, item, already=previous)
