# Sets FlipAssist up on a Windows PC, once (9 Nov 2026): its Python environment, its AI models in Ollama, then the
# app itself (build.ps1). Install these first, each with its normal Windows installer:
#   - Python 3.11 (python.org: tick "Add python.exe to PATH")
#   - Node.js 22 or newer (nodejs.org)
#   - Ollama for Windows (ollama.com), and open it once so it's running
# and put the repo's .env in the repo folder: copy yours from the Mac (it holds your keys), or fill in .env.example
# and save it as .env. FlipAssist's own models come from the Mac: there, launcher/export-models.sh copies them to a
# folder; bring that folder to this PC and name it here. In PowerShell, from the repo folder:
#   powershell -ExecutionPolicy Bypass -File launcher\windows-setup.ps1 -Models D:\FlipAssist-models
# Without -Models it still works: Gemma 3 4B and code do those models' jobs, as on a Mac without them.
param([string]$Models = "")
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here
$env:PYTHONUTF8 = "1" # Python reads and writes text as UTF-8 here, as on a Mac ("£", emoji)

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

Need node "nodejs.org"
Need npm "nodejs.org"
Need ollama "ollama.com"

# Python 3.11: through the py launcher that python.org installs, or python itself on the PATH
$pyExe = $null
$pyArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
  & py -3.11 --version *> $null
  if ($LASTEXITCODE -eq 0) { $pyExe = "py"; $pyArgs = @("-3.11") }
}
if (-not $pyExe -and (Get-Command python -ErrorAction SilentlyContinue)) {
  $version = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
  if ($version -eq "3.11") { $pyExe = "python" }
}
if (-not $pyExe) { throw "Python 3.11 isn't installed: get it from python.org (tick Add python.exe to PATH), then run this again" }

# the .env: your keys, which stay on this PC
if (-not (Test-Path (Join-Path $repo ".env"))) {
  throw "There's no .env in $repo yet: copy yours from the Mac, or fill in .env.example and save it as .env. Then run this again."
}

# the Python environment (.venv) and the libraries requirements.txt lists (on Windows, Pillow too: it converts photos)
$venvPython = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) { Step "Python environment (.venv)" { & $pyExe @pyArgs -m venv (Join-Path $repo ".venv") } }
Step "Python libraries (requirements.txt)" { & $venvPython -m pip install --disable-pip-version-check -r (Join-Path $repo "requirements.txt") }

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
