import { describe, expect, it } from "vitest";
import { jobName, modelName, readBy, reasonLine, writerName } from "../format";

describe("who read the listing", () => {
  it("names FlipAssist's own reader", () => {
    expect(readBy("flip-reader-5")).toBe("read by flip-reader-5 (on this device)");
    expect(modelName("flip-reader-5")).toBe("flip-reader-5");
  });
  it("still names Gemma and code", () => {
    expect(writerName("gemma3:4b")).toBe("Gemma 3 4B (on this device)");
    expect(writerName("flip-wording-4b")).toBe("flip-wording-4b (on this device)");
    expect(writerName("flip-style-1b")).toBe("flip-style-1b (on this device)");
    expect(readBy("code")).toBe("read by code (no AI)");
  });
});

describe("reasonLine", () => {
  it("says who worded the offer's reason and who checked it", () => {
    expect(reasonLine({ by: "flip-wording-3", checked: "ok" })).toBe("Reason by flip-wording-3 · checked by Claude Haiku 5.5");
    expect(reasonLine({ by: "claude-sonnet-5-5", checked: "fixed" })).toBe("Reason flagged by Claude Haiku 5.5, fixed by Claude Sonnet 5.5");
    expect(reasonLine({ by: "flip-wording-3", checked: "flagged, kept" })).toBe("Reason by flip-wording-3 · flagged by Claude Haiku 5.5, kept as written");
    expect(reasonLine({ by: "flip-wording-3", checked: "not checked" })).toBe("Reason by flip-wording-3 · not checked");
    expect(reasonLine({ by: "flip-wording-3", checked: "pending" })).toBe("Reason by flip-wording-3 · Claude Haiku 5.5 checking…");
  });
});

describe("what each model did, on Home", () => {
  it("calls an eBay listing's writing what it is (14 Oct)", () => {
    expect(jobName("gemma3:4b", "listing")).toBe("writing the eBay listing");
    expect(jobName("gemma3:4b", "draft")).toBe("writing the message");
    expect(jobName("claude-haiku-5-5", "reason")).toBe("checking the reason is sendable");
  });
});

describe("Rewrite's own job (14 Oct)", () => {
  it("says Gemma 3 4B was rewording the message, and a paid model doing it was a backup", () => {
    expect(jobName("gemma3:4b", "rewrite")).toBe("rewording the message");
    expect(jobName("claude-sonnet-5-5", "rewrite")).toBe("rewording the message as a backup");
  });
});

describe("the damage judges on Home (14 Oct)", () => {
  it("says Claude Haiku 5.5 judges and Claude Sonnet 5.5 decides how bad, not as a backup", () => {
    expect(jobName("claude-haiku-5-5", "severity")).toBe("judging how bad the damage is");
    expect(jobName("claude-sonnet-5-5", "severity")).toBe("deciding how bad the damage is");
  });
});
