from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_session_factory(db_path: Path) -> sessionmaker[Session]:
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def migrate_legacy_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "tasks" not in tables:
            pass
        else:
            columns = {
                row[1] for row in connection.exec_driver_sql("PRAGMA table_info(tasks)")
            }
            if "snoozed_until" in columns:
                connection.exec_driver_sql("ALTER TABLE tasks DROP COLUMN snoozed_until")

        if "settings" not in tables:
            return

        columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(settings)")
        }
        if "vision_base_url" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE settings ADD COLUMN vision_base_url VARCHAR(255) NOT NULL DEFAULT ''"
            )
        if "vision_model" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE settings ADD COLUMN vision_model VARCHAR(255) NOT NULL DEFAULT ''"
            )

        columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(settings)")
        }
        if {"ai_provider", "local_base_url", "local_model", "openai_model", "openrouter_model"} & columns:
            connection.exec_driver_sql(
                """
                UPDATE settings
                SET
                    vision_base_url = CASE
                        WHEN trim(vision_base_url) <> '' THEN vision_base_url
                        WHEN ai_provider = 'openai' THEN 'https://api.openai.com/v1'
                        WHEN ai_provider = 'openrouter' THEN 'https://openrouter.ai/api/v1'
                        ELSE COALESCE(local_base_url, '')
                    END,
                    vision_model = CASE
                        WHEN trim(vision_model) <> '' THEN vision_model
                        WHEN ai_provider = 'openai' THEN COALESCE(openai_model, '')
                        WHEN ai_provider = 'openrouter' THEN COALESCE(openrouter_model, '')
                        ELSE COALESCE(local_model, '')
                    END
                """
            )

        columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(settings)")
        }
        for column in (
            "ai_provider",
            "local_base_url",
            "local_model",
            "openai_model",
            "openrouter_model",
        ):
            if column in columns:
                connection.exec_driver_sql(f"ALTER TABLE settings DROP COLUMN {column}")


@contextmanager
def session_scope(session_factory: sessionmaker[Session]):
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
