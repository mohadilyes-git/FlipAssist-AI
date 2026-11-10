# Sets FlipAssist up on a Windows PC, once (9 Nov 2026): its Python environment, its AI models in Ollama, then the
# app itself (build.ps1). Install these first, each with its normal Windows installer:
#   - Python 3.11 (python.org: tick "Add python.exe to PATH")
#   - Node.js 22 or newer (nodejs.org)
#   - Ollama for Windows (ollama.com), and open it once so it's running
#   - the Microsoft Visual C++ Redistributable (x64), if the PC doesn't have it (aka.ms/vs/17/release/vc_redist.x64.exe)
# If you have a .env (it holds your keys), put it in the repo folder; without one, FlipAssist makes it on first launch,
# and your own Claude API key goes in it. FlipAssist's own models come from the Mac: there, launcher/export-models.sh
# copies them to a folder; bring that folder to this PC and name it here. In PowerShell, from the repo folder:
#   powershell -ExecutionPolicy Bypass -File launcher\windows-setup.ps1 -Models D:\FlipAssist-models
# Without -Models it still works: Gemma 3 4B and code do those models' jobs, as on a Mac without them.
param([string]$Models = "")
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here
$env:PYTHONUTF8 = "1" # Python reads and writes text as UTF-8 here, as on a Mac (pound signs, emoji)

function Step([string]$what, [scriptblock]$run) {
  Write-Host "- $what"
  & $run
  if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" }
}
function Need([string]$program, [string]$from) {
  if (-not (Get-Command $program -ErrorAction SilentlyContinue)) {
    throw "$program isn't installed: get it from $from, then run this again"
  }
}

foreach ($synced in @($env:OneDrive, $env:OneDriveConsumer, $env:OneDriveCommercial)) {
  if ($synced -and $repo.StartsWith($synced, [StringComparison]::OrdinalIgnoreCase)) {
    Write-Warning "The repo is inside OneDrive ($synced): it would sync node_modules, .venv and the app (about 1 GB) and can break npm. Clone it somewhere OneDrive doesn't sync, such as C:\FlipAssist."
  }
}

Need node "nodejs.org"
Need npm "nodejs.org"
Need ollama "ollama.com"
# MiniLM (FlipAssist's search of your past messages) runs on onnxruntime, which needs Microsoft's C++ runtime
$system = Join-Path $env:SystemRoot "System32"
if (-not (Test-Path (Join-Path $system "msvcp140.dll")) -or -not (Test-Path (Join-Path $system "vcruntime140_1.dll"))) {
  throw "Install the Microsoft Visual C++ Redistributable (x64) from https://aka.ms/vs/17/release/vc_redist.x64.exe (or: winget install -e --id Microsoft.VCRedist.2015+.x64), then run this again"
}

# Python 3.11: through the py launcher that python.org installs, or python itself on the PATH. Each is only asked
# with Continue: Windows PowerShell 5.1 stops the whole script at a program's first error line when it's Stop, and
# "py -3.11" says so when it's another Python that's installed
$pyExe = $null
$pyArgs = @()
$ErrorActionPreference = "Continue"
if (Get-Command py -ErrorAction SilentlyContinue) {
  & py -3.11 --version *> $null
  if ($LASTEXITCODE -eq 0) { $pyExe = "py"; $pyArgs = @("-3.11") }
}
if (-not $pyExe -and (Get-Command python -ErrorAction SilentlyContinue)) {
  $version = & python -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
  if ("$version" -eq "3.11") { $pyExe = "python" }
}
$ErrorActionPreference = "Stop"
if (-not $pyExe) { throw "Python 3.11 isn't installed: get it from python.org (tick Add python.exe to PATH), then run this again" }

# the .env: your keys, which stay on this PC. Without one, FlipAssist makes it on first launch with this PC's own
# FLIP_API_KEY; your Claude key (ANTHROPIC_API_KEY) is yours to add to it
if (-not (Test-Path (Join-Path $repo ".env"))) {
  Write-Host "No .env yet: FlipAssist makes one on first launch. Add your own Claude API key to it to turn Claude on."
}

# the Python environment (.venv) and the libraries requirements.txt lists (on Windows, Pillow too: it converts photos)
$venvPython = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) { Step "Python environment (.venv)" { & $pyExe @pyArgs -m venv (Join-Path $repo ".venv") } }
Step "Python libraries (requirements.txt)" { & $venvPython -m pip install --disable-pip-version-check -r (Join-Path $repo "requirements.txt") }
Step "onnxruntime loads (MiniLM's engine)" { & $venvPython -c "import onnxruntime" }

# the AI models, in Ollama
try { Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5 | Out-Null }
catch { throw "Ollama isn't running: open Ollama from the Start menu, then run this again" }
Step "Gemma 3 4B (about 3.3 GB to download)" { ollama pull gemma3:4b }
if ($Models) {
  foreach ($model in @("flip-reader-5", "flip-wording-4b", "flip-kinds-1", "flip-style-1b")) {
    $modelfile = Join-Path (Join-Path $Models $model) "Modelfile"
    if (-not (Test-Path $modelfile)) { throw "$model isn't in $Models (no $modelfile): export it on the Mac with launcher/export-models.sh" }
    Step "$model (about 2.5 GB)" { ollama create $model -f $modelfile }
  }
} else {
  Write-Host "No -Models folder: FlipAssist's own models aren't added, so Gemma 3 4B and code do their jobs."
}

# the app itself
& (Join-Path $here "build.ps1")
