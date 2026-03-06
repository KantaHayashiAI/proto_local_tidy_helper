from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from PIL import Image, ImageDraw
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from tidy_helper.app.config import AppConfig
from tidy_helper.app.database import session_scope
from tidy_helper.app.models import (
    CameraProfile,
    DiagnosticRun,
    MaskRegion,
    MemoryRule,
    NotificationEvent,
    Observation,
    SceneAnalysis,
    Settings,
    Task,
    TaskEvent,
)
from tidy_helper.app.schemas import (
    ActiveTaskResponse,
    CameraProfilePayload,
    DashboardStateResponse,
    HistoryItemResponse,
    MaskRegionPayload,
    MemoryRulePayload,
    SceneAnalysisResult,
    SettingsPayload,
)
from tidy_helper.app.services.camera import CameraError, build_camera_adapter
from tidy_helper.app.services.runtime import AppRuntime
from tidy_helper.app.services.vision import VisionError, build_vision_provider


def humanize_bytes(num_bytes: int) -> str:
    value = float(num_bytes)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def storage_usage_bytes(root: Path) -> int:
    total = 0
    if not root.exists():
        return total
    for path in root.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total


def is_quiet_hours(now: datetime, start_label: str, end_label: str) -> bool:
    start_hour, start_minute = (int(part) for part in start_label.split(":"))
    end_hour, end_minute = (int(part) for part in end_label.split(":"))
    current = now.time()
    start = time(start_hour, start_minute)
    end = time(end_hour, end_minute)
    if start <= end:
        return start <= current < end
    return current >= start or current < end


def settings_to_payload(settings: Settings) -> SettingsPayload:
    return SettingsPayload(
        locale=settings.locale,
        ai_provider=settings.ai_provider,
        local_base_url=settings.local_base_url,
        local_model=settings.local_model,
        openai_model=settings.openai_model,
        openrouter_model=settings.openrouter_model,
        capture_interval_minutes=settings.capture_interval_minutes,
        quiet_hours_start=settings.quiet_hours_start,
        quiet_hours_end=settings.quiet_hours_end,
        notification_cooldown_minutes=settings.notification_cooldown_minutes,
        notification_daily_limit=settings.notification_daily_limit,
    )


def camera_to_payload(camera: CameraProfile | None) -> CameraProfilePayload | None:
    if camera is None:
        return None
    return CameraProfilePayload(
        id=camera.id,
        kind=camera.kind,
        name=camera.name,
        rtsp_url=camera.rtsp_url,
        onvif_host=camera.onvif_host,
        onvif_port=camera.onvif_port,
        username=camera.username,
        password=camera.password,
        observe_preset=camera.observe_preset,
        privacy_preset=camera.privacy_preset,
        mock_image_dir=camera.mock_image_dir,
        active=camera.active,
    )


def mask_to_payload(mask: MaskRegion) -> MaskRegionPayload:
    return MaskRegionPayload(
        id=mask.id,
        name=mask.name,
        x=mask.x,
        y=mask.y,
        width=mask.width,
        height=mask.height,
        enabled=mask.enabled,
    )


def rule_to_payload(rule: MemoryRule) -> MemoryRulePayload:
    return MemoryRulePayload(
        id=rule.id,
        kind=rule.kind,
        title=rule.title,
        content=rule.content,
        enabled=rule.enabled,
    )


def ensure_settings(session: Session, config: AppConfig) -> Settings:
    settings = session.get(Settings, 1)
    if settings is None:
        settings = Settings(
            id=1,
            locale="ja",
            ai_provider="local",
            local_base_url=config.default_local_base_url,
            local_model=config.default_local_model,
            openai_model=config.default_openai_model,
            openrouter_model=config.default_openrouter_model,
        )
        session.add(settings)
        session.flush()
    return settings


def get_active_camera(session: Session) -> CameraProfile | None:
    return session.scalar(
        select(CameraProfile).where(CameraProfile.active.is_(True)).order_by(desc(CameraProfile.id))
    )


def get_active_tasks(session: Session, now: datetime | None = None) -> list[Task]:
    del now
    return list(
        session.scalars(
            select(Task)
            .where(Task.status == "active")
            .order_by(Task.priority.desc(), Task.created_at.desc())
        )
    )


def serialize_task(task: Task) -> ActiveTaskResponse:
    return ActiveTaskResponse.model_validate(task)


def latest_analysis(observation: Observation) -> SceneAnalysis | None:
    if not observation.analyses:
        return None
    return sorted(observation.analyses, key=lambda item: item.created_at)[-1]


def serialize_history_item(runtime: AppRuntime, observation: Observation) -> HistoryItemResponse:
    analysis = latest_analysis(observation)
    tasks = sorted(observation.tasks, key=lambda task: task.priority, reverse=True)
    return HistoryItemResponse(
        observation_id=observation.id,
        captured_at=observation.captured_at,
        source=observation.source,
        image_url=runtime.paths.artifact_url(observation.image_path),
        masked_image_url=runtime.paths.artifact_url(observation.masked_image_path),
        thumbnail_url=runtime.paths.artifact_url(observation.thumbnail_path),
        width=observation.width,
        height=observation.height,
        provider=analysis.provider if analysis else None,
        scene_summary=analysis.scene_summary if analysis else None,
        clutter_score=analysis.clutter_score if analysis else None,
        praise=analysis.praise if analysis else None,
        tasks=[serialize_task(task) for task in tasks],
    )


def notifications_today_count(session: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    start = datetime(now.year, now.month, now.day)
    end = start + timedelta(days=1)
    return int(
        session.scalar(
            select(func.count(NotificationEvent.id)).where(
                NotificationEvent.sent_at >= start, NotificationEvent.sent_at < end
            )
        )
        or 0
    )


def record_diagnostic(
    session: Session,
    *,
    check_name: str,
    status: str,
    message: str,
    details: dict[str, object] | None = None,
) -> DiagnosticRun:
    item = DiagnosticRun(
        check_name=check_name,
        status=status,
        message=message,
        details=json.dumps(details or {}, ensure_ascii=False),
    )
    session.add(item)
    session.flush()
    return item


def apply_masks(source_path: Path, masks: list[MaskRegion], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as image:
        draw = ImageDraw.Draw(image)
        width, height = image.size
        for mask in masks:
            if not mask.enabled:
                continue
            x0 = int(mask.x * width)
            y0 = int(mask.y * height)
            x1 = int((mask.x + mask.width) * width)
            y1 = int((mask.y + mask.height) * height)
            draw.rectangle((x0, y0, x1, y1), fill="black")
        image.save(destination)
    return destination


def create_thumbnail(source_path: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as image:
        image.thumbnail((720, 720))
        image.save(destination)
    return destination


def choose_task_for_notification(tasks: list[Task]) -> Task | None:
    if not tasks:
        return None
    ordered = sorted(
        tasks,
        key=lambda task: (task.priority, task.confidence, -task.estimated_minutes),
        reverse=True,
    )
    return ordered[0]


def recent_history_context(session: Session) -> list[dict[str, object]]:
    observations = list(
        session.scalars(select(Observation).order_by(desc(Observation.captured_at)).limit(5))
    )
    payload: list[dict[str, object]] = []
    for observation in observations:
        analysis = latest_analysis(observation)
        if analysis is None:
            continue
        payload.append(
            {
                "captured_at": observation.captured_at.isoformat(),
                "summary": analysis.scene_summary,
                "clutter_score": analysis.clutter_score,
            }
        )
    return payload


def active_task_context(session: Session) -> list[dict[str, object]]:
    return [
        {
            "id": task.id,
            "title": task.title,
            "instruction": task.instruction,
            "reason": task.reason,
        }
        for task in get_active_tasks(session)
    ]


def rules_context(session: Session) -> list[dict[str, object]]:
    return [
        {
            "id": rule.id,
            "kind": rule.kind,
            "title": rule.title,
            "content": rule.content,
        }
        for rule in session.scalars(select(MemoryRule).where(MemoryRule.enabled.is_(True)))
    ]


def persist_analysis(
    session: Session,
    *,
    observation: Observation,
    provider_name: str,
    result: SceneAnalysisResult,
) -> list[Task]:
    analysis = SceneAnalysis(
        observation_id=observation.id,
        provider=provider_name,
        scene_summary=result.scene_summary,
        clutter_score=result.clutter_score,
        praise=result.praise,
        provider_meta=json.dumps(result.provider_meta, ensure_ascii=False),
        raw_json=result.model_dump_json(),
    )
    session.add(analysis)
    session.flush()

    existing_titles = {
        task.title.strip().lower()
        for task in session.scalars(select(Task).where(Task.status == "active"))
    }
    created: list[Task] = []
    for candidate in result.tasks:
        if candidate.title.strip().lower() in existing_titles:
            continue
        task = Task(
            observation_id=observation.id,
            title=candidate.title,
            instruction=candidate.instruction,
            reason=candidate.reason,
            priority=candidate.priority,
            confidence=candidate.confidence,
            estimated_minutes=candidate.estimated_minutes,
            expected_visual_change=candidate.expected_visual_change,
            status="active",
        )
        session.add(task)
        session.flush()
        session.add(TaskEvent(task_id=task.id, kind="created", payload=candidate.model_dump_json()))
        created.append(task)
    return created


def collect_state(session: Session, runtime: AppRuntime) -> DashboardStateResponse:
    settings_model = ensure_settings(session, runtime.config)
    settings_payload = settings_to_payload(settings_model)
    camera = get_active_camera(session)
    masks = list(camera.masks) if camera else []
    rules = list(session.scalars(select(MemoryRule).order_by(desc(MemoryRule.updated_at))))
    last_observation = session.scalar(
        select(Observation).order_by(desc(Observation.captured_at)).limit(1)
    )
    now = datetime.now()
    quiet_hours = is_quiet_hours(
        now, settings_model.quiet_hours_start, settings_model.quiet_hours_end
    )
    return DashboardStateResponse(
        settings=settings_payload,
        camera_profile=camera_to_payload(camera),
        masks=[mask_to_payload(mask) for mask in masks],
        rules=[rule_to_payload(rule) for rule in rules],
        active_tasks=[serialize_task(task) for task in get_active_tasks(session)],
        last_observation=serialize_history_item(runtime, last_observation)
        if last_observation
        else None,
        next_run_at=runtime.next_run_at,
        quiet_hours_active=quiet_hours,
        storage_usage_bytes=storage_usage_bytes(runtime.paths.root),
        storage_usage_human=humanize_bytes(storage_usage_bytes(runtime.paths.root)),
        notifications_today=notifications_today_count(session),
    )


def upsert_camera_profile(session: Session, payload: CameraProfilePayload) -> CameraProfile:
    if payload.id is not None:
        camera = session.get(CameraProfile, payload.id)
    else:
        camera = None
    if camera is None:
        camera = CameraProfile()
        session.add(camera)
    camera.kind = payload.kind
    camera.name = payload.name
    camera.rtsp_url = payload.rtsp_url
    camera.onvif_host = payload.onvif_host
    camera.onvif_port = payload.onvif_port
    camera.username = payload.username
    camera.password = payload.password or camera.password
    camera.observe_preset = payload.observe_preset
    camera.privacy_preset = payload.privacy_preset
    camera.mock_image_dir = payload.mock_image_dir
    camera.active = payload.active
    session.flush()
    if camera.active:
        session.query(CameraProfile).filter(CameraProfile.id != camera.id).update(
            {CameraProfile.active: False}
        )
    return camera


def replace_masks(session: Session, camera: CameraProfile, masks: list[MaskRegionPayload]) -> None:
    for existing in list(camera.masks):
        session.delete(existing)
    session.flush()
    for mask in masks:
        session.add(
            MaskRegion(
                camera_profile_id=camera.id,
                name=mask.name,
                x=mask.x,
                y=mask.y,
                width=mask.width,
                height=mask.height,
                enabled=mask.enabled,
            )
        )
    session.flush()


async def refresh_scheduler(runtime: AppRuntime) -> None:
    with session_scope(runtime.session_factory) as session:
        settings = ensure_settings(session, runtime.config)
        interval = settings.capture_interval_minutes

    runtime.scheduler.remove_all_jobs()
    runtime.scheduler.add_job(
        run_observation_cycle,
        "interval",
        minutes=interval,
        id="observation-loop",
        kwargs={"runtime": runtime, "reason": "scheduled"},
        replace_existing=True,
    )
    runtime.update_next_run_at()
    await runtime.broadcast_state("scheduler-refreshed")


async def run_observation_cycle(runtime: AppRuntime, reason: str = "manual") -> dict[str, object]:
    result: dict[str, object] = {
        "observation_id": None,
        "notified_task_id": None,
        "message": "観測はまだ実行されていません。",
    }
    with session_scope(runtime.session_factory) as session:
        settings_model = ensure_settings(session, runtime.config)
        settings_payload = settings_to_payload(settings_model)
        camera_model = get_active_camera(session)
        if camera_model is None:
            raise CameraError("active camera profile is not configured")
        camera_payload = camera_to_payload(camera_model)
        assert camera_payload is not None
        adapter = build_camera_adapter(camera_payload)
        provider = build_vision_provider(settings_payload, runtime.config)

        masks = list(camera_model.masks)
        reference_summary = None
        latest_observation = session.scalar(
            select(Observation).order_by(desc(Observation.captured_at)).limit(1)
        )
        if latest_observation:
            previous_analysis = latest_analysis(latest_observation)
            reference_summary = previous_analysis.scene_summary if previous_analysis else None

        privacy_error = None
        try:
            try:
                adapter.move_to_preset("privacy")
            except Exception as exc:  # noqa: BLE001
                privacy_error = str(exc)
            adapter.move_to_preset("observe")
            frame = adapter.capture_frame(runtime.paths.images_dir)
        finally:
            try:
                adapter.move_to_preset("privacy")
            except Exception as exc:  # noqa: BLE001
                record_diagnostic(
                    session,
                    check_name="camera.privacy-return",
                    status="error",
                    message="観測後に privacy プリセットへ戻せませんでした。",
                    details={"error": str(exc)},
                )

        captured_at = frame.captured_at.astimezone(UTC).replace(tzinfo=None)
        observation = Observation(
            captured_at=captured_at,
            source=frame.source,
            image_path=str(frame.image_path),
            width=frame.width,
            height=frame.height,
            capture_status="ok",
            error_message=privacy_error,
        )
        session.add(observation)
        session.flush()

        masked_path = runtime.paths.masked_dir / f"masked-{frame.image_path.name}"
        thumbnail_path = runtime.paths.thumbnails_dir / f"thumb-{frame.image_path.name}"
        apply_masks(frame.image_path, masks, masked_path)
        create_thumbnail(masked_path, thumbnail_path)
        observation.masked_image_path = str(masked_path)
        observation.thumbnail_path = str(thumbnail_path)
        session.flush()

        for task in get_active_tasks(session):
            assessment = provider.check_completion(
                image_path=masked_path,
                task={
                    "title": task.title,
                    "instruction": task.instruction,
                    "expected_visual_change": task.expected_visual_change,
                },
                reference_summary=reference_summary,
            )
            task.last_evaluated_at = datetime.now(UTC).replace(tzinfo=None)
            if assessment.status == "done":
                task.status = "done"
                task.completed_at = datetime.now(UTC).replace(tzinfo=None)
                session.add(
                    TaskEvent(
                        task_id=task.id,
                        kind="auto_done",
                        payload=assessment.model_dump_json(),
                    )
                )

        scene_result = provider.analyze_scene(
            image_path=masked_path,
            recent_history=recent_history_context(session),
            active_tasks=active_task_context(session),
            rules=rules_context(session),
            quiet_hours_active=is_quiet_hours(
                datetime.now(),
                settings_model.quiet_hours_start,
                settings_model.quiet_hours_end,
            ),
            notifications_today=notifications_today_count(session),
        )
        created_tasks = persist_analysis(
            session,
            observation=observation,
            provider_name=provider.name,
            result=scene_result,
        )

        notifications_today = notifications_today_count(session)
        quiet_hours_active = is_quiet_hours(
            datetime.now(), settings_model.quiet_hours_start, settings_model.quiet_hours_end
        )
        latest_notification = session.scalar(
            select(NotificationEvent).order_by(desc(NotificationEvent.sent_at)).limit(1)
        )
        cooldown_ok = True
        if latest_notification is not None:
            cooldown_ok = latest_notification.sent_at <= datetime.now(UTC).replace(tzinfo=None) - timedelta(
                minutes=settings_model.notification_cooldown_minutes
            )
        if (
            created_tasks
            and not quiet_hours_active
            and notifications_today < settings_model.notification_daily_limit
            and cooldown_ok
        ):
            candidate = choose_task_for_notification(created_tasks)
            if candidate is not None:
                notification = NotificationEvent(
                    task_id=candidate.id,
                    title=f"次の一手: {candidate.title}",
                    body=candidate.instruction,
                    level="info",
                    channel="desktop",
                )
                session.add(notification)
                session.add(
                    TaskEvent(
                        task_id=candidate.id,
                        kind="notified",
                        payload=json.dumps({"reason": reason}, ensure_ascii=False),
                    )
                )
                session.flush()
                result["notified_task_id"] = candidate.id
                await runtime.broadcast_notification(
                    notification.title, notification.body, candidate.id
                )

        result["observation_id"] = observation.id
        result["message"] = "観測と分析を完了しました。"

    runtime.update_next_run_at()
    await runtime.broadcast_state("capture-complete")
    return result
