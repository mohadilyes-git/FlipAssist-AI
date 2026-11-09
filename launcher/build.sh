#!/bin/sh
# Builds FlipAssist.app, which opens FlipAssist in its own Mac window, and puts
# it in your Applications folder (~/Applications). Run it again after changing
# the app or the launcher:
#   launcher/build.sh
set -eu
here=$(cd "$(dirname "$0")" && pwd)
repo=$(dirname "$here")

# the web app, into frontend/dist: the window shows it from there
cd "$repo/frontend"
[ -d node_modules ] || npm ci
npm run build

# the launcher, into build/, with where the repo is (Gemma's API and the app live there)
cd "$here"
[ -d node_modules ] || npm ci
npm run build
node -e 'require("fs").writeFileSync("build/config.json", JSON.stringify({ repo: process.argv[1] }) + "\n")' "$repo"

# the icon, drawn once at 1024px, then in every size the Mac shows
npx electron build/icon.js "$here/build/icon.png"
rm -rf build/FlipAssist.iconset
mkdir build/FlipAssist.iconset
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" build/icon.png --out "build/FlipAssist.iconset/icon_${size}x${size}.png" >/dev/null
  sips -z $((size * 2)) $((size * 2)) build/icon.png --out "build/FlipAssist.iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns build/FlipAssist.iconset -o build/FlipAssist.icns

# the app: Electron with the launcher inside, signed for this Mac
arch=$(uname -m | sed 's/x86_64/x64/')
npx electron-packager . FlipAssist --platform=darwin --arch="$arch" --icon=build/FlipAssist.icns \
  --out=out --overwrite --quiet --app-bundle-id=com.alertflip.flipassist --app-version=0.1.0 \
  --ignore='^/(src|out|build\.sh|build\.ps1|windows-setup\.ps1|export-models\.sh|tsconfig\.json|build/FlipAssist\.iconset|build/FlipAssist\.ico|build/[^/]*\.test\.js)($|/)'
built="out/FlipAssist-darwin-$arch/FlipAssist.app"
codesign --force --deep --sign - "$built"

# into ~/Applications, where Spotlight and Launchpad find it; an older build goes to the Trash
mkdir -p "$HOME/Applications"
if [ -e "$HOME/Applications/FlipAssist.app" ]; then
  /usr/bin/trash "$HOME/Applications/FlipAssist.app"
fi
ditto "$built" "$HOME/Applications/FlipAssist.app"
echo "Built $HOME/Applications/FlipAssist.app"
