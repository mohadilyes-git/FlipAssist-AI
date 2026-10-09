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
| `briefs.py`, `briefs.json` | how each buyer was planned: code picked a voice and the habits, then Claude wrote the messages to that plan |
| `score.py` | runs the test and prints the table below |

The buyers are hard on purpose: typos repeated the same way every time, capitals that change between messages,
emojis, kisses, prices written as "150 quid", a phrase in only one message that sounds like a habit (it isn't one), and
two closings that look alike but use different words (neither is a habit).

## What counts as a habit

A habit is something a buyer repeats in **at least 2 of their messages and at least 40% of them**, in the same words.
Capital letters, punctuation and where the emoji sits may change; the spelling (typos included) may not. These are the
same rules the app uses.

## How the answer key was checked

1. Code wrote the plan for each buyer, so every kind of habit and every hard case is covered.
2. Claude wrote the messages to that plan, and listed the habits it had put in (`writer_key` in `writers.json`).
3. A second Claude, who never saw the plan, read only the messages and wrote down the habits it found
   (`blind_judge`).
4. Code counted, for every habit on either list, the messages it is really in. The key (`key`) keeps each habit that
   passes the 2-and-40% rule, from either list. A habit that doesn't pass is left out, whoever named it. Where both
   lists name a different habit for the same thing and both pass, the writer's is kept.
5. `score.py --check-key` repeats that count for the finished key. Run it yourself: it prints
   `0 key habits that don't repeat`.

## Run it

From the repository's root, with the Python environment set up as in the main README:

```bash
.venv/bin/python evals/style/score.py
```

That scores the code alone (the app's style card with no AI). To also ask a model in your own
[Ollama](https://ollama.com), and save its answers:

```bash
.venv/bin/python evals/style/score.py --ask gemma3:4b
```

To score answers saved before (ours for plain Gemma are here), or to check the key:

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
- **ai found / missed / wrong / invented**: the AI's own answer before any checking. *Wrong* means a phrase that does
  repeat but isn't the habit the key has there. *Invented* means words that don't repeat in the buyer's messages at all.

## Our results (6 Oct 2026)

| | found (of 189) | wrong | invented |
|---|---|---|---|
| Code alone | 105 | – | – |
| The app: code + plain Gemma 3 4B's sign-off, checked | 110 | – | – |
| Plain Gemma 3 4B, its own answer | 146 | 37 | 230 |
| **flip-style-1b**, its own answer | **182** | **6** | **3** |
| The app: code + flip-style-1b's sign-off, checked | 113 | – | – |

Plain Gemma finds many more habits than code, but it also makes up a lot, which is why the app only uses the sign-off it
names, and only once code has checked it. flip-style-1b, trained on made-up buyers like these (none of these 40), finds
nearly all of them and makes up almost nothing. It took this test once, after it was picked on its own validation
buyers. Its answers are in `answers-flip-style-1b.json`.

Keep in mind: these buyers and its training buyers were made the same way (Claude writing to code-written plans), so
this shows it learned the task as defined here. How well it reads real people's messages is a separate question.
