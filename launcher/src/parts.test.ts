import assert from "node:assert/strict";
import { test } from "node:test";
import { fileFor, keyFrom, typeOf } from "./parts";

test("the key is read the way the API reads .env", () => {
  assert.equal(keyFrom("ANTHROPIC_API_KEY=a\nFLIP_API_KEY=abc123\n"), "abc123");
  assert.equal(keyFrom("FLIP_API_KEY = \"abc 123\" \r\n"), "abc 123");
  assert.equal(keyFrom("FLIP_API_KEY='abc'\nFLIP_API_KEY=second"), "abc"); // the first one counts
  assert.equal(keyFrom("# FLIP_API_KEY=commented\nFLIP_API_KEY_OLD=x"), "");
  assert.equal(keyFrom("FLIP_API_KEY=a=b"), "a=b");
  assert.equal(keyFrom(""), "");
});

test("only the built app's own files are served", () => {
  const dist = "/repo/frontend/dist";
  assert.equal(fileFor(dist, "/"), "/repo/frontend/dist/index.html");
  assert.equal(fileFor(dist, "/assets/index-abc.js"), "/repo/frontend/dist/assets/index-abc.js");
  assert.equal(fileFor(dist, "/assets/a%20b.css"), "/repo/frontend/dist/assets/a b.css");
  for (const escape of ["/../../.env", "/%2e%2e/%2e%2e/.env", "/assets/../../.env", "/..%2f..%2f.env", "/%00", "/%E0%A4%A"]) {
    assert.equal(fileFor(dist, escape), null, escape);
  }
});

test("each file goes with its type", () => {
  assert.equal(typeOf("/x/index.html"), "text/html; charset=utf-8");
  assert.equal(typeOf("/x/INDEX-A1.JS"), "text/javascript; charset=utf-8");
  assert.equal(typeOf("/x/font.woff2"), "font/woff2");
  assert.equal(typeOf("/x/unknown.bin"), "application/octet-stream");
});
