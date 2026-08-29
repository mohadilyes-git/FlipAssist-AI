"""Photos for the AI. Every photo goes in as a JPEG no bigger than the model
needs: Gemma works at 896px and Claude charges by size, so bigger only costs
more. iPhone photos are HEIC, which neither model reads, so on a Mac they're
converted with the built-in sips tool.

Only photos reach sips: a file is a JPEG, PNG, HEIC or WebP by how its bytes
start, whatever it's called, and anything else (a PDF, a TIFF...) is refused,
as is one with more pixels than any camera photo, or one sips can't read in
SECONDS. sips reads whatever it's given, decoding all of it first."""

import base64
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

MAX_SIDE = 1024  # pixels on the longest side
MAX_PIXELS = 60_000_000  # a 48-megapixel iPhone photo fits; a 40,000 x 40,000 trick image doesn't
SECONDS = 20  # the longest sips gets for one photo
HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"hevm", b"hevs", b"mif1", b"msf1"}


class NotAPhoto(ValueError):
    """A file that can't go in as a photo, and why, in words."""

    def __init__(self, path, why):
        super().__init__(f"{Path(path).name}: {why}")
        self.why = why


def photo_kind(head):
    """What kind of photo some bytes are, by how they start: ".jpg", ".png",
    ".webp" or ".heic"; None for anything else."""
    if head[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    if head[4:8] == b"ftyp" and head[8:12] in HEIF_BRANDS:
        return ".heic"
    return None


def sips(path, *args, text=False):
    try:
        return subprocess.run(["sips", *args], capture_output=True, text=text, check=True, timeout=SECONDS).stdout
    except subprocess.TimeoutExpired:
        raise NotAPhoto(path, f"took over {SECONDS} seconds to read") from None


def photo_jpeg(path, max_side=MAX_SIDE, max_pixels=MAX_PIXELS):
    """The photo as JPEG bytes, shrunk (never enlarged) to max_side pixels."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"photo not found: {path}")
    with open(path, "rb") as f:
        kind = photo_kind(f.read(16))
    if kind is None:
        raise NotAPhoto(path, "send photos as JPEG, PNG, HEIC or WebP")
    if not shutil.which("sips"):
        # not a Mac: no converter, so only JPEGs can go in as they are
        if kind == ".jpg":
            return path.read_bytes()
        raise NotAPhoto(path, "save this photo as a JPEG first")
    size = dict(re.findall(r"pixel(Width|Height): (\d+)", sips(path, "-g", "pixelWidth", "-g", "pixelHeight",
                                                                 str(path), text=True)))
    if len(size) < 2:
        raise NotAPhoto(path, "can't be read as a photo")
    width, height = int(size["Width"]), int(size["Height"])
    if width * height > max_pixels:
        raise NotAPhoto(path, f"{width:,} x {height:,} pixels is more than a photo has "
                              f"(at most {max_pixels // 1_000_000} megapixels)")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "photo.jpg"
        resize = ["-Z", str(max_side)] if max(width, height) > max_side else []
        sips(path, "-s", "format", "jpeg", *resize, str(path), "--out", str(out))
        return out.read_bytes()


def photo_base64(path, max_side=MAX_SIDE):
    """The photo as base64 text, the way both models take images."""
    return base64.standard_b64encode(photo_jpeg(path, max_side)).decode("ascii")
