// ============================================
// AI Banking Call - Desktop App
// ============================================

let ws = null;
let sessionId = null;
let backendUrl = '';
let wsUrl = '';
let isRecording = false;
let mediaRecorder = null;
let audioChunks = [];
let audioContext = null;
let audioQueue = [];
let isPlaying = false;
let turnCount = 0;
let startTime = Date.now();
let currentResponseEl = null;

// --- Init ---
async function init() {
  backendUrl = await window.electronAPI.getBackendUrl();
  wsUrl = await window.electronAPI.getWsUrl();

  // Listen for backend logs
  window.electronAPI.onBackendLog((msg) => {
    appendLog(msg);
  });

  window.electronAPI.onBackendStatus((status) => {
    if (status === 'stopped') setServerStatus('stopped', 'Server Stopped');
  });

  // Wait for backend
  setServerStatus('loading', 'Starting server...');
  const health = await window.electronAPI.startBackend();
  if (health) {
    setServerStatus('ok', 'Running');
    connectWS();
    loadSystemInfo(health);
  } else {
    setServerStatus('error', 'Failed to start');
  }
}

// --- Server Status ---
function setServerStatus(state, text) {
  const dot = document.querySelector('#serverStatus .dot');
  const label = document.getElementById('serverStatusText');
  dot.className = 'dot' + (state === 'ok' ? ' ok' : state === 'loading' ? ' loading' : '');
  label.textContent = text;
}

// --- WebSocket ---
function connectWS() {
  const sid = sessionId || 'new';
  ws = new WebSocket(`${wsUrl}/ws/call/${sid}`);

  ws.onopen = () => {
    setServerStatus('ok', 'Connected');
    updateSession();
  };
  ws.onclose = () => {
    setServerStatus('loading', 'Reconnecting...');
    setTimeout(connectWS, 3000);
  };
  ws.onerror = () => setServerStatus('error', 'Connection error');
  ws.onmessage = (e) => handleMessage(JSON.parse(e.data));
}

function handleMessage(msg) {
  switch (msg.type) {
    case 'connected':
      sessionId = msg.session_id;
      document.getElementById('sessionId').textContent = sessionId;
      break;

    case 'transcript':
      addMsg('user', msg.text, msg.latency_ms ? `STT: ${msg.latency_ms}ms` : '');
      document.getElementById('typing').style.display = 'flex';
      currentResponseEl = null;
      break;

    case 'token':
      if (!currentResponseEl) currentResponseEl = addMsg('assistant', '', '');
      appendToMsg(currentResponseEl, msg.text);
      break;

    case 'audio':
      playAudioChunk(msg.data);
      break;

    case 'turn_complete':
      document.getElementById('typing').style.display = 'none';
      turnCount++;
      document.getElementById('turnCount').textContent = turnCount;
      if (msg.metrics) updateMetrics(msg.metrics);
      if (currentResponseEl && msg.full_response) {
        const bubble = currentResponseEl.querySelector('.msg-bubble');
        if (bubble) bubble.textContent = msg.full_response;
        const meta = currentResponseEl.querySelector('.msg-meta');
        if (meta && msg.metrics?.total_ms) meta.textContent = `${msg.metrics.total_ms}ms`;
      }
      currentResponseEl = null;
      break;

    case 'error':
      addMsg('system', msg.message);
      document.getElementById('typing').style.display = 'none';
      currentResponseEl = null;
      break;
  }
}

// --- Chat ---
function sendText() {
  const input = document.getElementById('textInput');
  const text = input.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: 'text', text }));
  input.value = '';
  document.getElementById('typing').style.display = 'flex';
  // Remove welcome message
  const welcome = document.querySelector('.welcome-msg');
  if (welcome) welcome.remove();
}

function updateSession() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({
    type: 'set_session',
    customer_name: document.getElementById('customerName').value,
    product: document.getElementById('productSelect').value,
  }));
}

function addMsg(role, text, meta = '') {
  const chat = document.getElementById('chatMessages');
  const welcome = chat.querySelector('.welcome-msg');
  if (welcome) welcome.remove();

  const div = document.createElement('div');
  div.className = `msg ${role}`;
  const avatar = role === 'user' ? 'KH' : role === 'assistant' ? 'AI' : '';
  div.innerHTML = `
    ${avatar ? `<div class="msg-avatar">${avatar}</div>` : ''}
    <div class="msg-body">
      <div class="msg-bubble">${escapeHtml(text)}</div>
      ${meta ? `<div class="msg-meta">${meta}</div>` : ''}
    </div>
  `;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function appendToMsg(el, text) {
  if (!el) return;
  const bubble = el.querySelector('.msg-bubble');
  if (bubble) bubble.textContent += text;
  document.getElementById('chatMessages').scrollTop = 999999;
}

function clearChat() {
  document.getElementById('chatMessages').innerHTML = `
    <div class="welcome-msg">
      <h3>AI Banking Call System</h3>
      <p>Gõ tin nhắn hoặc bấm mic để bắt đầu.</p>
    </div>`;
  turnCount = 0;
  document.getElementById('turnCount').textContent = '0';
  currentResponseEl = null;
}

// --- Mic ---
async function toggleMic() {
  if (isRecording) stopRecording();
  else await startRecording();
}

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true }
    });
    audioChunks = [];
    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
    mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      const blob = new Blob(audioChunks, { type: 'audio/webm' });
      const pcm = await blobToPCM(blob);
      sendAudio(pcm);
    };
    mediaRecorder.start();
    isRecording = true;
    document.getElementById('micBtn').classList.add('recording');
  } catch (err) {
    addMsg('system', 'Mic error: ' + err.message);
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
  isRecording = false;
  document.getElementById('micBtn').classList.remove('recording');
}

async function blobToPCM(blob) {
  if (!audioContext) audioContext = new AudioContext({ sampleRate: 16000 });
  const ab = await blob.arrayBuffer();
  const buf = await audioContext.decodeAudioData(ab);
  const ch = buf.getChannelData(0);
  const pcm = new Int16Array(ch.length);
  for (let i = 0; i < ch.length; i++) {
    const s = Math.max(-1, Math.min(1, ch[i]));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
  }
  return pcm.buffer;
}

function sendAudio(buf) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: 'audio', data: arrayBufferToBase64(buf) }));
  document.getElementById('typing').style.display = 'flex';
  const welcome = document.querySelector('.welcome-msg');
  if (welcome) welcome.remove();
}

// --- Audio Playback ---
function playAudioChunk(b64) {
  audioQueue.push(b64);
  if (!isPlaying) playNext();
}

async function playNext() {
  if (!audioQueue.length) { isPlaying = false; return; }
  isPlaying = true;
  const b64 = audioQueue.shift();
  try {
    if (!audioContext) audioContext = new AudioContext({ sampleRate: 24000 });
    const buf = await audioContext.decodeAudioData(base64ToArrayBuffer(b64));
    const src = audioContext.createBufferSource();
    src.buffer = buf;
    src.connect(audioContext.destination);
    src.onended = () => playNext();
    src.start();
  } catch { playNext(); }
}

// --- Metrics ---
function updateMetrics(m) {
  const max = 2000;
  setBar('STT', m.stt_ms || 0, max);
  setBar('RAG', m.rag_ms || 0, max);
  setBar('TTFA', m.ttfa_ms || 0, max);
  setBar('Total', m.total_ms || 0, max);

  const badge = document.getElementById('targetBadge');
  const ttfa = m.ttfa_ms || m.total_ms || 0;
  if (ttfa < 1000) {
    badge.className = 'metric-target pass';
    badge.textContent = `${ttfa}ms < 1000ms PASS`;
  } else {
    badge.className = 'metric-target fail';
    badge.textContent = `${ttfa}ms > 1000ms FAIL`;
  }

  const bar = document.getElementById('barTotal');
  bar.className = (m.total_ms || 0) > 2000 ? 'bar bar-red' : 'bar bar-green';
}

function setBar(name, val, max) {
  const bar = document.getElementById('bar' + name);
  const lbl = document.getElementById('val' + name);
  if (bar) bar.style.width = Math.min(val / max * 100, 100) + '%';
  if (lbl) lbl.textContent = val ? val + 'ms' : '-';
}

// --- Benchmark ---
async function runBench(type) {
  const el = document.getElementById('result' + type.toUpperCase());
  if (el) el.textContent = 'Running...';
  try {
    const res = await fetch(`${backendUrl}/api/benchmark/${type}`, { method: 'POST' });
    const data = await res.json();
    if (el) el.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    if (el) el.textContent = 'Error: ' + err.message;
  }
}

// --- Settings ---
async function loadSystemInfo(health) {
  const el = document.getElementById('systemInfo');
  if (health) {
    el.textContent = JSON.stringify(health, null, 2);
  } else {
    try {
      const h = await window.electronAPI.checkHealth();
      el.textContent = h ? JSON.stringify(h, null, 2) : 'Backend not running';
    } catch { el.textContent = 'Cannot connect'; }
  }
}

async function selectVoiceFile() {
  const filePath = await window.electronAPI.selectFile([
    { name: 'Audio', extensions: ['wav', 'mp3', 'flac'] }
  ]);
  if (filePath) document.getElementById('settingVoicePath').value = filePath;
}

// --- Logs ---
function appendLog(msg) {
  const el = document.getElementById('logViewer');
  el.textContent += msg + '\n';
  el.scrollTop = el.scrollHeight;
}

function clearLogs() {
  document.getElementById('logViewer').textContent = '';
}

// --- Navigation ---
function switchPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  document.querySelector(`.nav-btn[data-page="${name}"]`).classList.add('active');
}

// --- Utils ---
function escapeHtml(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
function arrayBufferToBase64(buf) {
  const bytes = new Uint8Array(buf); let b = '';
  for (let i = 0; i < bytes.length; i++) b += String.fromCharCode(bytes[i]);
  return btoa(b);
}
function base64ToArrayBuffer(b64) {
  const bin = atob(b64); const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

// Duration timer
setInterval(() => {
  const s = Math.floor((Date.now() - startTime) / 1000);
  document.getElementById('duration').textContent = `${Math.floor(s/60)}:${(s%60).toString().padStart(2,'0')}`;
}, 1000);

// Start
init();
