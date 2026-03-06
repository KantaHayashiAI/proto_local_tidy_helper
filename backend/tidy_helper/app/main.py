from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from tidy_helper.app.config import AppConfig, load_config
from tidy_helper.app.database import create_session_factory, migrate_legacy_schema, session_scope
from tidy_helper.app.models import Base, MemoryRule, Observation, Settings
from tidy_helper.app.schemas import (
    ActiveTaskResponse,
    CameraProfilePayload,
    CaptureRunResponse,
    DashboardStateResponse,
    DiagnosticCheckResponse,
    HistoryItemResponse,
    MaskRegionPayload,
    MemoryRulePayload,
    PatchSettingsRequest,
    SavePresetRequest,
    SettingsPayload,
    ValidateCameraRequest,
)
from tidy_helper.app.services.camera import CameraError, build_camera_adapter
from tidy_helper.app.services.diagnostics import latest_diagnostic_rows, run_diagnostics
from tidy_helper.app.services.pipeline import (
    camera_to_payload,
    collect_state,
    ensure_settings,
    get_active_camera,
    get_active_tasks,
    record_diagnostic,
    refresh_scheduler,
    replace_masks,
    rule_to_payload,
    run_observation_cycle,
    serialize_history_item,
    serialize_task,
    settings_to_payload,
    upsert_camera_profile,
)
from tidy_helper.app.services.runtime import AppPaths, AppRuntime
from tidy_helper.app.services.vision import VisionError


def get_runtime(app: FastAPI) -> AppRuntime:
    return app.state.runtime  # type: ignore[return-value]


def get_session(app: FastAPI):
    runtime = get_runtime(app)
    with session_scope(runtime.session_factory) as session:
        yield session


def get_db_session(app: FastAPI):
    def dependency() -> Session:
        yield from get_session(app)

    return dependency


def create_app(config_override: AppConfig | None = None) -> FastAPI:
    config = config_override or load_config()
    paths = AppPaths.from_root(config.app_data_root)
    paths.ensure()
    session_factory = create_session_factory(paths.db_path)
    runtime = AppRuntime(config=config, paths=paths, session_factory=session_factory)
    Base.metadata.create_all(session_factory.kw["bind"])
    migrate_legacy_schema(session_factory.kw["bind"])

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runtime = runtime
        runtime.start_scheduler()
        await refresh_scheduler(runtime)
        yield
        runtime.stop_scheduler()

    app = FastAPI(title="Mitou Local Tidy Helper", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/artifacts", StaticFiles(directory=paths.root), name="artifacts")

    session_dependency = get_db_session(app)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.get("/api/state", response_model=DashboardStateResponse)
    async def api_state(session: Session = Depends(session_dependency)):
        return collect_state(session, runtime)

    @app.get("/api/history", response_model=list[HistoryItemResponse])
    async def api_history(session: Session = Depends(session_dependency)):
        observations = list(
            session.scalars(select(Observation).order_by(desc(Observation.captured_at)).limit(50))
        )
        return [serialize_history_item(runtime, observation) for observation in observations]

    @app.get("/api/tasks/active", response_model=list[ActiveTaskResponse])
    async def api_tasks_active(session: Session = Depends(session_dependency)):
        return [serialize_task(task) for task in get_active_tasks(session)]

    @app.post("/api/setup/validate-camera")
    async def api_validate_camera(
        request: ValidateCameraRequest, session: Session = Depends(session_dependency)
    ):
        del session
        try:
            adapter = build_camera_adapter(request.profile)
            details = adapter.healthcheck()
            return {"ok": True, "details": details}
        except CameraError as exc:
            return {"ok": False, "details": {"error": str(exc)}}

    @app.post("/api/setup/save-presets")
    async def api_save_presets(
        request: SavePresetRequest, session: Session = Depends(session_dependency)
    ):
        try:
            adapter = build_camera_adapter(request.profile)
            result = adapter.save_preset(request.preset_name)
            payload = request.profile.model_copy()
            if request.preset_name == "observe":
                payload.observe_preset = result["preset"]
            else:
                payload.privacy_preset = result["preset"]
            camera = upsert_camera_profile(session, payload)
            return {"ok": True, "profile": camera_to_payload(camera)}
        except CameraError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/captures/run-now", response_model=CaptureRunResponse)
    async def api_run_now():
        try:
            result = await run_observation_cycle(runtime=runtime, reason="manual")
            return CaptureRunResponse(**result)
        except (CameraError, VisionError) as exc:
            with session_scope(runtime.session_factory) as session:
                record_diagnostic(
                    session,
                    check_name="capture.run",
                    status="error",
                    message="手動観測に失敗しました。",
                    details={"error": str(exc)},
                )
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/rules", response_model=MemoryRulePayload)
    async def api_rules(
        request: MemoryRulePayload, session: Session = Depends(session_dependency)
    ):
        if request.id:
            rule = session.get(MemoryRule, request.id)
        else:
            rule = None
        if rule is None:
            rule = MemoryRule()
            session.add(rule)
        rule.kind = request.kind
        rule.title = request.title
        rule.content = request.content
        rule.enabled = request.enabled
        session.flush()
        await runtime.broadcast_state("rules-updated")
        return rule_to_payload(rule)

    @app.patch("/api/settings", response_model=DashboardStateResponse)
    async def api_patch_settings(
        request: PatchSettingsRequest, session: Session = Depends(session_dependency)
    ):
        settings = ensure_settings(session, runtime.config)
        payload: SettingsPayload = request.settings
        settings.locale = payload.locale
        settings.ai_provider = payload.ai_provider
        settings.local_base_url = payload.local_base_url
        settings.local_model = payload.local_model
        settings.openai_model = payload.openai_model
        settings.openrouter_model = payload.openrouter_model
        settings.capture_interval_minutes = payload.capture_interval_minutes
        settings.quiet_hours_start = payload.quiet_hours_start
        settings.quiet_hours_end = payload.quiet_hours_end
        settings.notification_cooldown_minutes = payload.notification_cooldown_minutes
        settings.notification_daily_limit = payload.notification_daily_limit

        camera = None
        if request.camera_profile is not None:
            camera = upsert_camera_profile(session, request.camera_profile)
            replace_masks(session, camera, request.mask_regions)

        session.flush()
        await refresh_scheduler(runtime)
        await runtime.broadcast_state("settings-updated")
        return collect_state(session, runtime)

    @app.get("/api/diagnostics", response_model=list[DiagnosticCheckResponse])
    async def api_diagnostics(session: Session = Depends(session_dependency)):
        results = run_diagnostics(session, runtime)
        return results + latest_diagnostic_rows(session)

    @app.websocket("/ws")
    async def websocket_events(websocket: WebSocket):
        await runtime.websocket_hub.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await runtime.websocket_hub.disconnect(websocket)

    return app


app = create_app()


def main() -> None:
    config = load_config()
    uvicorn.run("tidy_helper.app.main:app", host="127.0.0.1", port=config.port, reload=False)


if __name__ == "__main__":
    main()
