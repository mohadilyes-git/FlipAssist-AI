"""Photos on Windows (9 Nov 2026), where there's no sips: Pillow converts them as sips does on a Mac. They run where
Pillow is installed (requirements.txt installs it on Windows only), and are skipped on a Mac without it."""

import importlib.util
import io

import pytest

from flip import photos
from flip.photos import NotAPhoto, photo_jpeg

pytestmark = pytest.mark.skipif(importlib.util.find_spec("PIL") is None, reason="Pillow converts photos on Windows")


@pytest.fixture
def windows(monkeypatch):
    """A computer with no sips, as Windows is."""
    monkeypatch.setattr(photos.shutil, "which", lambda name: None)
    from PIL import Image
    return Image


def save(Image, path, size, fmt, mode="RGB", colour=(200, 30, 30), **options):
    Image.new(mode, size, colour).save(path, fmt, **options)
    return path


def jpeg_size(data):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as out:
        assert out.format == "JPEG"
        return out.size


def test_a_big_png_goes_in_as_a_jpeg_1024_pixels_long(windows, tmp_path):
    data = photo_jpeg(save(windows, tmp_path / "shot.png", (3000, 2000), "PNG"))
    assert jpeg_size(data) == (1024, 683)


def test_a_small_webp_is_converted_but_never_enlarged(windows, tmp_path):
    assert jpeg_size(photo_jpeg(save(windows, tmp_path / "small.webp", (300, 200), "WEBP"))) == (300, 200)


def test_a_big_jpeg_is_shrunk_too_as_on_a_mac(windows, tmp_path):
    assert jpeg_size(photo_jpeg(save(windows, tmp_path / "big.jpg", (4032, 3024), "JPEG"))) == (1024, 768)


def test_a_photo_taken_sideways_comes_out_the_right_way_up(windows, tmp_path):
    exif = windows.Exif()
    exif[0x0112] = 6  # orientation: turned 90 degrees
    path = save(windows, tmp_path / "sideways.jpg", (200, 100), "JPEG", exif=exif.tobytes())
    assert jpeg_size(photo_jpeg(path)) == (100, 200)


def test_see_through_parts_of_a_png_come_out_white_not_black(windows, tmp_path):
    from PIL import Image
    path = save(windows, tmp_path / "clear.png", (40, 40), "PNG", mode="RGBA", colour=(0, 0, 0, 0))
    with Image.open(io.BytesIO(photo_jpeg(path))) as out:
        assert min(out.convert("RGB").getpixel((20, 20))) > 240


def test_one_over_the_pixel_limit_is_refused_with_what_to_do(windows, tmp_path):
    path = save(windows, tmp_path / "huge.png", (2000, 1000), "PNG")
    with pytest.raises(NotAPhoto, match="2,000 x 1,000 pixels .* over the 1-megapixel limit: save a smaller copy"):
        photo_jpeg(path, max_pixels=1_000_000)


def test_bytes_that_only_start_like_a_photo_are_refused(windows, tmp_path):
    path = tmp_path / "fake.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"not a photo" * 20)
    with pytest.raises(NotAPhoto, match="can't be read as a photo"):
        photo_jpeg(path)


def test_a_heic_photo_is_read_with_pillow_heif(windows, tmp_path):
    pillow_heif = pytest.importorskip("pillow_heif")
    path = tmp_path / "iphone.heic"
    try:
        pillow_heif.from_pillow(windows.new("RGB", (2048, 1536), (10, 120, 200))).save(path, quality=80)
    except Exception as e:  # noqa: BLE001 - a pillow-heif built without a HEIC encoder can still read them
        pytest.skip(f"this pillow-heif can't write HEIC: {e}")
    assert jpeg_size(photo_jpeg(path)) == (1024, 768)


def test_a_heic_with_no_pillow_heif_asks_for_a_jpeg(tmp_path):
    from PIL import Image, UnidentifiedImageError

    class NoHeic:  # Pillow without pillow-heif: it can't identify a HEIC
        DecompressionBombError = Image.DecompressionBombError

        @staticmethod
        def open(path):
            raise UnidentifiedImageError(path)

    path = tmp_path / "iphone.heic"
    path.write_bytes(b"\x00\x00\x00\x18ftypheic" + b"\x00" * 16)
    with pytest.raises(NotAPhoto, match="save this photo as a JPEG first"):
        photos.pillow_jpeg(path, ".heic", NoHeic)


def png_header(width, height):
    """A PNG that's only its header: enough for its size to be read, with no pixels to decode."""
    import struct
    import zlib

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IEND", b"")


def test_a_200_megapixel_photo_is_told_its_size_and_what_to_do(windows, tmp_path):
    # review, 9 Nov: Pillow's own guard refused it as it opened ("can't be read") before the size was checked
    path = tmp_path / "ultra.png"
    path.write_bytes(png_header(16320, 12240))
    with pytest.raises(NotAPhoto, match="16,320 x 12,240 pixels .* over the 60-megapixel limit: save a smaller copy"):
        photo_jpeg(path)


def test_a_photo_with_a_broken_exif_block_still_goes_in(windows, tmp_path):
    path = tmp_path / "odd.jpg"
    windows.new("RGB", (50, 40), (90, 90, 90)).save(path, "JPEG", exif=b"Exif\x00\x00not a tiff block")
    assert jpeg_size(photo_jpeg(path)) == (50, 40)


def test_a_cut_off_heic_is_refused_as_unreadable_not_a_crash(windows, tmp_path):
    pillow_heif = pytest.importorskip("pillow_heif")
    whole = tmp_path / "whole.heic"
    try:
        pillow_heif.from_pillow(windows.new("RGB", (640, 480), (10, 120, 200))).save(whole, quality=80)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"this pillow-heif can't write HEIC: {e}")
    cut = tmp_path / "cut.heic"
    cut.write_bytes(whole.read_bytes()[: whole.stat().st_size // 2])
    with pytest.raises(NotAPhoto, match="can't be read as a photo"):
        photo_jpeg(cut)
