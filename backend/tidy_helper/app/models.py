from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    locale: Mapped[str] = mapped_column(String(8), default="ja")
    vision_base_url: Mapped[str] = mapped_column(String(255), default="")
    vision_model: Mapped[str] = mapped_column(String(255), default="")
    capture_interval_minutes: Mapped[int] = mapped_column(Integer, default=180)
    quiet_hours_start: Mapped[str] = mapped_column(String(5), default="23:00")
    quiet_hours_end: Mapped[str] = mapped_column(String(5), default="08:00")
    notification_cooldown_minutes: Mapped[int] = mapped_column(Integer, default=180)
    notification_daily_limit: Mapped[int] = mapped_column(Integer, default=4)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive
    )


class CameraProfile(Base):
    __tablename__ = "camera_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), default="rtsp_onvif")
    name: Mapped[str] = mapped_column(String(128), default="My Room Camera")
    rtsp_url: Mapped[str] = mapped_column(String(512), default="")
    onvif_host: Mapped[str] = mapped_column(String(255), default="")
    onvif_port: Mapped[int] = mapped_column(Integer, default=8000)
    username: Mapped[str] = mapped_column(String(255), default="")
    password: Mapped[str] = mapped_column(String(255), default="")
    observe_preset: Mapped[str] = mapped_column(String(255), default="observe")
    privacy_preset: Mapped[str] = mapped_column(String(255), default="privacy")
    mock_image_dir: Mapped[str] = mapped_column(String(512), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive
    )

    masks: Mapped[list["MaskRegion"]] = relationship(
        back_populates="camera_profile", cascade="all, delete-orphan"
    )


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    source: Mapped[str] = mapped_column(String(64), default="unknown")
    image_path: Mapped[str] = mapped_column(String(1024))
    masked_image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    capture_status: Mapped[str] = mapped_column(String(32), default="ok")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    analyses: Mapped[list["SceneAnalysis"]] = relationship(
        back_populates="observation", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="observation", cascade="all, delete-orphan"
    )


class SceneAnalysis(Base):
    __tablename__ = "scene_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id"))
    provider: Mapped[str] = mapped_column(String(64))
    scene_summary: Mapped[str] = mapped_column(Text)
    clutter_score: Mapped[float] = mapped_column(Float)
    praise: Mapped[str] = mapped_column(Text)
    provider_meta: Mapped[str] = mapped_column(Text, default="{}")
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    observation: Mapped[Observation] = relationship(back_populates="analyses")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id"))
    title: Mapped[str] = mapped_column(String(255))
    instruction: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)
    estimated_minutes: Mapped[int] = mapped_column(Integer)
    expected_visual_change: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    observation: Mapped[Observation] = relationship(back_populates="tasks")
    events: Mapped[list["TaskEvent"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class TaskEvent(Base):
    __tablename__ = "task_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    task: Mapped[Task] = relationship(back_populates="events")


class NotificationEvent(Base):
    __tablename__ = "notification_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(String(32), default="info")
    channel: Mapped[str] = mapped_column(String(32), default="desktop")
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MemoryRule(Base):
    __tablename__ = "memory_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(64), default="ignore_object")
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive
    )


class MaskRegion(Base):
    __tablename__ = "mask_regions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_profile_id: Mapped[int] = mapped_column(ForeignKey("camera_profiles.id"))
    name: Mapped[str] = mapped_column(String(255), default="Mask")
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    width: Mapped[float] = mapped_column(Float)
    height: Mapped[float] = mapped_column(Float)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    camera_profile: Mapped[CameraProfile] = relationship(back_populates="masks")


class DiagnosticRun(Base):
    __tablename__ = "diagnostic_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    check_name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
