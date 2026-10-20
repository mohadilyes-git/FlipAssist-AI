// FlipAssist's API, as the front end sees it: one function per endpoint, with
// the same shapes the API publishes at /docs. Every call goes to /api/..., which
// the dev server passes on to the API with the key added (vite.config.ts).

export type Kind = "lower" | "asking" | "more";
export type Writer = "auto" | "template" | "ai";
/** how many of the listing's flaws a lower offer gives as its reason: the worst first, or all of them */
export type FlawsSaid = 1 | 2 | 3 | "all";

/** colour_only: a second look at the colour alone, when the local model was unsure from the photos */
export type Attempt = { model: string; problems: string[]; seconds: number; cost_pence: number; colour_only?: boolean;
  /** "reason": a step that worded the offer's reason (flip-wording, Haiku's check, Sonnet's fix) */
  job?: string };
/** The offer's reason as flip.wording worded and checked it: checked is "ok", "fixed", "flagged, kept" or "not checked" */
export type Reason = { clause: string; by: string; checked: string };

/** The listing's UK price from the AlertFlip app's prices backend: price with its flaws cut, middle a clean one's,
 * low to high the middle half of clean sales; flaws the sentences its flaws were read from, as read_by read them */
export type PriceEstimate = {
  price?: number | null; middle?: number | null; low?: number | null; high?: number | null; currency: string;
  /** how many clean sales middle is from: a for-parts price (parts_price) isn't from these, and the API doesn't say
   * how many for-parts sales it had */
  sales?: number | null; model?: string | null; item?: string | null; storage_gb?: number | null;
  ram_gb?: number | null;
  /** the size code found in the listing (null: it found none), against storage_gb/ram_gb, the size it priced */
  asked_storage_gb?: number | null; asked_ram_gb?: number | null;
  /** "iphone", "samsung" or "macbook"; kinds: the kinds of flaw found in the flaws and the title ("damage",
   * "fault"...); cuts: the ones the price was cut for. A locked or for-parts one is priced as that alone: cuts is just
   * "lock" or "parts", or none with parts_price (what for-parts ones sell for) */
  kind?: string | null; kinds?: string[]; cuts: string[]; parts_price?: boolean; mode?: string | null;
  rough: boolean; exact: boolean; skipped?: string | null; error?: string | null; flaws?: string[];
  read_by?: string | null;
  /** who sorted the flaws into kinds: "flip-kinds-1", "code" (its rules) or "flip-kinds-1 and code"; null: no flaws */
  sorted_by?: string | null;
  /** the damage cut FlipAssist measured (14 Oct): how bad, the model's price tier, the cut (-0.24), whether it's rough
   * (borrowed: from says where) and how many listings it's from */
  damage?: { level: string; tier: string; cut: number; rough: boolean; from?: string | null; n: number;
    /** who said how bad (14 Oct): "code and Claude Haiku 5.5" when they agreed, "Claude Sonnet 5.5" when it decided,
     * "code" without a key */
    by?: string } | null;
};

export type Reading = {
  flaws: string[];
  /** the reader's whole sentences the reason is worded from (before code cuts a seller's story off) */
  quotes?: string[];
  pickup: string;
  no_offers: string;
  read_by: string;
  attempts: Attempt[];
};

export type Listing = {
  title: string;
  description: string;
  asking_price: string;
  marketplace: string;
};

export type MessageRequest = {
  listing: Listing;
  kind: Kind;
  /** the price you picked on the slider, in pounds ("185.00"); the API starts from its own if it's left out */
  offer?: string;
  mention: boolean | null;
  length: "usual" | "longer";
  previous?: string | null;
  writer: Writer;
  /** the message on screen, for Rewrite: the new one says it in other words */
  rewrite_of?: string | null;
  /** the reason comes back as flip-wording wrote it ("pending") and checkReason checks it after the draft is shown */
  check_later?: boolean;
  /** with previous or rewrite_of: the reason the message on screen gives, and the lines it was worded from
   * (reading.quotes): kept rather than worded and checked again, when this listing still reads the same */
  reason?: (Reason & { quotes: string[] }) | null;
  /** with mention, how many flaws a lower offer gives (14 Oct); left out, as before */
  flaws_said?: FlawsSaid | null;
};

export type ReasonCheckRequest = {
  draft_id: number;
  listing: Listing;
  /** reading.flaws, for code's checks */
  flaws: string[];
  /** the draft's reason_from: the sentences flip-wording worded the reason from, which Haiku checks it against */
  quotes?: string[];
  clause: string;
  message: string;
  kind: Kind;
  offer_pence: number;
  /** reason.by: the model that worded the clause, credited back when the check keeps it */
  by?: string;
};

/** Haiku's check of a pending reason, and Sonnet's fix when Haiku flagged it: changed means a new message to show */
export type ReasonCheck = { reason: Reason; message: string; changed: boolean; problems: string[]; attempts: Attempt[];
  cost_pence: number };

export type Length = "usual" | "longer";

export type MessageDraft = {
  draft_id: number;
  status: "ready" | "needs you";
  message: string | null;
  written_by: string | null;
  kind: Kind;
  offer: string;
  offer_pence: number;
  note: string | null;
  ask: string | null;
  point: string[];
  mentioned: boolean;
  questions: string[];
  reading: Reading;
  reasons: string[];
  /** worth knowing before you send: a title and description naming different models, a rewrite with no other words */
  warnings: string[];
  attempts: Attempt[];
  reason?: Reason | null;
  /** the reader's lines the reason was worded from: the picked ones with flaws_said, else reading.quotes */
  reason_from?: string[];
  cost_pence: number;
};

export type ListingDraft = {
  draft_id: number;
  status: "ready" | "needs you";
  ebay_title: string | null;
  condition_id: string | null;
  condition_note: string | null;
  description: string | null;
  /** checked against the model's colours; null when neither the listing nor the photos settle it */
  colour: string | null;
  colour_from: "listing" | "photos" | null;
  /** the model that picked it from the photos */
  colour_by?: string | null;
  filled_by_code: Record<string, unknown>;
  /** eBay UK's category; phones so far */
  ebay_category: EbayCategory | null;
  /** eBay's fields filled by code, in eBay's order and words: the ones it needs first */
  item_specifics: ItemSpecific[];
  warnings: string[];
  reasons: string[];
  photo_count: number;
  attempts: Attempt[];
  cost_pence: number;
};

export type EbayCategory = { id: string; name: string; path: string };

/** value: null when nobody knows it. source: "the catalogue", "your title or notes" or "the photos: Midnight". */
export type ItemSpecific = {
  name: string; value: string | null; required: boolean; source: string | null; options: string[];
};

/** saved_to_style: an approved message joins the messages your style is learned from */
export type Approved = { draft_id: number; edited: boolean; at: string; saved_to_style: boolean };

/** What it learned from your messages, with plain code: nothing gets trained. */
/** one thing your style puts in a message; used is false once you've removed it */
export type Learned = { key: string; what: string; value: string; used: boolean };
export type Style = {
  count: number;
  traits: { k: string; v: string }[];
  phrases: { k: string; v: string }[];
  learned: Learned[];
};

/** One of the messages your style is learned from; price is in pounds, as written ("220"), or empty. */
export type StyleMessage = {
  id: string;
  title: string;
  price: string;
  text: string;
  marketplace: string;
  source: string;
  at: string;
};

export type NewStyleMessage = { title: string; price: string; text: string; marketplace?: string };

export type Stats = {
  drafts: number;
  ready: number;
  needs_you: number;
  /** successful outputs (answers that passed their checks) made on this device, free, and all of them, the paid ones
   * too (14 Oct) */
  outputs_here: number;
  outputs: number;
  /** each model once for each job it did: "read", "draft" (writing), "reason" or "colour" */
  models: { model: string; job: string; attempts: number; passed: number; cost_pence: number }[];
  cost_pence: number;
  cost_per_100_drafts_pence: number;
  approved: number;
  edited_before_sending: number;
};

export type Health = {
  local_model: string;
  local_running: boolean;
  /** the paid model that reads or writes when this device's models can't (Claude Sonnet 5.5) */
  api_model: string;
  api_key_set: boolean;
  /** the paid model that checks each reason is sendable (Claude Haiku 5.5), and the one that fixes a flagged reason;
   * empty when off */
  check_model?: string;
  fix_model?: string;
  /** AlertFlip's prices API (fresh UK sales) has its URL and key */
  prices_api_set?: boolean;
  flip_api_key_set: boolean;
  /** the models Ollama is asked for, by job, and whether this device has each (empty when Ollama isn't running) */
  models?: { job: string; name: string; installed: boolean }[];
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** What went wrong, in words: FastAPI says it as a string, or as a list of fields that failed. */
export function explain(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).filter((p) => p !== "body").join(" › ")}: ${d.msg}`)
      .join("; ");
  }
  if (status === 0 || status >= 502) return "FlipAssist's API isn't running: start it with .venv/bin/uvicorn flip.api:app";
  return `the API answered ${status}`;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, init);
  } catch {
    throw new ApiError(0, explain(0, null));
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, explain(response.status, body));
  return body as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => call<Health>("/health"),
  stats: () => call<Stats>("/stats"),
  draftMessage: (request: MessageRequest) => call<MessageDraft>("/messages/draft", json(request)),
  checkReason: (request: ReasonCheckRequest) => call<ReasonCheck>("/messages/check-reason", json(request)),
  /** with description, the API reads it for the flaws first; with flaws, they're used as they are */
  estimatePrice: (request: { title: string; description?: string; flaws?: string[] }) =>
    call<PriceEstimate>("/prices/estimate", json(request)),
  draftListing: (form: FormData) => call<ListingDraft>("/listings/draft", { method: "POST", body: form }),
  approve: (draftId: number, sent: string) => call<Approved>(`/drafts/${draftId}/approve`, json({ sent })),
  style: () => call<Style>("/style"),
  styleMessages: () => call<StyleMessage[]>("/style/messages"),
  /** your setup's answers, in place of your last setup's: your style is learned from them afresh */
  setUpStyle: (messages: NewStyleMessage[]) => call<StyleMessage[]>("/style/setup", { ...json(messages), method: "PUT" }),
  forgetStyleMessage: (id: string) => call<null>(`/style/messages/${encodeURIComponent(id)}`, { method: "DELETE" }),
  changeLearned: (key: string, used: boolean) => call<Style>("/style/learned", json({ key, used })),
};
