# FlipAssist-ai

Drafts eBay listings and offer messages for a reseller. Plain code does everything it can. A small local AI model does only what code can't. A paid API model steps in only when the local answer fails a check, and a person approves every draft.

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
- **Fills eBay's own fields in eBay's own words** (phones so far, `flip/ebay.py`):
  - the category (Mobile & Smart Phones) and the four fields eBay won't list a phone without: Brand, Model, Storage Capacity and Colour;
  - then what the catalogue and the reseller's notes already know: network, 4G/5G, operating system, screen size and chip;
  - spelt as eBay's lists spell them ("Apple iPhone 13", "128 GB", "Apple A15 Bionic"); each colour becomes one of eBay's 16 plain colours, the one UK sellers pick for it (Midnight is Black, Rose Gold is Pink: `data/ebay_map.json`, with the counts);
  - eBay's lists come from its own API (`python -m flip.ebay --refresh` writes `data/ebay_fields.json`), and a test holds every phone in the catalogue to them.
- **Says what to check in the seller's words:** a fault the seller's description mentions ("sometimes it does not focus") that the reseller's notes don't is quoted back to check before listing, and an empty field eBay needs gets the seller's word as a hint ("the seller says 128 GB"), never filled from it.
- **Sets eBay's condition from the reseller's notes:** For parts or not working for a fault, New or Opened - never used only when the notes back it, Used otherwise. A crack or scratch on its own is wear, not a fault. The AI writes the condition note to match and can't answer another condition.
- **Does the money in pence:** profit after fees, and an offer price rounded to a tidy number.
- **Checks an AI answer before it's used:**
  - the agreed shape and allowed values;
  - no numbers the inputs don't contain;
  - no yes/no claims about the box, charger, cable, case, controller, dock, game, screen protector, receipt, warranty or network lock that the inputs don't back up, with the reseller's notes beating the seller's text;
  - condition claims (new, sealed, working, flawless, battery, scratches and other marks) only when the reseller's own notes back them, and "For parts or not working" whenever the notes mention a fault;
  - where a mark is ("on the back") only when the notes say where;
  - what people type is read with typos allowed ("few scraches", "baterray 88", "bh 88%"), the AI's own words as written;
  - nothing that contradicts the item: another model, colour, storage size or edition;
  - no prices, contact details or paying off the platform;
  - length limits.
- **Drafts the rest with AI** (`python -m flip.draft`):
  - Gemma 3 4B runs on the reseller's own machine through Ollama. It's asked only for what code couldn't fill: the colour (from that model's real colours, or "unsure"), a condition note and a description, held to an exact answer shape.
  - The checks decide. An answer that fails gets one try on Claude Haiku. If that fails too, the item is marked "needs you".
  - If the local model isn't running, nothing is sent to the API instead.
  - If Gemma ends its answer with a curly quote (”), or writes two in a row, it's stopped there and the answer closed, instead of running on for a minute.
  - A draft is "ready" only when nothing is missing.
  - Every attempt goes into a private audit log with its tokens, seconds and cost.
- **Drafts offer messages in the reseller's own style** (`python -m flip.message`):
  - Three kinds of offer, each priced by code. The AI never picks a price.
    - Lower: 15% under asking by default, rounded down to a tidy number.
    - The asking price.
    - More: asking plus 5%, rounded up to a tidy number and at least one step over.
  - **The listing is read by AI, held to the seller's own words by code.** Gemma reads the flaws, where to collect and whether the seller takes offers; Haiku gets one try when Gemma's reading fails a check. Code then:
    - keeps only quotes that are in the listing word for word (capitals, punctuation, apostrophes and hyphens aside), so a flaw can't be made up;
    - counts a quote as a flaw only if it says what's wrong in so many words ("crack", "dot", "stiff", "drifts", "not working"...) and the seller doesn't deny it in the same clause. "Black spots" from "*No* black spots on the screen", "there aren't any dots" and "screen burn: none" fail the reading. Facts ("battery health 90%"), praise ("screen is perfect") and asides ("see pics") aren't flaws, and a seller's own story is cut to the flaw ("I dropped it and cracked the back" becomes "cracked the back");
    - keeps every flaw code finds by itself, judged the same way: AI can add a flaw, never take one away. The more precise words win ("cracked back" over "Good condition apart from cracked back");
    - takes "no offers" only in words that say it ("price is firm"), and never from a listing that takes offers ("open to offers", "offers over £400") or only limits them ("no offers under £250").

    With no model, or none that passes, code reads the listing alone. Sellers' words code has no list for ("black dot on the screen", "hinge is stiff") are then missed.
  - **"No offers" never changes the offer.** The reseller still picks lower, asking or more; the draft carries a note with the seller's words to show under the message.
  - What's worth saying with each offer, in the seller's own words:
    - a flaw ("broken back") is the reason for a lower offer, unless the seller says it's already priced in;
    - at the asking price, the message says the reseller doesn't mind it;
    - good condition with no flaw is the reason for paying more.
  - If the reseller's past messages usually mention condition, that point goes in by itself. Otherwise the draft leaves it out and asks: *The listing says "Broken back". Mention it as the reason for your offer?*
  - A longer message on request. It aims for about twice the reseller's usual length, between 30 and 70 words; three quarters of the aim passes, and it's never shorter than the draft it starts from. It says more only with their usual points and the questions the listing doesn't answer (battery health, unlocked, charger, box and so on, kept in `data/questions.json`). It can start from the draft on screen and keep its wording.
  - A style card worked out by code from the reseller's past messages: their usual greeting, length, questions, emojis and what they mention, plus their phrasebook (the opener, offer and closing they've written in at least two messages).
  - **Who writes:**
    - If the reseller's messages repeat, or there are none yet, code writes the message with no AI. It uses their own sentences with the new price, the seller's words for the flaw, and the open questions. A habit is a sentence in at least two messages that names no item and carries no second price. If the seller's words don't fit a sentence it knows ("I dropped it and cracked the back"), or the draft fails a check, the AI writes instead.
    - If their messages vary, the AI writes. It's shown the past messages for the most similar listings, found by meaning (MiniLM embeddings in a Chroma vector database, all on this machine), with their old prices hidden.
    - The pickup place from the listing goes in ("Can collect from Leeds LS6 today") only when the reseller's own messages talk about collecting.
  - The same checks and fallback as listings, plus checks of their own:
    - the exact offer and no other price;
    - an offer over asking is said, never asked ("would you take £210?" reads like asking for a discount);
    - the condition comes up only when it's meant to, and only as the listing says it: never a flaw it doesn't mention, never "working" for a faulty item. A question like "any scratches?" is fine;
    - nothing said to come with the item (box, charger, unlocked and so on) that the listing doesn't say, and no question the listing already answers;
    - a longer message has enough words;
    - no promise about collecting, cash or posting that the reseller's own messages don't make ("I can arrange collection quickly" was the AI's most common invention). A "games collection" or a "Collector's Edition" isn't a promise;
    - a reason about the item uses only the listing's words ("given the stiff hinge" fails on a listing that doesn't say it), and no other model is named;
    - the asking price is never misquoted, and a lower offer never offers more in words ("if not I can pay the full asking price");
    - no made-up story about the reseller in the common shapes: who it's for, why they want it, where they are, that they don't resell. A place name ("I'm in Leeds") still gets through;
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

## The API

What AlertFlip calls, from a Supabase function, so the key never sits inside the phone app (`flip/api.py`, FastAPI):

```bash
.venv/bin/uvicorn flip.api:app --port 8000    # then open http://127.0.0.1:8000/docs
```

| Endpoint | What it does |
|---|---|
| `GET /health` | Whether the local model is running and the keys are set (no key needed, none shown) |
| `POST /messages/draft` | Reads the listing, then drafts the offer at code's starting price or the one picked on the app's slider (`offer`, which must fit the kind of offer). It returns the message, who wrote it, the "no offers" note, what was read, every attempt with its seconds and cost, and a draft id |
| `POST /listings/draft` | The listing's text, your notes and up to 8 photos (form fields and file uploads) in, the eBay draft out |
| `POST /drafts/{id}/approve` | What you actually sent or listed, so the results can count how often a draft was right as it was. An approved message also joins the messages your style is learned from |
| `GET /stats` | The cost meter: drafts, the share done on this machine, cost per 100 drafts, how often a draft was edited before sending |
| `GET /style` | What it learned from your messages: the style card (habits in 40% or more of them) and the phrasebook (sentences in 2 or more) |
| `GET`, `POST /style/messages`, `DELETE /style/messages/{id}` | The messages it learns from: list them, add one or many (`title`, `price`, `text`), or delete one. The search for the closest past messages follows at once, so the next draft already uses what you added |

- **Who can call it.** It answers only on this machine (127.0.0.1) unless it's put online on purpose. Every endpoint but `/health` and the `/docs` pages (which only describe the API) needs `FLIP_API_KEY` from `.env` in an `X-API-Key` header. A key under 32 characters, like the example file's, counts as none, and the API then refuses every call.
- **Turned away before it's read.** A request without the key, or bigger than its endpoint takes (1 MB, or 121 MB for 8 photos), is refused before any of it is read, so nobody can fill the machine's memory or disk.
- **It never sends or lists anything itself.** AlertFlip does that, after the reseller approves.
- **Bad input is refused before anything runs:** an unknown kind of offer, a price that isn't a price (or is under £1), an offer that doesn't fit its kind, a file that isn't a photo. A photo is known by its bytes (JPEG, PNG, HEIC or WebP), not its name, and one with more pixels than any camera takes is refused before it's converted.

```bash
curl -s http://127.0.0.1:8000/messages/draft -H "X-API-Key: $FLIP_API_KEY" -H "Content-Type: application/json" \
  -d '{"listing": {"title": "iPhone 13 128GB", "asking_price": "220", "description": "Black dot on the screen"}, "mention": true}'
```

## The app

A Mac-style window in AlertFlip's design (`frontend/`, React and TypeScript), light or dark:
- **Set up your style**, on first launch: reply to 8 listings (each shows one habit, like whether you mention flaws), or paste messages you've already sent. Nothing gets trained: it learns from your own messages with plain code.
- **AI message:** price cards and a slider, the message with the seller's "no offers" note, what was read, and why, step by step.
- **List on eBay:** photos, notes, and the draft to check.
- **Home:** the cost meter, and whether Gemma, the backup and the key are ready.
- **Your style:** the style card, the phrasebook, and the messages it learns from, each yours to delete.

```bash
.venv/bin/uvicorn flip.api:app --port 8000      # the API, in one terminal
cd frontend && npm install && npm run dev       # the app, in another: then open http://127.0.0.1:5173
```

The app's dev server adds the API key on the way, from `.env`, so the key never reaches the browser.

## The launcher

FlipAssist opens like any Mac app: one double-click on **FlipAssist** (in Applications, Spotlight or the Dock) and it runs in its own window, with no browser around it (`launcher/`, Electron and TypeScript).

1. A launch screen shows Gemma and the API starting. Whatever is already running is used as it is; whatever isn't is started: Ollama for Gemma, and the API from the repo's own Python.
2. Gemma is loaded into memory straight away, so the first draft doesn't wait for it. Without Gemma, the launch screen says so and drafts use code only.
3. The app is the built front end, at `app://flipassist/`. Its calls to `/api/...` are passed on to the API by the launcher, which adds the key from `.env` on the way. The page never sees the key, and no other program on the Mac can borrow it, as it could from a local web server.
4. Quitting stops only what the launcher started. What each part printed is in `~/Library/Logs/FlipAssist`.

```bash
launcher/build.sh     # builds the app and the launcher, draws the icon, puts FlipAssist.app in ~/Applications
cd launcher && npm test && npm run selftest    # the launcher's own tests, then the real window checked end to end
```

The self-test opens the window, checks every kind of call (files, JSON, photo uploads, refused paths, copying, saved settings) without drafting or saving anything, and quits.

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
| Colour | Code if the text names it; otherwise the AI from the photo |
| eBay's category and fields (Brand, Model, Storage Capacity, Colour...) | Code, in eBay's words (`data/ebay_fields.json`, `data/ebay_map.json`); phones so far |
| Condition | Code, from the reseller's notes |
| Condition note, description | The AI, then checked by code |
| Offer price, profit | Code |
| The listing's flaws, pickup place, "no offers" | The AI, held word for word to the listing by code |
| What to say about the condition | Code picks it from that reading; the reseller's style or the reseller decides |
| The offer message's wording | Code, from the reseller's own sentences; the AI only when their messages vary |

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

`--mode local` uses only the local model, `--mode api` only Claude Haiku, and the default `auto` tries the local model first.

For messages, set up your style in the app, or put your past messages in `testset/private/messages.csv` (`testset/messages.example.csv` shows the columns) and learn them; either way they're kept in `private/style.sqlite3`, which never leaves this machine:

```bash
.venv/bin/python -m flip.message --learn
.venv/bin/python -m flip.message "iPhone 13 128GB Midnight" --asking 220 --marketplace facebook
.venv/bin/python -m flip.message "iPhone 13 128GB" --asking 220 --description "Broken back" --offer asking --mention yes
```

`--offer` picks `lower` (the default), `asking` or `more`. `--longer` makes it about twice the usual length; `--previous "..."` makes that draft longer instead. `--mention yes` or `no` answers the question about the listing's flaw or good condition; without it, the reseller's style decides. `--writer template` or `ai` overrides who writes; the default lets the reseller's past messages decide.

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
- `launcher/`: FlipAssist as a Mac app (`build.sh` builds it)
- `data/`: the catalogue, eBay's item conditions and the questions a message may ask (facts, not code)
- `tests/`: a test for every rule
- `testset/`: the example format for the test set
- `private/`: the audit log and anything else the app saves while it runs (never uploaded)
