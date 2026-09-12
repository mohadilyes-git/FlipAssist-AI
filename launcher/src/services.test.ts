import assert from "node:assert/strict";
import { test } from "node:test";
import { OLLAMA_ENV } from "./services";

test("Ollama starts on this Mac only, without the prompt cache", () => {
  assert.equal(OLLAMA_ENV.OLLAMA_HOST, "127.0.0.1:11434");
  assert.equal(OLLAMA_ENV.LLAMA_ARG_CACHE_RAM, "0"); // 0 turns the cache off; it held up to 8 GB
});
