import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App, markShell, SETUP_DONE, THEME } from "../App";
import type { Attempt, CutRow, ListingDraft, MessageDraft, PriceEstimate, Style } from "../api";
import { Steps } from "../ui";
import { ListingScreen } from "../screens/ListingScreen";
import { HomeScreen, ollamaRows, paidRows, runningRows } from "../screens/HomeScreen";
import { MessageScreen } from "../screens/MessageScreen";
import { cautions, cutWords, damageLine, itemName, poundsOff, PriceScreen, sortedBy } from "../screens/PriceScreen";

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
const STATS = { drafts: 2, ready: 2, needs_you: 0, outputs_here: 40, outputs: 50, models: [], cost_pence: 0,
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
    await user.click(screen.getByRole("button", { name: "Yes" })); // the counts come once you click Yes (14 Oct)
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

  it("starts an offer lower at Yes too (9 Nov), shows the counts, and writes nothing until you pick how many", async () => {
    const fetch = serve({ "POST /api/messages/draft": [200, DRAFT] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    // the owner, 9 Nov: "make say flaws on like pay asking price and offer more": Yes to start with (No is a click
    // away), and how many flaws is still yours to pick
    expect(["Yes", "No"].map((n) => screen.getByRole("button", { name: n }).getAttribute("aria-pressed")))
      .toEqual(["true", "false"]);
    expect(screen.queryByRole("button", { name: "My style" })).toBeNull();
    await user.type(screen.getByLabelText("Listing title"), "iPhone 13 128GB Blue");
    await user.type(screen.getByLabelText("Asking price"), "£220");
    const counts = within(screen.getByRole("group", { name: "How many flaws to say" }));
    expect(counts.getAllByRole("button").map((b) => [b.textContent, b.getAttribute("aria-pressed")])).toEqual(
      [["1 flaw only", "false"], ["2 flaws only", "false"], ["3 flaws only", "false"], ["All flaws", "false"]]);
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
    await user.click(screen.getByRole("button", { name: "Yes" }));
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

  it("lets you say you don't mind the flaw when paying asking or more, and starts at Yes there (4 Nov)", async () => {
    const fetch = serve({ "POST /api/messages/draft": [[200, { ...DRAFT, kind: "asking" }], [200, { ...DRAFT, kind: "more" }],
      [200, { ...DRAFT, kind: "asking" }], [200, { ...DRAFT, kind: "more" }]] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await user.type(screen.getByLabelText("Listing title"), "iPhone 13 128GB Blue");
    await user.type(screen.getByLabelText("Asking price"), "£220");
    const writeOrRewrite = () => screen.queryByRole("button", { name: "Write my message" })
      ?? screen.getByRole("button", { name: "Rewrite" });
    // the owner, 4 Nov: "it become on the yes always at the start unless they change it"; how many is still yours
    for (const [card, n] of [["Pay asking", 2], ["Offer more", 3]] as const) {
      await user.click(screen.getByRole("radio", { name: new RegExp(card) }));
      expect(screen.getByText("Say you don't mind the flaw")).toBeTruthy();
      expect(screen.getByRole("button", { name: "Yes" }).getAttribute("aria-pressed")).toBe("true");
      expect(screen.getByRole("group", { name: "How many flaws to say" })).toBeTruthy();
      await user.click(writeOrRewrite());
      expect(screen.getByText("Pick how many flaws to say")).toBeTruthy(); // nothing written until you pick how many
      await user.click(screen.getByRole("button", { name: `${n} flaws only` }));
      await user.click(writeOrRewrite());
      await screen.findByDisplayValue(DRAFT.message!);
    }
    const [askingYes, moreYes] = [sent(fetch, "POST /api/messages/draft", 0), sent(fetch, "POST /api/messages/draft", 1)];
    expect([askingYes.kind, askingYes.mention, askingYes.flaws_said]).toEqual(["asking", true, 2]);
    expect([moreYes.kind, moreYes.mention, moreYes.flaws_said]).toEqual(["more", true, 3]);
    // No, when you change it: no flaw said (at Offer more your style decides whether to say it's in good condition)
    for (const card of ["Pay asking", "Offer more"]) {
      await user.click(screen.getByRole("radio", { name: new RegExp(card) }));
      await user.click(screen.getByRole("button", { name: "No" }));
      expect(screen.queryByRole("group", { name: "How many flaws to say" })).toBeNull();
      await user.click(writeOrRewrite());
    }
    await vi.waitFor(() => expect(fetch.mock.calls.filter(([url]) => url === "/api/messages/draft").length).toBe(4));
    const [asking, more] = [sent(fetch, "POST /api/messages/draft", 2), sent(fetch, "POST /api/messages/draft", 3)];
    expect([asking.kind, asking.mention, asking.flaws_said]).toEqual(["asking", false, null]);
    expect([more.kind, more.mention, more.flaws_said]).toEqual(["more", null, null]);
    await user.click(screen.getByRole("radio", { name: /Offer lower/ }));
    expect(screen.getByText("Say the flaw")).toBeTruthy();
    // each card its own: No was picked for Pay asking, and an offer lower is still at Yes (9 Nov: Yes to start with)
    expect(screen.getByRole("button", { name: "Yes" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "No" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("sends the same listing's reading and checked reason back on another offer, and reads a changed one afresh (9 Nov)", async () => {
    // the owner: "when we do one and we not change the listing ... get the flaws that the reader found straight from
    // the previous request do not read it again"
    const first = { ...DRAFT, reason: { clause: "there's a black dot on the screen", by: "flip-wording-4b", checked: "ok" } };
    const fetch = serve({ "POST /api/messages/draft": [[200, first], [200, { ...first, kind: "asking" }],
      [200, { ...first, kind: "asking", draft_id: 9 }]] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await user.type(screen.getByLabelText("Listing title"), "iPhone 13 128GB Blue");
    await user.type(screen.getByLabelText("Asking price"), "£220");
    await user.click(screen.getByRole("button", { name: "1 flaw only" }));
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    await screen.findByDisplayValue(DRAFT.message!);
    expect(sent(fetch, "POST /api/messages/draft", 0).reading).toBeNull(); // the first draft reads it
    await user.click(screen.getByRole("radio", { name: /Pay asking/ }));
    await user.click(screen.getByRole("button", { name: "1 flaw only" }));
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    await vi.waitFor(() => expect(fetch.mock.calls.filter(([url]) => url === "/api/messages/draft").length).toBe(2));
    const again = sent(fetch, "POST /api/messages/draft", 1);
    expect(again.reading).toEqual({ flaws: DRAFT.reading.flaws, quotes: DRAFT.reading.quotes, pickup: DRAFT.reading.pickup,
      no_offers: DRAFT.reading.no_offers, read_by: DRAFT.reading.read_by });
    expect(again.reason.clause).toBe("there's a black dot on the screen"); // worded and checked once, kept
    await screen.findAllByDisplayValue(DRAFT.message!);
    await user.type(screen.getByLabelText("The seller's description"), "Battery 80%.");
    await user.click(screen.queryByRole("button", { name: "Write my message" }) ?? screen.getByRole("button", { name: "Rewrite" }));
    await vi.waitFor(() => expect(fetch.mock.calls.filter(([url]) => url === "/api/messages/draft").length).toBe(3));
    const changed = sent(fetch, "POST /api/messages/draft", 2);
    expect([changed.reading, changed.reason]).toEqual([null, null]); // a changed listing is read and worded afresh
  });

  it("writes every message with no AI, and only Rewrite has Gemma 3 4B reword it (14 Oct)", async () => {
    const fetch = serve({ "POST /api/messages/draft": [[200, DRAFT], [200, { ...DRAFT, draft_id: 8, message: "reworded" }],
      [200, { ...DRAFT, draft_id: 9 }]] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    expect(screen.queryByRole("group", { name: "Writer" })).toBeNull(); // no writer to pick
    expect(screen.queryByRole("button", { name: /AI writer|No AI writing|Auto/ })).toBeNull();
    await draft(user);
    expect(sent(fetch, "POST /api/messages/draft").writer).toBe("template");
    const rewriteButton = screen.getByRole("button", { name: "Rewrite" });
    expect(rewriteButton.hasAttribute("disabled")).toBe(false);
    expect(rewriteButton.getAttribute("title")).toBe("Gemma 3 4B rewords it on this device, keeping the price, the facts "
      + "and the checked reason word for word; Claude Sonnet 5.5 (paid) does it when Gemma 3 4B's tries fail code's checks");
    await user.click(rewriteButton);
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

  it("checks the reason against only the flaws you picked, and keeps them for Rewrite", async () => {
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
    await user.click(screen.getByRole("button", { name: "Rewrite" }));
    const rewrite = sent(fetch, "POST /api/messages/draft", 1);
    expect([rewrite.reason.quotes, rewrite.flaws_said]).toEqual([picked, 1]);
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
    expect(screen.getByText("Reason by flip-wording-3 · Claude Haiku 5.5 checking…")).toBeTruthy();
    await user.type(box, " Thanks");
    release();
    expect(await screen.findByText("Reason flagged by Claude Haiku 5.5, fixed by Claude Sonnet 5.5")).toBeTruthy();
    expect(screen.getByDisplayValue(`${DRAFT.message} Thanks`)).toBeTruthy();  // yours stays
  });

  // a reason Claude Haiku 5.5 flags goes to Claude Sonnet 5.5, and "flagged, kept" comes back however it was kept
  // (4 Nov): the check's steps and problems say whether Sonnet read it and kept it
  const flaggedReason = { clause: "there's a dot on the screen", by: "flip-wording-4b", checked: "flagged, kept" };
  const haikuStep: Attempt = { model: "claude-haiku-5-5", problems: [], seconds: 1, cost_pence: 0.008, job: "reason" };
  const sonnetStep: Attempt = { model: "claude-sonnet-5-5", problems: [], seconds: 1.4, cost_pence: 0.152, job: "reason" };
  const toCheck: MessageDraft = { ...DRAFT, reason: { ...flaggedReason, checked: "pending" } };

  it("says Claude Sonnet 5.5 kept the reason when it checked one Claude Haiku 5.5 flagged and kept it, and still after Rewrite (4 Nov)", async () => {
    const fetch = serve({ "POST /api/messages/draft": [[200, toCheck],
      [200, { ...toCheck, draft_id: 8, message: "reworded", reason: flaggedReason }]],  // Rewrite keeps the reason on screen
      "POST /api/messages/check-reason": [200, { reason: flaggedReason, message: toCheck.message, changed: false,
        problems: [], attempts: [haikuStep, sonnetStep], cost_pence: 0.16 }] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await draft(user);
    const keptBySonnet = "Reason by flip-wording-4b · flagged by Claude Haiku 5.5, kept by Claude Sonnet 5.5";
    expect(await screen.findByText(keptBySonnet)).toBeTruthy();
    expect(screen.queryByText(/kept as written/)).toBeNull();
    await user.click(screen.getByRole("button", { name: "Rewrite" }));
    expect(await screen.findByDisplayValue("reworded")).toBeTruthy();
    expect(screen.getByText(keptBySonnet)).toBeTruthy();  // the same reason, kept by the same model
    // the API gets its own reason back, with nothing of the screen's in it, and it isn't checked or paid for again
    expect(sent(fetch, "POST /api/messages/draft", 1).reason).toEqual({ ...flaggedReason, quotes: DRAFT.reading.flaws });
    expect(fetch.mock.calls.filter(([url]) => url === "/api/messages/check-reason")).toHaveLength(1);
  });

  it("still says kept as written when Claude Sonnet 5.5 couldn't answer, isn't set up, or its fix couldn't go in", async () => {
    const leftOut = "the message words the reason its own way, so Claude Sonnet 5.5's fix wasn't put in";
    for (const { attempts, problems } of [
      { attempts: [haikuStep, { ...sonnetStep, problems: ["the fix couldn't run (APITimeoutError)"] }], problems: [] },  // no answer
      { attempts: [haikuStep], problems: [] },  // no Sonnet to ask
      { attempts: [haikuStep, sonnetStep], problems: [leftOut] },  // Sonnet fixed it, but the message kept flip-wording's
    ]) {
      serve({ "POST /api/messages/draft": [200, toCheck],
        "POST /api/messages/check-reason": [200, { reason: flaggedReason, message: toCheck.message, changed: false,
          problems, attempts, cost_pence: 0.16 }] });
      const user = userEvent.setup();
      render(<MessageScreen />);
      await draft(user);
      expect(await screen.findByText("Reason by flip-wording-4b · flagged by Claude Haiku 5.5, kept as written")).toBeTruthy();
      problems.forEach((p) => expect(screen.getByText(p)).toBeTruthy());  // and why Sonnet's fix isn't in it
      cleanup();
    }
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

  it("names who writes it: your sentences with no AI, and Gemma 3 4B only to reword", async () => {
    serve({ "POST /api/messages/draft": [200, DRAFT] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await draft(user);
    expect(screen.getByText(/^No AI writing · /)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Rewrite" }).getAttribute("title")).toMatch(/^Gemma 3 4B rewords it/);
  });

  it("shows why, step by step", async () => {
    serve({ "POST /api/messages/draft": [200, DRAFT] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await draft(user);
    await user.click(screen.getByRole("button", { name: /Why · 2 steps/ }));
    // each step by its job and who did it (14 Oct): the reading first, then the writing
    expect(screen.getByText("Reading the listing · Gemma 3 4B (on this device) passed")).toBeTruthy();
    expect(screen.getByText("Writing the message · No AI writing passed")).toBeTruthy();
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
    expect(screen.getByText("Saved to My style")).toBeTruthy();
    expect(sent(fetch, "POST /api/drafts/7/approve").sent).toBe(DRAFT.message + " Cheers");
    expect(approved).toHaveBeenCalled();
    expect(await navigator.clipboard.readText()).toBe(DRAFT.message + " Cheers");
  });

  it("rewrites keeping the checked reason on screen, not wording it again", async () => {
    const checkedReason = { clause: "there's a black dot on the screen", by: "claude-sonnet-5-5", checked: "fixed" };
    const fetch = serve({ "POST /api/messages/draft": [[200, { ...DRAFT, reason: checkedReason }],
      [200, { ...DRAFT, draft_id: 8, reason: checkedReason }]] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await draft(user);
    await user.click(screen.getByRole("button", { name: "Rewrite" }));
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

  it("has My style On or Off above Say the flaw: Off writes the default way and teaches it nothing (14 Oct)", async () => {
    const fetch = serve({ "POST /api/messages/draft": [[200, DRAFT], [200, { ...DRAFT, draft_id: 8 }]],
      "POST /api/drafts/8/approve": [200, { draft_id: 8, edited: false, at: "now", saved_to_style: false }] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    const groups = screen.getAllByRole("group").map((g) => g.getAttribute("aria-label"));
    expect(groups.indexOf("My style")).toBe(groups.indexOf("Say the flaw") - 1); // right above it
    const row = within(screen.getByRole("group", { name: "My style" }));
    expect(row.getByText("My style")).toBeTruthy();
    expect(row.getAllByRole("button").map((b) => [b.textContent, b.getAttribute("aria-pressed")])).toEqual(
      [["On", "true"], ["Off", "false"]]);  // On until you turn it off
    await draft(user);
    expect(sent(fetch, "POST /api/messages/draft").style).toBe(true);
    await user.click(row.getByRole("button", { name: "Off" }));
    expect(localStorage.getItem("flipassist.myStyle")).toBe("off");  // remembered on this device
    await user.click(screen.getByRole("button", { name: "Rewrite" }));
    expect(sent(fetch, "POST /api/messages/draft", 1).style).toBe(false);
    await user.click(await screen.findByRole("button", { name: "Copy & approve" }));
    expect(sent(fetch, "POST /api/drafts/8/approve").learn).toBe(false);
    localStorage.removeItem("flipassist.myStyle");
  });

  it("has no Make it longer: every message is the usual length (14 Oct, the owner)", async () => {
    const fetch = serve({ "POST /api/messages/draft": [[200, DRAFT], [200, { ...DRAFT, draft_id: 8 }]] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await draft(user);
    expect(screen.queryByRole("button", { name: /Make it (longer|shorter)/ })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Rewrite" }));
    const rewrite = sent(fetch, "POST /api/messages/draft", 1);
    expect([rewrite.length, rewrite.previous, rewrite.rewrite_of]).toEqual(["usual", null, DRAFT.message]);
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
    await user.click(screen.getByRole("button", { name: "Yes" }));
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
    const how = [...screen.getByLabelText("How it works").querySelectorAll(":scope > ol > li")].map((li) => li.textContent!);
    expect(how.map((step) => step.split(/[,:.]| keeps/)[0])).toEqual(["AlertFlip API",
      "The middle price of clean ones of the same model and size is sent here", "flip-reader-5", "flip-kinds-1",
      "The price is cut for each kind"]);
    expect(screen.queryAllByRole("paragraph").filter((p) => p.className === "warn-row")).toHaveLength(0);
    expect(document.body.textContent).not.toMatch(/ebay/i);
    expect(sent(fetch, "POST /api/prices/estimate")).toEqual(
      { title: "iPhone 13 128GB Blue", description: "Cracked back, battery 81%" });
  });

  it("says when the price was asked for the model the description names (9 Nov)", async () => {
    serve({ "POST /api/prices/estimate": [200, { ...PRICED, asked_title: "MacBook Pro 15 inch 2018 Core i7" }] });
    const user = userEvent.setup();
    render(<PriceScreen />);
    await user.type(screen.getByLabelText("Listing title"), "MacBook Pro 15 inch");
    await user.type(screen.getByLabelText("The seller's description"), "Apple MacBook Pro 15 (2018) Core i7");
    await user.click(screen.getByRole("button", { name: "Check the UK price" }));
    expect((await screen.findByLabelText("UK price")).textContent)
      .toContain("Priced as “MacBook Pro 15 inch 2018 Core i7”, with the model details from the description");
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

  // 14 Oct, the owner: "give real description like here we had 2 flaws". The card said "Damage counted as moderate:
  // −30%" for a price cut 42%: now each flaw has its own row in the seller's words, with what it takes off in pounds.
  const TWO_FLAWS: PriceEstimate = { ...PRICED, price: 139, middle: 239.6, low: 220, high: 255, sales: 24,
    model: "iphone 14", asked_storage_gb: null, kinds: ["damage", "fault"], cuts: ["fault", "damage"],
    flaws: ["cracked back and the balck dot in the front screen"], sorted_by: "flip-kinds-1",
    damage: { level: "moderate", tier: "middle", cut: -0.304, rough: false, from: null, n: 191,
      by: "code and Claude Haiku 5.5" },
    breakdown: [
      { kinds: ["damage"], words: ["Cracked back"], title: false, cut: -0.304, by: "damage" },
      { kinds: ["fault"], words: ["The balck dot in the front screen"], title: false, cut: -0.171, by: "api" }],
    not_cut: [] };

  it("gives each flaw its own row in the seller's words, with what it takes off, adding up to the price", async () => {
    const got = await check("iphone 14", "cracked back and the balck dot in the front screen", TWO_FLAWS);
    expect(got.hero).toContain("−42%cut for its flaws");
    const flaws = screen.getByLabelText("Flaws it found");
    expect(within(flaws).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Cracked back−£73Damage, counted as moderate: −30%. UK sellers ask about 30% less for a mid-priced iPhone with "
        + "moderate damage (191 listings) · how bad: code and Claude Haiku 5.5",
      "The balck dot in the front screen−£28Fault: −17%. UK sellers ask about 17% less for one with a fault (the "
        + "AlertFlip API's cut)"]);
    expect(screen.getByLabelText("How the cuts add up").textContent).toBe("£240 with no flaws − £73 − £28 = £139");
    expect(flaws.textContent).toContain("Read by flip-reader-5 (on this device) · sorted by flip-kinds-1");
    expect(flaws.textContent).not.toContain("Damage counted as moderate");  // the old line, said once for every flaw
  });

  it("works out each row's pounds so they always add up to the price", () => {
    const row = (cut: number | null): CutRow => ({ kinds: ["wear"], words: ["x"], cut, by: cut == null ? null : "api" });
    expect(poundsOff([row(-0.3), row(-0.17)], 240, 139)).toEqual([72, 29]);  // £240 → £168 → £139
    expect(poundsOff([row(-0.304), row(null), row(-0.046)], 239.6, 159)).toEqual([73, null, 8]);  // £240 → £167 → £159
    for (const [middle, price] of [[239.6, 139], [175, 150], [999.5, 412]]) {
      const offs = poundsOff([row(-0.2), row(-0.1), row(-0.05)], middle, price);
      expect(Math.round(middle) - offs.reduce((a: number, b) => a + (b ?? 0), 0)).toBe(price);
    }
  });

  it("says what each kind of cut is, in plain words", () => {
    const e = { ...TWO_FLAWS, damage: { ...TWO_FLAWS.damage!, rough: true, from: "the US", by: "Claude Sonnet 5.5" } };
    const said = (row: Partial<CutRow>) => cutWords({ kinds: ["fault"], words: ["x"], cut: -0.171, by: "api", ...row }, e);
    expect(said({ kinds: ["damage"], cut: -0.304, by: "damage" })).toBe("Damage, counted as moderate: −30%. Sellers "
      + "ask about 30% less for a mid-priced iPhone with moderate damage (191 listings, rough) · Claude "
      + "Sonnet 5.5 decided how bad");
    expect(said({ kinds: ["battery"], cut: -0.048 })).toBe("Worn battery (under 80% or needs a service): −5%. UK sellers "
      + "ask about 5% less for one with a worn battery (the AlertFlip API's cut)");
    expect(said({ kinds: ["battery", "wear"], cut: -0.093, by: "api together" })).toBe("Worn battery (under 80% or needs a "
      + "service) and Wear: −9% together. UK sellers ask about 9% less for one with all of these (the AlertFlip API's cuts)");
    expect(said({ kinds: ["lock"], cut: -0.71, by: "parts price" }))
      .toBe("Locked: −71%, priced at what for-parts ones of this model sell for");
    expect(said({ kinds: ["lock"], cut: -0.38, by: "lock" }))
      .toBe("Locked: −38%, a rough cut (too few for-parts sales of this model to go on)");
    expect(cutWords({ kinds: ["damage"], words: ["x"], cut: null, by: "not on top" }, { ...e, parts_price: true }))
      .toBe("Damage: not cut on top of the for-parts price");
  });

  it("says the owner's battery cut, with the figure it went by", () => {
    // 14 Oct, the owner: "make the battery cut bigger for under 80%", by how low it is
    const rule = "FlipAssist's battery cut: 10% off at 75–79%, 15% at 70–74% or with no figure, 20% under 70%";
    const row: CutRow = { kinds: ["battery"], words: ["The battery is 75%"], cut: -0.1, by: "battery" };
    expect(cutWords(row, { ...TWO_FLAWS, battery: { figure: 75, cut: -0.1 } })).toBe(`Battery at 75%: −10%. ${rule}`);
    expect(cutWords({ ...row, cut: -0.15 }, { ...TWO_FLAWS, battery: { figure: null, cut: -0.15 } }))
      .toBe(`Worn battery, no figure given: −15%. ${rule}`);
    // the battery cut is the owner's rule, not one measured on phones: no "rough for a MacBook" for it
    expect(cautions({ ...PRICED, kind: "macbook", model: "macbook air 13 m1", ram_gb: 8, asked_ram_gb: 8, kinds: ["battery"],
      cuts: ["battery"], battery: { figure: 75, cut: -0.1 } })).toEqual([]);
  });

  it("puts a locked one's price first and the flaws not cut on top after it, and names what wasn't cut for", async () => {
    await check("iphone 14", "iCloud locked, screen smashed. No charger.", { ...TWO_FLAWS, price: 70, kinds: ["lock", "damage"],
      cuts: [], parts_price: true, damage: null, flaws: ["iCloud locked, screen smashed.", "No charger."],
      breakdown: [{ kinds: ["lock"], words: ["iCloud locked"], title: false, cut: 70 / 239.6 - 1, by: "parts price" },
        { kinds: ["damage"], words: ["Screen smashed"], title: false, cut: null, by: "not on top" }],
      not_cut: ["No charger"] });
    const flaws = screen.getByLabelText("Flaws it found");
    expect(within(flaws).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "iCloud locked−£170Locked: −71%, priced at what for-parts ones of this model sell for",
      "Screen smashed–Damage: not cut on top of the for-parts price"]);
    expect(screen.getByLabelText("How the cuts add up").textContent).toBe("£240 with no flaws − £170 = £70");
    expect(flaws.textContent).toContain("Not cut for: No charger");
  });

  it("names a flaw only the title gives as the title's", async () => {
    await check("iPhone 13 128GB cracked back", "Collection only from Leeds.", { ...PRICED, price: 190, middle: 220,
      kinds: ["damage"], cuts: ["damage"], flaws: [], damage: { level: "moderate", tier: "middle", cut: -0.136,
        rough: false, from: null, n: 191, by: "code" },
      breakdown: [{ kinds: ["damage"], words: ["iPhone 13 128GB cracked back"], title: true, cut: -0.136, by: "damage" }] });
    const flaws = screen.getByLabelText("Flaws it found");
    expect(flaws.textContent).toContain("None quoted from the description.");
    expect(within(flaws).getAllByRole("listitem")[0].textContent).toMatch(/^In the title: iPhone 13 128GB cracked back−£30/);
  });

  it("words each row as the cut was made (14 Oct review)", () => {
    const row = (r: Partial<CutRow>): CutRow => ({ kinds: ["fault"], words: ["x"], cut: -0.171, by: "api", ...r });
    // a Samsung's damage cut is borrowed from US listings: what sellers ask, not UK ones, and no "US" (9 Nov)
    const samsung = { ...TWO_FLAWS, kind: "samsung", damage: { level: "moderate", tier: "middle", cut: -0.444, rough: true,
      from: "the US (pooled with the bottom tier)", n: 17, by: "code" } };
    expect(cutWords(row({ kinds: ["damage"], cut: -0.444, by: "damage" }), samsung)).toBe("Damage, counted as moderate: "
      + "−44%. Sellers ask about 44% less for a mid-priced Samsung with moderate damage (17 listings, rough) · how bad: "
      + "code");
    // no for-parts sales to go on: the API's rough cut for a locked one, which nothing is cut on top of
    const locked = { ...TWO_FLAWS, parts_price: false, breakdown: [row({ kinds: ["lock"], cut: -0.38, by: "lock" }),
      row({ kinds: ["damage"], cut: null, by: "not on top" })] };
    expect(cutWords(locked.breakdown[1], locked)).toBe("Damage: not cut on top of the rough cut for a locked one");
    expect(cutWords(locked.breakdown[1], { ...locked, parts_price: true }))
      .toBe("Damage: not cut on top of the for-parts price");
    // wear after a fault adds nothing on top, as the API takes it
    expect(cutWords(row({ kinds: ["wear"], cut: null, by: "api none" }), TWO_FLAWS))
      .toBe("Wear: no more off, as it's counted in the cut above (the AlertFlip API's way)");
    // a MacBook's API cut was measured on phones
    expect(cutWords(row({}), { ...TWO_FLAWS, kind: "macbook" })).toBe("Fault: −17%. UK sellers ask about 17% less for "
      + "one with a fault (the AlertFlip API's cut, measured on phones)");
  });

  it("shows a cut that rounds to nothing as a dash, and leaves it out of the sum", async () => {
    await check("iPhone 8 64GB", "Small scratches on the frame", { ...PRICED, price: 50, middle: 50, low: 45, high: 55,
      kinds: ["wear"], cuts: ["wear"], damage: null, flaws: ["Small scratches on the frame"],
      breakdown: [{ kinds: ["wear"], words: ["Small scratches on the frame"], title: false, cut: -0.048, by: "api" }] });
    const flaws = screen.getByLabelText("Flaws it found");
    expect(within(flaws).getAllByRole("listitem")[0].textContent).toMatch(/^Small scratches on the frame–Wear: −5%/);
    expect(screen.queryByLabelText("How the cuts add up")).toBeNull();
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

  it("says how flaws cut the price a step at a time, with no counts or amounts that could go stale (4 Nov)", () => {
    // the owner, 4 Nov: the sales sorting a small line under the API; the reader, the sorter and the cuts a step each;
    // no "2,404 damaged"; clean and readable
    render(<PriceScreen />);
    const card = screen.getByLabelText("How it works");
    const steps = [...card.querySelectorAll(":scope > ol > li")];
    expect(steps).toHaveLength(5);
    expect(steps[0].querySelector(".how-sub")?.textContent).toBe("Claude Haiku 5.5 sorts each sale: its model, storage, a "
      + "MacBook's RAM, its condition and its flaws.");
    expect(steps[2].textContent).toBe("flip-reader-5, FlipAssist's own model on this device, reads the title and description "
      + "for flaws. If its reading fails code's checks, Claude Sonnet 5.5 reads it instead (a paid call).");
    expect(steps[3].textContent).toBe("flip-kinds-1, FlipAssist's own model on this device, sorts each flaw into a kind: "
      + "damage, a fault, a worn battery, wear and so on. Code's rules sort them when it isn't installed.");
    expect([...steps[4].querySelectorAll("li")].map((li) => li.textContent)).toEqual([
      "Any flaw takes a small cut, counted once. Each other flaw adds its own cut on top, and faults cut the most.",
      "Damage is cut by how bad it is (minor, moderate or severe) and how pricey the model is.",
      "A worn battery is cut by how low its health is, as it has to be replaced.",
      "A locked or for-parts one is priced at what for-parts ones of the same model and size sell for, or at a rough "
        + "guess when too few have sold. Its other flaws aren't cut on top."]);
    expect(card.textContent).not.toMatch(/\d\s?%|per ?cent|\d,\d{3}/);  // the cut tables are measured and can change
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

  it("gives a Samsung's and a MacBook's own cuts in words, and calls none of them measured on phones (4 Nov)", () => {
    // the owner: "MacBook cuts are rough: the flaw percentages were measured on phones. yh do them for sumsungs and
    // macbook": each kind is measured on the category's own UK listings now (data/kind_cuts.json)
    const own = (cut: number, n: number, from: string | null = null) => ({ cut, n, rough: from != null, from });
    const samsung: PriceEstimate = { ...PRICED, kind: "samsung", model: "galaxy s21", kinds: ["fault", "network lock",
      "wear"], cuts: ["fault", "network lock", "wear"], own_cuts: { fault: own(-0.333, 168),
      "network lock": own(-0.16, 139), wear: own(-0.125, 598) } };
    const row = (r: Partial<CutRow>): CutRow => ({ kinds: ["fault"], words: ["x"], cut: -0.333, by: "own", ...r });
    expect(cutWords(row({}), samsung)).toBe("Fault: −33%. UK sellers ask about 33% less for a Samsung with a fault "
      + "than a flawless one (168 Samsung listings)");
    // beside a worse flaw, only its part on top of the cut any flaw takes
    expect(cutWords(row({ kinds: ["network lock"], cut: -0.04 }), samsung)).toBe("Network locked: −4% more. UK "
      + "sellers ask about 16% less for a network-locked Samsung than a flawless one (139 Samsung listings); the part "
      + "any flaw takes is counted once, above");
    expect(cutWords(row({ kinds: ["wear"], cut: null, by: "own none" }), samsung))
      .toBe("Wear: no more off, as the cut any flaw takes is counted once, in the cut above");
    // too few MacBooks with parts that aren't genuine: the iPhone's, and rough
    const mac: PriceEstimate = { ...PRICED, kind: "macbook", model: "macbook air 13 m1", kinds: ["not genuine", "wear"],
      cuts: ["not genuine", "wear"], own_cuts: { "not genuine": own(-0.108, 100, "the iPhone"), wear: own(-0.048, 532) } };
    expect(cutWords(row({ kinds: ["not genuine"], cut: -0.108 }), mac)).toBe("Parts that aren't genuine: −11%. UK "
      + "sellers ask about 11% less for an iPhone with parts that aren't genuine than a flawless one (100 iPhone "
      + "listings: too few MacBooks had it, so it's rough)");
    expect(cautions(mac).some((c) => c.includes("measured on phones"))).toBe(false);
    expect(cautions(mac)).toContain("Rough for a MacBook: the not genuine cut is the iPhone's, as too few MacBooks had it");
    expect(cautions({ ...mac, kinds: ["wear"], cuts: ["wear"], own_cuts: { wear: own(-0.048, 532) } })).toEqual([]);
    // locked, too few for-parts sales: its own measured cut, rough as 25 is few
    const locked: PriceEstimate = { ...samsung, kinds: ["lock"], cuts: ["lock"], own_cuts: null, rough: true,
      own_whole: { kind: "lock", ...own(-0.516, 25, "few listings") } };
    expect(cutWords(row({ kinds: ["lock"], cut: -0.516, by: "own lock" }), locked)).toBe("Locked: −52%. UK sellers "
      + "ask about 52% less for a locked Samsung than a flawless one (25 Samsung listings, rough: few listings); too few "
      + "for-parts sales of this model to go on");
    expect(cautions({ ...locked, kind: "macbook" }).some((c) => c.includes("measured on phones"))).toBe(false);
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
    await user.type(screen.getByLabelText("Which iPhone"), "iphone 13 128gb");
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
    await user.type(screen.getByLabelText("Which iPhone"), "iphone 13 128gb");
    await user.click(screen.getByRole("button", { name: "Draft listing" }));
    expect(await screen.findByText("Midnight (from the photos, by Claude Haiku 5.5)")).toBeTruthy();
    // a phone's eBay Colour field says who picked it too
    cleanup();
    serve({ "POST /api/listings/draft": [200, { ...LISTED, colour: "Midnight", colour_from: "photos",
      colour_by: "claude-haiku-5-5", ebay_category: { id: "9355", name: "Mobile & Smart Phones", path: "Mobile Phones" },
      item_specifics: [{ name: "Colour", value: "Black", required: true, source: "the photos: Midnight", options: ["Black"] }],
      attempts: LISTED.attempts, cost_pence: 0 }] });
    render(<ListingScreen />);
    await user.type(screen.getByLabelText("Which iPhone"), "iphone 13 128gb");
    await user.click(screen.getByRole("button", { name: "Draft listing" }));
    expect(await screen.findByText("from the photos: Midnight, by Claude Haiku 5.5")).toBeTruthy();
    cleanup();
    serve({ "POST /api/listings/draft": [200, { ...LISTED, colour: "Midnight", colour_from: "photos",
      colour_by: "claude-haiku-5-5", attempts: [LISTED.attempts[0],
        { model: "claude-haiku-5-5", problems: [], seconds: 2.1, cost_pence: 0.0125, colour_only: true }],
      cost_pence: 0.0125 }] });
    render(<ListingScreen />);
    await user.type(screen.getByLabelText("Which iPhone"), "iphone 13 128gb");
    await user.click(screen.getByRole("button", { name: "Draft listing" }));
    await screen.findByText("Midnight (from the photos, by Claude Haiku 5.5)");
    expect(screen.getByText(/^Gemma 3 4B \(on this device\) ·/)).toBeTruthy(); // Gemma wrote it; Haiku only looked at the colour
    await user.click(screen.getByRole("button", { name: "Why" }));
    expect(screen.getByText("Looking at the colour · Claude Haiku 5.5 (paid) passed")).toBeTruthy();
    expect(screen.getByText("Writing the listing · Gemma 3 4B (on this device) passed")).toBeTruthy();
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
    await user.type(screen.getByLabelText("Which iPhone"), "iphone 13 128gb");
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
    await user.type(screen.getByLabelText("Which iPhone"), "iphone 13 128gb unlocked");
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

  it("says it's for iPhones only and writes from your title and notes alone: no seller's description box", async () => {
    // 14 Oct (the owner): iPhones only, said on the page; written from your notes, as AlertFlip's List on eBay is
    const fetch = serve({ "POST /api/listings/draft": [200, LISTED] });
    const user = userEvent.setup();
    render(<ListingScreen />);
    expect(screen.getByText("iPhones only · your notes and photos · a checked eBay draft")).toBeTruthy();
    expect(screen.getByText(/^For iPhones only\. Add photos and your notes/)).toBeTruthy();
    cleanup();
    render(<ListingScreen writer="claude-haiku-5-5" />);  // who writes, as /health says
    expect(screen.getByText(/Claude Haiku 5\.5 \(Claude Sonnet 5\.5 if a check fails\) writes the rest from your notes/))
      .toBeTruthy();
    cleanup();
    // 14 Oct: flip-reader-5 reads your notes and Claude Haiku 5.5 phrases what it found (FLIP_LISTING_WRITER=notes: as above)
    render(<ListingScreen writer="claude-haiku-5-5" reader="flip-reader-5" />);
    expect(screen.getByText(/Code fills the specs, flip-reader-5 reads your notes, and Claude Haiku 5\.5 \(Claude Sonnet 5\.5 if a check fails\) writes the rest from what it found\./))
      .toBeTruthy();
    cleanup();
    render(<ListingScreen />);
    expect(screen.queryByLabelText("The seller's description")).toBeNull();
    await user.type(screen.getByLabelText("Which iPhone"), "iphone 13");
    await user.type(screen.getByLabelText("Your notes from looking at it"), "battery 88%");
    await user.click(screen.getByRole("button", { name: "Draft listing" }));
    expect(await screen.findByText("Needs you")).toBeTruthy();
    const form = fetch.mock.calls[0][1]!.body as FormData;
    expect([form.get("title"), form.get("notes"), form.has("description")]).toEqual(["iphone 13", "battery 88%", false]);
  });

  it("says so when it isn't an iPhone, and an empty field eBay needs is yours to fill in", async () => {
    serve({ "POST /api/listings/draft": [200, { ...LISTED, ebay_title: null, condition_id: null, condition_note: null,
      description: null, filled_by_code: {}, reasons: ["List on eBay is for iPhones only"], attempts: [] }] });
    const user = userEvent.setup();
    render(<ListingScreen />);
    await user.type(screen.getByLabelText("Which iPhone"), "PS5 Slim digital");
    await user.click(screen.getByRole("button", { name: "Draft listing" }));
    expect(await screen.findByText("List on eBay is for iPhones only")).toBeTruthy();
    cleanup();
    serve({ "POST /api/listings/draft": [200, { ...LISTED,
      ebay_category: { id: "9355", name: "Mobile & Smart Phones", path: "Mobile Phones & Communication" },
      item_specifics: [{ name: "Storage Capacity", value: null, required: true, source: null,
        options: ["128 GB", "256 GB", "512 GB"] }] }] });
    render(<ListingScreen />);
    await user.type(screen.getByLabelText("Which iPhone"), "iphone 13");
    await user.click(screen.getByRole("button", { name: "Draft listing" }));
    expect(await screen.findByText("eBay needs this: fill it in")).toBeTruthy();
    expect((screen.getByLabelText("Storage Capacity") as HTMLInputElement).value).toBe("");
  });

  it("keeps code's title when no answer passed, and says the colour wasn't drafted rather than unsure", async () => {
    serve({ "POST /api/listings/draft": [200, { ...LISTED, condition_id: null, condition_note: null, description: null,
      ebay_title: "Apple iPhone 14 Pro Max Unlocked", reasons: ["no answer passed the checks", "fill in: storage, colour"] }] });
    const user = userEvent.setup();
    render(<ListingScreen />);
    await user.type(screen.getByLabelText("Which iPhone"), "iphone 14 pro max");
    await user.click(screen.getByRole("button", { name: "Draft listing" }));
    expect(await screen.findByDisplayValue("Apple iPhone 14 Pro Max Unlocked")).toBeTruthy();
    expect(screen.getAllByText("Not drafted")).toHaveLength(2); // condition and colour
    expect(screen.queryByText("Unsure from the photos: check it")).toBeNull();
  });
});

/** Every setup listing answered (14 Oct: no Skip), the first with these words, then See my style */
async function answerAll(user: ReturnType<typeof userEvent.setup>, first: string) {
  for (let n = 1; n <= 6; n++) {
    await user.type(screen.getByLabelText("Your message to this seller"), n === 1 ? first : `Reply ${n}`);
    await user.click(screen.getByRole("button", { name: n < 6 ? "Next" : "See my style" }));
  }
}

/** First launch (4 Nov): the welcome, Get started, then AI message, where Set up my style opens the setup */
async function openSetup(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Get started" }));
  await user.click(await screen.findByRole("button", { name: "Set up my style" }));
  await user.click(screen.getByRole("button", { name: "Do the setup" }));
}

describe("the app", () => {
  const usual = { "GET /api/health": [200, HEALTH] as Answer, "GET /api/style": [200, STYLE] as Answer,
    "GET /api/stats": [200, STATS] as Answer };

  it("says what the phrasebook is in plain words (4 Nov)", async () => {
    localStorage.setItem(SETUP_DONE, "1");
    window.location.hash = "#style";
    serve({ ...usual, "GET /api/style/messages": [200, []] });
    render(<App />);
    const book = await screen.findByRole("region", { name: "Phrasebook" });
    expect(within(book).getByText("Sentences you've used in at least two messages. Some go in every message, others in "
      + "only one kind of offer.")).toBeTruthy();
  });

  it("sends a drafted listing to AI UK price estimate, which opens and checks it straight away (4 Nov)", async () => {
    // the owner: "add a button after it drafts a msg send the listing to ai uk price estimate and then it sends the title
    // and description and it opens the window with check uk price there please and start checking"
    localStorage.setItem(SETUP_DONE, "1");
    window.location.hash = "#message";
    const estimate: PriceEstimate = { price: 150, middle: 175, low: 160, high: 190, currency: "GBP", sales: 51,
      model: "iphone 13", storage_gb: 128, asked_storage_gb: 128, kind: "iphone", kinds: [], cuts: [], rough: false,
      exact: true, flaws: [], breakdown: [], not_cut: [] };
    const fetch = serve({ ...usual, "POST /api/messages/draft": [200, DRAFT], "POST /api/prices/estimate": [200, estimate] });
    const user = userEvent.setup();
    render(<App />);
    const message = screen.getAllByRole("textbox", { name: "Listing title" })[0];
    expect(screen.queryByRole("button", { name: "Check the UK price" })).toBeNull(); // only once there's a draft
    await user.type(message, "iPhone 13 128GB Blue");
    await user.type(screen.getAllByRole("textbox", { name: "The seller's description" })[0], "Small crack on the back.");
    await user.type(screen.getByLabelText("Asking price"), "£220");
    await user.click(screen.getByRole("button", { name: "No" }));
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    await screen.findByDisplayValue(DRAFT.message!);
    await user.click(screen.getByRole("button", { name: "Check the UK price" }));
    expect(window.location.hash).toBe("#price");
    // with the flaws its draft's reader found and who that was (9 Nov, the owner: "it already get passed the founded
    // flaws so we safe time"): the price tab doesn't read the listing again
    await waitFor(() => expect(sent(fetch, "POST /api/prices/estimate")).toEqual({ title: "iPhone 13 128GB Blue",
      description: "Small crack on the back.", flaws: ["Black dot on the screen"], read_by: "gemma3:4b" }));
    const price = screen.getByRole("region", { name: "The item" });
    expect(within(price).getByDisplayValue("iPhone 13 128GB Blue")).toBeTruthy();
    expect(within(price).getByDisplayValue("Small crack on the back.")).toBeTruthy();
  });

  // 9 Nov review: a listing typed in on the price tab is read for its flaws (slow), a sent one comes with them (fast)
  const priced = (price: number): PriceEstimate => ({ price, middle: 175, low: 160, high: 190, currency: "GBP",
    sales: 51, model: "iphone 13", storage_gb: 128, asked_storage_gb: 128, kind: "iphone", kinds: [], cuts: [],
    rough: false, exact: true, flaws: [], breakdown: [], not_cut: [] });
  const checks = (fetch: { mock: { calls: [string, RequestInit?][] } }) =>
    fetch.mock.calls.filter(([url]) => url === "/api/prices/estimate").length;
  /** The listing written on AI message, its draft shown, and Check the UK price clicked */
  async function draftAndSend(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getAllByRole("textbox", { name: "Listing title" })[0], "iPhone 13 128GB Blue");
    await user.type(screen.getAllByRole("textbox", { name: "The seller's description" })[0], "Small crack on the back.");
    await user.type(screen.getByLabelText("Asking price"), "£220");
    await user.click(screen.getByRole("button", { name: "No" }));
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    await screen.findByDisplayValue(DRAFT.message!);
    await user.click(screen.getByRole("button", { name: "Check the UK price" }));
  }

  it("shows the latest check's price: an older check that answers last is dropped (9 Nov review)", async () => {
    localStorage.setItem(SETUP_DONE, "1");
    window.location.hash = "#message";
    const answers: Record<string, unknown> = { "GET /api/health": HEALTH, "GET /api/style": STYLE,
      "GET /api/stats": STATS, "POST /api/messages/draft": DRAFT };
    let answerTheOld: () => void = () => {};
    let oldRead = false;
    const fetch = vi.fn(async (url: string, init?: RequestInit) => {
      const route = `${init?.method ?? "GET"} ${url}`;
      if (route !== "POST /api/prices/estimate") {
        if (!(route in answers)) throw new TypeError(`nothing serves ${route}`);
        return { ok: true, status: 200, json: async () => answers[route] };
      }
      if (JSON.parse(String(init?.body)).flaws) return { ok: true, status: 200, json: async () => priced(150) };
      await new Promise<void>((resolve) => { answerTheOld = () => resolve(); }); // typed in: it's read first, so slow
      return { ok: true, status: 200, json: async () => { oldRead = true; return priced(999); } };
    });
    vi.stubGlobal("fetch", fetch);
    const user = userEvent.setup();
    render(<App />);
    // another listing typed in and checked on the price tab, still being read...
    await user.click(screen.getByRole("link", { name: /AI UK price estimate/ }));
    const item = screen.getByRole("region", { name: "The item" });
    await user.type(within(item).getByRole("textbox", { name: "Listing title" }), "iPhone 14 256GB");
    await user.click(screen.getAllByRole("button", { name: "Check the UK price" }).at(-1)!);
    // ...when a draft's listing is sent from AI message, with its flaws: it answers first
    await user.click(screen.getByRole("link", { name: /AI message/ }));
    await draftAndSend(user);
    expect((await screen.findByLabelText("UK price")).textContent).toContain("£150");
    await act(async () => {
      answerTheOld();
      await vi.waitFor(() => expect(oldRead).toBe(true));
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    // the older check's answer is dropped: the sent listing and its price stay, and the button isn't busy
    expect(screen.getByLabelText("UK price").textContent).toContain("£150");
    expect(screen.queryByText("£999")).toBeNull();
    expect((within(item).getByRole("textbox", { name: "Listing title" }) as HTMLInputElement).value)
      .toBe("iPhone 13 128GB Blue");
    expect(screen.getAllByRole("button", { name: "Check the UK price" }).at(-1)!.getAttribute("aria-busy")).toBe("false");
    expect(checks(fetch)).toBe(2);
  });

  it("checks a sent listing once: back from Set up my style it isn't checked again (9 Nov review)", async () => {
    localStorage.setItem(SETUP_DONE, "1");
    window.location.hash = "#message";
    const fetch = serve({ ...usual, "GET /api/style": [200, NO_STYLE], "POST /api/messages/draft": [200, DRAFT],
      "POST /api/prices/estimate": [200, priced(150)] });
    const user = userEvent.setup();
    render(<App />);
    await draftAndSend(user);
    await waitFor(() => expect(checks(fetch)).toBe(1));
    // another listing checked on the price tab
    const title = within(screen.getByRole("region", { name: "The item" })).getByRole("textbox", { name: "Listing title" });
    await user.clear(title);
    await user.type(title, "iPhone 14 256GB");
    await user.click(screen.getAllByRole("button", { name: "Check the UK price" }).at(-1)!);
    await waitFor(() => expect(checks(fetch)).toBe(2));
    // checked after an edit, the listing is read afresh: the sent draft's flaws aren't sent with it
    expect(sent(fetch, "POST /api/prices/estimate", 1)).toEqual(
      { title: "iPhone 14 256GB", description: "Small crack on the back." });
    // the setup opened from AI message and left: the tabs come back, and the sent listing isn't checked a third time
    await user.click(screen.getByRole("link", { name: /AI message/ }));
    await user.click(await screen.findByRole("button", { name: "Set up my style" }));
    await user.click(screen.getByRole("button", { name: "Go back" }));
    expect(window.location.hash).toBe("#message");
    await user.click(screen.getByRole("link", { name: /AI UK price estimate/ }));
    const back = within(screen.getByRole("region", { name: "The item" }));
    expect((back.getByRole("textbox", { name: "Listing title" }) as HTMLInputElement).value).toBe("");
    expect(checks(fetch)).toBe(2);
  });

  it("opens on a welcome at first launch, then AI message: the setup is never forced (4 Nov, the owner)", async () => {
    serve({ ...usual, "GET /api/style": [200, NO_STYLE] });
    const user = userEvent.setup();
    render(<App />);
    expect(screen.getByRole("heading", { name: "Welcome to FlipAssist" })).toBeTruthy();
    expect(screen.queryByRole("navigation")).toBeNull(); // no sidebar on the welcome
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Get started"]);
    expect(screen.queryByText(/skip/i)).toBeNull();
    await user.click(screen.getByRole("button", { name: "Get started" }));
    expect(screen.getByRole("navigation")).toBeTruthy();
    expect(window.location.hash).toBe("#message");
    expect(localStorage.getItem(SETUP_DONE)).toBe("1");
    // no My style yet: its On and Off greyed out, with Set up my style beside them
    const row = screen.getByRole("group", { name: "My style" });
    const setUp = await within(row).findByRole("button", { name: "Set up my style" });
    expect(row.className).toContain("greyed");
    expect(["On", "Off"].map((c) => within(row).getByRole("button", { name: c }).hasAttribute("disabled")))
      .toEqual([true, true]);
    await user.click(setUp);
    expect(screen.getByRole("heading", { name: "Set up my style" })).toBeTruthy();
    expect(screen.getByText(/reply to 6 quick listings/)).toBeTruthy(); // 14 Oct: it said 8 when there were 6
    expect(screen.queryByText(/\b8\b/)).toBeNull();
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Go back", "Do the setup"]);
    expect(screen.queryByText(/paste/i)).toBeNull(); // no pasting: Add more is gone
    await user.click(screen.getByRole("button", { name: "Go back" }));
    expect(window.location.hash).toBe("#message"); // back where you were
  });

  it("lists what it learned at the end of setup, and Remove deletes what you don't want", async () => {
    const fetch = serve({ ...usual, "GET /api/style": [[200, NO_STYLE], [200, STYLE], [200, NO_CASH]],
      "PUT /api/style/setup": [200, []], "POST /api/style/learned": [200, NO_CASH] });
    const user = userEvent.setup();
    render(<App />);
    await openSetup(user);
    await answerAll(user, "Hi mate, would you take £185 cash? Cheers");
    expect(await screen.findByText("This is what it'll put in your messages. Remove anything you don't want.")).toBeTruthy();
    const list = within(screen.getByLabelText("What it learned"));
    expect(list.getByText("about 12 words")).toBeTruthy(); // how long isn't something to remove
    expect(list.getAllByRole("button").map((b) => b.textContent)).toEqual(["Remove", "Remove", "Remove"]);
    await user.click(screen.getByRole("button", { name: "Remove “paying cash” from My style" }));
    expect(sent(fetch, "POST /api/style/learned")).toEqual({ key: "mention:cash", used: false });
    await waitFor(() => expect(list.queryByText("paying cash")).toBeNull()); // gone, not greyed out (14 Oct)
    expect(screen.queryByRole("button", { name: /again/ })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(window.location.hash).toBe("#message"); // back to AI message, where it was opened
  });

  it("removes a thing your style learned from Your style for good: no Use again", async () => {
    localStorage.setItem(SETUP_DONE, "1");
    window.location.hash = "#style";
    const fetch = serve({ ...usual, "GET /api/style": [[200, STYLE], [200, NO_CASH]], "GET /api/style/messages": [200, []],
      "POST /api/style/learned": [200, NO_CASH] });
    const user = userEvent.setup();
    render(<App />);
    const card = within(await screen.findByRole("region", { name: "Style card" }));
    await user.click(await card.findByRole("button", { name: "Remove “paying cash” from My style" }));
    expect(sent(fetch, "POST /api/style/learned")).toEqual({ key: "mention:cash", used: false });
    await waitFor(() => expect(card.queryByText("paying cash")).toBeNull());
    expect(screen.queryByRole("button", { name: /again/ })).toBeNull();
    const book = within(screen.getByRole("region", { name: "Phrasebook" }));
    expect(book.getByRole("button", { name: "Remove “Cheers” from My style" })).toBeTruthy();
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
    await user.click(book.getByRole("button", { name: "Remove “Can collect today.” from My style" }));
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
    expect(screen.getByRole("heading", { name: "Set up my style" })).toBeTruthy();
    expect(screen.getByText(/take the place of your last setup/)).toBeTruthy();
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Go back", "Do the setup"]);
    await user.click(screen.getByRole("button", { name: "Go back" }));
    expect(await screen.findByRole("heading", { name: "My style" })).toBeTruthy();
    expect(window.location.hash).toBe("#style");
  });

  it("has no Skip in the setup: each listing needs a reply before Next (14 Oct, the owner)", async () => {
    serve({ ...usual, "GET /api/style": [200, NO_STYLE] });
    const user = userEvent.setup();
    render(<App />);
    await openSetup(user);
    expect(screen.queryByRole("button", { name: "Skip" })).toBeNull();
    expect(screen.getByRole("button", { name: "Next" }).hasAttribute("disabled")).toBe(true);
    await user.type(screen.getByLabelText("Your message to this seller"), "   ");
    expect(screen.getByRole("button", { name: "Next" }).hasAttribute("disabled")).toBe(true); // spaces aren't a reply
    await user.type(screen.getByLabelText("Your message to this seller"), "Hi there, would you consider £185?");
    expect(screen.getByRole("button", { name: "Next" }).hasAttribute("disabled")).toBe(false);
    expect(screen.getByText("Your words, typos and all: each listing needs a reply.")).toBeTruthy();
  });

  it("goes through the 6 listings one at a time, sending every answer", async () => {
    const fetch = serve({ ...usual, "GET /api/style": [[200, NO_STYLE], [200, STYLE]],
      "PUT /api/style/setup": [200, []] });
    const user = userEvent.setup();
    render(<App />);
    await openSetup(user);
    expect(screen.getByText("1 of 6")).toBeTruthy();
    expect(screen.getByText("Offer lower · £185")).toBeTruthy();
    await user.type(screen.getByLabelText("Your message to this seller"), "Hi mate, £185 given the crack?");
    await user.click(screen.getByRole("button", { name: "Next" }));
    for (let n = 2; n < 6; n++) {
      await user.type(screen.getByLabelText("Your message to this seller"), `Reply ${n}`);
      await user.click(screen.getByRole("button", { name: "Next" }));
    }
    expect(screen.getByText("6 of 6")).toBeTruthy();
    expect(screen.queryByText(/Vinted|Apple Watch/)).toBeNull(); // 3 Oct: those two cards are gone
    await user.type(screen.getByLabelText("Your message to this seller"), "Reply 6");
    await user.click(screen.getByRole("button", { name: "See my style" }));
    expect(await screen.findByText("Learned from 6 messages")).toBeTruthy();
    const answers = sent(fetch, "PUT /api/style/setup");
    expect([answers.length, answers[0]]).toEqual([6, { title: "iPhone 13 128GB, cracked back", price: "220",
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
      ["Home", "AI message", "My style", "AI UK price estimate", "List on eBay"]);
    await user.click(within(screen.getByRole("navigation")).getByText("AI message"));
    // the shown screen's box: UK price has a Listing title too, kept (hidden) while you're elsewhere
    await user.type(screen.getByRole("textbox", { name: "Listing title" }), "iPhone 13");
    expect(await screen.findByText("Ollama running")).toBeTruthy();
    expect(await screen.findByText("Learning from 14 of your messages")).toBeTruthy();
    await user.click(within(screen.getByRole("navigation")).getByText("Home"));
    expect(await screen.findByText("Done by the models")).toBeTruthy();
    expect(await screen.findByText("50")).toBeTruthy();
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
    expect(document.documentElement.dataset.platform).toBe("mac");
    delete document.documentElement.dataset.shell;
    delete document.documentElement.dataset.platform;
  });

  it("on Windows, fills its window under the system's title bar with no drawn traffic lights (9 Nov)", () => {
    markShell(Object.assign(Object.create(window), { flipassistShell: { window: "windows" } }));
    expect(document.documentElement.dataset.shell).toBe("window");
    expect(document.documentElement.dataset.platform).toBe("windows");
    delete document.documentElement.dataset.shell;
    delete document.documentElement.dataset.platform;
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

  it("counts the successful outputs across all the models, with no Refresh and no buttons at the bottom", async () => {
    const reload = home();
    const hero = within(screen.getByRole("region", { name: "Done by the models" }));
    expect(await hero.findByText("50")).toBeTruthy(); // every model's, the paid ones too
    expect(hero.getByText("successful outputs across all the models")).toBeTruthy();
    expect(hero.queryByText(/all free|in total/)).toBeNull(); // 14 Oct: just the count
    expect(screen.queryByText(/no paid AI/)).toBeNull(); // 14 Oct: the paid check runs on purpose
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
    await screen.findByText("50");
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
      ["flip-style-1b", "reads My style", true, true],
      ["Gemma 3 4B", "rewords a message when you click Rewrite, and writes eBay listings", true, true],
      ["Claude Haiku 5.5 (paid)", "Only checks each message's reason is sendable", true, false],
      ["Claude Sonnet 5.5 (paid)", "Fixes a reason Claude Haiku 5.5 flags; when this device's models can't, writes a "
        + "message or eBay listing, reads a listing, or looks at the photos for the colour", true, false],
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
      ["Claude Haiku 5.5 (paid)", "When this device's models can't: writes a message or eBay listing, reads a listing, or "
        + "looks at the photos for the colour"],
      ["Claude Sonnet 5.5 (paid)", "Fixes a reason Claude Haiku 5.5 flags"]]);
  });

  it("names Claude Haiku 5.5 as the eBay listing writer once it writes them, and Gemma for Rewrite only (14 Oct)", () => {
    const lists = { ...HEALTH, listing_model: "claude-haiku-5-5" };
    expect(paidRows(lists).map((r) => [r.name, r.state])).toEqual([
      ["Claude Haiku 5.5 (paid)", "Checks each message's reason is sendable, and writes eBay listings"],
      ["Claude Sonnet 5.5 (paid)", "Fixes a reason Claude Haiku 5.5 flags; when this device's models can't, writes a "
        + "message, reads a listing, or looks at the photos for the colour; and writes an eBay listing when Claude "
        + "Haiku 5.5's fails the checks"]]);
    expect(ollamaRows(lists).at(-1)).toEqual(
      { name: "Gemma 3 4B", model: true, ok: true, state: "rewords a message when you click Rewrite" });
    expect(ollamaRows({ ...HEALTH, listing_model: "gemma3:4b" }).at(-1)?.state)
      .toBe("rewords a message when you click Rewrite, and writes eBay listings");
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
    expect(damageLine({ ...base, damage: { level: "severe", tier: "middle", cut: -0.391, rough: false, n: 32,
      by: "Claude Sonnet 5.5" } })).toBe("Damage counted as severe: −39% for a mid-priced iPhone, from 32 listings like it"
      + " · Claude Sonnet 5.5 decided how bad");
    expect(damageLine({ ...base, damage: { level: "minor", tier: "top", cut: -0.167, rough: false, n: 175,
      by: "code and Claude Haiku 5.5" } })).toBe("Damage counted as minor: −17% for a pricier iPhone, from 175 listings "
      + "like it · how bad: code and Claude Haiku 5.5");
  });
  it("says where a rough one came from", () => {
    const samsung = { ...base, kind: "samsung", damage: { level: "minor", tier: "top", cut: -0.059, rough: true,
      from: "the US", n: 11 } };
    expect(damageLine(samsung)).toBe("Damage counted as minor: −6% for a pricier Samsung, from 11 listings like it "
      + "(rough)");
    // near a tier's edge the cut blends the two tiers' (9 Nov), and says so
    const near = { ...base, kind: "macbook", damage: { level: "severe", tier: "middle", cut: -0.58, rough: true,
      from: "the US", n: 23, between: ["bottom", "middle"] as [string, string], share: 0.627 } };
    expect(damageLine(near)).toBe("Damage counted as severe: −58% for a MacBook priced between cheaper and mid-priced "
      + "ones, from 23 listings like it (rough)");
  });
  it("doesn't call a MacBook's damage cut one measured on phones", () => {
    const mac = { ...base, kind: "macbook", model: "macbook air 13 m1", sales: 40, exact: true,
      damage: { level: "minor", tier: "middle", cut: -0.133, rough: false, n: 11 } };
    expect(cautions(mac, "MacBook Air M1").some((c) => c.includes("measured on phones"))).toBe(false);
    expect(cautions({ ...mac, cuts: ["damage", "fault"], kinds: ["damage", "fault"] }, "MacBook Air M1")
      .some((c) => c.includes("measured on phones"))).toBe(true);
  });
});

describe("the steps behind a draft, by job and who did it (14 Oct)", () => {
  const step = (model: string, more: Partial<Attempt> = {}): Attempt =>
    ({ model, problems: [], seconds: 1, cost_pence: 0, ...more });
  const said = () => screen.getAllByRole("listitem").map((li) => li.querySelector("span")?.textContent);

  it("names each step by its job: reading, wording, checking, fixing, writing", () => {
    render(<Steps readings={1} attempts={[step("flip-reader-5"), step("flip-wording-4b", { job: "reason" }),
      step("claude-haiku-5-5", { job: "reason" }), step("claude-sonnet-5-5", { job: "reason" }), step("gemma3:4b"),
      step("claude-sonnet-5-5", { problems: ["no answer"] })]} />);
    expect(said()).toEqual([
      "Reading the listing · flip-reader-5 (on this device) passed",
      "Wording the reason · flip-wording-4b (on this device) passed",
      "Checking the reason · Claude Haiku 5.5 (paid) passed",
      "Fixing the reason · Claude Sonnet 5.5 (paid) passed",
      "Writing the message · Gemma 3 4B (on this device) passed",
      "Writing the message · Claude Sonnet 5.5 (paid) failed: no answer"]);
  });

  it("says Claude Haiku 5.5 flagged the reason when it did, not that it passed", () => {
    render(<Steps flagged attempts={[step("flip-wording-4b", { job: "reason" }), step("claude-haiku-5-5", { job: "reason" }),
      step("claude-sonnet-5-5", { job: "reason" })]} />);
    expect(said()).toEqual(["Wording the reason · flip-wording-4b (on this device) passed",
      "Checking the reason · Claude Haiku 5.5 (paid) flagged it", "Fixing the reason · Claude Sonnet 5.5 (paid) passed"]);
  });

  it("calls an eBay listing's writing what it is, and a look at the colour a look", () => {
    render(<Steps writing="listing" attempts={[step("gemma3:4b"), step("claude-sonnet-5-5", { colour_only: true })]} />);
    expect(said()).toEqual(["Writing the listing · Gemma 3 4B (on this device) passed",
      "Looking at the colour · Claude Sonnet 5.5 (paid) passed"]);
  });

  it("shows Claude Haiku 5.5's flag on the AI message when the reason was fixed", async () => {
    const fixed = { ...DRAFT, reason: { clause: "the black dot on the screen", by: "claude-sonnet-5-5", checked: "fixed" },
      attempts: [step("flip-wording-4b", { job: "reason" }), step("claude-haiku-5-5", { job: "reason" }),
        step("claude-sonnet-5-5", { job: "reason" }), ...DRAFT.attempts] };
    serve({ "POST /api/messages/draft": [200, fixed] });
    const user = userEvent.setup();
    render(<MessageScreen />);
    await user.type(screen.getByRole("textbox", { name: "Listing title" }), "iPhone 13");
    await user.type(screen.getByPlaceholderText("£220"), "220");
    await user.click(screen.getByRole("button", { name: "Yes" }));
    await user.click(screen.getByRole("button", { name: "1 flaw only" }));
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    await user.click(await screen.findByRole("button", { name: /Why · 5 steps/ }));
    expect(screen.getByText("Checking the reason · Claude Haiku 5.5 (paid) flagged it")).toBeTruthy();
    expect(screen.getByText("Reason flagged by Claude Haiku 5.5, fixed by Claude Sonnet 5.5")).toBeTruthy();
  });
});

describe("Home's numbers add up (14 Oct)", () => {
  it("shows the same total on the blue card as Who did the work's passed ones add up to", async () => {
    const models = [{ model: "flip-reader-5", job: "read", attempts: 23, passed: 23, cost_pence: 0 },
      { model: "template", job: "draft", attempts: 19, passed: 19, cost_pence: 0 },
      { model: "claude-haiku-5-5", job: "reason", attempts: 8, passed: 8, cost_pence: 0.126 },
      { model: "claude-sonnet-5-5", job: "draft", attempts: 2, passed: 1, cost_pence: 0.5 }];
    const stats = { ...STATS, models, outputs: 51, outputs_here: 42 };
    serve({ "GET /api/stats": [200, stats] });
    render(<HomeScreen go={vi.fn()} count={0} running={HEALTH} reload={vi.fn(async () => undefined)} />);
    const hero = within(screen.getByRole("region", { name: "Done by the models" }));
    expect(await hero.findByText("51")).toBeTruthy();
    const work = within(screen.getByRole("region", { name: "Who did the work" }));
    expect(work.getByText("51 passed in all")).toBeTruthy();
    const passed = work.getAllByText(/^\d+ of \d+ passed$/).map((p) => Number(p.textContent!.split(" ")[0]));
    expect(passed.reduce((a, b) => a + b, 0)).toBe(51);
    expect(work.getByText("Claude Sonnet 5.5 · writing the message as a backup")).toBeTruthy();
  });

  it("has no ready share in the blue card (4 Nov, the owner: \"remove the ready thing in the blue card\")", async () => {
    serve({ "GET /api/stats": [200, { ...STATS, drafts: 12, ready: 9 }] });
    render(<HomeScreen go={vi.fn()} count={0} running={HEALTH} reload={vi.fn(async () => undefined)} />);
    const hero = within(screen.getByRole("region", { name: "Done by the models" }));
    expect(await hero.findByText("12")).toBeTruthy();
    expect(hero.getByText("drafts")).toBeTruthy();
    expect(hero.queryByText("ready")).toBeNull();
    expect(hero.queryByText("75%")).toBeNull();
  });
});
