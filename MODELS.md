# FlipAssist's own models

FlipAssist reads second-hand listings, words the reason in an offer, sorts flaws for its UK price check and learns a
buyer's style with four models of its own, each fine-tuned from Google's Gemma 3 4B (the public `unsloth/gemma-3-4b-it`
weights). Each is a LoRA add-on (QLoRA), merged and quantised to Q4_K_M (2.5 GB) so it runs in Ollama on a Mac, with no
paid AI and nothing sent anywhere. A "b" in a name (flip-wording-4b, flip-style-1b) marks the second run of that round,
not a model size: every model here is Gemma 3 4B.

This page says what each model does, how it was trained, how it was tested and how to check a model file is the one
tested. The four model files in use are on the repo's GitHub release `models-v1`, not in git, and the training data
isn't published: see [Getting the weights](#getting-the-weights).

## In use (flip-reader-5 since 26 Sep 2026, the other three since 6 Oct)

| Model | Its job | Trained on (train / validation) | Tested result |
|---|---|---|---|
| **flip-reader-5** | Reads a listing: each flaw as the seller's own sentence, where to collect, and whether the seller takes offers | 33,160 / 595 listings: real phones and MacBooks from the UK, the US and Canada (and 85 from Australia), 400 copies of them with typos to practise on, and 3,098 made-up practice listings for 32 kinds of tricky line | Tested against round 4 on 5,032 listings neither had seen: a tie, each found 95.3% of the 3,162 flaws in the double-checked key, with 18 false alarms each (99.4% precision) |
| **flip-wording-4b** | Turns the reader's flaw sentences into the offer's reason ("there's a hairline crack on the top left of the screen"), keeping every fact and adding none, under four rules added on 6 Oct: "for parts only" kept but "can be used for parts" left out, a missing charger or box isn't a flaw, nor a mark on a screen protector, and a custom phone system (LineageOS, a custom ROM) is | 14,513 / 602 | Judged blind side by side with flip-wording-3 under the same rules: on 740 real listings **90.3% sendable vs 88.0%** (better on 34, worse on 17, p = 0.024), a made-up fact 3.4% vs 5.0%; on 80 made-up listings written for the four rules, 92.5% vs 63.8%. On fresh listings it isn't proven better: 94.5% vs 91.4% on the first fresh test (better on 6, worse on 2), and a tie on the second, the test planned as the proof (90.8% each, better on 11, worse on 11; both fresh tests together better on 17, worse on 13, p = 0.58). With your own Claude key in `.env` (and not in local mode), a Claude Haiku check and a Sonnet fix follow it in the app; without one, its reason goes out as it wrote it (below) |
| **flip-kinds-1** | Sorts each of the seller's flaw sentences into the kinds the price is cut for: lock, parts, network lock, not genuine, damage, fault, battery or wear ("small crack on the back, battery 79%" is damage and battery; "battery health 88%" is none) | 4,600 / 400 flaw sentences from the readers' training listings, each labelled by two labellers who couldn't see each other's answers, and a third where they differed | The sealed test: 400 flaw sentences it never saw (about 350 from real listings, about 50 from the reader's practice listings), labelled blind by three. Under the carrier rule (below; the test's carrier, network, SIM and lock sentences labelled again blind): the price cut off by 3 points or more on **3.8%** (by the prices API's UK cuts, the app's on 6 Oct: every sorter score here is worked out that way), 94.8% exactly right, against 17.5% for the app's own rules (25.0% before they followed the rule too). Under the first key, before that rule: 5.2% and 93.2%, against 23.5% for the app's own rules, 25.8% for the prices API's sorter (38.0% for its earlier one) and 65.8% for plain Gemma 3 4B; on the real sentences alone 5.8% against 23.4%, 25.7% and 64.2%. The app's rules' scores flatter them: two of their fixes came from reading this test's misses, and their carrier code from reading its carrier sentences. The first two labellers gave the same answer on 94.5% |
| **flip-style-1b** | Reads a buyer's past offer messages and names the habits they repeat: greeting, how they make the offer, what they add after it, how they say they like the item, sign-off, words they always write short | 2,833 / 245 made-up buyers (no real person's messages): 1,078 written by Claude agents from code-written plans and checked by a blind judge and by code, 2,000 built by code from Claude-written phrases | The hard style test ([`evals/style/`](evals/style/), 40 made-up buyers it never saw): **182 of 189 habits found, 6 wrong, 3 invented**, against plain Gemma 3 4B's 146 found, 28 wrong, 230 invented, and the app's code alone 105 found. The app takes only its sign-off, once code has checked it: 113 habits with it, 110 with plain Gemma |

With your Claude key, List on eBay uses two of them too: flip-reader-5 reads your notes on the iPhone for its flaws
and flip-kinds-1 sorts them, for Claude Haiku 5.5 to write the draft from (without a key, Gemma 3 4B writes it from
your notes).

flip-wording-4b's numbers come from judges who applied the four new rules, which flip-wording-3 wasn't trained for: under them flip-wording-3 is sendable on 87.1% of the 240 held-out listings, against 92.5% on 3 Oct. Compare the two models by their side-by-side numbers, not across the tables.

**Checked on the Mac (6 Oct 2026, a MacBook Air M4 with 16 GB).** Each of the three new models gave the same answers
as in its cloud test: flip-kinds-1 on 40 of 40 validation sentences, flip-wording-4b on 30 of 30 held-out listings,
flip-style-1b on 7 of 8 validation buyers (on the eighth it left out one extra phrase). flip-reader-5 was checked when
it was installed on 26 Sep: 28 of 30 check-set answers exactly as expected. Once loaded, each takes about 1.5 s a flaw
sentence (flip-kinds-1), 1.2-1.8 s a reason (flip-wording-4b) and about 4 s a buyer's messages (flip-style-1b; 2.6-6.5 s
for the style test's buyers after the first, on 9 Nov); the first answer, while the model loads, takes 3-9 s.

**A fresh test on the Mac**, on data none of them had seen, scored the same ways as the cloud tests: 245 real listings
(55 first seen by AlertFlip on 11-6 Oct, 190 from the reader's own test sets; none shares text with flip-reader-5's
training data or with any of flip-kinds-1's or flip-wording-4b's data), read by flip-reader-5, and 40 new made-up buyers
written free-form, with no code-written plan:

| Model | Fresh test | Against |
|---|---|---|
| flip-kinds-1 | 181 flaw sentences from the 128 listings with a flaw, first blind key: **91.7% exactly right, price cut wrong on 6.6%**; under the carrier rule (below): **3.9%**, 94.5% exactly right | the app's own rules: 74.6% and 23.8% (p < 0.0001); under the carrier rule 18.8% (18.2% until 4 Nov, when they began to read "works with Metro and T-Mobile service" as two networks, so no lock; 26.0% before they followed the rule) |
| flip-wording-4b | the 128 listings, blind judges: **94.5% sendable**, a made-up fact 3.1%, a fact lost 2.3% | flip-wording-3: 91.4%, 3.9%, 3.1% (better on 6, worse on 2: not a proven difference) |
| flip-style-1b | the 40 new buyers: **131 of 136 habits found, 0 wrong, 5 invented** | plain Gemma 3 4B: 108 found, 10 wrong, 276 invented |

Under the first key, 5 of flip-kinds-1's 12 misses there were a carrier named without saying it's locked: 4 on US
listings ("Network AT&T", "Works with verizon wireless") and 1 UK ("Unsure if locked or not, we are with EE"). The
carrier rule below counts all 5 as right (7 misses). The labels disagreed, not the model: flip-kinds-1's training and
validation labels called a carrier named with no lock word or "unlocked" a network lock 79% of the time (244 of 308),
that test's labellers 4 of its 7 such sentences.

**The carrier rule (set by the owner on 6 Oct evening).** A carrier or network named for the phone ("Carrier: AT&T",
"Galaxy S21 EE", "for Straight Talk", "works on Verizon") counts as a network lock unless the listing says it's
unlocked or works on any network. It's buyer-safe on purpose: a locked phone you overpaid for costs more than an offer
4-16% lower (the UK cuts measured on 4 Nov: 12% for an iPhone and 16% for a Samsung when the lock is the listing's
worst flaw, about 5% and 4% beside a worse flaw or damage). Every test sentence that mentions a carrier, a
network, a SIM or a lock (161 across the sealed test and both fresh tests) was labelled again on that one question,
blind, by two labellers (who agreed on 160) and a third on the split; the scores here use those keys, and the rule only
ever added a network lock (to 6 sealed sentences, 5 in the first fresh test, 18 in the second). flip-kinds-1 already
answers this way: on network lock it agreed with those labels on 158 of the 161 (93 of the 94 locks). The app's own
rules, which sort the title, any sentence the model can't answer and, since 4 Nov, a carrier line in the description
the reader didn't quote, follow it too since 6 Oct evening (`network_lock` and `carrier_line` in
[`flip/prices.py`](flip/prices.py)): before, they counted a lock only when the listing said so ("locked to EE", "EE
only") and found 23 of the 94. Two independent reviews tried 353 ways sellers write a carrier, an unlock or a word that
only looks like one ("Cosmic Orange Mobile Phone", "on three spots", "playing cricket", "unlocked from my iCloud", "I
think it's unlocked"); the first one's 193 and every one that failed are tests now
([`tests/carrier_cases.py`](tests/carrier_cases.py), [`tests/test_carrier_rule.py`](tests/test_carrier_rule.py)). On titles from 673 more listings from the reader's test
sets no one had read, labelled blind, every lock it found was right (113 of 113); it missed 6 that blind labellers
called locked. Those 6 were read and fixed after, so the rules now find all 119 and none wrong, and that's no longer
an unseen test. A code rule doing the opposite (a network lock only when the sentence says "locked", "only" or "tied to") was tried and
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
the app's own rules 21.0%. The app's own rules aren't scored blind: their carrier code was written after the carrier
sentences of these three tests had been read, and two earlier fixes came from reading the sealed test's misses, so
their scores here flatter them, not flip-kinds-1.

- **flip-kinds-2, a second training round**: flip-kinds-1's data plus 1,366 sentences labelled blind the same way,
  1,136 for training and 230 for validation (5,736 / 630). 363 of the training ones are kinds flip-kinds-1 got wrong
  under the labelling brief of the time (a passcode the seller knows, working only on charge, locked and for parts, a
  warning that names no flaw, a hinge, a payment plan, and a carrier named, which that brief said isn't a lock: the
  opposite of the owner's rule above); 273 are from Samsung and MacBook listings (Google and FRP locks, Knox, burn-in,
  screen lines; MDM, firmware passwords, keyboard and trackpad faults, a battery's "Service Recommended"); 500 are at
  random. Picked over a 3-pass run on validation (59 vs 60 of 630 priced wrong; flip-kinds-1: 57). Its rule, written
  before its fresh answers: it goes in only if it prices fewer sentences wrong than flip-kinds-1 and is no worse on
  iPhone, Samsung or MacBook. Scored to the carrier rule it priced 26 wrong against 25 (4 fixed, 5 broken, p = 1.0):
  1 fewer on Samsung and 1 fewer on MacBook, 3 more on iPhones (8 against 5), none of them a proven difference, and by
  its rule's counts it doesn't go in; under the first key, with the dropped code rule on both as the rule was written,
  26 each and more on iPhones too. So flip-kinds-1 stays. On the sealed test: 4.2% against 3.8%; 13 of those
  400 sentences come from listings whose other sentences it trained on, and on the other 387 it's 4.4% against 3.9%.

| Offer reason | Sendable (239 listings) | A made-up fact | Paid calls per 1,000 listings with a flaw |
|---|---|---|---|
| flip-wording-4b alone | 90.8% | 2.9% | none |
| flip-wording-3 alone | 90.8% | 5.0% | none |
| flip-wording-4b, every reason checked by Claude Haiku and a flagged one fixed by Sonnet (the app with your Claude key) | 93.7% | 1.3% | 1,000 Haiku + 243 Sonnet: £0.43 |
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
- **With no Claude key** (or in local mode) the paid check doesn't run, so flip-wording-4b's reason is what goes out,
  its 2.9% made-up facts included. Code's checks still hold the message's numbers and places to the listing alone, but
  take the reason's words on the condition and the battery as the listing's own, as code can't judge a rewording:
  held to the listing alone, code's checks would drop 57 of the 925 right reasons flip-wording-4b wrote in the saved
  blind tests (the cloud test's 740 and both fresh tests: 6.2%, such as "replaced" for "new screen", "locked to
  T-Mobile" for "T-Mobile only" or a French listing's reason in English) to catch 8 of its 35 made-up ones (15 Nov review).

Plain Gemma 3 4B (Google's, not fine-tuned) still writes the message when the AI writes (a draft, or Rewrite), reads a
listing when flip-reader-5 isn't installed or doesn't answer, and writes List on eBay's draft with no Claude key (or
`FLIP_LISTING_WRITER=gemma` in `.env`).

Earlier versions, and flip-kinds-2 (trained after flip-kinds-1, not used), kept to compare against:

| Model | Trained on | Tested result |
|---|---|---|
| flip-reader (round 1, 24 Sep) | 1,582 / 487 | its sealed test, 1,000 phones: 875 of 979 flaw sentences found (89.4%) vs plain Gemma 3 4B's 858 (87.6%), not a proven difference; 62 vs 79 wrong flags |
| flip-reader-3 (25 Sep) | 12,304 / 400 | 2,997 listings it never saw: 92.7% of flaws found, 95.7% precision; on Samsung and MacBook 89.6% vs plain Gemma's 71.1% |
| flip-reader-4 (25 Sep) | 30,031 / 593 | 5,819 listings in 3 countries, one hand-checked answer key: **96.4% of flaws found vs round 3's 94.8%** (p = 9e-5), false alarms 29 vs 130, precision 99.0% vs 95.6% |
| flip-wording (round 1, 1 Oct) | 8,346 / 500 | 240 held-out: 87.9% sendable (Claude Haiku 75.4%, code alone 38.8%), 4.2% with a made-up fact |
| flip-wording-2 (1 Oct) | 10,237 / 499 | 240 held-out: 90.4% sendable, 1.7% with a made-up fact |
| flip-wording-3 (3 Oct) | 12,428 / 498 | 240 held-out listings, blind judges: 92.5% sendable, 2.1% with a made-up fact, 1.5 s each; with a Claude Haiku check and a Sonnet fix after it, about 95%. In use until 6 Oct; the Mac it was tested on keeps it to go back to (`FLIP_WORDING_MODEL=flip-wording-3` in `.env`), but it isn't on the release |
| flip-kinds-2 (6 Oct, not used) | 5,736 / 630 | Scored to the carrier rule: the second fresh test, 8.5% priced wrong (flip-kinds-1 8.2%); the sealed test's 387 sentences from listings it never trained on, 4.4% (3.9%), and all 400, 13 of them from listings in its training data, 4.2% (3.8%). Same answers on the Mac as in the cloud on 80 of 80 validation sentences |

On 6 Oct the earlier versions were taken out of the Mac's Ollama to make room for the new ones; flip-wording-3 stays as
the way back, and flip-kinds-2 is installed beside flip-kinds-1 but not used. None of these is on the release: their
fingerprints below stay as the record of exactly what was tested.

## How they were trained

Unsloth's QLoRA recipe on one cloud GPU (the readers on Colab: a T4 for round 1, then an L4 and A100s; the other
models on Modal, which ran their notebooks, written for Kaggle, unchanged: an L4 for the first two wording rounds, then
A10s, and L40S cards for two comparison runs), written down in a run record for every model:

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

Library versions for the models in the table: unsloth 2026.11.3 (2026.11.2 for flip-reader-4), transformers 4.57.6,
trl 0.22.2, peft 0.21.2; torch 2.11.0 (2.14.1 for flip-reader-5).

## How they were tested

- **On listings the model never trained on.** Every test set was checked for repeats and near-copies of training
  listings, by id and by text, before any model answered it (a set drawn after training, as both fresh tests were,
  when it was drawn), and set aside before anyone read the results. Two exceptions: flip-kinds-2's
  new training sentences came from the same listings as 13 of the sealed test's 400, so its sealed score is also given
  on the other 387; and 19 short stock sentences in the second fresh test ("Battery health 85%", "Can be used for
  parts") also occur in flip-kinds-1's training rows. Both fresh tests have been read for misses since, so they're
  development sets now. The app's own rules aren't held to this: some of their fixes came from reading these tests, so
  their scores flatter them (above).
- **Keys follow the owner's rules.** When the owner set a rule after a key was made (the carrier rule, 6 Oct), every
  test sentence it could touch was labelled again blind and the scores were given both ways.
- **Against an answer key checked twice.** Claude agents labelled each listing under written rules. For the readers, a
  second labeller who couldn't see the first one's answers labelled samples again: they agreed with kappa 0.95. For
  the wording, every label was checked by a second agent and by code.
- **Wording judged blind.** From flip-wording-3's round on, each reason was judged by two Claude judges who didn't know
  which model, or code, wrote it; where they split, three fresh judges decided by majority (one third judge in
  flip-wording-3's own round). Rounds 1 and 2 had one judge, with a second on a sample to check they agreed.
- **A difference is called real only when it's significant** (McNemar's test on the same listings). Otherwise the
  result says "a tie" or "not proven".
- Each test plan, and each rule for picking or switching a model, was written before the new model's answers existed,
  so a result can't be picked after the fact (the exact flip-kinds-2 switch rule came after flip-kinds-1's fresh
  answers but before flip-kinds-2's); the carrier rule came after all the results, so those scores are given both ways.

## Getting the weights

The four model files in use are on the repo's GitHub release `models-v1` (9 Nov 2026, the owner's choice), each split
into parts under GitHub's 2 GB limit, with each model's Modelfile and SHA256SUMS, the SHA-256 of every part and
Modelfile. [`launcher/get-models.sh`](launcher/get-models.sh) (Mac) and
[`launcher\windows-setup.ps1`](launcher/windows-setup.ps1) (Windows) download them, check every part against
SHA256SUMS and then each whole model file against its fingerprint below, and add a model to Ollama only if it's the
version that was tested ([models/README.md](models/README.md)). On a Mac each Modelfile (the model's prompt template
and settings) must match its fingerprint below too, as must one `launcher/export-models.sh` copies out;
windows-setup.ps1 checks a release's Modelfile only against SHA256SUMS. A model Ollama already has as the tested
version is skipped. The other models below aren't on the release: their fingerprints are the record of what was
tested.

If the release isn't there (a fork's clone has none: GitHub doesn't copy releases), or a model or a file isn't on it,
both scripts stop and say which. get-models.sh asks whether the release is there and public
(`launcher/get-models.sh owner/name` names another repo's); windows-setup.ps1 stops before it builds the app and
names its other ways: `-Repo` or `-Tag` for another release, `-Models` with a folder made on a Mac by
`launcher/export-models.sh`, or `-NoModels`. A part that stops downloading carries on from where it
stopped, up to 10 tries in all on a Mac and 5 on Windows. On a Mac what it downloaded stays in
`~/Library/Caches/FlipAssist-models`, so running it again carries on; on Windows a run again skips the models already
added and starts the others afresh. Without these models FlipAssist still runs, with Gemma 3 4B and code doing their
jobs.

They're modified versions of Gemma 3 4B, under the Gemma Terms of Use ([models/NOTICE](models/NOTICE)).

The training data isn't published. The readers, the wording models and the flaw sorters learned from real sellers'
listings, and a model can repeat pieces of what it learned: don't use them to find, rebuild or republish anyone's
listing. **flip-style-1b** (it learns a buyer's habits: greeting, offer, sign-off) was trained only on made-up buyers,
so its data and its test can be published too.

## How to check a model file

Each file's SHA-256 is its fingerprint, and the scripts above check it themselves. By hand, the release's parts joined
(`cat flip-wording-4b.gguf.part-* | shasum -a 256`) must print the value below, and so must a model file copied out by
`launcher/export-models.sh` (`shasum -a 256 flip-wording-4b/flip-wording-4b.gguf`; on Windows
`Get-FileHash -Algorithm SHA256 flip-wording-4b\flip-wording-4b.gguf`, which prints it in capitals). In Ollama,
`ollama show flip-wording-4b --modelfile` shows the same value in its `FROM .../sha256-...` line.

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

Each model's Modelfile (`flip-wording-4b.Modelfile` on the release, say, or `flip-wording-4b/Modelfile` in an export)
is what Ollama 0.40.11's `ollama show --modelfile` prints for the tested model, with its `FROM` line made
`FROM ./<model>.gguf`, and `shasum -a 256` must print:

| Model | SHA-256 of its Modelfile |
|---|---|
| flip-reader-5 | `8c0a25f122166b29ef661b053c475a87cbcfcb7d5acd9fc4c99165538e224245` |
| flip-wording-4b | `49bbde2bcc475d2084f7424fae3b0eeec11a0b22f86b8cdf513e29bdc09aed4d` |
| flip-kinds-1 | `0eff6f2dc41da8ea134a65569b692ee8c57123b0ea9ce6f20ef473e996eeb8a1` |
| flip-style-1b | `9f3426680520a0baefba7e3ac11d69fe2d525e694aac4357ce7e49d77e6fbff2` |

An Ollama that prints a Modelfile differently gives other values for the same model: `launcher/upload-models.sh`,
`package-models.sh` and `export-models.sh` then refuse it until these values are changed together, here and in those
scripts and `get-models.sh`.

## A test you can run yourself

[`evals/style/`](evals/style/) is the hard style test: 40 made-up buyers with messy habits (typos, capitals, emojis,
shortcuts, one-off phrases that look like habits) and an answer key checked by a blind judge and by code. Score our
saved answers to get the same table we did:
`.venv/bin/python evals/style/score.py --answers evals/style/answers-gemma3-4b.json`, and the same with
`answers-flip-style-1b.json`. With `--ask gemma3:4b` it asks the model in your own Ollama instead and saves its answers
in a new dated file beside ours; another Ollama version or computer can change a few of them
([`evals/style/README.md`](evals/style/README.md)).
