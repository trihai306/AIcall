const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  getBackendUrl: () => ipcRenderer.invoke('backend-url'),
  getWsUrl: () => ipcRenderer.invoke('ws-url'),
  checkHealth: () => ipcRenderer.invoke('health'),
  getProjectDir: () => ipcRenderer.invoke('project-dir'),
  getMissingFiles: () => ipcRenderer.invoke('missing-files'),
  openLogs: () => ipcRenderer.invoke('open-logs'),
  restartServices: () => ipcRenderer.invoke('restart-services'),
  selectFile: (f) => ipcRenderer.invoke('select-file', f),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  onLog: (cb) => ipcRenderer.on('log', (_, msg) => cb(msg)),
});
