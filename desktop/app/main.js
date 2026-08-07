const { app, BrowserWindow, ipcMain, dialog, shell, Menu } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const http = require('http');

let mainWindow = null;

const isWin = process.platform === 'win32';
const isDev = process.argv.includes('--dev');

// Port phải khớp với script khởi động của từng nền tảng:
//   scripts/start_services.ps1  -> mặc định 8100 (Windows, máy chạy thật)
//   scripts/start_services.sh   -> 8000 (macOS/Linux, máy dev)
// Không đọc PORT trong .env: file đó đang ghi 8000 trong khi script Windows
// dùng 8100, nên tin vào .env là mở nhầm cổng rồi chờ chết 5 phút.
const PORT = isWin ? 8100 : 8000;

// Mở Chrome DevTools Protocol ở dev mode để electron-mcp-server kết nối được
if (isDev) {
  app.commandLine.appendSwitch('remote-debugging-port', '9222');
}

/**
 * Thư mục dự án - nơi chứa backend/, .venv/, models/, scripts/.
 *
 * Bản đóng gói portable KHÔNG chạy tại chỗ: electron-builder tạo file exe tự
 * bung, nó giải nén vào %TEMP%\ rồi chạy từ đó. Nên process.execPath trỏ vào
 * thư mục tạm, không phải nơi đặt exe. Biến PORTABLE_EXECUTABLE_DIR do
 * electron-builder đặt mới là thư mục thật chứa file exe (C:\duan\chat-ai).
 * Dùng nhầm execPath thì app đi tìm .venv trong %TEMP% và không bao giờ thấy.
 */
function resolveProjectDir() {
  if (!app.isPackaged) return path.resolve(__dirname, '..', '..');
  return process.env.PORTABLE_EXECUTABLE_DIR || path.dirname(process.execPath);
}

const projectDir = resolveProjectDir();
const startScript = path.join(projectDir, 'scripts', isWin ? 'start_services.ps1' : 'start_services.sh');
const stopScript = path.join(projectDir, 'scripts', isWin ? 'stop_services.ps1' : 'stop_services.sh');
const backendLog = path.join(projectDir, 'logs', 'backend.log');

/**
 * Các file bắt buộc phải có cạnh exe. Thiếu thì báo ngay, đừng chờ hết 5 phút.
 *
 * Python: chấp nhận nhiều vị trí vì venv của dự án KHÔNG theo bố cục chuẩn.
 * Trên máy Windows đang chạy thật, python nằm ở .venv\python.exe chứ không phải
 * .venv\Scripts\python.exe (start_services.ps1 cũng trỏ vào đúng chỗ đó).
 * Đòi đúng đường dẫn chuẩn thì hàm này báo thiếu và app im lặng không khởi động
 * dịch vụ nào - lỗi chỉ lộ ra khi máy khởi động nguội.
 */
function missingFiles() {
  const need = [
    ['backend/main.py'],
    [isWin ? 'scripts/start_services.ps1' : 'scripts/start_services.sh'],
    isWin
      ? ['.venv/python.exe', '.venv/Scripts/python.exe']
      : ['.venv/bin/python', '.venv/bin/python3'],
  ];
  return need
    .filter((alts) => !alts.some((f) => fs.existsSync(path.join(projectDir, f))))
    .map((alts) => alts.join(' hoặc '));
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1000,
    minHeight: 700,
    title: 'VoiceBank AI',
    backgroundColor: '#06080f',
    // Trong bản đóng gói, nội dung app/ nằm ở gốc asar nên '..' đi ra ngoài gói
    // và không có assets/ nào ở đó. Giữ icon BÊN TRONG app/ để cả hai chế độ
    // đều thấy. (Icon của chính file exe lấy từ build.win.icon, khác chỗ này.)
    icon: path.join(__dirname, 'assets', 'icon.png'),
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

// --- Dịch vụ nền ---

function sendLog(msg) {
  if (!msg) return;
  console.log('[srv]', msg);
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('log', msg);
}

/**
 * Khởi động dịch vụ qua script của dự án chứ không tự chạy uvicorn.
 *
 * start_services.ps1 làm 5 việc mà spawn uvicorn trực tiếp KHÔNG có:
 * PhoWhisper server :8178 (thiếu là mất hẳn STT), OLLAMA_KEEP_ALIVE=-1
 * (thiếu thì TTFT 1700ms thay vì ~515ms), khoá xung GPU 1500MHz (+160ms/lượt),
 * PATH ffmpeg, và STT_VAD_FILTER=0. Gọi lại script cũng có nghĩa là sửa script
 * thì app hưởng ngay, không phải build lại exe.
 *
 * Việc thứ 6, thêm 2026-08-07: script TỰ KHỞI ĐỘNG LẠI backend khi code trong
 * `backend/` hay `.env` mới hơn tiến trình đang chạy. Cần vì đóng app KHÔNG dừng
 * dịch vụ nền (xem `window-all-closed` cuối file), nên trước đây sửa code rồi mở
 * lại app vẫn là tiến trình cũ — hiện ra thành "gọi từ app câm tiếng mà script
 * gọi thử vẫn OK", và `/api/health` không lộ ra gì cả. Script bỏ qua việc khởi
 * động lại nếu đang có cuộc gọi.
 */
function startServices() {
  const missing = missingFiles();
  if (missing.length) {
    sendLog(`[LOI] Thiếu file trong ${projectDir}: ${missing.join(', ')}`);
    return false;
  }

  sendLog(`[Dịch vụ] Khởi động từ ${startScript} (cổng ${PORT})`);

  const proc = isWin
    ? spawn('powershell.exe', [
        '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', startScript,
        '-Detached', '-Port', String(PORT),
      ], { cwd: projectDir, windowsHide: true })
    : spawn('bash', [startScript], { cwd: projectDir });

  proc.stdout.on('data', (d) => sendLog(d.toString().trim()));
  proc.stderr.on('data', (d) => sendLog(d.toString().trim()));
  proc.on('error', (e) => sendLog(`[LOI] Không chạy được script: ${e.message}`));
  // Trên Windows script thoát ngay sau khi tạo tiến trình nền (-Detached).
  // Đó là điều mong muốn: dịch vụ sống độc lập với cửa sổ app.
  proc.on('exit', (code) => sendLog(`[Dịch vụ] Script khởi động kết thúc (mã ${code})`));

  return true;
}

function stopServices() {
  if (!fs.existsSync(stopScript)) return;
  const proc = isWin
    ? spawn('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', stopScript],
        { cwd: projectDir, windowsHide: true })
    : spawn('bash', [stopScript], { cwd: projectDir });
  proc.stdout.on('data', (d) => sendLog(d.toString().trim()));
  proc.stderr.on('data', (d) => sendLog(d.toString().trim()));
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

/** Backend sống VÀ TTS đã nạp. Vào app sớm hơn thì lượt nói đầu tiên bị câm. */
function isReady(h) {
  return !!h && h.status === 'ok' && h.services && h.services.tts === 'loaded';
}

/**
 * Chờ tới khi sẵn sàng. Hết giờ mà backend vẫn sống (chỉ TTS chưa nạp) thì
 * vẫn trả về health đó: các tab khác dùng được, chặn hết vào trang lỗi thì
 * phí. Chỉ trả null khi backend hoàn toàn không trả lời.
 */
async function waitBackend(maxWait = 300) {
  const deadline = Date.now() + maxWait * 1000;
  let last = null;
  while (Date.now() < deadline) {
    last = await checkBackend();
    if (isReady(last)) return last;
    await new Promise((r) => setTimeout(r, 1000));
  }
  return last;
}

// --- Menu ---

function buildMenu() {
  const template = [
    ...(process.platform === 'darwin' ? [{ role: 'appMenu' }] : []),
    {
      label: 'Hệ thống',
      submenu: [
        {
          label: 'Tải lại giao diện',
          accelerator: 'CmdOrCtrl+R',
          click: () => mainWindow && mainWindow.loadURL(`http://127.0.0.1:${PORT}`),
        },
        {
          label: 'Khởi động lại dịch vụ',
          click: () => { stopServices(); setTimeout(startServices, 2000); },
        },
        { type: 'separator' },
        {
          label: 'Dừng dịch vụ nền',
          click: async () => {
            const { response } = await dialog.showMessageBox(mainWindow, {
              type: 'question',
              buttons: ['Dừng', 'Huỷ'],
              defaultId: 1,
              cancelId: 1,
              title: 'Dừng dịch vụ nền',
              message: 'Dừng backend và PhoWhisper?',
              detail: 'Ollama vẫn chạy. Lần mở app sau sẽ phải chờ 2-3 phút để nạp lại F5-TTS.',
            });
            if (response === 0) stopServices();
          },
        },
        { type: 'separator' },
        {
          label: 'Mở log backend',
          click: () => {
            if (fs.existsSync(backendLog)) shell.openPath(backendLog);
            else dialog.showMessageBox(mainWindow, { message: `Chưa có log: ${backendLog}` });
          },
        },
        { label: 'Mở thư mục dự án', click: () => shell.openPath(projectDir) },
        { type: 'separator' },
        { role: 'toggleDevTools', label: 'Công cụ lập trình' },
        { role: 'quit', label: 'Thoát' },
      ],
    },
    { role: 'editMenu', label: 'Sửa' },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// --- IPC ---
ipcMain.handle('backend-url', () => `http://127.0.0.1:${PORT}`);
ipcMain.handle('ws-url', () => `ws://127.0.0.1:${PORT}`);
ipcMain.handle('health', () => checkBackend());
ipcMain.handle('project-dir', () => projectDir);
ipcMain.handle('missing-files', () => missingFiles());
ipcMain.handle('open-logs', () => shell.openPath(backendLog));
ipcMain.handle('restart-services', () => { stopServices(); setTimeout(startServices, 2000); });

ipcMain.handle('select-file', async (_, filters) => {
  const r = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: filters || [{ name: 'Audio', extensions: ['wav', 'mp3'] }],
  });
  return r.filePaths[0] || null;
});

ipcMain.handle('open-external', (_, url) => shell.openExternal(url));

// --- Vòng đời app ---
app.whenReady().then(async () => {
  buildMenu();
  createWindow();

  // Xoá HTTP cache để không bao giờ render UI cũ từ disk cache
  try { await mainWindow.webContents.session.clearCache(); } catch (e) {}

  // Trang chờ tự poll health qua preload và tự chuyển vào app khi sẵn sàng
  mainWindow.loadFile(path.join(__dirname, 'pages', 'loading.html'));

  const started = startServices();

  // Không gọi được script (thiếu file cạnh exe) mà backend cũng không có sẵn
  // thì chờ 5 phút là chờ vô ích - vào thẳng trang lỗi, nó liệt kê file thiếu.
  if (!started && !(await checkBackend())) {
    if (mainWindow) mainWindow.loadFile(path.join(__dirname, 'pages', 'error.html'));
    return;
  }

  // Lần khởi động đầu mất vài phút (F5-TTS ~2-3 phút, embedding, RAG) - 300s
  const health = await waitBackend(300);
  if (!mainWindow) return;
  const alreadyInApp = mainWindow.webContents.getURL().startsWith(`http://127.0.0.1:${PORT}`);
  if (health && !alreadyInApp) {
    mainWindow.loadURL(`http://127.0.0.1:${PORT}`);
  } else if (!health && !alreadyInApp) {
    mainWindow.loadFile(path.join(__dirname, 'pages', 'error.html'));
  }

  app.on('activate', () => {
    if (mainWindow) mainWindow.show();
    else { createWindow(); mainWindow.loadURL(`http://127.0.0.1:${PORT}`); }
  });
});

// Đóng cửa sổ chỉ thoát app, KHÔNG dừng dịch vụ nền: chúng chạy detached nên
// sống độc lập, và nạp lại F5-TTS tốn 2-3 phút mỗi lần. Muốn dừng hẳn thì dùng
// menu Hệ thống > Dừng dịch vụ nền.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
