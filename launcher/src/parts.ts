// The launcher's parts that need no Electron, so they can be tested on their
// own: the key from .env, a file of the built app (never one outside it), and
// what kind of file it is.
import path from "node:path";

/** A setting from the text of the repo's .env, read the way the API reads it
 * (flip.draft.load_env): the first one counts, and spaces and quotes around
 * it don't. undefined when it isn't there, "" when it's there but empty. */
export function settingFrom(env: string, name: string): string | undefined {
  for (const line of env.split(/\r?\n/)) {
    if (!line.includes("=") || line.trimStart().startsWith("#")) continue;
    const at = line.indexOf("=");
    if (line.slice(0, at).trim() === name) {
      return line.slice(at + 1).trim().replace(/^["']+|["']+$/g, "").trim();
    }
  }
  return undefined;
}

/** FLIP_API_KEY from the text of the repo's .env; "" when there's none. */
export function keyFrom(env: string): string {
  return settingFrom(env, "FLIP_API_KEY") ?? "";
}

/** A model to load when FlipAssist opens, with the working memory (tokens) the API asks it with: Ollama loads a
 * model again when that changes, which would waste the load. */
export type Warm = { model: string; numCtx: number };

// FlipAssist's own models, which every draft uses (3 Oct): its reader reads each listing (flip.reader), and
// flip-wording words the offer's reason (flip.wording). A setting in .env renames one, or turns it off when empty.
export const READER = { setting: "FLIP_READER_MODEL", model: "flip-reader-5", numCtx: 8192 };
export const WORDING = { setting: "FLIP_WORDING_MODEL", model: "flip-wording-4b", numCtx: 2048 }; // flip-wording-3 before 6 Oct
// ...and the two the price tab and Your style use (6 Oct): flip-kinds sorts a UK price's flaws (flip.kinds), and
// flip-style reads your style (flip.style_ai). The API reads the same settings: an empty one switches it off
export const KINDS = { setting: "FLIP_KINDS_MODEL", model: "flip-kinds-1" };
export const STYLE = { setting: "FLIP_STYLE_AI", model: "flip-style-1b" };
// Gemma 3 4B reads when the reader isn't there (or doesn't answer), rewords a message for Rewrite, and writes eBay
// listings when there's no Claude key (or FLIP_LISTING_WRITER=gemma): the app has no AI writer of messages (14 Oct)
export const GEMMA = { model: "gemma3:4b", numCtx: 8192 };
// each model as the app names it (14 Oct): FlipAssist's own by their names, Gemma 3 4B in full
const SHOWN: Record<string, string> = { [GEMMA.model]: "Gemma 3 4B" };
const shown = (model: string) => SHOWN[model] ?? model;

/** The models to load when FlipAssist opens, from the names Ollama has (its /api/tags) and the repo's .env:
 * flip-wording when it's there and on, then the reader (or Gemma, which reads when the reader isn't there or is
 * off). The reader goes last: when only one fits in memory, Ollama keeps the newest, and every draft reads first.
 * set: the environment the API starts with. Gemma isn't loaded beside the reader: on a 16 GB Mac three models don't
 * stay loaded together, so it loads when it's first asked (Rewrite, or List on eBay with no Claude key). */
export function modelsToWarm(installed: string[], env: string, set: Record<string, string | undefined> = {}): Warm[] {
  const has = hasIn(installed);
  const reader = named(READER, env, set);
  const wording = named(WORDING, env, set);
  const warm: Warm[] = [];
  if (wording && has(wording)) warm.push({ model: wording, numCtx: WORDING.numCtx });
  if (reader && has(reader)) warm.push({ model: reader, numCtx: READER.numCtx });
  else if (has(GEMMA.model)) warm.push({ model: GEMMA.model, numCtx: GEMMA.numCtx });
  return warm;
}

/** A model's name as the API reads it: what's set already wins over .env (load_env never overwrites); "" = off. */
function named(own: { setting: string; model: string }, env: string, set: Record<string, string | undefined>): string {
  return (set[own.setting] ?? settingFrom(env, own.setting) ?? own.model).trim();
}

/** Whether Ollama's list of names has a model ("flip-reader-5" or "flip-reader-5:latest"). */
function hasIn(installed: string[]): (model: string) => boolean {
  return (model) => installed.some((name) => name === model || name === `${model}:latest`);
}

/** What the launch screen says once Ollama is up: every model FlipAssist uses that Ollama has, by the name the app
 * shows (flip-reader-5, flip-wording-4b, flip-kinds-1, flip-style-1b, Gemma 3 4B), and any of FlipAssist's own that
 * isn't installed, with what does its job instead (6 Oct review: it named them without looking; 14 Oct: all five, not
 * the reader and the wording model alone). A model switched off in .env isn't named. */
export function readyWords(installed: string[], env: string, set: Record<string, string | undefined> = {}): string {
  const has = hasIn(installed);
  const own: [string, string][] = [
    // Gemma 3 4B reads in the reader's place, and code when Gemma 3 4B isn't there either (flip.reader.reader_for)
    [named(READER, env, set), has(GEMMA.model) ? "so Gemma 3 4B reads" : "so code reads"],
    [named(WORDING, env, set), "so code words the reason"],
    [named(KINDS, env, set), "so code's rules sort the flaws"],
    [named(STYLE, env, set), "so code reads your style alone"],
  ];
  const ready = [...new Set([...own.map(([model]) => model), GEMMA.model].filter((model) => model && has(model))
    .map(shown))];
  const missing = own.filter(([model]) => model && !has(model))
    .map(([model, instead]) => `${shown(model)} isn't installed, ${instead}`);
  const list = listed(ready);
  return [list ? `${list} ${ready.length > 1 ? "are" : "is"} ready` : "", ...missing].filter(Boolean).join("; ");
}

/** What the launch screen says when Gemma 3 4B isn't ready, and what still runs as the API decides it (15 Nov review:
 * it said "the AI writer can't write messages or eBay listings", and "drafts use code only" without Ollama). A model on
 * this device that can't answer is never sent to Claude in its place, so without Gemma 3 4B Rewrite can't run. With
 * your Claude key, Claude Haiku 5.5 writes List on eBay (unless FLIP_LISTING_WRITER=gemma) and, with the AlertFlip API
 * set, judges how bad a UK price's damage is, with Ollama or without. "no model": the models Ollama has, as readyWords
 * says them, then what Gemma 3 4B's absence stops. log: where Ollama's own words are, for "failed". */
export function notReadyWords(state: "no ollama" | "no model" | "failed", installed: string[], env: string,
  set: Record<string, string | undefined> = {}, log = ""): string {
  const setting = (name: string) => (set[name] ?? settingFrom(env, name) ?? "").trim(); // as named() reads them
  const claude = !!setting("ANTHROPIC_API_KEY");
  // as flip.api.listing_writer_name: Gemma 3 4B writes them with no Claude key, or when .env asks for it
  const claudeLists = claude && setting("FLIP_LISTING_WRITER").toLowerCase() !== "gemma";
  const cant = ["Rewrite can't run",
    ...(claudeLists ? [] : ["List on eBay can't write the condition note or description"])];
  if (state === "no model") {
    return [readyWords(installed, env, set), `Gemma 3 4B isn't installed, so ${listed(cant)}`]
      .filter(Boolean).join("; ");
  }
  // the damage judge (flip.api.damage_judge) asks no model on this device
  const judges = claude && !!setting("PRICES_URL") && !!setting("PRICES_KEY");
  const still = [...(claudeLists ? ["writes List on eBay"] : []),
    ...(judges ? ["judges how bad a UK price's damage is"] : [])];
  const why = state === "no ollama" ? "Ollama isn't installed" : `Ollama didn't start (what it said is in ${log})`;
  return `${why}: ${listed(["code does the models' work", ...cant])}`
    + (still.length ? `; Claude Haiku 5.5 still ${listed(still)}` : "");
}

/** ["a", "b", "c"] -> "a, b and c". */
function listed(words: string[]): string {
  return words.length > 1 ? `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}` : words[0] ?? "";
}

/** The file of the built app that a path asks for ("/" is index.html), or null
 * for one outside it: "/../../.env" never reaches the repo's keys. */
export function fileFor(dist: string, urlPath: string): string | null {
  let wanted: string;
  try {
    wanted = decodeURIComponent(urlPath);
  } catch {
    return null; // "%E0" and the like: not a path
  }
  if (wanted.includes("\0")) return null;
  const file = path.join(dist, wanted === "/" || wanted === "" ? "index.html" : wanted);
  return file.startsWith(dist + path.sep) ? file : null;
}

const TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".txt": "text/plain; charset=utf-8",
};

/** What a file is, by its ending, for the Content-Type the page is sent with. */
export function typeOf(file: string): string {
  return TYPES[path.extname(file).toLowerCase()] ?? "application/octet-stream";
}

/** FlipAssist's app ID: the Mac bundle's (build.sh), and on Windows the window's and its shortcuts' (main.ts,
 * shortcut.ts), which must be the same for a pinned FlipAssist to light up when it's open. */
export const APP_ID = "com.alertflip.flipassist";

// Windows as well as the Mac (9 Nov 2026, the owner: "make it compatible for windows as well"). Each answer below
// depends only on what it's given, so the tests on a Mac check the Windows answers too.
type Env = Record<string, string | undefined>;

/** Where Ollama is looked for when it isn't running. Opened from the Dock or the Start menu, the app gets a bare
 * PATH, so it looks where Ollama installs: Homebrew or Ollama.app on a Mac, the user's own Programs folder (or
 * Program Files) on Windows. */
export function ollamaPlaces(platform: string, env: Env = {}): string[] {
  if (platform === "darwin") {
    return ["/opt/homebrew/bin/ollama", "/usr/local/bin/ollama", "/Applications/Ollama.app/Contents/Resources/ollama"];
  }
  if (platform === "win32") {
    const win = path.win32;
    return [env.LOCALAPPDATA && win.join(env.LOCALAPPDATA, "Programs", "Ollama", "ollama.exe"),
      env.ProgramFiles && win.join(env.ProgramFiles, "Ollama", "ollama.exe")].filter((at): at is string => !!at);
  }
  return ["/usr/local/bin/ollama", "/usr/bin/ollama"];
}

/** How FlipAssist's API is started from the repo's own Python (.venv). On Windows it's the .venv's python.exe running
 * uvicorn itself, not the uvicorn.exe stub in front of it, so stopping it stops the server; and it reads text files
 * as UTF-8 ("£", emoji) as a Mac does, not in Windows' older code page. */
export function apiCommand(repo: string, platform: string): { command: string; args: string[]; env: Env } {
  const serve = ["flip.api:app", "--host", "127.0.0.1", "--port", "8000"];
  if (platform === "win32") {
    return { command: path.win32.join(repo, ".venv", "Scripts", "python.exe"), args: ["-m", "uvicorn", ...serve],
      env: { PYTHONUTF8: "1" } };
  }
  return { command: path.posix.join(repo, ".venv", "bin", "uvicorn"), args: serve, env: {} };
}

/** How the repo's own Python (.venv) that the API runs in is set up, run in the repo: windows-setup.ps1 on Windows,
 * Python 3.11 and requirements.txt elsewhere, as the README does. */
export function pythonSetup(platform: string): string {
  return platform === "win32" ? "powershell -ExecutionPolicy Bypass -File launcher\\windows-setup.ps1"
    : "python3.11 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt";
}

/** Where what Ollama and the API print goes: ~/Library/Logs/FlipAssist on a Mac, %LOCALAPPDATA%\FlipAssist\logs on
 * Windows. */
export function logsFolder(platform: string, home: string, env: Env = {}): string {
  if (platform === "win32") {
    return path.win32.join(env.LOCALAPPDATA || path.win32.join(home, "AppData", "Local"), "FlipAssist", "logs");
  }
  if (platform === "darwin") return path.posix.join(home, "Library", "Logs", "FlipAssist");
  return path.posix.join(home, ".local", "state", "FlipAssist", "logs");
}

/** The window's frame. On a Mac: the app's own top bar, with the Mac's traffic lights over it. On Windows: the
 * system's own title bar (minimise, maximise, close; a hidden one would leave no way to close the window), with the
 * menu bar out of sight until Alt is pressed. */
export function windowLook(platform: string): {
  titleBarStyle?: "hiddenInset"; trafficLightPosition?: { x: number; y: number }; autoHideMenuBar?: boolean;
} {
  return platform === "darwin" ? { titleBarStyle: "hiddenInset", trafficLightPosition: { x: 16, y: 15 } }
    : { autoHideMenuBar: true };
}

/** A Windows .ico of the icon at each size, every one stored as a PNG (which Windows reads since Vista): a 6-byte
 * header, a 16-byte entry per size (256 is written as 0), then the PNGs. */
export function icoFrom(images: { size: number; png: Buffer }[]): Buffer {
  const head = Buffer.alloc(6 + 16 * images.length);
  head.writeUInt16LE(0, 0); // reserved
  head.writeUInt16LE(1, 2); // 1: an icon
  head.writeUInt16LE(images.length, 4);
  let at = head.length;
  images.forEach(({ size, png }, n) => {
    const entry = 6 + 16 * n;
    head.writeUInt8(size >= 256 ? 0 : size, entry); // width
    head.writeUInt8(size >= 256 ? 0 : size, entry + 1); // height
    head.writeUInt16LE(1, entry + 4); // colour planes (bytes 2-3: no palette, reserved)
    head.writeUInt16LE(32, entry + 6); // bits per pixel
    head.writeUInt32LE(png.length, entry + 8);
    head.writeUInt32LE(at, entry + 12);
    at += png.length;
  });
  return Buffer.concat([head, ...images.map((image) => image.png)]);
}

/** The .env with this computer's own FLIP_API_KEY when it has none of 32 characters or more, else null (9 Nov: a
 * fresh download has no .env, and the launcher refused to start without the key). A short one is replaced and the
 * rest kept as it was; a new .env also says where your own Claude key goes, and what it pays Claude for, as
 * .env.example does (15 Nov review: "Claude's checks and backup" left out the eBay listings and the damage judge).
 * key: a new random one. */
export function withOwnKey(env: string, key: string): string | null {
  if (keyFrom(env).length >= 32) return null;
  const kept = env.split(/\r?\n/).filter((line) => !/^\s*FLIP_API_KEY\s*=/.test(line));
  while (kept.length && kept[kept.length - 1].trim() === "") kept.pop();
  const fresh = env.trim() ? [] : ["# FlipAssist's settings on this computer. Never uploaded (see .gitignore).",
    "# Your own Claude API key (console.anthropic.com): Claude Haiku 5.5 checks each offer's reason, writes eBay listings",
    "# and judges how bad a UK price's damage is; Claude Sonnet 5.5 fixes a flagged reason, decides how bad the damage",
    "# is when code and Haiku disagree, and steps in when this computer's models can't. You pay Anthropic for what you",
    "# use. Without it, everything runs on this computer. Put it after the =",
    "ANTHROPIC_API_KEY=", ""];
  return [...kept, ...fresh, "# this computer's own key for FlipAssist's API, made on first launch", `FLIP_API_KEY=${key}`, ""].join("\n");
}
