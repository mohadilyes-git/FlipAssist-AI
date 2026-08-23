import { describe, expect, it } from "vitest";
import { explain } from "../api";

describe("what went wrong, in words", () => {
  it("passes on what the API said", () => {
    expect(explain(401, { detail: "missing or wrong X-API-Key" })).toBe("missing or wrong X-API-Key");
  });
  it("names each field the API refused", () => {
    const body = { detail: [{ loc: ["body", "listing", "asking_price"], msg: "String should match pattern" }] };
    expect(explain(422, body)).toBe("listing › asking_price: String should match pattern");
  });
  it("says so when the API isn't running", () => {
    expect(explain(0, null)).toMatch(/isn't running/);
    expect(explain(502, null)).toMatch(/isn't running/);
  });
});
