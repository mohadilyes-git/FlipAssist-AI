"""Photos: only a JPEG, PNG, HEIC or WebP reaches sips, known by its bytes,
and none with more pixels than a camera takes, or that takes too long."""

import shutil
import subprocess

import pytest

from flip import photos
from flip.photos import NotAPhoto, photo_jpeg, photo_kind
from tests.test_api import JPEG

STARTS = {".jpg": b"\xff\xd8\xff\xe0\x00\x10JFIF\x00", ".png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
          ".webp": b"RIFF\x24\x00\x00\x00WEBPVP8 ", ".heic": b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00"}


@pytest.mark.parametrize("kind", STARTS)
def test_a_photo_is_known_by_how_its_bytes_start(kind):
    assert photo_kind(STARTS[kind]) == kind


@pytest.mark.parametrize("start", [b"%PDF-1.4\n%\xe2\xe3", b"II*\x00\x08\x00\x00\x00", b"GIF89a\x01\x00\x01\x00",
                                   b"BM\x36\x00\x00\x00", b"\x00\x00\x00\x18ftypavif\x00\x00", b"", b"hello"])
def test_anything_else_isnt_a_photo(start):
    assert photo_kind(start) is None


def test_a_pdf_called_photo_jpg_never_reaches_sips(tmp_path, monkeypatch):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"%PDF-1.4\n" + b"0" * 100)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("sips ran"))
    with pytest.raises(NotAPhoto, match="JPEG, PNG, HEIC or WebP"):
        photo_jpeg(path)


@pytest.mark.skipif(not shutil.which("sips"), reason="sips is on Macs only")
def test_more_pixels_than_the_limit_is_refused_before_it_is_converted_with_what_to_do(tmp_path, monkeypatch):
    path = tmp_path / "tiny.jpg"
    path.write_bytes(JPEG)  # 2 x 2
    assert photo_jpeg(path)[:3] == b"\xff\xd8\xff"
    with pytest.raises(NotAPhoto, match="2 x 2 pixels"):
        photo_jpeg(path, max_pixels=3)
    # a 200-megapixel Samsung Ultra photo is a real photo: the message says what to do, not that it isn't one
    monkeypatch.setattr(photos, "sips", lambda path, *args, text=False: "pixelWidth: 16320\npixelHeight: 12240")
    with pytest.raises(NotAPhoto) as refused:
        photo_jpeg(path)
    assert refused.value.why == \
        "16,320 x 12,240 pixels (200 megapixels) is over the 60-megapixel limit: save a smaller copy and send that"
    # just over the limit reads as over it: rounded up, to a tenth
    monkeypatch.setattr(photos, "sips", lambda path, *args, text=False: "pixelWidth: 9504\npixelHeight: 6336")
    with pytest.raises(NotAPhoto, match=r"\(60\.3 megapixels\) is over the 60-megapixel limit"):
        photo_jpeg(path)


def test_a_photo_sips_cant_read_in_time_is_refused(tmp_path, monkeypatch):
    path = tmp_path / "slow.jpg"
    path.write_bytes(JPEG)
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/sips")

    def slow(command, **options):
        assert options["timeout"] == photos.SECONDS
        raise subprocess.TimeoutExpired(command, options["timeout"])
    monkeypatch.setattr(subprocess, "run", slow)
    with pytest.raises(NotAPhoto, match=f"took over {photos.SECONDS} seconds"):
        photo_jpeg(path)
