export type ProviderKind = "local" | "openai" | "openrouter";
export type CameraKind = "rtsp_onvif" | "mock";

export type MaskRegion = {
  id?: number;
  name: string;
  x: number;
  y: number;
  width: number;
  height: number;
  enabled: boolean;
};

export type MemoryRule = {
  id?: number;
  kind: "ignore_object" | "note" | "quiet_hours";
  title: string;
  content: string;
  enabled: boolean;
};

export type CameraProfile = {
  id?: number;
  kind: CameraKind;
  name: string;
  rtsp_url: string;
  onvif_host: string;
  onvif_port: number;
  username: string;
  password: string;
  observe_preset: string;
  privacy_preset: string;
  mock_image_dir: string;
  active: boolean;
};

export type Settings = {
  locale: string;
  ai_provider: ProviderKind;
  local_base_url: string;
  local_model: string;
  openai_model: string;
  openrouter_model: string;
  capture_interval_minutes: number;
  quiet_hours_start: string;
  quiet_hours_end: string;
  notification_cooldown_minutes: number;
  notification_daily_limit: number;
};

export type ActiveTask = {
  id: number;
  title: string;
  instruction: string;
  reason: string;
  priority: number;
  confidence: number;
  estimated_minutes: number;
  expected_visual_change: string;
  status: string;
  snoozed_until?: string | null;
  created_at: string;
};

export type HistoryItem = {
  observation_id: number;
  captured_at: string;
  source: string;
  image_url?: string | null;
  masked_image_url?: string | null;
  thumbnail_url?: string | null;
  width: number;
  height: number;
  provider?: string | null;
  scene_summary?: string | null;
  clutter_score?: number | null;
  praise?: string | null;
  tasks: ActiveTask[];
};

export type DiagnosticCheck = {
  check_name: string;
  status: "ok" | "warning" | "error";
  message: string;
  details?: Record<string, unknown>;
  created_at: string;
};

export type DashboardState = {
  settings: Settings;
  camera_profile: CameraProfile | null;
  masks: MaskRegion[];
  rules: MemoryRule[];
  active_tasks: ActiveTask[];
  last_observation: HistoryItem | null;
  next_run_at: string | null;
  quiet_hours_active: boolean;
  storage_usage_bytes: number;
  storage_usage_human: string;
  notifications_today: number;
};

export type ValidateCameraResult = {
  ok: boolean;
  details: Record<string, unknown>;
};

export type CaptureRunResult = {
  observation_id: number | null;
  notified_task_id: number | null;
  message: string;
};

export type WebSocketMessage =
  | { type: "state"; payload: { reason: string } }
  | { type: "notification"; payload: { title: string; body: string; task_id?: number } };

declare global {
  interface Window {
    desktop?: {
      shellInfo: () => Promise<{
        platform: string;
        appVersion: string;
        isPackaged: boolean;
        dataDirectory: string;
        backendUrl: string;
      }>;
      openDataDirectory: () => Promise<{ ok: boolean }>;
      showNotification: (payload: { title: string; body: string }) => Promise<{ ok: boolean }>;
      runCaptureNow: () => Promise<CaptureRunResult>;
      onShellStatus: (callback: (payload: { stream: string; message: string }) => void) => () => void;
    };
  }
}
