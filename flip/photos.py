"""Photos for the AI. Every photo goes in as a JPEG no bigger than the model
needs: Gemma works at 896px and Claude charges by size, so bigger only costs
more. iPhone photos are HEIC, which neither model reads, so on a Mac they're
converted with the built-in sips tool."""

import base64
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

MAX_SIDE = 1024  # pixels on the longest side


def photo_jpeg(path, max_side=MAX_SIDE):
    """The photo as JPEG bytes, shrunk (never enlarged) to max_side pixels."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"photo not found: {path}")
    if not shutil.which("sips"):
        # not a Mac: no converter, so only JPEGs can go in as they are
        if path.suffix.lower() in (".jpg", ".jpeg"):
            return path.read_bytes()
        raise ValueError(f"{path.name}: save this photo as a JPEG first")
    size = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
                          capture_output=True, text=True, check=True).stdout
    longest = max(int(n) for n in re.findall(r"pixel(?:Width|Height): (\d+)", size))
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "photo.jpg"
        resize = ["-Z", str(max_side)] if longest > max_side else []
        subprocess.run(["sips", "-s", "format", "jpeg", *resize, str(path), "--out", str(out)],
                       capture_output=True, check=True)
        return out.read_bytes()


def photo_base64(path, max_side=MAX_SIDE):
    """The photo as base64 text, the way both models take images."""
    return base64.standard_b64encode(photo_jpeg(path, max_side)).decode("ascii")
