from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from tidy_helper.app.config import AppConfig
from tidy_helper.app.main import create_app


def _draw_shadow(draw: ImageDraw.ImageDraw, bounds: tuple[int, int, int, int], radius: int = 24) -> None:
    x0, y0, x1, y1 = bounds
    draw.rounded_rectangle((x0 + 8, y0 + 10, x1 + 8, y1 + 10), radius=radius, fill=(0, 0, 0, 36))


def _draw_notebook(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    *,
    cover: str,
    page: str = "#f8f5eb",
    accent: str = "#4b5563",
) -> None:
    _draw_shadow(draw, bounds, radius=18)
    draw.rounded_rectangle(bounds, radius=18, fill=cover)
    x0, y0, x1, y1 = bounds
    page_bounds = (x0 + 16, y0 + 20, x1 - 18, y1 - 20)
    draw.rounded_rectangle(page_bounds, radius=10, fill=page)
    for line_y in range(y0 + 46, y1 - 24, 22):
        draw.line((x0 + 26, line_y, x1 - 28, line_y), fill="#d6d3c7", width=2)
    draw.rectangle((x0 + 14, y0 + 12, x0 + 22, y1 - 12), fill=accent)


def _draw_keyboard(draw: ImageDraw.ImageDraw, bounds: tuple[int, int, int, int]) -> None:
    _draw_shadow(draw, bounds, radius=18)
    draw.rounded_rectangle(bounds, radius=18, fill="#d7d8de")
    x0, y0, x1, y1 = bounds
    key_w = 24
    key_h = 18
    gap = 7
    start_x = x0 + 18
    start_y = y0 + 16
    rows = [11, 11, 10, 9]
    for row_index, count in enumerate(rows):
        for column in range(count):
            left = start_x + column * (key_w + gap) + row_index * 4
            top = start_y + row_index * (key_h + gap)
            draw.rounded_rectangle(
                (left, top, left + key_w, top + key_h),
                radius=5,
                fill="#f4f5f8",
                outline="#b9bcc6",
            )
    draw.rounded_rectangle((x0 + 82, y1 - 30, x1 - 82, y1 - 12), radius=8, fill="#f4f5f8")


def _draw_mug(draw: ImageDraw.ImageDraw, center: tuple[int, int], *, body: str, drink: str) -> None:
    cx, cy = center
    _draw_shadow(draw, (cx - 42, cy - 42, cx + 42, cy + 42), radius=40)
    draw.ellipse((cx - 38, cy - 38, cx + 38, cy + 38), fill=body)
    draw.ellipse((cx - 28, cy - 28, cx + 28, cy + 28), fill=drink)
    draw.ellipse((cx + 28, cy - 12, cx + 48, cy + 12), outline=body, width=8)


def _draw_phone(draw: ImageDraw.ImageDraw, bounds: tuple[int, int, int, int], *, angle: int = 0) -> None:
    _draw_shadow(draw, bounds, radius=18)
    draw.rounded_rectangle(bounds, radius=18, fill="#202630")
    x0, y0, x1, y1 = bounds
    draw.rounded_rectangle((x0 + 8, y0 + 8, x1 - 8, y1 - 8), radius=12, fill="#111827")
    draw.ellipse((x0 + 28, y0 + 10, x0 + 36, y0 + 18), fill="#3b4452")
    if angle:
        draw.line((x0 + 12, y1 - 20, x1 - 12, y0 + 20), fill=(255, 255, 255, 28), width=3)


def _draw_sticky(draw: ImageDraw.ImageDraw, bounds: tuple[int, int, int, int], *, color: str, tilt: bool = False) -> None:
    _draw_shadow(draw, bounds, radius=8)
    x0, y0, x1, y1 = bounds
    draw.rectangle(bounds, fill=color)
    fold = 14
    draw.polygon(((x1 - fold, y0), (x1, y0), (x1, y0 + fold)), fill="#ffffff55")
    if tilt:
        draw.line((x0 + 12, y0 + 16, x1 - 14, y1 - 18), fill="#a16207", width=3)
    else:
        draw.line((x0 + 10, y0 + 18, x1 - 10, y0 + 18), fill="#a16207", width=3)
        draw.line((x0 + 10, y0 + 34, x1 - 18, y0 + 34), fill="#a16207", width=3)


def _draw_pen(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], *, body: str) -> None:
    draw.line((start, end), fill=body, width=9)
    draw.line((end, (end[0] + 10, end[1] - 2)), fill="#e5e7eb", width=4)


def _draw_cable(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], *, color: str = "#111827") -> None:
    draw.line(points, fill=color, width=8, joint="curve")
    end_x, end_y = points[-1]
    draw.ellipse((end_x - 6, end_y - 6, end_x + 6, end_y + 6), fill=color)


def _render_desk_scene(directory: Path, *, index: int, accent: str, mug_color: str, phone_offset: int) -> None:
    image = Image.new("RGBA", (960, 720), "#b88350")
    draw = ImageDraw.Draw(image, "RGBA")

    for stripe in range(0, 960, 54):
        draw.rectangle((stripe, 0, stripe + 28, 720), fill=(117, 73, 38, 38))
    draw.rectangle((0, 0, 960, 26), fill=(86, 52, 31, 90))
    draw.rectangle((0, 694, 960, 720), fill=(86, 52, 31, 90))

    desk_mat = (116, 72, 844, 642)
    _draw_shadow(draw, desk_mat, radius=32)
    draw.rounded_rectangle(desk_mat, radius=32, fill="#355f58")

    _draw_shadow(draw, (318, 92, 662, 274), radius=26)
    draw.rounded_rectangle((318, 92, 662, 274), radius=26, fill="#2f3541")
    draw.rounded_rectangle((340, 112, 640, 252), radius=18, fill="#9fb7d4")
    draw.rounded_rectangle((470, 254, 510, 286), radius=8, fill="#404758")

    _draw_keyboard(draw, (336, 300, 644, 414))
    _draw_notebook(draw, (170, 174, 356, 432), cover=accent)
    _draw_phone(draw, (704 + phone_offset, 188, 770 + phone_offset, 326), angle=index % 2)
    _draw_mug(draw, (740, 120), body=mug_color, drink="#6b4226")

    draw.rounded_rectangle((650, 384, 814, 486), radius=14, fill="#efe8d8")
    draw.line((670, 408, 792, 408), fill="#c9c2b2", width=3)
    draw.line((670, 432, 780, 432), fill="#c9c2b2", width=3)
    draw.line((670, 456, 788, 456), fill="#c9c2b2", width=3)

    _draw_sticky(draw, (194, 468, 262, 536), color="#fde68a")
    _draw_sticky(draw, (272, 486, 340, 554), color="#fca5a5", tilt=True)
    _draw_pen(draw, (420, 468), (538, 512), body="#f97316")
    _draw_pen(draw, (566, 502), (674, 546), body="#2563eb")
    _draw_cable(draw, [(676, 260), (694, 302), (734, 340), (770, 418), (816, 534)])

    draw.rounded_rectangle((148, 564, 286, 614), radius=14, fill="#2a3038")
    draw.rounded_rectangle((158, 574, 208, 604), radius=8, fill="#525f6f")
    draw.rounded_rectangle((220, 574, 276, 604), radius=8, fill="#4a5565")

    if index == 2:
        draw.rounded_rectangle((640, 514, 808, 598), radius=14, fill="#e5ddce")
        draw.line((662, 538, 786, 538), fill="#c3baa8", width=3)
        draw.line((662, 560, 776, 560), fill="#c3baa8", width=3)
        draw.line((662, 582, 784, 582), fill="#c3baa8", width=3)
        draw.rounded_rectangle((384, 504, 460, 558), radius=14, fill="#d4ecff")
        draw.rounded_rectangle((468, 522, 542, 576), radius=14, fill="#fecaca")
    else:
        draw.rounded_rectangle((386, 516, 540, 592), radius=16, fill="#d1fae5")
        draw.ellipse((552, 518, 618, 584), fill="#86efac")
        draw.ellipse((568, 534, 602, 568), fill="#bbf7d0")

    draw.text((170, 92), f"desk scene {index}", fill="#f9fafb")
    image.convert("RGB").save(directory / f"scene-{index}.png")


def make_fixture_images(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    _render_desk_scene(directory, index=1, accent="#2563eb", mug_color="#f8fafc", phone_offset=0)
    _render_desk_scene(directory, index=2, accent="#7c3aed", mug_color="#fcd34d", phone_offset=-24)


@pytest.fixture()
def client(tmp_path: Path):
    app_data = tmp_path / "appdata"
    image_dir = tmp_path / "mock_images"
    make_fixture_images(image_dir)

    config = AppConfig(
        port=8765,
        app_data_root=app_data,
        env_file=None,
        openai_api_key=None,
        openrouter_api_key=None,
        default_vision_base_url="mock://local-vlm",
        default_vision_model="deterministic-mock",
        timezone="Asia/Tokyo",
    )
    app = create_app(config)
    with TestClient(app) as test_client:
        yield test_client, image_dir, app_data
