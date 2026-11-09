// Makes the Windows icon: FlipAssist's 1024px PNG (icon.js draws it, as for the Mac) at each size Windows shows, in
// one .ico. build.ps1 runs it: electron build/ico.js <icon.png> <out.ico>
import { writeFileSync } from "node:fs";
import { app, nativeImage } from "electron";
import { icoFrom } from "./parts";

const SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256];

void app.whenReady().then(() => {
  const [png, out] = process.argv.slice(-2);
  const icon = nativeImage.createFromPath(png);
  if (icon.isEmpty()) throw new Error(`not a PNG: ${png}`);
  writeFileSync(out, icoFrom(SIZES.map((size) => ({ size, png: icon.resize({ width: size, height: size, quality: "best" }).toPNG() }))));
  app.quit();
});
