const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("desktop", {
  shellInfo: () => ipcRenderer.invoke("shell:info"),
  openDataDirectory: () => ipcRenderer.invoke("shell:open-data-directory"),
  showNotification: (payload) => ipcRenderer.invoke("shell:notify", payload),
  runCaptureNow: () => ipcRenderer.invoke("shell:run-capture-now"),
  onShellStatus: (callback) => {
    const wrapped = (_event, payload) => callback(payload);
    ipcRenderer.on("shell:status", wrapped);
    return () => ipcRenderer.removeListener("shell:status", wrapped);
  }
});
