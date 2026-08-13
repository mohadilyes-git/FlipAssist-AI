# FlipAssist-ai

Drafts eBay listings and offer messages for a reseller. Plain code does everything it can. A small local AI model does only what code can't. A paid API model steps in only when the local answer fails a check, and a person approves every draft.

> **Work in progress.** The plain-code half, its safety checks, the AI listing drafter and the message drafter are built and tested. Next: an API for the app, a catalogue agent and measured results.

## What it does now

- **Finds the product** in a messy listing title ("iphone13 128gb unlocked boxed") using a catalogue of 42 models: every iPhone from the SE to the 17, plus the Galaxy S23, PS5, PS5 Slim, Switch OLED and AirPods Pro 2. It then fills every fact the catalogue knows:
  - model and storage;
  - colour, when the text names exactly one;
  - options such as Disc or Digital;
  - network lock;
  - specs.
- **Leaves gaps instead of guessing.**
  - Anything code isn't sure about goes on a "missing" list.
  - Parts, accessories, wanted ads and listings that name two products aren't matched at all.
- **Builds the eBay title** from a template, within eBay's 80-character limit.
- **Does the money in pence:** profit after fees, and an offer price rounded to a tidy number.
- **Checks an AI answer before it's used:**
  - the agreed shape and allowed values;
  - no numbers the inputs don't contain;
  - no yes/no claims about the box, charger, cable, case, controller, dock, game, screen protector, receipt, warranty or network lock that the inputs don't back up, with the reseller's notes beating the seller's text;
  - condition claims (new, sealed, working, flawless, battery, scratches and other marks) only when the reseller's own notes back them, and "For parts or not working" whenever the notes mention a fault;
  - nothing that contradicts the item: another model, colour, storage size or edition;
  - no prices, contact details or paying off the platform;
  - length limits.
- **Drafts the rest with AI** (`python -m flip.draft`):
  - Gemma 3 4B runs on the reseller's own machine through Ollama. It's asked only for what code couldn't fill: the colour (from that model's real colours, or "unsure"), the condition, a condition note and a description, held to an exact answer shape.
  - The checks decide. An answer that fails gets one try on Claude Haiku. If that fails too, the item is marked "needs you".
  - If the local model isn't running, nothing is sent to the API instead.
  - A draft is "ready" only when nothing is missing.
  - Every attempt goes into a private audit log with its tokens, seconds and cost.
- **Drafts offer messages in the reseller's own style** (`python -m flip.message`):
  - Three kinds of offer, each priced by code. The AI never picks a price.
    - Lower: 15% under asking by default, rounded down to a tidy number.
    - The asking price.
    - More: asking plus 5%, rounded up to a tidy number and at least one step over.
  - Code reads the listing for what's worth saying, in the seller's own words:
    - a flaw ("broken back") is the reason for a lower offer, unless the seller says it's already priced in;
    - at the asking price, the message says the reseller doesn't mind it;
    - good condition with no flaw is the reason for paying more.
  - If the reseller's past messages usually mention condition, that point goes in by itself. Otherwise the draft leaves it out and asks: *The listing says "Broken back". Mention it as the reason for your offer?*
  - A style card worked out by code from the reseller's past messages: their usual greeting, length, questions, emojis and what they mention.
  - The past messages for the most similar listings, found by meaning (MiniLM embeddings in a Chroma vector database, all on this machine), shown to the AI as examples with their old prices hidden.
  - The same checks and fallback as listings, plus checks of their own:
    - the exact offer and no other price;
    - an offer over asking is said, never asked ("would you take £210?" reads like asking for a discount);
    - the condition comes up only when it's meant to, and only as the listing says it. A question like "any scratches?" is fine;
    - no invented numbers, no contact details, nothing off the platform.
- **Scores the code** against a private test set of real items, with a scoring script.

## Planned

- **A web app** (FastAPI + React) where a person approves each draft.
- **Measured results on the test set:**
  - fields right for local, API and the switch;
  - cost per 100 listings;
  - minutes per listing by hand vs with the assistant.

## Who does what

| Field | Filled by |
|---|---|
| Model, storage, specs, title | Code, from `data/catalogue.json` |
| Colour | Code if the text names it; otherwise the AI from the photo |
| Condition, condition note, description | The AI, then checked by code |
| Offer price, profit | Code |
| What to say about the condition | Code reads it from the listing; the reseller's style or the reseller decides |

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
cp .env.example .env      # then put your key in .env (never uploaded)
.venv/bin/python -m flip.draft testset/items.example.json --mode local
```

`--mode local` uses only the local model, `--mode api` only Claude Haiku, and the default `auto` tries the local model first.

For messages, put your past messages in `testset/private/messages.csv` (`testset/messages.example.csv` shows the columns), then:

```bash
.venv/bin/python -m flip.message --learn
.venv/bin/python -m flip.message "iPhone 13 128GB Midnight" --asking 220 --marketplace facebook
.venv/bin/python -m flip.message "iPhone 13 128GB" --asking 220 --description "Broken back" --offer asking --mention yes
```

`--offer` picks `lower` (the default), `asking` or `more`. `--mention yes` or `no` answers the question about the listing's flaw or good condition; without it, the reseller's style decides.

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

- `flip/`: the code
- `data/`: the catalogue and eBay's item conditions (facts, not code)
- `tests/`: a test for every rule
- `testset/`: the example format for the test set
- `private/`: the audit log and anything else the app saves while it runs (never uploaded)
