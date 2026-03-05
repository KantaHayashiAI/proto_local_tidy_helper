from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from tidy_helper.app.models import DiagnosticRun
from tidy_helper.app.schemas import DiagnosticCheckResponse
from tidy_helper.app.services.camera import CameraError, build_camera_adapter
from tidy_helper.app.services.pipeline import (
    camera_to_payload,
    ensure_settings,
    get_active_camera,
    record_diagnostic,
    settings_to_payload,
)
from tidy_helper.app.services.runtime import AppRuntime
from tidy_helper.app.services.vision import VisionError, build_vision_provider


def run_diagnostics(session: Session, runtime: AppRuntime) -> list[DiagnosticCheckResponse]:
    settings = ensure_settings(session, runtime.config)
    settings_payload = settings_to_payload(settings)
    checks: list[DiagnosticCheckResponse] = []

    try:
        record_diagnostic(
            session,
            check_name="database.write",
            status="ok",
            message="SQLite への書き込みに成功しました。",
        )
        checks.append(
            DiagnosticCheckResponse(
                check_name="database.write",
                status="ok",
                message="SQLite への書き込みに成功しました。",
                details={},
                created_at=datetime.now(UTC),
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            DiagnosticCheckResponse(
                check_name="database.write",
                status="error",
                message="SQLite への書き込みに失敗しました。",
                details={"error": str(exc)},
                created_at=datetime.now(UTC),
            )
        )

    camera = get_active_camera(session)
    if camera is None:
        checks.append(
            DiagnosticCheckResponse(
                check_name="camera.profile",
                status="warning",
                message="アクティブなカメラ設定がありません。",
                details={},
                created_at=datetime.now(UTC),
            )
        )
    else:
        try:
            payload = camera_to_payload(camera)
            assert payload is not None
            details = build_camera_adapter(payload).healthcheck()
            record_diagnostic(
                session,
                check_name="camera.healthcheck",
                status="ok",
                message="カメラ接続を確認しました。",
                details=details,
            )
            checks.append(
                DiagnosticCheckResponse(
                    check_name="camera.healthcheck",
                    status="ok",
                    message="カメラ接続を確認しました。",
                    details=details,
                    created_at=datetime.now(UTC),
                )
            )
        except CameraError as exc:
            checks.append(
                DiagnosticCheckResponse(
                    check_name="camera.healthcheck",
                    status="error",
                    message="カメラ接続に失敗しました。",
                    details={"error": str(exc)},
                    created_at=datetime.now(UTC),
                )
            )

    try:
        details = build_vision_provider(settings_payload, runtime.config).healthcheck()
        checks.append(
            DiagnosticCheckResponse(
                check_name="vision.provider",
                status="ok",
                message="AI プロバイダ設定を確認しました。",
                details=details,
                created_at=datetime.now(UTC),
            )
        )
    except VisionError as exc:
        checks.append(
            DiagnosticCheckResponse(
                check_name="vision.provider",
                status="error",
                message="AI プロバイダ設定に問題があります。",
                details={"error": str(exc)},
                created_at=datetime.now(UTC),
            )
        )

    checks.append(
        DiagnosticCheckResponse(
            check_name="secrets.openai",
            status="ok" if runtime.config.openai_api_key else "warning",
            message="OPENAI_API_KEY を検出しました。"
            if runtime.config.openai_api_key
            else "OPENAI_API_KEY は未設定です。",
            details={},
            created_at=datetime.now(UTC),
        )
    )
    checks.append(
        DiagnosticCheckResponse(
            check_name="secrets.openrouter",
            status="ok" if runtime.config.openrouter_api_key else "warning",
            message="OPENROUTER_API_KEY を検出しました。"
            if runtime.config.openrouter_api_key
            else "OPENROUTER_API_KEY は未設定です。",
            details={},
            created_at=datetime.now(UTC),
        )
    )

    return checks


def latest_diagnostic_rows(session: Session) -> list[DiagnosticCheckResponse]:
    rows = list(
        session.scalars(select(DiagnosticRun).order_by(desc(DiagnosticRun.created_at)).limit(25))
    )
    return [
        DiagnosticCheckResponse(
            check_name=row.check_name,
            status=row.status,
            message=row.message,
            details=json.loads(row.details or "{}"),
            created_at=row.created_at,
        )
        for row in rows
    ]
