from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class AppConfig:
    port: int
    app_data_root: Path
    env_file: Path | None
    openai_api_key: str | None
    openrouter_api_key: str | None
    default_vision_base_url: str
    default_vision_model: str
    timezone: str


def load_config() -> AppConfig:
    env_file = os.getenv("MITOU_TIDY_ENV_FILE")
    env_path = Path(env_file) if env_file else None
    if env_path and env_path.exists():
        load_dotenv(env_path)
    elif Path(".env").exists():
        load_dotenv(".env")

    app_data_root = Path(
        os.getenv("MITOU_TIDY_APPDATA")
        or Path.home() / "AppData" / "Local" / "MitouLocalTidyHelper"
    )

    return AppConfig(
        port=int(os.getenv("MITOU_TIDY_PORT", "8765")),
        app_data_root=app_data_root,
        env_file=env_path,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        default_vision_base_url=os.getenv(
            "VISION_BASE_URL",
            os.getenv("LOCAL_VISION_BASE_URL", "http://127.0.0.1:8080/v1"),
        ),
        default_vision_model=os.getenv(
            "VISION_MODEL",
            os.getenv("LOCAL_VISION_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct"),
        ),
        timezone=os.getenv("MITOU_TIDY_TIMEZONE", "Asia/Tokyo"),
    )
