# Sets FlipAssist up on a Windows PC, once (9 Nov 2026): its Python environment, its AI models in Ollama, then the
# app itself (build.ps1). Install these first, each with its normal Windows installer:
#   - Python 3.11 (python.org: tick "Add python.exe to PATH")
#   - Node.js 22 or newer (nodejs.org)
#   - Ollama for Windows (ollama.com), and open it once so it's running
#   - the Microsoft Visual C++ Redistributable (x64), if the PC doesn't have it (aka.ms/vs/17/release/vc_redist.x64.exe)
# Clone the repo somewhere OneDrive doesn't sync (C:\FlipAssist, say). If you have a .env (it holds your keys), put it
# in the repo folder; without one, FlipAssist makes it on first launch, and your own Claude API key goes in it.
# FlipAssist's own four models are downloaded from the repo's GitHub release (models-v1, models/README.md), each
# checked against the version that was tested. In PowerShell, from the repo folder:
#   powershell -ExecutionPolicy Bypass -File launcher\windows-setup.ps1
# -Repo owner/name: the GitHub repo with the release, when this folder isn't a clone of it; -Tag: another release;
# -Models E:\FlipAssist-models: a folder made on a Mac with launcher/export-models.sh (on an ExFAT USB drive) instead
# of downloading; -NoModels: without them (Gemma 3 4B and code do their jobs, as on a Mac without them).
param([string]$Models = "", [string]$Repo = "", [string]$Tag = "models-v1", [switch]$NoModels)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here # the repo folder (not $repo: PowerShell's names ignore case, so that would be -Repo)
$env:PYTHONUTF8 = "1" # Python reads and writes text as UTF-8 here, as on a Mac (pound signs, emoji)
# GitHub only talks TLS 1.2 or later, which Windows PowerShell 5.1 doesn't always offer by itself; and without its
# progress bar it downloads big files many times faster
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
$ProgressPreference = "SilentlyContinue"

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
  if ($synced -and $root.StartsWith($synced, [StringComparison]::OrdinalIgnoreCase)) {
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
if (-not (Test-Path (Join-Path $root ".env"))) {
  Write-Host "No .env yet: FlipAssist makes one on first launch. Add your own Claude API key to it to turn Claude on."
}

# the Python environment (.venv) and the libraries requirements.txt lists (on Windows, Pillow too: it converts photos)
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) { Step "Python environment (.venv)" { & $pyExe @pyArgs -m venv (Join-Path $root ".venv") } }
Step "Python libraries (requirements.txt)" { & $venvPython -m pip install --disable-pip-version-check -r (Join-Path $root "requirements.txt") }
Step "onnxruntime loads (MiniLM's engine)" { & $venvPython -c "import onnxruntime" }

# the AI models, in Ollama
try { Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5 | Out-Null }
catch { throw "Ollama isn't running: open Ollama from the Start menu, then run this again" }
Step "Gemma 3 4B (about 3.3 GB to download)" { ollama pull gemma3:4b }

# the tested versions of FlipAssist's own models (MODELS.md, How to check a model file): any other file is refused
$tested = [ordered]@{
  "flip-reader-5"   = "b946131ba11fc159fdc1cf683dab0d3b9c4a64cb80dd9726b1b4208b8632bae1"
  "flip-wording-4b" = "f8ad98ddf4849746e3520afb9d1d38689fc3437dc66fbd201ef536f2b18d35e1"
  "flip-kinds-1"    = "29d5df4e97c69c85892feed8c8a7f9a52f3d1f1c05fe7b07f6102a9d2dee45d0"
  "flip-style-1b"   = "2e64f58682c449660927e25afaa4d7c029c298a19b9527bd2c22c305e316d694"
}
function Sha256([string]$file) { (Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash.ToLowerInvariant() }

if ($NoModels) {
  Write-Host "-NoModels: FlipAssist's own models aren't added, so Gemma 3 4B and code do their jobs."
} elseif ($Models) {
  # from a folder made on a Mac with launcher/export-models.sh
  foreach ($model in $tested.Keys) {
    $folder = Join-Path $Models $model
    $modelfile = Join-Path $folder "Modelfile"
    $gguf = Join-Path $folder "$model.gguf"
    if (-not (Test-Path $modelfile) -or -not (Test-Path $gguf)) { throw "$model isn't in ${Models}: export it on the Mac with launcher/export-models.sh" }
    if ((Sha256 $gguf) -ne $tested[$model]) { throw "$gguf isn't the version of $model that was tested" }
    Step "$model (about 2.5 GB)" { ollama create $model -f $modelfile }
  }
} else {
  # from the repo's GitHub release (models/README.md): every part checked as it comes, then each whole file
  if (-not $Repo) {
    $origin = ""
    if (Get-Command git -ErrorAction SilentlyContinue) {
      $ErrorActionPreference = "Continue" # git's "not a git repository" (a ZIP download) mustn't stop the script
      $origin = "$(& git -C $root remote get-url origin 2>$null)"
      $ErrorActionPreference = "Stop"
    }
    if ($origin -match 'github\.com[:/]([^/]+/[^/]+?)(\.git)?$') { $Repo = $Matches[1] }
    else { throw "Say which GitHub repo has the models: -Repo owner/name (or -NoModels to go without them)" }
  }
  $base = "https://github.com/$Repo/releases/download/$Tag"
  $work = Join-Path $env:TEMP ("flipassist-models-" + [guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Path $work | Out-Null
  try {
    $sumsFile = Join-Path $work "SHA256SUMS"
    Invoke-WebRequest -UseBasicParsing -Uri "$base/SHA256SUMS" -OutFile $sumsFile
    $sums = @{}
    foreach ($line in Get-Content $sumsFile) { if ($line -match '^([0-9a-f]{64}) [ *](.+)$') { $sums[$Matches[2]] = $Matches[1] } }
    foreach ($model in $tested.Keys) {
      $parts = @($sums.Keys | Where-Object { $_ -like "$model.gguf.part-*" } | Sort-Object)
      if ($parts.Count -eq 0) { throw "$model isn't on the release at $base" }
      $gguf = Join-Path $work "$model.gguf"
      $joined = [IO.File]::Create($gguf)
      try {
        foreach ($name in $parts + @("$model.Modelfile")) {
          $file = Join-Path $work $name
          Write-Host "- downloading $name"
          Invoke-WebRequest -UseBasicParsing -Uri "$base/$name" -OutFile $file
          if ((Sha256 $file) -ne $sums[$name]) { throw "$name didn't download right: run this again" }
          if ($name -like "*.gguf.part-*") {
            $in = [IO.File]::OpenRead($file)
            try { $in.CopyTo($joined) } finally { $in.Close() }
            Remove-Item -LiteralPath $file
          }
        }
      } finally { $joined.Close() }
      if ((Sha256 $gguf) -ne $tested[$model]) { throw "$model on the release isn't the version that was tested" }
      Step "$model (adding to Ollama)" { ollama create $model -f (Join-Path $work "$model.Modelfile") }
      Remove-Item -LiteralPath $gguf
    }
  } finally { Remove-Item -Recurse -Force -LiteralPath $work -ErrorAction SilentlyContinue }
}

# the app itself
& (Join-Path $here "build.ps1")
