# The hard style test

FlipAssist learns how a buyer writes offer messages: how they open ("hiya"), how they make the offer
("wud u take {price}"), what they add after it ("can collect 2day"), how they say they like the item, how they sign off
("cheers sam :)") and which words they always write short ("u" for "you"). This folder is the test for that learning.

Everything here is made up. No real buyer's messages are in it.

## What's in it

| File | What it is |
|---|---|
| `writers.json` | 40 made-up buyers, 5 to 10 messages each (288 in all), with the answer key for each buyer |
| `answers-gemma3-4b.json`, `answers-flip-style-1b.json` | plain Gemma 3 4B's and flip-style-1b's answers, saved, so the table below can be scored without Ollama |
| `briefs.py`, `briefs.json` | how each buyer was planned: code picked a voice, the habits and two hard cases, then Claude wrote the messages to that plan (run `briefs.py` and it writes the same `briefs.json` again) |
| `score.py` | runs the test and prints the table below |

The buyers are hard on purpose: typos repeated the same way every time, capitals that change between messages,
emojis, kisses, prices written as "160£" or "140 pound", a phrase in only one message that sounds like a habit (it isn't
one), and two closings that look alike but use different words (neither is a habit).

One planned hard case, "one habit appears in exactly 2 of the messages (still a habit)", is a habit by the rule below
only for a buyer with 5 messages: 2 of 6 or more is under 40%. It was planned for 9 buyers, 8 of them with 6 to 10
messages, so the key has it once (w36: "can collect today", 2 of 5). Where the writer listed it anyway
(w16's "I can pay straight away", 2 of 8; w20's "can pick up asap", 2 of 6), the key leaves it out, and an AI that
names it counts as invented.

## What counts as a habit

A habit is something a buyer repeats in **at least 2 of their messages and at least 40% of them**, in the same words.
Capital letters and punctuation may change, and so may where an emoji sits, except in a sign-off: it must end the
messages with the same words, smileys and emojis, in the same order. The spelling (typos included) may not change. A
word counts as written short only if the buyer never writes it in full.

The app's own rules are close to these, but not all the same. Its style card keeps a greeting, a likes phrase, a
sign-off with a name or a smiley and a word written short by the same 2-and-40% rule (the greeting by 40% alone, which
is at least 2 messages for every buyer here), but a word counts as written short when the buyer writes it short more
often than in full. Its phrasebook, where it keeps the offer, what comes after it and a plain sign-off ("Cheers."),
takes a sentence in 2 messages whatever the share.

## How the answer key was checked

1. Code wrote the plan for each buyer, so every kind of habit and every hard case is covered (the 2-message one only
   once, as above).
2. Claude wrote the messages to that plan, and listed the habits it had put in (`writer_key` in `writers.json`).
3. A second Claude, who never saw the plan, read only the messages and wrote down the habits it found
   (`blind_judge`).
4. Code counted, for every habit on either list, the messages it is really in. The key (`key`) keeps each habit that
   passes the 2-and-40% rule, from either list. A habit that doesn't pass is left out, whoever named it. Where both
   lists name a different habit for the same thing and both pass, the writer's is kept. So the key has only habits
   one of the lists named: it leaves out one the app's code also learns, "ok" for "okay", for w06 (5 of 6 messages),
   w07 (5 of 7) and w39 (6 of 8), though it passes the rule. With it the key would have 192 habits: code would find
   108, the app 113 with plain Gemma and 116 with flip-style-1b, and each AI the same habits as now, as none named it.
   An AI that names it is counted wrong.
5. `score.py --check-key` repeats that count for the finished key. Run it yourself: it prints
   `0 key habits that don't repeat`.

## Run it

From the repository's root, with the Python environment set up as in the main README:

```bash
.venv/bin/python evals/style/score.py
```

That scores the code alone (the app's style card with no AI). To also ask a model in your own
[Ollama](https://ollama.com), and save its answers beside the buyers in a new file, dated (like
`answers-gemma3-4b-YYYY-MM-DD-HHMMSS.json`), so ours stay as they are:

```bash
.venv/bin/python evals/style/score.py --ask gemma3:4b
```

If no buyer gets an answer, because Ollama isn't running or doesn't have the model, it says so and stops, with
nothing saved or scored. If only some don't, it says how many, and scores those buyers as if the model named nothing.

To score answers saved before (ours for plain Gemma 3 4B and flip-style-1b are here), or to check the key:

```bash
.venv/bin/python evals/style/score.py --answers evals/style/answers-gemma3-4b.json
```

```bash
.venv/bin/python evals/style/score.py --check-key
```

`--writers OTHER.json` scores the same way on another set of buyers in this folder's format (with `--ask`, the model's
answers are saved beside that file).

## What the columns mean

- **habits**: how many habits of that kind the key has (189 in all).
- **code**: how many the app's code finds on its own.
- **app**: how many the app finds with the AI's help (the AI's answer is checked by code first; only what passes is
  used).
- **ai found / missed / wrong / invented**: the AI's own answer before any checking. *Wrong* means a phrase that passes
  the habit rule above but isn't the habit the key has there. *Invented* means one that doesn't pass it: it's in fewer
  than 2 of the buyer's messages or under 40% of them (for a sign-off, the messages that end with it; for a word written
  short, also when the buyer writes it in full). Of plain Gemma's 230, 86 are in no message, 71 in only one, 20 in more
  but under 40%, and 53 are shortcuts of a word the buyer also writes in full, most of them no shortcut at all
  ("it" written "the"). flip-style-1b's 3 are real phrases that don't pass: "Hey there" in 2 of 7 messages,
  "can pick up asap 🏃‍♀️" in 2 of 6, and "nadia :)" for a sign-off that ends "nadia :), cheers". A part after the
  offer that the AI lists more than once counts once.

## Our results (6 Oct 2026)

| | found (of 189) | wrong | invented |
|---|---|---|---|
| Code alone | 105 | – | – |
| The app: code + plain Gemma 3 4B's sign-off, checked | 110 | – | – |
| Plain Gemma 3 4B, its own answer | 146 | 28 | 230 |
| **flip-style-1b**, its own answer | **182** | **6** | **3** |
| The app: code + flip-style-1b's sign-off, checked | 113 | – | – |

Plain Gemma finds many more habits than code, but it also makes up a lot, which is why the app only uses the sign-off it
names, and only once code has checked it. flip-style-1b, trained on made-up buyers like these (none of these 40), finds
nearly all of them and makes up almost nothing. It took this test once, after it was picked on its own validation
buyers. Its answers are in `answers-flip-style-1b.json`.

Keep in mind: these buyers and its training buyers were made the same way (Claude writing to code-written plans), so
this shows it learned the task as defined here. How well it reads real people's messages is a separate question.
