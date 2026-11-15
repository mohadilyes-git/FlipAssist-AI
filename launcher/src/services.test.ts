import assert from "node:assert/strict";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { pythonSetup } from "./parts";
import { OLLAMA_ENV, Services } from "./services";

test("Ollama starts on this Mac only, without the prompt cache", () => {
  assert.equal(OLLAMA_ENV.OLLAMA_HOST, "127.0.0.1:11434");
  assert.equal(OLLAMA_ENV.LLAMA_ARG_CACHE_RAM, "0"); // 0 turns the cache off; it held up to 8 GB
});

test("with no Python environment the API isn't started, and the launch screen says how to set it up (15 Nov review)",
  async (t) => {
    // no API answers, and the repo has no .venv: nothing is started, so there's no api.log of this launch to send you to
    t.mock.method(globalThis, "fetch", async () => {
      throw new TypeError("nothing answers on the API's port");
    });
    const repo = path.join(os.tmpdir(), `flipassist-no-venv-${process.pid}`);
    assert.equal(await new Services(repo).api(), "FlipAssist's API didn't start: its Python environment (.venv) isn't "
      + `set up. In ${repo}, run ${pythonSetup(process.platform)}`);
  });
