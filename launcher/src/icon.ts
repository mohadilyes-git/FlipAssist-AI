// Draws FlipAssist's icon, AlertFlip's bolt on its blue tile, as a 1024px PNG.
// build.sh turns it into the .icns the Mac shows: electron build/icon.js <out.png>
import { writeFileSync } from "node:fs";
import { app, BrowserWindow } from "electron";

// the tile sits inside the Mac's icon grid (824 of 1024), with its rounded corners and a soft shadow
const DRAW = `(() => {
  const size = 1024, tile = 824, at = (size - tile) / 2;
  const canvas = Object.assign(document.createElement("canvas"), { width: size, height: size });
  const pen = canvas.getContext("2d");
  const fill = pen.createLinearGradient(at, at, at + tile * 0.75, at + tile);
  fill.addColorStop(0, "#2f6fed");
  fill.addColorStop(0.6, "#1c47a8");
  fill.addColorStop(1, "#12295f");
  Object.assign(pen, { shadowColor: "rgba(18, 41, 95, 0.35)", shadowBlur: 40, shadowOffsetY: 16, fillStyle: fill });
  pen.beginPath();
  pen.roundRect(at, at, tile, tile, 185);
  pen.fill();
  pen.shadowColor = "transparent";
  const scale = 6.4, offset = at + (tile - 100 * scale) / 2;
  pen.setTransform(scale, 0, 0, scale, offset, offset);
  pen.fillStyle = "rgba(255, 255, 255, 0.28)";
  pen.fill(new Path2D("M62 12 30 58h16l-4 30 28-40H74z"));
  pen.fillStyle = "#fff";
  pen.fill(new Path2D("M56 14 24 60h16l-4 30 28-40H50z"));
  return canvas.toDataURL("image/png");
})()`;

void app.whenReady().then(async () => {
  const window = new BrowserWindow({ show: false });
  await window.loadURL("about:blank");
  const png: string = await window.webContents.executeJavaScript(DRAW);
  writeFileSync(process.argv[process.argv.length - 1], Buffer.from(png.split(",")[1], "base64"));
  app.quit();
});
