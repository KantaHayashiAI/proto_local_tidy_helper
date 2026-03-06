from __future__ import annotations

import base64
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, TypeVar

import httpx
from openai import OpenAI
from pydantic import BaseModel

from tidy_helper.app.config import AppConfig
from tidy_helper.app.schemas import (
    CompletionAssessmentResult,
    SceneAnalysisResult,
    SettingsPayload,
)
from tidy_helper.app.services.prompting import (
    build_completion_prompt,
    build_scene_prompt,
    schema_prompt,
)

SchemaModel = TypeVar("SchemaModel", bound=BaseModel)


class VisionError(RuntimeError):
    pass


class ResponsesUnsupportedError(VisionError):
    pass


class VisionProvider(ABC):
    def __init__(self, name: str, model_name: str) -> None:
        self.name = name
        self.model_name = model_name

    @abstractmethod
    def analyze_scene(
        self,
        *,
        image_path: Path,
        recent_history: list[dict[str, object]],
        active_tasks: list[dict[str, object]],
        rules: list[dict[str, object]],
        quiet_hours_active: bool,
        notifications_today: int,
    ) -> SceneAnalysisResult:
        raise NotImplementedError

    @abstractmethod
    def check_completion(
        self,
        *,
        image_path: Path,
        task: dict[str, object],
        reference_summary: str | None,
    ) -> CompletionAssessmentResult:
        raise NotImplementedError

    @abstractmethod
    def healthcheck(self) -> dict[str, object]:
        raise NotImplementedError


class DeterministicVisionProvider(VisionProvider):
    def __init__(self) -> None:
        super().__init__("local", "deterministic-mock")

    def analyze_scene(
        self,
        *,
        image_path: Path,
        recent_history: list[dict[str, object]],
        active_tasks: list[dict[str, object]],
        rules: list[dict[str, object]],
        quiet_hours_active: bool,
        notifications_today: int,
    ) -> SceneAnalysisResult:
        del recent_history, active_tasks, rules, quiet_hours_active, notifications_today
        size_hint = image_path.stat().st_size
        clutter = 6.0 if size_hint % 2 else 4.0
        return SceneAnalysisResult(
            scene_summary="机まわりに日用品と容器が残っており、手前から片付けると改善しやすい状態です。",
            clutter_score=clutter,
            tasks=[
                {
                    "title": "手前の容器を1つだけ片付ける",
                    "instruction": "机のいちばん手前にある容器を1つだけ台所かゴミ箱に移してください。",
                    "reason": "視界の中心が少しでも空くと次の行動に入りやすくなります。",
                    "priority": 5,
                    "confidence": 0.72,
                    "estimated_minutes": 3,
                    "expected_visual_change": "机の手前の面積が少し広く見える",
                },
                {
                    "title": "紙類を1か所に束ねる",
                    "instruction": "散らばっている紙を重ねて机の端に寄せてください。",
                    "reason": "細かい紙が減ると散らかり感が大きく下がります。",
                    "priority": 3,
                    "confidence": 0.64,
                    "estimated_minutes": 4,
                    "expected_visual_change": "紙が1か所にまとまり、平らな面が見える",
                },
            ],
            praise="一度に全部ではなく、一手ずつ進めれば十分です。",
            provider_meta={"mode": "deterministic"},
        )

    def check_completion(
        self,
        *,
        image_path: Path,
        task: dict[str, object],
        reference_summary: str | None,
    ) -> CompletionAssessmentResult:
        del image_path, task, reference_summary
        return CompletionAssessmentResult(
            status="uncertain",
            confidence=0.4,
            reason="モックプロバイダのため自動完了判定は保守的に uncertain を返します。",
        )

    def healthcheck(self) -> dict[str, object]:
        return {"mode": "mock", "status": "ready"}


class JsonRetryingProvider(VisionProvider, ABC):
    def _image_data_url(self, image_path: Path) -> str:
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        suffix = image_path.suffix.lower().lstrip(".") or "jpeg"
        return f"data:image/{suffix};base64,{encoded}"

    def _parse_json(self, raw_text: str) -> dict[str, Any]:
        raw_text = raw_text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return json.loads(raw_text)

    def _strip_code_fence(self, raw_text: str) -> str:
        raw_text = raw_text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return raw_text

    def _validate_response(
        self,
        *,
        schema_model: type[SchemaModel],
        schema_name: str,
        schema: dict[str, object],
        generator,
    ) -> SchemaModel:
        last_error: Exception | None = None
        prompt_suffix = schema_prompt(schema_name, schema)
        for attempt in range(3):
            raw_text = generator(prompt_suffix, attempt, last_error)
            try:
                payload = self._parse_json(raw_text)
                return schema_model.model_validate(payload)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        raise VisionError(f"schema validation failed after retries: {last_error}") from last_error


class OpenAIResponsesVisionProvider(JsonRetryingProvider):
    def __init__(self, *, api_key: str, model_name: str) -> None:
        super().__init__("openai", model_name)
        self.client = OpenAI(api_key=api_key, timeout=30.0)

    def _run(self, *, image_path: Path, system_prompt: str, user_prompt: str, schema_text: str) -> str:
        response = self.client.responses.create(
            model=self.model_name,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": f"{system_prompt}\n\n{schema_text}"}],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": user_prompt},
                        {"type": "input_image", "image_url": self._image_data_url(image_path)},
                    ],
                },
            ],
        )
        return response.output_text

    def analyze_scene(
        self,
        *,
        image_path: Path,
        recent_history: list[dict[str, object]],
        active_tasks: list[dict[str, object]],
        rules: list[dict[str, object]],
        quiet_hours_active: bool,
        notifications_today: int,
    ) -> SceneAnalysisResult:
        system_prompt, user_prompt = build_scene_prompt(
            recent_history=recent_history,
            active_tasks=active_tasks,
            rules=rules,
            quiet_hours_active=quiet_hours_active,
            notifications_today=notifications_today,
        )
        return self._validate_response(
            schema_model=SceneAnalysisResult,
            schema_name="SceneAnalysisResult",
            schema=SceneAnalysisResult.model_json_schema(),
            generator=lambda schema_text, _attempt, _error: self._run(
                image_path=image_path,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_text=schema_text,
            ),
        )

    def check_completion(
        self,
        *,
        image_path: Path,
        task: dict[str, object],
        reference_summary: str | None,
    ) -> CompletionAssessmentResult:
        system_prompt, user_prompt = build_completion_prompt(
            task=task, reference_summary=reference_summary
        )
        return self._validate_response(
            schema_model=CompletionAssessmentResult,
            schema_name="CompletionAssessmentResult",
            schema=CompletionAssessmentResult.model_json_schema(),
            generator=lambda schema_text, _attempt, _error: self._run(
                image_path=image_path,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_text=schema_text,
            ),
        )

    def healthcheck(self) -> dict[str, object]:
        return {"provider": self.name, "model": self.model_name, "configured": True}


class OpenAICompatibleVisionProvider(JsonRetryingProvider):
    def __init__(
        self,
        *,
        provider_name: str,
        base_url: str,
        model_name: str,
        api_key: str | None = None,
        extra_headers: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__(provider_name, model_name)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.extra_headers = extra_headers or {}
        self.client = httpx.Client(timeout=timeout_seconds)

    def _run(self, *, image_path: Path, system_prompt: str, user_prompt: str, schema_text: str) -> str:
        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model_name,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": f"{system_prompt}\n\n{schema_text}"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": self._image_data_url(image_path)}},
                    ],
                },
            ],
        }
        response = self.client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):
            return "".join(part.get("text", "") for part in content if isinstance(part, dict))
        return content

    def _parse_json(self, raw_text: str) -> dict[str, Any]:
        cleaned_text = self._strip_code_fence(raw_text)
        cleaned_text = self._strip_think_blocks(cleaned_text)
        try:
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            pass

        for candidate in self._extract_json_candidates(cleaned_text):
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload

        raise json.JSONDecodeError("No JSON object found in response", cleaned_text, 0)

    def _strip_think_blocks(self, raw_text: str) -> str:
        cleaned = raw_text
        while True:
            start = cleaned.find("<think>")
            if start == -1:
                break
            end = cleaned.find("</think>", start)
            if end == -1:
                cleaned = cleaned[:start]
                break
            cleaned = f"{cleaned[:start]}{cleaned[end + len('</think>'):]}"
        return cleaned.strip()

    def _extract_json_candidates(self, raw_text: str) -> list[str]:
        candidates: list[str] = []
        for opening, closing in (("{", "}"), ("[", "]")):
            candidates.extend(self._extract_balanced_candidates(raw_text, opening, closing))
        return sorted(set(candidates), key=len, reverse=True)

    def _extract_balanced_candidates(
        self,
        raw_text: str,
        opening: str,
        closing: str,
    ) -> list[str]:
        candidates: list[str] = []
        for start in (index for index, char in enumerate(raw_text) if char == opening):
            depth = 0
            in_string = False
            escaping = False
            for index in range(start, len(raw_text)):
                char = raw_text[index]
                if escaping:
                    escaping = False
                    continue
                if char == "\\" and in_string:
                    escaping = True
                    continue
                if char == "\"":
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == opening:
                    depth += 1
                elif char == closing:
                    depth -= 1
                    if depth == 0:
                        candidates.append(raw_text[start : index + 1])
                        break
        return candidates

    def analyze_scene(
        self,
        *,
        image_path: Path,
        recent_history: list[dict[str, object]],
        active_tasks: list[dict[str, object]],
        rules: list[dict[str, object]],
        quiet_hours_active: bool,
        notifications_today: int,
    ) -> SceneAnalysisResult:
        system_prompt, user_prompt = build_scene_prompt(
            recent_history=recent_history,
            active_tasks=active_tasks,
            rules=rules,
            quiet_hours_active=quiet_hours_active,
            notifications_today=notifications_today,
        )
        return self._validate_response(
            schema_model=SceneAnalysisResult,
            schema_name="SceneAnalysisResult",
            schema=SceneAnalysisResult.model_json_schema(),
            generator=lambda schema_text, _attempt, _error: self._run(
                image_path=image_path,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_text=schema_text,
            ),
        )

    def check_completion(
        self,
        *,
        image_path: Path,
        task: dict[str, object],
        reference_summary: str | None,
    ) -> CompletionAssessmentResult:
        system_prompt, user_prompt = build_completion_prompt(
            task=task, reference_summary=reference_summary
        )
        return self._validate_response(
            schema_model=CompletionAssessmentResult,
            schema_name="CompletionAssessmentResult",
            schema=CompletionAssessmentResult.model_json_schema(),
            generator=lambda schema_text, _attempt, _error: self._run(
                image_path=image_path,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_text=schema_text,
            ),
        )

    def healthcheck(self) -> dict[str, object]:
        if self.base_url.startswith("mock://"):
            return {"provider": self.name, "mode": "mock"}
        try:
            response = self.client.get(f"{self.base_url}/models")
            response.raise_for_status()
            return {"provider": self.name, "reachable": True}
        except Exception as exc:  # noqa: BLE001
            raise VisionError(f"{self.name} endpoint healthcheck failed: {exc}") from exc


class OpenAICompatibleResponsesVisionProvider(JsonRetryingProvider):
    def __init__(
        self,
        *,
        provider_name: str,
        base_url: str,
        model_name: str,
        api_key: str | None = None,
        extra_headers: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__(provider_name, model_name)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.extra_headers = extra_headers or {}
        self.client = httpx.Client(timeout=timeout_seconds)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _extract_output_text(self, payload: dict[str, Any]) -> str:
        chunks: list[str] = []
        for item in payload.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    chunks.append(content.get("text", ""))
        return "".join(chunks)

    def _run(self, *, image_path: Path, system_prompt: str, user_prompt: str, schema_text: str) -> str:
        payload = {
            "model": self.model_name,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": f"{system_prompt}\n\n{schema_text}"}],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": user_prompt},
                        {"type": "input_image", "image_url": self._image_data_url(image_path)},
                    ],
                },
            ],
        }
        response = self.client.post(f"{self.base_url}/responses", headers=self._headers(), json=payload)
        if response.status_code in {404, 405, 501}:
            raise ResponsesUnsupportedError(
                f"{self.name} endpoint does not support /responses (status={response.status_code})"
            )
        response.raise_for_status()
        data = response.json()
        output_text = self._extract_output_text(data).strip()
        if not output_text:
            raise VisionError(f"{self.name} /responses returned empty output_text")
        return output_text

    def analyze_scene(
        self,
        *,
        image_path: Path,
        recent_history: list[dict[str, object]],
        active_tasks: list[dict[str, object]],
        rules: list[dict[str, object]],
        quiet_hours_active: bool,
        notifications_today: int,
    ) -> SceneAnalysisResult:
        system_prompt, user_prompt = build_scene_prompt(
            recent_history=recent_history,
            active_tasks=active_tasks,
            rules=rules,
            quiet_hours_active=quiet_hours_active,
            notifications_today=notifications_today,
        )
        return self._validate_response(
            schema_model=SceneAnalysisResult,
            schema_name="SceneAnalysisResult",
            schema=SceneAnalysisResult.model_json_schema(),
            generator=lambda schema_text, _attempt, _error: self._run(
                image_path=image_path,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_text=schema_text,
            ),
        )

    def check_completion(
        self,
        *,
        image_path: Path,
        task: dict[str, object],
        reference_summary: str | None,
    ) -> CompletionAssessmentResult:
        system_prompt, user_prompt = build_completion_prompt(
            task=task, reference_summary=reference_summary
        )
        return self._validate_response(
            schema_model=CompletionAssessmentResult,
            schema_name="CompletionAssessmentResult",
            schema=CompletionAssessmentResult.model_json_schema(),
            generator=lambda schema_text, _attempt, _error: self._run(
                image_path=image_path,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_text=schema_text,
            ),
        )

    def healthcheck(self) -> dict[str, object]:
        if self.base_url.startswith("mock://"):
            return {"provider": self.name, "mode": "mock"}
        try:
            response = self.client.get(f"{self.base_url}/models", headers=self._headers())
            response.raise_for_status()
            return {"provider": self.name, "reachable": True}
        except Exception as exc:  # noqa: BLE001
            raise VisionError(f"{self.name} endpoint healthcheck failed: {exc}") from exc


class PreferResponsesVisionProvider(VisionProvider):
    def __init__(
        self,
        *,
        primary: OpenAICompatibleResponsesVisionProvider,
        fallback: OpenAICompatibleVisionProvider,
    ) -> None:
        super().__init__(primary.name, primary.model_name)
        self.primary = primary
        self.fallback = fallback

    def analyze_scene(
        self,
        *,
        image_path: Path,
        recent_history: list[dict[str, object]],
        active_tasks: list[dict[str, object]],
        rules: list[dict[str, object]],
        quiet_hours_active: bool,
        notifications_today: int,
    ) -> SceneAnalysisResult:
        try:
            return self.primary.analyze_scene(
                image_path=image_path,
                recent_history=recent_history,
                active_tasks=active_tasks,
                rules=rules,
                quiet_hours_active=quiet_hours_active,
                notifications_today=notifications_today,
            )
        except ResponsesUnsupportedError:
            return self.fallback.analyze_scene(
                image_path=image_path,
                recent_history=recent_history,
                active_tasks=active_tasks,
                rules=rules,
                quiet_hours_active=quiet_hours_active,
                notifications_today=notifications_today,
            )

    def check_completion(
        self,
        *,
        image_path: Path,
        task: dict[str, object],
        reference_summary: str | None,
    ) -> CompletionAssessmentResult:
        try:
            return self.primary.check_completion(
                image_path=image_path,
                task=task,
                reference_summary=reference_summary,
            )
        except ResponsesUnsupportedError:
            return self.fallback.check_completion(
                image_path=image_path,
                task=task,
                reference_summary=reference_summary,
            )

    def healthcheck(self) -> dict[str, object]:
        return self.primary.healthcheck()


def build_vision_provider(settings: SettingsPayload, config: AppConfig) -> VisionProvider:
    if settings.ai_provider == "openai":
        if not config.openai_api_key:
            raise VisionError("OPENAI_API_KEY is not configured")
        return OpenAIResponsesVisionProvider(
            api_key=config.openai_api_key,
            model_name=settings.openai_model or config.default_openai_model,
        )

    if settings.ai_provider == "openrouter":
        if not config.openrouter_api_key:
            raise VisionError("OPENROUTER_API_KEY is not configured")
        return OpenAICompatibleVisionProvider(
            provider_name="openrouter",
            base_url="https://openrouter.ai/api/v1",
            model_name=settings.openrouter_model or config.default_openrouter_model,
            api_key=config.openrouter_api_key,
            extra_headers={"HTTP-Referer": "https://github.com/KantaHayashiAI/proto_local_tidy_helper"},
        )

    base_url = settings.local_base_url or config.default_local_base_url
    if base_url.startswith("mock://"):
        return DeterministicVisionProvider()
    return PreferResponsesVisionProvider(
        primary=OpenAICompatibleResponsesVisionProvider(
            provider_name="local",
            base_url=base_url,
            model_name=settings.local_model or config.default_local_model,
            timeout_seconds=180.0,
        ),
        fallback=OpenAICompatibleVisionProvider(
            provider_name="local",
            base_url=base_url,
            model_name=settings.local_model or config.default_local_model,
            timeout_seconds=180.0,
        ),
    )
