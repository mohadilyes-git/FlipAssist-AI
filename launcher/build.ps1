# Builds FlipAssist for Windows (9 Nov 2026): FlipAssist.exe, the same app as the Mac's FlipAssist.app, with the
# same splash screen, icon and screens. It goes in your own Programs folder, with a Start menu and a desktop shortcut.
# Run windows-setup.ps1 once first (it runs this at the end); run this again after changing the app or the launcher.
# In PowerShell, from the repo folder:
#   powershell -ExecutionPolicy Bypass -File launcher\build.ps1
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here

# a step that stops the build when its program fails (PowerShell doesn't stop on a program's exit code by itself)
function Step([string]$what, [scriptblock]$run) {
  Write-Host "- $what"
  & $run
  if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" }
}

if (Get-Process -Name FlipAssist -ErrorAction SilentlyContinue) { throw "FlipAssist is open: quit it, then run this again" }

# the web app, into frontend\dist: the window shows it from there
Push-Location (Join-Path $repo "frontend")
try {
  if (-not (Test-Path node_modules)) { Step "front end: npm ci" { npm ci } }
  Step "front end: build" { npm run build }
} finally { Pop-Location }

# the launcher, into build\, with where the repo is (the API and the app live there)
Push-Location $here
try {
  if (-not (Test-Path node_modules)) { Step "launcher: npm ci" { npm ci } }
  Step "launcher: build" { npm run build }
  $config = (@{ repo = $repo } | ConvertTo-Json -Compress) + "`n"
  [IO.File]::WriteAllText((Join-Path $here "build\config.json"), $config, (New-Object Text.UTF8Encoding $false))

  # the icon: drawn at 1024px as for the Mac (icon.js), then a Windows .ico of every size Windows shows (ico.js)
  $png = Join-Path $here "build\icon.png"
  $ico = Join-Path $here "build\FlipAssist.ico"
  Step "icon" { npx electron build/icon.js $png }
  Step "Windows icon" { npx electron build/ico.js $png $ico }

  # the app: Electron with the launcher inside (the same files as the Mac's, less the build scripts)
  Step "app" { npx electron-packager . FlipAssist --platform=win32 --arch=x64 --icon=build/FlipAssist.ico `
      --out=out --overwrite --quiet --app-version=0.1.0 --win32metadata.CompanyName=AlertFlip `
      --win32metadata.ProductName=FlipAssist --win32metadata.FileDescription=FlipAssist `
      '--ignore=^/(src|out|build\.sh|build\.ps1|windows-setup\.ps1|export-models\.sh|tsconfig\.json|build/FlipAssist\.iconset|build/FlipAssist\.ico|build/[^/]*\.test\.js)($|/)' }
} finally { Pop-Location }

# into %LOCALAPPDATA%\Programs\FlipAssist, where Windows keeps a person's own apps; an older build is replaced
$programs = Join-Path $env:LOCALAPPDATA "Programs"
$dest = Join-Path $programs "FlipAssist"
New-Item -ItemType Directory -Force -Path $programs | Out-Null
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
Copy-Item -Recurse (Join-Path $here "out\FlipAssist-win32-x64") $dest

# the shortcuts: one in the Start menu, one on the desktop
$exe = Join-Path $dest "FlipAssist.exe"
$shell = New-Object -ComObject WScript.Shell
foreach ($folder in @([Environment]::GetFolderPath("Programs"), [Environment]::GetFolderPath("Desktop"))) {
  $link = $shell.CreateShortcut((Join-Path $folder "FlipAssist.lnk"))
  $link.TargetPath = $exe
  $link.WorkingDirectory = $dest
  $link.IconLocation = "$exe,0"
  $link.Description = "FlipAssist"
  $link.Save()
}
Write-Host "Built $exe : open FlipAssist from the Start menu or the desktop"
