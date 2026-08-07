const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

let mainWindow = null;
let backendProcess = null;
const PORT = 8000;
const isDev = process.argv.includes('--dev');

const projectDir = path.resolve(__dirname, '..');
const venvBin = process.platform === 'win32' ? 'Scripts' : 'bin';
const pythonExe = path.join(projectDir, '.venv', venvBin, process.platform === 'win32' ? 'python.exe' : 'python3');

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1000,
    minHeight: 700,
    title: 'VoiceBank AI',
    backgroundColor: '#06080f',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    trafficLightPosition: { x: 14, y: 14 },
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.on('ready-to-show', () => mainWindow.show());
  mainWindow.on('closed', () => { mainWindow = null; });

  if (isDev) mainWindow.webContents.openDevTools({ mode: 'right' });
}

// --- Backend ---
function startBackend() {
  if (backendProcess) return;
  console.log('[Backend] Starting...', pythonExe);

  backendProcess = spawn(pythonExe, [
    '-m', 'uvicorn', 'backend.main:app',
    '--host', '127.0.0.1',
    '--port', String(PORT),
    '--log-level', 'info',
  ], {
    cwd: projectDir,
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
    stdio: ['pipe', 'pipe', 'pipe'],
  });

  backendProcess.stdout.on('data', (d) => {
    const msg = d.toString().trim();
    if (msg) {
      console.log('[srv]', msg);
      if (mainWindow) mainWindow.webContents.send('log', msg);
    }
  });
  backendProcess.stderr.on('data', (d) => {
    const msg = d.toString().trim();
    if (msg) {
      console.log('[srv]', msg);
      if (mainWindow) mainWindow.webContents.send('log', msg);
    }
  });
  backendProcess.on('exit', (code) => {
    console.log('[Backend] exited', code);
    backendProcess = null;
  });
}

function stopBackend() {
  if (!backendProcess) return;
  backendProcess.kill('SIGTERM');
  backendProcess = null;
}

function checkBackend() {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${PORT}/api/health`, (res) => {
      let body = '';
      res.on('data', (d) => body += d);
      res.on('end', () => { try { resolve(JSON.parse(body)); } catch { resolve(null); } });
    });
    req.on('error', () => resolve(null));
    req.setTimeout(2000, () => { req.destroy(); resolve(null); });
  });
}

async function waitBackend(maxWait = 60) {
  const deadline = Date.now() + maxWait * 1000;
  while (Date.now() < deadline) {
    const h = await checkBackend();
    if (h) return h;
    await new Promise(r => setTimeout(r, 1000));
  }
  return null;
}

// --- IPC ---
ipcMain.handle('backend-url', () => `http://127.0.0.1:${PORT}`);
ipcMain.handle('ws-url', () => `ws://127.0.0.1:${PORT}`);
ipcMain.handle('health', () => checkBackend());
ipcMain.handle('project-dir', () => projectDir);

ipcMain.handle('select-file', async (_, filters) => {
  const r = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: filters || [{ name: 'Audio', extensions: ['wav', 'mp3'] }],
  });
  return r.filePaths[0] || null;
});

ipcMain.handle('open-external', (_, url) => shell.openExternal(url));

// --- App lifecycle ---
app.whenReady().then(async () => {
  createWindow();
  startBackend();

  // Show loading page while backend starts
  mainWindow.loadFile(path.join(__dirname, 'pages', 'loading.html'));

  const health = await waitBackend(60);
  if (health) {
    // Load the real app from backend
    mainWindow.loadURL(`http://127.0.0.1:${PORT}`);
  } else {
    mainWindow.loadFile(path.join(__dirname, 'pages', 'error.html'));
  }

  app.on('activate', () => {
    if (mainWindow) mainWindow.show();
    else { createWindow(); mainWindow.loadURL(`http://127.0.0.1:${PORT}`); }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') { stopBackend(); app.quit(); }
});

app.on('before-quit', () => stopBackend());
