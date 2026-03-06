from __future__ import annotations

from pathlib import Path

from PIL import Image
from sqlalchemy import select

from tidy_helper.app.database import create_session_factory, migrate_legacy_schema, session_scope
from tidy_helper.app.models import Base, Observation, Task
from tidy_helper.app.services.pipeline import (
    apply_masks,
    get_active_tasks,
    humanize_bytes,
    is_quiet_hours,
)


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


def test_get_active_tasks_returns_only_active_tasks(tmp_path: Path):
    session_factory = create_session_factory(tmp_path / "test.db")
    Base.metadata.create_all(session_factory.kw["bind"])

    with session_scope(session_factory) as session:
        observation = Observation(
            source="mock",
            image_path="image.png",
            width=100,
            height=100,
        )
        session.add(observation)
        session.flush()
        session.add(
            Task(
                observation_id=observation.id,
                title="Clear bottles",
                instruction="Remove bottles from the desk",
                reason="Desk is cluttered",
                priority=5,
                confidence=0.9,
                estimated_minutes=3,
                expected_visual_change="Bottles disappear",
                status="active",
            )
        )
        session.add(
            Task(
                observation_id=observation.id,
                title="Archive papers",
                instruction="Put papers into the drawer",
                reason="Desk is cluttered",
                priority=3,
                confidence=0.7,
                estimated_minutes=5,
                expected_visual_change="Loose papers disappear",
                status="done",
            )
        )

    with session_scope(session_factory) as session:
        active_tasks = get_active_tasks(session)
        assert [task.title for task in active_tasks] == ["Clear bottles"]


def test_migrate_legacy_schema_removes_snoozed_until_column(tmp_path: Path):
    session_factory = create_session_factory(tmp_path / "legacy.db")
    engine = session_factory.kw["bind"]

    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                observation_id INTEGER NOT NULL,
                title VARCHAR(255) NOT NULL,
                instruction TEXT NOT NULL,
                reason TEXT NOT NULL,
                priority INTEGER NOT NULL,
                confidence FLOAT NOT NULL,
                estimated_minutes INTEGER NOT NULL,
                expected_visual_change TEXT NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                snoozed_until DATETIME,
                created_at DATETIME NOT NULL,
                completed_at DATETIME,
                last_evaluated_at DATETIME
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO tasks (
                observation_id,
                title,
                instruction,
                reason,
                priority,
                confidence,
                estimated_minutes,
                expected_visual_change,
                status,
                snoozed_until,
                created_at
            ) VALUES (
                1,
                'Clear bottles',
                'Remove bottles from the desk',
                'Desk is cluttered',
                5,
                0.9,
                3,
                'Bottles disappear',
                'active',
                '2026-03-07 12:00:00',
                '2026-03-06 12:00:00'
            )
            """
        )

    migrate_legacy_schema(engine)

    with engine.begin() as connection:
        columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(tasks)")
        }
        task_count = connection.exec_driver_sql("SELECT COUNT(*) FROM tasks").scalar_one()

    assert "snoozed_until" not in columns
    assert task_count == 1


def test_migrate_legacy_schema_rewrites_settings_to_base_url_and_model(tmp_path: Path):
    session_factory = create_session_factory(tmp_path / "legacy-settings.db")
    engine = session_factory.kw["bind"]

    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE settings (
                id INTEGER PRIMARY KEY,
                locale VARCHAR(8) NOT NULL DEFAULT 'ja',
                ai_provider VARCHAR(32) NOT NULL DEFAULT 'local',
                local_base_url VARCHAR(255) NOT NULL DEFAULT '',
                local_model VARCHAR(255) NOT NULL DEFAULT '',
                openai_model VARCHAR(255) NOT NULL DEFAULT '',
                openrouter_model VARCHAR(255) NOT NULL DEFAULT '',
                capture_interval_minutes INTEGER NOT NULL DEFAULT 180,
                quiet_hours_start VARCHAR(5) NOT NULL DEFAULT '23:00',
                quiet_hours_end VARCHAR(5) NOT NULL DEFAULT '08:00',
                notification_cooldown_minutes INTEGER NOT NULL DEFAULT 180,
                notification_daily_limit INTEGER NOT NULL DEFAULT 4,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO settings (
                id,
                locale,
                ai_provider,
                local_base_url,
                local_model,
                openai_model,
                openrouter_model,
                capture_interval_minutes,
                quiet_hours_start,
                quiet_hours_end,
                notification_cooldown_minutes,
                notification_daily_limit,
                created_at,
                updated_at
            ) VALUES (
                1,
                'ja',
                'openrouter',
                'http://127.0.0.1:1234/v1',
                'qwen/qwen3.5-9b',
                'gpt-4.1-mini',
                'qwen/qwen3.5-397b-a17b',
                180,
                '23:00',
                '08:00',
                180,
                4,
                '2026-03-06 12:00:00',
                '2026-03-06 12:00:00'
            )
            """
        )

    migrate_legacy_schema(engine)

    with engine.begin() as connection:
        columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(settings)")
        }
        row = connection.exec_driver_sql(
            "SELECT vision_base_url, vision_model FROM settings WHERE id = 1"
        ).one()

    assert "vision_base_url" in columns
    assert "vision_model" in columns
    assert "ai_provider" not in columns
    assert "openrouter_model" not in columns
    assert row == ("https://openrouter.ai/api/v1", "qwen/qwen3.5-397b-a17b")
