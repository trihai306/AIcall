// ============================================
// VoiceBank AI — Desktop App Logic
// ============================================

let ws = null;
let sessionId = null;
let isRecording = false;
let mediaRecorder = null;
let audioChunks = [];
let audioContext = null;
let turnCount = 0;
let startTime = Date.now();
let currentResponseEl = null;
// Bong bóng câu khách nói gần nhất. Cần giữ để gỡ được khi lượt bị cắt lời -
// câu đó sẽ xuất hiện lại bên trong câu đã ghép.
let bongBongKhachCuoi = null;

// ---- WebSocket ----
function connectWS() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const sid = sessionId || 'new';
  ws = new WebSocket(`${protocol}//${location.host}/ws/call/${sid}`);

  ws.onopen = () => {
    setStatus('connected', 'Đã kết nối');
    resetPlayback();   // phiên mới: bỏ lịch phát còn tồn của phiên trước
    sendSessionConfig();
    sendVoiceConfig();
    // Đo mạng vài nhịp đầu để lượt hỏi đầu tiên đã có số RTT mà trừ ra.
    pingRtt();
    setTimeout(pingRtt, 400);
    setTimeout(pingRtt, 1200);
  };
  ws.onclose = () => {
    setStatus('connecting', 'Đang kết nối lại...');
    setTimeout(connectWS, 3000);
  };
  ws.onerror = () => setStatus('error', 'Lỗi kết nối');
  ws.onmessage = (e) => handleMessage(JSON.parse(e.data));
}

function handleMessage(msg) {
  switch (msg.type) {
    case 'connected':
      sessionId = msg.session_id;
      document.getElementById('sessionId').textContent = sessionId;
      break;

    case 'filler':
      break;

    case 'transcript':
      removeWelcome();
      // Giữ tham chiếu để gỡ được nếu lượt này bị khách cắt lời: server nhấc câu
      // đó khỏi lịch sử rồi ghép vào câu sau, nên để nguyên trên màn hình là
      // thấy nó hai lần - một mình, rồi lại nằm trong câu đã ghép.
      bongBongKhachCuoi = addMessage('user', msg.text,
                                     msg.latency_ms ? `STT ${msg.latency_ms}ms` : '');
      showTyping(true);
      currentResponseEl = null;
      break;

    case 'token':
      if (!currentResponseEl) {
        removeWelcome();
        currentResponseEl = addMessage('assistant', '', '');
      }
      appendToMessage(currentResponseEl, msg.text);
      break;

    case 'response_chunk':
      break;

    case 'audio':
      // Mảnh của lượt đã bỏ: bỏ qua, đừng phát. Server đã huỷ lượt cũ nên hầu
      // như không còn, nhưng mảnh đã nằm trong đệm socket vẫn tới nơi.
      if (msg.turn_id !== undefined && msg.turn_id !== luotHienTai) {
        console.log(`[audio] bỏ mảnh của lượt ${msg.turn_id}, đang ở lượt ${luotHienTai}`);
        break;
      }
      playAudioChunk(msg.data);
      break;

    case 'turn_complete':
      markTurnEnd();
      showTyping(false);
      // Lượt bị chính khách cắt lời: bỏ bong bóng dở dang đi. Khách chưa nghe
      // hết câu đó và server cũng đã bỏ nó khỏi lịch sử, để lại nửa câu trên
      // màn hình chỉ gây khó hiểu. Không đếm là một lượt, không cập nhật số đo.
      if (msg.metrics && msg.metrics.bi_cat_loi) {
        currentResponseEl?.remove();
        currentResponseEl = null;
        // Gỡ cả câu khách vừa nói: server đã nhấc nó khỏi lịch sử để ghép vào
        // câu kế tiếp, để lại thì màn hình hiện nó hai lần.
        bongBongKhachCuoi?.remove();
        bongBongKhachCuoi = null;
        break;
      }
      datGoiY(recStream ? 'Mic đang mở · bấm để nói tiếp'
                        : 'Bấm để nói · bấm lần nữa khi nói xong');
      turnCount++;
      document.getElementById('turnCount').textContent = turnCount;
      if (msg.metrics) updateMetrics(msg.metrics);
      if (currentResponseEl && msg.full_response) {
        const bubble = currentResponseEl.querySelector('[data-bubble]');
        if (bubble) bubble.textContent = msg.full_response;
        const meta = currentResponseEl.querySelector('[data-meta]');
        if (meta && msg.metrics?.total_ms) meta.textContent = `${msg.metrics.total_ms}ms`;
      }
      currentResponseEl = null;
      break;

    case 'error':
      addMessage('system', msg.message);
      showTyping(false);
      currentResponseEl = null;
      break;

    case 'pong':
      onPong();
      break;

    case 'session_updated':
    case 'voice_updated':
      break;
  }
}

function sendSessionConfig() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({
    type: 'set_session',
    customer_name: document.getElementById('customerName').value,
    product: document.getElementById('product').value,
  }));
}

function sendVoiceConfig(changedEl) {
  const chatSel = document.getElementById('voiceSelect');
  const contactSel = document.getElementById('contactVoiceSelect');
  // Lấy giọng từ đúng selector vừa thay đổi, không đoán qua activeElement.
  const voice = changedEl?.value || contactSel?.value || chatSel?.value || 'default';
  if (chatSel && chatSel.value !== voice) chatSel.value = voice;
  if (contactSel && contactSel.value !== voice) contactSel.value = voice;
  // Lưu lựa chọn để lần sau mở lại vẫn giữ nguyên - NHƯNG chỉ khi chính người
  // dùng vừa đổi ô chọn (`changedEl` là phần tử DOM của sự kiện onchange).
  //
  // Vì sao phải phân biệt: `loadVoices()` và lúc mở WebSocket cũng gọi hàm này
  // mà KHÔNG có `changedEl`. Trước đây chúng cũng ghi localStorage, nên bất kỳ
  // lần nạp nào lỡ chọn nhầm là cái nhầm đó được đóng dấu VĨNH VIỄN - khởi động
  // lại không hết, vì lần sau `savedVoice` lại được ưu tiên hơn giọng mặc định.
  //
  // Đã xảy ra thật (11-08): app kẹt ở `fosd_1` rồi `heu_a` trong khi .env để
  // `giong_heu`, nên cuộc gọi từ app dùng giọng khác hẳn cuộc gọi bằng script -
  // người dùng nghe ra ngay mà log không hề nhắc tới giọng.
  if (changedEl) localStorage.setItem('selectedVoice', voice);
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: 'set_voice', voice_name: voice }));
}

// ---- Chat ----
function sendText() {
  const input = document.getElementById('textInput');
  const text = input.value.trim();
  if (!text) return;
  // Trước đây chỗ này `return` im lặng khi WS chưa OPEN (đang trong 3s nối lại),
  // nên tin nhắn biến mất không dấu vết. Giờ báo rõ cho người dùng.
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    setStatus('connecting', 'Chưa kết nối — thử lại sau giây lát');
    return;
  }
  markTurnStart('text');   // mốc T0 cho đường chat
  markSent();
  resetPlayback();
  clearTimeout(prefetchTimer);
  prefetchLast = '';       // hỏi lại đúng câu này lượt sau vẫn được nạp sẵn
  ws.send(JSON.stringify({ type: 'text', text, turn_id: luotHienTai }));
  input.value = '';
  showTyping(true);
  removeWelcome();
}

// ---- Nạp sẵn RAG trong lúc khách gõ ----
// RAG ăn 120-171ms và nằm nối tiếp NGAY TRƯỚC LLM. Báo trước cho server câu đang
// gõ để nó tra sẵn (trên CPU, không tranh GPU với TTS); lúc bấm gửi chỉ còn LLM +
// TTS. Khách gõ tiếp thì server tự huỷ bản cũ - đoán trượt không mất gì ngoài một
// lần tra CPU, và câu hỏi đưa vào prompt luôn là bản cuối cùng.
let prefetchTimer = null;
let prefetchLast = '';

function schedulePrefetch() {
  clearTimeout(prefetchTimer);
  // 350ms: đủ dài để không bắn theo từng phím, đủ ngắn để RAG (~150ms) kịp xong
  // trong quãng khách dừng tay trước khi bấm gửi.
  prefetchTimer = setTimeout(() => {
    const text = document.getElementById('textInput').value.trim();
    if (text.length < 8 || text === prefetchLast) return;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    prefetchLast = text;
    ws.send(JSON.stringify({ type: 'prefetch', text }));
  }, 350);
}

function addMessage(role, text, meta = '') {
  const chat = document.getElementById('chat');
  const div = document.createElement('div');
  div.className = 'animate-fade-up';

  if (role === 'user') {
    div.innerHTML = `
      <div class="flex gap-3 justify-end mb-4 max-w-[75%] ml-auto">
        <div class="flex flex-col items-end">
          <div class="msg-bubble-user px-4 py-2.5 text-[13px] leading-relaxed" data-bubble>${escapeHtml(text)}</div>
          ${meta ? `<span class="text-[10px] text-gray-600 mt-1 font-mono" data-meta>${meta}</span>` : ''}
        </div>
        <div class="w-7 h-7 rounded-full bg-cyan-500/20 flex items-center justify-center shrink-0 mt-0.5">
          <span class="text-[10px] font-bold text-cyan-400">KH</span>
        </div>
      </div>`;
  } else if (role === 'assistant') {
    div.innerHTML = `
      <div class="flex gap-3 mb-4 max-w-[75%]">
        <div class="w-7 h-7 rounded-full bg-emerald-500/20 flex items-center justify-center shrink-0 mt-0.5">
          <span class="text-[10px] font-bold text-emerald-400">AI</span>
        </div>
        <div class="flex flex-col">
          <div class="msg-bubble-ai px-4 py-2.5 text-[13px] leading-relaxed" data-bubble>${escapeHtml(text)}</div>
          <span class="text-[10px] text-gray-600 mt-1 font-mono" data-meta>${meta}</span>
        </div>
      </div>`;
  } else {
    div.innerHTML = `
      <div class="flex justify-center mb-3">
        <div class="msg-bubble-system px-3 py-1.5 text-[11px]">${escapeHtml(text)}</div>
      </div>`;
  }

  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function appendToMessage(el, text) {
  if (!el) return;
  const bubble = el.querySelector('[data-bubble]');
  if (bubble) bubble.textContent += text;
  document.getElementById('chat').scrollTop = 999999;
}

function clearChat() {
  resetPlayback();   // cắt luôn audio đang xếp hàng, không để nói tiếp sau khi xoá
  dongMic();         // hết cuộc gọi thì tắt mic, không để nó mở âm thầm
  bongBongKhachCuoi = null;
  datGoiY('Bấm để nói · bấm lần nữa khi nói xong');
  const chat = document.getElementById('chat');
  chat.innerHTML = `
    <div id="welcomeMsg" class="flex flex-col items-center justify-center h-full text-center pb-10 animate-fade-up">
      <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-cyan-500/20 to-emerald-500/20 border border-cyan-500/20 flex items-center justify-center mb-5">
        <svg class="w-8 h-8 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>
      </div>
      <h3 class="text-lg font-semibold text-white mb-2">Xin chào!</h3>
      <p class="text-sm text-gray-500 max-w-xs leading-relaxed">Bấm micro rồi nói như đang gọi điện. Bấm lần nữa khi nói xong để AI trả lời.</p>
    </div>`;
  turnCount = 0;
  document.getElementById('turnCount').textContent = '0';
  currentResponseEl = null;
}

function removeWelcome() {
  const w = document.getElementById('welcomeMsg');
  if (w) w.remove();
}

function showTyping(show) {
  document.getElementById('typing').style.display = show ? 'block' : 'none';
}

// ---- Microphone ----
async function toggleMic() {
  if (isRecording) { stopRecording(); return; }
  await moMic();          // đã mở sẵn thì không mở lại
  batDauGuiTieng();
}

// Thu bằng PCM thô thay vì MediaRecorder.
// MediaRecorder cho ra webm/opus, mà từng mẩu timeslice của nó KHÔNG giải mã độc
// lập được - phải có đủ cả file mới decode. Nên cách cũ buộc phải đợi khách nói
// xong hết rồi mới giải mã và tải lên: toàn bộ khoản đó nằm SAU khi khách dứt lời.
// Lấy PCM thô thì đẩy lên được ngay trong lúc khách đang nói, và server có thể
// phiên âm tạm để đoán trước.
let recCtx = null, recSrc = null, recProc = null, recGain = null, recStream = null;

// --- Cắt lời (barge-in) ---------------------------------------------------
// Micro mở SUỐT cuộc gọi chứ không chỉ lúc khách bấm nút: muốn biết khách nói
// đè lên thì phải nghe được trong lúc AI đang nói. Khi không thu, luồng mic chỉ
// dùng để dò mức tiếng, không gửi gì lên server.
//
// Ngưỡng phải đủ cao vì tiếng AI từ loa vọng ngược vào mic. echoCancellation của
// trình duyệt khử phần lớn nhưng không sạch hẳn - dùng loa ngoài mở to vẫn có thể
// tự cắt lời chính mình. Đeo tai nghe thì không còn vấn đề này.
// Ngưỡng KHÔNG cố định. Một con số chết không thể vừa cho phòng yên tĩnh đeo tai
// nghe, vừa cho phòng ồn dùng loa ngoài: đặt thấp thì AI tự cắt lời chính mình vì
// nghe tiếng nó vọng từ loa, đặt cao thì khách phải hét mới cắt được.
// Ngưỡng thực tế là số lớn nhất trong ba mốc:
//   1. sàn tuyệt đối - chặn nhiễu điện và tiếng thở
//   2. mức nền của phòng nhân hệ số - đo liên tục lúc AI im
//   3. mức tiếng AI đang phát nhân hệ số vọng - chống tự cắt lời
const CAT_LOI_SAN = 0.02;          // sàn tuyệt đối, RMS thang -1..1
const CAT_LOI_NEN_HE_SO = 4;       // phải to gấp 4 lần mức nền phòng
// Hệ số vọng: đo trên trang thật, chạy tiếng AI qua đúng đường phát rồi bơm
// từng chuỗi khung vào bộ dò. Bảng đánh đổi (chặn được vọng tới % / khách nói
// nhỏ tới %): 0.5 -> 30/30 · 0.6 -> 45/40 · 0.7 -> 45/60 · 0.8 -> 60/60 · 0.9 -> 60/100.
// 0.7 bị 0.6 lấn át hoàn toàn nên loại. Chọn 0.6 vì trình duyệt đã bật
// echoCancellation, tiếng còn sót thực tế thấp hơn 30% - đổi lại khách nói nhỏ
// vẫn cắt được. Nếu gặp cảnh AI tự cắt lời chính mình (loa ngoài mở to, không
// đeo tai nghe) thì nâng lên 0.8.
const CAT_LOI_VONG_HE_SO = 0.6;
const CAT_LOI_SO_KHUNG = 2;        // cần 2 khung liên tiếp (~256ms) mới tính là nói
let catLoiDem = 0;
let daCatLoi = false;
// Mức nền của phòng, tự đo lúc AI im lặng. Khởi đầu bằng sàn rồi bám dần theo
// thực tế; chỉ bám XUỐNG nhanh và LÊN chậm để một tiếng động lạ không kéo ngưỡng
// vọt lên rồi khách nói thật lại không cắt được.
let catLoiNen = CAT_LOI_SAN;
// Giữ lại chính những khung đã dùng để phát hiện. Không giữ thì chúng bị vứt và
// chỉ từ khung thứ ba mới gửi lên - mất ~256ms ĐẦU câu khách, đúng chỗ chứa từ
// đầu tiên. Đo được: "lãi suất vay tín chấp bao nhiêu" về tới server thành
// "unk suất vay tín chấp bao nhiêu" - mất hẳn chữ "lãi".
let catLoiDem_khung = [];

function dangPhatTieng() {
  if (!playCtx) return false;
  return playSources.length > 0 || nextPlayTime > playCtx.currentTime + 0.05;
}

function khungSangPCM(ch) {
  const pcm = new Int16Array(ch.length);
  for (let i = 0; i < ch.length; i++) {
    const s = Math.max(-1, Math.min(1, ch[i]));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
  }
  return pcm.buffer;
}

function rmsKhung(ch) {
  let t = 0;
  for (let i = 0; i < ch.length; i++) t += ch[i] * ch[i];
  return Math.sqrt(t / ch.length);
}

// Ngưỡng để coi một khung là "khách đang nói", tính lại theo từng khung.
// GỌI ĐÚNG MỘT LẦN mỗi khung: mucAIDinh() có trạng thái, gọi nhiều lần trong
// cùng một khung sẽ làm đỉnh giảm nhanh hơn thực tế.
function nguongCatLoi() {
  return Math.max(CAT_LOI_SAN,
                  catLoiNen * CAT_LOI_NEN_HE_SO,
                  mucAIDinh() * CAT_LOI_VONG_HE_SO);
}

function xuLyCatLoi(ch) {
  const rms = rmsKhung(ch);

  // AI đang im: đây là lúc duy nhất đo được mức nền thật của phòng.
  // Xuống nhanh (0.3) để vào phòng yên tĩnh là ngưỡng hạ theo ngay; lên chậm
  // (0.02) để một tiếng động lạ không đẩy ngưỡng vọt lên rồi khách nói không cắt được.
  if (!dangPhatTieng()) {
    const k = rms < catLoiNen ? 0.3 : 0.02;
    catLoiNen = Math.max(CAT_LOI_SAN / 4, catLoiNen * (1 - k) + rms * k);
    catLoiDem = 0; catLoiDem_khung = [];
    mucAIDinhGiaTri = 0;   // hết tiếng thì bỏ đỉnh cũ, đừng để nó chặn lượt sau
    return;
  }
  if (daCatLoi) { catLoiDem = 0; catLoiDem_khung = []; return; }

  const nguong = nguongCatLoi();
  if (rms < nguong) { catLoiDem = 0; catLoiDem_khung = []; return; }

  // Giữ bản sao: `ch` là bộ đệm dùng lại của ScriptProcessor, khung sau sẽ ghi
  // đè lên. Không sao chép thì tới lúc gửi chỉ còn dữ liệu của khung mới nhất.
  catLoiDem_khung.push(new Float32Array(ch));
  if (++catLoiDem < CAT_LOI_SO_KHUNG) return;

  daCatLoi = true;
  catLoiDem = 0;
  console.log(`[cắt lời] khách nói đè — mic ${rms.toFixed(3)} > ngưỡng ${nguong.toFixed(3)}`
            + ` (nền ${catLoiNen.toFixed(3)}, tiếng AI ${mucAIDangPhat().toFixed(3)})`);
  resetPlayback();                                   // im ngay tại máy khách
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'barge_in' }));   // bảo server thôi sinh tiếp
  }
  // Thu luôn câu khách đang nói: bắt họ bấm nút lúc đang nói dở là vô lý.
  const dem = catLoiDem_khung;
  batDauGuiTieng();
  // Gửi bù đúng những khung vừa dùng để phát hiện, TRƯỚC khi khung mới tới.
  for (const k of dem) sendAudioChunk(khungSangPCM(k));
}

// Trình duyệt CHỈ gắn navigator.mediaDevices khi trang chạy trong "ngữ cảnh an
// toàn": https, localhost, hoặc 127.0.0.1. Mở web qua IP thuần (LAN, Tailscale)
// thì cả cụm mediaDevices là undefined - lỗi bắn ra là "Cannot read properties
// of undefined", không hề nhắc gì tới micro nên rất dễ đi mò nhầm hướng.
async function layMic(constraints) {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error(
      `Trình duyệt chặn micro vì trang đang mở ở ${location.origin} (không phải `
      + `ngữ cảnh an toàn). Mở qua http://localhost hoặc https rồi thử lại.`
    );
  }
  return navigator.mediaDevices.getUserMedia(constraints);
}

async function moMic() {
  if (recStream) return;   // đã mở cho cuộc gọi này
  try {
    // echoCancellation: Chrome lấy chính luồng âm thanh TRÌNH DUYỆT đang phát
    // làm mẫu rồi trừ khỏi micro. Tiếng AI của mình phát qua Web Audio nằm
    // trong đó, nên nó bị loại TRƯỚC khi tới code này - đây mới là lớp chống
    // vọng chính, ngưỡng động chỉ là lớp đỡ thứ hai.
    //
    // autoGainControl: TẮT. Nó tự kéo mức thu lên xuống, nên tiếng vọng nhỏ bị
    // khuếch đại lên tới ngưỡng còn tiếng khách to lại bị nén xuống - làm hỏng
    // hẳn cách phân biệt theo mức. Tắt đi thì mức thu phản ánh đúng âm lượng thật.
    recStream = await layMic({
      audio: {
        sampleRate: 16000,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: false,
      }
    });
    baoThietLapMic(recStream);
    recCtx = new AudioContext({ sampleRate: 16000 });
    if (recCtx.state === 'suspended') await recCtx.resume();

    recSrc = recCtx.createMediaStreamSource(recStream);
    recProc = recCtx.createScriptProcessor(2048, 1, 1);   // ~128ms mỗi mẩu ở 16kHz
    recProc.onaudioprocess = (e) => {
      const ch = e.inputBuffer.getChannelData(0);
      if (!isRecording) { xuLyCatLoi(ch); return; }
      sendAudioChunk(khungSangPCM(ch));
    };

    // ScriptProcessor chỉ chạy khi có đường ra. Nối qua gain 0 để không vọng
    // tiếng khách ra loa (nối thẳng destination là nghe lại chính mình).
    recGain = recCtx.createGain();
    recGain.gain.value = 0;
    recSrc.connect(recProc);
    recProc.connect(recGain);
    recGain.connect(recCtx.destination);
  } catch (err) {
    addMessage('system', 'Lỗi microphone: ' + err.message);
    datGoiY('Không mở được micro: ' + err.message, 'text-rose-400');
    dongMic();
  }
}

// Báo xem trình duyệt CÓ THẬT SỰ bật khử vọng không. Yêu cầu trong getUserMedia
// chỉ là mong muốn - trình duyệt được phép từ chối, mà từ chối thì không báo lỗi.
// Không kiểm thì tới lúc AI tự cắt lời chính mình sẽ đi mò ngưỡng, trong khi
// nguyên nhân thật là khử vọng không chạy.
function baoThietLapMic(stream) {
  const track = stream?.getAudioTracks?.()[0];
  if (!track?.getSettings) return;
  const d = track.getSettings();
  console.log(`[mic] ${track.label || 'không rõ thiết bị'} | khử vọng: ${d.echoCancellation}`
            + ` | khử ồn: ${d.noiseSuppression} | tự chỉnh mức: ${d.autoGainControl}`
            + ` | ${d.sampleRate || '?'}Hz`);
  if (d.echoCancellation === false) {
    console.warn('[mic] KHỬ VỌNG KHÔNG BẬT - tiếng AI từ loa sẽ lọt vào micro. '
               + 'Đeo tai nghe, hoặc AI có thể tự cắt lời chính mình.');
    datGoiY('Khử vọng không bật — nên đeo tai nghe', 'text-amber-400');
  }
  if (d.autoGainControl === true) {
    console.warn('[mic] Tự chỉnh mức thu vẫn BẬT dù đã xin tắt - mức thu sẽ '
               + 'nhấp nhô, việc phân biệt tiếng khách với tiếng vọng kém chính xác hơn.');
  }
}

function batDauGuiTieng() {
  if (!recStream) return;
  isRecording = true;
  daCatLoi = false;
  catLoiDem = 0;
  catLoiDem_khung = [];
  document.getElementById('micBtn').classList.add('recording');
  datGoiY('Đang nghe… bấm lần nữa khi nói xong', 'text-rose-400');
}

// Dòng chữ dưới nút micro. Bỏ ô gõ chữ rồi thì đây là chỗ duy nhất nói cho
// người dùng biết hệ thống đang ở trạng thái nào.
function datGoiY(chu, mau = 'text-gray-500') {
  const el = document.getElementById('micHint');
  if (el) {
    el.textContent = chu;
    el.className = 'text-xs font-mono ' + mau;
  }
}

// Đóng hẳn micro. Chỉ gọi khi kết thúc cuộc gọi (xoá hội thoại / rời trang) -
// KHÔNG gọi sau mỗi lượt, vì đóng rồi thì không nghe được khách cắt lời nữa.
function dongMic() {
  if (recProc) { recProc.onaudioprocess = null; try { recProc.disconnect(); } catch (e) {} recProc = null; }
  if (recGain) { try { recGain.disconnect(); } catch (e) {} recGain = null; }
  if (recSrc) { try { recSrc.disconnect(); } catch (e) {} recSrc = null; }
  if (recStream) { recStream.getTracks().forEach((t) => t.stop()); recStream = null; }
  if (recCtx) { try { recCtx.close(); } catch (e) {} recCtx = null; }
  isRecording = false;
  daCatLoi = false;
  catLoiDem = 0;
  catLoiDem_khung = [];
  document.getElementById('micBtn')?.classList.remove('recording');
}

function stopRecording() {
  // Mốc T0: khách vừa dứt lời. Audio đã được đẩy dần lên server trong lúc nói,
  // nên ở đây gần như không còn gì phải mã hoá hay tải lên nữa.
  markTurnStart('thoại');
  isRecording = false;
  // KHÔNG đóng mic ở đây: phải còn nghe được để bắt lúc khách nói đè lên AI.
  daCatLoi = false;
  catLoiDem = 0;
  document.getElementById('micBtn').classList.remove('recording');
  datGoiY('AI đang trả lời… nói đè lên để cắt lời', 'text-cyan-400');
  sendAudioEnd();
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

// Đẩy một mẩu PCM lên ngay trong lúc khách còn đang nói.
function sendAudioChunk(buf) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: 'audio_chunk', data: arrayBufferToBase64(buf) }));
}

// Báo khách đã dứt lời. Không kèm dữ liệu - audio đã lên server từ trước.
function sendAudioEnd() {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    setStatus('connecting', 'Chưa kết nối — thử lại sau giây lát');
    return;
  }
  markSent();
  resetPlayback();
  ws.send(JSON.stringify({ type: 'audio_end', turn_id: luotHienTai }));
  showTyping(true);
  removeWelcome();
}

// Giữ lại đường gửi cả cục cho tương thích ngược (trang khác còn gọi).
function sendAudio(buf) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    setStatus('connecting', 'Chưa kết nối — thử lại sau giây lát');
    return;
  }
  resetPlayback();
  markSent();   // mốc T1: đã mã hoá xong và gửi đi
  ws.send(JSON.stringify({ type: 'audio', data: arrayBufferToBase64(buf), turn_id: luotHienTai }));
  showTyping(true);
  removeWelcome();
}

// ---- Audio Playback (gapless) ----
// Chunks are decoded as soon as they arrive and scheduled back-to-back on the
// WebAudio timeline, instead of waiting for the previous chunk to finish
// (the old onended approach added an audible gap at every sentence boundary).
let nextPlayTime = 0;
let decodeChain = Promise.resolve();

// Context RIÊNG cho phát, 24kHz (F5-TTS xuất 24kHz).
// Không dùng chung `audioContext` với luồng thu mic: nó tạo context 16kHz, và
// luồng nào chạy trước thì khoá sample rate cho cả hai — bấm mic trước là mọi
// câu trả lời sau đó bị resample sai.
let playCtx = null;
let playSources = [];
// Máy đo mức tiếng AI đang phát. Cần để phân biệt "khách nói" với "tiếng AI từ
// loa vọng ngược vào micro" - xem mucAIDangPhat().
let playAnalyser = null;

function playbackCtx() {
  if (!playCtx) {
    playCtx = new AudioContext({ sampleRate: 24000 });
    playAnalyser = playCtx.createAnalyser();
    playAnalyser.fftSize = 2048;
    playAnalyser.connect(playCtx.destination);
  }
  return playCtx;
}

// Mức tiếng AI đang phát ra loa ngay lúc này (RMS, thang 0..1).
function mucAIDangPhat() {
  if (!playAnalyser) return 0;
  const b = new Float32Array(playAnalyser.fftSize);
  playAnalyser.getFloatTimeDomainData(b);
  let t = 0;
  for (let i = 0; i < b.length; i++) t += b[i] * b[i];
  return Math.sqrt(t / b.length);
}

// Đỉnh mức tiếng AI trong khoảng gần đây, giữ rồi giảm dần.
// Không dùng giá trị tức thời vì tiếng từ loa vọng về micro luôn TRỄ hơn so với
// lúc nó được phát: một khung vọng to gặp đúng lúc máy đo đọc được mức thấp là
// kích hoạt nhầm. Đo được: rò rỉ 60% gây tự cắt lời khi so với mức tức thời,
// hết hẳn khi so với đỉnh.
const MUC_AI_GIAM = 0.85;          // mỗi khung (~128ms) giảm 15%
let mucAIDinhGiaTri = 0;

function mucAIDinh() {
  mucAIDinhGiaTri = Math.max(mucAIDangPhat(), mucAIDinhGiaTri * MUC_AI_GIAM);
  return mucAIDinhGiaTri;
}

// Gọi khi sang lượt mới / xoá hội thoại / WebSocket nối lại.
// Không reset thì nextPlayTime của lượt trước còn nằm ở tương lai, chunk của
// lượt mới bị xếp hàng sau nó và người dùng không nghe thấy gì suốt hàng chục
// giây — im lặng hoàn toàn, vì lỗi cũng không được log.
// Số lượt do client cấp, tăng mỗi lần gửi. Server gắn số này vào mọi mảnh audio
// nó trả về, mảnh nào lệch số là của lượt đã bỏ -> vứt.
// Cần vì resetPlayback() chỉ dừng được nguồn ĐÃ tạo; mảnh còn đang trên đường
// (trong đệm socket, hoặc đang giải mã) thì đến sau reset và vẫn được phát.
// Đo được: gửi tin 2 lúc t=1201ms thì các mảnh của tin 1 còn tới ở t=1451,
// 1698, 1984 - khoảng 8 giây tiếng của câu trả lời cũ.
let luotHienTai = 0;

// Hạ tiếng trong 30ms rồi mới tắt, thay vì tắt phựt.
// Đo được: dừng ngay giữa sóng làm biên độ rơi thẳng từ 0.065-0.19 về 0 - loa
// phải dịch chuyển đột ngột nên nghe "tách". Để so sánh, bậc nhảy ở ranh giới
// giữa hai mảnh TTS chỉ 0.0001, tức chỗ ghép mảnh vốn đã sạch, không cần đụng.
// 30ms đủ để hết tiếng nổ mà tai không kịp nhận ra là tiếng bị vuốt nhỏ dần.
const CAT_TIENG_VUOT_S = 0.03;

function resetPlayback() {
  const ctx = playCtx;
  const bay_gio = ctx ? ctx.currentTime : 0;
  for (const s of playSources) {
    try {
      if (s.gain) {
        // Chốt giá trị hiện tại trước khi vuốt: không chốt thì ramp tính từ
        // giá trị mặc định chứ không phải từ mức đang phát.
        s.gain.gain.setValueAtTime(s.gain.gain.value, bay_gio);
        s.gain.gain.linearRampToValueAtTime(0, bay_gio + CAT_TIENG_VUOT_S);
        s.src.stop(bay_gio + CAT_TIENG_VUOT_S + 0.005);
      } else {
        s.src.stop();
      }
    } catch (e) { /* đã kết thúc */ }
  }
  playSources = [];
  nextPlayTime = playCtx ? playCtx.currentTime : 0;
  // Bỏ luôn hàng đợi giải mã: mảnh đang chờ trong chuỗi promise sẽ giải mã xong
  // SAU vòng lặp trên nên không có trong playSources, dừng kiểu gì cũng không trúng.
  decodeChain = Promise.resolve();
  // Sang lượt mới ngay tại đây, không để mỗi chỗ gửi tự tăng: xoá hội thoại và
  // nối lại WebSocket cũng gọi hàm này mà không gửi gì, quên tăng thì mảnh cũ
  // vẫn khớp số và vẫn được phát.
  luotHienTai++;
}

// ============ BỘ ĐO ĐỘ TRỄ THẬT ============
// ttfa_ms của server đo từ lúc SERVER bắt đầu xử lý đến lúc GỬI mảnh thật đầu
// tiên. Nó bỏ qua 3 thứ khách thực sự phải chịu:
//   - thời gian client mã hoá audio sau khi khách dứt lời (blobToPCM)
//   - đường truyền hai chiều
//   - thời gian giải mã + xếp lịch trước khi loa thực sự kêu
// và nó bỏ qua filler - thứ khách nghe ĐẦU TIÊN.
//
// Bộ đo này bám đúng 4 mốc:
//   T0 khách dứt lời  ->  T1 gửi đi  ->  T2 nhận tiếng đầu  ->  T3 LOA BẬT TIẾNG
// Con số cần nhìn là ĐÁP ỨNG = T3 - T0.
let turnT0 = null;        // khách dứt lời (nhả nút mic / bấm gửi)
let turnT1 = null;        // đã gửi lên server
let turnFirstChunk = true;
let dapUngDaDo = false;   // lượt này đã đo được lúc loa kêu chưa
window.__latency = [];    // lịch sử để soi trong console

// Độ trễ mạng đo bằng ping/pong trên chính WebSocket đang dùng.
// Cần tách ra vì mở trang từ máy khác (qua Tailscale/relay) thì con số đáp ứng
// bị đội lên vì mạng, không phản ánh năng lực xử lý của máy chạy AI.
let wsRtt = null;
let rttPending = null;
let inTurn = false;       // đang có lượt chạy hay không

// CHỈ đo khi rảnh. Ping giữa lúc server đang bơm audio thì gói pong bị xếp hàng
// sau chúng, đo ra cả thời gian xử lý -> từng cho ra RTT 3000ms và "xử lý" âm.
function pingRtt() {
  if (inTurn || rttPending !== null) return;
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  rttPending = performance.now();
  ws.send(JSON.stringify({ type: 'ping' }));
}

function onPong() {
  if (rttPending === null) return;
  const r = performance.now() - rttPending;
  rttPending = null;
  if (inTurn) return;        // lượt mới chen vào giữa -> mẫu đã bẩn, bỏ
  if (r > 2000) return;      // mẫu vô lý, bỏ
  wsRtt = wsRtt === null ? r : wsRtt * 0.7 + r * 0.3;
}

setInterval(pingRtt, 5000);   // giữ số RTT luôn tươi khi rảnh

function markTurnStart(nguon) {
  turnT0 = performance.now();
  turnT1 = null;
  turnFirstChunk = true;
  dapUngDaDo = false;
  inTurn = true;
  rttPending = null;   // huỷ ping đang chờ, mẫu của nó sẽ bẩn
  window.__lastSource = nguon;
}

function markTurnEnd() {
  inTurn = false;
  setTimeout(pingRtt, 400);   // đợi đường truyền lắng rồi mới đo mạng
}

function markSent() {
  turnT1 = performance.now();
}

// Gọi khi mảnh audio ĐẦU TIÊN của lượt đã được xếp lịch phát.
// startAt là mốc trên đồng hồ AudioContext -> quy về đồng hồ thực để biết
// chính xác mili giây loa bắt đầu kêu.
function markFirstAudio(ctx, startAt) {
  if (!turnFirstChunk || turnT0 === null) return;
  turnFirstChunk = false;

  // outputLatency = trễ từ lúc Web Audio dựng xong đến khi âm ra KHỎI LOA
  // (buffer driver + phần cứng). Bỏ qua nó thì con số báo sớm hơn thực tế;
  // với tai nghe Bluetooth khoản này có thể lên hàng trăm ms.
  const outLat = (ctx.outputLatency || ctx.baseLatency || 0) * 1000;
  const loaBatMs = performance.now() + (startAt - ctx.currentTime) * 1000 + outLat;

  const dapUng = Math.round(loaBatMs - turnT0);
  const mang = wsRtt === null ? null : Math.round(wsRtt);
  const r = {
    nguon: window.__lastSource || '?',
    ma_hoa_ms: turnT1 ? Math.round(turnT1 - turnT0) : null,
    xu_ly_ms: turnT1 ? Math.round(loaBatMs - turnT1 - (mang || 0)) : null,
    mang_ms: mang,
    loa_ms: Math.round(outLat),
    dap_ung_ms: dapUng,                                    // SỐ THẬT tại máy này
    dap_ung_tru_mang_ms: mang === null ? null : dapUng - mang,  // năng lực máy AI
  };
  window.__latency.push(r);
  console.info(
    `[ĐÁP ỨNG] ${r.dap_ung_ms}ms tổng` +
    (mang === null ? '' : ` = ${r.dap_ung_tru_mang_ms}ms xử lý + ${mang}ms mạng`) +
    ` | mã hoá ${r.ma_hoa_ms}ms, trễ loa ${r.loa_ms}ms`
  );
  showDapUng(r);
}

// Chèn thêm một dòng vào bảng chỉ số bên phải (không sửa index.html).
function showDapUng(r) {
  let row = document.getElementById('rowDapUng');
  if (!row) {
    const anchor = document.getElementById('barTTFA')?.closest('.metric-row');
    if (!anchor) return;
    row = document.createElement('div');
    row.id = 'rowDapUng';
    row.className = 'metric-row';
    row.innerHTML =
      '<div class="flex items-center justify-between mb-1">' +
      '<span class="text-[10px] font-semibold uppercase tracking-wider text-cyan-400">Đáp ứng thật</span>' +
      '<span class="text-[11px] font-mono font-semibold text-cyan-400" id="valDapUng">—</span></div>' +
      '<div class="h-1.5 bg-deep rounded-full overflow-hidden">' +
      '<div class="h-full bg-cyan-400 rounded-full transition-all duration-700 ease-out" id="barDapUng" style="width:0%"></div></div>' +
      '<div class="text-[9px] font-mono text-gray-500 mt-1" id="valDapUngChiTiet"></div>';
    anchor.parentNode.insertBefore(row, anchor.nextSibling);
  }
  // Thanh và màu chấm theo phần XỬ LÝ (trừ mạng): mở trang từ máy khác thì mạng
  // không phải lỗi của hệ thống AI, chấm cả mạng vào sẽ đánh giá sai năng lực máy.
  const cham = r.dap_ung_tru_mang_ms ?? r.dap_ung_ms;
  const lbl = document.getElementById('valDapUng');
  const bar = document.getElementById('barDapUng');
  const sub = document.getElementById('valDapUngChiTiet');
  if (lbl) lbl.textContent = r.dap_ung_ms + 'ms';
  if (sub) {
    sub.textContent = r.mang_ms === null
      ? `trễ loa ${r.loa_ms}ms · đang đo mạng…`
      : `${cham}ms xử lý + ${r.mang_ms}ms mạng · trễ loa ${r.loa_ms}ms`;
  }
  if (bar) {
    bar.style.width = Math.min(cham / 2000 * 100, 100) + '%';
    bar.className = 'h-full rounded-full transition-all duration-700 ease-out ' +
                    (cham < 1000 ? 'bg-emerald-400' : cham < 1500 ? 'bg-amber-500' : 'bg-red-500');
  }

  // Badge ĐẠT/KHÔNG ĐẠT chấm theo SỐ ĐO TẠI MÁY KHÁCH tới lúc loa kêu, không
  // theo ttfa_ms của server. ttfa_ms bỏ qua đường truyền, bỏ qua độ trễ loa và
  // bỏ qua cả filler - tức là bỏ qua đúng thứ mà mốc 1000ms cần chứng minh.
  // Thanh TTFA bên cạnh vẫn hiện lúc câu trả lời THẬT tới, không giấu gì.
  dapUngDaDo = true;
  const ind = document.getElementById('targetIndicator');
  if (ind) {
    const dat = cham < 1000;
    ind.className = 'target-badge px-3 py-1.5 rounded-lg text-xs font-bold font-mono ' +
                    (dat ? 'pass' : 'fail');
    ind.textContent = `${cham}ms — ${dat ? 'ĐẠT' : 'KHÔNG ĐẠT'}`;
  }
}

function playAudioChunk(b64) {
  decodeChain = decodeChain
    .then(() => scheduleChunk(b64))
    .catch((e) => console.error('[audio] không phát được chunk:', e));
}

async function scheduleChunk(b64) {
  const ctx = playbackCtx();
  if (ctx.state === 'suspended') await ctx.resume();
  const buf = await ctx.decodeAudioData(base64ToArrayBuffer(b64));
  const src = ctx.createBufferSource();
  src.buffer = buf;
  // Mỗi mảnh đi qua một núm âm lượng riêng. Nối thẳng vào destination thì lúc
  // khách cắt lời chỉ còn cách tắt phựt - mà tắt giữa sóng là nghe "tách".
  const gain = ctx.createGain();
  src.connect(gain);
  // Qua playAnalyser (đã nối tới loa) chứ không nối thẳng destination: cần đo
  // được mức tiếng AI đang phát để không nhầm tiếng vọng là khách nói.
  gain.connect(playAnalyser || ctx.destination);
  const now = ctx.currentTime;
  // Chặn lịch cũ: tụt lại phía sau, hoặc vọt quá xa (>30s) đều kéo về hiện tại.
  if (nextPlayTime < now || nextPlayTime > now + 30) nextPlayTime = now;
  const startAt = Math.max(now + 0.03, nextPlayTime); // 30ms safety margin
  src.start(startAt);
  markFirstAudio(ctx, startAt);   // mốc T3: loa thực sự bắt đầu kêu
  const nut = { src, gain };
  src.onended = () => { playSources = playSources.filter((x) => x !== nut); };
  playSources.push(nut);
  nextPlayTime = startAt + buf.duration;
}

// ---- Metrics ----
function updateMetrics(m) {
  const max = 2000;
  setBar('STT', m.stt_ms || 0, max);
  setBar('RAG', m.rag_ms || 0, max);
  setBar('TTFA', m.ttfa_ms || 0, max);
  setBar('Total', m.total_ms || 0, max);

  // Badge do showDapUng ghi (đo tại máy khách tới lúc loa kêu). Chỉ ghi ở đây
  // khi lượt vừa rồi KHÔNG phát ra tiếng nào - không có loa thì không có gì để
  // đo, mà để badge đứng nguyên số của lượt trước là báo cáo sai.
  if (!dapUngDaDo) {
    const ind = document.getElementById('targetIndicator');
    const ttfa = m.ttfa_ms || m.total_ms || 0;
    ind.className = 'target-badge px-3 py-1.5 rounded-lg text-xs font-bold font-mono fail';
    // Nói rõ VÌ SAO im tiếng. "không có tiếng" trơ trọi từng khiến phải mò gần
    // một tiếng, trong khi lý do gần như luôn là F5-TTS chưa nạp xong (mất 2-3
    // phút sau mỗi lần khởi động lại) chứ không phải hỏng gì.
    const ttsChuaSan = window.trangThaiTTS && window.trangThaiTTS !== 'loaded';
    const lyDo = ttsChuaSan ? ' (TTS chưa nạp xong)' : '';
    ind.textContent = (ttfa ? `${ttfa}ms — không có tiếng` : 'không có tiếng') + lyDo;
    ind.title = ttsChuaSan
      ? 'F5-TTS chưa nạp xong - đợi 2-3 phút sau khi khởi động rồi thử lại'
      : 'Lượt này không phát ra tiếng nào';
  }

  const totalBar = document.getElementById('barTotal');
  if (totalBar) {
    totalBar.className = (m.total_ms || 0) > 1500
      ? 'h-full bg-red-500 rounded-full transition-all duration-700 ease-out'
      : 'h-full bg-emerald-500 rounded-full transition-all duration-700 ease-out';
  }
}

function setBar(name, val, max) {
  const bar = document.getElementById('bar' + name);
  const lbl = document.getElementById('val' + name);
  if (bar) bar.style.width = Math.min(val / max * 100, 100) + '%';
  if (lbl) lbl.textContent = val ? val + 'ms' : '—';
}

// ---- Benchmark ----
// id trong HTML KHÔNG phải lúc nào cũng là type viết hoa: ô end-to-end tên là
// "benchResultFull" chứ không phải "benchResultFULL". getElementById phân biệt
// hoa thường, nên bản cũ ghép chuỗi rồi tìm trượt -> lấy kết quả về xong VỨT ĐI,
// không báo lỗi gì. Ba ô kia trùng khớp ngẫu nhiên vì STT/LLM/TTS/RAG vốn viết
// hoa cả. Tra bảng cho chắc.
const BENCH_EL = {
  stt: 'benchResultSTT', llm: 'benchResultLLM', tts: 'benchResultTTS',
  rag: 'benchResultRAG', full: 'benchResultFull',
};

// Điền tên MODEL ĐANG CHẠY vào tiêu đề 4 thẻ, thay cho chữ ghi cứng trong HTML.
// Nhãn cũ ghi "LLM — Qwen2.5" trong khi máy chạy bản đã fine-tune, và
// "STT — Whisper" trong khi đã đổi sang PhoWhisper-medium: người đọc số tin
// mình đang đo cái khác với thứ thật sự chạy.
async function napTenModelBenchmark() {
  try {
    const res = await fetch('/api/benchmark/info');
    const d = await res.json();
    for (const [k, v] of Object.entries(d)) {
      const el = document.getElementById('benchTen' + k.toUpperCase());
      if (el && v) el.textContent = v;
    }
  } catch (err) {
    console.warn('Không lấy được tên model cho trang Benchmark:', err);
  }
}

async function runBenchmark(type) {
  const elId = BENCH_EL[type];
  const el = document.getElementById(elId);
  if (!el) { console.error('Không có ô kết quả cho benchmark:', type); return; }
  if (el) {
    el.textContent = 'Đang chạy...';
    el.classList.add('running');
  }
  try {
    const res = await fetch(`/api/benchmark/${type}`, { method: 'POST' });
    const data = await res.json();
    if (el) {
      el.textContent = JSON.stringify(data, null, 2);
      el.classList.remove('running');
    }
  } catch (err) {
    if (el) {
      el.textContent = 'Lỗi: ' + err.message;
      el.classList.remove('running');
    }
  }
}

// ---- Cài đặt Model ----
let setupJobId = null;
let setupPollTimer = null;

async function loadSetupStatus() {
  try {
    const res = await fetch('/api/setup/status');
    const data = await res.json();
    renderModelList(data.components || []);
    renderServiceList(data.services || {});

    // Có job đang chạy (vd: mở lại tab giữa chừng) thì bám theo tiếp
    if (data.running_job && data.running_job !== setupJobId) {
      setupJobId = data.running_job;
      pollSetupJob();
    }
  } catch (err) {
    document.getElementById('modelList').innerHTML =
      `<div class="col-span-2 text-xs text-red-400 text-center py-10">Lỗi tải trạng thái: ${escapeHtml(err.message)}</div>`;
  }
}

function renderModelList(components) {
  const busy = !!setupPollTimer;
  document.getElementById('modelList').innerHTML = components.map(c => {
    const ok = c.installed;
    const badge = ok
      ? '<span class="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400">Đã cài</span>'
      : '<span class="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-gray-500/10 text-gray-500">Chưa cài</span>';
    const size = c.size_mb > 0 ? `${c.size_mb} MB trên đĩa` : c.size_hint;
    const btn = ok
      ? `<button onclick="installComponent('${c.id}')" ${busy ? 'disabled' : ''} class="w-full py-2 rounded-lg bg-deep border border-slate-750 text-gray-500 text-xs font-semibold hover:text-cyan-400 hover:border-cyan-500/30 transition-colors disabled:opacity-40">Cài lại</button>`
      : `<button onclick="installComponent('${c.id}')" ${busy ? 'disabled' : ''} class="w-full py-2 rounded-lg bg-cyan-500/10 text-cyan-400 text-xs font-semibold hover:bg-cyan-500/20 transition-colors disabled:opacity-40">Cài — ${escapeHtml(c.size_hint)}</button>`;

    return `
      <div class="bg-deep border ${ok ? 'border-emerald-500/20' : 'border-slate-750'} rounded-xl p-5">
        <div class="flex items-start justify-between mb-2">
          <div>
            <div class="text-sm font-semibold text-white">${escapeHtml(c.name)}</div>
            <div class="text-[10px] text-gray-500 mt-0.5">${escapeHtml(c.desc)}</div>
          </div>
          ${badge}
        </div>
        <div class="text-[10px] font-mono text-gray-600 mb-3 truncate" title="${escapeHtml(c.detail)}">${escapeHtml(c.detail)} · ${escapeHtml(size)}</div>
        ${btn}
      </div>`;
  }).join('');
}

function renderServiceList(s) {
  const row = (label, up, action, hint) => `
    <div class="flex items-center justify-between bg-void/50 rounded-lg px-3 py-2.5">
      <div class="flex items-center gap-2 min-w-0">
        <span class="w-2 h-2 rounded-full shrink-0 ${up ? 'bg-emerald-500' : 'bg-gray-600'}"></span>
        <div class="min-w-0">
          <div class="text-xs text-gray-300 truncate">${label}</div>
          <div class="text-[10px] text-gray-600">${up ? 'Đang chạy' : hint}</div>
        </div>
      </div>
      ${up ? '' : `<button onclick="${action}" class="shrink-0 ml-2 px-2.5 py-1 rounded-md bg-emerald-500/10 text-emerald-400 text-[10px] font-semibold hover:bg-emerald-500/20 transition-colors">Bật</button>`}
    </div>`;

  document.getElementById('serviceList').innerHTML =
    row('Ollama', s.ollama, "startSetupService('ollama')", 'Tắt — cổng 11434') +
    row('PhoWhisper', s.whisper, "startSetupService('whisper')", 'Tắt — cổng 8178') +
    row('F5-TTS (RAM)', s.tts_loaded, 'reloadTTS()', 'Chưa nạp model');
}

async function installComponent(id) {
  setupLog(`Đang khởi động tiến trình cài "${id}"...`);
  try {
    const res = await fetch(`/api/setup/install/${id}`, { method: 'POST' });
    const data = await res.json();
    if (data.error) { setupLog('Lỗi: ' + data.error); return; }
    setupJobId = data.id;
    pollSetupJob();
  } catch (err) {
    setupLog('Lỗi: ' + err.message);
  }
}

function pollSetupJob() {
  if (setupPollTimer) clearInterval(setupPollTimer);
  document.getElementById('setupCancelBtn').classList.remove('hidden');

  const tick = async () => {
    if (!setupJobId) return;
    try {
      const res = await fetch(`/api/setup/jobs/${setupJobId}`);
      const job = await res.json();
      if (job.error) { stopSetupPoll(); setupLog('Lỗi: ' + job.error); return; }

      setupLog(job.lines.join('\n'));
      const st = document.getElementById('setupJobStatus');
      st.textContent = `${job.label} — ${job.status} — ${job.elapsed_s}s`;
      st.className = 'text-[10px] font-mono ' + (
        job.status === 'done' ? 'text-emerald-400' :
        job.status === 'running' ? 'text-cyan-400' : 'text-red-400');

      if (job.status !== 'running') {
        stopSetupPoll();
        loadSetupStatus();
      }
    } catch (err) {
      stopSetupPoll();
      setupLog('Mất kết nối: ' + err.message);
    }
  };

  tick();
  setupPollTimer = setInterval(tick, 1500);
}

function stopSetupPoll() {
  if (setupPollTimer) clearInterval(setupPollTimer);
  setupPollTimer = null;
  document.getElementById('setupCancelBtn').classList.add('hidden');
}

async function cancelSetupJob() {
  if (!setupJobId) return;
  await fetch(`/api/setup/jobs/${setupJobId}/cancel`, { method: 'POST' });
}

async function startSetupService(name) {
  setupLog(`Đang bật dịch vụ "${name}"... (PhoWhisper mất ~20-40 giây nạp model)`);
  try {
    const res = await fetch(`/api/setup/service/${name}/start`, { method: 'POST' });
    const data = await res.json();
    setupLog(JSON.stringify(data, null, 2));
  } catch (err) {
    setupLog('Lỗi: ' + err.message);
  }
  loadSetupStatus();
}

async function reloadTTS() {
  setupLog('Đang nạp F5-TTS vào RAM, mất khoảng 30-60 giây...');
  try {
    const res = await fetch('/api/setup/reload-tts', { method: 'POST' });
    const data = await res.json();
    setupLog(JSON.stringify(data, null, 2));
  } catch (err) {
    setupLog('Lỗi: ' + err.message);
  }
  loadSetupStatus();
}

function setupLog(text) {
  const el = document.getElementById('setupLog');
  el.textContent = text;
  el.scrollTop = el.scrollHeight;
}

// ---- Health ----
async function checkHealth() {
  const el = document.getElementById('systemInfo');
  try {
    const res = await fetch('/api/health');
    const data = await res.json();
    // Ghi lại để badge độ trễ nói được VÌ SAO im tiếng (xem chỗ 'không có tiếng').
    // F5-TTS mất 2-3 phút mới nạp xong sau mỗi lần khởi động lại; trong lúc đó
    // mọi lượt đều câm mà giao diện cũ không hé lộ gì.
    window.trangThaiTTS = data?.services?.tts;
    if (el) el.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    if (el) el.textContent = 'Lỗi: ' + err.message;
  }
}

// TTS nạp xong ở phía sau chứ không báo ra; hỏi lại vài lần đầu để badge không
// mắc kẹt ở "chưa nạp xong" sau khi model đã sẵn sàng. Dừng ngay khi thấy loaded.
function theoDoiTTSNap(conLai = 20) {
  if (window.trangThaiTTS === 'loaded' || conLai <= 0) return;
  setTimeout(() => { checkHealth().finally(() => theoDoiTTSNap(conLai - 1)); }, 10000);
}

// ---- Logs ----
//
// Trang này trước đây là VỎ RỖNG: `clearLogs()` là hàm duy nhất chạm vào
// #logViewer, không có gì đổ dữ liệu vào và backend không có endpoint nào. Nó
// hiển thị "Đang chờ kết nối server..." mãi mãi. Người dùng báo "log chuyển
// menu là mất" - thật ra nó chưa bao giờ có gì để mất.
let logTimer = null;
let logDaXoa = false;      // người dùng bấm Xóa -> đừng vẽ lại ngay ở nhịp sau

async function napLog() {
  const v = document.getElementById('logViewer');
  const tt = document.getElementById('logTrangThai');
  if (!v || logDaXoa) return;
  const nguon = (document.getElementById('logNguon') || {}).value || 'backend';
  try {
    const d = await fetch(`/api/logs?ten=${encodeURIComponent(nguon)}&so_dong=400`)
                    .then(r => r.json());
    if (d.error) { v.textContent = d.error; return; }
    if (!d.co_tep) { v.textContent = `Chưa có tệp ${d.tep} — dịch vụ này chưa chạy lần nào.`; return; }

    // Chỉ vẽ lại khi nội dung ĐỔI: gán textContent làm mất vị trí cuộn, nên
    // người đang đọc dòng ở giữa bị kéo đi mỗi 2 giây.
    const moi = d.dong.join('\n');
    if (moi !== v.textContent) {
      const bamDay = (document.getElementById('logTuCuon') || {}).checked;
      const cuonCu = v.scrollTop;
      v.textContent = moi;
      v.scrollTop = bamDay ? v.scrollHeight : cuonCu;
    }
    if (tt) tt.textContent = `${d.so_dong} dòng · ${(d.kich_thuoc / 1024).toFixed(0)} KB`;
  } catch (err) {
    if (tt) tt.textContent = 'lỗi: ' + err.message;
  }
}

function doiNguonLog() {
  logDaXoa = false;
  document.getElementById('logViewer').textContent = 'Đang tải…';
  napLog();
}

function batDauXemLog() {
  logDaXoa = false;
  napLog();
  if (logTimer) clearInterval(logTimer);
  logTimer = setInterval(napLog, 2000);
}

function dungXemLog() {
  if (logTimer) { clearInterval(logTimer); logTimer = null; }
}

function clearLogs() {
  // Chỉ xoá phần ĐANG HIỂN THỊ, không đụng tệp log trên máy chủ. Dừng bám tiếp
  // cho tới khi người dùng đổi nguồn hoặc quay lại trang - nếu không thì nhịp
  // sau vẽ lại ngay và nút Xóa trông như hỏng.
  document.getElementById('logViewer').textContent = '';
  logDaXoa = true;
  const tt = document.getElementById('logTrangThai');
  if (tt) tt.textContent = 'đã xoá màn hình — đổi nguồn để xem tiếp';
}

// ---- Navigation ----
function switchPage(name) {
  document.querySelectorAll('.page').forEach(p => { p.classList.add('hidden'); p.classList.remove('flex'); });
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  const page = document.getElementById('page-' + name);
  page.classList.remove('hidden');
  if (name === 'chat' || name === 'logs') page.classList.add('flex');
  document.querySelector(`.nav-btn[data-page="${name}"]`).classList.add('active');
  if (name === 'models') loadSetupStatus();
  // Vào tab Thiết bị là quét luôn: người dùng vừa cắm máy vào thì việc đầu tiên
  // họ muốn biết là máy có lên hay không, không phải bấm thêm một nút nữa.
  // `checkAllDevices` chứ không phải `loadDevices`: loadDevices chỉ ĐỌC trạng
  // thái đã lưu, mà trạng thái đó chỉ đổi khi có người bấm "Kiểm tra". Sau mỗi
  // lần khởi động lại backend, máy đang cắm và online vẫn hiện "Chưa kiểm tra"
  // với "Sẵn sàng: 0" - nhìn y như rớt máy. `scanAdb` cũng không cứu được: nó
  // liệt kê máy ADB nhưng không ghi lại trạng thái từng thiết bị.
  if (name === 'devices') { checkAllDevices().catch(() => loadDevices()); scanAdb(); napTocThoai(); }
  if (name === 'contacts') loadCampaigns().then(() => loadContacts());
  if (name === 'sessions') { loadSessionStats(); loadSessionHistory(); }
  if (name === 'voice-test') initVoiceTest();
  if (name === 'voice-training') initVoiceTraining();
  // Trang Training LLM trước đây không có hook nào - mở lên là bảng trống cho
  // tới khi người dùng tự bấm "Làm mới".
  if (name === 'training') { refreshTrainStatus(); loadDatasets(); }
  // Vào trang Benchmark là hỏi lại tên model đang chạy - nó đổi được
  // giữa chừng (đổi .env rồi khởi động lại dịch vụ).
  if (name === 'benchmark') napTenModelBenchmark();
  if (name === 'knowledge') loadTriThuc();
  batDauTuCapNhat(name);
}

// ---- Tự cập nhật theo trang -------------------------------------------------
//
// Trước đây mỗi trang chỉ nạp MỘT LẦN lúc mở. Chiến dịch đang chạy, số đang được
// gọi, máy vừa rút cáp - tất cả đứng im cho tới khi người dùng tự bấm "Làm mới".
// Nhìn ra y như hệ thống treo.
//
// Chỉ làm mới TRANG ĐANG XEM, và dừng hẳn khi cửa sổ bị ẩn: mỗi nhịp là vài
// truy vấn xuống máy Windows, chạy nền cho những trang không ai nhìn là phí
// băng thông đường hầm lẫn CPU của máy đang bận gọi điện.
const _NHIP = {
  overview: 5000,     // số liệu tổng hợp, không cần dày
  contacts: 2500,     // đang gọi tới số nào - thứ đổi nhanh nhất
  sessions: 4000,
  devices: 6000,      // quét ADB tốn, để thưa
  reports: 15000,
};

let _timerTrang = null;
let _trangHienTai = '';

function _napLaiTrang(name) {
  // Không nạp lại khi có hộp thoại đang mở: nạp lại vẽ lại danh sách và đóng
  // mất hộp thoại người dùng đang điền dở.
  if (document.querySelector('.modal:not(.hidden), [id$="Modal"]:not(.hidden)')) return;
  if (name === 'overview' && typeof loadOverview === 'function') loadOverview();
  if (name === 'contacts' && typeof loadContacts === 'function') loadContacts();
  if (name === 'sessions') {
    if (typeof loadSessionStats === 'function') loadSessionStats();
    if (typeof loadSessionHistory === 'function') loadSessionHistory();
  }
  if (name === 'devices' && typeof loadDevices === 'function') loadDevices();
  // Báo cáo: hàm tên `loadReport` (số ít) và nằm ở trang_moi.js, không phải
  // app.js. Tra tên hàm chỉ trong app.js là bỏ sót - frontend có HAI tệp js.
  if (name === 'reports' && typeof loadReport === 'function') loadReport();
}

function batDauTuCapNhat(name) {
  _trangHienTai = name;
  if (_timerTrang) { clearInterval(_timerTrang); _timerTrang = null; }
  // Trang Logs có nhịp riêng vì nó đọc tệp trên đĩa chứ không gọi API dữ liệu,
  // và phải dừng khi rời trang - bám log 2 giây/lần trong lúc người dùng đang ở
  // trang khác là đọc đĩa vô ích trên máy đang bận gọi điện.
  if (typeof dungXemLog === 'function') dungXemLog();
  if (name === 'logs' && typeof batDauXemLog === 'function') {
    if (!document.hidden) batDauXemLog();
    return;
  }
  const nhip = _NHIP[name];
  if (!nhip || document.hidden) return;
  _timerTrang = setInterval(() => _napLaiTrang(name), nhip);
}

// Ẩn cửa sổ thì dừng hẳn, hiện lại thì nạp NGAY rồi chạy tiếp - người dùng quay
// lại là thấy số mới luôn, không phải chờ hết một nhịp.
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    if (_timerTrang) { clearInterval(_timerTrang); _timerTrang = null; }
    if (typeof dungXemLog === 'function') dungXemLog();
  } else if (_trangHienTai) {
    _napLaiTrang(_trangHienTai);
    batDauTuCapNhat(_trangHienTai);
  }
});

// ---- Status ----
function setStatus(state, text) {
  const dot = document.getElementById('statusDot');
  const label = document.getElementById('statusText');
  dot.className = 'status-dot w-2 h-2 rounded-full shrink-0 ' + (state === 'connected' ? 'connected' : state === 'connecting' ? 'connecting' : 'bg-red-500');
  label.textContent = text;
}

// ---- Voices ----
async function loadVoices() {
  try {
    const res = await fetch('/api/voices');
    const data = await res.json();
    const selectors = ['voiceSelect', 'contactVoiceSelect'].map(id => document.getElementById(id)).filter(Boolean);
    selectors.forEach(sel => { sel.innerHTML = ''; });
    // Ưu tiên: 1) giọng đã lưu trong localStorage, 2) giọng mặc định từ server.
    const savedVoice = localStorage.getItem('selectedVoice');
    let resolvedVoice = data.mac_dinh || null;
    const coTen = [];
    (data.voices || []).forEach(v => {
      coTen.push(v.name);
      selectors.forEach(sel => {
        const o = document.createElement('option');
        o.value = v.name;
        o.textContent = v.name + (v.mac_dinh ? ' (mặc định)' : '');
        sel.appendChild(o);
      });
      if (v.mac_dinh && !resolvedVoice) resolvedVoice = v.name;
    });

    // CHỈ nhận giọng đã lưu khi nó CÒN trong danh sách. Giọng bị xoá/đổi tên mà
    // vẫn nhận thì đoạn dưới không khớp option nào, và ô lặng lẽ giữ nguyên
    // option ĐẦU danh sách - tức chạy bằng một giọng chẳng ai chọn.
    const pickVoice = (savedVoice && coTen.includes(savedVoice)) ? savedVoice
                    : (resolvedVoice && coTen.includes(resolvedVoice)) ? resolvedVoice
                    : null;

    if (pickVoice === null) {
      // Không xác định được giọng nào (server chưa kịp trả `mac_dinh`, hoặc
      // danh sách rỗng). ĐỪNG đoán đại và ĐỪNG báo server: cứ im lặng thì
      // server dùng giọng mặc định của chính nó, còn đoán đại là vừa sai vừa
      // bị ghi nhớ lại. Thử lại khi TTS nạp xong.
      console.warn('Chưa xác định được giọng mặc định - giữ nguyên giọng của server.');
      setTimeout(loadVoices, 3000);
      return;
    }
    selectors.forEach(sel => { sel.value = pickVoice; });
    // Báo server dùng đúng giọng vừa chọn. KHÔNG truyền phần tử DOM nào ->
    // `sendVoiceConfig` sẽ không ghi localStorage, vì đây không phải người dùng
    // chọn mà chỉ là khôi phục trạng thái.
    sendVoiceConfig();
  } catch {}
}

// ---- Utilities ----
function escapeHtml(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
function arrayBufferToBase64(buf) {
  const b = new Uint8Array(buf); let s = '';
  for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
  return btoa(s);
}
function base64ToArrayBuffer(b64) {
  const bin = atob(b64); const b = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) b[i] = bin.charCodeAt(i);
  return b.buffer;
}

// Duration
setInterval(() => {
  const s = Math.floor((Date.now() - startTime) / 1000);
  document.getElementById('duration').textContent = `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;
}, 1000);

// ---- Voice Management ----
async function loadVoiceList() {
  try {
    const res = await fetch('/api/voices');
    const data = await res.json();
    const list = document.getElementById('voiceList');
    const ttsSelect = document.getElementById('ttsTestVoice');
    if (!list) return;

    if (!data.voices || data.voices.length === 0) {
      list.innerHTML = '<div class="text-xs text-gray-600 text-center py-8">Chưa có giọng nào. Upload file WAV để bắt đầu.</div>';
      return;
    }

    list.innerHTML = data.voices.map(v => `
      <div class="flex items-center justify-between p-3 bg-void/50 rounded-lg group">
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-lg bg-violet-500/10 flex items-center justify-center">
            <svg class="w-4 h-4 text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M15.536 8.464a5 5 0 010 7.072M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/></svg>
          </div>
          <div>
            <div class="flex items-center gap-2">
              <span class="text-xs font-semibold text-white">${escapeHtml(v.name)}</span>
              ${v.duration ? `<span class="text-[10px] font-mono text-gray-600">${v.duration}s</span>` : ''}
              ${v.silent ? '<span class="tag" style="background:rgba(239,68,68,.12);color:#f87171" title="File giọng mẫu không có tiếng — đọc ra sẽ im lặng">Không có tiếng</span>' : ''}
            </div>
            <div class="text-[10px] ${v.silent ? 'text-red-400/80' : 'text-gray-500'}">
              ${v.silent
                ? 'Thu lại 5-10 giây rồi upload đè lên giọng này'
                : escapeHtml(v.ref_text || 'Không có transcript')}
            </div>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <!-- Tốc riêng từng giọng: F5 sao chép cả nhịp nói của đoạn mẫu, đo được
               giong_heu 3.44 âm tiết/giây còn nam_moi2 chỉ 2.30 - chênh 1.5 lần.
               Một số chung cho mọi giọng thì không thể vừa. -->
          <div class="flex items-center gap-1.5 mr-1" title="Tốc độ đọc riêng cho giọng này">
            <span class="text-[9px] text-gray-600 uppercase tracking-wider">Tốc</span>
            <input type="range" min="0.5" max="1.6" step="0.02" value="${v.speed ?? 1}"
                   oninput="this.nextElementSibling.textContent = (+this.value).toFixed(2)"
                   onchange="datTocGiong('${v.name}', this.value)"
                   class="w-24 accent-violet-500 cursor-pointer">
            <span class="text-[10px] font-mono ${v.speed_rieng ? 'text-violet-300' : 'text-gray-600'} w-8">${(+(v.speed ?? 1)).toFixed(2)}</span>
            ${v.speed_rieng ? `<button onclick="boTocGiong('${v.name}')" class="text-[9px] text-gray-600 hover:text-amber-400" title="Bỏ tốc riêng, dùng lại tốc chung">↺</button>` : ''}
          </div>
          <button onclick="playVoiceSample('${v.name}')" data-nghe="${escapeHtml(v.name)}"
                  class="p-1.5 rounded-md text-gray-500 hover:text-cyan-400 hover:bg-cyan-500/10 transition-colors" title="Nghe thử">
            ${ICON_NGHE}
          </button>
          <button onclick="deleteVoice('${v.name}')" class="p-1.5 rounded-md text-gray-500 hover:text-red-400 hover:bg-red-500/10 transition-colors opacity-0 group-hover:opacity-100" title="Xóa">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
          </button>
        </div>
      </div>
    `).join('');

    // Vẽ lại danh sách là mất nút ⏸ trong khi tiếng vẫn đang chạy - đặt lại cho
    // giọng đang nghe, không thì nút nói một đằng loa phát một nẻo.
    if (mauDangNghe && !mauDangNghe.audio.paused) datIconNghe(mauDangNghe.ten, true);

    if (ttsSelect) {
      ttsSelect.innerHTML = data.voices.map(v =>
        `<option value="${v.name}">${v.name}</option>`
      ).join('');
    }
  } catch {}
}

async function uploadVoice() {
  const name = document.getElementById('voiceUploadName').value.trim();
  const file = document.getElementById('voiceUploadFile').files[0];
  const refText = document.getElementById('voiceUploadText').value.trim();

  if (!name || !file) {
    alert('Vui lòng nhập tên và chọn file audio');
    return;
  }

  const formData = new FormData();
  formData.append('file', file);
  formData.append('name', name);
  formData.append('ref_text', refText);

  try {
    const res = await fetch('/api/voices/upload', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    document.getElementById('voiceUploadName').value = '';
    document.getElementById('voiceUploadFile').value = '';
    document.getElementById('voiceUploadText').value = '';
    loadVoiceList();
    loadVoices();
  } catch (err) { alert('Upload lỗi: ' + err.message); }
}

async function deleteVoice(name) {
  if (!confirm(`Xóa giọng "${name}"?`)) return;
  await fetch(`/api/voices/${name}`, { method: 'DELETE' });
  loadVoiceList();
  loadVoices();
}

// Nghe thử giọng mẫu. MỘT mẫu tại một thời điểm, và bấm lại thì dừng.
//
// Bản cũ tạo `new Audio()` rồi vứt luôn tham chiếu: không có gì để gọi pause()
// nên nghe rồi phải chờ hết, mà bấm giọng thứ hai thì hai mẫu chồng tiếng lên
// nhau - đúng lúc đang so hai giọng thì không nghe ra giọng nào.
const ICON_NGHE = '<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>';
const ICON_DUNG = '<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M10 9v6m4-6v6"/><path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>';

let mauDangNghe = null;      // { ten, audio }
let _tiengThu = null;        // tiếng của các nút nghe thử lẻ (thử tốc, thử 8kHz)

// MỘT tiếng tại một thời điểm trên toàn app. Các nút nghe thử nằm rải rác -
// mẫu giọng, thử tốc từng giọng, thử tốc qua kênh thoại, nghe lại câu vừa thu -
// và trước đây mỗi chỗ tự `new Audio().play()` rồi vứt tham chiếu. Hệ quả: kéo
// thanh Tốc vài lần là mấy câu mẫu chồng tiếng lên nhau, không cách nào dừng.
function dungHetTieng() {
  if (_tiengThu) { _tiengThu.pause(); _tiengThu = null; }
  const vt = document.getElementById('vtrainAudio');
  if (vt && !vt.paused) vt.pause();
  if (mauDangNghe && !mauDangNghe.audio.paused) mauDangNghe.audio.pause();
}

function phatTiengThu(src) {
  dungHetTieng();
  _tiengThu = new Audio(src);
  _tiengThu.play().catch(() => {});
  return _tiengThu;
}

function datIconNghe(ten, dangPhat) {
  const nut = document.querySelector(`button[data-nghe="${CSS.escape(ten)}"]`);
  if (nut) {
    nut.innerHTML = dangPhat ? ICON_DUNG : ICON_NGHE;
    nut.title = dangPhat ? 'Tạm dừng' : 'Nghe thử';
  }
}

function playVoiceSample(name) {
  // Bấm lại chính giọng đang nghe: tạm dừng / chạy tiếp.
  if (mauDangNghe && mauDangNghe.ten === name) {
    const a = mauDangNghe.audio;
    if (a.paused) a.play().catch(() => {}); else a.pause();
    return;
  }

  // Đổi sang giọng khác: dừng hẳn mẫu cũ chứ không chỉ pause, không thì lần sau
  // bấm lại nó tiếp tục từ giữa câu. Dừng luôn tiếng của các nút thử khác -
  // trên cùng màn Giọng nói còn có nút thử tốc, hai thứ đè nhau thì không so
  // được giọng nào ra giọng nào.
  dungHetTieng();
  if (mauDangNghe) mauDangNghe.audio.currentTime = 0;

  const audio = new Audio(`/api/voices/${encodeURIComponent(name)}/audio`);
  const xong = () => {
    datIconNghe(name, false);
    if (mauDangNghe && mauDangNghe.ten === name) mauDangNghe = null;
  };
  // Bám vào SỰ KIỆN của audio chứ không tự tay đặt icon ở từng nhánh bấm: chỉ
  // cần một đường dừng tiếng mà không đi qua nút (trình duyệt ngắt, mẫu lỗi
  // giữa chừng) là nút kẹt ở ⏸ trong khi loa đã im.
  audio.onplay = () => datIconNghe(name, true);
  audio.onpause = () => datIconNghe(name, false);
  audio.onended = xong;
  audio.onerror = xong;
  mauDangNghe = { ten: name, audio };
  audio.play().catch(xong);
}

async function testTTS() {
  const text = document.getElementById('ttsTestText').value.trim();
  const voice = document.getElementById('ttsTestVoice').value;
  const btn = document.getElementById('ttsTestBtn');
  const result = document.getElementById('ttsTestResult');
  const msg = document.getElementById('ttsTestMsg');

  // Viết vào ô thông báo RIÊNG (#ttsTestMsg), tuyệt đối không đặt innerHTML lên
  // #ttsTestResult: thẻ <audio> là con của nó, ghi đè là xoá mất thẻ đó và panel
  // hỏng vĩnh viễn tới khi F5. Dùng textContent nên chữ của server không bao giờ
  // bị hiểu thành HTML.
  const bao = (t, mau) => {
    result.classList.remove('hidden');
    msg.textContent = t;
    msg.className = mau;
  };

  if (!text) return;
  btn.textContent = 'Đang tạo...';
  btn.disabled = true;

  try {
    const formData = new FormData();
    formData.append('text', text);
    formData.append('voice_name', voice);
    // Cắt mảnh giống cuộc gọi. Không bật thì F5 nhận NGUYÊN cả câu một phát -
    // nhịp và thời lượng lệch ~10% so với thứ khách thật sự nghe.
    const catManh = (document.getElementById('ttsTestCatManh') || {}).checked;
    formData.append('cat_manh', catManh ? 'true' : 'false');

    const res = await fetch('/api/voices/test-tts', { method: 'POST', body: formData });
    const data = await res.json();

    if (data.error) {
      bao(data.error, 'text-amber-400');
    } else if (data.audio) {
      // Hiện số đo thay vì để trống: chỉ nghe tai thì không biết bản cắt mảnh
      // dài hơn bản một phát bao nhiêu, mà đó chính là thứ cần so.
      const manh = data.so_manh > 1 ? `${data.so_manh} mảnh` : 'một phát';
      bao(`${manh} · ${(data.duration_ms / 1000).toFixed(2)}s tiếng · `
          + `sinh ${data.elapsed_ms}ms${data.rtf != null ? ` · RTF ${data.rtf}` : ''}`,
          'text-gray-500');
      // Chỗ cắt phải NHÌN được, không chỉ đếm: nghe thấy ngắt lạ mà không biết
      // nó cắt ở đâu thì không lần ra được nguyên nhân.
      const oManh = document.getElementById('ttsTestManh');
      if (oManh) {
        oManh.textContent = data.so_manh > 1 ? data.manh.join('  |  ') : '';
      }
      const audioEl = document.getElementById('ttsTestAudio');
      audioEl.src = 'data:audio/wav;base64,' + data.audio;
      audioEl.play();
    }
  } catch (err) {
    // `fetch` chỉ ném khi KHÔNG tới được server (backend tắt, còn đang nạp
    // F5-TTS, hoặc đường hầm SSH rớt) - lỗi HTTP 4xx/5xx vẫn về nhánh trên.
    // Chuỗi trần "Failed to fetch" của trình duyệt khiến người dùng tưởng giọng
    // nói hỏng, trong khi TTS không hề được gọi tới.
    const mangDut = err instanceof TypeError;
    bao(mangDut
      ? 'Không kết nối được server. Kiểm tra backend còn chạy (/api/health) '
        + 'và tải lại trang — chưa gọi tới được TTS nên chưa biết giọng có lỗi hay không.'
      : `Lỗi: ${err.message}`, 'text-red-400');
  }
  btn.textContent = 'Phát thử';
  btn.disabled = false;
}

// ---- Training ----
async function loadDatasets() {
  try {
    const res = await fetch('/api/training/datasets');
    const data = await res.json();
    const list = document.getElementById('datasetList');
    const select = document.getElementById('trainDataset');

    if (!data.datasets || data.datasets.length === 0) {
      list.innerHTML = '<div class="text-xs text-gray-600 text-center py-8">Chưa có dataset. Upload hoặc tạo dataset mẫu.</div>';
      if (select) select.innerHTML = '<option value="">-- Chưa có dataset --</option>';
      return;
    }

    list.innerHTML = data.datasets.map(d => `
      <div class="flex items-center justify-between p-3 bg-void/50 rounded-lg group">
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-lg bg-amber-500/10 flex items-center justify-center">
            <svg class="w-4 h-4 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
          </div>
          <div>
            <div class="text-xs font-semibold text-white">${escapeHtml(d.id)}</div>
            <div class="text-[10px] text-gray-500">${d.samples} mẫu · ${d.size_kb} KB · ${escapeHtml(d.filename.split('.').pop())}</div>
          </div>
        </div>
        <div class="flex items-center gap-1">
        <button onclick="checkDataset('${d.id}')" title="Soi phong cách" class="px-2 py-1 rounded-md text-[10px] text-gray-500 hover:text-emerald-400 hover:bg-emerald-500/10 transition-colors opacity-0 group-hover:opacity-100">Kiểm tra</button>
        <button onclick="deleteDataset('${d.id}')" class="p-1.5 rounded-md text-gray-500 hover:text-red-400 hover:bg-red-500/10 transition-colors opacity-0 group-hover:opacity-100">
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
        </button>
        </div>
      </div>
    `).join('');

    if (select) {
      select.innerHTML = '<option value="">-- Chọn dataset --</option>' +
        data.datasets.map(d => `<option value="${d.id}">${d.id} (${d.samples} mẫu)</option>`).join('');
    }
  } catch {}
}

/** Hiện kết quả soi phong cách. Đây là phần quan trọng nhất của luồng upload:
 *  dataset sai phong cách vẫn train được và vẫn ra model chạy, chỉ là model nói
 *  sai kiểu - không có gì báo lỗi, nên phải nói thẳng ra ở đây. */
function renderDatasetCheck(kt, tenFile) {
  const el = document.getElementById('datasetCheck');
  if (!kt) { el.classList.add('hidden'); return; }
  el.classList.remove('hidden');

  const coLoi = kt.so_dong_loi > 0;
  el.className = 'text-[11px] rounded-lg p-3 border ' + (coLoi
    ? 'bg-red-500/5 border-red-500/25 text-red-300'
    : 'bg-emerald-500/5 border-emerald-500/25 text-emerald-300');

  let html = `<div class="font-semibold mb-1">${escapeHtml(tenFile || '')} — `
    + `${kt.dat}/${kt.tong} dòng đạt</div>`;

  if (!coLoi) {
    html += `<div class="text-emerald-400/80">Không có dòng nào vi phạm. Dùng train được.</div>`;
  } else {
    html += `<div class="mb-2">${kt.so_dong_loi} dòng vi phạm phong cách. `
      + `Model học theo dữ liệu, không học theo system prompt — train bằng mẫu sai kiểu `
      + `thì model sẽ nói sai kiểu.</div>`;
    const xau = kt.chi_tiet.filter(c => c.loi.length).slice(0, 6);
    html += '<ul class="space-y-1.5">' + xau.map(c =>
      `<li><span class="text-gray-500">dòng ${c.dong}:</span> ${escapeHtml(c.loi.join('; '))}`
      + `<div class="text-gray-500 mt-0.5">${escapeHtml(c.tra_loi)}</div></li>`).join('') + '</ul>';
    const con = kt.so_dong_loi - xau.length;
    if (con > 0) html += `<div class="mt-1.5 text-gray-500">… còn ${con} dòng nữa</div>`;
  }
  el.innerHTML = html;
}

async function uploadDataset() {
  const name = document.getElementById('datasetName').value.trim();
  const file = document.getElementById('datasetFile').files[0];
  if (!file) { alert('Vui lòng chọn file CSV, JSONL hoặc TXT'); return; }

  const formData = new FormData();
  formData.append('file', file);
  formData.append('name', name);

  try {
    const res = await fetch('/api/training/datasets/upload', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    document.getElementById('datasetName').value = '';
    document.getElementById('datasetFile').value = '';
    renderDatasetCheck(data.kiem_tra, data.filename);
    loadDatasets();
    refreshTrainStatus();
  } catch (err) { alert('Upload lỗi: ' + err.message); }
}

async function checkDataset(id) {
  try {
    const data = await fetch('/api/training/datasets/' + encodeURIComponent(id) + '/check')
      .then(r => r.json());
    if (data.error) { alert(data.error); return; }
    renderDatasetCheck(data.kiem_tra, data.filename);
    document.getElementById('datasetCheck').scrollIntoView({ block: 'nearest' });
  } catch (err) { alert('Lỗi: ' + err.message); }
}

async function generateSampleDataset() {
  try {
    const res = await fetch('/api/training/datasets/generate-sample', { method: 'POST' });
    const data = await res.json();
    loadDatasets();
    alert(data.message || 'Dataset mẫu đã tạo');
  } catch (err) { alert('Lỗi: ' + err.message); }
}

async function deleteDataset(id) {
  if (!confirm(`Xóa dataset "${id}"?`)) return;
  await fetch(`/api/training/datasets/${id}`, { method: 'DELETE' });
  loadDatasets();
}

// ============================================
// Training LLM
// ============================================
let trainJobId = null;
let trainTimer = null;

function trainLog(text) {
  const el = document.getElementById('trainingOutput');
  el.textContent = text;
  el.scrollTop = el.scrollHeight;
}

function moKhungTienDo(nhan) {
  document.getElementById('trainProgressCard').classList.remove('hidden');
  document.getElementById('trainJobLabel').textContent = nhan;
}

/** 3725 -> "1 giờ 2 phút". Hiện giây khi còn dưới một phút. */
function fmtThoiGian(giay) {
  if (giay == null || !isFinite(giay)) return '—';
  giay = Math.max(0, Math.round(giay));
  if (giay < 60) return giay + ' giây';
  const p = Math.floor(giay / 60) % 60, h = Math.floor(giay / 3600);
  return h ? `${h} giờ ${p} phút` : `${p} phút ${giay % 60} giây`;
}

async function refreshTrainStatus() {
  const grid = document.getElementById('trainStatusGrid');
  try {
    const s = await fetch('/api/training/status').then(r => r.json());

    const vram = s.vram_free_gb != null ? `${s.vram_free_gb} / ${s.vram_total_gb} GB` : '—';
    grid.innerHTML = [
      statCell('Môi trường', s.env_ready ? 'Sẵn sàng' : 'Chưa cài',
               s.env_ready ? 'text-emerald-400' : 'text-red-400'),
      statCell('GPU', s.gpu_ok ? (s.gpu_name || 'CUDA') : s.device,
               s.gpu_ok ? 'text-emerald-400' : 'text-red-400'),
      statCell('VRAM trống', vram, 'text-cyan-400'),
      statCell('Dữ liệu', `${s.tong_mau} mẫu`,
               s.du_mau ? 'text-emerald-400' : 'text-amber-400'),
      statCell('Model đang dùng', s.model_dang_dung, 'text-violet-400'),
      statCell('Sau khi train', s.model_sau_train, 'text-gray-400'),
    ].join('');

    // grid-column:1/-1 thay cho col-span-*: tailwind.css biên dịch sẵn chỉ có
    // tới col-span-3, khai lớp không tồn tại thì ô co lại một cột.
    if (!s.du_mau) {
      grid.innerHTML += `<div class="stat-cell text-[11px] text-amber-400/80" style="grid-column:1/-1">`
        + `Mới có ${s.tong_mau} mẫu, dưới mức ${s.min_samples} nên fine-tune hiệu quả thấp. `
        + `Nên bổ sung thêm dữ liệu trước khi train.</div>`;
    }

    const btnTrain = document.getElementById('btnStartTrain');
    btnTrain.disabled = !s.env_ready || !s.gpu_ok;
    btnTrain.classList.toggle('opacity-40', btnTrain.disabled);
    btnTrain.classList.toggle('cursor-not-allowed', btnTrain.disabled);
    document.getElementById('btnSetupEnv').textContent =
      s.env_ready ? 'Cài lại môi trường training' : 'Cài môi trường training';

    // Backend có thể đã chạy job từ trước khi mở trang - bám vào để xem tiếp.
    if (s.running_job && !trainJobId) {
      trainJobId = s.running_job;
      moKhungTienDo('Đang chạy');
      pollTrainJob();
    }
  } catch (err) {
    grid.innerHTML = `<div class="stat-cell text-xs text-red-400 text-center py-4" style="grid-column:1/-1">Lỗi: ${escapeHtml(err.message)}</div>`;
  }
}

async function setupTrainEnv() {
  const lai = document.getElementById('btnSetupEnv').textContent.includes('lại');
  if (lai && !confirm('Cài lại sẽ xoá .venv-train rồi tải lại vài GB. Tiếp tục?')) return;

  moKhungTienDo('Cài môi trường training');
  trainLog('Đang bắt đầu…');
  try {
    const job = await fetch('/api/training/env/setup' + (lai ? '?force=true' : ''),
                            { method: 'POST' }).then(r => r.json());
    if (job.error) { trainLog('Lỗi: ' + job.error); return; }
    trainJobId = job.id;
    pollTrainJob();
  } catch (err) {
    trainLog('Lỗi: ' + err.message);
  }
}

async function startTraining() {
  const config = {
    base_model: document.getElementById('trainBaseModel').value,
    epochs: parseInt(document.getElementById('trainEpochs').value, 10) || 3,
    learning_rate: parseFloat(document.getElementById('trainLR').value) || 2e-4,
    lora_rank: parseInt(document.getElementById('trainLoraRank').value, 10) || 16,
    batch_size: parseInt(document.getElementById('trainBatch').value, 10) || 2,
    grad_accum: parseInt(document.getElementById('trainGradAccum').value, 10) || 8,
    auto_deploy: document.getElementById('trainAutoDeploy').checked,
  };

  if (!confirm('Train sẽ nhả F5-TTS và Ollama khỏi VRAM — hệ thống ngừng nhận cuộc gọi '
             + 'cho tới khi xong. Tiếp tục?')) return;

  moKhungTienDo('Fine-tune ' + config.base_model);
  trainLog('Đang bắt đầu…');
  try {
    const job = await fetch('/api/training/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    }).then(r => r.json());
    if (job.error) { trainLog('Lỗi: ' + job.error); return; }
    trainJobId = job.id;
    pollTrainJob();
  } catch (err) {
    trainLog('Lỗi: ' + err.message);
  }
}

function stopTrainPoll() {
  if (trainTimer) clearInterval(trainTimer);
  trainTimer = null;
  document.getElementById('btnCancelTrain').classList.add('hidden');
}

function pollTrainJob() {
  stopTrainPoll();
  document.getElementById('btnCancelTrain').classList.remove('hidden');

  const tick = async () => {
    if (!trainJobId) return;
    try {
      const job = await fetch('/api/training/jobs/' + trainJobId).then(r => r.json());
      if (job.error) { stopTrainPoll(); trainLog('Lỗi: ' + job.error); return; }

      trainLog((job.lines || []).join('\n'));

      const nhan = { running: 'đang chạy', done: 'xong', error: 'lỗi', cancelled: 'đã huỷ' }[job.status] || job.status;
      const mau = { running: 'text-cyan-400', done: 'text-emerald-400', error: 'text-red-400', cancelled: 'text-gray-400' }[job.status] || 'text-gray-400';
      const st = document.getElementById('trainJobStatus');
      st.textContent = `${nhan} · ${fmtThoiGian(job.elapsed_s)}`;
      st.className = 'text-[11px] font-semibold ' + mau;

      const p = job.progress;
      if (p) {
        document.getElementById('trainBar').style.width = (p.percent ?? 0) + '%';
        document.getElementById('trainBarLeft').textContent = (p.percent ?? 0) + '%';
        document.getElementById('trainBarRight').textContent =
          p.eta_s != null ? 'còn ' + fmtThoiGian(p.eta_s) : '';
        document.getElementById('trainStep').textContent = `${p.step} / ${p.total}`;
        document.getElementById('trainEpochNow').textContent = p.epoch ?? '—';
        document.getElementById('trainLoss').textContent = p.loss ?? '—';
        document.getElementById('trainEta').textContent = fmtThoiGian(p.eta_s);
      } else if (job.status === 'running') {
        // Bước tải model / xuất GGUF không có tiến độ theo bước - nói rõ đang
        // chạy thay vì để thanh 0% khiến người dùng tưởng treo.
        document.getElementById('trainBarLeft').textContent = 'đang chuẩn bị…';
      }

      if (job.status !== 'running') {
        stopTrainPoll();
        if (job.status === 'done') {
          document.getElementById('trainBar').style.width = '100%';
          document.getElementById('trainBarLeft').textContent = '100%';
          document.getElementById('trainBarRight').textContent = '';
        }
        trainJobId = null;
        refreshTrainStatus();
        loadDatasets();
      }
    } catch (err) {
      stopTrainPoll();
      trainLog('Mất kết nối: ' + err.message);
    }
  };
  tick();
  trainTimer = setInterval(tick, 2000);
}

async function cancelTrainJob() {
  if (!trainJobId) return;
  if (!confirm('Huỷ tiến trình đang chạy?')) return;
  try {
    await fetch('/api/training/jobs/' + trainJobId + '/cancel', { method: 'POST' });
  } catch (err) {
    trainLog('Lỗi khi huỷ: ' + err.message);
  }
}

// ============================================
// Thiết bị kết nối
// ============================================
const DEVICE_KINDS = {
  adb: 'Phone farm (ADB/USB)',
  phone_link: 'Điện thoại qua app/gateway',
  usb_modem: 'USB modem / SIM box',
  sip: 'SIP / tổng đài',
  audio: 'Sound card / mic-loa',
};

const DEVICE_STATUS = {
  online: { label: 'Sẵn sàng', cls: 'st-online' },
  offline: { label: 'Mất kết nối', cls: 'st-offline' },
  error: { label: 'Lỗi', cls: 'st-error' },
  unknown: { label: 'Chưa kiểm tra', cls: 'st-unknown' },
};

let devices = [];
let editingDeviceId = null;

function statCell(label, value, color) {
  return `
    <div class="stat-cell">
      <div class="k">${label}</div>
      <div class="v ${color}">${escapeHtml(String(value))}</div>
    </div>`;
}

async function loadDevices() {
  try {
    const res = await fetch('/api/devices');
    const data = await res.json();
    devices = data.devices || [];
    renderDeviceStats();
    renderDeviceList();
    renderDeviceSelects();
  } catch (err) {
    document.getElementById('deviceList').innerHTML =
      `<div class="col-span-2 text-xs text-red-400 text-center py-10">Lỗi tải thiết bị: ${escapeHtml(err.message)}</div>`;
  }
}

function renderDeviceStats() {
  const online = devices.filter(d => d.status === 'online').length;
  const offline = devices.filter(d => d.status === 'offline' || d.status === 'error').length;
  const def = devices.find(d => d.is_default);
  document.getElementById('deviceStats').innerHTML = [
    statCell('Tổng thiết bị', devices.length, 'text-white'),
    statCell('Sẵn sàng', online, 'text-emerald-400'),
    statCell('Mất kết nối', offline, offline ? 'text-red-400' : 'text-gray-600'),
    statCell('Thiết bị mặc định', def ? def.name : '—', 'text-cyan-400 stat-name'),
  ].join('');
}

function renderDeviceList() {
  const list = document.getElementById('deviceList');
  if (!devices.length) {
    list.innerHTML = `
      <div class="col-span-2 panel border-dashed py-12 text-center">
        <div class="text-sm text-gray-400 font-semibold mb-1">Chưa có thiết bị nào</div>
        <div class="text-xs text-gray-600">Bấm “+ Thêm thiết bị” để khai điện thoại / gateway dùng gọi ra.</div>
      </div>`;
    return;
  }

  list.innerHTML = devices.map(d => {
    const st = DEVICE_STATUS[d.status] || DEVICE_STATUS.unknown;
    return `
    <div class="panel p-4 flex flex-col ${d.is_default ? 'border-cyan-500/25' : ''}">
      <div class="flex items-start gap-3 flex-1">
        <div class="w-9 h-9 rounded-lg bg-violet-500/10 flex items-center justify-center shrink-0">
          <svg class="w-4 h-4 text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z"/></svg>
        </div>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="text-sm font-semibold text-white truncate">${escapeHtml(d.name)}</span>
            ${d.is_default ? '<span class="tag tag-cyan">Mặc định</span>' : ''}
            <span class="pill ${st.cls} ml-auto shrink-0"><span class="dot"></span>${st.label}</span>
          </div>
          <div class="text-[11px] text-gray-500 mt-0.5">
            ${DEVICE_KINDS[d.kind] || 'Loại không còn hỗ trợ (' + escapeHtml(d.kind) + ') — nên xoá'}${d.phone_number ? ` · <span class="font-mono">${escapeHtml(d.phone_number)}</span>` : ''}
          </div>

          <div class="mt-2.5 space-y-1">
            ${metaRow('Địa chỉ', d.address)}
            ${d.dial_url
              ? metaRow('Link gọi', d.dial_url)
              : '<div class="text-[10px] text-amber-500/80">Chưa có link gọi — phải bấm số thủ công trên máy</div>'}
            ${d.note ? `<div class="text-[10px] text-gray-600">${escapeHtml(d.note)}</div>` : ''}
            ${d.last_error ? `<div class="text-[10px] text-red-400/80">${escapeHtml(d.last_error)}</div>` : ''}
          </div>
        </div>
      </div>

      <div class="flex items-center gap-1.5 mt-3 pt-3 border-t border-slate-750/60">
        <button onclick="checkDevice('${d.device_id}')" class="btn btn-soft">Kiểm tra</button>
        ${d.kind === 'adb' ? `<button onclick="diagnoseSerial('${escapeHtml(d.address)}', '${escapeHtml(d.name)}')" class="btn btn-ghost">Soi chi tiết</button>` : ''}
        ${d.kind === 'adb' ? `<button onclick="hangupDevice('${d.device_id}')" class="btn btn-ghost">Cúp máy</button>` : ''}
        ${d.is_default ? '' : `<button onclick="setDefaultDevice('${d.device_id}')" class="btn btn-ghost">Đặt mặc định</button>`}
        <button onclick="editDevice('${d.device_id}')" class="btn btn-ghost">Sửa</button>
        <span class="text-[10px] text-gray-600 ml-auto mr-1">${d.last_seen ? 'Online ' + fmtTime(d.last_seen) : ''}</span>
        <button onclick="deleteDevice('${d.device_id}')" class="btn btn-danger">Xóa</button>
      </div>
    </div>`;
  }).join('');
}

function metaRow(label, value) {
  if (!value) return '';
  return `
    <div class="flex gap-2 text-[10px] leading-4">
      <span class="w-14 text-gray-600 shrink-0">${label}</span>
      <span class="font-mono text-gray-400 truncate" title="${escapeHtml(value)}">${escapeHtml(value)}</span>
    </div>`;
}

function renderDeviceSelects() {
  const sel = document.getElementById('testCallDevice');
  if (!sel) return;
  sel.innerHTML = devices.length
    ? devices.map(d => `<option value="${d.device_id}"${d.is_default ? ' selected' : ''}>${escapeHtml(d.name)}</option>`).join('')
    : '<option value="">-- Chưa có thiết bị --</option>';
}

function toggleDevicePanel(show) {
  const panel = document.getElementById('panelDevice');
  const open = show === undefined ? panel.classList.contains('hidden') : show;
  panel.classList.toggle('hidden', !open);
  if (!open) resetDeviceForm();
}

function deviceFormValues() {
  return {
    name: document.getElementById('deviceName').value.trim(),
    kind: document.getElementById('deviceKind').value,
    address: document.getElementById('deviceAddress').value.trim(),
    dial_url: document.getElementById('deviceDialUrl').value.trim(),
    phone_number: document.getElementById('devicePhone').value.trim(),
    note: document.getElementById('deviceNote').value.trim(),
  };
}

async function saveDevice() {
  const body = deviceFormValues();
  if (!body.name) { alert('Vui lòng nhập tên thiết bị'); return; }

  const url = editingDeviceId ? `/api/devices/${editingDeviceId}` : '/api/devices';
  const res = await fetch(url, {
    method: editingDeviceId ? 'PATCH' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (data.error) { alert(data.error); return; }

  toggleDevicePanel(false);
  loadDevices();
}

function editDevice(id) {
  const d = devices.find(x => x.device_id === id);
  if (!d) return;
  editingDeviceId = id;
  document.getElementById('deviceName').value = d.name;
  document.getElementById('deviceKind').value = d.kind;
  document.getElementById('deviceAddress').value = d.address;
  document.getElementById('deviceDialUrl').value = d.dial_url;
  document.getElementById('devicePhone').value = d.phone_number;
  document.getElementById('deviceNote').value = d.note;
  document.getElementById('deviceFormTitle').textContent = `Sửa thiết bị — ${d.name}`;
  document.getElementById('deviceSaveBtn').textContent = 'Lưu thay đổi';
  document.getElementById('panelDevice').classList.remove('hidden');
}

function resetDeviceForm() {
  editingDeviceId = null;
  ['deviceName', 'deviceAddress', 'deviceDialUrl', 'devicePhone', 'deviceNote']
    .forEach(id => { document.getElementById(id).value = ''; });
  document.getElementById('deviceKind').value = 'phone_link';
  document.getElementById('deviceFormTitle').textContent = 'Thêm thiết bị';
  document.getElementById('deviceSaveBtn').textContent = 'Thêm thiết bị';
}

async function deleteDevice(id) {
  const d = devices.find(x => x.device_id === id);
  if (!confirm(`Xóa thiết bị "${d ? d.name : id}"?`)) return;
  await fetch(`/api/devices/${id}`, { method: 'DELETE' });
  if (editingDeviceId === id) toggleDevicePanel(false);
  loadDevices();
}

async function setDefaultDevice(id) {
  await fetch(`/api/devices/${id}/default`, { method: 'POST' });
  loadDevices();
}

async function checkDevice(id) {
  const res = await fetch(`/api/devices/${id}/check`, { method: 'POST' });
  const data = await res.json();
  await loadDevices();
  if (data.detail) showTestCallResult(data.status === 'online', data.detail);
}

async function checkAllDevices() {
  const res = await fetch('/api/devices/check-all', { method: 'POST' });
  const data = await res.json();
  devices = data.devices || [];
  renderDeviceStats();
  renderDeviceList();
  renderDeviceSelects();
}

async function scanDevices() {
  const box = document.getElementById('deviceSuggestions');
  box.classList.remove('hidden');
  box.innerHTML = '<div class="text-[11px] text-gray-600">Đang quét cổng USB...</div>';

  const res = await fetch('/api/devices/suggestions');
  const data = await res.json();
  const found = data.suggestions || [];

  box.innerHTML = `
    <div class="flex items-center justify-between mb-2">
      <span class="text-[11px] font-semibold text-gray-300">Cổng tìm thấy trên máy</span>
      <button onclick="document.getElementById('deviceSuggestions').classList.add('hidden')" class="text-[10px] text-gray-500 hover:text-white">Đóng</button>
    </div>
    ${found.length
      ? `<div class="flex gap-2 flex-wrap">${found.map(s => `
          <button onclick="useSuggestion('${escapeHtml(s.name)}', '${s.kind}', '${escapeHtml(s.address)}')" class="chip">
            ${escapeHtml(s.name)} <span class="text-gray-600 font-mono">${escapeHtml(s.address)}</span>
          </button>`).join('')}</div>`
      : '<div class="text-[11px] text-gray-600">Không thấy cổng USB nào. Nếu dùng app trên điện thoại, nhập địa chỉ IP thủ công ở form thêm thiết bị.</div>'}`;
}

function useSuggestion(name, kind, address) {
  document.getElementById('panelDevice').classList.remove('hidden');
  document.getElementById('deviceName').value = name;
  document.getElementById('deviceKind').value = kind;
  document.getElementById('deviceAddress').value = address;
}

async function testCall() {
  const id = document.getElementById('testCallDevice').value;
  const number = document.getElementById('testCallNumber').value.trim();
  if (!id) { alert('Chưa có thiết bị nào để gọi thử'); return; }
  if (!number) { alert('Vui lòng nhập số cần gọi thử'); return; }

  const res = await fetch(`/api/devices/${id}/test-call`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ number }),
  });
  const data = await res.json();
  showTestCallResult(!!data.dialed, data.error || data.detail);
  loadDevices();
}

function showTestCallResult(ok, detail) {
  const el = document.getElementById('testCallResult');
  if (!el) return;
  el.classList.remove('hidden');
  el.className = `text-[11px] ${ok ? 'text-emerald-400' : 'text-amber-400'}`;
  el.textContent = detail || '';
}

// ============================================
// Danh bạ gọi
// ============================================
const CONTACT_STATUS = {
  pending: { label: 'Chưa gọi', cls: 'st-unknown' },
  calling: { label: 'Đang gọi', cls: 'st-calling' },
  done: { label: 'Đã tư vấn', cls: 'st-online' },
  no_answer: { label: 'Không nghe máy', cls: 'st-error' },
  busy: { label: 'Máy bận', cls: 'st-error' },
  refused: { label: 'Từ chối', cls: 'st-offline' },
  invalid: { label: 'Số không hợp lệ', cls: 'st-unknown' },
  dnc: { label: 'Không gọi lại', cls: 'st-offline' },
};

let contacts = [];
let campaigns = [];
let selectedCampaign = '';
let contactPage = 1;
let contactTotal = 0;
let activeCall = null;
let searchTimer = null;

function toggleContactPanel(which) {
  const map = { add: 'panelAddContact', import: 'panelImport' };
  const el = document.getElementById(map[which]);
  const willOpen = el.classList.contains('hidden');
  Object.values(map).forEach(id => document.getElementById(id).classList.add('hidden'));
  if (willOpen) el.classList.remove('hidden');
}

function debouncedContactSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadContacts(1), 300);
}

async function loadContacts(page) {
  if (page) contactPage = page;
  const params = new URLSearchParams({
    page: contactPage,
    limit: 50,
    status: document.getElementById('filterStatus').value,
    campaign_id: selectedCampaign,
    search: document.getElementById('contactSearch').value.trim(),
  });

  try {
    const res = await fetch(`/api/phones/contacts?${params}`);
    const data = await res.json();
    contacts = data.contacts || [];
    contactTotal = data.total || 0;
    fillStatusFilter(data.statuses || []);
    renderContactTable();
    document.getElementById('contactPageInfo').textContent = contactTotal
      ? `${contactTotal} số · trang ${contactPage}/${Math.max(1, Math.ceil(contactTotal / 50))}`
      : 'Chưa có số nào';
    loadContactStats();
  } catch (err) {
    document.getElementById('contactTableBody').innerHTML =
      `<tr><td colspan="9" class="text-center text-xs text-red-400 py-12">Lỗi tải danh bạ: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function fillStatusFilter(statuses) {
  const sel = document.getElementById('filterStatus');
  if (sel.options.length > 1) return;   // đã dựng rồi, giữ nguyên lựa chọn
  sel.innerHTML = '<option value="">Mọi trạng thái</option>' +
    statuses.map(s => `<option value="${s}">${(CONTACT_STATUS[s] || {}).label || s}</option>`).join('');
}

function renderContactTable() {
  const body = document.getElementById('contactTableBody');
  if (!contacts.length) {
    body.innerHTML = `
      <tr><td colspan="9" class="py-12 text-center">
        <div class="text-sm text-gray-400 font-semibold mb-1">Chưa có số nào</div>
        <div class="text-xs text-gray-600">Bấm “+ Thêm số” hoặc “Nhập danh sách” để bắt đầu chiến dịch.</div>
      </td></tr>`;
    updateBulkBar();
    return;
  }

  body.innerHTML = contacts.map(c => {
    const camp = campaigns.find(x => x.campaign_id === c.campaign_id);
    const st = CONTACT_STATUS[c.status] || CONTACT_STATUS.pending;
    return `
    <tr>
      <td><input type="checkbox" class="contact-check" value="${c.contact_id}" onchange="updateBulkBar()"></td>
      <td class="font-mono text-[12.5px] text-gray-100">${escapeHtml(c.phone)}</td>
      <td class="text-gray-300">${escapeHtml(c.name || '—')}</td>
      <td class="col-product text-gray-500">${escapeHtml(c.product || '—')}</td>
      <td class="col-campaign text-gray-500">${camp ? escapeHtml(camp.name) : '—'}</td>
      <td>
        <select onchange="updateContactStatus('${c.contact_id}', this.value)" class="status-select ${st.cls}">
          ${Object.entries(CONTACT_STATUS).map(([k, v]) =>
            `<option value="${k}"${k === c.status ? ' selected' : ''}>${v.label}</option>`).join('')}
        </select>
      </td>
      <td class="text-center font-mono text-gray-500">${c.attempts || '—'}</td>
      <td class="col-when text-gray-600 text-[11px]">${c.last_called_at ? fmtTime(c.last_called_at) : '—'}</td>
      <td class="text-right pr-4 whitespace-nowrap">
        <button onclick="callContact('${c.contact_id}')" class="btn btn-soft">Gọi</button>
        <span class="row-actions">
          <button onclick="showAttempts('${c.contact_id}', '${escapeHtml(c.phone)}')" class="btn btn-danger hover:text-cyan-400">Lịch sử</button>
          <button onclick="deleteContact('${c.contact_id}')" class="btn btn-danger">Xóa</button>
        </span>
      </td>
    </tr>`;
  }).join('');
  updateBulkBar();
}

function updateBulkBar() {
  const n = document.querySelectorAll('.contact-check:checked').length;
  const bar = document.getElementById('bulkBar');
  bar.classList.toggle('hidden', n === 0);
  bar.classList.toggle('flex', n > 0);
  document.getElementById('bulkCount').textContent = n;
}

async function loadContactStats() {
  const res = await fetch(`/api/phones/stats?campaign_id=${encodeURIComponent(selectedCampaign)}`);
  const s = await res.json();
  const by = s.by_status || {};
  const called = (by.done || 0) + (by.no_answer || 0) + (by.busy || 0) + (by.refused || 0);
  document.getElementById('contactStats').innerHTML = [
    statCell('Tổng số', s.total || 0, 'text-white'),
    statCell('Chưa gọi', by.pending || 0, 'text-gray-300'),
    statCell('Đã gọi', called, 'text-cyan-400'),
    statCell('Tư vấn xong', by.done || 0, 'text-emerald-400'),
    statCell('Từ chối / chặn gọi', (by.refused || 0) + (by.dnc || 0), 'text-red-400'),
  ].join('');
}

async function addContact() {
  const body = {
    phone: document.getElementById('contactPhone').value.trim(),
    name: document.getElementById('contactName').value.trim(),
    product: document.getElementById('contactProduct').value,
    campaign_id: document.getElementById('contactCampaign').value,
    note: document.getElementById('contactNote').value.trim(),
  };
  if (!body.phone) { alert('Vui lòng nhập số điện thoại'); return; }

  const res = await fetch('/api/phones/contacts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (data.error) { alert(data.error); return; }

  document.getElementById('contactPhone').value = '';
  document.getElementById('contactName').value = '';
  document.getElementById('contactNote').value = '';
  loadCampaigns();
  loadContacts(1);
}

async function updateContactStatus(id, status) {
  await fetch(`/api/phones/contacts/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
  loadContacts();
}

async function deleteContact(id) {
  const c = contacts.find(x => x.contact_id === id);
  if (!confirm(`Xóa số ${c ? c.phone : id} khỏi danh bạ?`)) return;
  await fetch(`/api/phones/contacts/${id}`, { method: 'DELETE' });
  loadCampaigns();
  loadContacts();
}

function toggleAllContacts(checked) {
  document.querySelectorAll('.contact-check').forEach(cb => { cb.checked = checked; });
  updateBulkBar();
}

async function deleteSelectedContacts() {
  const ids = [...document.querySelectorAll('.contact-check:checked')].map(cb => cb.value);
  if (!ids.length) return;
  if (!confirm(`Xóa ${ids.length} số đã chọn?`)) return;

  await fetch('/api/phones/contacts/bulk-delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contact_ids: ids }),
  });
  document.getElementById('contactCheckAll').checked = false;
  loadCampaigns();
  loadContacts();
}

function changeContactPage(delta) {
  const next = contactPage + delta;
  if (next < 1 || (delta > 0 && next > Math.ceil(contactTotal / 50))) return;
  loadContacts(next);
}

async function importContacts() {
  const file = document.getElementById('contactCsvFile').files[0];
  const text = document.getElementById('contactPasteText').value.trim();
  if (!file && !text) { alert('Chọn file CSV hoặc dán danh sách số'); return; }

  const form = new FormData();
  if (file) form.append('file', file);
  form.append('text', text);
  form.append('campaign_id', selectedCampaign);

  const res = await fetch('/api/phones/contacts/import', { method: 'POST', body: form });
  const data = await res.json();
  if (data.error) { alert(data.error); return; }

  document.getElementById('contactCsvFile').value = '';
  document.getElementById('contactPasteText').value = '';
  toggleContactPanel('import');
  alert(`Thêm mới ${data.added} số · cập nhật ${data.updated} · bỏ qua ${data.skipped}`);
  loadCampaigns();
  loadContacts(1);
}

function exportContacts() {
  const params = new URLSearchParams({
    campaign_id: selectedCampaign,
    status: document.getElementById('filterStatus').value,
  });
  window.open(`/api/phones/contacts/export?${params}`, '_blank');
}

function getSelectedVoice() {
  return document.getElementById('contactVoiceSelect')?.value ||
         document.getElementById('voiceSelect')?.value || 'default';
}

async function callContact(id) {
  const res = await fetch(`/api/phones/contacts/${id}/call`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ voice_name: getSelectedVoice() }),
  });
  handleCallResponse(await res.json());
}

async function callNext() {
  const res = await fetch(`/api/phones/call-next?campaign_id=${encodeURIComponent(selectedCampaign)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ voice_name: getSelectedVoice() }),
  });
  handleCallResponse(await res.json());
}

function handleCallResponse(data) {
  if (data.error) { alert(data.error); return; }

  activeCall = data.contact;
  document.getElementById('activeCallBar').classList.remove('hidden');
  document.getElementById('activeCallPhone').textContent =
    `${data.contact.phone}${data.contact.name ? ' — ' + data.contact.name : ''}`;

  // Nói rõ có ghi âm hay không. Người vận hành cần biết NGAY lúc gọi, chứ để
  // tới lúc mở Báo cáo mới phát hiện cuộc vừa rồi không có bản ghi thì đã muộn.
  const phan = [data.dialed ? 'Đã bấm số qua ' + data.device.name : data.detail];
  if (data.duong_tieng) phan.push('đang ghi âm');
  else if (data.canh_bao) phan.push('KHÔNG ghi âm: ' + data.canh_bao);
  phan.push('phiên AI ' + data.session_id);
  document.getElementById('activeCallDetail').textContent = phan.join(' · ');

  loadContacts();
}

async function finishCall(status) {
  if (!activeCall) return;
  const res = await fetch(`/api/phones/contacts/${activeCall.contact_id}/result`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
  const data = await res.json();
  if (data.error) { alert(data.error); return; }

  // Cho biết cuộc gọi đã được chấm gì và có bị xếp lịch gọi lại không — trước
  // đây bấm xong là thanh biến mất, không phản hồi gì.
  const bc = data.bao_cao || {};
  const ct = data.contact || {};
  const phan = [];
  if (bc.quality) phan.push('chất lượng: ' + bc.quality);
  if (ct.next_retry_at) {
    phan.push('sẽ gọi lại lúc ' +
      new Date(ct.next_retry_at * 1000).toLocaleTimeString('vi-VN',
        { hour: '2-digit', minute: '2-digit' }));
  }
  if (phan.length) {
    const el = document.getElementById('activeCallDetail');
    el.textContent = 'Đã chốt · ' + phan.join(' · ');
    setTimeout(() => document.getElementById('activeCallBar').classList.add('hidden'), 2500);
  } else {
    document.getElementById('activeCallBar').classList.add('hidden');
  }

  activeCall = null;
  loadContacts();
}

async function showAttempts(id, phone) {
  const res = await fetch(`/api/phones/contacts/${id}/attempts`);
  const data = await res.json();
  const panel = document.getElementById('attemptPanel');
  panel.classList.remove('hidden');
  document.getElementById('attemptPhone').textContent = phone;

  const attempts = data.attempts || [];
  document.getElementById('attemptList').innerHTML = attempts.length
    ? attempts.map(a => `
        <div class="flex items-center justify-between px-3 py-2.5 bg-void/50 rounded-lg">
          <div class="min-w-0">
            <div class="text-xs text-gray-300">
              ${a.status === 'dialed' ? 'Đã bấm số' : 'Gọi lỗi'}
              ${a.session_id ? `· <span class="font-mono text-gray-500">${escapeHtml(a.session_id)}</span>` : ''}
            </div>
            <div class="text-[10px] text-gray-600 mt-0.5 truncate">${escapeHtml(a.detail || '')}</div>
          </div>
          <div class="text-[10px] text-gray-600 shrink-0 ml-3">${fmtTime(a.started_at)}</div>
        </div>`).join('')
    : '<div class="text-xs text-gray-600 py-4 text-center">Số này chưa được gọi lần nào.</div>';
}

// ---- Chiến dịch ----
async function loadCampaigns() {
  const res = await fetch('/api/phones/campaigns');
  const data = await res.json();
  campaigns = data.campaigns || [];
  renderCampaignChips();

  const assign = document.getElementById('contactCampaign');
  const keep = assign.value;
  assign.innerHTML = '<option value="">-- Không thuộc chiến dịch --</option>' +
    campaigns.map(c => `<option value="${c.campaign_id}">${escapeHtml(c.name)}</option>`).join('');
  assign.value = keep;
}

function renderCampaignChips() {
  const chips = [`
    <button onclick="selectCampaign('')" class="chip ${selectedCampaign ? '' : 'active'}">Tất cả</button>`];

  campaigns.forEach(c => {
    const active = selectedCampaign === c.campaign_id;
    chips.push(`
      <button onclick="selectCampaign('${c.campaign_id}')" class="chip ${active ? 'active' : ''}">
        ${escapeHtml(c.name)}
        <span class="${active ? 'text-cyan-500/70' : 'text-gray-600'}">${c.pending}/${c.total}</span>
        ${active ? `<span onclick="event.stopPropagation(); deleteCampaign('${c.campaign_id}')" class="chip-x" title="Xóa chiến dịch">×</span>` : ''}
      </button>`);
  });

  chips.push(`<button onclick="addCampaign()" class="chip chip-add">+ Chiến dịch</button>`);
  document.getElementById('campaignChips').innerHTML = chips.join('');

  const target = document.getElementById('importTargetCampaign');
  if (target) {
    const c = campaigns.find(x => x.campaign_id === selectedCampaign);
    target.textContent = c ? c.name : 'Không thuộc chiến dịch nào';
  }
}

function selectCampaign(id) {
  selectedCampaign = id;
  renderCampaignChips();
  loadContacts(1);
}

async function addCampaign() {
  const name = prompt('Tên chiến dịch:');
  if (!name || !name.trim()) return;
  await fetch('/api/phones/campaigns', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name.trim() }),
  });
  loadCampaigns();
}

async function deleteCampaign(id) {
  const c = campaigns.find(x => x.campaign_id === id);
  if (!confirm(`Xóa chiến dịch "${c ? c.name : id}"? Các số vẫn được giữ lại trong danh bạ.`)) return;
  await fetch(`/api/phones/campaigns/${id}`, { method: 'DELETE' });
  selectedCampaign = '';
  await loadCampaigns();
  loadContacts(1);
}

function fmtTime(epochSeconds) {
  const d = new Date(epochSeconds * 1000);
  const pad = n => String(n).padStart(2, '0');
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// ---- Quét thiết bị thật: phone farm (ADB) ----
// Kết quả quét giữ ở đây để biết dòng nào người dùng đã tick khi bấm "Thêm".
let scanned = { adb: [] };

const ADB_STATE_HINT = {
  device: { label: 'Sẵn sàng', cls: 'text-emerald-400' },
  unauthorized: { label: 'Chưa cho phép gỡ lỗi USB', cls: 'text-amber-400' },
  offline: { label: 'Mất kết nối USB', cls: 'text-red-400' },
};

function scanPlaceholder(msg, tone = 'gray') {
  const color = tone === 'error' ? 'text-red-400' : tone === 'warn' ? 'text-amber-400' : 'text-gray-600';
  return `<div class="text-xs ${color} text-center py-6">${escapeHtml(msg)}</div>`;
}

async function scanAdb() {
  const box = document.getElementById('adbScanResult');
  box.innerHTML = scanPlaceholder('Đang quét máy qua ADB...');
  document.getElementById('adbImportBar').classList.add('hidden');

  try {
    const res = await fetch('/api/devices/scan/adb');
    const data = await res.json();
    scanned.adb = data.devices || [];

    if (!data.adb_installed) {
      box.innerHTML = scanPlaceholder(
        'Chưa cài adb. Cài Android Platform Tools (macOS: brew install android-platform-tools) rồi quét lại.', 'warn');
      return;
    }
    if (data.error) { box.innerHTML = scanPlaceholder(data.error, 'error'); return; }
    if (!scanned.adb.length) {
      box.innerHTML = scanPlaceholder('Không thấy máy nào. Cắm USB, bật Gỡ lỗi USB rồi quét lại.');
      return;
    }

    box.innerHTML = scanned.adb.map((d, i) => {
      const st = ADB_STATE_HINT[d.state] || { label: d.state, cls: 'text-gray-400' };
      const meta = [
        d.operator || null,
        d.android ? 'Android ' + d.android : null,
        d.battery != null ? d.battery + '% pin' : null,
      ].filter(Boolean).join(' · ');
      return `
        <label class="flex items-center gap-3 p-2.5 rounded-lg bg-void/50 ${d.saved || d.state !== 'device' ? 'opacity-60' : 'cursor-pointer hover:bg-void'}">
          <input type="checkbox" data-scan="adb" data-idx="${i}" onchange="updateImportBar('adb')"
                 ${d.saved || d.state !== 'device' ? 'disabled' : 'checked'} class="shrink-0">
          <div class="min-w-0 flex-1">
            <div class="text-xs font-semibold text-white truncate">${escapeHtml(d.name)}</div>
            <div class="text-[10px] text-gray-500 font-mono truncate">${escapeHtml(d.address)}${meta ? ' · ' + escapeHtml(meta) : ''}</div>
          </div>
          <span class="text-[10px] ${st.cls} shrink-0">${d.saved ? 'Đã thêm' : st.label}</span>
          <button type="button" class="btn btn-soft shrink-0 !py-1 !px-2 !text-[10px]"
                  onclick="event.preventDefault(); event.stopPropagation(); diagnoseSerial('${escapeHtml(d.address)}', '${escapeHtml(d.name)}')">
            Kiểm tra
          </button>
        </label>`;
    }).join('');
    updateImportBar('adb');
  } catch (e) {
    box.innerHTML = scanPlaceholder('Lỗi quét: ' + e.message, 'error');
  }
}

// ---- Kiểm tra một máy vừa cắm ----
// Cắm máy vào mà không gọi được thì nguyên nhân nằm rải rác ở nhiều khâu, nên
// hiện từng mục kèm cách khắc phục thay vì một chữ "offline" bắt người dùng đoán.

const DIAG_TONE = {
  ok:   { dot: 'bg-emerald-400', text: 'text-emerald-400' },
  warn: { dot: 'bg-amber-400',   text: 'text-amber-400' },
  fail: { dot: 'bg-red-400',     text: 'text-red-400' },
};

function diagBanner(data) {
  if (!data.connected) {
    return `<div class="text-xs font-semibold text-red-400 mb-2">Chưa kết nối được máy</div>`;
  }
  if (!data.callable) {
    return `<div class="text-xs font-semibold text-amber-400 mb-2">Kết nối được, nhưng chưa gọi ra được</div>`;
  }
  return `<div class="text-xs font-semibold text-emerald-400 mb-2">Máy sẵn sàng gọi</div>`;
}

async function diagnoseSerial(serial, label) {
  const box = document.getElementById('diagResult');
  document.getElementById('diagTarget').textContent = label || serial;
  box.innerHTML = scanPlaceholder('Đang kiểm tra ' + (label || serial) + '...');

  try {
    const res = await fetch('/api/devices/diagnose/' + encodeURIComponent(serial));
    const data = await res.json();
    if (data.error) { box.innerHTML = scanPlaceholder(data.error, 'error'); return; }

    box.innerHTML = diagBanner(data) + (data.checks || []).map(c => {
      const t = DIAG_TONE[c.status] || DIAG_TONE.warn;
      return `
        <div class="flex items-start gap-2.5 p-2 rounded-lg bg-void/50">
          <span class="w-1.5 h-1.5 rounded-full ${t.dot} mt-1.5 shrink-0"></span>
          <div class="min-w-0 flex-1">
            <div class="text-[11px] text-white">${escapeHtml(c.label)}</div>
            <div class="text-[10px] ${t.text} break-words">${escapeHtml(c.detail)}</div>
            ${c.hint ? `<div class="text-[10px] text-gray-500 mt-0.5 break-words">${escapeHtml(c.hint)}</div>` : ''}
          </div>
        </div>`;
    }).join('');
  } catch (e) {
    box.innerHTML = scanPlaceholder('Lỗi kiểm tra: ' + e.message, 'error');
  }
}

function selectedScanned(kind) {
  return [...document.querySelectorAll(`input[data-scan="${kind}"]:checked`)]
    .map(cb => scanned[kind][Number(cb.dataset.idx)])
    .filter(Boolean);
}

function updateImportBar(kind) {
  const bar = document.getElementById(kind + 'ImportBar');
  const info = document.getElementById(kind + 'SelectedInfo');
  const n = selectedScanned(kind).length;
  bar.classList.toggle('hidden', n === 0);
  if (n) info.textContent = `Đã chọn ${n} thiết bị`;
}

async function importScanned(kind) {
  const picked = selectedScanned(kind);
  if (!picked.length) return;

  const payload = picked.map(d => ({
    name: d.name,
    kind,
    address: d.address,
    dial_url: '',
    phone_number: '',
    note: [d.operator, d.android ? 'Android ' + d.android : ''].filter(Boolean).join(' · '),
  }));

  try {
    const res = await fetch('/api/devices/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ devices: payload }),
    });
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    await loadDevices();
    scanAdb();                                     // refresh cờ "Đã thêm"
  } catch (e) { alert('Lỗi thêm thiết bị: ' + e.message); }
}

async function hangupDevice(deviceId) {
  try {
    const res = await fetch(`/api/devices/${deviceId}/hangup`, { method: 'POST' });
    const data = await res.json();
    alert(data.detail || (data.hungup ? 'Đã cúp máy' : 'Không cúp được máy'));
  } catch (e) { alert('Lỗi: ' + e.message); }
}

// ---- Quản lý phiên hội thoại ----
let sessPage = 1;
let sessTotal = 0;
const SESS_LIMIT = 15;
let sessSearchTimer = null;
let currentSessId = null;

function fmtDur(sec) {
  if (sec == null) return '—';
  const m = Math.floor(sec / 60), s = Math.round(sec % 60);
  return m > 0 ? `${m}p ${s}s` : `${s}s`;
}

async function loadSessionStats() {
  try {
    const res = await fetch('/api/history/stats');
    const { stats } = await res.json();
    if (!stats) return;
    const cards = [
      { label: 'Tổng phiên', value: stats.total_sessions ?? 0, color: 'cyan' },
      { label: '24 giờ qua', value: stats.sessions_24h ?? 0, color: 'emerald' },
      { label: 'Tổng lượt thoại', value: stats.total_turns ?? 0, color: 'violet' },
      { label: 'TB thời lượng', value: fmtDur(stats.avg_duration_seconds), color: 'amber' },
      { label: 'TB phản hồi', value: stats.avg_total_ms ? stats.avg_total_ms + 'ms' : '—', color: 'rose' },
    ];
    document.getElementById('sessionStats').innerHTML = cards.map(c => `
      <div class="bg-deep border border-slate-750 rounded-xl p-4">
        <div class="text-[10px] text-gray-500 uppercase tracking-wider mb-1">${c.label}</div>
        <div class="text-xl font-bold text-${c.color}-400">${c.value}</div>
      </div>`).join('');
  } catch {}
}

async function loadSessionHistory() {
  const q = document.getElementById('sessSearch').value.trim();
  const status = document.getElementById('sessStatusFilter').value;
  try {
    const res = await fetch(`/api/history?page=${sessPage}&limit=${SESS_LIMIT}&q=${encodeURIComponent(q)}&status=${status}`);
    const data = await res.json();
    sessTotal = data.total || 0;
    const list = document.getElementById('sessionList');

    if (!data.sessions || data.sessions.length === 0) {
      list.innerHTML = '<div class="text-xs text-gray-600 text-center py-10">Chưa có phiên nào' + (q || status ? ' khớp bộ lọc' : '') + '.</div>';
    } else {
      list.innerHTML = data.sessions.map(s => `
        <div class="grid grid-cols-[90px_1fr_150px_70px_90px_130px_70px] gap-2 px-4 py-3 border-b border-slate-750/50 items-center hover:bg-void/40 cursor-pointer transition-colors group" onclick="viewSession('${s.session_id}')">
          <span class="text-[11px] font-mono text-cyan-400">${escapeHtml(s.session_id)}</span>
          <span class="text-xs text-gray-300 truncate">${escapeHtml(s.customer_name || '—')}</span>
          <span class="text-[11px] text-gray-500 truncate">${escapeHtml(s.product || '—')}</span>
          <span class="text-[11px] text-gray-400">${s.turn_count}</span>
          <span class="text-[11px] text-gray-400">${fmtDur(s.duration_seconds)}</span>
          <span class="text-[11px] text-gray-500 font-mono">${fmtTime(s.created_at)}</span>
          <div class="flex items-center gap-1 justify-end">
            ${s.status === 'active'
              ? '<span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span><span class="text-[10px] text-emerald-400">live</span>'
              : `<button onclick="event.stopPropagation(); deleteSessionRecord('${s.session_id}', false)" class="p-1 rounded text-gray-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity" title="Xoá">
                   <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                 </button>`}
          </div>
        </div>`).join('');
    }

    const maxPage = Math.max(1, Math.ceil(sessTotal / SESS_LIMIT));
    document.getElementById('sessPageInfo').textContent = `${sessTotal} phiên · trang ${sessPage}/${maxPage}`;
    document.getElementById('sessPrevBtn').disabled = sessPage <= 1;
    document.getElementById('sessNextBtn').disabled = sessPage >= maxPage;
  } catch (e) {
    document.getElementById('sessionList').innerHTML = `<div class="text-xs text-red-400 text-center py-10">Lỗi tải danh sách: ${e.message}</div>`;
  }
}

function sessSearchChanged() {
  clearTimeout(sessSearchTimer);
  sessSearchTimer = setTimeout(() => { sessPage = 1; loadSessionHistory(); }, 300);
}

function sessFilterChanged() { sessPage = 1; loadSessionHistory(); }
function sessPrevPage() { if (sessPage > 1) { sessPage--; loadSessionHistory(); } }
function sessNextPage() { sessPage++; loadSessionHistory(); }

async function viewSession(id) {
  currentSessId = id;
  try {
    const res = await fetch(`/api/sessions/${id}`);
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    const s = data.session;

    document.getElementById('sessModalTitle').textContent =
      `${s.customer_name || 'Khách'} — ${s.product || ''}`;
    document.getElementById('sessModalMeta').textContent =
      `${id} · ${s.turn_count} lượt · ${fmtDur(s.duration_seconds)}` +
      (s.created_at ? ` · ${fmtTime(s.created_at)}` : '');

    const latByTurn = {};
    (s.latency_log || []).forEach(m => { latByTurn[m.turn] = m; });

    let userTurn = 0;
    const bubbles = (s.history || []).map(t => {
      if (t.role === 'user') {
        userTurn++;
        return `
          <div class="flex justify-end mb-3">
            <div class="max-w-[80%]">
              <div class="msg-bubble-user px-3.5 py-2 text-xs leading-relaxed">${escapeHtml(t.content)}</div>
            </div>
          </div>`;
      }
      const m = latByTurn[userTurn];
      const metaStr = m
        ? ['stt_ms', 'rag_ms', 'ttfa_ms', 'total_ms']
            .filter(k => m[k] != null)
            .map(k => `${k.replace('_ms', '').toUpperCase()} ${m[k]}ms`)
            .join(' · ')
        : '';
      return `
        <div class="flex mb-3">
          <div class="max-w-[80%]">
            <div class="msg-bubble-ai px-3.5 py-2 text-xs leading-relaxed">${escapeHtml(t.content)}</div>
            ${metaStr ? `<div class="text-[9px] text-gray-600 mt-1 font-mono">${metaStr}</div>` : ''}
          </div>
        </div>`;
    }).join('');

    document.getElementById('sessModalBody').innerHTML =
      bubbles || '<div class="text-xs text-gray-600 text-center py-8">Phiên không có nội dung.</div>';
    document.getElementById('sessModal').classList.remove('hidden');
  } catch (e) { alert('Lỗi tải phiên: ' + e.message); }
}

function closeSessModal() {
  document.getElementById('sessModal').classList.add('hidden');
  currentSessId = null;
}

async function deleteSessionRecord(id, fromModal) {
  if (!id) return;
  if (!confirm(`Xoá phiên ${id}? Toàn bộ hội thoại và số liệu của phiên này sẽ mất vĩnh viễn.`)) return;
  try {
    const res = await fetch(`/api/history/${id}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    if (fromModal) closeSessModal();
    loadSessionStats();
    loadSessionHistory();
  } catch (e) { alert('Lỗi xoá: ' + e.message); }
}

// ---- Init ----
window.addEventListener('load', () => {
  document.getElementById('textInput')?.addEventListener('input', schedulePrefetch);
  connectWS();
  loadVoices();
  checkHealth().finally(() => theoDoiTTSNap());
  loadVoiceList();
  loadDatasets();
});

// ============================================================
// Test giọng — so sánh A/B
// ============================================================

const VTEST_PRESETS = [
  ['Số tiền', 'Dạ khoản vay hai trăm triệu đồng trong ba năm thì mỗi tháng anh trả khoảng sáu triệu tám trăm nghìn ạ.'],
  ['Lãi suất', 'Dạ lãi suất ưu đãi chỉ từ sáu phẩy năm phần trăm một năm trong hai năm đầu ạ.'],
  ['Số điện thoại', 'Dạ anh cho em xin lại số điện thoại không chín một hai, ba bốn năm, sáu bảy tám ạ.'],
  ['Ngày tháng', 'Dạ hồ sơ của anh sẽ được duyệt trước ngày mười lăm tháng ba năm hai nghìn không trăm hai mươi sáu ạ.'],
  ['Từ chối', 'Dạ em xin lỗi đã làm phiền anh chị ạ. Em cảm ơn và chúc anh chị một ngày tốt lành ạ.'],
];

let vtestWavs = { A: null, B: null };
let vtestInited = false;

function initVoiceTest() {
  if (!vtestInited) {
    const box = document.getElementById('vtestPresets');
    box.innerHTML = VTEST_PRESETS.map((p, i) =>
      `<button onclick="useVoiceTestPreset(${i})" class="px-3 py-1.5 rounded-lg bg-void border border-slate-750 text-[11px] text-gray-400 hover:text-cyan-400 hover:border-cyan-500/30 transition-colors">${escapeHtml(p[0])}</button>`
    ).join('');
    vtestInited = true;
  }
  loadVoiceTestVoices();
}

function useVoiceTestPreset(i) {
  document.getElementById('vtestText').value = VTEST_PRESETS[i][1];
}

async function loadVoiceTestVoices() {
  const warn = document.getElementById('vtestWarn');
  try {
    const [voicesRes, healthRes] = await Promise.all([
      fetch('/api/voices').then(r => r.json()),
      fetch('/api/health').then(r => r.json()),
    ]);
    const voices = voicesRes.voices || [];
    const opts = voices.map(v => `<option value="${escapeHtml(v.name)}">${escapeHtml(v.name)}</option>`).join('');
    const selA = document.getElementById('vtestVoiceA');
    const selB = document.getElementById('vtestVoiceB');
    selA.innerHTML = opts;
    selB.innerHTML = opts;
    if (voices.length > 1) selB.selectedIndex = 1;

    const ttsState = (healthRes.services || {}).tts;
    if (ttsState !== 'loaded') {
      warn.textContent = 'TTS chưa được tải nên chưa tổng hợp được. Vào tab "Cài Model" cài F5-TTS ViVoice, rồi bấm nạp model.';
      warn.classList.remove('hidden');
    } else if (!voices.length) {
      warn.textContent = 'Chưa có giọng mẫu nào. Vào tab "Giọng nói" upload một file WAV 5-10 giây kèm transcript.';
      warn.classList.remove('hidden');
    } else {
      warn.classList.add('hidden');
    }
  } catch (err) {
    warn.textContent = 'Không đọc được danh sách giọng: ' + err.message;
    warn.classList.remove('hidden');
  }
}

async function synthOne(slot, voice, text, fast) {
  const meta = document.getElementById('vtestMeta' + slot);
  const audio = document.getElementById('vtestAudio' + slot);
  const dl = document.getElementById('vtestDl' + slot);
  meta.textContent = 'Đang tổng hợp…';
  audio.removeAttribute('src');
  dl.classList.add('hidden');

  const fd = new FormData();
  fd.append('text', text);
  fd.append('voice_name', voice);
  fd.append('fast', fast ? 'true' : 'false');

  try {
    const res = await fetch('/api/voices/test-tts', { method: 'POST', body: fd });
    const data = await res.json();
    if (data.error) { meta.textContent = data.error; return; }
    audio.src = 'data:audio/wav;base64,' + data.audio;
    vtestWavs[slot] = { b64: data.audio, voice };
    dl.classList.remove('hidden');
    const rtf = data.rtf != null ? ` · RTF ${data.rtf}` : '';
    meta.textContent = `${data.elapsed_ms} ms tổng hợp · ${(data.duration_ms / 1000).toFixed(1)}s audio${rtf}`;
  } catch (err) {
    meta.textContent = 'Lỗi: ' + err.message;
  }
}

async function runVoiceTest() {
  const text = document.getElementById('vtestText').value.trim();
  if (!text) return;
  const btn = document.getElementById('vtestBtn');
  const status = document.getElementById('vtestStatus');
  const fast = document.getElementById('vtestFast').checked;
  const a = document.getElementById('vtestVoiceA').value;
  const b = document.getElementById('vtestVoiceB').value;
  if (!a && !b) { status.textContent = 'Chưa có giọng nào để test.'; return; }

  btn.disabled = true;
  btn.classList.add('opacity-50');
  status.textContent = 'Đang chạy…';
  // Tuần tự, không song song: TTS chỉ có một worker, chạy song song thì con số
  // độ trễ đo được sẽ gồm cả thời gian xếp hàng của giọng kia.
  if (a) await synthOne('A', a, text, fast);
  if (b) await synthOne('B', b, text, fast);
  status.textContent = a === b ? 'Hai bên cùng một giọng — đổi giọng B để so sánh.' : '';
  btn.disabled = false;
  btn.classList.remove('opacity-50');
}

function downloadVoiceTest(slot) {
  const item = vtestWavs[slot];
  if (!item) return;
  const bin = atob(item.b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const url = URL.createObjectURL(new Blob([bytes], { type: 'audio/wav' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = `test_${item.voice}.wav`;
  a.click();
  URL.revokeObjectURL(url);
}

// ============================================================
// Training giọng
// ============================================================

let vtrainScript = [];
let vtrainRecorded = {};      // "001" -> {duration_s,...}
let vtrainIdx = 0;
let vtrainVoice = '';
let vtrainRec = null;         // MediaRecorder đang chạy
let vtrainChunks = [];
let vtrainStream = null;
let vtrainCtx = null;         // AudioContext riêng: audioContext toàn cục bị
                              // khoá ở 16kHz/24kHz tuỳ luồng nào chạy trước
let vtrainJobId = null;
let vtrainTimer = null;

function vtrainMsg(text, tone = 'gray') {
  const el = document.getElementById('vtrainRecMsg');
  el.className = `text-[11px] mt-3 text-${tone}-400`;
  el.textContent = text;
}

async function initVoiceTraining() {
  if (!vtrainScript.length) {
    try {
      const data = await fetch('/api/voice-training/script').then(r => r.json());
      vtrainScript = data.sentences || [];
      document.getElementById('vtrainTotal').textContent = vtrainScript.length;
    } catch (err) {
      vtrainMsg('Không đọc được kịch bản: ' + err.message, 'red');
    }
  }
  await refreshVoiceTrainStatus();
}

async function refreshVoiceTrainStatus() {
  let st;
  try {
    st = await fetch('/api/voice-training/status?voice_name=' + encodeURIComponent(vtrainVoice)).then(r => r.json());
  } catch { return; }

  // Danh sách bộ thu âm đã có
  const chips = document.getElementById('vtrainVoices');
  chips.innerHTML = (st.voices || []).length
    ? '<span class="text-[10px] text-gray-600 mr-1 self-center">Đã có:</span>' + st.voices.map(v =>
        `<button onclick="openVoiceTrainSet('${escapeHtml(v)}')" class="px-2.5 py-1 rounded-lg bg-void border border-slate-750 text-[11px] ${v === vtrainVoice ? 'text-violet-400 border-violet-500/30' : 'text-gray-400'} hover:text-violet-400">${escapeHtml(v)}</button>`
      ).join('')
    : '';

  // Chặn train khi không có GPU
  const warn = document.getElementById('vtrainGpuWarn');
  const trainBtn = document.getElementById('vtrainTrainBtn');
  if (!st.gpu_ok) {
    warn.textContent = `Máy này chạy trên "${st.device}"${st.gpu_name ? ' (' + st.gpu_name + ')' : ''}. `
      + 'Fine-tune F5-TTS cần GPU NVIDIA. Thu âm và chuẩn hoá dataset vẫn làm được ở đây, '
      + 'nhưng bước train phải mở giao diện trên máy có RTX.';
    warn.classList.remove('hidden');
    trainBtn.disabled = true;
    trainBtn.classList.add('opacity-40', 'cursor-not-allowed');
  } else {
    warn.classList.add('hidden');
    trainBtn.disabled = false;
    trainBtn.classList.remove('opacity-40', 'cursor-not-allowed');
  }

  if (vtrainVoice) {
    const mins = st.total_seconds / 60;
    const enough = st.enough_audio ? '' : ` · cần ≥ ${st.min_minutes} phút`;
    document.getElementById('vtrainTienDo').innerHTML =
      `Đã thu <span class="${st.enough_audio ? 'text-emerald-400' : 'text-cyan-400'}">${st.recorded}</span>/${st.total_sentences}`
      + ` · ${mins.toFixed(1)} phút${enough}`;
  }

  // TỰ QUYẾT ô "dùng nhận dạng giọng nói" theo NGUỒN của bản thu, thay vì bắt
  // người dùng nhớ. Cắt từ file dài thì nội dung không khớp kịch bản 60 câu -
  // tắt nhận dạng là mọi mẫu bị gán nhầm lời, và lỗi chỉ lộ ra sau vài giờ
  // train. Khoá luôn ô để không tắt nhầm; backend cũng tự ép, đây chỉ là để
  // người dùng NHÌN THẤY vì sao.
  const oAsr = document.getElementById('vtrainUseAsr');
  const ghi = document.getElementById('vtrainAsrVi');
  if (oAsr) {
    if (st.can_nhan_dang) {
      oAsr.checked = true;
      oAsr.disabled = true;
      if (ghi) ghi.textContent = 'Tự bật: bản thu cắt từ file dài, không khớp kịch bản 60 câu.';
    } else {
      oAsr.disabled = false;
      if (ghi) ghi.textContent = '';
    }
  }

  // Có job đang chạy (ví dụ vừa reload trang) thì bám theo tiếp
  if (st.running_job && !vtrainJobId) {
    vtrainJobId = st.running_job;
    pollVoiceTrainJob();
  }
  return st;
}

async function openVoiceTrainSet(name) {
  document.getElementById('vtrainName').value = name;
  await loadVoiceTraining();
}

// 'Giọng Lan' -> 'giong_lan'. Phải khớp safe_voice_name() bên
// backend/api/voice_training.py: bỏ dấu trước, nếu không "giọng" thành "gi_ng".
function safeVoiceName(raw) {
  return (raw || '').trim().toLowerCase()
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/đ/g, 'd')
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

async function loadVoiceTraining() {
  const oName = document.getElementById('vtrainName');
  const name = safeVoiceName(oName.value);
  if (!name) {
    // Báo Ở NGAY Ô NHẬP, không chỉ ở khối bước 2. Người dùng bấm "Mở bộ thu âm"
    // rồi nhìn xuống thấy trang không đổi gì và tưởng nút hỏng - dòng chữ nhỏ
    // trong bước 2 quá kín để nhận ra. Đã có người báo đúng triệu chứng đó.
    vtrainMsg('Nhập tên giọng trước.', 'red');
    oName.classList.add('ring-2', 'ring-red-500');
    oName.focus();
    oName.placeholder = 'Nhập tên giọng ở đây, vd: giong_lan';
    setTimeout(() => oName.classList.remove('ring-2', 'ring-red-500'), 2500);
    return;
  }
  oName.classList.remove('ring-2', 'ring-red-500');
  document.getElementById('vtrainName').value = name;
  vtrainVoice = name;

  document.getElementById('vtrainRecorder').classList.remove('hidden');
  document.getElementById('vtrainRecorderEmpty').classList.add('hidden');

  await reloadVoiceTrainRecordings();
  // Nhảy tới câu đầu tiên chưa thu
  const firstGap = vtrainScript.findIndex(s => !vtrainRecorded[s.no]);
  vtrainIdx = firstGap === -1 ? 0 : firstGap;
  renderVoiceTrainSentence();
}

async function reloadVoiceTrainRecordings() {
  try {
    const data = await fetch('/api/voice-training/recordings?voice_name=' + encodeURIComponent(vtrainVoice)).then(r => r.json());
    vtrainRecorded = {};
    (data.recordings || []).forEach(r => { vtrainRecorded[r.no] = r; });
  } catch { /* giữ nguyên state cũ */ }
  renderVoiceTrainGrid();
  await refreshVoiceTrainStatus();
}

function renderVoiceTrainGrid() {
  document.getElementById('vtrainGrid').innerHTML = vtrainScript.map((s, i) => {
    const done = !!vtrainRecorded[s.no];
    const cur = i === vtrainIdx;
    const cls = done ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                     : 'bg-void text-gray-600 border-slate-750';
    return `<button onclick="jumpVoiceTrain(${i})" title="Câu ${s.no}"
      class="w-7 h-7 rounded border text-[9px] font-mono ${cls} ${cur ? 'ring-1 ring-cyan-400' : ''} hover:text-cyan-400">${s.no}</button>`;
  }).join('');
}

function renderVoiceTrainSentence() {
  const s = vtrainScript[vtrainIdx];
  if (!s) return;
  document.getElementById('vtrainNo').textContent = s.no;
  document.getElementById('vtrainGroup').textContent = s.group || '';
  document.getElementById('vtrainSentence').textContent = s.text;

  const rec = vtrainRecorded[s.no];
  document.getElementById('vtrainPlayBtn').classList.toggle('hidden', !rec);
  document.getElementById('vtrainDelBtn').classList.toggle('hidden', !rec);
  vtrainMsg(rec ? `Đã thu ${rec.duration_s}s (${rec.sample_rate} Hz)` : 'Chưa thu câu này.');
  renderVoiceTrainGrid();
}

function jumpVoiceTrain(i) {
  if (vtrainRec) return;
  vtrainIdx = i;
  renderVoiceTrainSentence();
}

function stepVoiceTrain(delta) {
  if (vtrainRec) return;
  const next = vtrainIdx + delta;
  if (next < 0 || next >= vtrainScript.length) return;
  vtrainIdx = next;
  renderVoiceTrainSentence();
}

async function toggleVoiceTrainRecord() {
  if (vtrainRec) { stopVoiceTrainRecord(); return; }

  const btn = document.getElementById('vtrainRecBtn');
  try {
    vtrainStream = await layMic({
      audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false }
    });
  } catch (err) {
    vtrainMsg('Không mở được microphone: ' + err.message, 'red');
    return;
  }

  vtrainChunks = [];
  vtrainRec = new MediaRecorder(vtrainStream);
  vtrainRec.ondataavailable = e => { if (e.data.size > 0) vtrainChunks.push(e.data); };
  vtrainRec.onstop = onVoiceTrainRecStop;
  vtrainRec.start();

  btn.textContent = '■ Dừng';
  btn.classList.replace('bg-red-500/15', 'bg-red-500/30');
  vtrainMsg('Đang thu… đọc tự nhiên như đang nói điện thoại.', 'red');
}

function stopVoiceTrainRecord() {
  if (vtrainRec && vtrainRec.state !== 'inactive') vtrainRec.stop();
}

async function onVoiceTrainRecStop() {
  const btn = document.getElementById('vtrainRecBtn');
  btn.textContent = '● Thu';
  btn.classList.replace('bg-red-500/30', 'bg-red-500/15');

  const blob = new Blob(vtrainChunks, { type: vtrainRec.mimeType || 'audio/webm' });
  vtrainStream.getTracks().forEach(t => t.stop());
  vtrainRec = null;
  vtrainStream = null;

  const s = vtrainScript[vtrainIdx];
  vtrainMsg('Đang lưu…');

  try {
    // Không ép sampleRate: giữ nguyên rate gốc của thiết bị và báo lên server.
    // prepare_dataset.py hạ về 24kHz mono ở bước sau.
    if (!vtrainCtx) vtrainCtx = new AudioContext();
    const buf = await vtrainCtx.decodeAudioData(await blob.arrayBuffer());
    const ch = buf.getChannelData(0);
    const pcm = new Int16Array(ch.length);
    for (let i = 0; i < ch.length; i++) {
      const v = Math.max(-1, Math.min(1, ch[i]));
      pcm[i] = v < 0 ? v * 0x8000 : v * 0x7FFF;
    }

    const res = await fetch(`/api/voice-training/recordings/${s.no}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        voice_name: vtrainVoice,
        sample_rate: Math.round(buf.sampleRate),
        pcm_b64: arrayBufferToBase64(pcm.buffer),
      }),
    });
    const data = await res.json();
    if (data.error) { vtrainMsg(data.error, 'red'); return; }

    vtrainRecorded[s.no] = data;
    await reloadVoiceTrainRecordings();
    renderVoiceTrainSentence();
    vtrainMsg(`Đã lưu ${data.duration_s}s. Nghe lại hoặc sang câu sau.`, 'emerald');
  } catch (err) {
    vtrainMsg('Lỗi xử lý audio: ' + err.message, 'red');
  }
}

function playVoiceTrainTake() {
  const s = vtrainScript[vtrainIdx];
  const audio = document.getElementById('vtrainAudio');
  // Thẻ này bị ẩn (không có thanh điều khiển) nên bấm lại là cách DUY NHẤT để
  // dừng - phải xử lý, không thì nghe lại một câu thu hỏng vẫn phải chờ hết.
  if (!audio.paused) { audio.pause(); return; }
  dungHetTieng();
  audio.src = `/api/voice-training/recordings/${s.no}/audio?voice_name=${encodeURIComponent(vtrainVoice)}&t=${Date.now()}`;
  audio.play().catch(() => {});
}

async function deleteVoiceTrainTake() {
  const s = vtrainScript[vtrainIdx];
  await fetch(`/api/voice-training/recordings/${s.no}?voice_name=${encodeURIComponent(vtrainVoice)}`, { method: 'DELETE' });
  delete vtrainRecorded[s.no];
  await reloadVoiceTrainRecordings();
  renderVoiceTrainSentence();
}

async function uploadVoiceTrainFiles() {
  const input = document.getElementById('vtrainUploadFiles');
  const msg = document.getElementById('vtrainUploadMsg');
  if (!input.files.length) { msg.textContent = 'Chưa chọn file nào.'; return; }

  const fd = new FormData();
  fd.append('voice_name', vtrainVoice);
  for (const f of input.files) fd.append('files', f);

  msg.textContent = 'Đang upload…';
  try {
    const data = await fetch('/api/voice-training/recordings/upload', { method: 'POST', body: fd }).then(r => r.json());
    if (data.error) { msg.textContent = data.error; return; }
    const bo = data.skipped || [];
    const skipped = bo.map(s => `${s.file} (${s.reason})`).join(', ');
    msg.innerHTML = `Nhận ${data.saved.length} file.`
      + (skipped ? ` <span class="text-amber-400">Bỏ qua: ${escapeHtml(skipped)}</span>` : '');
    // Khi TẤT CẢ bị bỏ vì tên file, nói luôn phải làm gì. Lý do "tên file không
    // phải số thứ tự câu" đúng nhưng không chỉ ra cách sửa, và người dùng nhìn
    // ra thành "upload hỏng". Tên phải là số câu vì transcript lấy theo kịch
    // bản 60 câu - sai số là train ra giọng đọc sai lời.
    if (!data.saved.length && bo.some(s => /số thứ tự/.test(s.reason || ''))) {
      msg.innerHTML += `<div class="mt-1 text-amber-300">Đổi tên file thành số câu rồi upload lại:
        <b>001.wav</b>, <b>002.wav</b>… đúng theo thứ tự trong kịch bản 60 câu bên trên.
        File thu ngoài kịch bản thì vẫn đánh số, rồi tích
        "Dùng PhoWhisper cho file ngoài kịch bản" ở bước 3.</div>`;
    }
    input.value = '';
    await reloadVoiceTrainRecordings();
    renderVoiceTrainSentence();
  } catch (err) {
    msg.textContent = 'Lỗi upload: ' + err.message;
  }
}

async function uploadVoiceTrainLong() {
  const input = document.getElementById('vtrainLongFile');
  const msg = document.getElementById('vtrainLongMsg');
  if (!vtrainVoice) { msg.textContent = 'Nhập tên giọng rồi bấm "Mở bộ thu âm" trước.'; return; }
  if (!input.files.length) { msg.textContent = 'Chưa chọn file nào.'; return; }

  const f = input.files[0];
  const fd = new FormData();
  fd.append('voice_name', vtrainVoice);
  fd.append('file', f);

  // File 30-60 phút nặng vài trăm MB: báo rõ đang tải lên, không thì người dùng
  // tưởng treo rồi bấm lại và tạo hai job cùng lúc.
  msg.textContent = `Đang tải lên ${(f.size / 1048576).toFixed(0)} MB…`;
  try {
    const data = await fetch('/api/voice-training/recordings/upload-long',
                             { method: 'POST', body: fd }).then(r => r.json());
    if (data.error) { msg.textContent = data.error; return; }
    input.value = '';
    msg.textContent = 'Đang cắt…';
    vtrainJobId = data.id;
    theoDoiJobCatDai();
  } catch (err) {
    msg.textContent = 'Lỗi upload: ' + err.message;
  }
}

async function theoDoiJobCatDai() {
  const msg = document.getElementById('vtrainLongMsg');
  while (vtrainJobId) {
    const job = await fetch('/api/voice-training/jobs/' + vtrainJobId).then(r => r.json());
    vtrainLog((job.lines || []).join('\n'));
    if (job.status !== 'running') {
      vtrainJobId = null;
      if (job.status === 'error') { msg.textContent = 'Cắt thất bại — xem Log bên dưới.'; return; }
      await reloadVoiceTrainRecordings();
      renderVoiceTrainSentence();
      msg.innerHTML = 'Cắt xong. <span class="text-amber-300">Nhớ tích "Dùng PhoWhisper '
        + 'cho file ngoài kịch bản" ở bước 3 — các đoạn vừa cắt không khớp kịch bản 60 câu.</span>';
      return;
    }
    await new Promise(r => setTimeout(r, 1500));
  }
}

// ---- Job: chuẩn hoá + train ----

function vtrainLog(text) {
  const el = document.getElementById('vtrainLog');
  el.textContent = text;
  el.scrollTop = el.scrollHeight;
}

async function startVoiceJob(path, body, label) {
  if (!vtrainVoice) { vtrainLog('Chưa chọn giọng.'); return; }
  document.getElementById('vtrainDone').classList.add('hidden');
  vtrainLog(label + '…');
  try {
    const data = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(r => r.json());
    if (data.error) { vtrainLog(data.error); return; }
    vtrainJobId = data.id;
    pollVoiceTrainJob();
  } catch (err) {
    vtrainLog('Lỗi: ' + err.message);
  }
}

function startVoicePrepare() {
  startVoiceJob('/api/voice-training/prepare', {
    voice_name: vtrainVoice,
    use_asr: document.getElementById('vtrainUseAsr').checked,
  }, 'Chuẩn hoá dataset');
}

function startVoiceTrain() {
  startVoiceJob('/api/voice-training/train', {
    voice_name: vtrainVoice,
    epochs: parseInt(document.getElementById('vtrainEpochs').value, 10) || 100,
    batch_size: parseInt(document.getElementById('vtrainBatch').value, 10) || 3200,
  }, 'Bắt đầu train');
}

function stopVoiceTrainPoll() {
  if (vtrainTimer) clearInterval(vtrainTimer);
  vtrainTimer = null;
  document.getElementById('vtrainCancelBtn').classList.add('hidden');
}

function pollVoiceTrainJob() {
  stopVoiceTrainPoll();
  document.getElementById('vtrainCancelBtn').classList.remove('hidden');

  const tick = async () => {
    if (!vtrainJobId) return;
    try {
      const job = await fetch('/api/voice-training/jobs/' + vtrainJobId).then(r => r.json());
      if (job.error) { stopVoiceTrainPoll(); vtrainLog('Lỗi: ' + job.error); return; }

      vtrainLog(job.lines.join('\n'));

      // train.sh in mốc "=== [n/4] ... ===" — bám để hiện bước hiện tại
      const step = [...job.lines].reverse().find(l => /^===\s*\[\d\/\d\]/.test(l));
      const label = { running: 'đang chạy', done: 'xong', error: 'lỗi', cancelled: 'đã hủy' }[job.status] || job.status;
      document.getElementById('vtrainJobStatus').textContent =
        `${label} · ${fmtThoiGian(job.elapsed_s)}`
        + (step && job.status === 'running' ? ` · ${step.replace(/=/g, '').trim()}` : '');

      veTienDoGiong(job);

      if (job.status !== 'running') {
        stopVoiceTrainPoll();
        if (job.status === 'done' && job.component === 'train') showVoiceTrainDone();
        vtrainJobId = null;
        reloadVoiceTrainRecordings();
      }
    } catch (err) {
      stopVoiceTrainPoll();
      vtrainLog('Mất kết nối: ' + err.message);
    }
  };
  tick();
  vtrainTimer = setInterval(tick, 1500);
}

/** Vẽ tiến độ train giọng bằng số backend bóc từ tqdm (xem core/jobs.py).
 *
 *  Điểm quan trọng nhất là ETA: tqdm chỉ biết vòng lặp của epoch hiện tại nên
 *  in "còn 02:00" trong khi cả buổi còn gần ba tiếng. Khi backend tính được
 *  ETA toàn buổi thì nói rõ; khi không thì ghi "epoch này" để người dùng không
 *  đọc nhầm thành thời gian còn lại của cả buổi.
 */
function veTienDoGiong(job) {
  const khung = document.getElementById('vtrainTienDo');
  if (!khung) return;
  const p = job.progress;
  if (!p || job.status !== 'running') {
    if (job.status !== 'running') khung.classList.add('hidden');
    return;
  }
  khung.classList.remove('hidden');

  const pct = p.percent ?? 0;
  document.getElementById('vtrainBar').style.width = pct + '%';
  document.getElementById('vtrainPct').textContent = pct + '%';
  document.getElementById('vtrainEta').textContent =
    p.eta_s != null
      ? 'còn ' + fmtThoiGian(p.eta_s) + (p.eta_toan_buoi ? '' : ' (epoch này)')
      : 'đang ước lượng…';

  document.getElementById('vtrainEpoch').textContent = p.epoch || '—';
  document.getElementById('vtrainStep').textContent =
    p.buoc_trong_epoch || (p.step != null ? `${p.step}/${p.total}` : '—');
  document.getElementById('vtrainLoss').textContent = p.loss ?? '—';
  document.getElementById('vtrainSpeed').textContent =
    p.giay_moi_buoc != null ? p.giay_moi_buoc + 's/bước' : '—';

  // Giải nghĩa "sai số" bằng lời: người vận hành không biết loss là gì, mà đây
  // là chỉ dấu duy nhất cho biết buổi train có ăn thua hay không.
  const gt = document.getElementById('vtrainGiaiThich');
  if (gt) {
    const loss = parseFloat(p.loss);
    gt.textContent = isNaN(loss) ? ''
      : 'Sai số càng nhỏ càng giống giọng mẫu. '
        + (loss > 1 ? 'Đang còn cao — mới bắt đầu học, cứ để chạy tiếp.'
          : loss > 0.5 ? 'Đang giảm bình thường.'
            : 'Đã thấp — giọng đang bám sát mẫu.');
  }
}

function showVoiceTrainDone() {
  const el = document.getElementById('vtrainDone');
  el.innerHTML = `Train xong. Sửa <code class="text-white">.env</code> rồi khởi động lại dịch vụ:<br>`
    + `<span class="font-mono text-[10px] text-gray-300">`
    + `F5TTS_CKPT_PATH=./models/tts/finetuned/${escapeHtml(vtrainVoice)}/model_last.pt<br>`
    + `F5TTS_VOCAB_PATH=./models/tts/finetuned/${escapeHtml(vtrainVoice)}/vocab.txt<br>`
    + `F5TTS_REF_AUDIO=./models/tts/ref_voices/${escapeHtml(vtrainVoice)}.wav`
    + `</span>`;
  el.classList.remove('hidden');
}

async function cancelVoiceTrainJob() {
  if (!vtrainJobId) return;
  await fetch(`/api/voice-training/jobs/${vtrainJobId}/cancel`, { method: 'POST' });
}

// ============================================================================
// Tri thức AI — tài liệu bot đọc để tư vấn
// ============================================================================
//
// Vì sao là một trang riêng chứ không nhét vào "Nguồn dữ liệu": hai thứ khác
// bản chất. Nguồn dữ liệu NỐI tới file ngoài và nạp lại theo lịch (bảng lớn hay
// đổi). Ở đây là tài liệu tĩnh của hệ thống — mô tả sản phẩm, điều kiện — và
// người vận hành cần SỬA ĐƯỢC TRỰC TIẾP, vì đây là chỗ duy nhất quyết định con
// số bot đọc cho khách.

const KN_NHAN_NHOM = {
  products: 'Sản phẩm',
  faq: 'Câu hỏi thường gặp',
  chinh_sach: 'Chính sách',
};

function knByte(n) {
  return n < 1024 ? n + ' B' : (n / 1024).toFixed(1) + ' KB';
}

async function loadTriThuc() {
  const tb = document.getElementById('knRows');
  if (!tb) return;
  try {
    const d = await fetch('/api/knowledge').then(r => r.json());
    const ds = d.tai_lieu || [];
    if (!ds.length) {
      tb.innerHTML = '<tr><td colspan="6" class="text-center text-gray-600 py-8 text-xs">'
        + 'Chưa có tài liệu nào. Bot sẽ không có gì để tư vấn.</td></tr>';
    } else {
      tb.innerHTML = ds.map(t => {
        // so_manh = 0 nghĩa là file có trên đĩa nhưng RAG CHƯA đọc. Phải nói
        // thẳng: người dùng sửa xong tưởng đã xong, mà bot vẫn trả lời bản cũ.
        const doc = t.so_manh > 0
          ? `<span class="text-emerald-400">${t.so_manh} mảnh</span>`
          : '<span class="text-amber-400">chưa nạp</span>';
        return `<tr>
          <td class="font-medium text-white">${escapeHtml(t.ten)}</td>
          <td class="text-gray-400">${escapeHtml(KN_NHAN_NHOM[t.nhom] || t.nhom)}</td>
          <td class="text-gray-500 font-mono text-[11px]">${knByte(t.kich_thuoc)}</td>
          <td class="text-[11px]">${doc}</td>
          <td class="text-gray-500 text-[11px]">${new Date(t.sua_doi * 1000).toLocaleString('vi-VN')}</td>
          <td class="text-right whitespace-nowrap">
            <button onclick="soanTaiLieu('${escapeHtml(t.nhom)}','${escapeHtml(t.ten)}')"
                    class="px-2 py-1 rounded-md text-[10px] text-gray-400 hover:text-cyan-400 hover:bg-cyan-500/10">Sửa</button>
            <button onclick="xoaTaiLieu('${escapeHtml(t.nhom)}','${escapeHtml(t.ten)}')"
                    class="px-2 py-1 rounded-md text-[10px] text-gray-500 hover:text-red-400 hover:bg-red-500/10">Xoá</button>
          </td></tr>`;
      }).join('');
    }

    // Cảnh báo dữ liệu mẫu: đây là lý do bot đọc lãi suất bịa cho khách. Ai mở
    // trang này cũng phải thấy ngay, không phải đi tìm.
    const cb = document.getElementById('knCanhBao');
    if (cb) {
      const mau = ds.filter(t => ['vay_tin_chap', 'vay_mua_nha', 'the_tin_dung', 'faq_banking']
        .includes(t.ten)).length;
      if (mau) {
        cb.classList.remove('hidden');
        cb.innerHTML = `Đang còn <b>${mau}</b> tài liệu MẪU của "Ngân hàng ABC" — `
          + 'lãi suất, hạn mức trong đó là số bịa để chạy thử. Bot đang đọc chính '
          + 'những số này cho khách. Sửa hoặc thay bằng dữ liệu thật trước khi gọi.';
      } else {
        cb.classList.add('hidden');
      }
    }
  } catch (e) {
    tb.innerHTML = `<tr><td colspan="6" class="text-center text-red-400 py-8 text-xs">Lỗi: ${escapeHtml(e.message)}</td></tr>`;
  }
}

async function uploadTriThuc() {
  const inp = document.getElementById('knFile');
  const box = document.getElementById('knUpKetQua');
  if (!inp.files.length) { alert('Chọn file trước đã'); return; }

  const btn = document.getElementById('knUpBtn');
  btn.disabled = true; btn.textContent = 'Đang tải…';
  const fd = new FormData();
  fd.append('file', inp.files[0]);
  fd.append('nhom', document.getElementById('knNhom').value);
  try {
    const d = await fetch('/api/knowledge/upload', { method: 'POST', body: fd }).then(r => r.json());
    box.classList.remove('hidden');
    if (d.error) {
      box.className = 'mt-3 text-[11px] text-red-300';
      box.textContent = d.error;
    } else {
      box.className = 'mt-3 text-[11px] text-emerald-300';
      box.innerHTML = `Đã ${d.ghi_de ? 'ghi đè' : 'thêm'} <b>${escapeHtml(d.ten)}</b> — `
        + `${d.so_dong} dòng, AI đọc được ${d.so_manh} mảnh.`
        + `<pre class="mt-2 text-[10px] text-gray-500 bg-void/50 rounded p-2 overflow-x-auto">${escapeHtml(d.xem_truoc || '')}</pre>`;
      inp.value = '';
      loadTriThuc();
    }
  } catch (e) {
    box.classList.remove('hidden');
    box.className = 'mt-3 text-[11px] text-red-300';
    box.textContent = 'Lỗi: ' + e.message;
  } finally {
    btn.disabled = false; btn.textContent = 'Tải lên';
  }
}

async function soanTaiLieu(nhom, ten) {
  const kh = document.getElementById('knEditor');
  document.getElementById('knEditTitle').textContent = ten ? 'Sửa: ' + ten : 'Soạn tài liệu mới';
  document.getElementById('knEditTen').value = ten || '';
  document.getElementById('knEditNhom').value = nhom || 'products';
  const ta = document.getElementById('knEditNoiDung');
  ta.value = ten ? 'Đang tải…' : '';
  kh.classList.remove('hidden');
  if (ten) {
    const d = await fetch(`/api/knowledge/noi-dung?nhom=${encodeURIComponent(nhom)}&ten=${encodeURIComponent(ten)}`)
      .then(r => r.json());
    ta.value = d.error ? ('Lỗi: ' + d.error) : (d.noi_dung || '');
  }
}

function dongSoanTaiLieu() {
  document.getElementById('knEditor').classList.add('hidden');
}

async function luuTaiLieu() {
  const ten = document.getElementById('knEditTen').value.trim();
  if (!ten) { alert('Đặt tên file đã'); return; }
  const btn = document.getElementById('knLuuBtn');
  btn.disabled = true; btn.textContent = 'Đang lưu…';
  const fd = new FormData();
  fd.append('nhom', document.getElementById('knEditNhom').value);
  fd.append('ten', ten);
  fd.append('noi_dung', document.getElementById('knEditNoiDung').value);
  try {
    const d = await fetch('/api/knowledge/luu', { method: 'POST', body: fd }).then(r => r.json());
    if (d.error) { alert(d.error); return; }
    dongSoanTaiLieu();
    loadTriThuc();
  } catch (e) {
    alert('Lỗi: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Lưu và nạp cho AI';
  }
}

async function xoaTaiLieu(nhom, ten) {
  if (!confirm(`Xoá tài liệu "${ten}"? Bot sẽ không còn tra được nội dung này.`)) return;
  const d = await fetch(`/api/knowledge?nhom=${encodeURIComponent(nhom)}&ten=${encodeURIComponent(ten)}`,
                        { method: 'DELETE' }).then(r => r.json());
  if (d.error) { alert(d.error); return; }
  loadTriThuc();
}

async function napLaiTriThuc() {
  if (!confirm('Nạp lại toàn bộ tài liệu vào kho tri thức của AI?')) return;
  const d = await fetch('/api/knowledge/nap-lai', { method: 'POST' }).then(r => r.json());
  if (d.error) { alert(d.error); return; }
  alert(`Đã nạp lại ${d.so_tai_lieu} tài liệu trong ${d.ms}ms.`);
  loadTriThuc();
}

// ---- Upload cho Nguồn dữ liệu ----------------------------------------------

async function uploadNguonDuLieu() {
  const inp = document.getElementById('dsFile');
  const box = document.getElementById('dsUpKetQua');
  if (!inp.files.length) { alert('Chọn file trước đã'); return; }

  const btn = document.getElementById('dsUpBtn');
  btn.disabled = true; btn.textContent = 'Đang tải…';
  const fd = new FormData();
  fd.append('file', inp.files[0]);
  try {
    const d = await fetch('/api/data-sources/upload', { method: 'POST', body: fd }).then(r => r.json());
    box.classList.remove('hidden');
    if (d.error) {
      box.className = 'mt-3 text-[11px] text-red-300';
      box.textContent = d.error;
      return;
    }
    const ct = d.cau_truc || {};
    const bang = ct.bang || [];
    // Hiện danh sách bảng kèm cột: người dùng CHỌN thay vì gõ mò tên bảng và
    // tên cột khoá - hai chỗ gõ sai hay gặp nhất, mà lỗi báo ra rất chung chung.
    let html = `<div class="text-emerald-300 mb-2">Đã tải lên <b>${escapeHtml(d.ten_tep)}</b> `
      + `(${knByte(d.kich_thuoc)}) — loại <b>${escapeHtml(d.kind)}</b></div>`
      + `<div class="text-gray-500 mb-2">Đường dẫn: <span class="font-mono text-gray-400">${escapeHtml(d.path)}</span></div>`;
    if (ct.loi) {
      html += `<div class="text-amber-300">${escapeHtml(ct.loi)}</div>`;
    } else if (!bang.length) {
      html += '<div class="text-amber-300">Không thấy bảng nào bên trong.</div>';
    } else {
      html += `<div class="text-gray-400 mb-1">${bang.length} ${d.kind === 'sqlite' ? 'bảng' : 'sheet'} bên trong — bấm để dùng:</div>`
        + '<div class="space-y-1">' + bang.map(b => `
          <button onclick="dungBangNay('${escapeHtml(d.path)}','${escapeHtml(d.kind)}','${escapeHtml(b.ten)}')"
                  class="w-full text-left bg-void/50 hover:bg-void rounded-lg px-3 py-2 transition-colors">
            <span class="text-white font-mono">${escapeHtml(b.ten)}</span>
            <span class="text-gray-500"> · ${b.so_dong == null ? '?' : b.so_dong} dòng</span>
            <div class="text-gray-600 text-[10px] mt-0.5">${escapeHtml((b.cot || []).slice(0, 12).join(', ')) || 'không đọc được cột'}</div>
          </button>`).join('') + '</div>';
    }
    box.className = 'mt-3 text-[11px]';
    box.innerHTML = html;
    inp.value = '';
  } catch (e) {
    box.classList.remove('hidden');
    box.className = 'mt-3 text-[11px] text-red-300';
    box.textContent = 'Lỗi: ' + e.message;
  } finally {
    btn.disabled = false; btn.textContent = 'Tải lên & dò cấu trúc';
  }
}

/** Mở form "Thêm nguồn" đã điền sẵn đường dẫn + bảng vừa chọn. */
function dungBangNay(path, kind, bang) {
  newDataSource();
  const dat = (id, v) => { const e = document.getElementById(id); if (e) e.value = v; };
  dat('dsPath', path);
  dat('dsKind', kind);
  dat('dsName', bang);
  if (kind === 'sqlite') dat('dsTable', bang); else dat('dsSheet', bang);
}


/** Đặt tốc đọc riêng cho một giọng, rồi đọc thử NGAY để nghe kết quả.
 *
 *  Nghe thử ngay là phần quan trọng: chỉnh tốc mà không nghe lại thì phải mò,
 *  và bộ nhớ đệm tiếng cũ từng làm người dùng tưởng nút không ăn (backend đã
 *  dọn cache khi đổi tốc, xem `dat_toc_do`).
 */
async function datTocGiong(ten, toc) {
  try {
    const d = await fetch(`/api/voices/${encodeURIComponent(ten)}/speed`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ speed: parseFloat(toc) }),
    }).then(r => r.json());
    if (d.error) { alert(d.error); return; }
    nghesThuToc(ten);
  } catch (e) {
    alert('Lỗi: ' + e.message);
  }
}

async function boTocGiong(ten) {
  await fetch(`/api/voices/${encodeURIComponent(ten)}/speed`, { method: 'DELETE' });
  loadVoiceList();
}

/** Đọc một câu mẫu bằng giọng + tốc vừa đặt. Dùng /test-tts để không đụng vào
 *  bộ nhớ đệm mà cuộc gọi thật đang dùng. */
async function nghesThuToc(ten) {
  try {
    // /test-tts nhận FORM chứ không phải JSON, và tên trường là `voice_name`.
    const fd = new FormData();
    fd.append('text', 'Dạ em chào anh chị, lãi suất vay tín chấp hiện tại là 7.9% một năm ạ.');
    fd.append('voice_name', ten);
    const d = await fetch('/api/voices/test-tts', { method: 'POST', body: fd })
      .then(r => r.json());
    if (d.audio) phatTiengThu('data:audio/wav;base64,' + d.audio);
  } catch (e) { /* nghe thử hỏng thì thôi, tốc vẫn đã lưu */ }
}

// ---- Tốc độ đọc khi gọi điện thoại -----------------------------------------
//
// Tách riêng khỏi tốc từng giọng: kênh GSM 8kHz cắt sạch trên 4kHz, đúng dải
// mang phụ âm. Cùng một tốc, nghe trên web rõ mà qua điện thoại dính chữ.

async function napTocThoai() {
  const th = document.getElementById('tocThoai');
  if (!th) return;
  try {
    const d = await fetch('/api/voices/phone-speed').then(r => r.json());
    if (d.error) return;
    th.value = d.he_so;
    document.getElementById('tocThoaiSo').textContent = (+d.he_so).toFixed(2);
  } catch (e) { /* trang vẫn dùng được với giá trị mặc định */ }

  // Ô chọn giọng để nghe thử — mặc định lấy giọng đang dùng cho cuộc gọi.
  const sel = document.getElementById('tocThoaiGiong');
  if (sel && !sel.options.length) {
    try {
      const v = await fetch('/api/voices').then(r => r.json());
      sel.innerHTML = (v.voices || []).map(x =>
        `<option value="${escapeHtml(x.name)}">${escapeHtml(x.name)} · tốc ${(+(x.speed ?? 1)).toFixed(2)}</option>`).join('');
    } catch (e) { /* bỏ qua */ }
  }
}

async function luuTocThoai(v) {
  const tt = document.getElementById('tocThoaiTrangThai');
  try {
    const d = await fetch('/api/voices/phone-speed', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ he_so: parseFloat(v) }),
    }).then(r => r.json());
    if (d.error) { tt.textContent = d.error; return; }
    tt.textContent = 'đã lưu';
    setTimeout(() => { tt.textContent = ''; }, 2000);
  } catch (e) { tt.textContent = 'Lỗi: ' + e.message; }
}

/** Nghe thử. `quaDienThoai=true` hạ 24kHz->8kHz rồi nâng lại, tức nghe ĐÚNG
 *  thứ khách nghe. Chỉnh trên bản 24kHz rồi ra cuộc gọi lại khác là vô ích. */
async function ngheThuThoai(quaDienThoai) {
  const tt = document.getElementById('tocThoaiTrangThai');
  const giong = (document.getElementById('tocThoaiGiong') || {}).value || 'default';
  tt.textContent = 'đang dựng tiếng…';
  try {
    const fd = new FormData();
    fd.append('text', 'Dạ em chào anh Hải, lãi suất vay tín chấp hiện tại là 7.9% một năm, '
                    + 'hạn mức lên đến 500 triệu đồng ạ.');
    fd.append('voice_name', giong);
    fd.append('qua_dien_thoai', quaDienThoai ? 'true' : 'false');
    const d = await fetch('/api/voices/test-tts', { method: 'POST', body: fd })
      .then(r => r.json());
    if (d.error) { tt.textContent = d.error; return; }
    phatTiengThu('data:audio/wav;base64,' + d.audio);
    tt.textContent = `${d.duration_ms || d.elapsed_ms}ms · ${quaDienThoai ? 'qua kênh 8kHz' : 'bản gốc 24kHz'}`;
  } catch (e) { tt.textContent = 'Lỗi: ' + e.message; }
}
