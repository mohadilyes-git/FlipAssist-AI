// What the launcher starts when it isn't running already: Ollama (which runs
// Gemma) and FlipAssist's API. It stops only what it started, so a server you
// started yourself keeps running after FlipAssist quits. What each one prints
// goes to ~/Library/Logs/FlipAssist.
import { type ChildProcess, spawn } from "node:child_process";
import { closeSync, existsSync, mkdirSync, openSync, readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { GEMMA, modelsToWarm } from "./parts";

export const OLLAMA = "http://127.0.0.1:11434";
export const API = "http://127.0.0.1:8000";
export const LOGS = path.join(os.homedir(), "Library", "Logs", "FlipAssist");
// opened from the Dock, a Mac app gets a bare PATH, so Ollama is looked for where it installs
const OLLAMA_AT = ["/opt/homebrew/bin/ollama", "/usr/local/bin/ollama", "/Applications/Ollama.app/Contents/Resources/ollama"];
// No prompt cache: it kept up to 8 GB of older prompts' work in memory (half this Mac's) to save a few
// seconds on going back to an older listing, and helped freeze the Mac on 2 Sep. The last prompt's work
// is still kept, so drafting the same listing again stays quick, and answers don't change.
export const OLLAMA_ENV = { OLLAMA_HOST: "127.0.0.1:11434", LLAMA_ARG_CACHE_RAM: "0" };

/** How Gemma came up: ready, or why drafts will use code only. */
export type Gemma = "ready" | "no ollama" | "no model" | "failed";

type Started = { name: string; child: ChildProcess; gone: boolean };

/** The JSON a local server answers with, or null if it doesn't answer (in time). */
export async function ask(url: string, init: RequestInit = {}, seconds = 2): Promise<unknown> {
  try {
    const response = await fetch(url, { ...init, signal: AbortSignal.timeout(seconds * 1000) });
    return response.ok ? await response.json() : null;
  } catch {
    return null;
  }
}

/** Ask every quarter second until it's true, the time is up, or the process it waits for has gone. */
export async function until(check: () => Promise<boolean>, seconds: number, started?: Started): Promise<boolean> {
  const end = Date.now() + seconds * 1000;
  while (Date.now() < end) {
    if (await check()) return true;
    if (started?.gone) return false;
    await new Promise((wait) => setTimeout(wait, 250));
  }
  return false;
}

// FlipAssist's /health, not something else that happens to be on its port
const isFlipAssist = (body: unknown) => typeof body === "object" && body !== null && "local_model" in body;

export class Services {
  private started: Started[] = [];

  constructor(private readonly repo: string) {}

  /** Gemma: Ollama started if it isn't running, then the models every draft
   * uses loaded into memory (without waiting for them), so the first draft
   * doesn't wait for them to load: FlipAssist's own reader and flip-wording
   * (parts.modelsToWarm), or Gemma when the reader isn't there. */
  async gemma(): Promise<Gemma> {
    const up = async () => (await ask(`${OLLAMA}/api/tags`)) !== null;
    if (!(await up())) {
      const ollama = OLLAMA_AT.find((at) => existsSync(at));
      if (!ollama) return "no ollama";
      const started = this.start("ollama", ollama, ["serve"], OLLAMA_ENV);
      if (!(await until(up, 30, started))) return "failed";
    }
    const tags = (await ask(`${OLLAMA}/api/tags`)) as { models?: { name?: string }[] } | null;
    const installed = (tags?.models ?? []).map((m) => m.name ?? "");
    const warm = modelsToWarm(installed, this.env(), process.env);
    void (async () => { // one after the other: two loading at once fight over memory
      for (const { model, numCtx } of warm) {
        await ask(`${OLLAMA}/api/generate`, { method: "POST",
          body: JSON.stringify({ model, keep_alive: "30m", options: { num_ctx: numCtx } }) }, 120);
      }
    })();
    // what the launch screen says is Gemma's: it writes listings and, with the AI writer, messages
    return installed.some((name) => name === GEMMA.model) ? "ready" : "no model";
  }

  /** The text of the repo's .env, or "" when there's none. */
  private env(): string {
    try {
      return readFileSync(path.join(this.repo, ".env"), "utf8");
    } catch {
      return "";
    }
  }

  /** FlipAssist's API, started from the repo's own Python (.venv) if it isn't running. */
  async api(): Promise<boolean> {
    const up = async () => isFlipAssist(await ask(`${API}/health`));
    if (await up()) return true;
    const uvicorn = path.join(this.repo, ".venv", "bin", "uvicorn");
    if (!existsSync(uvicorn)) return false;
    const started = this.start("api", uvicorn, ["flip.api:app", "--host", "127.0.0.1", "--port", "8000"], {}, this.repo);
    return until(up, 90, started);
  }

  /** Stop what was started here: asked to stop first, made to after 5 seconds. */
  async stop() {
    await Promise.all(this.started.map((started) => new Promise<void>((done) => {
      if (started.gone) return done();
      const force = setTimeout(() => started.child.kill("SIGKILL"), 5000);
      started.child.once("exit", () => {
        clearTimeout(force);
        done();
      });
      started.child.kill("SIGTERM");
    })));
    this.started = [];
  }

  private start(name: string, command: string, args: string[], env: NodeJS.ProcessEnv = {}, cwd?: string): Started {
    mkdirSync(LOGS, { recursive: true });
    const log = openSync(path.join(LOGS, `${name}.log`), "a");
    const child = spawn(command, args, { cwd, env: { ...process.env, ...env }, stdio: ["ignore", log, log] });
    closeSync(log); // the process has its own copy
    const started: Started = { name, child, gone: false };
    child.once("exit", () => (started.gone = true));
    child.once("error", () => (started.gone = true)); // couldn't start at all
    this.started.push(started);
    return started;
  }
}
