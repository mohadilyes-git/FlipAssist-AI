import { describe, expect, it } from "vitest";
import { modelName, readBy, writerName } from "../format";

describe("who read the listing", () => {
  it("names FlipAssist's own reader", () => {
    expect(readBy("flip-reader-5")).toBe("read by Fine-tuned Gemma, on this Mac");
    expect(modelName("flip-reader-5")).toBe("Fine-tuned Gemma");
  });
  it("still names Gemma and code", () => {
    expect(writerName("gemma3:4b")).toBe("Gemma, on this Mac");
    expect(readBy("code")).toBe("read by code (no AI)");
  });
});
