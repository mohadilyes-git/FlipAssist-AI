import assert from "node:assert/strict";
import { test } from "node:test";
import { apiCommand, fileFor, icoFrom, keyFrom, logsFolder, modelsToWarm, ollamaPlaces, readyWords, settingFrom, typeOf,
  windowLook, withOwnKey } from "./parts";

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
  const all = ["gemma3:4b", "flip-reader-5:latest", "flip-wording-4b:latest", "flip-kinds-1:latest", "flip-style-1b:latest",
    "flip-wording-3:latest", "flip-kinds-2:latest"];
  // every model FlipAssist uses, by the app's names (14 Oct), and none it doesn't (flip-wording-3, flip-kinds-2)
  assert.equal(readyWords(all, ""), "flip-reader-5, flip-wording-4b, flip-kinds-1, flip-style-1b and Gemma 3 4B are ready");
  assert.equal(readyWords(["gemma3:4b", "flip-reader-5:latest", "flip-kinds-1:latest", "flip-style-1b:latest"], ""),
    "flip-reader-5, flip-kinds-1, flip-style-1b and Gemma 3 4B are ready; flip-wording-4b isn't installed, so code words "
    + "the reason");
  assert.equal(readyWords(["gemma3:4b"], "FLIP_WORDING_MODEL=\nFLIP_KINDS_MODEL=\nFLIP_STYLE_AI="),
    "Gemma 3 4B is ready; flip-reader-5 isn't installed, so Gemma 3 4B reads");
  assert.equal(readyWords(["gemma3:4b", "flip-reader-5:latest", "flip-wording-4b:latest"], ""),
    "flip-reader-5, flip-wording-4b and Gemma 3 4B are ready; flip-kinds-1 isn't installed, so code's rules sort the "
    + "flaws; flip-style-1b isn't installed, so code reads your style alone");
  // switched off in .env, or by what's set already, as the API reads them; plain Gemma 3 4B reading your style is one
  assert.equal(readyWords(all, "FLIP_KINDS_MODEL=", { FLIP_STYLE_AI: "gemma3:4b" }),
    "flip-reader-5, flip-wording-4b and Gemma 3 4B are ready");
});

// Windows as well as the Mac (9 Nov): every answer is checked for both, on this Mac
test("Ollama is looked for where it installs: Homebrew or Ollama.app on a Mac, the user's Programs on Windows", () => {
  assert.deepEqual(ollamaPlaces("darwin"), ["/opt/homebrew/bin/ollama", "/usr/local/bin/ollama",
    "/Applications/Ollama.app/Contents/Resources/ollama"]); // as before 9 Nov
  assert.deepEqual(ollamaPlaces("win32", { LOCALAPPDATA: "C:\\Users\\Sam\\AppData\\Local", ProgramFiles: "C:\\Program Files" }),
    ["C:\\Users\\Sam\\AppData\\Local\\Programs\\Ollama\\ollama.exe", "C:\\Program Files\\Ollama\\ollama.exe"]);
  assert.deepEqual(ollamaPlaces("win32", {}), []); // no folders known: Ollama counts as not installed, as on a Mac
});

test("the API starts from the repo's own Python: uvicorn on a Mac, python.exe -m uvicorn in UTF-8 on Windows", () => {
  assert.deepEqual(apiCommand("/Users/sam/flip", "darwin"), { command: "/Users/sam/flip/.venv/bin/uvicorn",
    args: ["flip.api:app", "--host", "127.0.0.1", "--port", "8000"], env: {} }); // as before 9 Nov
  assert.deepEqual(apiCommand("C:\\Users\\Sam\\flip", "win32"), { command: "C:\\Users\\Sam\\flip\\.venv\\Scripts\\python.exe",
    args: ["-m", "uvicorn", "flip.api:app", "--host", "127.0.0.1", "--port", "8000"], env: { PYTHONUTF8: "1" } });
});

test("logs go to ~/Library/Logs on a Mac and the user's local app data on Windows", () => {
  assert.equal(logsFolder("darwin", "/Users/sam"), "/Users/sam/Library/Logs/FlipAssist"); // as before 9 Nov
  assert.equal(logsFolder("win32", "C:\\Users\\Sam", { LOCALAPPDATA: "C:\\Users\\Sam\\AppData\\Local" }),
    "C:\\Users\\Sam\\AppData\\Local\\FlipAssist\\logs");
  assert.equal(logsFolder("win32", "C:\\Users\\Sam", {}), "C:\\Users\\Sam\\AppData\\Local\\FlipAssist\\logs");
});

test("the window: the Mac's traffic lights over the app's bar; Windows' own title bar, so it can always be closed", () => {
  assert.deepEqual(windowLook("darwin"), { titleBarStyle: "hiddenInset", trafficLightPosition: { x: 16, y: 15 } });
  const windows = windowLook("win32");
  assert.equal(windows.titleBarStyle, undefined); // a hidden title bar on Windows has no close button
  assert.equal(windows.autoHideMenuBar, true);
});

test("the Windows icon is a real .ico: its header, one entry per size (256 written as 0), then each PNG", () => {
  const png = (n: number) => Buffer.from([0x89, 0x50, 0x4e, 0x47, n]);
  const ico = icoFrom([{ size: 16, png: png(1) }, { size: 256, png: png(2) }]);
  assert.equal(ico.readUInt16LE(0), 0);
  assert.equal(ico.readUInt16LE(2), 1); // an icon, not a cursor
  assert.equal(ico.readUInt16LE(4), 2);
  assert.deepEqual([ico[6], ico[7], ico[22], ico[23]], [16, 16, 0, 0]);
  assert.equal(ico.readUInt16LE(6 + 6), 32); // bits per pixel
  const first = ico.readUInt32LE(6 + 12), second = ico.readUInt32LE(22 + 12);
  assert.equal(first, 6 + 32);
  assert.deepEqual([...ico.subarray(first, first + 5)], [...png(1)]);
  assert.deepEqual([...ico.subarray(second, second + 5)], [...png(2)]);
  assert.equal(ico.length, 6 + 32 + 10);
});

test("a fresh download gets its own FLIP_API_KEY on first launch, and nobody's Claude key (9 Nov)", () => {
  const key = "k".repeat(43);
  const made = withOwnKey("", key)!;
  assert.equal(keyFrom(made), key);
  assert.match(made, /^ANTHROPIC_API_KEY=$/m); // empty: the person's own Claude key goes there
  const short = withOwnKey("ANTHROPIC_API_KEY=theirs\nFLIP_API_KEY=short\nPRICES_URL=x\n", key)!;
  assert.equal(keyFrom(short), key);
  assert.match(short, /^ANTHROPIC_API_KEY=theirs$/m);
  assert.match(short, /^PRICES_URL=x$/m);
  assert.equal(short.match(/^FLIP_API_KEY=/gm)?.length, 1);
  assert.equal(withOwnKey(`FLIP_API_KEY=${"a".repeat(32)}\n`, key), null); // a key that's long enough is kept as it is
});
