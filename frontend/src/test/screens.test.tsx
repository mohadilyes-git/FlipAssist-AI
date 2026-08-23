import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import type { ListingDraft, MessageDraft } from "../api";
import { ListingScreen } from "../screens/ListingScreen";
import { MessageScreen } from "../screens/MessageScreen";

const DRAFT: MessageDraft = {
  draft_id: 7, status: "ready", written_by: "template", kind: "lower", offer: "£185", offer_pence: 18500,
  message: "Hi mate, would you take £185 cash, given the black dot on the screen? Can collect from Leeds LS6 today.",
  note: 'The seller says: "Price is firm, no offers"', ask: null, point: ["Black dot on the screen"], mentioned: true,
  questions: [], reasons: [], cost_pence: 0,
  attempts: [{ model: "template", problems: [], seconds: 0.001, cost_pence: 0 }],
  reading: { flaws: ["Black dot on the screen"], pickup: "Leeds LS6", no_offers: "Price is firm, no offers",
    read_by: "gemma3:4b", attempts: [{ model: "gemma3:4b", problems: [], seconds: 1.2, cost_pence: 0 }] },
};

function answers(...bodies: [number, unknown][]) {
  const fetch = vi.fn();
  for (const [status, body] of bodies) {
    fetch.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
  }
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:photo");
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = "";
});

describe("message the seller", () => {
  async function draft(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByLabelText("Listing title"), "iPhone 13 128GB Blue");
    await user.type(screen.getByLabelText("Asking price"), "£220");
    await user.click(screen.getByRole("button", { name: "Write my message" }));
  }

  it("shows the message, the seller's note, what was read and who wrote it", async () => {
    const fetch = answers([200, DRAFT]);
    const user = userEvent.setup();
    render(<MessageScreen />);
    await draft(user);
    expect(await screen.findByDisplayValue(DRAFT.message!)).toBeTruthy();
    expect(screen.getByText('The seller says: "Price is firm, no offers"')).toBeTruthy();
    expect(screen.getByText("Black dot on the screen")).toBeTruthy();
    expect(screen.getAllByText(/Your own sentences \(no AI\)/).length).toBeGreaterThan(0);
    const sent = JSON.parse(fetch.mock.calls[0][1].body);
    expect([sent.listing.asking_price, sent.offer]).toEqual(["220.00", "185.00"]); // code's starting price
    expect(fetch.mock.calls[0][0]).toBe("/api/messages/draft");
  });

  it("approves what you actually send, edits and all", async () => {
    const fetch = answers([200, DRAFT], [200, { draft_id: 7, edited: true, at: "now" }]);
    const user = userEvent.setup();
    render(<MessageScreen />);
    await draft(user);
    const box = await screen.findByDisplayValue(DRAFT.message!);
    await user.type(box, " Cheers");
    await user.click(screen.getByRole("button", { name: "Copy & approve" }));
    expect(await screen.findByText(/you changed it first/)).toBeTruthy();
    expect(fetch.mock.calls[1][0]).toBe("/api/drafts/7/approve");
    expect(JSON.parse(fetch.mock.calls[1][1].body).sent).toBe(DRAFT.message + " Cheers");
  });

  it("makes the message on screen longer, keeping your edits", async () => {
    const fetch = answers([200, DRAFT], [200, { ...DRAFT, draft_id: 8 }]);
    const user = userEvent.setup();
    render(<MessageScreen />);
    await draft(user);
    await user.type(await screen.findByDisplayValue(DRAFT.message!), " Cheers");
    await user.click(screen.getByRole("button", { name: "Make it longer" }));
    const sent = JSON.parse(fetch.mock.calls[1][1].body);
    expect([sent.length, sent.previous]).toEqual(["longer", DRAFT.message + " Cheers"]);
  });

  it("says what the API refused", async () => {
    answers([422, { detail: [{ loc: ["body", "listing", "asking_price"], msg: "String should match pattern" }] }]);
    const user = userEvent.setup();
    render(<MessageScreen />);
    await draft(user);
    expect((await screen.findByRole("alert")).textContent).toBe("listing › asking_price: String should match pattern");
  });
});

describe("list on eBay", () => {
  const LISTED: ListingDraft = {
    draft_id: 3, status: "ready", ebay_title: "Apple iPhone 13 128GB Midnight Unlocked", condition_id: "3000",
    condition_note: "Light scratch on the back.", description: "Apple iPhone 13 128GB in Midnight.", colour: "Midnight",
    filled_by_code: { model: "iPhone 13", storage: "128GB" }, warnings: [], reasons: [], photo_count: 2,
    attempts: [{ model: "gemma3:4b", problems: [], seconds: 9.5, cost_pence: 0 }], cost_pence: 0,
  };

  it("takes at most 8 photos and sends them with the form", async () => {
    const fetch = answers([200, LISTED]);
    const user = userEvent.setup();
    const { container } = render(<ListingScreen />);
    const photos = Array.from({ length: 10 }, (_, n) => new File(["x"], `p${n}.jpg`, { type: "image/jpeg" }));
    await user.upload(container.querySelector("input[type=file]") as HTMLInputElement, photos);
    expect(screen.getAllByRole("img")).toHaveLength(8);
    expect(container.querySelector("input[type=file]")).toBeNull(); // no "Add photo" slot once there are 8
    await user.type(screen.getByLabelText("The seller's title"), "iphone 13 128gb");
    await user.click(screen.getByRole("button", { name: "Draft listing" }));
    expect(await screen.findByDisplayValue(LISTED.ebay_title!)).toBeTruthy();
    expect(screen.getByText("Used")).toBeTruthy();
    const form = fetch.mock.calls[0][1].body as FormData;
    expect(form.getAll("photos")).toHaveLength(8);
    expect(form.get("title")).toBe("iphone 13 128gb");
  });
});

describe("the app", () => {
  it("switches screens from the tabs", async () => {
    answers([200, { local_model: "gemma3:4b", local_running: true, api_model: "claude-haiku-5-5", api_key_set: true,
      flip_api_key_set: true }], [200, { drafts: 2, ready: 2, needs_you: 0, done_on_this_mac: 1, models: [],
      cost_pence: 0, cost_per_100_drafts_pence: 0, approved: 0, edited_before_sending: 0 }]);
    const user = userEvent.setup();
    render(<App />);
    expect(screen.getByRole("button", { name: "Write my message" })).toBeTruthy();
    await user.click(within(screen.getByRole("navigation")).getByText("Home"));
    expect(await screen.findByText("DONE ON THIS MAC")).toBeTruthy();
    expect(window.location.hash).toBe("#home");
  });
});


describe("the price line", () => {
  it("slides the lower offer and swaps the new price into the message", async () => {
    answers([200, DRAFT]);
    const user = userEvent.setup();
    render(<MessageScreen />);
    await user.type(screen.getByLabelText("Listing title"), "iPhone 13 128GB Blue");
    await user.type(screen.getByLabelText("Asking price"), "220");
    const line = screen.getByRole("slider", { name: "Offer lower price" }) as HTMLInputElement;
    expect([line.min, line.max, line.step, line.value]).toEqual(["2000", "21500", "500", "18500"]);
    await user.click(screen.getByRole("button", { name: "Write my message" }));
    await screen.findByDisplayValue(DRAFT.message!);
    fireEvent.change(line, { target: { value: "15000" } });
    expect(screen.getByDisplayValue(DRAFT.message!.replace("£185", "£150"))).toBeTruthy();
    expect(screen.getByText("£70 under")).toBeTruthy();
  });
});
