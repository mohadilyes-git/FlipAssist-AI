// How the API's answers read on screen.

const WRITERS: Record<string, string> = {
  // the Writer you pick on AI message (14 Oct): your sentences, or AlertFlip's until it has learned yours
  template: "No AI writing",
  "gemma3:4b": "Gemma 3 4B (on this device)",
  "flip-reader-5": "flip-reader-5 (on this device)",
  "flip-wording-3": "flip-wording-3 (on this device)",
  "flip-wording-4b": "flip-wording-4b (on this device)",  // the wording model since 6 Oct
  "flip-style-1b": "flip-style-1b (on this device)",  // the style reader since 6 Oct
  "flip-kinds-1": "flip-kinds-1 (on this device)",
  "claude-haiku-5-5": "Claude Haiku 5.5 (paid)",
  "claude-sonnet-5-5": "Claude Sonnet 5.5 (paid)",
  code: "Code only",
};  // each model by its real name (4 Oct), the same everywhere; one not here shows as it's called ("flip-reader-4")

/** Who worded the offer's reason and who checked it: "Reason by flip-wording · checked by Claude Haiku". */
export function reasonLine(reason: { by: string; checked: string }): string {
  const checker = modelName("claude-haiku-5-5");
  if (reason.checked === "fixed") return `Reason flagged by ${checker}, fixed by ${modelName(reason.by)}`;
  const by = `Reason by ${modelName(reason.by)}`;
  if (reason.checked === "ok") return `${by} · checked by ${checker}`;
  if (reason.checked === "flagged, kept") return `${by} · flagged by ${checker}, kept as written`;
  if (reason.checked === "pending") return `${by} · ${checker} checking…`;
  return `${by} · not checked`;
}

/** What a model did, for Home's "who did the work": "reading the listing", "checking the reason". */
export function jobName(model: string, job: string): string {
  if (job === "read") return "reading the listing";
  if (job === "price") return "reading for a UK price";
  if (job === "colour") return "checking the colour";
  if (job === "listing") return "writing the eBay listing";  // a listing's own job since 14 Oct
  if (job === "reason") {
    return model.startsWith("claude-haiku") ? "checking the reason is sendable" : model.startsWith("claude-sonnet") ? "fixing the reason"
      : "wording the reason";
  }
  return "writing the message";
}

/** "template" -> "No AI writing", "gemma3:4b" -> "Gemma 3 4B (on this device)". */
export function writerName(model: string | null): string {
  return model ? (WRITERS[model] ?? model) : "Nobody yet";
}

/** A model's name for inside a sentence: "flip-wording-3", "Claude Haiku 5.5". */
export function modelName(model: string): string {
  return writerName(model).split(/,| \(/)[0];
}

/** Who read the listing: "read by flip-reader-5 (on this device)", or "read by code (no AI)". */
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
