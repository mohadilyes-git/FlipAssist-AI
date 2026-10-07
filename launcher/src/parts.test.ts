import assert from "node:assert/strict";
import { test } from "node:test";
import { fileFor, keyFrom, modelsToWarm, readyWords, settingFrom, typeOf } from "./parts";

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

test("a setting is read the way the API reads .env: missing is undefined, empty is off", () => {
  assert.equal(settingFrom("FLIP_WORDING_MODEL=\n", "FLIP_WORDING_MODEL"), "");
  assert.equal(settingFrom("A=1\n", "FLIP_WORDING_MODEL"), undefined);
  assert.equal(settingFrom("FLIP_READER_MODEL = 'flip-reader-4'", "FLIP_READER_MODEL"), "flip-reader-4");
});

test("FlipAssist opens with the models every draft uses loaded, each with the working memory it's asked with", () => {
  const all = ["gemma3:4b", "flip-reader-5:latest", "flip-wording-4b:latest", "flip-wording-3:latest"];
  // the reader last: when only one fits, Ollama keeps the newest, and every draft reads first
  assert.deepEqual(modelsToWarm(all, ""), [{ model: "flip-wording-4b", numCtx: 2048 }, { model: "flip-reader-5", numCtx: 8192 }]);
  // no reader: Gemma reads, so it's loaded instead; no flip-wording: code words the reason
  assert.deepEqual(modelsToWarm(["gemma3:4b"], ""), [{ model: "gemma3:4b", numCtx: 8192 }]);
  // turned off or renamed in .env, and what's set already wins over .env, as with the API
  assert.deepEqual(modelsToWarm(all, "FLIP_READER_MODEL=\nFLIP_WORDING_MODEL=flip-wording-3"),
    [{ model: "flip-wording-3", numCtx: 2048 }, { model: "gemma3:4b", numCtx: 8192 }]);
  assert.deepEqual(modelsToWarm(all, "FLIP_WORDING_MODEL=flip-wording-3", { FLIP_WORDING_MODEL: "" }),
    [{ model: "flip-reader-5", numCtx: 8192 }]);
  assert.deepEqual(modelsToWarm([], ""), []); // nothing downloaded: drafts use code only
});

test("the launch screen names what's ready and says a model that isn't installed (6 Oct review)", () => {
  assert.equal(readyWords(["gemma3:4b", "flip-reader-5:latest", "flip-wording-4b:latest"], ""),
    "flip-reader-5, flip-wording-4b and Gemma 3 4B are ready");
  assert.equal(readyWords(["gemma3:4b", "flip-reader-5:latest"], ""),
    "flip-reader-5 and Gemma 3 4B are ready; flip-wording-4b isn't installed, so code words the reason");
  assert.equal(readyWords(["gemma3:4b"], "FLIP_WORDING_MODEL="), "Gemma 3 4B is ready; flip-reader-5 isn't installed, so Gemma reads");
});
