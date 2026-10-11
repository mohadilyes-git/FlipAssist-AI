# FlipAssist's own models

FlipAssist reads second-hand listings, words the reason in an offer, sorts flaws for its UK price check and learns a
buyer's style with four models of its own, each fine-tuned from Google's Gemma 3 4B (the public `unsloth/gemma-3-4b-it`
weights). Each is a LoRA add-on (QLoRA), merged and quantised to Q4_K_M (2.5 GB) so it runs in Ollama on a Mac, with no
paid AI and nothing sent anywhere. A "b" in a name (flip-wording-4b, flip-style-1b) marks the second run of that round,
not a model size: every model here is Gemma 3 4B.

This page says what each model does, how it was trained, how it was tested and how to check a model file is the one
tested. The weights and the training data aren't in this repo: see [Why the weights aren't public](#why-the-weights-arent-public).

## In use (since 6 Oct 2026)

| Model | Its job | Trained on (train / validation) | Tested result |
|---|---|---|---|
| **flip-reader-5** | Reads a listing: each flaw as the seller's own sentence, where to collect, and whether the seller takes offers | 33,160 / 595 listings: phones and MacBooks from the UK, the US and Canada, plus 3,098 made-up practice listings for 32 kinds of tricky line | Tested against round 4: a tie |
| **flip-wording-4b** | Turns the reader's flaw sentences into the offer's reason ("there's a hairline crack on the top left of the screen"), keeping every fact and adding none, under four rules added on 6 Oct: "for parts only" kept but "can be used for parts" left out, a missing charger or box isn't a flaw, nor a mark on a screen protector, and a custom phone system (LineageOS, a custom ROM) is | 14,513 / 602 | Judged blind side by side with flip-wording-3 under the same rules: on 740 real listings **90.3% sendable vs 88.0%** (better on 34, worse on 17, p = 0.024), a made-up fact 3.4% vs 5.0%; on 80 made-up listings written for the four rules, 92.5% vs 63.8%. A Claude Haiku check and a Sonnet fix still follow it in the app |
| **flip-kinds-1** | Sorts each of the seller's flaw sentences into the kinds the price is cut for: lock, parts, network lock, not genuine, damage, fault, battery or wear ("small crack on the back, battery 79%" is damage and battery; "battery health 88%" is none) | 4,600 / 400 flaw sentences from the readers' training listings, each labelled by two labellers who couldn't see each other's answers, and a third where they differed | The sealed test: 400 flaw sentences it never saw (about 350 from real listings, about 50 from the reader's practice listings), labelled blind by three. Under the carrier rule (below; the test's carrier, network, SIM and lock sentences labelled again blind): the price cut off by 3 points or more on **3.8%**, 94.8% exactly right, against 17.5% for the app's own rules (25.0% before they followed the rule too). Under the first key, before that rule: 5.2% and 93.2%, against 23.5% for the app's own rules, 25.8% for the prices API's sorter (38.0% for its earlier one) and 65.8% for plain Gemma 3 4B; on the real sentences alone 5.8% against 23.4%, 25.7% and 64.2%. The first two labellers gave the same answer on 94.5% |
| **flip-style-1b** | Reads a buyer's past offer messages and names the habits they repeat: greeting, how they make the offer, what they add after it, how they say they like the item, sign-off, words they always write short | 2,833 / 245 made-up buyers (no real person's messages): 1,078 written by Claude agents from code-written plans and checked by a blind judge and by code, 2,000 built by code from Claude-written phrases | The hard style test ([`evals/style/`](evals/style/), 40 made-up buyers it never saw): **182 of 189 habits found, 6 wrong, 3 invented**, against plain Gemma 3 4B's 146 found, 37 wrong, 230 invented, and the app's code alone 105 found. The app takes only its sign-off, once code has checked it: 113 habits with it, 110 with plain Gemma |

flip-wording-4b's numbers come from judges who applied the four new rules, which flip-wording-3 wasn't trained for: under them flip-wording-3 is sendable on 87.1% of the 240 held-out listings, against 92.5% on 3 Oct. Compare the two models by their side-by-side numbers, not across the tables.

**Checked on the Mac (6 Oct 2026, a MacBook Air M4 with 16 GB).** Each model gave the same answers as in its cloud
test: flip-kinds-1 on 40 of 40 validation sentences, flip-wording-4b on 30 of 30 held-out listings, flip-style-1b on 7 of 8
validation buyers (on the eighth it left out one extra phrase). Once loaded, each takes about 1.5 s a flaw sentence
(flip-kinds-1), 1.2-1.8 s a reason (flip-wording-4b) and 4-8 s a buyer's messages (flip-style-1b); the first answer,
while the model loads, takes 3-8 s.

**A fresh test on the Mac**, on data none of them had seen, scored the same ways as the cloud tests: 245 real listings
(55 first seen by AlertFlip on 11-6 Oct, 190 from the reader's own test sets; none shares text with flip-reader-5's
training data or with any of flip-kinds-1's or flip-wording-4b's data), read by flip-reader-5, and 40 new made-up buyers
written free-form, with no code-written plan:

| Model | Fresh test | Against |
|---|---|---|
| flip-kinds-1 | 181 flaw sentences from the 128 listings with a flaw, first blind key: **91.7% exactly right, price cut wrong on 6.6%**; under the carrier rule (below): **3.9%**, 94.5% exactly right | the app's own rules: 74.6% and 23.8% (p < 0.0001); under the carrier rule 18.2% (26.0% before they followed it) |
| flip-wording-4b | the 128 listings, blind judges: **94.5% sendable**, a made-up fact 3.1%, a fact lost 2.3% | flip-wording-3: 91.4%, 3.9%, 3.1% (better on 6, worse on 2: not a proven difference) |
| flip-style-1b | the 40 new buyers: **131 of 136 habits found, 0 wrong, 5 invented** | plain Gemma 3 4B: 108 found, 16 wrong, 276 invented |

Under the first key, 5 of flip-kinds-1's 12 misses there were a carrier named without saying it's locked: 4 on US
listings ("Network AT&T", "Works with Verizon") and 1 UK ("Unsure if locked or not, we are with EE"). The carrier rule
below counts all 5 as right (7 misses). The labels disagreed, not the model: flip-kinds-1's training and validation
labels called a carrier named like that a network lock 79% of the time (244 of 308), that test's labellers on 4 of 7.

**The carrier rule (set by the owner on 6 Oct evening).** A carrier or network named for the phone ("Carrier: AT&T",
"Galaxy S21 EE", "for Straight Talk", "works on Verizon") counts as a network lock unless the listing says it's
unlocked or works on any network. It's buyer-safe on purpose: a locked phone you overpaid for costs more than an offer
5-10% lower (10% when the carrier line is the listing's only flaw). Every test sentence that mentions a carrier, a
network, a SIM or a lock (161 across the sealed test and both fresh tests) was labelled again on that one question,
blind, by two labellers (who agreed on 160) and a third on the split; the scores here use those keys, and the rule only
ever added a network lock (to 6 sealed sentences, 5 in the first fresh test, 18 in the second). flip-kinds-1 already
answers this way: on network lock it agreed with those labels on 158 of the 161 (93 of the 94 locks). The app's own
rules, which sort the title and any sentence the model can't answer, follow it too since 6 Oct evening (`network_lock`
in [`flip/prices.py`](flip/prices.py)): before, they counted a lock only when the listing said so ("locked to EE", "EE
only") and found 23 of the 94. Two independent reviews tried 353 ways sellers write a carrier, an unlock or a word that
only looks like one ("Cosmic Orange Mobile Phone", "on three spots", "playing cricket", "unlocked from my iCloud", "I
think it's unlocked"); the first one's 193 and every one that failed are tests now
([`tests/carrier_cases.py`](tests/carrier_cases.py), [`tests/test_carrier_rule.py`](tests/test_carrier_rule.py)). On titles from 673 more listings from the reader's test
sets no one had read, labelled blind, every lock it found was right (119 of 119); it missed 6 that blind labellers
called locked, now read too, so that's no longer an unseen test. A code rule doing the opposite (a network lock only when the sentence says "locked", "only" or "tied to") was tried and
dropped, as it contradicts the rule. Under the earlier keys its record was mixed: on the second fresh test it took
flip-kinds-1 from 43 to 26 of 305 priced wrong (that key's brief said a named carrier isn't a lock), on the sealed test
from 21 to 34 of 400.

**A second fresh test (6 Oct evening)** on 600 more real listings from the reader's test sets (UK, US and Canada;
none in the first fresh test; no listing shares text with the training, validation or test files of flip-reader-5,
flip-kinds-1 or flip-wording-4b, or with flip-kinds-2's training data, though a few short stock sentences such as
"Battery health 85%" also occur in flip-kinds-1's training rows), read by flip-reader-5 on the Mac: 239 with a flaw,
holding 305 flaw sentences. Labelled and judged blind as above: the two sorter labellers gave the same answer on 97.0%,
and the reason judges agreed on 309 of the 323 different reasons the four set-ups wrote, with three fresh judges
deciding the other 14. The plan was written before any of these answers existed; the exact rule for switching to
flip-kinds-2 was added after flip-kinds-1's and the reason test's answers existed but before flip-kinds-2's; the
carrier rule, and the relabel of 63 of the 305 sentences (18 gained a network lock), came after all of them.

| Flaw sorter, scored to the carrier rule | Price cut wrong (305 sentences) | iPhone (146) | Samsung (70) | MacBook (82) | Sealed 400 |
|---|---|---|---|---|---|
| the app's own rules (following the rule) | 20.0% | 14.4% | 25.7% | 23.2% | 17.5% |
| the app's own rules, before | 26.9% | 19.9% | 44.3% | 23.2% | 25.0% |
| **flip-kinds-1 (in use)** | **8.2%** | 3.4% | 10.0% | 12.2% | **3.8%** |
| flip-kinds-2 (not used) | 8.5% | 5.5% | 8.6% | 11.0% | 4.2% |

The other 7 of the 305 come from listings whose title names none of the three; each sorter priced 3 of them wrong.
Under the first key (before the carrier rule) the second fresh test gave flip-kinds-1 14.1%, flip-kinds-2 13.8% and
the app's own rules 21.0%.

- **flip-kinds-2, a second training round**: flip-kinds-1's data plus 1,366 sentences labelled blind the same way,
  1,136 for training and 230 for validation (5,736 / 630). 363 of the training ones are kinds flip-kinds-1 got wrong
  under the labelling brief of the time (a passcode the seller knows, working only on charge, locked and for parts, a
  warning that names no flaw, a hinge, a payment plan, and a carrier named, which that brief said isn't a lock: the
  opposite of the owner's rule above); 273 are from Samsung and MacBook listings (Google and FRP locks, Knox, burn-in,
  screen lines; MDM, firmware passwords, keyboard and trackpad faults, a battery's "Service Recommended"); 500 are at
  random. Picked over a 3-pass run on validation (59 vs 60 of 630 priced wrong; flip-kinds-1: 57). Its rule, written
  before its fresh answers: it goes in only if it prices fewer sentences wrong than flip-kinds-1 and is no worse on
  iPhone, Samsung or MacBook. Scored to the carrier rule it priced 26 wrong against 25 (4 fixed, 5 broken), better on
  Samsung and MacBook but worse on iPhones; under the first key, with the dropped code rule on both as the rule was
  written, 26 each and worse on iPhones too. So flip-kinds-1 stays. On the sealed test: 4.2% against 3.8%; 13 of those
  400 sentences come from listings whose other sentences it trained on, and on the other 387 it's 4.4% against 3.9%.

| Offer reason | Sendable (239 listings) | A made-up fact | Paid calls per 1,000 listings with a flaw |
|---|---|---|---|
| flip-wording-4b alone | 90.8% | 2.9% | none |
| flip-wording-3 alone | 90.8% | 5.0% | none |
| flip-wording-4b, every reason checked by Claude Haiku and a flagged one fixed by Sonnet (the app with the paid check on) | 93.7% | 1.3% | 1,000 Haiku + 243 Sonnet: £0.43 |
| flip-wording-4b, Haiku checking only the 28% where flip-wording-3 wrote a different reason | 93.7% | 1.7% | 276 Haiku + 96 Sonnet: £0.19 |

- **flip-wording-4b vs flip-wording-3**: a tie here (each better on 11 listings), so the plan's proof (this test alone,
  p < 0.05) isn't met. The two fresh tests together give 17 better and 13 worse (p = 0.58); with the cloud test's 740
  (34 vs 17) it's 51 and 30 (p = 0.026), carried mostly by the cloud test. Two of its 11 wins here come from the
  6 Oct rules ("can be used for parts", "no charger"), the rest from flip-wording-3's one-off slips; its 11 losses are
  one-off slips too: 4 details dropped, 3 facts changed (one says "it can't charge" where the seller says it still
  charges), 1 garbled phrase and 3 awkward wordings. Fewer made-up facts (7 listings vs 12) isn't a proven difference
  on its own.
- **The paid check**: better than flip-wording-4b alone on 10 listings and worse on 3 (p = 0.09); checking only where
  the two models differ, better on 9 and worse on 2 (p = 0.07). Neither is proven on these 239 alone. Checking only
  the least-trusted reasons costs less than half as much, but flip-wording-3 then has to word every reason too (2.5 GB
  more memory, about 1.5 s more each) to save about 24p per 1,000 listings with a flaw, so the app still checks every
  reason when the paid check is on.

Plain Gemma 3 4B (Google's, not fine-tuned) still writes the message when the AI writes, and reads a listing when FlipAssist's reader isn't installed.

Earlier versions, and flip-kinds-2 (trained after flip-kinds-1, not used), kept to compare against:

| Model | Trained on | Tested result |
|---|---|---|
| flip-reader (round 1, 24 Sep) | 1,582 / 487 | its sealed test, 1,000 phones: 875 of 979 flaw sentences found (89.4%) vs plain Gemma 3 4B's 858 (87.6%), not a proven difference; 62 vs 79 wrong flags |
| flip-reader-3 (25 Sep) | 12,304 / 400 | 2,997 listings it never saw: 92.7% of flaws found, 95.7% precision; on Samsung and MacBook 89.6% vs plain Gemma's 71.1% |
| flip-reader-4 (25 Sep) | 30,031 / 593 | 5,819 listings in 3 countries, one hand-checked answer key: **96.4% of flaws found vs round 3's 94.8%** (p = 9e-5), false alarms 29 vs 130, precision 99.0% vs 95.6% |
| flip-wording (round 1, 1 Oct) | 8,346 / 500 | 240 held-out: 87.9% sendable (Claude Haiku 75.4%, code alone 38.8%), 4.2% with a made-up fact |
| flip-wording-2 (1 Oct) | 10,237 / 499 | 240 held-out: 90.4% sendable, 1.7% with a made-up fact |
| flip-wording-3 (3 Oct) | 12,428 / 498 | 240 held-out listings, blind judges: 92.5% sendable, 2.1% with a made-up fact, 1.5 s each; with a Claude Haiku check and a Sonnet fix after it, about 95%. In use until 6 Oct, and still installed to go back to (`FLIP_WORDING_MODEL=flip-wording-3` in `.env`) |
| flip-kinds-2 (6 Oct, not used) | 5,736 / 630 | Scored to the carrier rule: the second fresh test, 8.5% priced wrong (flip-kinds-1 8.2%); the sealed test's 387 sentences from listings it never trained on, 4.4% (3.9%), and all 400, 13 of them from listings in its training data, 4.2% (3.8%). Same answers on the Mac as in the cloud on 80 of 80 validation sentences |

On 6 Oct the earlier versions were taken out of the Mac's Ollama to make room for the new ones; flip-wording-3 stays as
the way back, and flip-kinds-2 is installed beside flip-kinds-1 but not used. Their fingerprints below stay as the
record of exactly what was tested.

## How they were trained

Unsloth's QLoRA recipe on one cloud GPU (Colab, Kaggle or Modal: a T4 for round 1, then L4, A10 and A100 cards),
written down in a run record for every model:

| Setting | flip-reader-4 and -5 | flip-wording-3 | flip-wording-4b | flip-kinds-1 | flip-style-1b |
|---|---|---|---|---|---|
| Base | Gemma 3 4B, loaded in 4 bits | the same | the same | the same | the same |
| LoRA rank / alpha | 16 / 16 | 16 / 16 | 32 / 32 | 16 / 16 | 16 / 16 |
| Learning rate, warm-up, weight decay | 1e-4, 5%, 0.01 | the same | the same | the same | the same |
| Batch | 2 × 2 (gradient accumulation) | 4 | 4 | 4 | 2 × 2 |
| Passes over the data | 1 | 2 (the best of the two-pass run, at step 4,000 of 6,214) | 2 (best at step 6,500 of 7,258) | 2 (best at step 2,000 of 2,300) | 3 (best at step 2,000 of 2,127) |
| Length limit (tokens) | 1,024 | the same | the same | 1,536 | 3,072 |
| What it learns from | the answer and its end-of-turn token only, in the exact prompt layout Ollama sends | the same | the same | the same | the same |
| Kept | the checkpoint with the lowest validation loss | the same | the same | the same | the same |
| Picked over | – | a 3-pass run (flip-wording-3b) | a rank-16 run (flip-wording-4): 559 vs 558 clean validation answers of 602 | a 3-pass run (flip-kinds-1b): 21 vs 22 of 400 validation sentences priced wrong | a 2-pass run (flip-style-1): habits found minus wrong and invented on the 245 validation buyers, 914 vs 903 |

Each pick was made on validation data by a rule written before either version answered anything, never on a test set.

Library versions: unsloth 2026.11, transformers 4.57.6, trl 0.22.2, peft 0.21.2.

## How they were tested

- **On listings the model never trained on.** Every test set was checked for repeats and near-copies of training
  listings, by id and by text, before training, and set aside before anyone read the results. One exception, found
  after training: flip-kinds-2's new training sentences came from the same listings as 13 of the sealed test's 400, so
  its sealed score is also given on the other 387.
- **Keys follow the owner's rules.** When the owner set a rule after a key was made (the carrier rule, 6 Oct), every
  test sentence it could touch was labelled again blind and the scores were given both ways.
- **Against an answer key checked twice.** Claude agents labelled each listing under written rules. For the readers, a
  second labeller who couldn't see the first one's answers labelled samples again: they agreed with kappa 0.95. For
  the wording, every label was checked by a second agent and by code.
- **Wording judged blind.** Each reason was judged by two Claude judges who didn't know which model, or code, wrote it,
  with a third on the ones they split.
- **A difference is called real only when it's significant** (McNemar's test on the same listings). Otherwise the
  result says "a tie" or "not proven".
- The test plans and the rule for picking a model were written before the runs, so a result can't be picked after
  the fact.

## Why the weights aren't public

The readers, the wording models and the flaw sorters learned from real sellers' listings. A model can repeat pieces of what it learned
from, and those listings are other people's words, so neither the weights nor the data are published. To check them,
ask for access: a reviewer gets the files of the models in use privately, and can match them to this page with the
fingerprints below.

**flip-style-1b** (it learns a buyer's habits: greeting, offer, sign-off) is the exception: it was trained only on
made-up buyers, so it can be published with its data and its test.

## How to check a model file

Each file's SHA-256 is its fingerprint: `shasum -a 256 flip-wording-4b.Q4_K_M.gguf` must print the value below. In
Ollama, `ollama show flip-wording-4b --modelfile` shows the same value in its `FROM .../sha256-...` line.

| Model | SHA-256 of the model file |
|---|---|
| flip-kinds-1 | `29d5df4e97c69c85892feed8c8a7f9a52f3d1f1c05fe7b07f6102a9d2dee45d0` |
| flip-kinds-2 (not used) | `64f31fd1280b99ab26c5f68c9351fb7b23ba489a446c83ee6d4e1be9d49a2865` |
| flip-wording-4b | `f8ad98ddf4849746e3520afb9d1d38689fc3437dc66fbd201ef536f2b18d35e1` |
| flip-style-1b | `2e64f58682c449660927e25afaa4d7c029c298a19b9527bd2c22c305e316d694` |
| flip-reader-5 | `b946131ba11fc159fdc1cf683dab0d3b9c4a64cb80dd9726b1b4208b8632bae1` |
| flip-reader-4 | `84310ee6f48610530cc46b3e4d7050e6ced2ac200b4a438293f11a5884df24fe` |
| flip-reader-3 | `f95f81eb6d6259f083a1f46ed8a04381cdfedcced9ed2734d554938f6711ae0c` |
| flip-reader | `4f21a671f02f4478fe7c929ee15d9f34881d1cfde3345d27c58f0f59c75fbb6c` |
| flip-wording-3 | `02dadcdeeb2d09b0baea7847913959f2cd697a8a6e4095adc65035188a81e5e0` |
| flip-wording-2 | `5514021db78cfdc84f4db6b9e5c3ebc26bf425667e49244f5bc4ddf018609b2b` |
| flip-wording | `5a37e4100bf2b4d238ed5c5a48f763bf95933bc7d9210aa12df5de67e731f7f7` |
| gemma3:4b (Google's, not fine-tuned) | `f06e91e18fc74295d0c781bf91622508c75655e2c18ed869d52447ffe1e667e1` |

## A test you can run yourself

[`evals/style/`](evals/style/) is the hard style test: 40 made-up buyers with messy habits (typos, capitals, emojis,
shortcuts, one-off phrases that look like habits) and an answer key checked by a blind judge and by code. Run it on
this repo's code, and on Gemma 3 4B in Ollama if you have it, to get the same table we did.
