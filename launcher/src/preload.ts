// Tells the page it's in FlipAssist's own window, and on which computer: on a Mac it
// leaves room for the Mac's traffic lights instead of drawing its own; on Windows
// (9 Nov) the system's title bar is above it, so it draws none. That's all the
// page gets: no Node, no files, no key.
import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("flipassistShell", { window: process.platform === "darwin" ? "mac" : "windows" });
