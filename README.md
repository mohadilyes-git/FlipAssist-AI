# FlipAssist-AI

**A local-first AI assistant for people who resell second-hand phones and laptops.** Paste in a listing for an iPhone, a Samsung phone or a MacBook, and FlipAssist estimates its UK price flaw by flaw and drafts your offer to the seller in your own style. Give it your notes and photos of an iPhone, and it drafts the eBay listing.

The idea: plain code does everything it can. FlipAssist's own small models, fine-tuned and running on your computer, do what code can't. Claude is used only where it tested better, or to check an answer. Every AI answer has to pass code's checks, and nothing is sent or listed for you: you approve every draft.

It's a Mac app: a Python (FastAPI) backend under a React and TypeScript window in Electron, with four fine-tuned Gemma 3 4B models running in Ollama. The code was written with Claude Code.

**Status.** Built and tested on a Mac: the five screens, the API, the launcher, the four models and the checks. Windows support is built and tested on a Mac, but hasn't run on a Windows PC yet. What's next is under [Planned](#planned).

## Highlights

- **Reads listings well.** flip-reader-5 found the damage in 305 of 312 damaged UK listings it had never seen (iPhone 96.4%, Samsung 99.1%, MacBook 97.8%), and 95.3% of the 3,162 flaws in 5,032 unseen listings, at 99.4% precision.
- **Prices flaws better than rules do.** flip-kinds-1 sorts each flaw into the kinds the UK price is cut for. On 400 sealed flaw sentences it got the cut wrong (by 3 points or more) on 3.8%; code's own rules did on 17.5%.
- **Offer reasons ready to send.** flip-wording-4b words the reason on your computer, Claude Haiku 5.5 checks it and Claude Sonnet 5.5 fixes one it flags: 94-99% sendable on 239 fresh listings, depending on your taste. Strict blind judges passed 93.7%, counting a dropped detail or an odd wording as a miss, and 98.7% added or changed no fact.
- **eBay listings ready to post.** 95% of drafts were postable as is on 40 real UK iPhones, judged blind: as good as Claude Sonnet 5.5 alone (90%), at about a seventh of the cost (0.040p a listing).
- **Damage judged consistently.** Code and Claude Haiku 5.5, with Claude Sonnet 5.5 deciding when they disagree, matched three blind checkers on 93.3% of 299 fresh UK listings.
- **Learns your style without making it up.** flip-style-1b found 182 of 189 habits on the hard style test and invented 3, where plain Gemma 3 4B found 146 and invented 230.
- **Code where code is better.** On made-up listings, code's offer messages for a new user were fine to send 95% of the time and a small AI's 35%, so in the app code writes every message, around the reason the model words.
- **Fast and cheap.** A draft is on screen in 3.1-3.8 s on a 16 GB Mac (9-11 s before). The paid reason check costs about 43p per 1,000 listings with a flaw, with Claude's prompt cache warm.
- **Tested.** 5,500+ tests: 5,458 Python, 126 screen and 16 launcher. Claude test agents wrote over 4,000 cases to break the rules, and the 418 real failures they found are fixed and kept as tests.

The judges, labellers and checkers in these tests are Claude, working blind. [Results](#results) gives each test's size; [MODELS.md](MODELS.md) has the full record, including what didn't ship.

## How it works

Each job goes to the cheapest thing that does it well, in this order:

1. **Code first.** Plain Python does everything a rule can: the product's facts from a catalogue, the battery health, the offer prices, eBay's fields and condition, the price cuts, and the message itself, built from your own sentences. It's free, instant and gives the same answer every time.
2. **FlipAssist's own models next.** Four small models, each Gemma 3 4B fine-tuned for one job, run on your computer in Ollama. They read listings, word the offer's reason, sort flaws for the price and read your style. What they read stays on the computer.
3. **Claude only where it tested better, or to check.** With your own Anthropic key, Claude Haiku 5.5 checks every offer's reason, phrases the eBay listing and judges how bad the damage is. Claude Sonnet 5.5 fixes a reason Haiku flags, decides a damage call when code and Haiku disagree, and steps in when an answer from your computer fails a check.

| Job | Code | FlipAssist's models (your computer) | Claude (your key) |
|---|---|---|---|
| Find the model, storage, specs and eBay title | All of it, from `data/catalogue.json` | – | – |
| Read the battery health | All of it (`flip/numbers.py`) | – | – |
| Set the three offer prices | All of it | – | – |
| Read the listing: each flaw, the pickup place, "no offers" | Holds every quote to the listing; reads alone when no model can | flip-reader-5 (Gemma 3 4B when it isn't installed) | Sonnet reads again when a model's reading fails the checks |
| Word the offer's reason | Words it when flip-wording-4b isn't installed | flip-wording-4b | Haiku checks every reason; Sonnet fixes a flagged one |
| Write the offer message | Your own sentences (AlertFlip's before you have any), around the reason | Gemma 3 4B, only when you click Rewrite | Sonnet, when Gemma 3 4B's tries fail the checks |
| Learn your style | The style card and the phrasebook | flip-style-1b names your sign-off, which code checks | – |
| Sort each flaw for the UK price | The title, and any sentence the model can't answer | flip-kinds-1 | – |
| Judge how bad the damage is | Reads it | – | Haiku reads it too; Sonnet decides when they disagree |
| Cut the UK price | All of it, from the AlertFlip prices API's clean price: no model sets a number | – | – |
| Write the eBay condition note and description | Sets eBay's condition and fields; checks every fact made it in | flip-reader-5 pulls the facts from your notes; Gemma 3 4B writes with no key | Haiku phrases the facts; Sonnet rewrites a draft that fails |
| Pick the colour from the photos | Uses the colour the title or notes name | Gemma 3 4B, with no key | The listing's writer picks it; Sonnet looks again when it's unsure |

### FlipAssist's own models

All four are Gemma 3 4B fine-tuned with QLoRA (Unsloth), merged and quantised to Q4_K_M: about 2.5 GB each, run in Ollama. A "b" in a name marks the second run of a round, not a model size.

| Model | Its job | Trained on |
|---|---|---|
| flip-reader-5 | Reads a listing: each flaw as the seller's own sentence, where to collect, and whether the seller takes offers | 33,160 listings |
| flip-wording-4b | Turns the reader's flaw sentences into the offer's reason, keeping every fact and adding none | 14,513 reasons |
| flip-kinds-1 | Sorts each flaw sentence into the kinds the price is cut for: lock, parts, network lock, not genuine, damage, fault, battery or wear | 4,600 flaw sentences |
| flip-style-1b | Names the habits a buyer repeats in their offer messages: greeting, offer, sign-off and more | 2,833 made-up buyers (no real person's messages) |

Each was picked on validation data by a rule written before it answered, then scored on data it never trained on. A difference counts only when McNemar's test says it's significant. The training data isn't published. [MODELS.md](MODELS.md) says how each model was trained and tested, lists the earlier rounds, and gives each file's SHA-256 fingerprint.

### The checks

Every AI answer goes through plain-code checks before you see it:

- **Shape:** the agreed JSON shape and allowed values, within length limits.
- **Facts:** no number the inputs don't contain; no claim about what comes with the item (box, charger, cable, case...) or its condition (new, working, battery, scratches) that the inputs don't back; nothing that contradicts the item (another model, colour, storage size or edition).
- **Quotes:** every flaw a reading quotes must be in the listing word for word (a seller's typos aside), a flaw the seller denies ("no scratches") is dropped, and "no offers" counts only in words that say it.
- **Safety:** no price but the offer, no contact details, no paying off the platform, no made-up story about you, no promise to collect or pay cash that your own messages don't make, and nothing about how the damage happened that the listing doesn't say.
- **Manners (AlertFlip's rules):** no asking about iCloud or locks before the seller replies, no paying before collecting, no compliments, no "as agreed" about a talk there hasn't been, at most two questions, no emojis unless you use them, and nothing you removed from your style.
- **Typos:** what people type is read with slips allowed ("few scraches", "baterray 88"), but a real word is never read as a typo ("cash" isn't "case"). Of 3,195 typos of the words the checks look for, 91% are read.

An answer that fails gets one more try. A message first gets a free one on Gemma 3 4B, told what was turned down; then, with your key, Claude Sonnet 5.5 gets one try. If that fails too, the draft is marked "needs you". A model on your computer that's down is never swapped for the paid one. The checks catch an answer that's broken or made up, but they can't tell whether a believable answer is true: that's why you approve every draft.

Without your key, everything runs on your computer, and nothing catches a fact flip-wording-4b makes up (it made one up on 2.9% of 239 fresh listings).

## What it does

Five screens in a sidebar, light or dark. On first launch a welcome screen opens, and you can set up My style any time.

### AI message

For iPhones, Samsung phones and MacBooks (the title has to name one). Enter the listing's title, asking price and description, then:

- **Pick a price.** Code sets three: Offer lower (15% under asking, rounded down to a tidy number), Pay asking, and Offer more (5% over, rounded up, at least one step over). A slider moves it. The AI never picks a price.
- **Say the flaw** (Offer lower) or **Say you don't mind the flaw** (the other two): Yes to start with, then 1, 2 or 3 flaws, the worst first by how much each cuts the price, or all of them.
- **My style** On or Off. Off writes the default way, and a message you approve then isn't learned from.
- **Write my message.** flip-reader-5 reads the listing, flip-wording-4b words the reason, and code writes the message around it from your own sentences. With your key, Claude Haiku 5.5 then checks the reason. A fix from Claude Sonnet 5.5 replaces it only if you haven't edited the message and the message with the fix passes every check.
- The screen shows what was read, who wrote and checked what, the time and the cost, and **Why**, step by step. A seller's "no offers" shows as a note: it never changes the offer.
- **Rewrite.** Gemma 3 4B rewords the message on your computer, keeping the price, the facts and the checked reason word for word. Claude Sonnet 5.5 (paid) does it when Gemma 3 4B's tries fail the checks. Without Gemma 3 4B, nothing is sent to Claude in its place: Rewrite says it couldn't run, and your message stays as it was.
- **Copy & approve** copies the message and records what you sent, which then joins the messages My style learns from. **Check the UK price** sends the listing, with the flaws already read, to the price screen.

A listing is written as one you collect and pay cash for, unless it says it's posted, and cash isn't offered where the listing says no cash. Before you have past messages, the messages follow the AlertFlip app's own. For a made-up iPhone 14 Pro listed at £250 whose listing says "Battery Health: 80%":

- Offer lower, moved to £235: *Hi, would you take £235 cash for it? I'm offering that because the battery health is 80%. I can come and collect.*
- Pay asking: *Hi, is this still available? I'll pay the full £250 cash and can come and collect. Could you hold it for me?*
- Offer more, at code's £265: *Hi, I'll pay £265 cash if you take the listing down and sell it to me. I can come and collect.*

The reason uses only the seller's words, with their story cut to the flaw ("I dropped it and cracked the back" gives "cracked the back"). A battery health of 85% or less is a flaw, and so is a battery that's been replaced. When no model can read the listing, code reads it alone, and then misses wording it has no list for ("hinge is stiff").

### AI UK price estimate

A title and description in, a UK price out, for iPhones, Samsung phones and MacBooks:

1. The AlertFlip prices API gives the middle price of clean UK sales of the same model and size, with the cheapest quarter left out, as those often hide flaws.
2. flip-reader-5 reads the flaws (Gemma 3 4B when it isn't installed, code when neither is). With your key, Claude Sonnet 5.5 reads again when a model's reading fails code's checks.
3. flip-kinds-1 sorts each flaw into a kind: lock, parts, network lock, not genuine, damage, fault, battery or wear. Code's rules sort the title and any sentence it can't. A carrier named for the phone counts as a network lock unless the listing says it's unlocked or works on any network. That's buyer-safe on purpose: a locked phone you overpaid for costs more than an offer 4-16% lower.
4. Code cuts the price for each kind, by amounts measured on UK listings of the same kind of item: iPhones on iPhones, Samsungs on Samsungs, MacBooks on MacBooks. Damage is cut by how bad it is (minor, moderate or severe) and how pricey the model is, a worn battery by how low its health is, and a locked or for-parts one is priced at what for-parts ones sell for.
5. How bad the damage is: code reads it, and with your key Claude Haiku 5.5 reads it too, sent the title, the first 1,500 characters of the description and the flaw sentences, never a price. When they disagree, Claude Sonnet 5.5 decides. Judging 764 damaged listings this way cost about £0.29. Without a key, code judges alone.

The screen shows each kind of flaw with its own cut, and who read and sorted the flaws.

**Free UK prices.** UK prices for iPhones, Samsung phones and MacBooks work with no key. With no `PRICES_KEY` in `.env`, FlipAssist asks the AlertFlip prices API for its free UK prices. They're refreshed about monthly: once a model's sales are a month old, the next ask checks them again. The screen says when a price is a free one and when its sales were last checked, and warns you when they're over a month old and couldn't be checked again. Each ask sends the title, the kinds of flaw and the size, and no key. The description stays on your computer, apart from the model details it adds to a title that has none. When the free prices are busy, the screen says when to try again. `FLIP_PUBLIC_PRICES=off` in `.env` turns them off. Your own `PRICES_URL` and `PRICES_KEY` still work as before.

### List on eBay

For iPhones only. Enter which iPhone, your notes from looking at it and up to 8 photos, and you get a checked eBay draft to copy into eBay:

- **Code fills what the catalogue knows** (every iPhone from the SE to the 17): the title, within eBay's 80 characters, eBay's category (Mobile & Smart Phones) and its fields in eBay's own words, starting with the four it won't list a phone without: Brand, Model, Storage Capacity and Colour. eBay's lists come from its Taxonomy API, and each colour maps to one of eBay's 16 plain colours (Midnight is Black).
- **Code sets eBay's condition** from your notes: For parts or not working for a fault, New or Opened - never used only when the notes back it, Used otherwise. A crack or scratch on its own is wear, not a fault.
- **The writing.** flip-reader-5 and code pull the facts from your notes: each flaw, the battery, the network, what's in the box, what works, repairs. Claude Haiku 5.5 gets only that list, never the notes, and phrases the condition note and description. Code checks every fact made it in, and Claude Sonnet 5.5 rewrites a draft that fails the checks or leaves a fact out. Without a key, Gemma 3 4B writes it from your notes.
- It's written from your title and notes alone, never the original seller's description: on eBay you're the seller, so it says only what you checked. A field eBay needs that nobody knows is left for you.

### My style

- **Set up my style:** reply to 6 listings the way you'd message their sellers, each showing one habit (how you mention flaws, your plain offer, paying full price...). Nothing gets trained: code learns from your own messages.
- **The style card and the phrasebook:** code works out your greeting, length, questions, emojis and what you mention (habits in 40% or more of your messages), and the sentences you've written in at least two (your opener, your offer under, at or over asking, your closing).
- **flip-style-1b** reads your messages in the background when they change, never while drafting. Code checks the sign-off it names against your messages (in at least 2 of them and 40%), and only that fills a gap in code's card.
- **Your nearest past messages** for the same kind of deal, found by meaning (MiniLM embeddings in Chroma, on your computer), set what a message may promise, such as paying cash or collecting, and are the examples an AI is shown when it writes.
- Everything it learned is listed, each thing yours to remove: a removed one is never written again, and a draft that writes it fails the checks. The messages it learns from are listed too, each yours to delete. Redo setup replaces your last setup's answers.

### Home

- **Done by the models:** every successful output across the models, paid ones too, the cost per 100 drafts, the number of drafts, and how many you edited before sending.
- **Running:** Ollama and each model with its job (or, for one that isn't installed, what does its job instead), Claude Haiku 5.5 and Claude Sonnet 5.5 and what each does, the AlertFlip prices API (the free UK prices, your own, or off), and the API key.
- **Who did the work:** each model by job, with its tries, how many passed and what they cost.

## Results

Each model was scored on data it never trained on. Keys were labelled by Claude agents under written rules and checked by a second labeller who couldn't see the first one's answers (kappa 0.95 for the reader); the judges were Claude, blind to who wrote each answer.

| Part | Test | Result | Compared with |
|---|---|---|---|
| flip-reader-5, finding damage | 312 damaged UK listings | 305 found: iPhone 96.4%, Samsung 99.1%, MacBook 97.8% | – |
| flip-reader-5, finding every flaw | 5,032 listings, 3,162 flaws in a double-checked key | 95.3% found, 18 false alarms (99.4% precision) | – |
| flip-kinds-1, sorting flaws for the price | 400 sealed flaw sentences | price cut wrong on 3.8% | code's rules: 17.5% |
| flip-kinds-1, two fresh tests | 181 and 305 flaw sentences | 3.9% and 8.2% | code's rules: 18.8% and 20.0% |
| The offer's reason: flip-wording-4b, Haiku's check, Sonnet's fix | 239 fresh listings | 94-99% sendable by taste: 93.7% to strict judges, 98.7% with no fact added or changed | flip-wording-4b alone: 90.8% and 97.1% |
| How bad the damage is: code and Haiku, Sonnet on a split | 299 fresh UK listings, three blind checkers | 93.3% right | – |
| flip-style-1b, the hard style test | 40 made-up buyers, 189 habits | 182 found, 6 wrong, 3 invented | plain Gemma 3 4B: 146, 28, 230 |
| flip-style-1b, a fresh test | 40 new made-up buyers, 136 habits | 131 found, 0 wrong, 5 invented | plain Gemma 3 4B: 108, 10, 276 |
| Code's offer messages, fine to send as is | made-up listings, three kinds of buyer | new user 95%, messages that repeat 65%, chatty 100% | AI-written: 35%, 49%, 63% |

List on eBay's writers, judged blind by two judges on 40 real UK iPhones, as the app shows them:

| Writer | Postable as is | Says something the notes don't | Leaves a note out | Score (1-5) | Per listing |
|---|---|---|---|---|---|
| **flip-reader-5's facts, Claude Haiku 5.5 phrasing them, Sonnet if it fails (in use)** | **95%** | **2%** | **5%** | **4.59** | **0.040p** |
| Claude Haiku 5.5 reading the notes itself, Sonnet if it fails | 90% | 2% | 26% | 4.45 | 0.036p |
| Claude Sonnet 5.5 alone | 90% | 8% | 10% | 4.64 | 0.289p |
| flip-reader-5's facts, Gemma 3 4B phrasing them, Sonnet if it fails | 69% | 18% | 8% | 3.98 | 0.153p |

Gemma 3 4B made up marks even from the checked facts, so Sonnet rewrote 22 of its 40 drafts, which made it the dearest way.

## Run it on a Mac

Needs Python 3.11 or newer, Node.js 22 or newer and [Ollama](https://ollama.com).

```bash
python3.11 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt    # the API's Python, once
.venv/bin/pytest                # the Python tests
brew install ollama
ollama serve                    # leave this running in its own terminal (or open the Ollama app)
ollama pull gemma3:4b           # Gemma 3 4B, about 3.4 GB
launcher/get-models.sh          # FlipAssist's four models, about 10 GB
launcher/build.sh               # builds the app and the launcher, puts FlipAssist.app in ~/Applications
```

Then open **FlipAssist** from Applications, Spotlight or the Dock. On first launch it makes `.env` with this computer's own API key; add your Anthropic key there if you have one ([Keys and settings](#keys-and-settings)).

To work on the screens, run the API and the front end's dev server in two terminals instead. The dev server adds the API key from `.env` on the way, so the key never reaches the browser; make `.env` first, as in [Keys and settings](#keys-and-settings).

```bash
.venv/bin/uvicorn flip.api:app --port 8000      # the API: its docs at http://127.0.0.1:8000/docs
cd frontend && npm install && npm run dev       # the screens: open http://127.0.0.1:5173
```

### The launcher

FlipAssist opens like any Mac app, in its own window with no browser around it (`launcher/`, Electron and TypeScript):

1. A launch screen starts what isn't running already: Ollama, with its prompt cache off (it kept up to 8 GB of older prompts in memory), and the API, from the repo's own Python. What's already running is used as it is.
2. flip-wording-4b and then flip-reader-5 are loaded straight away, so the first draft doesn't wait. The reader goes last because, when only one fits in memory, Ollama keeps the newest, and every draft reads first. Gemma 3 4B loads in the reader's place when the reader isn't there; otherwise it loads when it's first asked, as three models don't stay loaded together on a 16 GB Mac.
3. The launch screen names the models Ollama has and, for any of FlipAssist's own that's missing, what does its job instead. Without Ollama it says code does the models' work. A fault while starting shows there too.
4. The window shows the built app at `app://flipassist/`. Its calls to `/api/...` go to the API through the launcher, which adds the key from `.env`: the page never sees it, and no other program on the Mac can borrow it.
5. Quitting stops only what the launcher started. Logs are in `~/Library/Logs/FlipAssist`.

The launcher needs the repo's Python environment (the first command above). Without it, the launch screen says so and gives the command.

### Getting the models

FlipAssist's four models are on the repo's GitHub release `models-v1`, not in git. `launcher/get-models.sh` downloads them, checks every part and each whole model file against the version that was tested, and adds each to Ollama. It needs about 13 GB free while it runs. A model Ollama already has as that version is skipped, and a download that stops part-way is kept in `~/Library/Caches/FlipAssist-models`, so running it again carries on. If the release or a file on it can't be downloaded, it stops and says which, and the models it added before that stay.

In a folder downloaded as a ZIP, or a fork's clone (GitHub doesn't copy releases), name the repo: `launcher/get-models.sh mohadilyes-git/FlipAssist-AI`. Without the models, FlipAssist still runs: Gemma 3 4B and code do their jobs ([models/README.md](models/README.md)). They're modified versions of Gemma 3 4B, under the Gemma Terms of Use ([models/NOTICE](models/NOTICE)).

To make the release, on a Mac with the four models in Ollama and the code pushed: `launcher/upload-models.sh mohadilyes-git/FlipAssist-AI`. It needs GitHub's gh tool, logged in (`brew install gh`, then `gh auth login`), and uploads one model at a time, so it needs room for only one model's parts (about 2.5 GB). Or `launcher/package-models.sh <an empty folder with about 11 GB free>` makes the same files, to upload to a release tagged `models-v1` by hand. Both refuse a model, or a Modelfile, that isn't the version that was tested.

## Run it on Windows

Built and tested on a Mac, not yet run on a Windows PC. It's the same app, API and models; what differs is where things live, all in `launcher/src/parts.ts`:

- The window has Windows' own title bar, and the menu bar stays hidden until Alt is pressed.
- Ollama is looked for in your Programs folder (or Program Files). The API starts from `.venv\Scripts\python.exe -m uvicorn` in UTF-8 mode, and quitting ends each one's whole process tree.
- Logs go to `%LOCALAPPDATA%\FlipAssist\logs`.
- Photos are converted by Pillow, and HEIC by pillow-heif, where a Mac uses its built-in sips. `requirements.txt` installs both on Windows only.

To set it up:

1. Install Python 3.11 (tick "Add python.exe to PATH"), Node.js 22 or newer, Git for Windows (git-scm.com), Ollama, and the Microsoft Visual C++ Redistributable (x64) if the PC doesn't have it (aka.ms/vs/17/release/vc_redist.x64.exe). Open Ollama once.
2. Clone the repo somewhere OneDrive doesn't sync (C:\FlipAssist, say), and put your `.env` in it if you have one. From a ZIP download or a fork's clone, add `-Repo mohadilyes-git/FlipAssist-AI` to the command in step 3, so it finds the models' release.
3. In PowerShell, in the repo folder: `powershell -ExecutionPolicy Bypass -File launcher\windows-setup.ps1`. It sets up the Python environment, downloads Gemma 3 4B (about 3.4 GB) and FlipAssist's four models (about 10 GB, each checked against the version that was tested), and builds FlipAssist into your Programs folder, with a Start menu and a desktop shortcut.

After a change, `powershell -ExecutionPolicy Bypass -File launcher\build.ps1` builds it again. Step 3 needs about 13 GB free on C: while it adds the models. If it stops, run it again: a model Ollama already has is skipped, and within a run a dropped download carries on where it stopped (up to 5 tries, 10 s apart). If the release or a file on it can't be downloaded, it stops before building and says what it couldn't get. Its options:

- `-Models D:\FlipAssist-models`: a folder made on a Mac by `launcher/export-models.sh /Volumes/USB/FlipAssist-models` on an ExFAT USB drive, instead of downloading the 10 GB.
- `-NoModels`: build it without them (Gemma 3 4B and code do their jobs).
- `-Repo owner/name` or `-Tag`: another repo's release, or another release.

Behind a proxy, set `HTTPS_PROXY`: the model files come with curl.exe, which doesn't read Windows' proxy settings. Drafting speed depends on the PC: a Mac runs the models on its own graphics, and a PC does that with a recent graphics card. Without one they run on the processor, and a draft takes longer.

## Keys and settings

Nobody's keys are in the repo: `.env` is never uploaded (`.gitignore`). The app makes `.env` on first launch with this computer's own `FLIP_API_KEY`. To make it by hand: `cp .env.example .env`, then paste a random key of 32 characters or more from `.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(32))"`.

Claude runs on your own key, and Anthropic bills you for what you use. Without it, everything runs on your computer, and nothing catches a fact flip-wording-4b makes up. UK prices need no key: they're the AlertFlip prices API's free ones unless you set your own.

| Setting in `.env` | What it does | When it's not set |
|---|---|---|
| `ANTHROPIC_API_KEY` | Your Claude key (console.anthropic.com), for every Claude step above | Everything runs on your computer |
| `FLIP_API_KEY` | The key every caller of the API sends in an `X-API-Key` header, 32 characters or more | The API refuses every call (the app makes one) |
| `PRICES_URL`, `PRICES_KEY` | Your own AlertFlip prices API and its key, for the UK price estimate. `PRICES_URL` with no key is asked the free way. A `PRICES_KEY` with no `PRICES_URL` asks nothing: the key is never sent to the free UK prices' address | The free UK prices: iPhones, Samsung phones and MacBooks, refreshed about monthly |
| `FLIP_PUBLIC_PRICES` | `off` turns the free UK prices off; your own `PRICES_URL` and `PRICES_KEY` still work | On whenever there's no `PRICES_KEY` |
| `USD_TO_GBP` | The dollar-to-pound rate the cost meter uses | 0.80 |
| `FLIP_READER_MODEL` | The listing reader | flip-reader-5; empty: Gemma 3 4B reads |
| `FLIP_WORDING_MODEL` | The model that words the offer's reason | flip-wording-4b; empty: code words it |
| `FLIP_WORDING_CHECK`, `FLIP_WORDING_FIX` | The reason's check and fix | claude-haiku-5-5 and claude-sonnet-5-5; empty turns one off |
| `FLIP_KINDS_MODEL` | The flaw sorter for the UK price | flip-kinds-1; empty: code's rules sort |
| `FLIP_STYLE_AI` | The style reader | flip-style-1b; empty: code alone; `gemma3:4b`: plain Gemma 3 4B |
| `FLIP_LISTING_WRITER` | List on eBay's writer: `notes` has Claude Haiku 5.5 read your notes itself; `gemma` has Gemma 3 4B write on your computer | Claude Haiku 5.5 phrases flip-reader-5's facts (Gemma 3 4B with no key) |
| `FLIP_BACKUP_MODEL` | The paid backup | claude-sonnet-5-5 |
| `FLIP_API_URL` | Where the front end's dev server sends API calls | http://127.0.0.1:8000 |
| `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` | Your eBay developer app's production keys, only to ask eBay UK for its fields again | Drafting never needs them |

## The API

`flip/api.py` (FastAPI) is what the screens call, and what the AlertFlip phone app is to call from a server function, so the key never sits in the phone app ([Planned](#planned)). Run it with `.venv/bin/uvicorn flip.api:app --port 8000`; every endpoint is described at http://127.0.0.1:8000/docs.

| Endpoint | What it does |
|---|---|
| `GET /health` | No key needed, none shown. Whether Ollama and the keys are set, how UK prices are asked (`prices_mode`: `public` for the free UK prices, `key` for your own, `off`, or `no url` for a `PRICES_KEY` with no `PRICES_URL`), which models Ollama has, and who does each job: the paid backup, the reason's check and fix, and List on eBay's writer and reader |
| `POST /messages/draft` | Reads the listing, then drafts the offer at code's price or `offer`. `kind` is `lower`, `asking` or `more`; `mention` says the flaw or good condition; `flaws_said` (1, 2, 3 or `"all"`) picks how many flaws, worst first; `check_later` leaves the reason's check for the next endpoint. Returns the message, who wrote it, the "no offers" note, what was read, `reason_from`, every attempt with its seconds and cost, and a draft id |
| `POST /messages/check-reason` | The second step of a draft made with `check_later`: Claude Haiku 5.5 checks the reason, Claude Sonnet 5.5 fixes one it flags, and the fix goes in only if the message with it passes every message check |
| `POST /listings/draft` | Form fields (`title`, `notes`) and up to 8 photos in, the eBay draft out. iPhones only |
| `POST /prices/estimate` | A listing's UK price with its flaws cut, from the AlertFlip prices API. The description is read for flaws unless `flaws` (with `read_by`) are sent. A free price says so (`public`), with when its sales were last checked (`checked_at`) and whether they're older (`stale`) |
| `POST /drafts/{id}/approve` | What you actually sent or listed, so the results can count how often a draft was right as it was. An approved message joins the messages your style learns from |
| `GET /stats` | The cost meter: drafts, outputs made on this device against all outputs, cost per 100 drafts, how often a draft was edited, and each model's tries, passes and cost by job |
| `GET /style` | The style card, the phrasebook, and everything it puts in a message, each with whether you still use it |
| `POST /style/learned` | Remove one thing it learned, or put it back (`key`, `used`) |
| `PUT /style/setup` | Your setup answers, in place of your last setup's. Drafts you approved and a CSV stay |
| `GET`, `POST /style/messages`, `DELETE /style/messages/{id}` | The messages it learns from: list them, add one or many (`title`, `price`, `text`), or delete one. The next draft already uses what you added |

- **Who can call it.** It answers only on this machine (127.0.0.1) unless it's put online on purpose. Every endpoint but `/health` and the `/docs` pages needs `FLIP_API_KEY` in an `X-API-Key` header. A key under 32 characters, like the example file's empty one, counts as none.
- **Turned away before it's read.** A request without the key, or bigger than its endpoint takes (1 MB, or 121 MB for 8 photos), is refused before any of it is read.
- **Bad input is refused before anything runs:** an unknown kind of offer, a price that isn't one (or is under £1), an offer that doesn't fit its kind, a title that names no iPhone, Samsung phone or MacBook, and a file that isn't a photo. A photo is known by its bytes (JPEG, PNG, HEIC or WebP), not its name, and one with more pixels than any camera takes is refused before it's converted.
- **A reading sent back is held to the listing.** `reading`, the listing's reading from the draft before, is checked like any model's reading; one that fails is read again.
- **It never sends or lists anything itself.**

```bash
curl -s http://127.0.0.1:8000/messages/draft -H "X-API-Key: $FLIP_API_KEY" -H "Content-Type: application/json" \
  -d '{"listing": {"title": "iPhone 13 128GB", "asking_price": "220", "description": "Black dot on the screen"}, "mention": true}'
```

## Command-line tools

```bash
.venv/bin/python -m flip.draft testset/items.example.json --mode local    # draft eBay listings for test items
.venv/bin/python -m flip.message --learn                                   # learn your past messages from a CSV
.venv/bin/python -m flip.message "iPhone 13 128GB Midnight" --asking 220 --marketplace facebook
.venv/bin/python -m flip.message "iPhone 13 128GB" --asking 220 --description "Broken back" --offer asking --mention yes
.venv/bin/python -m flip.ebay --refresh       # ask eBay UK for each category's fields again (needs the eBay keys)
.venv/bin/python -m flip.real_words           # rebuild data/real_words.json from macOS's dictionary
```

- `--mode local` uses only the models on your computer, `--mode api` only the paid backup, and the default `auto` tries your computer first. `flip.draft --limit N` drafts only the first N items.
- `--learn` reads your past messages from `testset/private/messages.csv` (`testset/messages.example.csv` shows the columns). The app keeps them in `private/style.sqlite3`, which never leaves your computer.
- `--offer` picks `lower` (the default), `asking` or `more`, and `--discount` how far under asking a lower offer goes (15 by default). `--mention yes` or `no` answers whether to say the flaw or good condition. `--longer` makes a message about twice the usual length, and `--previous "..."` makes that draft longer. `--writer template` or `ai` overrides who writes.

## Tests

```bash
.venv/bin/pytest                                  # 5,458 Python tests (12 more, for photos on Windows, need Pillow)
cd frontend && npm install && npm test            # 126 tests of the screens
cd launcher && npm test && npm run selftest       # 16 launcher tests, then the real window, end to end
```

The self-test opens the window, checks every kind of call (files, JSON, photo uploads, refused paths, copying, saved settings) without drafting or saving anything, and quits. Run it after `launcher/build.sh`.

[`evals/style/`](evals/style/) is the hard style test: 40 made-up buyers with messy habits, which you can score yourself. `.venv/bin/python evals/style/score.py --answers evals/style/answers-flip-style-1b.json` scores our saved answers (and the same with `answers-gemma3-4b.json`); `--ask gemma3:4b` asks a model in your own Ollama instead.

### Your own test set

Real items stay in `testset/private/`, which git never uploads: it holds other sellers' listing text and photos.

```bash
mkdir -p testset/private/photos
cp testset/items.example.csv testset/private/items.csv
```

1. Open `testset/private/items.csv` in Numbers or Excel and fill one row per item: the original title and description, your notes, the photo file names (photos go in `testset/private/photos/`; separate names with `;`), the prices, and the right answer for every field. Write a model the catalogue doesn't cover as `not in catalogue`.
2. Save it as CSV and run `.venv/bin/python -m flip.testset`. It writes `items.json`, or tells you the row with a typo.
3. Run `.venv/bin/python -m flip.score` to see how often code alone gets each field right, and `.venv/bin/python -m flip.draft` to draft them all.

Include a few items the catalogue doesn't have: the right answer for those is "needs you".

## Folders

- `flip/`: the Python code (`flip/api.py` is the API)
- `frontend/`: the screens, in React and TypeScript
- `launcher/`: FlipAssist as a Mac or Windows app (`build.sh` builds it on a Mac, `build.ps1` on Windows), and the scripts that get, upload, pack and export the models
- `models/`: what goes with the models on their release: its notes, and the Gemma notice and terms
- `evals/`: the hard style test (`evals/style/`)
- `data/`: the catalogue, eBay's fields and conditions, the price cuts, the models' prompts and rules, and the questions a message may ask (facts, not code)
- `tests/`: a test for every rule
- `testset/`: the example format for your own test set
- `private/`: the audit log, your style and everything else the app saves while it runs (never uploaded)

## Planned

- **The AlertFlip side:** a server function (on Supabase) that calls the API from the AlertFlip phone app.
- **Windows on a Windows PC:** the Windows version has been built and tested on a Mac only.
- **Measured results on your own test set:** how often each field is right with the models on your computer, with Claude, and with both; the cost per 100 listings; and minutes per listing by hand against with FlipAssist.
