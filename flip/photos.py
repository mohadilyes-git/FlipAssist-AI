"""Photos for the AI. Every photo goes in as a JPEG no bigger than the model
needs: Gemma works at 896px and Claude charges by size, so bigger only costs
more. iPhone photos are HEIC, which neither model reads, so they're converted:
on a Mac with its built-in sips tool, on Windows (9 Nov) with Pillow, which
reads HEIC with pillow-heif (requirements.txt installs both on Windows only).

Only photos reach the converter: a file is a JPEG, PNG, HEIC or WebP by how its
bytes start, whatever it's called, and anything else (a PDF, a TIFF...) is
refused, as is one over MAX_PIXELS (with what to do: send a smaller copy), or
one sips can't read in SECONDS. sips reads whatever it's given, decoding all of
it first; Pillow reads the size from the file's header before decoding any of it."""

import base64
import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

MAX_SIDE = 1024  # pixels on the longest side
# a 48-megapixel iPhone photo fits; a 40,000 x 40,000 trick image doesn't, and nor does a 200-megapixel
# photo from a Samsung Ultra (sips decodes all of it first): that one goes in as a smaller copy
MAX_PIXELS = 60_000_000
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


def megapixels(pixels):
    """Megapixels as a size over the limit reads: rounded up, to a tenth
    under 100 ("60.2", not "60") and whole from there ("1,600")."""
    tenths = -(-pixels // 100_000)
    return f"{-(-tenths // 10):,}" if tenths >= 1000 else f"{tenths / 10:g}"


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
        image = pillow()
        if image is not None:  # Windows (9 Nov): Pillow does what sips does on a Mac
            return pillow_jpeg(path, kind, image, max_side, max_pixels)
        # no converter at all, so only JPEGs can go in as they are
        if kind == ".jpg":
            return path.read_bytes()
        raise NotAPhoto(path, "save this photo as a JPEG first")
    size = dict(re.findall(r"pixel(Width|Height): (\d+)", sips(path, "-g", "pixelWidth", "-g", "pixelHeight",
                                                                 str(path), text=True)))
    if len(size) < 2:
        raise NotAPhoto(path, "can't be read as a photo")
    width, height = int(size["Width"]), int(size["Height"])
    check_size(path, width, height, max_pixels)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "photo.jpg"
        resize = ["-Z", str(max_side)] if max(width, height) > max_side else []
        sips(path, "-s", "format", "jpeg", *resize, str(path), "--out", str(out))
        return out.read_bytes()


def check_size(path, width, height, max_pixels=MAX_PIXELS):
    """Refuse a photo with more pixels than max_pixels, saying what to do: send a smaller copy."""
    if width * height > max_pixels:
        raise NotAPhoto(path, f"{width:,} x {height:,} pixels ({megapixels(width * height)} megapixels) is over the "
                              f"{max_pixels // 1_000_000}-megapixel limit: save a smaller copy and send that")


def pillow():
    """Pillow's Image, reading HEIC too when pillow-heif is installed; None when Pillow isn't (a Mac has sips)."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass  # HEIC can't be read: pillow_jpeg asks for a JPEG instead
    return Image


def pillow_jpeg(path, kind, image, max_side=MAX_SIDE, max_pixels=MAX_PIXELS):
    """What sips does on a Mac, done with Pillow (image: its Image module): the photo the right way up, as JPEG bytes,
    shrunk (never enlarged) to max_side pixels, with see-through parts (a PNG screenshot) on white. The size is read
    from the header and checked before any of the photo is decoded."""
    from PIL import ImageOps, UnidentifiedImageError
    try:
        with image.open(path) as photo:
            check_size(path, *photo.size, max_pixels)
            upright = ImageOps.exif_transpose(photo)
            if upright.mode in ("RGBA", "LA", "PA") or (upright.mode == "P" and "transparency" in upright.info):
                rgba = upright.convert("RGBA")
                upright = image.new("RGB", rgba.size, "white")
                upright.paste(rgba, mask=rgba.getchannel("A"))
            else:
                upright = upright.convert("RGB")
    except NotAPhoto:
        raise
    except UnidentifiedImageError:
        # a HEIC with no pillow-heif to read it, or bytes that only start like a photo
        raise NotAPhoto(path, "save this photo as a JPEG first" if kind == ".heic" else "can't be read as a photo") from None
    except (OSError, ValueError, image.DecompressionBombError):
        raise NotAPhoto(path, "can't be read as a photo") from None
    upright.thumbnail((max_side, max_side))  # never enlarges
    out = io.BytesIO()
    upright.save(out, "JPEG", quality=85)
    return out.getvalue()


def photo_base64(path, max_side=MAX_SIDE):
    """The photo as base64 text, the way both models take images."""
    return base64.standard_b64encode(photo_jpeg(path, max_side)).decode("ascii")
