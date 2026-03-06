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
            return

        columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(tasks)")
        }
        if "snoozed_until" not in columns:
            return

        connection.exec_driver_sql("ALTER TABLE tasks DROP COLUMN snoozed_until")


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
