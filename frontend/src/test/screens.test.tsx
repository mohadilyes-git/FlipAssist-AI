import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App, markShell, SETUP_DONE, THEME } from "../App";
import type { ListingDraft, MessageDraft, PriceEstimate, Style } from "../api";
import { ListingScreen } from "../screens/ListingScreen";
import { HomeScreen, ollamaRows, paidRows, runningRows } from "../screens/HomeScreen";
import { MessageScreen } from "../screens/MessageScreen";
import { cautions, damageLine, itemName, PriceScreen, sortedBy } from "../screens/PriceScreen";

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
  phrases: [{ k: "Closing", v: "Cheers" }],
  learned: [{ key: "greeting:hi mate", what: "Opens with", value: "Hi mate", used: true },
    { key: "mention:cash", what: "Mentions", value: "paying cash", used: true },
    { key: "phrase:closing:cheers", what: "Closing", value: "Cheers", used: true }] };
const NO_STYLE: Style = { count: 0, traits: [], phrases: [], learned: [] };
// the same style with paying cash removed
const NO_CASH: Style = { ...STYLE, learned: STYLE.learned.map((r) => (r.key === "mention:cash" ? { ...r, used: false } : r)) };
// 14 Oct: Claude Haiku 5.5 only checks each reason; Claude Sonnet 5.5 writes when this device's models can't
const HEALTH = { local_model: "gemma3:4b", local_running: true, api_model: "claude-sonnet-5-5", api_key_set: true,
  check_model: "claude-haiku-5-5", fix_model: "claude-sonnet-5-5", prices_api_set: true, flip_api_key_set: true,
  models: [{ job: "reads listings", name: "flip-reader-5", installed: true },
    { job: "words the reason", name: "flip-wording-4b", installed: true },
    { job: "sorts price flaws", name: "flip-kinds-1", installed: true },
    { job: "reads your style", name: "flip-style-1b", installed: true },
    { job: "writes messages", name: "gemma3:4b", installed: true }] };
const STATS = { drafts: 2, ready: 2, needs_you: 0, done_on_this_device: 0.8, models: [], cost_pence: 0,
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
  /** the listing typed in, and how many flaws to say picked: nothing is written for a lower offer until you pick */
  async function fill(user: ReturnType<typeof userEvent.setup>, title = "iPhone 13 128GB Blue", price = "£220") {
    await user.type(screen.getByLabelText("Listing title"), title);
    await user.type(screen.getByLabelText("Asking price"), price);
    await user.click(screen.getByRole("button", { name: "All flaws" }));
  }
  async function draft(user: ReturnType<typeof userEvent.setup>) {
    await fill(user);
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
    expect(screen.getByText("No AI writing · 1.2s · free · read by Gemma 3 4B (on this device)")).toBeTruthy();
    const body = sent(fetch, "POST /api/messages/draft");
    expect([body.listing.asking_price, body.offer, body.listing.marketplace]).toEqual(["220.00", "185.00", "facebook"]);
  });

  it("has no marketplace to pick: it writes for a listing you collect, unless the listing says it's posted", () => {
    render(<MessageScreen />);
    expect(screen.queryByText("Marketplace")).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("says the flaw only once you pick how many: none picked turns the row red and writes nothing", async () => {
    const fetch = serve({ "POST /api/messages/draft": [200, DRAFT] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    expect(screen.getByRole("button", { name: "Yes" }).getAttribute("aria-pressed")).toBe("true"); // the flaw is said
    expect(screen.queryByRole("button", { name: "My style" })).toBeNull();
    const counts = within(screen.getByRole("group", { name: "How many flaws to say" }));
    expect(counts.getAllByRole("button").map((b) => [b.textContent, b.getAttribute("aria-pressed")])).toEqual(
      [["1 flaw only", "false"], ["2 flaws only", "false"], ["3 flaws only", "false"], ["All flaws", "false"]]);
    await user.type(screen.getByLabelText("Listing title"), "iPhone 13 128GB Blue");
    await user.type(screen.getByLabelText("Asking price"), "£220");
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Pick how many flaws to say");
    expect(screen.getByRole("group", { name: "How many flaws to say" }).className).toContain("missing");
    expect(fetch).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "2 flaws only" }));
    expect(screen.queryByRole("alert")).toBeNull(); // picking clears the red
    expect(screen.getByRole("group", { name: "How many flaws to say" }).className).not.toContain("missing");
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    await screen.findByDisplayValue(DRAFT.message!);
    const body = sent(fetch, "POST /api/messages/draft");
    expect([body.kind, body.mention, body.flaws_said]).toEqual(["lower", true, 2]);
  });

  it.each([["1 flaw only", 1], ["3 flaws only", 3], ["All flaws", "all"]])("sends %s as the flaws to say", async (label, said) => {
    const fetch = serve({ "POST /api/messages/draft": [200, DRAFT] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await user.type(screen.getByLabelText("Listing title"), "iPhone 13 128GB Blue");
    await user.type(screen.getByLabelText("Asking price"), "£220");
    await user.click(screen.getByRole("button", { name: label as string }));
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    await screen.findByDisplayValue(DRAFT.message!);
    expect([sent(fetch, "POST /api/messages/draft").mention, sent(fetch, "POST /api/messages/draft").flaws_said])
      .toEqual([true, said]);
  });

  it("says no flaw with No, and doesn't ask how many", async () => {
    const fetch = serve({ "POST /api/messages/draft": [200, DRAFT] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await user.type(screen.getByLabelText("Listing title"), "iPhone 13 128GB Blue");
    await user.type(screen.getByLabelText("Asking price"), "£220");
    await user.click(screen.getByRole("button", { name: "Write my message" })); // turns red...
    await user.click(screen.getByRole("button", { name: "No" })); // ...and No needs no count
    expect(screen.queryByRole("group", { name: "How many flaws to say" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    await screen.findByDisplayValue(DRAFT.message!);
    const body = sent(fetch, "POST /api/messages/draft");
    expect([body.mention, body.flaws_said]).toEqual([false, null]);
  });

  it("never says a flaw when paying asking or more: a flaw is a lower offer's reason", async () => {
    const fetch = serve({ "POST /api/messages/draft": [[200, { ...DRAFT, kind: "asking" }], [200, { ...DRAFT, kind: "more" }]] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await user.type(screen.getByLabelText("Listing title"), "iPhone 13 128GB Blue");
    await user.type(screen.getByLabelText("Asking price"), "£220");
    for (const card of ["Pay asking", "Offer more"]) {
      await user.click(screen.getByRole("radio", { name: new RegExp(card) }));
      expect(screen.queryByRole("button", { name: "Yes" })).toBeNull();
      expect(screen.queryByRole("group", { name: "How many flaws to say" })).toBeNull();
      expect(screen.getByText("Not said when paying asking or more")).toBeTruthy();
      await user.click(screen.getByRole("button", { name: "Write my message" })); // no count to pick
      await screen.findByDisplayValue(DRAFT.message!);
    }
    const [asking, more] = [sent(fetch, "POST /api/messages/draft", 0), sent(fetch, "POST /api/messages/draft", 1)];
    expect([asking.kind, asking.mention, asking.flaws_said]).toEqual(["asking", false, null]);
    expect([more.kind, more.mention, more.flaws_said]).toEqual(["more", null, null]); // your style: good condition
    await user.click(screen.getByRole("radio", { name: /Offer lower/ }));
    expect(screen.getByRole("button", { name: "Yes" }).getAttribute("aria-pressed")).toBe("true"); // back again
  });

  it("writes with the AI writer or with no AI writing, and only the AI writer rewrites", async () => {
    const fetch = serve({ "POST /api/messages/draft": [[200, DRAFT], [200, { ...DRAFT, draft_id: 8, message: "reworded" }]] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    const writers = within(screen.getByRole("group", { name: "Writer" }));
    expect(writers.getAllByRole("button").map((b) => [b.textContent, b.getAttribute("aria-pressed")])).toEqual(
      [["AI writer", "false"], ["No AI writing", "true"]]);
    expect(screen.queryByRole("button", { name: "Auto" })).toBeNull();
    await draft(user);
    expect(sent(fetch, "POST /api/messages/draft").writer).toBe("template");
    expect(screen.getByRole("button", { name: "Rewrite (AI writer only)" }).hasAttribute("disabled")).toBe(true);
    await user.click(screen.getByRole("button", { name: "AI writer" }));
    await user.click(screen.getByRole("button", { name: "Rewrite" }));
    expect(await screen.findByDisplayValue("reworded")).toBeTruthy();
    const rewrite = sent(fetch, "POST /api/messages/draft", 1);
    expect([rewrite.writer, rewrite.rewrite_of]).toEqual(["ai", DRAFT.message]);
  });

  it("shows the draft at once, then the reason's check, and a fix replaces the message only if you haven't edited it", async () => {
    const pending: MessageDraft = { ...DRAFT, message: "Hi mate, would you take £185 cash? I'm offering that because there's a dot on the screen. Can collect today.",
      reason: { clause: "there's a dot on the screen", by: "flip-wording-3", checked: "pending" } };
    const fixedMessage = "Hi mate, would you take £185 cash? I'm offering that because there's a black dot on the screen. Can collect today.";
    const fetch = serve({ "POST /api/messages/draft": [200, pending],
      "POST /api/messages/check-reason": [200, { reason: { clause: "there's a black dot on the screen", by: "claude-sonnet-5-5",
        checked: "fixed" }, message: fixedMessage, changed: true, problems: [], cost_pence: 0.16,
        attempts: [{ model: "claude-haiku-5-5", problems: [], seconds: 1, cost_pence: 0.008, job: "reason" },
          { model: "claude-sonnet-5-5", problems: [], seconds: 1.4, cost_pence: 0.152, job: "reason" }] }] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    expect(await screen.findByDisplayValue(fixedMessage)).toBeTruthy();  // the fix replaced the untouched draft
    expect(screen.getByText("Reason flagged by Claude Haiku 5.5, fixed by Claude Sonnet 5.5")).toBeTruthy();
    expect(sent(fetch, "POST /api/messages/draft").check_later).toBe(true);
    const check = sent(fetch, "POST /api/messages/check-reason");
    expect([check.draft_id, check.clause, check.flaws, check.offer_pence]).toEqual([7, "there's a dot on the screen", ["Black dot on the screen"], 18500]);
  });

  it("checks the reason against the reader's whole sentences, the ones it was worded from", async () => {
    const pending: MessageDraft = { ...DRAFT,
      reading: { ...DRAFT.reading, flaws: ["cracked the back"], quotes: ["I dropped it and cracked the back"] },
      reason: { clause: "the back is cracked", by: "flip-wording-3", checked: "pending" } };
    const fetch = serve({ "POST /api/messages/draft": [200, pending],
      "POST /api/messages/check-reason": [200, { reason: { ...pending.reason!, checked: "ok" }, message: pending.message,
        changed: false, problems: [], cost_pence: 0.008, attempts: [] }] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    expect(await screen.findByText("Reason by flip-wording-3 · checked by Claude Haiku 5.5")).toBeTruthy();
    const check = sent(fetch, "POST /api/messages/check-reason");
    expect([check.quotes, check.flaws]).toEqual([["I dropped it and cracked the back"], ["cracked the back"]]);
  });

  it("checks the reason against only the flaws you picked, and keeps them for Make it longer", async () => {
    const picked = ["Face ID not working"];
    const pending: MessageDraft = { ...DRAFT, reason_from: picked,
      reading: { ...DRAFT.reading, flaws: ["Back glass cracked", "Face ID not working", "Battery 79%"],
        quotes: ["Back glass cracked.", "Face ID not working.", "Battery 79%."] },
      reason: { clause: "the Face ID isn't working", by: "flip-wording-4b", checked: "pending" } };
    const fetch = serve({ "POST /api/messages/draft": [[200, pending], [200, { ...pending, draft_id: 8 }]],
      "POST /api/messages/check-reason": [200, { reason: { ...pending.reason!, checked: "ok" }, message: pending.message,
        changed: false, problems: [], cost_pence: 0.008, attempts: [] }] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await fill(user);
    await user.click(screen.getByRole("button", { name: "1 flaw only" }));
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    expect(await screen.findByText("Reason by flip-wording-4b · checked by Claude Haiku 5.5")).toBeTruthy();
    expect(sent(fetch, "POST /api/messages/check-reason").quotes).toEqual(picked);
    await user.click(screen.getByRole("button", { name: "Make it longer" }));
    const longer = sent(fetch, "POST /api/messages/draft", 1);
    expect([longer.reason.quotes, longer.flaws_said]).toEqual([picked, 1]);
  });

  it("no longer asks for a UK price: that has its own tab (4 Oct)", async () => {
    const fetch = serve({ "POST /api/messages/draft": [200, DRAFT] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    await screen.findByDisplayValue(DRAFT.message!);
    expect(fetch.mock.calls.map(([url]) => url)).toEqual(["/api/messages/draft"]);
    expect(screen.queryByLabelText("UK price")).toBeNull();
  });

  it("keeps your own edits when a fixed reason comes back", async () => {
    const pending: MessageDraft = { ...DRAFT, reason: { clause: "there's a dot on the screen", by: "flip-wording-3", checked: "pending" } };
    let release: () => void = () => {};
    const waited = new Promise<void>((resolve) => { release = resolve; });
    const fetch = vi.fn(async (url: string) => {
      if (url === "/api/messages/check-reason") {
        await waited;
        return { ok: true, status: 200, json: async () => ({ reason: { clause: "x", by: "claude-sonnet-5-5", checked: "fixed" },
          message: "the fixed one", changed: true, problems: [], attempts: [], cost_pence: 0.15 }) };
      }
      return { ok: true, status: 200, json: async () => pending };
    });
    vi.stubGlobal("fetch", fetch);
    const user = userEvent.setup();
    render(<MessageScreen />);
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    const box = await screen.findByDisplayValue(DRAFT.message!);
    expect(screen.getByText("Reason by flip-wording-3 · checking…")).toBeTruthy();
    await user.type(box, " Thanks");
    release();
    expect(await screen.findByText("Reason flagged by Claude Haiku 5.5, fixed by Claude Sonnet 5.5")).toBeTruthy();
    expect(screen.getByDisplayValue(`${DRAFT.message} Thanks`)).toBeTruthy();  // yours stays
  });

  it("says so plainly when no draft passed the checks", async () => {
    serve({ "POST /api/messages/draft": [200, { ...DRAFT, status: "needs you", message: null, written_by: null,
      reasons: ["no answer passed the checks"] }] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await fill(user, "iPhone 13", "220");
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    expect(await screen.findByText(/^No draft passed · /)).toBeTruthy();
  });

  it("calls the no-AI writer what it is: the AI still reads the listing", () => {
    render(<MessageScreen />);
    const chip = screen.getByRole("button", { name: "No AI writing" });
    expect(chip.getAttribute("title")).toBe("The AI still reads the listing's flaws; your sentences (or AlertFlip's) "
      + "write the message");
    expect(screen.queryByRole("button", { name: "No AI" })).toBeNull();
    expect(screen.getByRole("button", { name: "AI writer" }).getAttribute("title")).toContain("Gemma 3 4B");
  });

  it("shows why, step by step", async () => {
    serve({ "POST /api/messages/draft": [200, DRAFT] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await draft(user);
    await user.click(screen.getByRole("button", { name: /Why · 2 steps/ }));
    expect(screen.getByText("Gemma 3 4B (on this device) passed")).toBeTruthy();
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
    expect(body.reason).toBeNull(); // this draft has no worded reason to keep
  });

  it("makes it longer keeping the checked reason on screen, not wording it again", async () => {
    const checkedReason = { clause: "there's a black dot on the screen", by: "claude-sonnet-5-5", checked: "fixed" };
    const fetch = serve({ "POST /api/messages/draft": [[200, { ...DRAFT, reason: checkedReason }],
      [200, { ...DRAFT, draft_id: 8, reason: checkedReason }]] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await draft(user);
    await user.click(screen.getByRole("button", { name: "Make it longer" }));
    expect(sent(fetch, "POST /api/messages/draft", 1).reason).toEqual({ ...checkedReason, quotes: DRAFT.reading.flaws });
  });

  it("clears the draft when you change the title or the description, so you write one for the listing as it is", async () => {
    const checkedReason = { clause: "there's a black dot on the screen", by: "flip-wording-3", checked: "ok" };
    const fetch = serve({ "POST /api/messages/draft": [[200, { ...DRAFT, reason: checkedReason }],
      [200, { ...DRAFT, draft_id: 8, message: "the new one" }]] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await draft(user);
    await user.type(screen.getByLabelText("The seller's description"), " The phone turns off sometimes.");
    expect(screen.queryByDisplayValue(DRAFT.message!)).toBeNull(); // the old message is gone...
    expect(screen.queryByRole("button", { name: /^Rewrite/ })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Write my message" })); // ...and you write a new one
    expect(await screen.findByDisplayValue("the new one")).toBeTruthy();
    const body = sent(fetch, "POST /api/messages/draft", 1);
    expect([body.reason, body.rewrite_of, body.listing.description]).toEqual([null, null, " The phone turns off sometimes."]);
    await user.type(screen.getByLabelText("Listing title"), " Pro");
    expect(screen.queryByDisplayValue("the new one")).toBeNull(); // the title too
  });

  it("flips Make it longer to Make it shorter, and a rewrite keeps the length on screen", async () => {
    const LONGER = { ...DRAFT, draft_id: 8, message: DRAFT.message + " Is it unlocked? Does it come with a charger?" };
    const fetch = serve({ "POST /api/messages/draft": [[200, DRAFT], [200, LONGER], [200, { ...LONGER, draft_id: 9 }],
      [200, { ...DRAFT, draft_id: 10 }]] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await user.click(screen.getByRole("button", { name: "AI writer" })); // a rewrite is the AI writer's
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
    await user.click(screen.getByRole("button", { name: "AI writer" }));
    await draft(user);
    expect(screen.getByText(/The title says iPhone 15 Pro Max but the description says iPhone 14/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Rewrite" }));
    expect((await screen.findByRole("alert")).textContent).toBe("No new wording passed the checks, so your message is unchanged");
    expect(screen.getByDisplayValue(DRAFT.message!)).toBeTruthy();
  });

  it("has no question about mentioning the flaw: Say the flaw already says it", async () => {
    const asked = { ...DRAFT, ask: 'The listing says "Black dot on the screen". Mention it as the reason for your offer?' };
    serve({ "POST /api/messages/draft": [200, asked] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await draft(user);
    expect(screen.queryByText(asked.ask)).toBeNull();
    expect(screen.queryByRole("button", { name: "Yes, mention it" })).toBeNull();
  });

  it("says what the API refused", async () => {
    serve({ "POST /api/messages/draft": [422, { detail: [{ loc: ["body", "listing", "asking_price"], msg: "String should match pattern" }] }] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await fill(user, "iPhone 13", "220");
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
    await user.click(screen.getByRole("button", { name: "All flaws" }));
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

describe("AI UK price estimate", () => {
  const PRICED: PriceEstimate = { price: 150, middle: 175, low: 160, high: 190, currency: "GBP", sales: 51,
    model: "iphone 13", storage_gb: 128, ram_gb: null, asked_storage_gb: 128, asked_ram_gb: null, kind: "iphone",
    kinds: ["damage"], cuts: ["damage"], parts_price: false, rough: false, exact: true, mode: "catalogue",
    flaws: ["cracked back", "battery 81%"], read_by: "flip-reader-5" };

  it("reads the description for flaws and shows the price cut for them, with no eBay in it", async () => {
    const fetch = serve({ "POST /api/prices/estimate": [200, PRICED] });
    const user = userEvent.setup();
    render(<PriceScreen />);
    await user.type(screen.getByLabelText("Listing title"), "iPhone 13 128GB Blue");
    await user.type(screen.getByLabelText("The seller's description"), "Cracked back, battery 81%");
    await user.click(screen.getByRole("button", { name: "Check the UK price" }));
    const hero = await screen.findByLabelText("UK price");
    expect(hero.textContent).toContain("£150");
    expect(hero.textContent).toContain("iPhone 13 128GB · from 51 UK sales");
    expect(hero.textContent).toContain("£175with no flaws");
    expect(hero.textContent).toContain("−14%cut for its flaws");
    expect(hero.textContent).toContain("£160–£190middle half of clean sales(cheapest quarter left out)");
    const flaws = screen.getByLabelText("Flaws it found");
    expect(within(flaws).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["cracked back", "battery 81%"]);
    expect(flaws.textContent).toContain("Read by flip-reader-5 (on this device) · counted as damage");
    const how = within(screen.getByLabelText("How it works")).getAllByRole("listitem").map((li) => li.textContent);
    expect(how.map((step) => step.split(/[,:.]| keeps| organises| reads/)[0])).toEqual(
      ["AlertFlip prices API", "Claude Haiku 5", "The middle price of clean ones", "flip-reader-5"]);
    expect(screen.queryAllByRole("paragraph").filter((p) => p.className === "warn-row")).toHaveLength(0);
    expect(document.body.textContent).not.toMatch(/ebay/i);
    expect(sent(fetch, "POST /api/prices/estimate")).toEqual(
      { title: "iPhone 13 128GB Blue", description: "Cracked back, battery 81%" });
  });

  it("says when it's not a phone it prices, and drops a price once the listing changes", async () => {
    serve({ "POST /api/prices/estimate": [[200, { currency: "GBP", cuts: [], rough: false, exact: false,
      skipped: "Estimates are for iPhones, Samsung phones and MacBooks only" }], [200, PRICED]] });
    const user = userEvent.setup();
    render(<PriceScreen />);
    await user.type(screen.getByLabelText("Listing title"), "PS5 Slim");
    await user.click(screen.getByRole("button", { name: "Check the UK price" }));
    expect(await screen.findByText("Estimates are for iPhones, Samsung phones and MacBooks only")).toBeTruthy();
    await user.clear(screen.getByLabelText("Listing title"));
    await user.type(screen.getByLabelText("Listing title"), "iPhone 13");
    expect(screen.queryByText("Estimates are for iPhones, Samsung phones and MacBooks only")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Check the UK price" }));
    expect((await screen.findByLabelText("UK price")).textContent).toContain("£150");
  });

  it("prices a MacBook with its RAM and storage, and says when it priced another size", async () => {
    serve({ "POST /api/prices/estimate": [200, { ...PRICED, price: 420, middle: 420, low: 390, high: 460, sales: 33,
      model: "macbook air 13 m1", kind: "macbook", storage_gb: 512, ram_gb: 8, asked_storage_gb: 1024,
      asked_ram_gb: 8, kinds: [], cuts: [], flaws: [], exact: false, rough: true }] });
    const user = userEvent.setup();
    render(<PriceScreen />);
    await user.type(screen.getByLabelText("Listing title"), "MacBook Air M1 8GB 1TB");
    await user.click(screen.getByRole("button", { name: "Check the UK price" }));
    const hero = await screen.findByLabelText("UK price");
    expect(hero.textContent).toContain("MacBook Air 13-inch M1 8GB RAM 512GB · from 33 UK sales");
    expect(hero.textContent).toContain("nonecut for its flaws");
    expect(screen.getByText("Too few sales of an 8GB RAM 1TB one: this is an 8GB RAM 512GB one's price, not changed for size"))
      .toBeTruthy();
    expect(screen.getByText("None: priced as one with no flaws.")).toBeTruthy();
  });

  it("says what to know before trusting the price", () => {
    const said = (change: Partial<PriceEstimate>) => cautions({ ...PRICED, ...change });
    expect(said({})).toEqual([]);
    expect(said({ asked_storage_gb: null })).toEqual(
      ["Couldn't find the storage in the listing: priced as a 128GB one, the size that sells most"]);
    expect(said({ exact: false })).toEqual(["Rough: only 51 sales of this size to go on"]);  // its own size, under 5
    expect(said({ sales: 12, rough: true })).toEqual(["Rough: only 12 sales to go on"]);
    expect(said({ kinds: ["lock"], parts_price: true })).toEqual(["Priced at what for-parts ones sell for"]);
    expect(said({ kinds: ["network lock"], rough: true })).toEqual(["Rough: network lock is hard to price"]);
    expect(said({ kind: "macbook", ram_gb: 8, asked_ram_gb: null, kinds: ["damage"] })).toEqual([
      "Couldn't find the RAM in the listing: priced as an 8GB RAM 128GB one, the size that sells most",
      "Rough for a MacBook: the flaw cuts were measured on phones"]);
    expect(said({ mode: "keyword", model: null, item: "iPhone 17 Air" })).toEqual(
      ["Rough: priced from a search by words, not a model it knows"]);
  });

  it("names the backend's models as they're written", () => {
    expect(["iphone 13 pro max", "galaxy s23 fe", "iphone xr", "galaxy z flip 5", "galaxy s10 5g", "macbook air 13 m1",
      "macbook pro 14 m3 pro", "macbook pro 2019"].map(itemName))
      .toEqual(["iPhone 13 Pro Max", "Galaxy S23 FE", "iPhone XR", "Galaxy Z Flip 5", "Galaxy S10 5G",
        "MacBook Air 13-inch M1", "MacBook Pro 14-inch M3 Pro", "MacBook Pro 2019"]);
  });

  // 6 Oct review: the card says what the price did. Each answer is the one /prices/estimate gave for the listing.
  /** The listing typed in and checked, with this answer: the hero's text, the warnings and the flaws card's text */
  async function check(title: string, description: string, answer: PriceEstimate) {
    serve({ "POST /api/prices/estimate": [200, answer] });
    const user = userEvent.setup();
    render(<PriceScreen />);
    await user.type(screen.getByLabelText("Listing title"), title);
    await user.type(screen.getByLabelText("The seller's description"), description);
    await user.click(screen.getByRole("button", { name: "Check the UK price" }));
    const hero = await screen.findByLabelText("UK price");
    return { hero: hero.textContent, flaws: screen.getByLabelText("Flaws it found").textContent,
      warned: [...document.querySelectorAll(".warn-row")].map((p) => p.textContent) };
  }

  it("says it couldn't find a size, not that the listing has none", async () => {
    // "128gig" was missed (flip/prices.py reads sizes; the screen only words what code knows), so the size that sells most
    const got = await check("iPhone 13 Blue", "128gig, unlocked, works perfectly.", { ...PRICED, price: 285, middle: 285,
      low: 270, high: 295, sales: 15, storage_gb: 256, asked_storage_gb: null, kinds: [], cuts: [], flaws: [], rough: true });
    expect(got.hero).toContain("iPhone 13 256GB · from 15 UK sales");
    expect(got.warned).toEqual(["Couldn't find the storage in the listing: priced as a 256GB one, the size that sells most",
      "Rough: only 15 sales to go on"]);
    expect(document.body.textContent).not.toContain("No storage in the listing");
  });

  it("says a MacBook was priced as another size, even when the listing leaves the other size out", async () => {
    const swapped = { ...PRICED, kind: "macbook", model: "macbook air 13 m1", price: 550, middle: 550, low: 530, high: 560,
      sales: 12, storage_gb: 512, ram_gb: 16, exact: false, rough: true, kinds: [], cuts: [], flaws: [] };
    // S7: 3 sales of an 8GB RAM 256GB one, too few, so a 16GB RAM 512GB one's price
    const got = await check("MacBook Air M1 256GB Space Grey", "Works perfectly, battery cycle count 210.",
      { ...swapped, asked_storage_gb: 256, asked_ram_gb: null });
    expect(got.hero).toContain("MacBook Air 13-inch M1 16GB RAM 512GB · from 12 UK sales");
    expect(got.warned).toEqual(["Couldn't find the RAM in the listing, and too few sales of a 256GB one: this is a 16GB "
      + "RAM 512GB one's price, not changed for size", "Rough: only 12 sales to go on"]);
    // S7b: "MacBook Air M1 8GB Space Grey"
    expect(cautions({ ...swapped, asked_storage_gb: null, asked_ram_gb: 8 })).toEqual(["Couldn't find the storage in the "
      + "listing, and too few sales of an 8GB RAM one: this is a 16GB RAM 512GB one's price, not changed for size",
    "Rough: only 12 sales to go on"]);
  });

  it("names the title's own flaws when the reader quoted none, rather than saying it has none", async () => {
    // S10: the crack is only in the title, and the price is cut for it
    let got = await check("iPhone 13 128GB cracked back", "Collection only from Leeds.", { ...PRICED, price: 190,
      middle: 220, low: 210, high: 230, sales: 30, kinds: ["damage"], cuts: ["damage"], flaws: [] });
    expect(got.hero).toContain("−14%cut for its flaws");
    expect(got.flaws).toBe("Flaws it foundNone quoted from the description. Counted from the title: damage"
      + "Read by flip-reader-5 (on this device)");
    cleanup();
    // S9: a for-parts title, priced at what for-parts ones sell for
    got = await check("Faulty iPhone 12 64GB for parts", "Collection only from Leeds.", { ...PRICED, price: 70, middle: 180,
      low: 170, high: 190, sales: 30, model: "iphone 12", storage_gb: 64, asked_storage_gb: 64, kinds: ["fault", "parts"],
      cuts: [], parts_price: true, flaws: [] });
    expect(got.flaws).toBe("Flaws it foundNone quoted from the description. Counted from the title: fault, parts"
      + "Read by flip-reader-5 (on this device) · priced at what for-parts ones sell for, with nothing cut on top");
  });

  it("says which flaws a locked or for-parts price doesn't cut on top", async () => {
    const description = "iCloud locked to the previous owner. Cracked screen and Face ID not working.";
    const locked = { ...PRICED, price: 135, middle: 220, low: 210, high: 230, sales: 30, kinds: ["lock", "damage", "fault"],
      cuts: ["lock"], flaws: ["iCloud locked to the previous owner.", "Cracked screen and Face ID not working."] };
    // S1: 3 for-parts sales, too few, so the lock's rough guess: the crack and Face ID aren't cut on top
    let got = await check("iPhone 13 128GB", description, locked);
    expect(got.flaws).toContain("Read by flip-reader-5 (on this device) · counted as lock, damage, fault · priced as locked: "
      + "damage and fault aren't cut on top");
    cleanup();
    // S2: 8 for-parts sales, so what they sold for
    got = await check("iPhone 13 128GB", description, { ...locked, price: 95, cuts: [], parts_price: true });
    expect(got.flaws).toContain("Read by flip-reader-5 (on this device) · counted as lock, damage, fault · priced at what "
      + "for-parts ones sell for, with nothing cut on top");
    cleanup();
    // for parts, with too few for-parts sales
    got = await check("iPhone 13 128GB", "Needs repair. Screen is cracked and Face ID doesn't work.", { ...locked,
      price: 160, kinds: ["parts", "damage", "fault"], cuts: ["parts"],
      flaws: ["Needs repair.", "Screen is cracked and Face ID doesn't work."] });
    expect(got.flaws).toContain(" · counted as parts, damage, fault · priced as for parts: damage and fault aren't cut on top");
    cleanup();
    // S3: locked and for parts, nothing else to leave out
    got = await check("iPhone 13 128GB", "Sold for parts. iCloud locked.", { ...locked, kinds: ["parts", "lock"],
      flaws: ["Sold for parts.", "iCloud locked."] });
    expect(got.flaws).toMatch(/ · counted as parts, lock$/);
  });

  it("warns of few sales when the listing gives no size, however few", () => {
    const sizeless = { ...PRICED, asked_storage_gb: null, kinds: [], cuts: [], flaws: [] };
    const which = "Couldn't find the storage in the listing: priced as a 128GB one, the size that sells most";
    // S4, "iPhone 13 Blue": 3 sales of the size that sells most, too few to be exact
    expect(cautions({ ...sizeless, exact: false, sales: 3, rough: true })).toEqual([which, "Rough: only 3 sales to go on"]);
    // S4b: 12 of them
    expect(cautions({ ...sizeless, exact: true, sales: 12, rough: true })).toEqual([which, "Rough: only 12 sales to go on"]);
    expect(cautions({ ...sizeless, exact: false, sales: 1 })).toEqual([which, "Rough: only 1 sale to go on"]);
    expect(cautions({ ...sizeless, sales: 20 })).toEqual([which]);
    // "MacBook Air M1 Space Grey", 4 sales
    expect(cautions({ ...sizeless, kind: "macbook", model: "macbook air 13 m1", storage_gb: 256, ram_gb: 8,
      asked_ram_gb: null, exact: false, sales: 4 })).toEqual(["Couldn't find the storage or RAM in the listing: priced as "
      + "an 8GB RAM 256GB one, the size that sells most", "Rough: only 4 sales to go on"]);
  });

  it("names flip-kinds-1 when it sorted the flaws, and nothing more when code's rules did", () => {
    expect(sortedBy("flip-kinds-1")).toBe(" (sorted by flip-kinds-1)");
    expect(sortedBy("flip-kinds-1 and code")).toBe(" (sorted by flip-kinds-1 and code)");
    expect(sortedBy("code")).toBe("");
    expect(sortedBy(null)).toBe("");
    expect(sortedBy(undefined)).toBe("");
  });

  it("says how flaws cut the price as the prices API does it, with no amounts that could go stale", () => {
    render(<PriceScreen />);
    const step = within(screen.getByLabelText("How it works")).getAllByRole("listitem")[3].textContent;
    expect(step).toBe("flip-reader-5, our AI on this device, reads the title and description for flaws (if its reading "
      + "fails our checks, Claude Sonnet 5.5 reads it instead, a paid call). flip-kinds-1, our flaw-sorting AI on this device, "
      + "sorts each flaw into a kind (code's rules do when it isn't installed), and the price is cut by amounts measured on phone listings: any flaw takes a small cut, faults cut the most, "
      + "and different kinds' cuts multiply. Damage is cut by how bad it is (minor, moderate or severe) and how pricey the "
      + "model is, as measured on 1,697 damaged iPhone, Samsung and MacBook listings. A locked or for-parts one is priced at what for-parts ones of the same model "
      + "and size sell for, or at a rough guess when too few have sold, with its other flaws not cut on top.");
    expect(step).not.toMatch(/\d\s?%|per ?cent/);  // the prices API's cut table is its own and can change
  });

  it("says a search by words left out a size only the description gives", async () => {
    const words = { ...PRICED, mode: "keyword", model: null, item: "Samsung Galaxy A52 phone (not A52s or A53)",
      kind: "samsung", price: 130, middle: 130, low: 100, high: 140, sales: 20, storage_gb: null, ram_gb: null,
      asked_storage_gb: 128, kinds: [], cuts: [], flaws: [] };
    // S11: the A52 isn't a model the API knows, and "128GB" is only in the description
    const got = await check("Samsung Galaxy A52 Black", "128GB, works perfectly.", words);
    expect(got.warned).toEqual(
      ["Rough: priced from a search by words, not a model it knows, and for any size: the listing's 128GB wasn't used"]);
    // a size the title names is in the search words
    const searched = ["Rough: priced from a search by words, not a model it knows"];
    expect(cautions(words, "Samsung Galaxy A52 128GB Black")).toEqual(searched);
    expect(cautions(words, "Samsung galaxy a52 128 black")).toEqual(searched);
    expect(cautions({ ...words, asked_storage_gb: 1024 }, "Galaxy S10 Plus 1TB")).toEqual(searched);
    // a MacBook's RAM and SSD from "16GB RAM, 512GB SSD." in the description: "MacBook Pro 16" is a screen, not RAM
    const mac = { ...words, kind: "macbook", item: "MacBook Pro 2017", asked_storage_gb: 512, asked_ram_gb: 16 };
    const both = "Rough: priced from a search by words, not a model it knows, and for any size: the listing's 16GB RAM "
      + "512GB wasn't used";
    expect(cautions(mac, "MacBook Pro 2017 13 inch Space Grey")).toEqual([both]);
    expect(cautions(mac, "MacBook Pro 16 2019 Space Grey")).toEqual([both]);
    expect(cautions(mac, "MacBook Pro 2017 16GB")).toEqual(["Rough: priced from a search by words, not a model it knows, "
      + "and for any storage: the listing's 512GB wasn't used"]);
    expect(cautions(mac, "MacBook Pro 2017 16/512")).toEqual(searched);
  });

  it("says a for-parts price isn't from the clean sales it counts", async () => {
    // S2: 30 clean sales, and 8 for-parts ones the price is from (the API doesn't say how many)
    let got = await check("iPhone 13 128GB", "iCloud locked to the previous owner. Cracked screen and Face ID not working.",
      { ...PRICED, price: 95, middle: 220, low: 210, high: 230, sales: 30, kinds: ["lock", "damage", "fault"], cuts: [],
        parts_price: true, flaws: ["iCloud locked to the previous owner.", "Cracked screen and Face ID not working."] });
    expect(got.hero).toContain("iPhone 13 128GB · for-parts price · clean price from 30 UK sales");
    expect(got.warned).toEqual(["Priced at what for-parts ones sell for"]);
    cleanup();
    // S9: "Faulty iPhone 12 64GB for parts"
    got = await check("Faulty iPhone 12 64GB for parts", "Collection only from Leeds.", { ...PRICED, price: 70, middle: 180,
      low: 170, high: 190, sales: 30, model: "iphone 12", storage_gb: 64, asked_storage_gb: 64, kinds: ["fault", "parts"],
      cuts: [], parts_price: true, flaws: [] });
    expect(got.hero).toContain("iPhone 12 64GB · for-parts price · clean price from 30 UK sales");
    // so few clean sales say nothing about it
    const parts = { ...PRICED, kinds: ["lock"], cuts: [], parts_price: true };
    expect(cautions({ ...parts, sales: 12 })).toEqual(["Priced at what for-parts ones sell for"]);
    expect(cautions({ ...parts, exact: false, sales: 3 })).toEqual(["Priced at what for-parts ones sell for"]);
  });

  it("doesn't call a MacBook's own for-parts price a cut measured on phones", () => {
    // S8: "MacBook Air M1 8GB 256GB", "Activation locked, I don't have the password.", 8 for-parts sales
    const mac = { ...PRICED, kind: "macbook", model: "macbook air 13 m1", price: 175, middle: 430, low: 410, high: 450,
      sales: 25, storage_gb: 256, ram_gb: 8, asked_storage_gb: 256, asked_ram_gb: 8, kinds: ["lock"], cuts: [],
      parts_price: true, flaws: ["Activation locked, I don't have the password."] };
    expect(cautions(mac)).toEqual(["Priced at what for-parts ones sell for"]);
    // 3 for-parts sales, too few: the lock's rough guess, measured on phones
    expect(cautions({ ...mac, price: 265, cuts: ["lock"], parts_price: false })).toEqual(
      ["Rough: lock is hard to price", "Rough for a MacBook: the flaw cuts were measured on phones"]);
    // "Small crack on the corner of the lid."
    expect(cautions({ ...mac, price: 370, kinds: ["damage"], cuts: ["damage"], parts_price: false })).toEqual(
      ["Rough for a MacBook: the flaw cuts were measured on phones"]);
  });
});

describe("List on eBay", () => {
  const LISTED: ListingDraft = {
    draft_id: 3, status: "needs you", ebay_title: "Apple iPhone 13 128GB Midnight Unlocked", condition_id: "3000",
    condition_note: "Light scratch on the back.", description: "Apple iPhone 13 128GB in Midnight.", colour: null,
    colour_from: null,
    filled_by_code: { brand: "Apple", model: "iPhone 13", storage: "128GB", battery: "78", specs: { "Screen Size": "6.1 in" } },
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

  it("says who picked the colour, and a colour-only look doesn't count as writing the draft", async () => {
    serve({ "POST /api/listings/draft": [200, { ...LISTED, colour: "Midnight", colour_from: "photos",
      colour_by: "claude-haiku-5-5", attempts: [LISTED.attempts[0],
        { model: "claude-haiku-5-5", problems: [], seconds: 2.1, cost_pence: 0.0125, colour_only: true }],
      cost_pence: 0.0125 }] });
    const user = userEvent.setup();
    render(<ListingScreen />);
    await user.type(screen.getByLabelText("The seller's title"), "iphone 13 128gb");
    await user.click(screen.getByRole("button", { name: "Draft listing" }));
    expect(await screen.findByText("Midnight (from the photos, by Claude Haiku 5.5)")).toBeTruthy();
    // a phone's eBay Colour field says who picked it too
    cleanup();
    serve({ "POST /api/listings/draft": [200, { ...LISTED, colour: "Midnight", colour_from: "photos",
      colour_by: "claude-haiku-5-5", ebay_category: { id: "9355", name: "Mobile & Smart Phones", path: "Mobile Phones" },
      item_specifics: [{ name: "Colour", value: "Black", required: true, source: "the photos: Midnight", options: ["Black"] }],
      attempts: LISTED.attempts, cost_pence: 0 }] });
    render(<ListingScreen />);
    await user.type(screen.getByLabelText("The seller's title"), "iphone 13 128gb");
    await user.click(screen.getByRole("button", { name: "Draft listing" }));
    expect(await screen.findByText("from the photos: Midnight, by Claude Haiku 5.5")).toBeTruthy();
    cleanup();
    serve({ "POST /api/listings/draft": [200, { ...LISTED, colour: "Midnight", colour_from: "photos",
      colour_by: "claude-haiku-5-5", attempts: [LISTED.attempts[0],
        { model: "claude-haiku-5-5", problems: [], seconds: 2.1, cost_pence: 0.0125, colour_only: true }],
      cost_pence: 0.0125 }] });
    render(<ListingScreen />);
    await user.type(screen.getByLabelText("The seller's title"), "iphone 13 128gb");
    await user.click(screen.getByRole("button", { name: "Draft listing" }));
    await screen.findByText("Midnight (from the photos, by Claude Haiku 5.5)");
    expect(screen.getByText(/^Gemma 3 4B \(on this device\) ·/)).toBeTruthy(); // Gemma wrote it; Haiku only looked at the colour
    await user.click(screen.getByRole("button", { name: "Why" }));
    expect(screen.getByText("Claude Haiku 5.5, colour only: passed")).toBeTruthy();
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
    expect(screen.getByText("Battery health").nextElementSibling?.textContent).toBe("78%"); // read from the notes
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

  it("says what the seller's description says for an empty field eBay needs", async () => {
    serve({ "POST /api/listings/draft": [200, { ...LISTED,
      ebay_category: { id: "9355", name: "Mobile & Smart Phones", path: "Mobile Phones & Communication" },
      item_specifics: [{ name: "Storage Capacity", value: null, required: true, source: null,
        options: ["128 GB", "256 GB", "512 GB"], hint: "the seller says 128 GB" }] }] });
    const user = userEvent.setup();
    render(<ListingScreen />);
    await user.type(screen.getByLabelText("The seller's title"), "iphone 13");
    await user.click(screen.getByRole("button", { name: "Draft listing" }));
    expect(await screen.findByText("eBay needs this: the seller says 128 GB, check it")).toBeTruthy();
    expect((screen.getByLabelText("Storage Capacity") as HTMLInputElement).value).toBe(""); // a hint, never filled
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

  it("asks you to set up your style on first launch: 6 listings, Do the setup or Skip for now, nothing else", async () => {
    serve({ ...usual, "GET /api/style": [200, NO_STYLE] });
    const user = userEvent.setup();
    render(<App />);
    expect(screen.getByRole("heading", { name: "Set up your style" })).toBeTruthy();
    expect(screen.queryByRole("navigation")).toBeNull(); // no sidebar until it's done
    expect(screen.getByText(/reply to 6 quick listings/)).toBeTruthy(); // 14 Oct: it said 8 when there were 6
    expect(screen.queryByText(/\b8\b/)).toBeNull();
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Skip for now", "Do the setup"]);
    expect(screen.queryByText(/paste/i)).toBeNull(); // no pasting: Add more is gone
    await user.click(screen.getByRole("button", { name: "Skip for now" }));
    expect(screen.getByRole("navigation")).toBeTruthy();
    expect(window.location.hash).toBe("#home");
    expect(localStorage.getItem(SETUP_DONE)).toBe("1");
  });

  it("lists what it learned at the end of setup, and Remove deletes what you don't want", async () => {
    const fetch = serve({ ...usual, "GET /api/style": [[200, NO_STYLE], [200, STYLE], [200, NO_CASH]],
      "PUT /api/style/setup": [200, []], "POST /api/style/learned": [200, NO_CASH] });
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Do the setup" }));
    await user.type(screen.getByLabelText("Your message to this seller"), "Hi mate, would you take £185 cash? Cheers");
    await user.click(screen.getByRole("button", { name: "Next" }));
    for (let n = 2; n <= 6; n++) await user.click(screen.getByRole("button", { name: "Skip" }));
    expect(await screen.findByText("This is what it'll put in your messages. Remove anything you don't want.")).toBeTruthy();
    const list = within(screen.getByLabelText("What it learned"));
    expect(list.getByText("about 12 words")).toBeTruthy(); // how long isn't something to remove
    expect(list.getAllByRole("button").map((b) => b.textContent)).toEqual(["Remove", "Remove", "Remove"]);
    await user.click(screen.getByRole("button", { name: "Remove “paying cash” from your style" }));
    expect(sent(fetch, "POST /api/style/learned")).toEqual({ key: "mention:cash", used: false });
    await waitFor(() => expect(list.queryByText("paying cash")).toBeNull()); // gone, not greyed out (14 Oct)
    expect(screen.queryByRole("button", { name: /again/ })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Start" }));
    expect(window.location.hash).toBe("#home");
  });

  it("removes a thing your style learned from Your style for good: no Use again", async () => {
    localStorage.setItem(SETUP_DONE, "1");
    window.location.hash = "#style";
    const fetch = serve({ ...usual, "GET /api/style": [[200, STYLE], [200, NO_CASH]], "GET /api/style/messages": [200, []],
      "POST /api/style/learned": [200, NO_CASH] });
    const user = userEvent.setup();
    render(<App />);
    const card = within(await screen.findByRole("region", { name: "Style card" }));
    await user.click(await card.findByRole("button", { name: "Remove “paying cash” from your style" }));
    expect(sent(fetch, "POST /api/style/learned")).toEqual({ key: "mention:cash", used: false });
    await waitFor(() => expect(card.queryByText("paying cash")).toBeNull());
    expect(screen.queryByRole("button", { name: /again/ })).toBeNull();
    const book = within(screen.getByRole("region", { name: "Phrasebook" }));
    expect(book.getByRole("button", { name: "Remove “Cheers” from your style" })).toBeTruthy();
  });

  it("puts a sentence for one kind of offer or one marketplace in the phrasebook, and Remove deletes it", async () => {
    localStorage.setItem(SETUP_DONE, "1");
    window.location.hash = "#style";
    const only = (used: boolean): Style => ({ ...STYLE, learned: [...STYLE.learned,
      { key: "phrase:closing_lower:can collect today.", what: "Closing under asking", value: "Can collect today.", used },
      { key: "phrase:offer:would you take £[offer]?", what: "Offer sentence on eBay and Vinted", value: "Would you take £…?",
        used: true },
      { key: "ask:is it unlocked", what: "Asks every time", value: "is it unlocked?", used: true }] });
    const fetch = serve({ ...usual, "GET /api/style": [[200, only(true)], [200, only(false)]],
      "GET /api/style/messages": [200, []], "POST /api/style/learned": [200, only(false)] });
    const user = userEvent.setup();
    render(<App />);
    const book = within(await screen.findByRole("region", { name: "Phrasebook" }));
    for (const what of ["Closing under asking", "Offer sentence on eBay and Vinted", "Asks every time"]) {
      expect(await book.findByText(what)).toBeTruthy();
    }
    const card = within(screen.getByRole("region", { name: "Style card" }));
    expect(card.queryByText("Closing under asking")).toBeNull(); // not a habit on the style card
    await user.click(book.getByRole("button", { name: "Remove “Can collect today.” from your style" }));
    expect(sent(fetch, "POST /api/style/learned")).toEqual({ key: "phrase:closing_lower:can collect today.", used: false });
    await waitFor(() => expect(book.queryByText("Closing under asking")).toBeNull());
  });

  it("says Do setup before you've set up and Redo setup after; Go back returns to Your style", async () => {
    localStorage.setItem(SETUP_DONE, "1");
    window.location.hash = "#style";
    const answer = { id: "msg-1", title: "PS5", price: "300", text: "Hi mate, £255?", marketplace: "facebook", source: "added",
      at: "now" };
    const approved = { ...answer, id: "draft-3", source: "approved" };
    serve({ ...usual, "GET /api/style/messages": [[200, [approved]], [200, [answer, approved]]] });
    const user = userEvent.setup();
    const { unmount } = render(<App />);
    expect(await screen.findByRole("button", { name: "Do setup" })).toBeTruthy(); // an approved draft isn't a setup
    expect(screen.queryByRole("button", { name: /Add more/ })).toBeNull();
    unmount();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Redo setup" }));
    expect(screen.getByRole("heading", { name: "Set up your style" })).toBeTruthy();
    expect(screen.getByText(/take the place of your last setup/)).toBeTruthy();
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Go back", "Do the setup"]);
    await user.click(screen.getByRole("button", { name: "Go back" }));
    expect(await screen.findByRole("heading", { name: "Your style" })).toBeTruthy();
    expect(window.location.hash).toBe("#style");
  });

  it("redoing the setup and skipping all 6 sends nothing and keeps your style", async () => {
    localStorage.setItem(SETUP_DONE, "1");
    window.location.hash = "#style";
    const fetch = serve({ ...usual, "GET /api/style/messages": [200, [{ id: "msg-1", title: "PS5", price: "300",
      text: "Hi mate, £255?", marketplace: "facebook", source: "added", at: "now" }]] });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Redo setup" }));
    await user.click(screen.getByRole("button", { name: "Do the setup" }));
    for (let n = 1; n <= 6; n++) await user.click(screen.getByRole("button", { name: "Skip" }));
    expect(await screen.findByText("You skipped all 6, so your style stays as it was.")).toBeTruthy();
    expect(fetch.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(await screen.findByRole("heading", { name: "Your style" })).toBeTruthy();
  });

  it("goes through the 6 listings one at a time, sending only the ones you answered", async () => {
    const fetch = serve({ ...usual, "GET /api/style": [[200, NO_STYLE], [200, STYLE]],
      "PUT /api/style/setup": [200, []] });
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Do the setup" }));
    expect(screen.getByText("1 of 6")).toBeTruthy();
    expect(screen.getByText("Offer lower · £185")).toBeTruthy();
    await user.type(screen.getByLabelText("Your message to this seller"), "Hi mate, £185 given the crack?");
    await user.click(screen.getByRole("button", { name: "Next" }));
    for (let n = 2; n < 6; n++) await user.click(screen.getByRole("button", { name: "Skip" }));
    expect(screen.getByText("6 of 6")).toBeTruthy();
    expect(screen.queryByText(/Vinted|Apple Watch/)).toBeNull(); // 3 Oct: those two cards are gone
    await user.click(screen.getByRole("button", { name: "See my style" }));
    expect(await screen.findByText("Learned from 1 message")).toBeTruthy();
    expect(sent(fetch, "PUT /api/style/setup")).toEqual([{ title: "iPhone 13 128GB, cracked back", price: "220",
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
    expect(screen.getByText("FlipAssist · Home")).toBeTruthy(); // it opens on Home (4 Oct)
    expect(within(screen.getByRole("navigation")).getAllByRole("link").map((l) => l.textContent)).toEqual(
      ["Home", "AI message", "Your style", "AI UK price estimate", "List on eBay"]);
    await user.click(within(screen.getByRole("navigation")).getByText("AI message"));
    // the shown screen's box: UK price has a Listing title too, kept (hidden) while you're elsewhere
    await user.type(screen.getByRole("textbox", { name: "Listing title" }), "iPhone 13");
    expect(await screen.findByText("Ollama running")).toBeTruthy();
    expect(await screen.findByText("Learning from 14 of your messages")).toBeTruthy();
    await user.click(within(screen.getByRole("navigation")).getByText("Home"));
    expect(await screen.findByText("Done on this device")).toBeTruthy();
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
    expect(await screen.findByText("Hi mate")).toBeTruthy();
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

describe("Home (fix 2, 14 Oct)", () => {
  /** Home on its own, with /stats answering stats; reload stands in for the app's /health call. */
  const home = (running: Parameters<typeof runningRows>[0] = HEALTH, stats: unknown = STATS) => {
    serve({ "GET /api/stats": [200, stats] });
    const reload = vi.fn(async () => undefined);
    render(<HomeScreen go={vi.fn()} count={3} running={running} reload={reload} />);
    return reload;
  };

  it("says how many drafts used no paid AI at any step, with no Refresh and no buttons at the bottom", async () => {
    const reload = home();
    const hero = within(screen.getByRole("region", { name: "Done on this device" }));
    expect(await hero.findByText("80%")).toBeTruthy();
    expect(hero.getByText("of drafts used no paid AI at any step")).toBeTruthy();
    expect(hero.getByText("edited · none sent yet")).toBeTruthy();
    expect(screen.queryByText(/never needed the paid backup/)).toBeNull();
    expect(screen.queryByRole("button", { name: /Refresh/ })).toBeNull();
    expect(screen.queryByText("Message a seller")).toBeNull();
    expect(screen.queryByText("List on eBay")).toBeNull();
    expect(reload).toHaveBeenCalledTimes(1); // it loads when you open it
    expect(document.body.textContent).not.toMatch(/\bMac\b/); // it can be opened from any device
  });

  it("loads again by itself when you come back to the window", async () => {
    const reload = home();
    await screen.findByText("80%");
    window.dispatchEvent(new Event("focus"));
    await vi.waitFor(() => expect(reload).toHaveBeenCalledTimes(2));
  });

  it("counts edits out of the messages you sent", async () => {
    home(HEALTH, { ...STATS, approved: 4, edited_before_sending: 1 });
    expect(await screen.findByText("25%")).toBeTruthy();
    expect(screen.getByText("edited, of 4 sent")).toBeTruthy();
  });

  it("lists Ollama, then each of its models on its own line with its job, then each paid model and the AlertFlip API", () => {
    expect(runningRows(HEALTH).map((r) => [r.name, r.state, r.ok, !!r.model])).toEqual([
      ["Ollama", "Running on this device", true, false],
      ["flip-reader-5", "reads the listing", true, true],
      ["flip-wording-4b", "words the offer's reason", true, true],
      ["flip-kinds-1", "sorts the flaws for the UK price", true, true],
      ["flip-style-1b", "reads your style", true, true],
      ["Gemma 3 4B", "the AI writer: writes messages and eBay listings", true, true],
      ["Claude Haiku 5.5 (paid)", "Only checks each message's reason is sendable", true, false],
      ["Claude Sonnet 5.5 (paid)", "Writes when this device's models can't: fixes a reason the check flags, writes a "
        + "message or eBay listing, or reads a listing or its photos", true, false],
      ["AlertFlip API", "Fresh local sales data for the UK price estimate", true, false],
      ["FlipAssist API key", "Set", true, false],
    ]);
  });

  it("shows the running card on screen, each model on its own line", async () => {
    home();
    const card = within(screen.getByRole("region", { name: "Running" }));
    expect(card.getByText("Ollama")).toBeTruthy();
    expect(card.getByText("flip-reader-5").closest(".running")?.className).toContain("model-line");
    expect(card.getByText("Claude Haiku 5.5 (paid)").closest(".running")?.className).not.toContain("model-line");
    expect(card.getByText("Only checks each message's reason is sendable")).toBeTruthy();
    expect(card.getByText("AlertFlip API")).toBeTruthy();
  });

  it("says a model that isn't installed and what does its job instead (6 Oct review)", () => {
    expect(ollamaRows({ ...HEALTH, models: [
      { job: "reads listings", name: "flip-reader-5", installed: false },
      { job: "words the reason", name: "flip-wording-4b", installed: false }] })).toEqual([
      { name: "Ollama", ok: true, state: "Running on this device, 2 of its models not installed" },
      { name: "flip-reader-5", model: true, ok: false, state: "Not installed: Gemma 3 4B reads the listing instead" },
      { name: "flip-wording-4b", model: true, ok: false, state: "Not installed: code words the reason instead" }]);
    expect(ollamaRows({ ...HEALTH, local_running: false, models: [] }))
      .toEqual([{ name: "Ollama", ok: false, state: "Not running: start it with ollama serve" }]);
  });

  it("greys the paid models out with no Anthropic key, and names each job when another model does it", () => {
    expect(paidRows({ ...HEALTH, api_key_set: false, check_model: "", fix_model: "" })).toEqual([
      { name: "Claude Haiku 5.5 (paid)", ok: "off", state: "Off: no Anthropic key, so reasons aren't checked" },
      { name: "Claude Sonnet 5.5 (paid)", ok: "off", state: "Off: no Anthropic key, so everything runs on this device" }]);
    expect(paidRows({ ...HEALTH, api_model: "claude-haiku-5-5" }).map((r) => [r.name, r.state])).toEqual([
      ["Claude Haiku 5.5 (paid)", "Only checks each message's reason is sendable"],
      ["Claude Haiku 5.5 (paid)", "Writes when this device's models can't: writes a message or eBay listing, or reads a listing or its photos"],
      ["Claude Sonnet 5.5 (paid)", "Fixes a reason the check flags"]]);
  });

  it("says when the AlertFlip API or the key isn't set, and the API's own state before it answers", () => {
    const rows = runningRows({ ...HEALTH, prices_api_set: false, flip_api_key_set: false });
    expect(rows.slice(-2)).toEqual([
      { name: "AlertFlip API", ok: false, state: "Not set: add PRICES_URL and PRICES_KEY to .env" },
      { name: "FlipAssist API key", ok: false, state: "Missing: every draft is refused" }]);
    expect(runningRows(null)).toEqual([{ name: "FlipAssist's API", state: "Checking…", ok: true }]);
    expect(runningRows("down")[0].ok).toBe(false);
  });
});

describe("the damage cut by how bad (fix 1, 14 Oct)", () => {
  const base: PriceEstimate = { price: 147, middle: 210, currency: "GBP", cuts: ["damage"], kinds: ["damage"],
    rough: false, exact: true, kind: "iphone" };
  it("says how bad, the cut and the tier, from how many listings", () => {
    expect(damageLine({ ...base, damage: { level: "moderate", tier: "middle", cut: -0.304, rough: false, n: 191 } }))
      .toBe("Damage counted as moderate: −30% for a mid-priced iPhone, from 191 listings like it");
    expect(damageLine({ ...base })).toBe("");
  });
  it("says where a rough one came from", () => {
    const samsung = { ...base, kind: "samsung", damage: { level: "minor", tier: "top", cut: -0.059, rough: true,
      from: "the US", n: 11 } };
    expect(damageLine(samsung)).toBe("Damage counted as minor: −6% for a pricier Samsung, from 11 listings like it "
      + "(rough: from US sales)");
  });
  it("doesn't call a MacBook's damage cut one measured on phones", () => {
    const mac = { ...base, kind: "macbook", model: "macbook air 13 m1", sales: 40, exact: true,
      damage: { level: "minor", tier: "middle", cut: -0.133, rough: false, n: 11 } };
    expect(cautions(mac, "MacBook Air M1").some((c) => c.includes("measured on phones"))).toBe(false);
    expect(cautions({ ...mac, cuts: ["damage", "fault"], kinds: ["damage", "fault"] }, "MacBook Air M1")
      .some((c) => c.includes("measured on phones"))).toBe(true);
  });
});
