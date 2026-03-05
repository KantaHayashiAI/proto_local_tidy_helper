import { test, expect } from "@playwright/test";

test("dashboard renders mocked backend state", async ({ page }) => {
  await page.addInitScript(() => {
    class MockSocket {
      onmessage: ((event: { data: string }) => void) | null = null;
      onopen: (() => void) | null = null;
      constructor() {
        setTimeout(() => this.onopen?.(), 0);
      }
      close() {}
      send() {}
    }
    // @ts-expect-error test shim
    window.WebSocket = MockSocket;
    // @ts-expect-error test shim
    window.desktop = {
      shellInfo: async () => ({
        platform: "win32",
        appVersion: "0.1.0",
        isPackaged: false,
        dataDirectory: "C:/tmp",
        backendUrl: "http://127.0.0.1:8765"
      }),
      openDataDirectory: async () => ({ ok: true }),
      showNotification: async () => ({ ok: true }),
      runCaptureNow: async () => ({
        observation_id: 1,
        notified_task_id: 1,
        message: "観測と分析を完了しました。"
      }),
      onShellStatus: () => () => {}
    };
  });

  await page.route("http://127.0.0.1:8765/api/**", async (route) => {
    const url = route.request().url();
    if (url.endsWith("/api/state")) {
      await route.fulfill({
        json: {
          settings: {
            locale: "ja",
            ai_provider: "local",
            local_base_url: "mock://local-vlm",
            local_model: "deterministic-mock",
            openai_model: "gpt-4.1-mini",
            openrouter_model: "qwen/qwen3.5-397b-a17b",
            capture_interval_minutes: 120,
            quiet_hours_start: "23:00",
            quiet_hours_end: "08:00",
            notification_cooldown_minutes: 30,
            notification_daily_limit: 5
          },
          camera_profile: null,
          masks: [],
          rules: [],
          active_tasks: [
            {
              id: 1,
              title: "コップを1つ戻す",
              instruction: "机の手前にあるコップをキッチンに戻してください。",
              reason: "目に入る散らかりを最短で減らせます。",
              priority: 5,
              confidence: 0.8,
              estimated_minutes: 3,
              expected_visual_change: "机の手前が少し広く見える",
              status: "active",
              snoozed_until: null,
              created_at: "2026-03-06T00:00:00"
            }
          ],
          last_observation: null,
          next_run_at: null,
          quiet_hours_active: false,
          storage_usage_bytes: 1024,
          storage_usage_human: "1.0 KB",
          notifications_today: 1
        }
      });
      return;
    }
    if (url.endsWith("/api/history")) {
      await route.fulfill({ json: [] });
      return;
    }
    if (url.endsWith("/api/diagnostics")) {
      await route.fulfill({
        json: [
          {
            check_name: "camera.healthcheck",
            status: "ok",
            message: "カメラ接続を確認しました。",
            details: {},
            created_at: "2026-03-06T00:00:00"
          }
        ]
      });
      return;
    }
    await route.fulfill({ json: { ok: true } });
  });

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "部屋が、そっと声をかける" })).toBeVisible();
  await expect(page.getByText("コップを1つ戻す")).toBeVisible();
  await expect(page.getByText("カメラ接続を確認しました。")).toBeVisible();
});
