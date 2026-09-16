// How the API's answers read on screen.

const WRITERS: Record<string, string> = {
  template: "Your own sentences (no AI)",
  "gemma3:4b": "Gemma, on this Mac",
  "claude-haiku-5-5": "Claude Haiku (paid backup)",
  code: "Code only",
};

/** "template" -> "Your own sentences (no AI)", "gemma3:4b" -> "Gemma, on this Mac". */
export function writerName(model: string | null): string {
  return model ? (WRITERS[model] ?? model) : "Nobody yet";
}

/** A model's short name, for inside a sentence: "Gemma", "Claude Haiku". */
export function modelName(model: string): string {
  return writerName(model).split(/,| \(/)[0];
}

/** Who read the listing: "read by Gemma, on this Mac", or "read by code (no AI)". */
export function readBy(model: string): string {
  return model === "code" ? "read by code (no AI)" : `read by ${writerName(model)}`;
}

/** 0 -> "free"; 0.0091 -> "0.009p". */
export function cost(pence: number): string {
  return pence ? `${pence < 0.001 ? "<0.001" : pence.toFixed(3)}p` : "free";
}

export function seconds(attempts: { seconds: number }[]): string {
  const total = attempts.reduce((sum, a) => sum + a.seconds, 0);
  return total < 0.1 ? "instant" : `${total.toFixed(1)}s`;
}

/** eBay's conditions by id, as eBay names them. */
export const CONDITIONS: Record<string, string> = {
  "1000": "New",
  "1500": "Opened – never used",
  "3000": "Used",
  "7000": "For parts or not working",
};

export const MARKETPLACES = [
  { id: "facebook", name: "Facebook" },
  { id: "ebay", name: "eBay" },
  { id: "vinted", name: "Vinted" },
  { id: "gumtree", name: "Gumtree" },
  { id: "other", name: "Other" },
];
