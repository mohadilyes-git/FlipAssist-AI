import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App, markShell, SETUP_DONE, THEME } from "../App";
import type { ListingDraft, MessageDraft, Style } from "../api";
import { ListingScreen } from "../screens/ListingScreen";
import { MessageScreen } from "../screens/MessageScreen";

const DRAFT: MessageDraft = {
  draft_id: 7, status: "ready", written_by: "template", kind: "lower", offer: "£185", offer_pence: 18500,
  message: "Hi mate, would you take £185 cash, given the black dot on the screen? Can collect from Leeds LS6 today.",
  note: 'The seller says: "Price is firm, no offers"', ask: null, point: ["Black dot on the screen"], mentioned: true,
  questions: [], reasons: [], warnings: [], cost_pence: 0,
  attempts: [{ model: "template", problems: [], seconds: 0.001, cost_pence: 0 }],
  reading: { flaws: ["Black dot on the screen"], pickup: "Leeds LS6", no_offers: "Price is firm, no offers",
    read_by: "gemma3:4b", attempts: [{ model: "gemma3:4b", problems: [], seconds: 1.2, cost_pence: 0 }] },
};
const STYLE: Style = { count: 14, traits: [{ k: "Opens with", v: "'Hi mate'" }, { k: "Length", v: "about 12 words" }],
  phrases: [{ k: "Closing", v: "Cheers" }] };
const HEALTH = { local_model: "gemma3:4b", local_running: true, api_model: "claude-haiku-5-5", api_key_set: true,
  flip_api_key_set: true };
const STATS = { drafts: 2, ready: 2, needs_you: 0, done_on_this_mac: 0.8, models: [], cost_pence: 0,
  cost_per_100_drafts_pence: 0, approved: 0, edited_before_sending: 0 };

type Answer = [number, unknown];
/** The API, pretend: each "METHOD /api/path" answers in turn, its last answer again and again. */
function serve(routes: Record<string, Answer | Answer[]>) {
  const queues = Object.fromEntries(Object.entries(routes).map(([route, answers]) =>
    [route, typeof answers[0] === "number" ? [answers as Answer] : [...(answers as Answer[])]]));
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const queue = queues[`${init?.method ?? "GET"} ${url}`];
    if (!queue) throw new TypeError(`nothing serves ${init?.method ?? "GET"} ${url}`);
    const [status, body] = queue.length > 1 ? queue.shift()! : queue[0];
    return { ok: status < 400, status, json: async () => body };
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
const sent = (fetch: ReturnType<typeof serve>, route: string, n = 0) =>
  JSON.parse(String(fetch.mock.calls.filter(([url, init]) => `${init?.method ?? "GET"} ${url}` === route)[n][1]?.body));

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:photo");
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = "";
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("AI message", () => {
  async function draft(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByLabelText("Listing title"), "iPhone 13 128GB Blue");
    await user.type(screen.getByLabelText("Asking price"), "£220");
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    return screen.findByDisplayValue(DRAFT.message!);
  }

  it("waits for a title and a price, then shows the message, the seller's words and what was read", async () => {
    const fetch = serve({ "POST /api/messages/draft": [200, DRAFT] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    expect(screen.getByRole("button", { name: "Write my message" }).hasAttribute("disabled")).toBe(true);
    await draft(user);
    expect(screen.getByText('The seller says: "Price is firm, no offers"')).toBeTruthy();
    expect(screen.getByText("Black dot on the screen")).toBeTruthy();
    expect(screen.getByText("Collect: Leeds LS6")).toBeTruthy();
    expect(screen.getByText("The seller says no offers")).toBeTruthy(); // Offer lower is picked
    expect(screen.getByText("Your own sentences (no AI) · 1.2s · free · read by Gemma, on this Mac")).toBeTruthy();
    const body = sent(fetch, "POST /api/messages/draft");
    expect([body.listing.asking_price, body.offer, body.listing.marketplace]).toEqual(["220.00", "185.00", "facebook"]);
  });

  it("says so plainly when no draft passed the checks", async () => {
    serve({ "POST /api/messages/draft": [200, { ...DRAFT, status: "needs you", message: null, written_by: null,
      reasons: ["no answer passed the checks"] }] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await user.type(screen.getByLabelText("Listing title"), "iPhone 13");
    await user.type(screen.getByLabelText("Asking price"), "220");
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    expect(await screen.findByText(/^No draft passed · /)).toBeTruthy();
  });

  it("shows why, step by step", async () => {
    serve({ "POST /api/messages/draft": [200, DRAFT] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await draft(user);
    await user.click(screen.getByRole("button", { name: /Why · 2 steps/ }));
    expect(screen.getByText("Gemma, on this Mac passed")).toBeTruthy();
    expect(screen.getByText("1.2s · free")).toBeTruthy();
  });

  it("approves what you actually send, edits and all, and it joins your style", async () => {
    const fetch = serve({ "POST /api/messages/draft": [200, DRAFT],
      "POST /api/drafts/7/approve": [200, { draft_id: 7, edited: true, at: "now", saved_to_style: true }] });
    const user = userEvent.setup();
    const approved = vi.fn();
    render(<MessageScreen onApproved={approved} />);
    await user.type(await draft(user), " Cheers");
    await user.click(screen.getByRole("button", { name: "Copy & approve" }));
    expect(await screen.findByText("Copied and saved: you changed it first.")).toBeTruthy();
    expect(screen.getByText("Saved to your style")).toBeTruthy();
    expect(sent(fetch, "POST /api/drafts/7/approve").sent).toBe(DRAFT.message + " Cheers");
    expect(approved).toHaveBeenCalled();
    expect(await navigator.clipboard.readText()).toBe(DRAFT.message + " Cheers");
  });

  it("makes the message on screen longer, keeping your edits", async () => {
    const fetch = serve({ "POST /api/messages/draft": [[200, DRAFT], [200, { ...DRAFT, draft_id: 8 }]] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await user.type(await draft(user), " Cheers");
    await user.click(screen.getByRole("button", { name: "Make it longer" }));
    const body = sent(fetch, "POST /api/messages/draft", 1);
    expect([body.length, body.previous]).toEqual(["longer", DRAFT.message + " Cheers"]);
  });

  it("flips Make it longer to Make it shorter, and a rewrite keeps the length on screen", async () => {
    const LONGER = { ...DRAFT, draft_id: 8, message: DRAFT.message + " Is it unlocked? Does it come with a charger?" };
    const fetch = serve({ "POST /api/messages/draft": [[200, DRAFT], [200, LONGER], [200, { ...LONGER, draft_id: 9 }],
      [200, { ...DRAFT, draft_id: 10 }]] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await draft(user);
    await user.click(screen.getByRole("button", { name: "Make it longer" }));
    expect(await screen.findByDisplayValue(LONGER.message!)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Rewrite" }));
    const rewrite = sent(fetch, "POST /api/messages/draft", 2);
    expect([rewrite.length, rewrite.rewrite_of, rewrite.previous]).toEqual(["longer", LONGER.message, null]);
    await user.click(await screen.findByRole("button", { name: "Make it shorter" }));
    const shorter = sent(fetch, "POST /api/messages/draft", 3);
    expect([shorter.length, shorter.previous, shorter.rewrite_of]).toEqual(["usual", null, null]);
    expect(await screen.findByRole("button", { name: "Make it longer" })).toBeTruthy();
  });

  it("keeps your message when no new wording passes, and shows what's worth knowing", async () => {
    const warned = { ...DRAFT, warnings: ["The title says iPhone 15 Pro Max but the description says iPhone 14: check which it is"] };
    serve({ "POST /api/messages/draft": [[200, warned], [200, { ...DRAFT, draft_id: 8, status: "needs you", message: null,
      written_by: null, reasons: ["no answer passed the checks"] }]] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await draft(user);
    expect(screen.getByText(/The title says iPhone 15 Pro Max but the description says iPhone 14/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Rewrite" }));
    expect((await screen.findByRole("alert")).textContent).toBe("No new wording passed the checks, so your message is unchanged");
    expect(screen.getByDisplayValue(DRAFT.message!)).toBeTruthy();
  });

  it("asks before mentioning the flaw, and redrafts with your answer", async () => {
    const asked = { ...DRAFT, ask: 'The listing says "Black dot on the screen". Mention it as the reason for your offer?' };
    const fetch = serve({ "POST /api/messages/draft": [[200, asked], [200, DRAFT]] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await draft(user);
    await user.click(screen.getByRole("button", { name: "Yes, mention it" }));
    expect(sent(fetch, "POST /api/messages/draft", 1).mention).toBe(true);
    expect(screen.getByRole("button", { name: "Yes" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("says what the API refused", async () => {
    serve({ "POST /api/messages/draft": [422, { detail: [{ loc: ["body", "listing", "asking_price"], msg: "String should match pattern" }] }] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await user.type(screen.getByLabelText("Listing title"), "iPhone 13");
    await user.type(screen.getByLabelText("Asking price"), "220");
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    expect((await screen.findByRole("alert")).textContent).toBe("listing › asking_price: String should match pattern");
  });
});

describe("the price line", () => {
  it("moves a step at a time from the keys and swaps the new price into the message", async () => {
    serve({ "POST /api/messages/draft": [200, DRAFT] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await user.type(screen.getByLabelText("Listing title"), "iPhone 13 128GB Blue");
    await user.type(screen.getByLabelText("Asking price"), "220");
    const line = screen.getByRole("slider", { name: "Offer lower price" });
    const at = () => ["aria-valuemin", "aria-valuemax", "aria-valuenow", "aria-valuetext"].map((a) => line.getAttribute(a));
    expect(at()).toEqual(["2000", "21500", "18500", "£185"]); // £20 to £215, from £185
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    await screen.findByDisplayValue(DRAFT.message!);
    line.focus();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByDisplayValue(DRAFT.message!.replace("£185", "£180"))).toBeTruthy();
    await user.keyboard("{PageDown}");
    expect(line.getAttribute("aria-valuetext")).toBe("£155");
    expect(screen.getByText("£65 under")).toBeTruthy();
    await user.keyboard("{Home}");
    expect(line.getAttribute("aria-valuetext")).toBe("£20");
    await user.keyboard("{End}{ArrowRight}");
    expect(line.getAttribute("aria-valuetext")).toBe("£215"); // never past the end
  });

  it("has no prices to offer under £1", async () => {
    const user = userEvent.setup();
    render(<MessageScreen />);
    await user.type(screen.getByLabelText("Listing title"), "Free sofa");
    await user.type(screen.getByLabelText("Asking price"), "0.50");
    expect(screen.getAllByText("enter a price")).toHaveLength(3);
    expect(screen.getByRole("button", { name: "Write my message" }).hasAttribute("disabled")).toBe(true);
  });

  it("starts again from code's prices when the asking price changes", async () => {
    const user = userEvent.setup();
    render(<MessageScreen />);
    await user.type(screen.getByLabelText("Asking price"), "220");
    screen.getByRole("slider").focus();
    await user.keyboard("{Home}");
    await user.type(screen.getByLabelText("Asking price"), "0");
    expect(screen.getByRole("slider").getAttribute("aria-valuetext")).toBe("£1,870"); // 15% under £2,200
  });
});

describe("List on eBay", () => {
  const LISTED: ListingDraft = {
    draft_id: 3, status: "needs you", ebay_title: "Apple iPhone 13 128GB Midnight Unlocked", condition_id: "3000",
    condition_note: "Light scratch on the back.", description: "Apple iPhone 13 128GB in Midnight.", colour: null,
    colour_from: null,
    filled_by_code: { brand: "Apple", model: "iPhone 13", storage: "128GB", specs: { "Screen Size": "6.1 in" } },
    ebay_category: null, item_specifics: [],
    warnings: [], reasons: ["Fill in: colour"], photo_count: 2,
    attempts: [{ model: "gemma3:4b", problems: [], seconds: 9.5, cost_pence: 0 }], cost_pence: 0,
  };

  it("takes at most 8 photos and sends them with the form", async () => {
    const fetch = serve({ "POST /api/listings/draft": [200, { ...LISTED, colour: "Midnight", colour_from: "photos" }] });
    const user = userEvent.setup();
    const { container } = render(<ListingScreen />);
    const photos = Array.from({ length: 10 }, (_, n) => new File(["x"], `p${n}.jpg`, { type: "image/jpeg" }));
    await user.upload(container.querySelector("input[type=file]") as HTMLInputElement, photos);
    expect(screen.getAllByRole("img")).toHaveLength(8);
    expect(screen.getByText("Cover")).toBeTruthy();
    expect(container.querySelector("input[type=file]")).toBeNull(); // no "Add photo" slot once there are 8
    await user.type(screen.getByLabelText("The seller's title"), "iphone 13 128gb");
    await user.click(screen.getByRole("button", { name: "Draft listing" }));
    expect(await screen.findByDisplayValue(LISTED.ebay_title!)).toBeTruthy();
    expect(screen.getByText("Midnight (from the photos)")).toBeTruthy();
    const form = fetch.mock.calls[0][1]!.body as FormData;
    expect(form.getAll("photos")).toHaveLength(8);
    expect(form.get("title")).toBe("iphone 13 128gb");
  });

  it("leaves out a photo too big to send, or a file that isn't a photo, and says so", async () => {
    const user = userEvent.setup({ applyAccept: false });
    const { container } = render(<ListingScreen />);
    const big = new File(["x"], "huge.jpg", { type: "image/jpeg" });
    Object.defineProperty(big, "size", { value: 16 * 1024 * 1024 });
    const pdf = new File(["%PDF"], "invoice.pdf", { type: "application/pdf" });
    await user.upload(container.querySelector("input[type=file]") as HTMLInputElement,
      [big, pdf, new File(["x"], "ok.jpg", { type: "image/jpeg" })]);
    expect(screen.getAllByRole("img")).toHaveLength(1);
    expect(screen.getByRole("alert").textContent).toBe(
      "Left out: invoice.pdf isn't a JPEG, PNG, HEIC or WebP photo; huge.jpg is over 15 MB.");
  });

  it("shows the draft to check: what needs you, the condition by name, and what code filled", async () => {
    serve({ "POST /api/listings/draft": [200, LISTED], "POST /api/drafts/3/approve": [200, { draft_id: 3, edited: false,
      at: "now", saved_to_style: false }] });
    const user = userEvent.setup();
    render(<ListingScreen />);
    expect(screen.getByText("Your eBay draft shows here")).toBeTruthy();
    await user.type(screen.getByLabelText("The seller's title"), "iphone 13 128gb");
    await user.click(screen.getByRole("button", { name: "Draft listing" }));
    expect(await screen.findByText("Needs you")).toBeTruthy();
    expect(screen.getByText("Fill in: colour")).toBeTruthy();
    expect(screen.getByText("Used")).toBeTruthy();
    expect(screen.getByText("Unsure from the photos: check it")).toBeTruthy();
    expect(screen.getByText(`${LISTED.ebay_title!.length}/80`)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /Filled by code, no AI/ }));
    expect(screen.getByText("Screen Size")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Copy & approve" }));
    expect(await screen.findByText("Copied and saved: title, condition and description.")).toBeTruthy();
    expect(await navigator.clipboard.readText()).toContain("Condition: Used");
  });

  it("shows eBay's category and fields in eBay's words, yours to change, and copies them", async () => {
    const field = (name: string, value: string | null, required: boolean, source: string | null, options: string[] = []) =>
      ({ name, value, required, source, options });
    serve({ "POST /api/listings/draft": [200, { ...LISTED, ebay_title: "Apple iPhone 13 128GB Unlocked",
      ebay_category: { id: "9355", name: "Mobile & Smart Phones", path: "Mobile Phones & Communication" },
      item_specifics: [
        field("Brand", "Apple", true, "the catalogue", ["Apple"]),
        field("Model", "Apple iPhone 13", true, "the catalogue", ["Apple iPhone 13", "Apple iPhone 13 mini"]),
        field("Storage Capacity", "128 GB", true, "your title or notes", ["128 GB", "256 GB", "512 GB"]),
        field("Colour", null, true, null, ["Black", "Blue", "White"]),
        field("Network", "Unlocked", false, "your title or notes", ["Unlocked", "EE"]),
        field("Screen Size", "6.1 in", false, "the catalogue"),
      ] }],
      "POST /api/drafts/3/approve": [200, { draft_id: 3, edited: false, at: "now", saved_to_style: false }] });
    const user = userEvent.setup();
    render(<ListingScreen />);
    await user.type(screen.getByLabelText("The seller's title"), "iphone 13 128gb unlocked");
    await user.click(screen.getByRole("button", { name: "Draft listing" }));
    const fields = within(await screen.findByRole("region", { name: "eBay's fields" }));
    expect(fields.getByText("Mobile & Smart Phones")).toBeTruthy();
    expect(fields.getByText("eBay needs these")).toBeTruthy();
    expect((fields.getByLabelText("Model") as HTMLInputElement).value).toBe("Apple iPhone 13");
    expect((fields.getByLabelText("Storage Capacity") as HTMLInputElement).value).toBe("128 GB");
    expect(fields.getAllByText("from the catalogue")).toHaveLength(3);
    expect(fields.getByText("Unsure from the photos: check it")).toBeTruthy(); // eBay needs a colour nobody saw
    expect(screen.queryByText("Colour", { selector: ".rows .row-name" })).toBeNull(); // no second colour row
    await user.type(fields.getByLabelText("Colour"), "Black");
    expect(fields.getByText("your edit")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Copy & approve" }));
    expect(await screen.findByText("Copied and saved: title, condition, eBay's fields and description.")).toBeTruthy();
    const copied = await navigator.clipboard.readText();
    expect(copied).toContain("Category: Mobile & Smart Phones\nBrand: Apple\nModel: Apple iPhone 13\nStorage Capacity: 128 GB");
    expect(copied).toContain("Colour: Black\nNetwork: Unlocked\nScreen Size: 6.1 in");
  });

  it("keeps code's title when no answer passed, and says the colour wasn't drafted rather than unsure", async () => {
    serve({ "POST /api/listings/draft": [200, { ...LISTED, condition_id: null, condition_note: null, description: null,
      ebay_title: "Apple iPhone 14 Pro Max Unlocked", reasons: ["no answer passed the checks", "fill in: storage, colour"] }] });
    const user = userEvent.setup();
    render(<ListingScreen />);
    await user.type(screen.getByLabelText("The seller's title"), "iphone 14 pro max");
    await user.click(screen.getByRole("button", { name: "Draft listing" }));
    expect(await screen.findByDisplayValue("Apple iPhone 14 Pro Max Unlocked")).toBeTruthy();
    expect(screen.getAllByText("Not drafted")).toHaveLength(2); // condition and colour
    expect(screen.queryByText("Unsure from the photos: check it")).toBeNull();
  });
});

describe("the app", () => {
  const usual = { "GET /api/health": [200, HEALTH] as Answer, "GET /api/style": [200, STYLE] as Answer,
    "GET /api/stats": [200, STATS] as Answer };

  it("asks you to set up your style on first launch, and learns from the messages you paste", async () => {
    const fetch = serve({ ...usual, "GET /api/style": [[200, { count: 0, traits: [], phrases: [] }], [200, STYLE]],
      "POST /api/style/messages": [201, []] });
    const user = userEvent.setup();
    render(<App />);
    expect(screen.getByRole("heading", { name: "Set up your style" })).toBeTruthy();
    expect(screen.queryByRole("navigation")).toBeNull(); // no sidebar until it's done
    await user.click(screen.getByRole("button", { name: "Paste my messages" }));
    const learn = screen.getByRole("button", { name: "Learn my style" });
    expect(learn.hasAttribute("disabled")).toBe(true);
    const first = within(screen.getByRole("region", { name: "Message 1" }));
    await user.type(first.getByLabelText("Listing title"), "iPhone 12 64GB");
    await user.type(first.getByLabelText("Price"), "£150");
    await user.type(first.getByLabelText("Your message"), "Hi mate, would you take £125 cash? Cheers");
    await user.click(screen.getByRole("button", { name: "Learn from 1 message" }));
    expect(await screen.findByText("Learned from 1 message")).toBeTruthy();
    expect(screen.getByText("about 12 words")).toBeTruthy();
    expect(sent(fetch, "POST /api/style/messages")).toEqual(
      [{ title: "iPhone 12 64GB", price: "£150", text: "Hi mate, would you take £125 cash? Cheers" }]);
    await user.click(screen.getByRole("button", { name: "Start" }));
    expect(screen.getByRole("navigation")).toBeTruthy();
    expect(window.location.hash).toBe("#message");
    expect(localStorage.getItem(SETUP_DONE)).toBe("1");
  });

  it("goes through the 8 listings one at a time, sending only the ones you answered", async () => {
    const fetch = serve({ ...usual, "GET /api/style": [[200, { count: 0, traits: [], phrases: [] }], [200, STYLE]],
      "POST /api/style/messages": [201, []] });
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Reply to 8 listings" }));
    expect(screen.getByText("1 of 8")).toBeTruthy();
    expect(screen.getByText("Offer lower · £185")).toBeTruthy();
    await user.type(screen.getByLabelText("Your message to this seller"), "Hi mate, £185 given the crack?");
    await user.click(screen.getByRole("button", { name: "Next" }));
    for (let n = 2; n < 8; n++) await user.click(screen.getByRole("button", { name: "Skip" }));
    expect(screen.getByText("Offer lower · £125")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "See my style" }));
    expect(await screen.findByText("Learned from 1 message")).toBeTruthy();
    expect(sent(fetch, "POST /api/style/messages")).toEqual([{ title: "iPhone 13 128GB, cracked back", price: "220",
      marketplace: "facebook", text: "Hi mate, £185 given the crack?" }]);
  });

  it("skips setup when the API already knows your style", async () => {
    serve(usual);
    render(<App />);
    expect(await screen.findByRole("navigation")).toBeTruthy();
    expect(localStorage.getItem(SETUP_DONE)).toBe("1");
  });

  it("switches screens from the sidebar, and says which one in the title bar", async () => {
    localStorage.setItem(SETUP_DONE, "1");
    serve(usual);
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Listing title"), "iPhone 13");
    expect(await screen.findByText("Gemma running")).toBeTruthy();
    expect(await screen.findByText("Learning from 14 of your messages")).toBeTruthy();
    await user.click(within(screen.getByRole("navigation")).getByText("Home"));
    expect(await screen.findByText("Done on this Mac")).toBeTruthy();
    expect(await screen.findByText("80%")).toBeTruthy();
    expect(window.location.hash).toBe("#home");
    expect(screen.getByText("FlipAssist · Home")).toBeTruthy();
    await user.click(within(screen.getByRole("navigation")).getByText("AI message"));
    expect(screen.getByDisplayValue("iPhone 13")).toBeTruthy(); // what you typed is still there
  });

  it("shows what it learned and deletes a message you no longer want it to learn from", async () => {
    localStorage.setItem(SETUP_DONE, "1");
    window.location.hash = "#style";
    const fetch = serve({ ...usual, "GET /api/style/messages": [200, [{ id: "msg-1", title: "Pixel 8", price: "260",
      text: "Hi mate, would you take £220 cash?", marketplace: "", source: "added", at: "now" }]],
      "DELETE /api/style/messages/msg-1": [204, null] });
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByText("Pixel 8 · £260")).toBeTruthy();
    expect(await screen.findByText("'Hi mate'")).toBeTruthy();
    expect(screen.getByText("Cheers")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Delete this message" }));
    expect(screen.queryByText("Pixel 8 · £260")).toBeNull();
    expect(fetch.mock.calls.some(([url, init]) => url === "/api/style/messages/msg-1" && init?.method === "DELETE")).toBe(true);
  });

  it("switches between light and dark, and remembers it", async () => {
    localStorage.setItem(SETUP_DONE, "1");
    serve(usual);
    const user = userEvent.setup();
    render(<App />);
    expect(document.documentElement.dataset.theme).toBe("light");
    await user.click(screen.getByRole("button", { name: "Dark mode" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem(THEME)).toBe("dark");
    expect(screen.getByRole("button", { name: "Light mode" })).toBeTruthy();
  });

  it("fills its own Mac window when the launcher opens it, and only then", () => {
    markShell(window);
    expect(document.documentElement.dataset.shell).toBeUndefined();
    markShell(Object.assign(Object.create(window), { flipassistShell: { window: "mac" } }));
    expect(document.documentElement.dataset.shell).toBe("window");
    delete document.documentElement.dataset.shell;
  });

  it("says so when the API isn't running", async () => {
    localStorage.setItem(SETUP_DONE, "1");
    serve({});
    render(<App />);
    expect(await screen.findByText("API not running")).toBeTruthy();
  });
});
