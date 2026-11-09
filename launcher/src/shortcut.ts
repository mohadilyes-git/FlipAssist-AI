// Makes FlipAssist's Windows shortcuts (build.ps1 runs it), each with the same app ID as the window (main.ts), so
// Windows ties a pinned FlipAssist to its open window instead of showing a second taskbar button. WScript.Shell's
// shortcuts can't carry one. Its working folder is your home, not the app's own: a folder in use can't be replaced
// by the next build.
//   electron build/shortcut.js <FlipAssist.exe> <working folder> <shortcut.lnk>...
import { app, shell } from "electron";
import { APP_ID } from "./parts";

void app.whenReady().then(() => {
  const [exe, cwd, ...links] = process.argv.slice(2);
  const made = links.every((link) => shell.writeShortcutLink(link, "create", {
    target: exe, cwd, icon: exe, iconIndex: 0, description: "FlipAssist", appUserModelId: APP_ID,
  }));
  app.exit(made && links.length > 0 ? 0 : 1);
});
