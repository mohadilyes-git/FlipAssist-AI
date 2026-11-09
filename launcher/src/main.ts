// FlipAssist as a desktop app, on a Mac or (9 Nov) Windows. One double-click:
// 1. opens its window on the launch screen: "Starting FlipAssist…";
// 2. starts what isn't running yet: Gemma (through Ollama) and the API;
// 3. shows the app, the repo's built front end (frontend/dist), at app://flipassist/.
//    Its calls to /api/... are passed on to the API here, with the key from .env
//    added on the way: the page never sees the key, and unlike a local web
//    server, no other program on this Mac can borrow it;
// 4. on quit, stops only what it started.
// --selftest checks the window, the files and the API calls, then quits.
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { app, BrowserWindow, clipboard, nativeTheme, net, protocol, shell } from "electron";
import { APP_ID, fileFor, keyFrom, typeOf, windowLook } from "./parts";
import { API, type Gemma, LOGS, Services } from "./services";

const HOME = "app://flipassist";
const ICON = path.join(__dirname, "icon.png"); // build.sh and build.ps1 draw it (icon.js)
// Windows groups the window under the app's own name and icon, not Electron's; its shortcuts carry the same ID
if (process.platform === "win32") app.setAppUserModelId(APP_ID);
const { repo } = JSON.parse(readFileSync(path.join(__dirname, "config.json"), "utf8")) as { repo: string };
const dist = path.join(repo, "frontend", "dist");
const services = new Services(repo);
let key = "";
let win: BrowserWindow | null = null;

protocol.registerSchemesAsPrivileged([{
  scheme: "app",
  privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true },
}]);

/** app://flipassist/...: the built app's files, and /api/... passed on to the API. */
async function serve(request: Request): Promise<Response> {
  const url = new URL(request.url);
  if (url.pathname === "/api" || url.pathname.startsWith("/api/")) return toApi(request, url);
  const file = fileFor(dist, url.pathname);
  if (!file) return new Response("Not found", { status: 404 });
  try {
    return new Response(await readFile(file), { headers: { "Content-Type": typeOf(file) } });
  } catch {
    return new Response("Not found", { status: 404 });
  }
}

async function toApi(request: Request, url: URL): Promise<Response> {
  const headers = new Headers(request.headers);
  for (const name of ["host", "origin", "referer", "cookie", "content-length"]) headers.delete(name);
  headers.set("X-API-Key", key);
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer();
  try {
    return await net.fetch(`${API}${url.pathname.slice("/api".length)}${url.search}`,
      { method: request.method, headers, body });
  } catch {
    return Response.json({ detail: "FlipAssist's API has stopped: quit FlipAssist and open it again" }, { status: 502 });
  }
}

function open(): BrowserWindow {
  const window = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 760,
    minHeight: 600,
    show: false,
    title: "FlipAssist",
    ...windowLook(process.platform), // a Mac: its traffic lights over the app's top bar; Windows: its own title bar
    icon: process.platform !== "darwin" && existsSync(ICON) ? ICON : undefined, // a Mac takes the app's own
    backgroundColor: nativeTheme.shouldUseDarkColors ? "#12161f" : "#eef1f6",
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, sandbox: true },
  });
  window.once("ready-to-show", () => window.show());
  // the window only ever shows FlipAssist: links open in the browser, a photo dropped
  // outside the photo slots doesn't replace the app
  window.webContents.on("will-navigate", (event, url) => {
    if (url.startsWith(`${HOME}/`)) return;
    event.preventDefault();
    if (/^https?:\/\//.test(url)) void shell.openExternal(url);
  });
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url)) void shell.openExternal(url);
    return { action: "deny" };
  });
  return window;
}

// each model by its real name (4 Oct): Ollama runs flip-reader-5, flip-wording-4b, flip-kinds-1, flip-style-1b (6 Oct)
// and Gemma 3 4B on this device; once it's up, the launch screen names the ones it really has (parts.readyWords)
const GEMMA_WORDS: Record<Gemma, string> = {
  "ready": "flip-reader-5, flip-wording-4b, flip-kinds-1, flip-style-1b and Gemma 3 4B are ready",
  "no ollama": "Ollama isn't installed: drafts use code only",
  "no model": "Gemma 3 4B isn't downloaded: the AI writer can't write messages or eBay listings",
  "failed": `Ollama didn't start: drafts use code only (${LOGS}/ollama.log)`,
};

async function launch() {
  const window = (win = open());
  await window.loadFile(path.join(__dirname, "..", "splash.html"));
  const say = (state: Record<string, string>) =>
    window.webContents.executeJavaScript(`show(${JSON.stringify(state)})`).catch(() => undefined);
  if (!existsSync(path.join(dist, "index.html"))) {
    // Windows runs no scripts until told to, so the whole command
    const build = process.platform === "win32" ? "powershell -ExecutionPolicy Bypass -File launcher\\build.ps1" : "launcher/build.sh";
    return void say({ error: `The app isn't built yet: run ${build}` });
  }
  try {
    key = keyFrom(readFileSync(path.join(repo, ".env"), "utf8"));
  } catch {
    key = "";
  }
  const gemma = services.gemma().then((state) => {
    // named from what Ollama really has (6 Oct review), not a fixed list
    void say({ gemma: state === "ready" ? "ok" : "warn", gemmaWords: state === "ready" ? services.readyWords() : GEMMA_WORDS[state] });
    return state;
  });
  const api = await services.api();
  void say({ api: api ? "ok" : "bad", apiWords: api ? "Ready" : "Didn't start" });
  if (!api) return void say({ error: `FlipAssist's API didn't start: what it said is in ${LOGS}/api.log` });
  const health = (await (await net.fetch(`${API}/health`)).json()) as { flip_api_key_set?: boolean };
  if (!health.flip_api_key_set || key.length < 32) {
    return void say({ error: "FLIP_API_KEY in the repo's .env is missing or too short: it needs 32 characters or more" });
  }
  void net.fetch(`${API}/style`, { headers: { "X-API-Key": key } }).catch(() => undefined); // ready before it's needed
  await gemma;
  await say({ done: "Opening FlipAssist…" });
  await new Promise((wait) => setTimeout(wait, 600)); // a moment to read how Gemma is
  await window.loadURL(`${HOME}/`);
  if (process.argv.includes("--selftest")) await selfTest(window);
}

// Runs in the page: the window, the files and every kind of API call, with nothing saved or drafted
const CHECKS = `(async () => {
  const out = {};
  const json = async (r) => [r.status, await r.json().catch(() => null)];
  out.shell = document.documentElement.dataset.shell;
  out.computer = window.flipassistShell && window.flipassistShell.window;
  out.lights = getComputedStyle(document.querySelector(".lights")).visibility;
  out.title = document.title;
  out.health = (await json(await fetch("/api/health")))[0];
  out.style = (await json(await fetch("/api/style")))[0];
  const form = new FormData();
  form.append("title", "iPhone 13 128GB");
  form.append("photos", new Blob(["%PDF-1.4 not a photo"], { type: "image/jpeg" }), "photo.jpg");
  const [uploaded, said] = await json(await fetch("/api/listings/draft", { method: "POST", body: form }));
  out.upload = [uploaded, said && said.detail];
  const [posted, answer] = await json(await fetch("/api/messages/draft", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ listing: { title: "x", asking_price: "0" } }) }));
  out.json = [posted, answer && answer.detail];
  out.escape = [(await fetch("/%2e%2e/%2e%2e/.env")).status, (await fetch("/../../.env")).status];
  await navigator.clipboard.writeText("FlipAssist self-test");
  localStorage.setItem("flipassist.selftest", "1");
  out.storage = localStorage.getItem("flipassist.selftest");
  localStorage.removeItem("flipassist.selftest");
  return out;
})()`;

async function selfTest(window: BrowserWindow) {
  const kept = await clipboard.readText(); // the test copies something: whatever you had is put back
  app.focus({ steal: true }); // a page may only copy while its window is in front
  window.focus();
  await new Promise((wait) => setTimeout(wait, 1500)); // the app's first calls
  let result: Record<string, unknown>;
  try {
    result = await window.webContents.executeJavaScript(CHECKS, true);
    const copied = await clipboard.readText();
    result.clipboard = copied === "FlipAssist self-test" || `held ${JSON.stringify(copied.slice(0, 40))}`;
  } catch (e) {
    result = { error: String(e) };
  }
  await clipboard.writeText(kept);
  if (process.env.FLIPASSIST_SHOT) writeFileSync(process.env.FLIPASSIST_SHOT, (await window.webContents.capturePage()).toPNG());
  const ok = result.shell === "window" && result.computer === (process.platform === "darwin" ? "mac" : "windows")
    && result.lights === "hidden" && result.health === 200 && result.style === 200
    && JSON.stringify(result.upload) === JSON.stringify([422, "photo.jpg: send photos as JPEG, PNG, HEIC or WebP"])
    && Array.isArray(result.json) && result.json[0] === 422 && String(result.json[1]).includes("under £1")
    && JSON.stringify(result.escape) === "[404,404]" && result.storage === "1" && result.clipboard === true;
  console.log(`SELFTEST ${ok ? "PASSED" : "FAILED"} ${JSON.stringify(result)}`);
  await services.stop();
  app.exit(ok ? 0 : 1);
}

if (!app.requestSingleInstanceLock()) {
  app.quit(); // already open: that window comes to the front instead
} else {
  app.on("second-instance", () => {
    if (win?.isMinimized()) win.restore();
    win?.focus();
  });
  void app.whenReady().then(() => {
    protocol.handle("app", serve);
    // a fault while starting shows on the launch screen, which otherwise waits forever (3 Oct: a launch right after
    // another FlipAssist quit stayed on "Starting FlipAssist…" and started nothing)
    void launch().catch((error: unknown) => {
      const words = `FlipAssist couldn't start (${String(error).slice(0, 160)}): quit it and open it again`;
      void win?.webContents.executeJavaScript(`show(${JSON.stringify({ error: words })})`).catch(() => undefined);
      if (process.argv.includes("--selftest")) {
        console.log(`SELFTEST FAILED ${JSON.stringify({ error: String(error) })}`);
        void services.stop().finally(() => app.exit(1));
      }
    });
  });
}

app.on("window-all-closed", () => app.quit());
let stopping = false;
app.on("before-quit", (event) => {
  if (stopping) return;
  event.preventDefault(); // stop what was started here first
  stopping = true;
  void services.stop().finally(() => app.quit());
});
