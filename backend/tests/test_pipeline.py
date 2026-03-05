from __future__ import annotations

from pathlib import Path

from PIL import Image

from tidy_helper.app.services.pipeline import apply_masks, humanize_bytes, is_quiet_hours


def test_quiet_hours_wrap_midnight():
    from datetime import datetime

    assert is_quiet_hours(datetime(2026, 3, 6, 23, 30), "23:00", "08:00") is True
    assert is_quiet_hours(datetime(2026, 3, 7, 7, 30), "23:00", "08:00") is True
    assert is_quiet_hours(datetime(2026, 3, 7, 14, 0), "23:00", "08:00") is False


def test_apply_masks_blacks_rectangle(tmp_path: Path):
    source = tmp_path / "source.png"
    Image.new("RGB", (100, 100), "#ffffff").save(source)
    destination = tmp_path / "masked.png"

    class Mask:
        enabled = True
        x = 0.1
        y = 0.2
        width = 0.2
        height = 0.3

    apply_masks(source, [Mask()], destination)
    with Image.open(destination) as image:
        assert image.getpixel((15, 25)) == (0, 0, 0)
        assert image.getpixel((90, 90)) == (255, 255, 255)


def test_humanize_bytes():
    assert humanize_bytes(1024) == "1.0 KB"
