import { useEffect, useMemo, useRef, useState } from "react";
import {
  connectWebSocket,
  fetchDiagnostics,
  fetchHistory,
  fetchState,
  markTaskDone,
  patchSettings,
  runCaptureNow,
  savePreset,
  snoozeTask,
  upsertRule,
  validateCamera
} from "./api";
import { copyForLocale, type Locale } from "./i18n";
import type {
  CameraProfile,
  DashboardState,
  DiagnosticCheck,
  HistoryItem,
  MaskRegion,
  MemoryRule,
  Settings,
  WebSocketMessage
} from "./types";

const defaultSettings: Settings = {
  locale: "ja",
  ai_provider: "local",
  local_base_url: "http://127.0.0.1:8080/v1",
  local_model: "Qwen/Qwen2.5-VL-7B-Instruct",
  openai_model: "gpt-4.1-mini",
  openrouter_model: "qwen/qwen3.5-397b-a17b",
  capture_interval_minutes: 180,
  quiet_hours_start: "23:00",
  quiet_hours_end: "08:00",
  notification_cooldown_minutes: 180,
  notification_daily_limit: 4
};

const defaultCamera: CameraProfile = {
  kind: "rtsp_onvif",
  name: "My Room Camera",
  rtsp_url: "",
  onvif_host: "",
  onvif_port: 8000,
  username: "",
  password: "",
  observe_preset: "observe",
  privacy_preset: "privacy",
  mock_image_dir: "",
  active: true
};

const defaultRule: MemoryRule = {
  kind: "ignore_object",
  title: "",
  content: "",
  enabled: true
};

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json"
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function clampMask(value: number) {
  return Math.max(0, Math.min(1, value));
}

export default function App() {
  const [dashboard, setDashboard] = useState<DashboardState | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [diagnostics, setDiagnostics] = useState<DiagnosticCheck[]>([]);
  const [settingsDraft, setSettingsDraft] = useState<Settings>(defaultSettings);
  const [cameraDraft, setCameraDraft] = useState<CameraProfile>(defaultCamera);
  const [maskDrafts, setMaskDrafts] = useState<MaskRegion[]>([]);
  const [ruleDraft, setRuleDraft] = useState<MemoryRule>(defaultRule);
  const [locale, setLocale] = useState<Locale>("ja");
  const [statusMessage, setStatusMessage] = useState<string>("起動中...");
  const [busy, setBusy] = useState(false);
  const [shellLogs, setShellLogs] = useState<string[]>([]);
  const [shellInfo, setShellInfo] = useState<{
    platform: string;
    appVersion: string;
    isPackaged: boolean;
    dataDirectory: string;
    backendUrl: string;
  } | null>(null);
  const [drawingMask, setDrawingMask] = useState<MaskRegion | null>(null);
  const maskCanvasRef = useRef<HTMLDivElement | null>(null);

  const copy = useMemo(() => copyForLocale(locale), [locale]);
  const latestImage =
    dashboard?.last_observation?.masked_image_url ||
    dashboard?.last_observation?.image_url ||
    null;

  async function refreshAll() {
    const [nextState, nextHistory, nextDiagnostics] = await Promise.all([
      fetchState(),
      fetchHistory(),
      fetchDiagnostics()
    ]);
    setDashboard(nextState);
    setHistory(nextHistory);
    setDiagnostics(nextDiagnostics);
    setSettingsDraft(nextState.settings);
    setCameraDraft(nextState.camera_profile ?? defaultCamera);
    setMaskDrafts(nextState.masks);
    setLocale((nextState.settings.locale || "ja") as Locale);
  }

  useEffect(() => {
    void refreshAll()
      .then(() => setStatusMessage("準備完了"))
      .catch((error) => setStatusMessage(String(error)));

    const socket = connectWebSocket((message: WebSocketMessage) => {
      if (message.type === "state") {
        void refreshAll();
      }
      if (message.type === "notification") {
        void window.desktop?.showNotification({
          title: message.payload.title,
          body: message.payload.body
        });
        setStatusMessage(message.payload.body);
        void refreshAll();
      }
    });

    void window.desktop?.shellInfo().then(setShellInfo);
    const dispose = window.desktop?.onShellStatus((payload) => {
      setShellLogs((current) => [payload.message.trim(), ...current].slice(0, 12));
    });

    return () => {
      socket.close();
      dispose?.();
    };
  }, []);

  async function handleSaveSettings() {
    setBusy(true);
    try {
      const nextState = await patchSettings({
        settings: settingsDraft,
        camera_profile: cameraDraft,
        mask_regions: maskDrafts
      });
      setDashboard(nextState);
      setStatusMessage("設定を保存しました。");
      await refreshAll();
    } catch (error) {
      setStatusMessage(`保存に失敗しました: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleValidateCamera() {
    setBusy(true);
    try {
      const result = await validateCamera(cameraDraft);
      setStatusMessage(
        result.ok ? `カメラ診断成功: ${JSON.stringify(result.details)}` : `診断失敗: ${JSON.stringify(result.details)}`
      );
    } catch (error) {
      setStatusMessage(`診断に失敗しました: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleSavePreset(name: "observe" | "privacy") {
    setBusy(true);
    try {
      const result = await savePreset(cameraDraft, name);
      if (result.profile) {
        setCameraDraft(result.profile);
      }
      setStatusMessage(`${name} プリセットを保存しました。`);
      await refreshAll();
    } catch (error) {
      setStatusMessage(`プリセット保存に失敗しました: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleRunNow() {
    setBusy(true);
    try {
      const result = window.desktop ? await window.desktop.runCaptureNow() : await runCaptureNow();
      setStatusMessage(result.message);
      await refreshAll();
    } catch (error) {
      setStatusMessage(`観測の実行に失敗しました: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleAddRule() {
    if (!ruleDraft.title.trim() || !ruleDraft.content.trim()) {
      setStatusMessage("ルールのタイトルと内容を入力してください。");
      return;
    }
    setBusy(true);
    try {
      await upsertRule(ruleDraft);
      setRuleDraft(defaultRule);
      setStatusMessage("ルールを保存しました。");
      await refreshAll();
    } catch (error) {
      setStatusMessage(`ルール保存に失敗しました: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleDoneTask(taskId: number) {
    await markTaskDone(taskId);
    setStatusMessage("タスクを完了にしました。");
    await refreshAll();
  }

  async function handleSnoozeTask(taskId: number) {
    await snoozeTask(taskId, 120);
    setStatusMessage("2時間スヌーズしました。");
    await refreshAll();
  }

  function beginMaskDraw(event: React.MouseEvent<HTMLDivElement>) {
    if (!maskCanvasRef.current) return;
    const rect = maskCanvasRef.current.getBoundingClientRect();
    const x = clampMask((event.clientX - rect.left) / rect.width);
    const y = clampMask((event.clientY - rect.top) / rect.height);
    setDrawingMask({
      name: `Mask ${maskDrafts.length + 1}`,
      x,
      y,
      width: 0.001,
      height: 0.001,
      enabled: true
    });
  }

  function updateMaskDraw(event: React.MouseEvent<HTMLDivElement>) {
    if (!maskCanvasRef.current || !drawingMask) return;
    const rect = maskCanvasRef.current.getBoundingClientRect();
    const x = clampMask((event.clientX - rect.left) / rect.width);
    const y = clampMask((event.clientY - rect.top) / rect.height);
    const nextMask: MaskRegion = {
      ...drawingMask,
      width: Math.max(0.01, x - drawingMask.x),
      height: Math.max(0.01, y - drawingMask.y)
    };
    setDrawingMask(nextMask);
  }

  function finishMaskDraw() {
    if (!drawingMask) return;
    setMaskDrafts((current) => [...current, drawingMask]);
    setDrawingMask(null);
  }

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">MITOU LOCAL TIDY HELPER</p>
          <h1>{copy.title}</h1>
          <p className="hero-copy">{copy.subtitle}</p>
        </div>
        <div className="hero-actions">
          <button className="primary" onClick={handleRunNow} disabled={busy}>
            {copy.runNow}
          </button>
          <button className="secondary" onClick={handleSaveSettings} disabled={busy}>
            {copy.save}
          </button>
        </div>
      </header>

      <section className="status-strip">
        <div>
          <span className="strip-label">状態</span>
          <strong>{statusMessage}</strong>
        </div>
        <div>
          <span className="strip-label">次回観測</span>
          <strong>{dashboard?.next_run_at ? new Date(dashboard.next_run_at).toLocaleString() : "未設定"}</strong>
        </div>
        <div>
          <span className="strip-label">保存容量</span>
          <strong>{dashboard?.storage_usage_human ?? "0 B"}</strong>
        </div>
        <div>
          <span className="strip-label">本日の通知</span>
          <strong>{dashboard?.notifications_today ?? 0}</strong>
        </div>
      </section>

      <main className="grid">
        <section className="card span-2">
          <div className="card-head">
            <h2>{copy.setup}</h2>
            <div className="inline-actions">
              <button className="ghost" onClick={handleValidateCamera} disabled={busy}>
                {copy.validate}
              </button>
              <button className="ghost" onClick={() => handleSavePreset("observe")} disabled={busy}>
                observe保存
              </button>
              <button className="ghost" onClick={() => handleSavePreset("privacy")} disabled={busy}>
                privacy保存
              </button>
            </div>
          </div>
          <div className="form-grid">
            <label>
              UI言語
              <select
                value={locale}
                onChange={(event) => {
                  const next = event.target.value as Locale;
                  setLocale(next);
                  setSettingsDraft((current) => ({ ...current, locale: next }));
                }}
              >
                <option value="ja">日本語</option>
                <option value="en">English</option>
              </select>
            </label>
            <label>
              AIプロバイダ
              <select
                value={settingsDraft.ai_provider}
                onChange={(event) =>
                  setSettingsDraft((current) => ({
                    ...current,
                    ai_provider: event.target.value as Settings["ai_provider"]
                  }))
                }
              >
                <option value="local">Local / llama.cpp</option>
                <option value="openai">OpenAI</option>
                <option value="openrouter">OpenRouter</option>
              </select>
            </label>
            <label>
              ローカル base URL
              <input
                value={settingsDraft.local_base_url}
                onChange={(event) =>
                  setSettingsDraft((current) => ({ ...current, local_base_url: event.target.value }))
                }
              />
            </label>
            <label>
              ローカルモデル
              <input
                value={settingsDraft.local_model}
                onChange={(event) =>
                  setSettingsDraft((current) => ({ ...current, local_model: event.target.value }))
                }
              />
            </label>
            <label>
              OpenAIモデル
              <input
                value={settingsDraft.openai_model}
                onChange={(event) =>
                  setSettingsDraft((current) => ({ ...current, openai_model: event.target.value }))
                }
              />
            </label>
            <label>
              OpenRouterモデル
              <input
                value={settingsDraft.openrouter_model}
                onChange={(event) =>
                  setSettingsDraft((current) => ({ ...current, openrouter_model: event.target.value }))
                }
              />
            </label>
            <label>
              カメラ種別
              <select
                value={cameraDraft.kind}
                onChange={(event) =>
                  setCameraDraft((current) => ({
                    ...current,
                    kind: event.target.value as CameraProfile["kind"]
                  }))
                }
              >
                <option value="rtsp_onvif">RTSP + ONVIF</option>
                <option value="mock">Mock images</option>
              </select>
            </label>
            <label>
              カメラ名
              <input
                value={cameraDraft.name}
                onChange={(event) =>
                  setCameraDraft((current) => ({ ...current, name: event.target.value }))
                }
              />
            </label>
            <label>
              RTSP URL
              <input
                value={cameraDraft.rtsp_url}
                onChange={(event) =>
                  setCameraDraft((current) => ({ ...current, rtsp_url: event.target.value }))
                }
              />
            </label>
            <label>
              ONVIF Host
              <input
                value={cameraDraft.onvif_host}
                onChange={(event) =>
                  setCameraDraft((current) => ({ ...current, onvif_host: event.target.value }))
                }
              />
            </label>
            <label>
              ONVIF Port
              <input
                type="number"
                value={cameraDraft.onvif_port}
                onChange={(event) =>
                  setCameraDraft((current) => ({
                    ...current,
                    onvif_port: Number(event.target.value)
                  }))
                }
              />
            </label>
            <label>
              Username
              <input
                value={cameraDraft.username}
                onChange={(event) =>
                  setCameraDraft((current) => ({ ...current, username: event.target.value }))
                }
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={cameraDraft.password}
                onChange={(event) =>
                  setCameraDraft((current) => ({ ...current, password: event.target.value }))
                }
              />
            </label>
            <label>
              Mock画像ディレクトリ
              <input
                value={cameraDraft.mock_image_dir}
                onChange={(event) =>
                  setCameraDraft((current) => ({ ...current, mock_image_dir: event.target.value }))
                }
              />
            </label>
            <label>
              observe preset
              <input
                value={cameraDraft.observe_preset}
                onChange={(event) =>
                  setCameraDraft((current) => ({
                    ...current,
                    observe_preset: event.target.value
                  }))
                }
              />
            </label>
            <label>
              privacy preset
              <input
                value={cameraDraft.privacy_preset}
                onChange={(event) =>
                  setCameraDraft((current) => ({
                    ...current,
                    privacy_preset: event.target.value
                  }))
                }
              />
            </label>
          </div>
        </section>

        <section className="card">
          <div className="card-head">
            <h2>通知・スケジュール</h2>
            <button className="ghost" onClick={() => window.desktop?.openDataDirectory()}>
              データフォルダ
            </button>
          </div>
          <div className="form-grid compact">
            <label>
              観測間隔 (分)
              <input
                type="number"
                value={settingsDraft.capture_interval_minutes}
                onChange={(event) =>
                  setSettingsDraft((current) => ({
                    ...current,
                    capture_interval_minutes: Number(event.target.value)
                  }))
                }
              />
            </label>
            <label>
              Quiet start
              <input
                value={settingsDraft.quiet_hours_start}
                onChange={(event) =>
                  setSettingsDraft((current) => ({ ...current, quiet_hours_start: event.target.value }))
                }
              />
            </label>
            <label>
              Quiet end
              <input
                value={settingsDraft.quiet_hours_end}
                onChange={(event) =>
                  setSettingsDraft((current) => ({ ...current, quiet_hours_end: event.target.value }))
                }
              />
            </label>
            <label>
              通知クールダウン (分)
              <input
                type="number"
                value={settingsDraft.notification_cooldown_minutes}
                onChange={(event) =>
                  setSettingsDraft((current) => ({
                    ...current,
                    notification_cooldown_minutes: Number(event.target.value)
                  }))
                }
              />
            </label>
            <label>
              1日の通知上限
              <input
                type="number"
                value={settingsDraft.notification_daily_limit}
                onChange={(event) =>
                  setSettingsDraft((current) => ({
                    ...current,
                    notification_daily_limit: Number(event.target.value)
                  }))
                }
              />
            </label>
          </div>
          <div className="mini-stats">
            <div>
              <span>Quiet Hours</span>
              <strong>{dashboard?.quiet_hours_active ? "現在は通知抑制中" : "通知可能"}</strong>
            </div>
            <div>
              <span>Shell</span>
              <strong>{shellInfo ? `${shellInfo.platform} / v${shellInfo.appVersion}` : "読み込み中"}</strong>
            </div>
          </div>
        </section>

        <section className="card">
          <div className="card-head">
            <h2>{copy.tasks}</h2>
            <button className="ghost" onClick={() => downloadJson("tidy-history.json", history)}>
              履歴JSONを保存
            </button>
          </div>
          <div className="task-list">
            {dashboard?.active_tasks.length ? (
              dashboard.active_tasks.map((task) => (
                <article key={task.id} className="task-card">
                  <div>
                    <p className="task-priority">Priority {task.priority}</p>
                    <h3>{task.title}</h3>
                    <p>{task.instruction}</p>
                    <small>{task.reason}</small>
                  </div>
                  <div className="task-actions">
                    <button className="primary" onClick={() => handleDoneTask(task.id)}>
                      完了
                    </button>
                    <button className="ghost" onClick={() => handleSnoozeTask(task.id)}>
                      2h スヌーズ
                    </button>
                  </div>
                </article>
              ))
            ) : (
              <p className="empty">アクティブなタスクはありません。</p>
            )}
          </div>
        </section>

        <section className="card span-2">
          <div className="card-head">
            <h2>マスク編集</h2>
            <span className="hint">最新画像上をドラッグして黒塗り領域を追加</span>
          </div>
          <div
            className="mask-editor"
            ref={maskCanvasRef}
            onMouseDown={beginMaskDraw}
            onMouseMove={updateMaskDraw}
            onMouseUp={finishMaskDraw}
            onMouseLeave={finishMaskDraw}
          >
            {latestImage ? (
              <img src={`http://127.0.0.1:8765${latestImage}`} alt="Latest capture" />
            ) : (
              <div className="empty">まだ観測画像がありません。</div>
            )}
            {maskDrafts.map((mask, index) => (
              <div
                key={`${mask.name}-${index}`}
                className="mask-rect"
                style={{
                  left: `${mask.x * 100}%`,
                  top: `${mask.y * 100}%`,
                  width: `${mask.width * 100}%`,
                  height: `${mask.height * 100}%`
                }}
              />
            ))}
            {drawingMask && (
              <div
                className="mask-rect draft"
                style={{
                  left: `${drawingMask.x * 100}%`,
                  top: `${drawingMask.y * 100}%`,
                  width: `${drawingMask.width * 100}%`,
                  height: `${drawingMask.height * 100}%`
                }}
              />
            )}
          </div>
          <div className="mask-list">
            {maskDrafts.map((mask, index) => (
              <label key={`${mask.name}-${index}`}>
                <span>{mask.name}</span>
                <button
                  className="ghost danger"
                  onClick={() =>
                    setMaskDrafts((current) => current.filter((_, currentIndex) => currentIndex !== index))
                  }
                >
                  削除
                </button>
              </label>
            ))}
          </div>
        </section>

        <section className="card">
          <div className="card-head">
            <h2>メモリルール</h2>
            <button className="ghost" onClick={handleAddRule}>
              追加
            </button>
          </div>
          <div className="form-grid compact">
            <label>
              種別
              <select
                value={ruleDraft.kind}
                onChange={(event) =>
                  setRuleDraft((current) => ({
                    ...current,
                    kind: event.target.value as MemoryRule["kind"]
                  }))
                }
              >
                <option value="ignore_object">片付け対象外</option>
                <option value="note">メモ</option>
                <option value="quiet_hours">通知抑制メモ</option>
              </select>
            </label>
            <label>
              タイトル
              <input
                value={ruleDraft.title}
                onChange={(event) =>
                  setRuleDraft((current) => ({ ...current, title: event.target.value }))
                }
              />
            </label>
            <label className="full">
              内容
              <textarea
                value={ruleDraft.content}
                onChange={(event) =>
                  setRuleDraft((current) => ({ ...current, content: event.target.value }))
                }
              />
            </label>
          </div>
          <div className="rule-list">
            {dashboard?.rules.map((rule) => (
              <article key={rule.id} className="rule-card">
                <strong>{rule.title}</strong>
                <p>{rule.content}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="card span-2">
          <div className="card-head">
            <h2>{copy.history}</h2>
          </div>
          <div className="history-list">
            {history.map((item) => (
              <article key={item.observation_id} className="history-card">
                {item.thumbnail_url ? (
                  <img
                    src={`http://127.0.0.1:8765${item.thumbnail_url}`}
                    alt={`Observation ${item.observation_id}`}
                  />
                ) : (
                  <div className="history-thumb empty" />
                )}
                <div>
                  <p className="history-meta">
                    {new Date(item.captured_at).toLocaleString()} / clutter {item.clutter_score ?? "-"}
                  </p>
                  <h3>{item.scene_summary ?? "分析結果なし"}</h3>
                  <p>{item.praise}</p>
                  <div className="history-tags">
                    {item.tasks.map((task) => (
                      <span key={task.id}>{task.title}</span>
                    ))}
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="card">
          <div className="card-head">
            <h2>{copy.diagnostics}</h2>
            <button className="ghost" onClick={() => refreshAll()}>
              再取得
            </button>
          </div>
          <div className="diagnostics-list">
            {diagnostics.map((item, index) => (
              <article key={`${item.check_name}-${index}`} className={`diagnostic ${item.status}`}>
                <strong>{item.check_name}</strong>
                <p>{item.message}</p>
              </article>
            ))}
          </div>
          <div className="log-list">
            {shellLogs.map((line, index) => (
              <code key={`${line}-${index}`}>{line}</code>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
