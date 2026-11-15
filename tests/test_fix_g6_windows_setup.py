"""The Windows setup (launcher/windows-setup.ps1) and build (launcher/build.ps1), fixed after the 15 Nov review of the
Windows scripts. A Mac has no PowerShell, so these read each script for the step and where it is; the options the
setup gives curl.exe are run with this computer's own curl, against a small GitHub-like release on 127.0.0.1."""

import http.server
import re
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

LAUNCHER = Path(__file__).resolve().parent.parent / "launcher"


def code(script):
    """What PowerShell runs of a script: without its comments (a whole line, or after " # ")."""
    text = (LAUNCHER / script).read_text(encoding="utf-8")
    return "\n".join("" if line.lstrip().startswith("#") else line.split(" # ")[0] for line in text.splitlines())


SETUP = code("windows-setup.ps1")
BUILD = code("build.ps1")


# ── scripts-windows-2: a run after a failure fetched all four models again, each part from its first byte, with
# nothing on screen for minutes ──────────────────────────────────────────────────────────────────────────────────

def test_a_model_ollama_already_has_as_the_tested_version_isnt_fetched_again():
    ask = SETUP.index("& ollama show --modelfile $model 2>$null")
    assert '-match "sha256-$($tested[$model])"' in SETUP[ask:ask + 100]  # its FROM line names the file's SHA-256
    # asked with Continue: Windows PowerShell 5.1 stops at "not found" on stderr under Stop, even with 2>$null
    before = SETUP[:ask]
    assert before.rindex('$ErrorActionPreference = "Continue"') > before.rindex('$ErrorActionPreference = "Stop"')
    assert SETUP.index('$ErrorActionPreference = "Stop"', ask) < SETUP.index("SHA256SUMS")
    # before anything is downloaded or added, and then only the missing ones are, from the release or a -Models folder
    assert ask < SETUP.index("SHA256SUMS") and ask < SETUP.index("ollama create")
    assert "foreach ($model in $tested.Keys)" not in SETUP[ask:]
    assert SETUP.count("foreach ($model in $missing)") == 2


def curl_options():
    """What the setup gives curl.exe for each file of the release, with $file and $url as they're written there."""
    calls = [line.split("& curl.exe", 1)[1].split() for line in SETUP.splitlines() if "& curl.exe" in line]
    assert len(calls) == 1, calls
    return calls[0]


def test_each_file_comes_with_curl_which_shows_how_far_it_has_got_and_carries_on_when_it_stops():
    options = curl_options()
    assert ("-C", "-") in zip(options, options[1:])  # carries on from the bytes already there
    assert "--progress-bar" in options and "-fL" in options  # how far it's got; an HTTP error fails; redirects
    fetch = SETUP[SETUP.index("function Fetch"):]
    fetch = fetch[:fetch.index("\n}") + 2]
    # run again when it stops, a few times, then a plain message; with Continue, as curl's progress is on stderr
    assert re.search(r"foreach \(\$attempt in 1\.\.\d\)", fetch) and "if ($LASTEXITCODE -eq 0) { return }" in fetch
    assert '$ErrorActionPreference = "Continue"' in fetch and 'throw "Couldn' in fetch
    assert 'Fetch "$base/$name" $file' in SETUP
    # PowerShell's own download, which can't carry on and shows nothing with its progress bar off, only gets the list
    assert all("SHA256SUMS" in line for line in SETUP.splitlines() if "Invoke-WebRequest" in line)


class Release(http.server.BaseHTTPRequestHandler):
    """A GitHub-like release: /releases/download/<tag>/<name> sends curl on to the file, which comes in ranges, as
    GitHub's do. The first time a file is asked for, the connection drops after CUT bytes."""
    BODY = bytes(range(256)) * 2048  # 512 KiB
    CUT = 200_000
    asked = []  # (path, Range header), set for each test
    cut = set()

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.asked.append((self.path, self.headers.get("Range")))
        if self.path.startswith("/releases/download/"):
            self.send_response(302)
            self.send_header("Location", "/assets/" + self.path.rsplit("/", 1)[1])
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        start = int(re.match(r"bytes=(\d+)-", self.headers.get("Range") or "bytes=0-").group(1))
        if start >= len(self.BODY):  # nothing left to send
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{len(self.BODY)}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(206 if start else 200)
        if start:
            self.send_header("Content-Range", f"bytes {start}-{len(self.BODY) - 1}/{len(self.BODY)}")
        self.send_header("Content-Length", str(len(self.BODY) - start))
        self.end_headers()
        if self.path in self.cut:
            self.wfile.write(self.BODY[start:])
        else:
            self.cut.add(self.path)
            self.wfile.write(self.BODY[start:start + self.CUT])  # and the connection closes, short
            self.close_connection = True


@pytest.fixture
def release():
    """The release's address on 127.0.0.1, and what was asked of it."""
    class Fresh(Release):
        asked, cut = [], set()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fresh)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/releases/download/models-v1", Fresh.asked
    server.shutdown()
    server.server_close()


@pytest.mark.skipif(not shutil.which("curl"), reason="needs curl")
def test_with_those_options_a_dropped_download_carries_on_where_it_stopped(tmp_path, release):
    base, asked = release
    part = tmp_path / "flip-reader-5.gguf.part-a"
    said = {"$file": str(part), "$url": f"{base}/flip-reader-5.gguf.part-a"}
    command = ["curl"] + [said.get(option, option) for option in curl_options()]

    def run():
        return subprocess.run(command, capture_output=True, timeout=60).returncode

    assert run() != 0 and part.stat().st_size == Release.CUT  # the connection dropped: what came is kept
    assert run() == 0 and part.read_bytes() == Release.BODY  # the next try carries on from there...
    assert asked[-1] == ("/assets/flip-reader-5.gguf.part-a", f"bytes={Release.CUT}-")  # ...asking only for the rest
    assert run() == 0 and part.read_bytes() == Release.BODY  # and one that's all there is left as it is


# ── scripts-windows-4: each run made a new folder in %TEMP%, and only the end of a run deleted it, so a run that was
# stopped (the window closed, a restart) left up to 4 GB there that no later run looked at ───────────────────────

def test_the_download_folder_is_the_same_every_run_and_what_a_stopped_run_left_is_cleared_first():
    assert "NewGuid" not in SETUP
    assert '$work = Join-Path $env:TEMP "flipassist-models"' in SETUP
    cleared = SETUP.index("if (Test-Path -LiteralPath $work) { Remove-Item -Recurse -Force -LiteralPath $work }")
    assert SETUP.index("$work = Join-Path") < cleared < SETUP.index("New-Item -ItemType Directory -Path $work")


# ── scripts-windows-3: a full disk showed only after a long download, as .NET's own message ───────────────────────

def test_room_is_checked_before_anything_is_downloaded_and_covers_the_real_files():
    check = SETUP.index("AvailableFreeSpace")
    # after what a stopped run left is cleared (it would count against the room), before anything is downloaded
    assert SETUP.index("Remove-Item -Recurse -Force -LiteralPath $work }") < check < SETUP.index("SHA256SUMS")
    room = SETUP[SETUP.index("$store ="):check]
    assert "$env:OLLAMA_MODELS" in room and "$missing.Count" in room  # Ollama's folder, for each model it'll add
    # enough for the real files: a model is at most 2,489,894,016 bytes, and %TEMP% holds part-a (1,900 MiB, as
    # upload-models.sh splits them) beside the file it's joined into; a drive with both holds the joined file too
    model = float(re.search(r"([\d.]+)GB \* \(\$missing\.Count \+ 1\)", room).group(1)) * 2**30
    temp = float(re.search(r"\$tempDrive = ([\d.]+)GB;", room).group(1)) * 2**30
    assert model >= 2_489_894_016 and temp >= 2 * 1900 * 2**20
    assert "need about {0} GB free on {1}" in SETUP[check:]  # says how much, and where


# ── scripts-windows-5: no release there (a fork's clone, a mistyped -Repo or -Tag, none made yet) showed only .NET's
# "The remote server returned an error: (404) Not Found." ───────────────────────────────────────────────────────

def test_a_release_that_isnt_there_says_what_to_do():
    get = SETUP.index('Invoke-WebRequest -UseBasicParsing -Uri "$base/SHA256SUMS"')
    handler = SETUP[get:SETUP.index("$sums = @{}")]
    assert "[int]$_.Exception.Response.StatusCode -eq 404" in handler
    message = re.search(r'throw "([^"]+)"', handler).group(1)
    assert "github.com/$Repo" in message and "'$Tag'" in message
    assert all(re.search(rf"{flag}\b", message) for flag in ("-Repo", "-Tag", "-Models", "-NoModels"))
    # anything else (no internet, a DNS failure) isn't called a missing release: it goes on as it came
    assert re.search(r"\n\s*throw\s*\n", handler)


# ── scripts-windows-7: the build blamed an Ollama started in the app's folder, but FlipAssist starts it from your home
# folder (services.ts) and its shortcuts start in your home folder too, so quitting Ollama couldn't free the folder ──

def test_the_build_names_what_can_really_hold_the_app_folder_open():
    message = re.search(r'catch \{ throw "(Something still has[^"]*)" \}', BUILD).group(1)
    assert not re.search(r"Ollama|taskkill|tray", message)
    assert all(what in message for what in ("PowerShell", "Command Prompt", "File Explorer", "antivirus"))
