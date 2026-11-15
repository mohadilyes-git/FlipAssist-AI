# FlipAssist-ai

Drafts eBay listings and offer messages for a reseller, and prices a listing for the UK. Plain code does everything it can. A small local AI model does only what code can't. With your own Anthropic key, Claude Haiku 5.5 also checks every offer's reason, writes the eBay listing (since 14 Oct: measured better and cheaper, below) and judges how bad the damage is for the UK price, and a paid API model steps in when a local answer fails a check. A person approves every draft.

> **Work in progress.** The plain-code half, its safety checks, the AI listing drafter, the message drafter and the API are built and tested. Next: a catalogue agent and measured results on real items.

## What it does now

- **Finds the product** in a messy listing title ("iphone13 128gb unlocked boxed") using a catalogue of 42 models: every iPhone from the SE to the 17, plus the Galaxy S23, PS5, PS5 Slim, Switch OLED and AirPods Pro 2. It then fills every fact the catalogue knows:
  - model and storage;
  - colour, when the text names exactly one;
  - options such as Disc or Digital;
  - network lock;
  - specs.
- **Reads numbers by what the product can be** (`flip/numbers.py`). Once the model is known, so are its possible answers:
  - storage: an iPhone 13 comes in 128, 256 or 512 GB, so "iPhone 13 128", "128g", "128 gig" and "128 go" are all 128GB, while "64" isn't a size it comes in;
  - battery health, from the reseller's notes however it's written ("battery 84", "84 battery health", "%84 BH", "84🔋", or "78" on its own), handed to the AI as a settled fact;
  - numbers that belong to something else are taken out first: the model's name (the 13 in "iPhone 13"), prices ("£128", "128 ono", "bought 128"), times ("90 days"), addresses ("77 High Street"), codes ("BH21"), charge cycles ("256 cycles") and phone numbers;
  - each battery word belongs to one figure, so in "iPhone 13 128 Battery 87%" the 128 is still the storage;
  - on 2,091 real UK phone titles, storage is filled in 1,067 instead of 1,028, with none lost or changed, and every battery figure read from real listings has a battery word or a % sign next to it;
  - two test agents wrote 436 messy cases to break it; the 73 real failures they found are fixed and kept as tests.
- **Leaves gaps instead of guessing.**
  - Anything code isn't sure about goes on a "missing" list.
  - Parts, accessories, wanted ads and listings that name two products aren't matched at all.
- **Builds the eBay title** from a template, within eBay's 80-character limit.
- **Fills eBay's own fields in eBay's own words** (iPhones, `flip/ebay.py`):
  - the category (Mobile & Smart Phones) and the four fields eBay won't list a phone without: Brand, Model, Storage Capacity and Colour;
  - then what the catalogue and the reseller's notes already know: network, 4G/5G, operating system, screen size and chip;
  - spelt as eBay's lists spell them ("Apple iPhone 13", "128 GB", "Apple A15 Bionic"); each colour becomes one of eBay's 16 plain colours, the one UK sellers pick for it (Midnight is Black, Rose Gold is Pink: `data/ebay_map.json`, with the counts);
  - eBay's lists come from its own API (`python -m flip.ebay --refresh` writes `data/ebay_fields.json`), and a test holds every phone in the catalogue to them.
- **List on eBay is for iPhones only, written from the reseller's title and notes alone** (14 Oct 2026, the owner's call; the page says so). Anything else the catalogue knows (the Galaxy S23, the consoles, AirPods) is turned away before the AI is asked, and the original seller's description isn't asked for or used: on eBay the reseller is the seller, so the listing says only what they checked, as AlertFlip's List on eBay does. An empty field eBay needs is theirs to fill in.
- **flip-reader-5 reads your notes and Claude Haiku 5.5 phrases what it found: the eBay listing's condition note and description; Claude Sonnet 5.5 rewrites one that fails the checks or leaves a fact out** (14 Oct 2026). flip-reader-5 (Gemma 3 4B when it isn't installed, code when neither is) and code pull the facts out of your notes (each flaw sentence split into its flaws; battery, network, what's in the box, what works, repairs, in your own words), and Haiku gets only that list, never the notes, and turns it into sentences; code checks every fact made it in. Judged blind by two judges on 40 real UK iPhones (notes made from Vinted listings no model had seen), as the app shows them:

  | Writer | Postable as is | Says something the notes don't | Leaves a note out | Score (1-5) | Per listing |
  |---|---|---|---|---|---|
  | **flip-reader-5's facts, Claude Haiku 5.5 phrasing them, Sonnet if it fails** | **95%** | **2%** | **5%** | **4.59** | **0.040p** |
  | Claude Haiku 5.5 reading the notes itself, Sonnet if it fails | 90% | 2% | 26% | 4.45 | 0.036p |
  | flip-reader-5's facts, Gemma 3 4B phrasing them, Sonnet if it fails | 69% | 18% | 8% | 3.98 | 0.153p |
  | flip-reader-5's facts, code writing them (no model) | 6% | 1% | 20% | 3.30 | free |
  | Claude Sonnet 5.5 alone | 90% | 8% | 10% | 4.64 | 0.289p |

  Gemma 3 4B made up marks even from the checked facts (Sonnet rewrote 22 of 40, so it was the dearest way), and code's own sentences read like notes. `FLIP_LISTING_WRITER=notes` in `.env` goes back to Haiku reading the notes itself, `gemma` to Gemma 3 4B. The writer is told it's an iPhone, to write as the seller about the phone (never about the notes), and is handed no specs (eBay's fields carry them); code puts your battery figure in the condition note when the writer leaves it out. The tests found checks refusing faithful drafts ("never repaired and fully working", "no charger or box", "doesn't affect how it works", a scratched screen protector, "a black dot on the screen" read as the phone's colour), "no box, charger or cable" read as a charger and a cable that come with it, and an unused case or an unopened pack of screen protectors making a used phone New: all fixed, with the cases as tests.
- **Sets eBay's condition from the reseller's notes:** For parts or not working for a fault, New or Opened - never used only when the notes back it, Used otherwise. A crack or scratch on its own is wear, not a fault. The AI writes the condition note to match and can't answer another condition.
- **Does the money in pence:** profit after fees, and an offer price rounded to a tidy number.
- **Checks an AI answer before it's used:**
  - the agreed shape and allowed values;
  - no numbers the inputs don't contain;
  - no yes/no claims about the box, charger, cable, case, controller, dock, game, screen protector, receipt, warranty or network lock that the inputs don't back up, with the reseller's notes beating the seller's text;
  - condition claims (new, sealed, working, flawless, battery, scratches and other marks) only when the reseller's own notes back them, and "For parts or not working" whenever the notes mention a fault;
  - where a mark is ("on the back") only when the notes say where;
  - what people type is read with typos allowed ("few scraches", "baterray 88", "bh 88%"), the AI's own words as written. A slip is a letter left out, doubled or swapped, a key touching the right one ("scrstch") or another vowel ("excellant"): one in a word of 4 to 8 letters, two in a longer one. A real word is never read as a typo ("cash" isn't a case: `data/real_words.json`, built from macOS's dictionary by `python -m flip.real_words`), nor is a typo as close to an everyday word ("minr" is as close to minor as to mint). A typo inside a "no" still says no ("crak free", "out of warrenty"), and so does a "no" typed without its apostrophe ("doesnt come with charger");
  - nothing that contradicts the item: another model, colour, storage size or edition;
  - no prices, contact details or paying off the platform;
  - length limits.
- **Drafts the rest with AI** (`python -m flip.draft`):
  - Gemma 3 4B runs on the reseller's own machine through Ollama. It's asked only for what code couldn't fill: the colour (from that model's real colours, or "unsure"), a condition note and a description, held to an exact answer shape.
  - The checks decide. An answer that fails gets one try on Claude Sonnet 5.5 (Claude Haiku 5.5 before 14 Oct: in the app, Haiku now writes the listing first, as above). If that fails too, the item is marked "needs you".
  - If Gemma 3 4B's answer passes but it can't tell the colour from the photos, Claude Sonnet 5.5 gets one look at the colour alone (about 0.01p when it was Haiku; Sonnet's tokens cost 20 times as much). The draft is still Gemma 3 4B's, and the app says who picked the colour.
  - If Ollama isn't running, nothing is sent to Claude Sonnet 5.5 instead.
  - If Gemma 3 4B ends its answer with a curly quote (”), or writes two in a row, it's stopped there and the answer closed, instead of running on for a minute.
  - A draft is "ready" only when nothing is missing.
  - Every attempt goes into a private audit log with its tokens, seconds and cost.
- **Drafts offer messages in the reseller's own style** (`python -m flip.message`):
  - **Before the reseller has any past messages, it writes AlertFlip's.** These are the messages the AlertFlip app's AI writes, here written by code with no AI. On Facebook and Gumtree the reseller pays cash and comes to collect; on eBay and Vinted it's paid through the site, so neither is said. For an iPhone 14 Pro at £250 whose listing says "Battery Health: 80%":
    - lower: *Hi, would you take £235 cash for it? I'm offering that because the battery health is 80%. I can come and collect.*
    - asking: *Hi, is this still available? I'll pay the full £250 cash and can come and collect. Could you hold it for me?*
    - more: *Hi, I'll pay £265 cash if you take the listing down and sell it to me. I can come and collect.*

    Before this (12 Sep) the same listing got *Hi, would you take £235 for it? Thanks.* from code, and *I can pay £235* from Gemma 3 4B, which passed the checks of the time.

    Cash is said unless the listing says no cash ("No cash, bank transfer only", "PayPal only"): then neither code, the AI nor the reseller's own sentences offer it.
  - **When the AI writes before there are past messages**, it gets the shape of a good message for its kind and a short list of what the message must do, last, where a small model follows it. On Facebook and Gumtree it says cash and collecting in the offer's own sentence ("I can pay £300 cash and come and collect it"). After a lower offer, code adds the reason and that sentence itself ("I'm offering that because the back glass is cracked. I can pay cash and come and collect it."), as the AI pasted the seller's words in badly; elsewhere code adds whichever half is missing, never to a message that asks the seller to deliver. iCloud and locks aren't named at all unless the listing talks about them.
  - **An answer that fails the checks gets one free try on Gemma 3 4B before Claude Sonnet 5.5** (Haiku before 14 Oct), told what was turned down in the checks' own words; one that can't be read (cut off at its token limit, or not JSON) has nothing to be told about and goes straight to Sonnet.
  - Three kinds of offer, each priced by code. The AI never picks a price.
    - Lower: 15% under asking by default, rounded down to a tidy number.
    - The asking price.
    - More: asking plus 5%, rounded up to a tidy number and at least one step over.
  - **FlipAssist's own reader reads the listing when this Mac has it.** That's flip-reader-5: Gemma 3 4B fine-tuned on 33,160 labelled listings to quote exactly the sentences that state a flaw. It isn't in the repo itself (it's on the repo's GitHub release: [FlipAssist's own models](#flipassists-own-models)); when Ollama doesn't list it, or it doesn't answer, Gemma 3 4B reads as described below, and `FLIP_READER_MODEL=` (empty) in `.env` turns it off. Its reading gets the safety checks only: every quote must be in the listing, a flaw the seller denies is dropped, a seller's story told before the flaw is cut off, and the pickup and "no offers" are checked as for any reading. The splitting and adding below (counting only quotes in so many flaw words, adding code's own flaws) is left out because on 5,032 listings no model had seen (26 Sep 2026) it took the flaws the reader found from 96.5% to 89.4% on UK iPhones and from 94.3% to 68.3% on US and Canadian listings. The message's reason is worded from the reader's whole sentences (next point), never cut to a few words.
  - **The reason is worded by FlipAssist's own wording model, and checked** (`flip/wording.py`, 3 Oct 2026):
    1. flip-wording (Gemma 3 4B with a LoRA trained on 14,513 labelled reasons, merged for Ollama as `flip-wording-4b`; `flip-wording-3` before 6 Oct) turns the reader's flaw sentences into one clause: "the battery health is 81%, there's a small chip on the bottom left corner and there are a few light scratches on the screen". Free, on this Mac.
    2. Claude Haiku checks every clause against the rules (`data/wording_rules.md`) and answers only "ok" or "fix" (about 0.01-0.04p). Any other answer counts as no check: the reason goes out as flip-wording wrote it, marked not checked.
    3. Only a clause Haiku flags (about 1 in 7: 105 of 740 in the 3 Oct test) goes to Claude Sonnet, which keeps it or corrects it.
    - Measured on 740 listings no model had trained on, judged blind (3 Oct, round 3, `flip-wording-3`): 91.6% sendable alone, with Haiku's flag and Sonnet's fix about 95%; plain code's wording 39% (on 240 of them).
    - Round 4 (`flip-wording-4b`, 6 Oct) learned four more rules: "for parts only" is said but a seller's "can be used for parts" isn't, a missing charger or box isn't a flaw, nor is a mark on a screen protector, and a custom phone system is. Judged side by side with round 3 under those rules on the same 740 listings: 90.3% sendable against 88.0% (p = 0.024), a made-up fact 3.4% against 5.0% ([MODELS.md](MODELS.md)). On fresh listings it isn't proven better: 94.5% against 91.4% on the first fresh test, then a tie on the second (90.8% each). `FLIP_WORDING_MODEL=flip-wording-3` in `.env` goes back, on a Mac that still has it (it isn't on the release).
    - Every step falls back: no flip-wording (or `FLIP_WORDING_MODEL=` in `.env`) and code words the reason as before; a failed or slow check sends flip-wording's clause as it is; with no API key, or in local mode, nothing leaves the Mac, and the reason goes out unchecked. `FLIP_WORDING_CHECK=` / `FLIP_WORDING_FIX=` turn off the check or the fix.
    - The screen says who worded the reason and who checked it, and each step's cost is in the cost meter.
    - **Fast:** the draft is on screen before the check: it comes back with flip-wording's reason ("checking…"), the app asks `/messages/check-reason`, and a fixed reason replaces the message only if you haven't edited it and the message with it passes the same checks as any message, judged against the listing alone: the offer is its only price, and it gives no number, contact detail, talk of paying off the platform, story, extra, condition or battery the listing doesn't (the audit log keeps the fixed text, so approving it counts as unedited). flip-wording asks Ollama for a 2,048-token working memory, so it can stay loaded next to flip-reader-5 instead of swapping (3 Oct, live: 9-11 s per draft before, on screen in 3.1-3.8 s and checked about 1 s later after). With other apps open on a 16 GB Mac, Ollama often keeps only one of them, and loading the other back takes about 2.5 s. Haiku's check runs without thinking.
    - **Cost, measured through the API (3 Oct):** Haiku's check about 0.005-0.008p a listing; it flags about 14%, which go to Sonnet at about 0.15p each: about 30p per 1,000 flawed listings with the cache warm (about £1.59 when every message is 5+ minutes apart and the rules are cached again each time). Listings with no flaw cost nothing.
  - **Without it, the listing is read by Gemma 3 4B, held to the seller's own words by code.** Gemma 3 4B reads the flaws, where to collect and whether the seller takes offers; Claude Sonnet 5.5 (Haiku before 14 Oct) gets one try when Gemma 3 4B's reading fails a check. Code then:
    - keeps only quotes that are in the listing word for word (capitals, punctuation, apostrophes and hyphens aside), so a flaw can't be made up. A quote whose only difference is the seller's typos put right ("Small scratch" for the listing's "Small scratich"), or a few of their words left out ("needs new back screen" from "needs new front screen and back screen"), goes back to the seller's whole phrase; a word the listing doesn't have still fails. The reading's own instruction copied into a flaw ("each fault, damage, mark or sign of wear...") is taken off;
    - counts a quote as a flaw only if it says what's wrong in so many words ("crack", "dot", "stiff", "drifts", "not working"...) and the seller doesn't deny it in the same clause. "Black spots" from "*No* black spots on the screen", "there aren't any dots" and "screen burn: none" fail the reading. A "no" before a list that ends in "or" denies every item: "no scratches, scuffs or visible damage" has no flaw, while "No charger, cracked screen" still has a cracked screen. Facts ("battery health 90%"), praise ("screen is perfect") and asides ("see pics") aren't flaws, and nor are marks said of what comes with the phone ("the protector itself is scratched", "box has a dent": a scratch under the protector is still the phone's), or a part that only points back at a flaw said elsewhere ("the crack does not affect photos", "price reflects the lens damage"). A battery health of 85% or less is a flaw (the reseller's line), and so is a battery that's been replaced, by Apple or anyone (the reseller's rule). So are "eSIM only" (except on the iPhone Air, which only comes that way), "untested", a part the iPhone can't verify and "runs up to iOS 15", each a kind of its own, so a message can't call an untested phone faulty. A seller's own story is cut to the flaw ("I dropped it and cracked the back" becomes "cracked the back");
    - keeps every flaw code finds by itself, judged the same way: AI can add a flaw, never take one away. The more precise words win ("cracked back" over "Good condition apart from cracked back");
    - takes "no offers" only in words that say it ("price is firm"), and never from a listing that takes offers ("open to offers", "offers over £400") or only limits them ("no offers under £250"). A "no offers" Gemma 3 4B gets wrong ("open to reasonable offers") is dropped and code reads it instead: Gemma 3 4B's flaws still count.

    With no model, or none that passes, code reads the listing alone. Sellers' words code has no list for ("black dot on the screen", "hinge is stiff") are then missed.
  - **"No offers" never changes the offer.** The reseller still picks lower, asking or more; the draft carries a note with the seller's words to show under the message.
  - What's worth saying with each offer, in the seller's own words:
    - a flaw ("broken back") is the reason for a lower offer, even when the seller says it's already priced in. A battery health of 85% or less is one of the flaws, read by the same number reader as the reseller's notes. On its own it's said the way AlertFlip says it ("I'm offering that because the battery health is 80%"); with another flaw, both are given ("because of the cracked back and because the battery health is 79%");
    - at the asking price, the message says the reseller doesn't mind it;
    - good condition with no flaw is the reason for paying more.
  - Whether that point goes in isn't learned from the reseller's past messages (14 Oct 2026, the owner's call): the reseller picks, and in the app it's Yes to start with for every kind of offer. Left to the drafter, a lower offer gives its reason, as AlertFlip's do, and over asking good condition goes in when the reseller's past messages give it as the reason for paying more. Otherwise (at the asking price, say) the draft leaves it out and asks: *The listing says "Broken back". Say you don't mind it?*
  - A longer message is still in the API (`length: "longer"`: about twice the reseller's usual length, between 30 and 70 words, saying more only with their usual points and the questions the listing doesn't answer, kept in `data/questions.json`), but the app no longer offers it: Make it longer was taken off the AI message screen on 14 Oct 2026 (the owner's call).
  - A style card worked out by code from the reseller's past messages: their usual greeting, length, questions, emojis and what they mention, plus their phrasebook (the opener, offer and closing they've written in at least two messages, and how they word each kind of offer: under, at or over the asking price).
  - **flip-style-1b reads the messages too** (`flip/style_ai.py`), in the background when they change, never while drafting: flip-style-1b, Gemma 3 4B fine-tuned on 2,833 made-up buyers (never anyone's real messages) to name the habits a buyer repeats. Code checks the sign-off it names against the reseller's messages (in at least 2 of them and 40%), and only that sign-off fills a gap in code's card, marked with the model that found it ("found by flip-style-1b"); its other habits aren't used yet. On the hard style test ([`evals/style/`](evals/style/), 40 made-up buyers it never saw) it found 182 of 189 habits, plain Gemma 3 4B 146. `FLIP_STYLE_AI=` (empty) in `.env` turns it off; `FLIP_STYLE_AI=gemma3:4b` goes back to plain Gemma 3 4B.
  - **Everything it learned is listed, each thing the reseller's to remove**: the greeting, a habit such as paying cash, a sentence, a question asked every time. A removed one is off the style card and out of the past messages the AI is shown as examples, the AI is told never to write it, and a draft that writes it fails the checks. Put back, it's used again. Their messages themselves don't change.
  - **Who writes:**
    - If the reseller's messages repeat, or there are none yet, code writes the message with no AI. It uses their own sentences with the new price, the seller's words for the flaw, and the open questions. A habit is a sentence in at least two messages that names no item and carries no second price. If the seller's words don't fit a sentence it knows ("I dropped it and cracked the back"), or the draft fails a check, the AI writes instead. A lower offer is always asked: if the reseller's habit is paying asking ("I can pay £X cash"), a lower offer comes out as "Would you take £X cash?" until they've asked for less in their own words twice.
    - If their messages vary, the AI writes. It's shown the past messages for the most similar listings, found by meaning (MiniLM embeddings in a Chroma vector database, all on this machine), with their old prices hidden.
    - The pickup place from the listing goes in ("Can collect from Leeds LS6 today") only when the message says it'll collect: the reseller's own messages talk about collecting, or, with none yet, it's a Facebook or Gumtree listing.
  - **The AI gets AlertFlip's rules too** (the app's own instructions to Claude), and code checks every draft against them, whoever wrote it:
    - no asking about iCloud, Find My or locks (that's for once the seller replies; saying back what the listing says about them is fine), no paying before collecting, no compliments about the item, no talk of a conversation there hasn't been ("as you've said", "as agreed"), at most two questions in a usual message, no emojis unless the reseller uses them. "I'll pay" twice is fine;
    - with no past messages: it opens with "Hi", stays under 250 characters, and says cash and collecting on Facebook and Gumtree; never cash on eBay or Vinted, nor where the listing says no cash;
    - nothing the reseller removed from their style.
  - The same checks and fallback as listings, plus checks of their own:
    - the exact offer and no other price;
    - an offer over asking is said, never asked ("would you take £210?" reads like asking for a discount);
    - the condition comes up only when it's meant to, and only as the listing says it: never a flaw it doesn't mention, never "working" for a faulty item. A question like "any scratches?" is fine. The reason flip-wording words counts as the listing's own words here, as code can't judge its rewording: held to the listing alone, code's condition and battery checks would drop 57 of the 925 right reasons flip-wording-4b wrote in the saved blind tests (6.2%) to catch 8 of its 35 made-up ones (15 Nov review). So a fact it makes up (2.9% of 239 fresh listings on 6 Oct, [MODELS.md](MODELS.md)) is caught only by Claude Haiku's check, and with no API key, or in local mode, nothing catches it;
    - nothing said to come with the item (box, charger, unlocked and so on) that the listing doesn't say, and no question the listing already answers;
    - a longer message has enough words;
    - no promise about collecting, cash or posting that the reseller's own messages don't make, or, with none yet, AlertFlip's ("I can arrange collection quickly" was the AI's most common invention). A "games collection" or a "Collector's Edition" isn't a promise;
    - a reason about the item uses only the listing's words ("given the stiff hinge" fails on a listing that doesn't say it), and no other model is named;
    - the asking price is never misquoted, and a lower offer never offers more in words ("if not I can pay the full asking price");
    - no made-up story about the reseller in the common shapes: who it's for, why they want it, where they are, that they don't resell. A place name ("I'm in Leeds") still gets through;
    - nothing about how the damage happened that the listing doesn't say ("I know you dropped it", "looks like water damage", "never been dropped"). Asking ("was it ever dropped?") is fine;
    - no invented numbers, no contact details, nothing off the platform.
- **Scores the code** against a private test set of real items, with a scoring script.

## Measured so far

Two tests from 18 Aug 2026, both on made-up listings, so the real numbers wait for the test set.

**Writing offer messages: code vs AI.** The same listings and offers went through the same checks for 3 resellers. One had no past messages, one's messages all repeat (`testset/messages.example.csv`), and one wrote chatty messages that all differ (made up). 9 Claude judges then ranked 723 drafts blind, without knowing how each was written.

| Reseller | Judged best: the AI's draft | Fine to send as is: code / AI |
|---|---|---|
| No past messages | 3% | 95% / 35% |
| Messages that repeat | 12% | 65% / 49% |
| Chatty, all different | 50% | 100% / 63% (usual length) |

Code's draft took about 5 ms and cost nothing. The AI's took a median of 3.7 seconds. Gemma passed the checks first time in only half the cases, and Haiku fixed the rest for 2.4p across 252 drafts.

The judges' main complaints about the AI's drafts:
- a bare "I can pay £340" with no greeting;
- copying the listing back at the seller;
- promising collection or cash the reseller never offered.

So code writes unless the reseller's messages vary. All three judges agreed on the best draft in 205 of 241 cases. AI judges tend to favour AI writing, which, if anything, counts against code here.

**Reading the listing: code vs AI.** On 24 short descriptions:

| | Code | Gemma, Haiku backup, code checks |
|---|---|---|
| Flaws found | 10 of 17 | 17 of 17 |
| Clean listings given a flaw | 0 of 7 | 0 of 7 |
| Pickup place | none | 3 of 4 (the 4th, "meet halfway", isn't a place) |
| "No offers" | the usual words only | 1 of 1, never wrong |

Without the checks, Gemma claimed flaws on 2 clean listings and said "no offers" on 21 that never did. The reader needed Haiku once in 24 tries, for 0.005p in total.

**Reading flaws on real listings, labelled by the reseller (23 Sep).** The reseller marked each of 652 sentences from 82 real Facebook listings as a flaw or not; with their rule that a replaced battery is a flaw, 102 were flaws. Each sentence was then read as if the AI had quoted it whole, together with code's own reading of its listing:

| | Flaws found (of 102) | Wrong flaws (of 550) |
|---|---|---|
| Code on 14 Sep | 58 | 6 |
| Code now | 99 | 0 |

A MiniLM checker trained on the same labels found 74 of 99 (before the battery-replacement rule) with 25 wrong. It can't compare numbers: a 79% battery and a 93% one look alike to it. So it isn't built. What made the difference:
- a battery health of 85% or less is a flaw. That's the reseller's line, read from the labels: every figure of 85 or under was a flaw, and every one of 86 and up wasn't. Only the battery's health now counts, not a charge level ("battery level 60%"), the past ("was 84%"), a bound ("over 85%"), a rating ("10/10"), a price or a model's number;
- a replaced battery is a flaw, whoever replaced it;
- words the list was missing ("no longer turns on", "untested", "only charges wirelessly", "camera unknown", "eSIM only", "runs up to iOS 15", "dust inside the camera", "light signs of use"...);
- a sentence about one flaw can run to 15 words, not 12;
- no flaw from a denial ("no parts have ever been replaced"), a spec ("2556x1179-pixel display"), a choice ("can be replaced if desired"), what comes with the phone ("the protector itself is scratched") or a part that points back at a flaw said elsewhere.

The three left: a screen protector's cracks the reseller labelled a flaw (they later decided a protector's marks aren't), iOS's own doubt about a battery reading, and a figure on its own line that code does read, as "Battery health 79%", but sentence by sentence can't credit. The 85% line comes from the same labels, the listings were picked for being interesting, and one person labelled them all. The labelled listings stay on this Mac.

Through the whole reading, Gemma's reading failed the checks on 18 of the 82 listings, and each would have paid Haiku to read it again. 16 were a "no offers" Gemma got wrong and 2 a seller's typo it put right. With both fixed, 17 of the 18 pass on this Mac; the last is two quotes Gemma reworded, still refused.

**Breaking the 23 Sep changes.** Four test agents wrote 2,417 cases against the battery rule, the new flaw words, the guards against wrong flaws and how it all fits together, and a second agent re-ran every failure: 63 confirmed. They included a model's number read as the battery ("iPhone 13 battery is good" gave "the battery health is 13%"), a rating, a date or a charge level read the same way ("battery 10/10", "Battery level 60% in photos"), "I no longer work from home" read as a fault in the reseller's own notes, and a scratch under the screen protector dropped as the protector's. All 63 are fixed and kept as tests (`tests/test_flaw_cases.py`). A second round found the case and protector rule dropping the phone's own marks ("Comes with box and charger, has a small crack"), so a mark is now a case's or a protector's only when it's said of it, before it or on it.

**Fresh listings from Vinted (23 Sep).** The explainer ran 165 real Vinted phones, scored against an answer key, through the whole reading: 158 of 185 flaws found, 3 wrong, with code throwing away 15 flaws Gemma had found. The words behind them are now read ("battery low", "Face ID is disabled", "a new screen may be required", "soft OLED", "well used", "for spare parts", iOS 15 or lower), each with a look-alike that isn't a flaw ("battery lasts all day", "Original screen", "No charging cable"). These words came from those listings, so the next honest test needs another fresh batch.

**The AI's messages before the reseller has a style (14 Sep).** 42 messages (14 made-up listings, each kind of offer), Gemma 3 4B on this Mac: 10 passed the checks first time before these changes, 39 after, and 3 would go to Haiku (32 before). Asking about iCloud went from 4 to 0. The changes were first tried outside the app by the explainer session, then measured again in the app as built.

**Messages before the reseller has a style (12 Sep).** Giving a lower offer's reason by itself, as AlertFlip does, means every misreading of the listing ends up in the message. So four test agents wrote 651 cases to break it, and a second agent re-ran every failure: 242 confirmed. They included:
- labels with their answers ("Faults: none", "Scratches – no", "Any damage? Nope", "Scratches ❌") read as flaws;
- lists the seller denies ("no scratches, dents, or marks", "never been dropped, cracked or repaired");
- what guards against damage ("scratch resistant", "water damage indicator not triggered");
- a "no" that took a real flaw with it ("no offers small crack on back");
- a seller's "battery 80%" that was the charge, not the health;
- reasons that read badly ("because of the screen cracked", "because of the • Cracked screen");
- checks that let "transfer now" or "nice console!" through;
- removed parts of a style that came back through the reseller's old examples.

All 242 are fixed and kept as tests (`tests/test_message_cases.py`, `tests/test_style_book.py`).

**The colour from photos (2 Sep, 14 Sep).** 198 real phone photos, each with the colour taken out of its title:

| | Right | Wrong | Unsure |
|---|---|---|---|
| Gemma | 68 | 4 | 126 |
| Haiku's look at the colour alone | 113 | 3 | 82 |
| Gemma, then Haiku's look when Gemma is unsure | 131 | 5 | 61 |

A wrong answer here includes a near one (Teal for Ultramarine). Haiku's look costs about 0.0125p. Most wrong answers came from photos that showed only the box's picture or the wallpaper, not the phone's back; one "wrong" answer was right and the seller's title wrong. Telling the models a box or wallpaper isn't the item's colour made Haiku lose 32 right answers to remove one wrong one, so it isn't in the prompt.

**Typos (14 Sep).** Every claim word typed with each slip people make (3,195 typos): 26% were read before, 91% now. The rest are typos that are real words themselves, as close to an everyday word, or under 4 letters. On 3,969 real listings, one more typo is read and no real word is misread.

**Breaking the 14 Sep changes.** Five test agents wrote 664 cases against the typos, the phone names, the "how it happened" check, each kind of offer in the reseller's style, and the colour look; a second agent re-ran every failure: 40 confirmed. They included a crash on a typo in a long sentence, a real iPhone 13 mini read as the 13 ("13 mini scratches on back"), "iPhone 16 e-sim" read as the 16e, "you've dropped your asking price" refused as a made-up drop, and a greeting written twice ("Hi mate, hi mate, would you..."). All 40 are fixed and kept as tests.

## The API

What AlertFlip calls, from a Supabase function, so the key never sits inside the phone app (`flip/api.py`, FastAPI):

```bash
.venv/bin/uvicorn flip.api:app --port 8000    # then open http://127.0.0.1:8000/docs
```

| Endpoint | What it does |
|---|---|
| `GET /health` | Whether the local model is running and the keys are set, which of the models it asks for Ollama has, and who does each job: the paid backup, the reason's check and fix, who writes List on eBay's draft and who reads its notes (`listing_reader`: flip-reader-5 when Ollama has it, else gemma3:4b, else code). No key needed, none shown |
| `POST /messages/draft` | Reads the listing, then drafts the offer at code's starting price or the one picked on the app's slider (`offer`, which must fit the kind of offer). `flaws_said` (1, 2, 3 or `"all"`, with `"mention": true`) picks how many flaws a lower offer gives as its reason: the worst first, by how much each cuts the price (`flip/picking.py`); a message that gives one left out is refused. It returns the message, who wrote it, the "no offers" note, what was read, the lines the reason was worded from (`reason_from`), every attempt with its seconds and cost, and a draft id |
| `POST /messages/check-reason` | The second step for a draft made with `check_later` (the app's way): Claude Haiku 5.5 checks the reason and Claude Sonnet 5.5 fixes one it flags. The fix goes into the message only when the message with it passes the same checks as any message, and the audit log keeps the new text |
| `POST /listings/draft` | The listing's text, your notes and up to 8 photos (form fields and file uploads) in, the eBay draft out |
| `POST /prices/estimate` | A listing's UK price with its flaws cut, for iPhones, Samsung phones and MacBooks, from the AlertFlip prices API (`PRICES_URL` and `PRICES_KEY` in `.env`): the description is read for its flaws as for a draft, unless `flaws` are sent (a draft's, with `read_by`) |
| `POST /drafts/{id}/approve` | What you actually sent or listed, so the results can count how often a draft was right as it was. An approved message also joins the messages your style is learned from |
| `GET /stats` | The cost meter: drafts, the successful outputs made on this device (free) against all of them, cost per 100 drafts, how often a draft was edited before sending, and who did the work: each model's tries, passes and cost by job, flip-kinds-1's sorting and flip-style-1b's reading of your style included |
| `GET /style` | What it learned from your messages: the style card (habits in 40% or more of them), the phrasebook (sentences in 2 or more), and everything it puts in a message, each with whether you still use it |
| `POST /style/learned` | Remove one thing it learned, or put it back (`key`, `used`). A removed one is never written; the app removes for good |
| `PUT /style/setup` | Your answers from setting up your style, in place of your last setup's: what you removed is cleared, so it's learned from them afresh. Drafts you approved and a CSV stay |
| `GET`, `POST /style/messages`, `DELETE /style/messages/{id}` | The messages it learns from: list them, add one or many (`title`, `price`, `text`), or delete one. The search for the closest past messages follows at once, so the next draft already uses what you added |

- **Who can call it.** It answers only on this machine (127.0.0.1) unless it's put online on purpose. Every endpoint but `/health` and the `/docs` pages (which only describe the API) needs `FLIP_API_KEY` from `.env` in an `X-API-Key` header. A key under 32 characters, like the example file's, counts as none, and the API then refuses every call.
- **Turned away before it's read.** A request without the key, or bigger than its endpoint takes (1 MB, or 121 MB for 8 photos), is refused before any of it is read, so nobody can fill the machine's memory or disk.
- **It never sends or lists anything itself.** AlertFlip does that, after the reseller approves.
- **Bad input is refused before anything runs:** an unknown kind of offer, a price that isn't a price (or is under £1), an offer that doesn't fit its kind, a message for a listing whose title names no iPhone, Samsung phone or MacBook (FlipAssist is made and tested for those three only), a file that isn't a photo. A photo is known by its bytes (JPEG, PNG, HEIC or WebP), not its name, and one with more pixels than any camera takes is refused before it's converted.
- **A reading sent back is held to the listing.** `reading`, the listing's reading from the draft before (so another kind of offer doesn't read it again), is checked as any model's reading is: every quote (the flaws, the pickup place, the "no offers") must be the listing's words, no flaw may be one the seller denies, and a "no offers" must say it. One that fails is read again.

```bash
curl -s http://127.0.0.1:8000/messages/draft -H "X-API-Key: $FLIP_API_KEY" -H "Content-Type: application/json" \
  -d '{"listing": {"title": "iPhone 13 128GB", "asking_price": "220", "description": "Black dot on the screen"}, "mention": true}'
```

## The app

A window in AlertFlip's design (`frontend/`, React and TypeScript), light or dark, that reads the same wherever it's opened:
- **Set up your style**, on first launch (Skip for now, or Do the setup): reply to 6 listings, each showing one habit, like how you mention flaws. Nothing gets trained: it learns from your own messages. It ends with everything it learned, each with a Remove button that deletes it.
- **AI message:** for iPhones, Samsung phones and MacBooks only (the title has to name one): price cards and a slider, the message with the seller's "no offers" note, what was read, and why, step by step. Say the flaw is Yes to start with (then 1, 2 or 3 flaws only, the worst first, or all of them: pick one), or No; only an offer under asking says a flaw. Every message is written with no AI: your sentences (or AlertFlip's) write it around the reason flip-wording-4b words from what flip-reader-5 read (with your Claude key, Claude Haiku 5.5 checks the reason), in about 3 s. Only Rewrite has an AI write: Gemma 3 4B rewords the message, told to keep the price, the facts and the checked reason (shown to it as [REASON], put back word for word) and add nothing new; Claude Sonnet 5.5 (paid) rewords it when Gemma 3 4B's tries fail the checks. Without Gemma 3 4B, or with Ollama down, nothing is sent to Claude in its place: Rewrite says it couldn't run and why, and your message stays as it was. A listing is written as one you collect unless it says it's posted.
- **AI UK price estimate:** a title and description in, a UK price out, for iPhones, Samsung phones and MacBooks only. The clean middle price comes from the AlertFlip prices API's recent UK sales; flip-reader-5 finds the listing's flaws (Gemma 3 4B when it isn't installed, code when neither is; with an Anthropic key, Claude Sonnet 5.5 reads it again when a model's reading fails code's checks), flip-kinds-1 sorts each into the kind the price is cut for (lock, parts, network lock, not genuine, damage, fault, battery, wear), and code's rules sort any it can't, and the title. flip-kinds-1 counts a carrier or network named for the phone as a network lock unless the listing says it's unlocked or works on any network (the owner's buyer-safe rule; it matched a blind relabel on 158 of 161 test sentences), and code's rules follow the same rule. On 400 flaw sentences it never saw, scored to that rule, flip-kinds-1 priced 3.8% wrong and code's rules 17.5%; on two fresh tests, 3.9% and 8.2% ([MODELS.md](MODELS.md)). The screen names flip-kinds-1 when it sorted them ("and code" when code sorted some). Damage is cut by how bad it is (minor, moderate or severe, `flip/severity.py`) and how pricey the model is. Code reads how bad it is and, with an Anthropic key, Claude Haiku 5.5 reads it too, sent the title, the first 1,500 characters of the description and the reader's flaw sentences, never a price; when they disagree, Claude Sonnet 5.5 decides. Scored once against three blind checkers on 299 fresh UK listings, this judge was right on 93.3% (Sonnet decided 62 of them), and judging 764 damaged listings cost about £0.29. It asks while the prices API answers, so it's paid for even when that call fails, and the same listing priced again isn't paid for again while the API runs. Without a key, code alone judges.
- **List on eBay:** photos, notes, and the draft to check.
- **Home:** the cost meter (every successful output across the models, paid ones too; cost per 100 drafts; drafts; how many you edited before sending), who did the work (each model by its job, with how many of its answers passed and what they cost), and what's running, one line each: Ollama and each model on this device with its job (or, when it isn't installed, what does its job instead), Claude Haiku 5.5 (checks each message's reason is sendable and writes eBay listings), Claude Sonnet 5.5 (fixes a reason Claude Haiku 5.5 flags, and when this device's models can't, writes a message, reads a listing or looks at the photos for the colour, and writes an eBay listing when Claude Haiku 5.5's fails the checks), the AlertFlip prices API (fresh local sales) and the key. With the AlertFlip prices API set, Claude Haiku 5.5 also judges how bad the damage is for the UK price, and Claude Sonnet 5.5 decides when code and Claude Haiku 5.5 disagree; with no Anthropic key, both show as off. It refreshes each time you open it.
- **Your style:** the style card and the phrasebook (sentences for every offer, or for one kind of offer or marketplace), each thing yours to remove for good, and the messages it learns from, each yours to delete. Do setup, or Redo setup once you have: your new answers take the place of your last setup's.

```bash
.venv/bin/uvicorn flip.api:app --port 8000      # the API, in one terminal
cd frontend && npm install && npm run dev       # the app, in another: then open http://127.0.0.1:5173
```

The app's dev server adds the API key on the way, from `.env`, so the key never reaches the browser.

## The launcher

FlipAssist opens like any Mac app: one double-click on **FlipAssist** (in Applications, Spotlight or the Dock) and it runs in its own window, with no browser around it (`launcher/`, Electron and TypeScript).

1. A launch screen shows the models on this device (Ollama) and FlipAssist's API starting. Whatever is already running is used as it is; whatever isn't is started: Ollama for the models on this device, and the API from the repo's own Python. Ollama starts with its prompt cache off: it kept up to 8 GB of older prompts in memory to save a few seconds on going back to an older listing. The last prompt is still kept, so drafting the same listing again stays quick.
2. The models every draft uses are loaded into memory straight away, so the first draft doesn't wait for them: flip-wording-4b (words the offer's reason), then flip-reader-5 (reads the listing), each with the working memory the API asks it with (`launcher/src/parts.ts`, `modelsToWarm`). flip-reader-5 goes last because, when only one fits in memory, Ollama keeps the newest, and every draft reads first. Gemma 3 4B is loaded in flip-reader-5's place when flip-reader-5 isn't downloaded or `FLIP_READER_MODEL=` turns it off; otherwise it loads when it's first asked (Rewrite, or List on eBay when there's no Claude key or `FLIP_LISTING_WRITER=gemma`), since three models don't stay loaded together on a 16 GB Mac. The launch screen names the models FlipAssist uses that Ollama has (flip-reader-5, flip-wording-4b, flip-kinds-1, flip-style-1b and Gemma 3 4B; one switched off in `.env` isn't named), and says when one of FlipAssist's own isn't installed and what does its job instead (Gemma 3 4B reads, or code when Gemma 3 4B isn't there either; code words the reason; code's rules sort the flaws; code reads your style alone). Without Gemma 3 4B it says Rewrite can't run (nor, with no Claude key or with `FLIP_LISTING_WRITER=gemma`, List on eBay's condition note and description). Without Ollama, or when it doesn't start (its own words are in its log), it says code does the models' work, the same can't run, and with your Claude key Claude Haiku 5.5 still writes List on eBay and, with the AlertFlip prices API set, judges how bad a UK price's damage is. A fault while starting shows on the launch screen instead of leaving it waiting.
3. The app is the built front end, at `app://flipassist/`. Its calls to `/api/...` are passed on to the API by the launcher, which adds the key from `.env` on the way. The page never sees the key, and no other program on the Mac can borrow it, as it could from a local web server.
4. Quitting stops only what the launcher started. What each part printed is in `~/Library/Logs/FlipAssist`.

The API runs in the repo's own Python, which `launcher/build.sh` doesn't set up: do that once first, as in [Run it](#run-it). Without it, the launch screen says the API's Python environment isn't set up, and gives the command for it.

```bash
python3.11 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt    # once: the API's Python
launcher/build.sh     # builds the app and the launcher, draws the icon, puts FlipAssist.app in ~/Applications
cd launcher && npm test && npm run selftest    # the launcher's own tests, then the real window checked end to end
```

The self-test opens the window, checks every kind of call (files, JSON, photo uploads, refused paths, copying, saved settings) without drafting or saving anything, and quits.

### FlipAssist's own models

On a Mac, `launcher/get-models.sh` downloads the four model files from the repo's GitHub release `models-v1`, checks
each one against the version that was tested, and adds it to Ollama (about 10 GB in all; it needs about 13 GB free
while it runs). A model Ollama already has as that version is skipped, and a download that stops part-way is kept in
`~/Library/Caches/FlipAssist-models`, so running it again carries on from there. If the release, or a file on it,
can't be downloaded, it stops and says which, and the models it added before that stay. In a folder downloaded as a
ZIP, or a fork's clone (GitHub doesn't copy releases), name the repo:
`launcher/get-models.sh mohadilyes-git/FlipAssist-AI`. Without the models, Gemma 3 4B and code do their jobs
(models/README.md).

To make the release, on a Mac with the four models in Ollama, once the code is pushed (a repo with no commits can't
have a release): `launcher/upload-models.sh mohadilyes-git/FlipAssist-AI`. It needs GitHub's gh tool, logged in
(`brew install gh`, then `gh auth login`), makes the release `models-v1` with models/README.md as its notes, and
uploads one model at a time, so it needs room for only one model's parts (about 2.5 GB). Or
`launcher/package-models.sh <an empty folder with about 11 GB free>` makes the same files, to upload to a release
tagged `models-v1` by hand. Both refuse a model in Ollama, or its Modelfile, that isn't the version that was tested.

### Your own keys

Nobody's keys are in the repo: `.env` is never uploaded (`.gitignore`). On first launch the app makes `.env` with this
computer's own `FLIP_API_KEY`. Claude runs on your own key: put it after `ANTHROPIC_API_KEY=` in `.env`
(console.anthropic.com), and Anthropic bills you for what you use. Without it, everything runs on this computer. The
UK price estimate asks AlertFlip's prices service (`PRICES_URL`, `PRICES_KEY`), which isn't public; without it, the
price tab says so.

### On Windows (9 Nov 2026: built and tested on a Mac, not yet run on a Windows PC)

The same app runs on Windows: the same splash screen, icon and screens, the same API and models. What differs is only
where things live, all in `launcher/src/parts.ts` and tested on the Mac for both:

- **The window** has Windows' own title bar (minimise, maximise, close), so the app draws no traffic lights; the menu
  bar stays out of sight until Alt is pressed.
- **Ollama** is looked for in the user's Programs folder (or Program Files), and **the API** starts from
  `.venv\Scripts\python.exe -m uvicorn`, in UTF-8 mode. Quitting ends each one's whole process tree (taskkill), so
  Ollama's model runners don't stay behind.
- **Logs** go to `%LOCALAPPDATA%\FlipAssist\logs`.
- **Photos** are converted by Pillow, and HEIC by pillow-heif (`flip/photos.py`), where a Mac uses its built-in sips.
  `requirements.txt` installs both on Windows only. Every text file is read and written as UTF-8 (`tests/test_utf8.py`).

To set it up:

1. On the PC, install Python 3.11 (tick "Add python.exe to PATH"), Node.js 22 or newer, Git for Windows
   (git-scm.com), Ollama, and the Microsoft Visual C++ Redistributable (x64) if the PC doesn't have it
   (aka.ms/vs/17/release/vc_redist.x64.exe), and open Ollama once.
2. Clone the repo on the PC (git clone), somewhere OneDrive doesn't sync (C:\FlipAssist, say), and put your `.env` in
   it if you have one (it holds your keys). From a ZIP download or a fork's clone instead, add
   `-Repo mohadilyes-git/FlipAssist-AI` to the command in step 3, so it finds the models' release.
3. On the PC, in PowerShell in the repo folder:
   `powershell -ExecutionPolicy Bypass -File launcher\windows-setup.ps1`.
   It sets up the Python environment, downloads Gemma 3 4B through Ollama (about 3.4 GB) and FlipAssist's four models
   from the repo's GitHub release (about 10 GB, each checked against the version that was tested, models/README.md),
   and builds FlipAssist into your Programs folder, with a Start menu and a desktop shortcut. After a change,
   `powershell -ExecutionPolicy Bypass -File launcher\build.ps1` builds it again. To save the 10 GB of FlipAssist's
   models, copy them on a Mac to an ExFAT USB drive (`launcher/export-models.sh /Volumes/USB/FlipAssist-models`) and add
   `-Models D:\FlipAssist-models`: Gemma 3 4B and the Python and Node libraries still download.

Step 3 needs about 13 GB free on C: while it adds all four models. If it stops, run it again: a model Ollama already
has as the tested version is skipped, and within a run a dropped download carries on where it stopped (up to 5 tries,
10 s apart), though a model left half downloaded when a run stopped starts again. If the release, or a file on it,
can't be downloaded, it stops before building FlipAssist and says what it couldn't get; `-NoModels` builds it without
them (Gemma 3 4B and code do their jobs). Behind a proxy, set `HTTPS_PROXY`: the model files come with curl.exe,
which doesn't read Windows' proxy settings.

How fast it drafts depends on the PC: a Mac runs the models on its own graphics, and a PC does that with a recent
graphics card. Without one they run on the processor, and a draft takes longer.

## Planned

- **The AlertFlip side:** a Supabase function that calls the API from the phone app.
- **Measured results on the test set:**
  - fields right for local, API and the switch;
  - cost per 100 listings;
  - minutes per listing by hand vs with the assistant.

## Who does what

| Field | Filled by |
|---|---|
| Model, storage, specs, title | Code, from `data/catalogue.json` |
| Battery health | Code, from the reseller's notes (`flip/numbers.py`) |
| Colour | Code if the text names it; otherwise the listing's writer from the photos (Claude Haiku 5.5 in the app; Gemma 3 4B with no Anthropic key or `FLIP_LISTING_WRITER=gemma`), and, with a key, Claude Sonnet 5.5's look when the writer is unsure or saw the colour only on the screen or a case |
| eBay's category and fields (Brand, Model, Storage Capacity, Colour...) | Code, in eBay's words (`data/ebay_fields.json`, `data/ebay_map.json`); phones so far |
| Condition | Code, from the reseller's notes |
| Condition note, description | The AI, then checked by code |
| Offer price, profit | Code |
| The listing's flaws, pickup place, "no offers" | The AI, held word for word to the listing by code |
| What to say about the condition | Code picks it from that reading; the reseller picks whether it's said (left to code, a lower offer gives it, and over asking their style decides) |
| The offer message's wording | Code: AlertFlip's sentences before the reseller has past messages, then their own; the AI only when their messages vary, or code can't word the flaw (in the app, only for Rewrite) |
| The offer's reason | flip-wording-4b, from the reader's flaw sentences (code when it isn't installed); with an Anthropic key, Claude Haiku 5.5 checks it and Claude Sonnet 5.5 fixes one it flags |

## Run it

Needs Python 3.11 or newer.

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/pytest
```

For the AI drafter, install [Ollama](https://ollama.com) and the local model (about 3.4 GB), and add an Anthropic API key for the fallback:

```bash
brew install ollama
ollama serve              # leave this running in its own terminal
ollama pull gemma3:4b
cp .env.example .env      # then put both keys in .env (never uploaded): yours from Anthropic, and a random FLIP_API_KEY
.venv/bin/python -m flip.draft testset/items.example.json --mode local
```

`--mode local` uses only the local model, `--mode api` only the paid backup (Claude Sonnet 5.5, or the model `FLIP_BACKUP_MODEL` names), and the default `auto` tries the local model first.

For messages, set up your style in the app, or put your past messages in `testset/private/messages.csv` (`testset/messages.example.csv` shows the columns) and learn them; either way they're kept in `private/style.sqlite3`, which never leaves this machine:

```bash
.venv/bin/python -m flip.message --learn
.venv/bin/python -m flip.message "iPhone 13 128GB Midnight" --asking 220 --marketplace facebook
.venv/bin/python -m flip.message "iPhone 13 128GB" --asking 220 --description "Broken back" --offer asking --mention yes
```

`--offer` picks `lower` (the default), `asking` or `more`. `--longer` makes it about twice the usual length; `--previous "..."` makes that draft longer instead. `--mention yes` or `no` answers the question about the listing's flaw or good condition; without it, a lower offer gives the flaw as its reason, over asking the reseller's style decides whether good condition goes in, and otherwise the draft asks. `--writer template` or `ai` overrides who writes; the default lets the reseller's past messages decide.

## The test set

Real items stay in `testset/private/`, which git never uploads: it holds other sellers' listing text and photos. The easiest way to fill it is a spreadsheet:

```bash
mkdir -p testset/private/photos
cp testset/items.example.csv testset/private/items.csv
```

1. Open `testset/private/items.csv` in Numbers or Excel and fill one row per item:
   - the original title and description;
   - your notes;
   - the photo file names (put the photos in `testset/private/photos/`; separate names with `;`);
   - the prices;
   - the right answer for every field. Write a model the catalogue doesn't cover as `not in catalogue`.
2. Save it as CSV and run `.venv/bin/python -m flip.testset`. It writes `items.json`, or tells you the row with a typo.
3. Run `.venv/bin/python -m flip.score` to see how often code alone gets each field right, and `.venv/bin/python -m flip.draft` to draft them all.

Include a few items the catalogue doesn't have: the right answer for those is "needs you".

## Folders

- `flip/`: the code (`flip/api.py` is the API)
- `frontend/`: the app (`npm test` runs its tests)
- `launcher/`: FlipAssist as a Mac or Windows app (`build.sh` builds it on a Mac, `build.ps1` on Windows), and the scripts that get, upload, pack and export FlipAssist's models
- `models/`: what goes with FlipAssist's models on their release: its notes, the Gemma notice and terms (the models themselves are on the release)
- `evals/`: the hard style test (`evals/style/`), which you can run yourself
- `data/`: the catalogue, eBay's item conditions and the questions a message may ask (facts, not code)
- `tests/`: a test for every rule
- `testset/`: the example format for the test set
- `private/`: the audit log and anything else the app saves while it runs (never uploaded)
