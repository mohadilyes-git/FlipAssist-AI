// What the launcher starts when it isn't running already: Ollama (which runs
// Gemma) and FlipAssist's API. It stops only what it started, so a server you
// started yourself keeps running after FlipAssist quits. What each one prints
// goes to ~/Library/Logs/FlipAssist on a Mac, %LOCALAPPDATA%\FlipAssist\logs on
// Windows (parts.logsFolder).
import { type ChildProcess, spawn } from "node:child_process";
import { closeSync, existsSync, mkdirSync, openSync, readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { apiCommand, GEMMA, logsFolder, modelsToWarm, ollamaPlaces, readyWords } from "./parts";

export const OLLAMA = "http://127.0.0.1:11434";
export const API = "http://127.0.0.1:8000";
export const LOGS = logsFolder(process.platform, os.homedir(), process.env);
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
  private installed: string[] = []; // the models Ollama listed when it came up

  constructor(private readonly repo: string) {}

  /** Gemma: Ollama started if it isn't running, then the models every draft
   * uses loaded into memory (without waiting for them), so the first draft
   * doesn't wait for them to load: FlipAssist's own reader and flip-wording
   * (parts.modelsToWarm), or Gemma when the reader isn't there. */
  async gemma(): Promise<Gemma> {
    const up = async () => (await ask(`${OLLAMA}/api/tags`)) !== null;
    if (!(await up())) {
      const ollama = ollamaPlaces(process.platform, process.env).find((at) => existsSync(at));
      if (!ollama) return "no ollama";
      // on Windows from your home folder, not the app's: a folder something runs in can't be replaced by the next build
      const started = this.start("ollama", ollama, ["serve"], OLLAMA_ENV, process.platform === "win32" ? os.homedir() : undefined);
      if (!(await until(up, 30, started))) return "failed";
    }
    const tags = (await ask(`${OLLAMA}/api/tags`)) as { models?: { name?: string }[] } | null;
    const installed = (this.installed = (tags?.models ?? []).map((m) => m.name ?? ""));
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

  /** What the launch screen says once Gemma is ready: the models Ollama has, and a missing one with what does its
   * job instead (parts.readyWords). */
  readyWords(): string {
    return readyWords(this.installed, this.env(), process.env);
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
    const { command, args, env } = apiCommand(this.repo, process.platform); // uvicorn, as this computer runs it
    if (!existsSync(command)) return false;
    const started = this.start("api", command, args, env, this.repo);
    return until(up, 90, started);
  }

  /** Stop what was started here: asked to stop first, made to after 5 seconds. */
  async stop() {
    await Promise.all(this.started.map((started) => new Promise<void>((done) => {
      if (started.gone) return done();
      const force = setTimeout(() => end(started, true), 5000);
      started.child.once("exit", () => {
        clearTimeout(force);
        done();
      });
      end(started, false);
    })));
    this.started = [];
  }

  private start(name: string, command: string, args: string[], env: NodeJS.ProcessEnv = {}, cwd?: string): Started {
    mkdirSync(LOGS, { recursive: true });
    const log = openSync(path.join(LOGS, `${name}.log`), "a");
    // windowsHide: on Windows, no console window pops up for Ollama or the API
    const child = spawn(command, args, { cwd, env: { ...process.env, ...env }, stdio: ["ignore", log, log], windowsHide: true });
    closeSync(log); // the process has its own copy
    const started: Started = { name, child, gone: false };
    child.once("exit", () => (started.gone = true));
    child.once("error", () => (started.gone = true)); // couldn't start at all
    this.started.push(started);
    return started;
  }
}

/** Stop a process started here: on a Mac it's asked to (SIGTERM), then made to (SIGKILL). Windows has no asking, and
 * a process's helpers (Ollama's model runners) don't stop with it there, so taskkill ends the whole tree at once
 * (and again if it's still there after 5 seconds). */
function end(started: Started, force: boolean) {
  if (process.platform === "win32") {
    if (!started.child.pid) return;
    // by its full path (a bare name hangs on the PATH), and if it can't run, the process itself is ended, so quitting
    // never waits forever
    const taskkill = path.join(process.env.SystemRoot ?? "C:\\Windows", "System32", "taskkill.exe");
    spawn(taskkill, ["/pid", String(started.child.pid), "/t", "/f"], { stdio: "ignore", windowsHide: true })
      .once("error", () => started.child.kill());
    return;
  }
  started.child.kill(force ? "SIGKILL" : "SIGTERM");
}
