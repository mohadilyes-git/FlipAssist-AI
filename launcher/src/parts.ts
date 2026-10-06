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
export const WORDING = { setting: "FLIP_WORDING_MODEL", model: "flip-wording-3", numCtx: 2048 };
// Gemma reads when the reader isn't there, and writes when the AI writes (the AI writer, Rewrite)
export const GEMMA = { model: "gemma3:4b", numCtx: 8192 };

/** The models to load when FlipAssist opens, from the names Ollama has (its /api/tags) and the repo's .env:
 * flip-wording when it's there and on, then the reader (or Gemma, which reads when the reader isn't there or is
 * off). The reader goes last: when only one fits in memory, Ollama keeps the newest, and every draft reads first.
 * set: the environment the API starts with. Gemma isn't loaded beside the reader: on a 16 GB Mac three models don't
 * stay loaded together, so it loads when the AI first writes. */
export function modelsToWarm(installed: string[], env: string, set: Record<string, string | undefined> = {}): Warm[] {
  const has = (model: string) => installed.some((name) => name === model || name === `${model}:latest`);
  // as the API reads it: what's set already wins over .env (load_env never overwrites)
  const named = (own: { setting: string; model: string }) =>
    (set[own.setting] ?? settingFrom(env, own.setting) ?? own.model).trim();
  const reader = named(READER);
  const wording = named(WORDING);
  const warm: Warm[] = [];
  if (wording && has(wording)) warm.push({ model: wording, numCtx: WORDING.numCtx });
  if (reader && has(reader)) warm.push({ model: reader, numCtx: READER.numCtx });
  else if (has(GEMMA.model)) warm.push({ model: GEMMA.model, numCtx: GEMMA.numCtx });
  return warm;
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
