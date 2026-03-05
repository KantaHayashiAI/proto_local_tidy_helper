const { app, BrowserWindow, Tray, Menu, Notification, ipcMain, shell } = require("electron");
const path = require("node:path");
const fs = require("node:fs");
const { spawn } = require("node:child_process");
const { getTrayIconDataUrl } = require("./tray-icon");

const BACKEND_PORT = 8765;
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;

let mainWindow = null;
let tray = null;
let isQuitting = false;
let backendProcess = null;

function sendShellStatus(status) {
  BrowserWindow.getAllWindows().forEach((window) => {
    window.webContents.send("shell:status", status);
  });
}

function resolveBackendRoot() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "backend");
  }
  return path.join(app.getAppPath(), "backend");
}

function resolveEnvFile() {
  if (app.isPackaged) {
    return path.join(process.cwd(), ".env");
  }
  return path.join(app.getAppPath(), ".env");
}

function startBackend() {
  const backendRoot = resolveBackendRoot();
  const env = {
    ...process.env,
    MITOU_TIDY_APPDATA: path.join(app.getPath("userData"), "data"),
    MITOU_TIDY_ENV_FILE: resolveEnvFile(),
    MITOU_TIDY_PORT: String(BACKEND_PORT)
  };

  const bundledExecutable = path.join(backendRoot, "dist", "mitou-tidy-backend.exe");
  const command = fs.existsSync(bundledExecutable) ? bundledExecutable : "uv";
  const args = fs.existsSync(bundledExecutable)
    ? []
    : ["run", "--project", backendRoot, "python", "-m", "tidy_helper.app.main"];

  backendProcess = spawn(command, args, {
    cwd: backendRoot,
    env,
    windowsHide: true
  });

  backendProcess.stdout.on("data", (chunk) => {
    sendShellStatus({ stream: "stdout", message: chunk.toString() });
  });
  backendProcess.stderr.on("data", (chunk) => {
    sendShellStatus({ stream: "stderr", message: chunk.toString() });
  });
  backendProcess.on("exit", (code) => {
    sendShellStatus({ stream: "lifecycle", message: `backend exited (${code ?? "unknown"})` });
  });
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1480,
    height: 980,
    minWidth: 1180,
    minHeight: 840,
    backgroundColor: "#09131b",
    title: "Mitou Local Tidy Helper",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  const devUrl = process.env.VITE_DEV_SERVER_URL;
  if (devUrl) {
    mainWindow.loadURL(devUrl);
  } else {
    mainWindow.loadFile(path.join(app.getAppPath(), "dist", "index.html"));
  }

  mainWindow.on("close", (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
}

function createTray() {
  tray = new Tray(nativeImageFromSvg());
  tray.setToolTip("Mitou Local Tidy Helper");
  tray.on("double-click", () => {
    mainWindow.show();
    mainWindow.focus();
  });

  const buildMenu = () =>
    Menu.buildFromTemplate([
      {
        label: "ダッシュボードを開く",
        click: () => {
          mainWindow.show();
          mainWindow.focus();
        }
      },
      {
        label: "今すぐ観測を実行",
        click: async () => {
          await triggerCapture();
        }
      },
      {
        label: "データフォルダを開く",
        click: async () => {
          const dataDir = path.join(app.getPath("userData"), "data");
          await shell.openPath(dataDir);
        }
      },
      { type: "separator" },
      {
        label: "終了",
        click: () => {
          isQuitting = true;
          app.quit();
        }
      }
    ]);

  tray.setContextMenu(buildMenu());
}

function nativeImageFromSvg() {
  const { nativeImage } = require("electron");
  return nativeImage.createFromDataURL(getTrayIconDataUrl());
}

async function triggerCapture() {
  const response = await fetch(`${BACKEND_URL}/api/captures/run-now`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`capture failed: ${response.status}`);
  }
  return response.json();
}

app.whenReady().then(() => {
  const lock = app.requestSingleInstanceLock();
  if (!lock) {
    app.quit();
    return;
  }

  app.on("second-instance", () => {
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });

  startBackend();
  createMainWindow();
  createTray();
});

app.on("before-quit", () => {
  isQuitting = true;
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill();
  }
});

ipcMain.handle("shell:info", () => ({
  platform: process.platform,
  appVersion: app.getVersion(),
  isPackaged: app.isPackaged,
  dataDirectory: path.join(app.getPath("userData"), "data"),
  backendUrl: BACKEND_URL
}));

ipcMain.handle("shell:open-data-directory", async () => {
  const dataDir = path.join(app.getPath("userData"), "data");
  await fs.promises.mkdir(dataDir, { recursive: true });
  await shell.openPath(dataDir);
  return { ok: true };
});

ipcMain.handle("shell:notify", async (_event, payload) => {
  const notification = new Notification({
    title: payload.title ?? "Mitou Local Tidy Helper",
    body: payload.body ?? "",
    silent: false
  });
  notification.on("click", () => {
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });
  notification.show();
  return { ok: true };
});

ipcMain.handle("shell:run-capture-now", async () => triggerCapture());
