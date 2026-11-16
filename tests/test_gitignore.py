"""Private data must never reach GitHub: .gitignore has to cover every place
the app keeps it."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MUST_IGNORE = ["testset/private/", "private/", "chroma/", ".chroma/", "*.sqlite3", "logs/", ".env*", ".venv/"]
PRIVATE_FILES = ["testset/private/items.json", "private/audit.sqlite3", "private/photos/front.jpg",
                 "chroma/chroma.sqlite3", "logs/run.log", ".env", ".env.local"]


def test_gitignore_lists_every_private_place():
    lines = {line.strip() for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()}
    assert [pattern for pattern in MUST_IGNORE if pattern not in lines] == []
    assert "!.env.example" in lines  # the example file, with no real keys, is uploaded


@pytest.mark.skipif(not shutil.which("git") or not (ROOT / ".git").exists(), reason="needs the git repo")
def test_git_really_ignores_them():
    def ignored(path):
        return subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=ROOT).returncode == 0
    assert [path for path in PRIVATE_FILES if not ignored(path)] == []
    assert not ignored(".env.example")


def test_the_example_env_leaves_the_claude_key_empty():
    """Any value in ANTHROPIC_API_KEY counts as a key and turns Claude on, so .env.example's must stay empty: a copy
    of it with a placeholder would ask Claude with a key that can only fail."""
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    assert "ANTHROPIC_API_KEY=" in lines


def test_a_copy_of_the_example_env_asks_the_free_uk_prices(monkeypatch):
    """.env.example leaves PRICES_URL, PRICES_KEY and FLIP_PUBLIC_PRICES empty, so a copy of it gets the free UK prices:
    a placeholder key would have nowhere to go, and turn them off."""
    from flip import prices
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    assert {"FLIP_PUBLIC_PRICES=", "PRICES_URL=", "PRICES_KEY="} <= set(lines)
    for line in lines:  # as flip.draft.load_env reads it
        if "=" in line and not line.lstrip().startswith("#"):
            name, value = line.split("=", 1)
            monkeypatch.setenv(name.strip(), value.strip().strip("\"'"))
    assert prices.mode() == "public"
