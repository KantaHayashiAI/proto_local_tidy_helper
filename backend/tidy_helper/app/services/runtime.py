from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import WebSocket
from sqlalchemy.orm import Session, sessionmaker

from tidy_helper.app.config import AppConfig


@dataclass(slots=True)
class AppPaths:
    root: Path
    db_path: Path
    images_dir: Path
    masked_dir: Path
    thumbnails_dir: Path
    exports_dir: Path
    logs_dir: Path

    @classmethod
    def from_root(cls, root: Path) -> "AppPaths":
        return cls(
            root=root,
            db_path=root / "app.db",
            images_dir=root / "images",
            masked_dir=root / "masked",
            thumbnails_dir=root / "thumbnails",
            exports_dir=root / "exports",
            logs_dir=root / "logs",
        )

    def ensure(self) -> None:
        for directory in (
            self.root,
            self.images_dir,
            self.masked_dir,
            self.thumbnails_dir,
            self.exports_dir,
            self.logs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def artifact_url(self, raw_path: str | None) -> str | None:
        if not raw_path:
            return None
        path = Path(raw_path)
        try:
            relative = path.relative_to(self.root)
        except ValueError:
            return None
        return f"/artifacts/{relative.as_posix()}"


class WebSocketHub:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._lock:
            stale: list[WebSocket] = []
            for websocket in self._connections:
                try:
                    await websocket.send_json(message)
                except Exception:
                    stale.append(websocket)
            for websocket in stale:
                self._connections.discard(websocket)


class AppRuntime:
    def __init__(
        self,
        config: AppConfig,
        paths: AppPaths,
        session_factory: sessionmaker[Session],
    ) -> None:
        self.config = config
        self.paths = paths
        self.session_factory = session_factory
        self.scheduler = AsyncIOScheduler(timezone=config.timezone)
        self.websocket_hub = WebSocketHub()
        self.next_run_at: datetime | None = None

    def start_scheduler(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()

    def stop_scheduler(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def update_next_run_at(self) -> None:
        job = self.scheduler.get_job("observation-loop")
        self.next_run_at = job.next_run_time if job else None

    async def broadcast_state(self, reason: str) -> None:
        await self.websocket_hub.broadcast({"type": "state", "payload": {"reason": reason}})

    async def broadcast_notification(self, title: str, body: str, task_id: int | None) -> None:
        await self.websocket_hub.broadcast(
            {
                "type": "notification",
                "payload": {"title": title, "body": body, "task_id": task_id},
            }
        )
