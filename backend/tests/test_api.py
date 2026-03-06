from __future__ import annotations


def test_end_to_end_mock_capture_flow(client):
    test_client, image_dir, _app_data = client

    response = test_client.patch(
        "/api/settings",
        json={
            "settings": {
                "locale": "ja",
                "ai_provider": "local",
                "local_base_url": "mock://local-vlm",
                "local_model": "deterministic-mock",
                "openai_model": "gpt-4.1-mini",
                "openrouter_model": "qwen/qwen3.5-397b-a17b",
                "capture_interval_minutes": 120,
                "quiet_hours_start": "23:00",
                "quiet_hours_end": "08:00",
                "notification_cooldown_minutes": 30,
                "notification_daily_limit": 10
            },
            "camera_profile": {
                "kind": "mock",
                "name": "Fixture camera",
                "rtsp_url": "",
                "onvif_host": "",
                "onvif_port": 8000,
                "username": "",
                "password": "",
                "observe_preset": "observe",
                "privacy_preset": "privacy",
                "mock_image_dir": str(image_dir),
                "active": True
            },
            "mask_regions": [
                {
                    "name": "Desk corner",
                    "x": 0.0,
                    "y": 0.0,
                    "width": 0.1,
                    "height": 0.1,
                    "enabled": True
                }
            ]
        },
    )
    assert response.status_code == 200

    capture = test_client.post("/api/captures/run-now")
    assert capture.status_code == 200
    body = capture.json()
    assert body["observation_id"] is not None

    state = test_client.get("/api/state")
    assert state.status_code == 200
    assert state.json()["active_tasks"]
    task_id = state.json()["active_tasks"][0]["id"]
    assert "snoozed_until" not in state.json()["active_tasks"][0]

    history = test_client.get("/api/history")
    assert history.status_code == 200
    assert len(history.json()) == 1

    done = test_client.post(f"/api/tasks/{task_id}/done")
    assert done.status_code == 404

    snooze = test_client.post(f"/api/tasks/{task_id}/snooze", json={"minutes": 120})
    assert snooze.status_code == 404

    diagnostics = test_client.get("/api/diagnostics")
    assert diagnostics.status_code == 200
    assert diagnostics.json()
