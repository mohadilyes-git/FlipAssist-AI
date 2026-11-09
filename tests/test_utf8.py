"""Every text file FlipAssist's code reads or writes says it's UTF-8 (9 Nov 2026, for Windows). A Mac reads text as
UTF-8 anyway, but Windows reads it in its older code page, where "£" and emoji fail. The launcher also starts the API
in UTF-8 mode there (PYTHONUTF8=1, launcher/src/parts.ts apiCommand): this keeps the code right without it."""

import re
from pathlib import Path

FLIP = Path(__file__).resolve().parent.parent / "flip"
# open(...) itself (not Image.open), read_text(...), write_text(...)
TEXT_CALL = re.compile(r"(?<![\w.])open\(|\.(?:read_text|write_text)\(")
BINARY = re.compile(r"""["'](?:[rwax]\+?b|b[rwax]?\+?|[rwax]b\+?)["']""")


def said_in(text, start):
    """What's between a call's brackets, from the one at start to its match, over lines too: write_text(json.dumps(x),
    encoding="utf-8") says all of json.dumps(x), encoding="utf-8"."""
    depth = 0
    for at in range(start, len(text)):
        depth += {"(": 1, ")": -1}.get(text[at], 0)
        if depth == 0:
            return text[start + 1:at]
    return text[start + 1:]


def text_calls_without_utf8(text):
    """Each text open, read_text or write_text that doesn't say encoding=, as its line number."""
    found = []
    for call in TEXT_CALL.finditer(text):
        said = said_in(text, call.end() - 1)
        if "encoding=" not in said and not BINARY.search(said.split(",", 2)[1] if said.count(",") else ""):
            found.append(text.count("\n", 0, call.start()) + 1)
    return found


def test_every_text_file_is_read_and_written_as_utf8():
    missing = [f"flip/{file.name}:{n}" for file in sorted(FLIP.glob("*.py"))
               for n in text_calls_without_utf8(file.read_text(encoding="utf-8"))]
    assert missing == []


def test_the_check_finds_a_text_file_read_without_utf8():  # the check above can fail
    assert text_calls_without_utf8('x = Path("a").read_text()\nopen(path, "w")') == [1, 2]
    assert text_calls_without_utf8('Path(p).write_text(json.dumps(x, indent=1) + "\\n", encoding="utf-8")') == []
    assert text_calls_without_utf8('open(path, "rb")\nopen(\n  path,\n  encoding="utf-8")') == []
    assert text_calls_without_utf8("Image.open(path)") == []
