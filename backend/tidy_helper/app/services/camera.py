from __future__ import annotations

import shutil
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import cv2
from PIL import Image
from onvif import ONVIFCamera
from zeep.exceptions import Fault

from tidy_helper.app.schemas import CameraProfilePayload


class CameraError(RuntimeError):
    pass


@dataclass(slots=True)
class CapturedFrame:
    image_path: Path
    captured_at: datetime
    source: str
    width: int
    height: int


class CameraAdapter(ABC):
    def __init__(self, profile: CameraProfilePayload) -> None:
        self.profile = profile

    @abstractmethod
    def healthcheck(self) -> dict[str, object]:
        raise NotImplementedError

    @abstractmethod
    def move_to_preset(self, name: str) -> dict[str, object]:
        raise NotImplementedError

    @abstractmethod
    def capture_frame(self, storage_dir: Path) -> CapturedFrame:
        raise NotImplementedError

    @abstractmethod
    def list_presets(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def save_preset(self, name: str) -> dict[str, object]:
        raise NotImplementedError


class MockCameraAdapter(CameraAdapter):
    def __init__(self, profile: CameraProfilePayload) -> None:
        super().__init__(profile)
        self._cursor = 0

    @property
    def image_dir(self) -> Path:
        return Path(self.profile.mock_image_dir)

    def _list_images(self) -> list[Path]:
        if not self.image_dir.exists():
            raise CameraError(f"mock image directory not found: {self.image_dir}")
        images = [
            path
            for path in sorted(self.image_dir.iterdir())
            if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".ppm", ".webp"}
        ]
        if not images:
            raise CameraError("mock image directory has no supported images")
        return images

    def healthcheck(self) -> dict[str, object]:
        images = self._list_images()
        return {"mode": "mock", "images": len(images), "directory": str(self.image_dir)}

    def move_to_preset(self, name: str) -> dict[str, object]:
        return {"preset": name, "mode": "mock"}

    def capture_frame(self, storage_dir: Path) -> CapturedFrame:
        images = self._list_images()
        source = images[self._cursor % len(images)]
        self._cursor += 1
        captured_at = datetime.now(timezone.utc)
        destination = storage_dir / f"mock-{captured_at.strftime('%Y%m%d-%H%M%S-%f')}.png"
        shutil.copy2(source, destination)
        with Image.open(destination) as image:
            width, height = image.size
        return CapturedFrame(
            image_path=destination,
            captured_at=captured_at,
            source="mock",
            width=width,
            height=height,
        )

    def list_presets(self) -> list[str]:
        return ["observe", "privacy"]

    def save_preset(self, name: str) -> dict[str, object]:
        return {"preset": name, "mode": "mock"}


class RtspOnvifCameraAdapter(CameraAdapter):
    def __init__(self, profile: CameraProfilePayload) -> None:
        super().__init__(profile)
        self._camera: ONVIFCamera | None = None
        self._media_service = None
        self._ptz_service = None
        self._profile_token: str | None = None

    def _ensure_onvif(self) -> None:
        if self._camera:
            return
        self._camera = ONVIFCamera(
            self.profile.onvif_host,
            self.profile.onvif_port,
            self.profile.username,
            self.profile.password,
        )
        self._media_service = self._camera.create_media_service()
        self._ptz_service = self._camera.create_ptz_service()
        profiles = self._media_service.GetProfiles()
        if not profiles:
            raise CameraError("ONVIF profile not found")
        profile_token = getattr(profiles[0], "token", None) or getattr(profiles[0], "_token", None)
        if not profile_token:
            raise CameraError("ONVIF profile token not found")
        self._profile_token = profile_token

    def _resolve_preset_name(self, name: str) -> str:
        if name == "observe":
            return self.profile.observe_preset
        if name == "privacy":
            return self.profile.privacy_preset
        return name

    def _get_presets(self):
        self._ensure_onvif()
        request = self._ptz_service.create_type("GetPresets")
        request.ProfileToken = self._profile_token
        return self._ptz_service.GetPresets(request)

    def healthcheck(self) -> dict[str, object]:
        details: dict[str, object] = {
            "rtsp_url": self.profile.rtsp_url,
            "onvif": self.profile.onvif_host,
            "presets": [],
        }
        frame = self.capture_frame(Path.cwd())
        details["rtsp_frame_size"] = [frame.width, frame.height]
        if frame.image_path.exists():
            frame.image_path.unlink(missing_ok=True)
        try:
            details["presets"] = self.list_presets()
        except Fault as exc:
            raise CameraError(f"ONVIF preset listing failed: {exc}") from exc
        return details

    def move_to_preset(self, name: str) -> dict[str, object]:
        self._ensure_onvif()
        resolved_name = self._resolve_preset_name(name)
        preset = next(
            (
                candidate
                for candidate in self._get_presets()
                if getattr(candidate, "Name", "") == resolved_name
            ),
            None,
        )
        if preset is None:
            raise CameraError(f"preset not found: {resolved_name}")
        request = self._ptz_service.create_type("GotoPreset")
        request.ProfileToken = self._profile_token
        request.PresetToken = getattr(preset, "token", None) or getattr(preset, "_token", None)
        self._ptz_service.GotoPreset(request)
        time.sleep(1.0)
        return {"preset": resolved_name}

    def capture_frame(self, storage_dir: Path) -> CapturedFrame:
        storage_dir.mkdir(parents=True, exist_ok=True)
        capture = cv2.VideoCapture(self.profile.rtsp_url, cv2.CAP_FFMPEG)
        if not capture.isOpened():
            capture = cv2.VideoCapture(self.profile.rtsp_url)
        if not capture.isOpened():
            raise CameraError("RTSP stream could not be opened")

        image = None
        for _ in range(24):
            ok, frame = capture.read()
            if ok and frame is not None:
                image = frame
                time.sleep(0.05)
        capture.release()
        if image is None:
            raise CameraError("RTSP stream did not yield a frame")

        captured_at = datetime.now(timezone.utc)
        destination = storage_dir / f"capture-{captured_at.strftime('%Y%m%d-%H%M%S-%f')}.jpg"
        cv2.imwrite(str(destination), image, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        height, width = image.shape[:2]
        return CapturedFrame(
            image_path=destination,
            captured_at=captured_at,
            source="rtsp",
            width=width,
            height=height,
        )

    def list_presets(self) -> list[str]:
        return [getattr(preset, "Name", "") for preset in self._get_presets()]

    def save_preset(self, name: str) -> dict[str, object]:
        self._ensure_onvif()
        resolved_name = self._resolve_preset_name(name)
        current = next(
            (
                candidate
                for candidate in self._get_presets()
                if getattr(candidate, "Name", "") == resolved_name
            ),
            None,
        )
        request = self._ptz_service.create_type("SetPreset")
        request.ProfileToken = self._profile_token
        request.PresetName = resolved_name
        if current is not None:
            request.PresetToken = getattr(current, "token", None) or getattr(
                current, "_token", None
            )
        token = self._ptz_service.SetPreset(request)
        return {"preset": resolved_name, "token": token}


def build_camera_adapter(profile: CameraProfilePayload) -> CameraAdapter:
    if profile.kind == "mock":
        return MockCameraAdapter(profile)
    return RtspOnvifCameraAdapter(profile)
