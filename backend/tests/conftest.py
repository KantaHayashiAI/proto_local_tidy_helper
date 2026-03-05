from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from tidy_helper.app.config import AppConfig
from tidy_helper.app.main import create_app


def make_fixture_images(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for index, color in enumerate(("#365a4e", "#6f4d2a"), start=1):
        image = Image.new("RGB", (960, 720), color)
        draw = ImageDraw.Draw(image)
        draw.rectangle((80, 100, 360, 360), fill="#d9e9df")
        draw.rectangle((410, 210, 710, 460), fill="#efb75e")
        draw.text((120, 420), f"scene-{index}", fill="#0d1317")
        image.save(directory / f"scene-{index}.png")


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
        default_openai_model="gpt-4.1-mini",
        default_openrouter_model="qwen/qwen3.5-397b-a17b",
        default_local_base_url="mock://local-vlm",
        default_local_model="deterministic-mock",
        timezone="Asia/Tokyo",
    )
    app = create_app(config)
    with TestClient(app) as test_client:
        yield test_client, image_dir, app_data
