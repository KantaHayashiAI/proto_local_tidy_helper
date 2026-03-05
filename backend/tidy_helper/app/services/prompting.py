from __future__ import annotations

import json
from collections.abc import Iterable


def schema_prompt(schema_name: str, schema: dict[str, object]) -> str:
    return (
        f"Return JSON only for schema '{schema_name}'. "
        "Do not wrap it in markdown. Follow the schema exactly.\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}"
    )


def build_scene_prompt(
    *,
    recent_history: Iterable[dict[str, object]],
    active_tasks: Iterable[dict[str, object]],
    rules: Iterable[dict[str, object]],
    quiet_hours_active: bool,
    notifications_today: int,
) -> tuple[str, str]:
    system = (
        "You are a compassionate tidy coach for someone who struggles to start cleaning. "
        "Prioritize the smallest realistic next action, avoid blame, and keep suggestions concrete."
    )
    user = {
        "recent_history": list(recent_history),
        "active_tasks": list(active_tasks),
        "rules": list(rules),
        "quiet_hours_active": quiet_hours_active,
        "notifications_today": notifications_today,
        "instructions": [
            "Describe the room state visible in the image.",
            "Estimate clutter on a 0-10 scale.",
            "Propose at most three tasks and order them by practical impact.",
            "The first task should be doable in under ten minutes.",
            "Include a short praise message that never sounds patronizing."
        ],
    }
    return system, json.dumps(user, ensure_ascii=False, indent=2)


def build_completion_prompt(
    *,
    task: dict[str, object],
    reference_summary: str | None,
) -> tuple[str, str]:
    system = (
        "You compare a previous room state and a new room state to judge whether the requested tidy task was completed."
    )
    user = {
        "task": task,
        "reference_summary": reference_summary,
        "instructions": [
            "Mark done only when the requested visual change is clearly visible.",
            "Use pending when the task clearly remains.",
            "Use uncertain when the image is ambiguous or partially occluded."
        ],
    }
    return system, json.dumps(user, ensure_ascii=False, indent=2)
