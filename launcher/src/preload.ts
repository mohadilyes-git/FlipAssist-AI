// Tells the page it's in FlipAssist's own Mac window, so it fills the window and
// leaves room for the Mac's traffic lights instead of drawing its own. That's all
// the page gets: no Node, no files, no key.
import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("flipassistShell", { window: "mac" });
