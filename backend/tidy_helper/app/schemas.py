from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class SettingsPayload(BaseModel):
    locale: str = "ja"
    ai_provider: Literal["local", "openai", "openrouter"] = "local"
    local_base_url: str = ""
    local_model: str = ""
    openai_model: str = ""
    openrouter_model: str = ""
    capture_interval_minutes: int = 180
    quiet_hours_start: str = "23:00"
    quiet_hours_end: str = "08:00"
    notification_cooldown_minutes: int = 180
    notification_daily_limit: int = 4

    @field_validator("capture_interval_minutes")
    @classmethod
    def validate_interval(cls, value: int) -> int:
        return max(15, min(value, 1440))

    @field_validator("notification_cooldown_minutes")
    @classmethod
    def validate_cooldown(cls, value: int) -> int:
        return max(15, min(value, 1440))

    @field_validator("notification_daily_limit")
    @classmethod
    def validate_daily_limit(cls, value: int) -> int:
        return max(1, min(value, 32))


class CameraProfilePayload(BaseModel):
    id: int | None = None
    kind: Literal["rtsp_onvif", "mock"] = "rtsp_onvif"
    name: str = "My Room Camera"
    rtsp_url: str = ""
    onvif_host: str = ""
    onvif_port: int = 8000
    username: str = ""
    password: str = ""
    observe_preset: str = "observe"
    privacy_preset: str = "privacy"
    mock_image_dir: str = ""
    active: bool = True


class MaskRegionPayload(BaseModel):
    id: int | None = None
    name: str = "Mask"
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)
    enabled: bool = True


class MemoryRulePayload(BaseModel):
    id: int | None = None
    kind: Literal["ignore_object", "note", "quiet_hours"] = "ignore_object"
    title: str
    content: str
    enabled: bool = True


class ValidateCameraRequest(BaseModel):
    profile: CameraProfilePayload


class SavePresetRequest(BaseModel):
    profile: CameraProfilePayload
    preset_name: Literal["observe", "privacy"]


class PatchSettingsRequest(BaseModel):
    settings: SettingsPayload
    camera_profile: CameraProfilePayload | None = None
    mask_regions: list[MaskRegionPayload] = []


class TaskCandidate(BaseModel):
    title: str
    instruction: str
    reason: str
    priority: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0.0, le=1.0)
    estimated_minutes: int = Field(ge=1, le=120)
    expected_visual_change: str


class SceneAnalysisResult(BaseModel):
    scene_summary: str
    clutter_score: float = Field(ge=0.0, le=10.0)
    tasks: list[TaskCandidate]
    praise: str
    provider_meta: dict[str, Any] = {}


class CompletionAssessmentResult(BaseModel):
    status: Literal["done", "pending", "uncertain"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class ActiveTaskResponse(BaseModel):
    id: int
    title: str
    instruction: str
    reason: str
    priority: int
    confidence: float
    estimated_minutes: int
    expected_visual_change: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class HistoryItemResponse(BaseModel):
    observation_id: int
    captured_at: datetime
    source: str
    image_url: str | None
    masked_image_url: str | None
    thumbnail_url: str | None
    width: int
    height: int
    provider: str | None
    scene_summary: str | None
    clutter_score: float | None
    praise: str | None
    tasks: list[ActiveTaskResponse]


class DashboardStateResponse(BaseModel):
    settings: SettingsPayload
    camera_profile: CameraProfilePayload | None
    masks: list[MaskRegionPayload]
    rules: list[MemoryRulePayload]
    active_tasks: list[ActiveTaskResponse]
    last_observation: HistoryItemResponse | None
    next_run_at: datetime | None
    quiet_hours_active: bool
    storage_usage_bytes: int
    storage_usage_human: str
    notifications_today: int


class DiagnosticCheckResponse(BaseModel):
    check_name: str
    status: Literal["ok", "warning", "error"]
    message: str
    details: dict[str, Any] = {}
    created_at: datetime


class CaptureRunResponse(BaseModel):
    observation_id: int | None
    notified_task_id: int | None
    message: str
