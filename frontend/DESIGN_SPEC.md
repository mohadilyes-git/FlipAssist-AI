# FlipAssist web app: design spec

A web front end for FlipAssist. It drafts **offer messages to marketplace sellers** and **eBay listings** for a UK reseller.

It must look like the reseller's phone app, **AlertFlip**: the same fonts, colours, shapes and components. The tokens below come from AlertFlip's own theme file, `apppp/src/lib/theme.ts`, and its AI message sheet, `apppp/src/components/seller-message-sheet.tsx`.

- **Platform:** a Mac app window opened by a launcher (see §0), built as a web page inside it. It's mobile first: below 860 wide it's a single column with 16px side gutters, like the phone app; wider, the work screens use two columns.
- **Tech** (if you write code): React 19, TypeScript and Vite, with plain CSS and CSS variables (no UI library). Keep the logic files as they are: `src/api.ts`, `src/prices.ts`, `src/format.ts`.
- **Light and dark:** both, following the device setting.

---

## 0. It's a launcher: a Mac app window, not a website

FlipAssist runs on the reseller's own laptop, because its AI (Gemma) does. So it opens like an app:
1. A **FlipAssist icon** on the Desktop or in the Dock. Double-clicking it starts Gemma and the API.
2. While they start, a short **launch screen** shows the AlertFlip-style logo mark and "Starting FlipAssist…". Then it reads "Gemma is ready", or "Gemma isn't running: drafts use code and Claude Haiku only".
3. Then an **app window** opens, with no browser address bar or tabs:
   - about **1200×800**, resizable down to about 420 wide;
   - the traffic-light window buttons sit over the top-left of the app's background.

**Layout in the window:**
- **Message the seller** and **List on eBay** use **two columns** when the window is wide:
  - left: the listing, the price cards, the slider and the options;
  - right: the drafted message (or eBay draft), what was read, and the buttons.

  Below about 860 wide they stack into one column, exactly as on a phone.
- The **dock** keeps its floating pill shape, centred at the bottom of the window.
- **Home** puts the hero card and the two status cards in a row when there's room.

Everything else in this spec (tokens, components, wording, behaviour, API) stays the same in the window.

## 1. Design tokens (AlertFlip)

### Fonts
| Use | Font | Weight | Size |
|---|---|---|---|
| Screen title | Space Grotesk | 600 | 19px, letter-spacing −0.02em |
| Prices, big numbers | Space Grotesk | 700 | 19px (cards), 44px (hero) |
| Body, fields | Manrope | 600 | 14.5px, line-height 22px |
| Labels | Manrope | 800 | 11.5px |
| Small caps labels ("READ FROM THE LISTING") | Manrope | 800 | 10px, letter-spacing 0.1em, uppercase |
| Buttons | Manrope | 800 | 15px main, 14.5px second |
| Sub-lines, notes | Manrope | 700 | 12–12.5px |

### Colours
| Token | Light | Dark | Used for |
|---|---|---|---|
| bgTop / bgMid / bgBottom | #ffffff / #eef1f6 / #dbe3ef | #1c2331 / #12161f / #090c12 | page background: a radial gradient from the top centre (ellipse 120% × 90%, stops at 0%, 52% and 100%) |
| surfaceCard | #ffffff | #161b26 | cards |
| sheetFill | #f7f9fc | #161b26 | the slider thumb's ring |
| textPrimary | #0e1116 | #eef2f8 | text |
| textSecondary | rgba(14,17,22,.5) | rgba(255,255,255,.6) | sub-lines, gaps |
| textLabel | rgba(14,17,22,.42) | rgba(255,255,255,.48) | field labels |
| textBody | rgba(14,17,22,.72) | rgba(255,255,255,.72) | paragraphs |
| textPlaceholder | rgba(14,17,22,.34) | rgba(255,255,255,.35) | placeholders |
| brand / accentFill | #2f6fed | #2f6fed / #4a86ff | the picked card's border, slider fill, main button |
| accentText | #2f6fed | #8fb4ff | links, active tab, icons |
| iconTile | rgba(47,111,237,.10) | rgba(74,134,255,.14) | the head's icon tile |
| pickedBg | rgba(47,111,237,.08) | rgba(74,134,255,.14) | the picked price card |
| ring | rgba(47,111,237,.12) | rgba(47,111,237,.12) | the 3px ring round the picked card |
| accentChip | rgba(47,111,237,.17) | rgba(74,134,255,.2) | an active chip and the active dock tab |
| surfaceField | rgba(14,17,22,.04) | rgba(255,255,255,.06) | inputs, the message box, the tips box |
| borderCard | rgba(14,17,22,.08) | rgba(255,255,255,.1) | card borders |
| borderField | rgba(14,17,22,.1) | rgba(255,255,255,.12) | input borders |
| track | rgba(14,17,22,.10) | rgba(255,255,255,.14) | the slider's empty track |
| positive / positiveTint | #137c4a / rgba(19,124,74,.12) | #4fd695 / rgba(52,199,123,.16) | "£35 under", "Ready", collect place |
| orange | #c2410c | #ff9f6b | "£15 over", "The seller says no offers" |
| warning / warningTint | #b06f0a / rgba(216,140,20,.12) | #f0aa3c / rgba(240,170,60,.16) | "Needs you", the "No offers" tag |
| negative / negativeTint | #be2828 / rgba(190,40,40,.08) | #ff7a7a / rgba(255,122,122,.1) | errors |
| surfaceDock | rgba(255,255,255,.85) | rgba(21,26,36,.88) | the floating tab bar, with an 18px backdrop blur |
| tabInactive | rgba(14,17,22,.4) | rgba(255,255,255,.45) | inactive tabs |
| slotBg / slotBorder | rgba(47,111,237,.06) / rgba(47,111,237,.4) | rgba(122,162,255,.09) / rgba(122,162,255,.45) | the "Add photo" slot (dashed) |
| ghostBorder | rgba(14,17,22,.14) | rgba(255,255,255,.14) | empty photo slots (dashed) |

### Gradients
- **Main button:** top to bottom, #2f6fed → #2760d8 (55%) → #1f52c4. Shadow 0 12px 28px rgba(28,71,168,.35).
- **Hero card:** 160°, #2f6fed → #1c47a8 (58%) → #12295f. Shadow 0 20px 44px rgba(28,71,168,.36).

### Radii
pill 999 · hero 26 · panel 22 · chip 20 · card 18 · button 16 · field 16 · price card 14 · thumb/photo slot 14 · icon tile 12 · tag 7.

### Shadows
- **Card:** 0 8px 22px rgba(25,50,105,.06).
- **Dock:** 0 18px 40px rgba(25,50,105,.18).
- **Slider thumb:** 0 4px 10px rgba(28,71,168,.35).

In dark mode the borders do the lifting and the shadows are nearly invisible.

---

## 2. Components

- **Screen head:** a 36×36 icon tile (radius 12, iconTile background, accentText icon), then the title (Space Grotesk 600 19px) with a sub-line under it (Manrope 700 12.5px, textSecondary). An optional link sits on the right.
- **Card:** surfaceCard, 1px borderCard, radius 18, padding 14, card shadow, 12px gap between children.
- **Field:** a label above (Manrope 800 11.5px, textLabel), then the input (surfaceField background, 1px borderField, radius 16, padding 13px 14px). A select has a small chevron.
- **Price card (one of three, in a row, 8px apart):**
  - **Shape:** radius 14, 1.5px border, padding 10px 11px.
  - **Lines:** label ("Offer lower", Manrope 800 11.5px, textSecondary), price (Space Grotesk 700 19px), gap ("£35 under", Manrope 800 11px).
  - **Picked:** pickedBg, a brand border, and a 3px ring outside it.
  - **Not picked:** a chip background with borderCard.
  - **Gap colour:** positive under asking, orange over it, textSecondary at "asking".
- **Price slider:** a 6px track, radius 999. Filled with brand up to the thumb, track colour after it. The 26px thumb is a brand circle with a 3px sheetFill ring and the thumb shadow. The touch area is 40px tall. The lowest and highest prices sit under the two ends (Manrope 800 11.5px, textSecondary). Tapping the track jumps there. It must work with a keyboard and a screen reader, with the price read out.
- **Chip:** min height 32, padding 6px 12px, radius 999, Manrope 800 12.5px. Active: accentChip background, brand border, accentText.
- **Main button:** height 52, radius 16, gradient, white Manrope 800 15px. Pressed: scale 0.985, opacity 0.94.
- **Second button:** height 52, radius 16, 1px border, card background, Manrope 800 14.5px, with an optional accentText icon.
- **Warn row:** a warning-triangle icon (14px) and text, both orange, Manrope 800 12.5px.
- **Tips box:** surfaceField, 1px borderCard, radius 14, padding 10px 12px. A small caps label, then tags (radius 7, chip background) and lines in Manrope 700 12.5px.
- **Badge:** "Ready" (positive on positiveTint) or "Needs you" (warning on warningTint). Pill-shaped, Manrope 800 11.5px.
- **Dock (the tab bar):** a floating pill fixed 18px from the bottom, centred, surfaceDock with blur, 1px borderCard, dock shadow, 6px padding. Each tab is about 92×54 with an 18px icon over a Manrope 800 11px label. The active tab gets an accentChip pill (radius 20) and accentText. Pages leave room under their content so the dock never covers the last button.

Icons are line icons, 2px stroke, rounded: sparkle (AI message), tag (eBay), gauge (home), warning triangle, camera.

---

## 3. Screens, in this order

### 3.1 Message the seller (the main screen), like AlertFlip's AI message sheet

From top to bottom:
1. **Head:** sparkle icon, **"AI message"**, sub-line **"Pick your price · we write the message"**.
2. **Card with the listing:**
   - "Listing title" (placeholder *iPhone 13 128GB Blue*);
   - "Asking price" (placeholder *£220*) and "Marketplace" side by side (Facebook, eBay, Vinted, Gumtree, Other);
   - "The seller's description" (4 rows, placeholder *Flaws, where to collect, "no offers"…*).
3. **Three price cards:** **Offer lower · Pay asking · Offer more**.
   - Each shows its price and the gap ("£35 under", "asking", "£15 over").
   - Before there's an asking price they show "–" and "enter a price".
   - Offer lower is picked to start with.
4. **Price slider** under the cards, for Offer lower and Offer more only, not for Pay asking. Rules in §4.
5. **Warn row "The seller says no offers":** only when Offer lower is picked and the listing's reading says no offers.
6. **Option chips on one wrapping line:** "Say the flaw" **My style · Yes · No**, then "Writer" **Auto · No AI · AI**.
7. **Before a draft:** the note "Code sets the price and checks every draft before you see it.", then the main button **"Write my message"**. It reads "Writing…" while waiting, and is disabled until there's a valid asking price.
8. **After a draft:**
   - **Message box:** min height 118. It's editable, and you can change anything before you send.
   - **Note under the box (orange):** the seller's own words, e.g. *The seller says: "Price is firm, no offers"*. Only shown when there are some.
   - **"Needs you" reasons (orange):** when no draft passed, e.g. *no answer passed the checks*. The message box is then empty with the placeholder "No draft passed the checks: write your own here."
   - **Question box:** a card for when the draft left the listing's flaw out, e.g. *The listing says "Broken back". Mention it as the reason for your offer?*, with the second buttons **"Yes, mention it"** and **"No"**. Either one redrafts.
   - **Link "Make it longer":** redrafts, keeping the text in the box and adding to it.
   - **Tips box:**
     - the label **READ FROM THE LISTING**;
     - tags for each flaw (plain), the collect place ("Collect: Leeds LS6", positive) and "No offers" (warning);
     - the line *"Your own sentences (no AI) · 1.6s · free · read by Gemma, on this Mac"*;
     - an expandable **"Why · 2 steps"** listing each attempt ("Gemma, on this Mac failed: the message leaves out what the listing says…", or "passed"), each with seconds and cost.
   - **Bottom buttons:** second **"Rewrite"** (sparkle icon) and main **"Copy & approve"**.
   - **After approving:** a green line, "Copied and saved: sent as drafted." or "Copied and saved: you changed it first."
9. **Errors:** a red box with the API's words, e.g. "FlipAssist's API isn't running: start it with .venv/bin/uvicorn flip.api:app" or "listing › asking_price: String should match pattern".

### 3.2 List on eBay, like AlertFlip's eBay screens

1. **Head:** tag icon, **"List on eBay"**, sub-line **"Your notes and photos · a checked eBay draft"**.
2. **Photo grid, 4 columns, 8 square slots:**
   - Filled slots show the photo with a round × to remove it, and the first one says **"Cover"**.
   - The next slot is **"Add photo"**: camera icon, dashed slotBorder, slotBg.
   - The rest are dashed ghost slots.
   - You can drop photos anywhere on the grid. They can be JPEG, PNG, HEIC or WebP, up to 8.
3. **Card:**
   - "The seller's title" (placeholder *iphone 13 128gb unlocked boxed*);
   - "The seller's description";
   - "Your notes from looking at it" (placeholder *battery 87%, light scratch on the back, screen perfect, boxed, no charger*).
4. **Main button "Draft listing"**, reading "Drafting…" while waiting.
5. **Result card:**
   - a badge plus "2 photos read";
   - orange lines for the reasons and warnings (e.g. *fill in: colour*);
   - an editable **"eBay title"** with a counter like "30/80" (eBay's limit is 80);
   - rows: Condition, Condition note, Colour;
   - an editable **"Description"**;
   - an expandable **"Filled by code, no AI"** with rows for brand, model, storage, network, colour and the specs;
   - a tips line (*"Gemma, on this Mac · 4.2s · free"*) and **"Why"**.
   - The condition is shown by name: New, Opened – never used, Used, or For parts or not working. The colour reads "Unsure from the photos: check it" when the AI couldn't tell.
6. **Bottom buttons after a draft:** second **"Redraft"** and main **"Copy & approve"**. The copy holds the title, condition, condition note and description.

### 3.3 Home

1. **Head:** gauge icon, **"FlipAssist"**, sub-line **"Code first · AI on this Mac · paid AI only when it must"**, and a **"Refresh"** link on the right.
2. **Hero card (blue gradient):**
   - the small caps **DONE ON THIS MAC**;
   - a big **80%**;
   - a thin white rule;
   - four small stats: **0.303p** per 100 drafts · **50** drafts · **82%** ready · **0%** edited.
3. **Card "RUNNING"**, rows with a green or red dot:
   - Gemma, on this Mac: "Running", or "Not running: start it with ollama serve".
   - Claude Haiku (paid backup): "Ready if Gemma's answer fails a check", or "No key: local only".
   - API key: "Set", or "Missing: every draft is refused".
4. **Card "WHO DID THE WORK"**, a row per model, e.g. "Gemma, on this Mac: 36 of 50 passed · free" or "Claude Haiku (paid backup): 11 of 12 passed · 0.152p".
5. **Buttons:** second **"List on eBay"** and main **"Message a seller"**.

### 3.4 History (next)
A list of past drafts: the date, message or listing, who wrote it, the cost, and whether it was sent as drafted or edited. It needs one new endpoint, `GET /drafts`.

### Navigation
The dock has three tabs: **Message** (sparkle), **List on eBay** (tag) and **Home** (gauge). Each screen has its own address (#message, #listing, #home), so a refresh keeps you there. Message is the first screen.

---

## 4. Behaviour the design must keep

**Prices** are in pounds. They follow FlipAssist's rules, already in `src/prices.ts`:
- **Offer lower** starts 15% under asking, rounded down: whole pounds under £20, £5 steps from £20. £220 gives £185.
- **Pay asking** is the asking price. It has no slider.
- **Offer more** starts 5% over asking, rounded up to the step, and always at least one step over. £220 gives £235.
- **Steps:** £1 under £60, £5 under £1,000, £10 from £1,000.
- **Slider range for lower:** from £200 under asking (or a quarter under, whichever reaches further, never below one step) up to just under asking. £220 gives £20 to £215.
- **Slider range for more:** from just over asking up to £200 over (or 15% over, whichever reaches further).
- **Sliding after a draft** swaps the new price into the message and keeps every other word, including your edits.
- **Changing the asking price** resets the slid prices.

**Who wrote it**, in words:

| The API says | Show |
|---|---|
| template | Your own sentences (no AI) |
| gemma3:4b | Gemma, on this Mac |
| claude-haiku-5-5 | Claude Haiku (paid backup) |
| code | Code only |

A cost of 0 shows as **free**; any other cost shows like **0.009p**.

**Copy & approve** copies the text to the clipboard, then tells the API what was actually sent. If the browser blocks copying, the text stays on screen to copy by hand.

**Never, anywhere on the page:**
- send a message or list an item (the reseller does that in the marketplace);
- show or store the API key, which the dev server adds on the way to the API (`vite.config.ts`);
- make up a price other than these rules or the reseller's own slide.

---

## 5. The API it talks to

Every call goes to `/api/...` on the page's own server, which passes it on to FlipAssist's API with the key added. The full shapes are at http://127.0.0.1:8000/docs while the API is running.

**`POST /api/messages/draft`**
```json
{"listing": {"title": "iPhone 13 128GB Blue", "asking_price": "220.00", "marketplace": "facebook",
             "description": "Black dot on the screen, doesn't affect use. Collection only from Leeds LS6. Price is firm, no offers."},
 "kind": "lower", "offer": "150.00", "mention": true, "length": "usual", "previous": null, "writer": "auto"}
```
`kind` is "lower", "asking" or "more"; `mention` is true, false or null ("My style"); `length` is "usual" or "longer" (with `previous` set to the text on screen); `writer` is "auto", "template" or "ai". `offer` is the price picked on the slider. Until the API takes it, the page swaps the picked price into the drafted text.

The answer:
```json
{"draft_id": 47, "status": "ready", "message": "Hi, would you take £150 for it, given the black dot on the screen? Thanks.",
 "written_by": "template", "kind": "lower", "offer": "£150", "offer_pence": 15000,
 "note": "The seller says: \"Price is firm, no offers\"", "ask": null, "point": ["Black dot on the screen"], "mentioned": true,
 "questions": [], "reasons": [], "cost_pence": 0,
 "reading": {"flaws": ["Black dot on the screen"], "pickup": "Leeds LS6", "no_offers": "Price is firm, no offers",
             "read_by": "gemma3:4b", "attempts": [{"model": "gemma3:4b", "problems": [], "seconds": 1.4, "cost_pence": 0}]},
 "attempts": [{"model": "template", "problems": [], "seconds": 0.0, "cost_pence": 0}]}
```

**`POST /api/listings/draft`** (a form: `title`, `description`, `notes`, and up to 8 `photos` files)
```json
{"draft_id": 48, "status": "needs you", "ebay_title": "Apple iPhone 13 128GB Unlocked", "condition_id": "3000",
 "condition_note": "Light scratch on the back. Battery health 87%.", "description": "Apple iPhone 13 128GB, unlocked…",
 "colour": "unsure", "filled_by_code": {"brand": "Apple", "model": "iPhone 13", "storage": "128GB", "network": "Unlocked",
 "specs": {"Screen Size": "6.1 in"}}, "warnings": [], "reasons": ["fill in: colour"], "photo_count": 0,
 "attempts": [{"model": "gemma3:4b", "problems": [], "seconds": 4.2, "cost_pence": 0}], "cost_pence": 0}
```

**`POST /api/drafts/{draft_id}/approve`**: send `{"sent": "the text actually sent"}`, get back `{"draft_id": 47, "edited": false, "at": "2026-08-18T20:36:33+00:00"}`.

**`GET /api/stats`**
```json
{"drafts": 50, "ready": 41, "needs_you": 9, "done_on_this_mac": 0.8, "cost_pence": 0.152, "cost_per_100_drafts_pence": 0.303,
 "approved": 1, "edited_before_sending": 0,
 "models": [{"model": "gemma3:4b", "attempts": 50, "passed": 36, "cost_pence": 0}, {"model": "claude-haiku-5-5", "attempts": 12, "passed": 11, "cost_pence": 0.152}]}
```

**`GET /api/health`**
```json
{"local_model": "gemma3:4b", "local_running": true, "api_model": "claude-haiku-5-5", "api_key_set": true, "flip_api_key_set": true}
```

**Errors** come as `{"detail": "missing or wrong X-API-Key"}`, or as a list of refused fields: `{"detail": [{"loc": ["body", "listing", "asking_price"], "msg": "…"}]}`. Show them in words: `src/api.ts`'s `explain()` already does this.
