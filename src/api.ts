import type {
  CaptureRunResult,
  CameraProfile,
  DashboardState,
  DiagnosticCheck,
  HistoryItem,
  MaskRegion,
  MemoryRule,
  Settings,
  ValidateCameraResult,
  WebSocketMessage
} from "./types";

const API_ROOT = "http://127.0.0.1:8765";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    headers: {
      "Content-Type": "application/json"
    },
    ...options
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function fetchState() {
  return request<DashboardState>("/api/state");
}

export async function fetchHistory() {
  return request<HistoryItem[]>("/api/history");
}

export async function fetchDiagnostics() {
  return request<DiagnosticCheck[]>("/api/diagnostics");
}

export async function validateCamera(profile: CameraProfile) {
  return request<ValidateCameraResult>("/api/setup/validate-camera", {
    method: "POST",
    body: JSON.stringify({ profile })
  });
}

export async function savePreset(profile: CameraProfile, preset_name: "observe" | "privacy") {
  return request<{ ok: boolean; profile: CameraProfile }>("/api/setup/save-presets", {
    method: "POST",
    body: JSON.stringify({ profile, preset_name })
  });
}

export async function runCaptureNow() {
  return request<CaptureRunResult>("/api/captures/run-now", {
    method: "POST"
  });
}

export async function patchSettings(payload: {
  settings: Settings;
  camera_profile: CameraProfile | null;
  mask_regions: MaskRegion[];
}) {
  return request<DashboardState>("/api/settings", {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function upsertRule(rule: MemoryRule) {
  return request<MemoryRule>("/api/rules", {
    method: "POST",
    body: JSON.stringify(rule)
  });
}

export function connectWebSocket(onMessage: (message: WebSocketMessage) => void) {
  const socket = new WebSocket("ws://127.0.0.1:8765/ws");
  socket.onmessage = (event) => {
    const data = JSON.parse(event.data) as WebSocketMessage;
    onMessage(data);
  };
  return socket;
}
