import { describe, expect, it } from "vitest";
import { modelName, readBy, reasonLine, writerName } from "../format";

describe("who read the listing", () => {
  it("names FlipAssist's own reader", () => {
    expect(readBy("flip-reader-5")).toBe("read by flip-reader-5 (on this Mac)");
    expect(modelName("flip-reader-5")).toBe("flip-reader-5");
  });
  it("still names Gemma and code", () => {
    expect(writerName("gemma3:4b")).toBe("Gemma 3 4B (on this Mac)");
    expect(readBy("code")).toBe("read by code (no AI)");
  });
});

describe("reasonLine", () => {
  it("says who worded the offer's reason and who checked it", () => {
    expect(reasonLine({ by: "flip-wording-3", checked: "ok" })).toBe("Reason by flip-wording-3 · checked by Claude Haiku 5.5");
    expect(reasonLine({ by: "claude-sonnet-5-5", checked: "fixed" })).toBe("Reason flagged by Claude Haiku 5.5, fixed by Claude Sonnet 5.5");
    expect(reasonLine({ by: "flip-wording-3", checked: "flagged, kept" })).toBe("Reason by flip-wording-3 · flagged, kept as written");
    expect(reasonLine({ by: "flip-wording-3", checked: "not checked" })).toBe("Reason by flip-wording-3 · not checked");
    expect(reasonLine({ by: "flip-wording-3", checked: "pending" })).toBe("Reason by flip-wording-3 · checking…");
  });
});
