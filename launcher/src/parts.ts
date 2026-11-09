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
// Gemma 3 4B reads when the reader isn't there, and writes when the AI writes (the AI writer, Rewrite, eBay listings)
export const GEMMA = { model: "gemma3:4b", numCtx: 8192 };
// each model as the app names it (14 Oct): FlipAssist's own by their names, Gemma 3 4B in full
const SHOWN: Record<string, string> = { [GEMMA.model]: "Gemma 3 4B" };
const shown = (model: string) => SHOWN[model] ?? model;

/** The models to load when FlipAssist opens, from the names Ollama has (its /api/tags) and the repo's .env:
 * flip-wording when it's there and on, then the reader (or Gemma, which reads when the reader isn't there or is
 * off). The reader goes last: when only one fits in memory, Ollama keeps the newest, and every draft reads first.
 * set: the environment the API starts with. Gemma isn't loaded beside the reader: on a 16 GB Mac three models don't
 * stay loaded together, so it loads when the AI first writes. */
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

/** What the launch screen says once Ollama has Gemma 3 4B: every model FlipAssist uses that Ollama has, by the name
 * the app shows (flip-reader-5, flip-wording-4b, flip-kinds-1, flip-style-1b, Gemma 3 4B), and any of FlipAssist's
 * own that isn't installed, with what does its job instead (6 Oct review: it named them without looking; 14 Oct: all
 * five, not the reader and the wording model alone). A model switched off in .env isn't named. */
export function readyWords(installed: string[], env: string, set: Record<string, string | undefined> = {}): string {
  const has = hasIn(installed);
  const own: [string, string][] = [
    [named(READER, env, set), "so Gemma 3 4B reads"],
    [named(WORDING, env, set), "so code words the reason"],
    [named(KINDS, env, set), "so code's rules sort the flaws"],
    [named(STYLE, env, set), "so code reads your style alone"],
  ];
  const ready = [...new Set([...own.map(([model]) => model), GEMMA.model].filter((model) => model && has(model))
    .map(shown))];
  const missing = own.filter(([model]) => model && !has(model))
    .map(([model, instead]) => `${shown(model)} isn't installed, ${instead}`);
  const list = ready.length > 1 ? `${ready.slice(0, -1).join(", ")} and ${ready[ready.length - 1]}` : ready[0] ?? "";
  return [list ? `${list} ${ready.length > 1 ? "are" : "is"} ready` : "", ...missing].filter(Boolean).join("; ");
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
