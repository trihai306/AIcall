/* Giao diện cho các tính năng bổ sung theo Điều 6 hợp đồng.
 *
 * Để riêng khỏi app.js (đã hơn 3000 dòng) chứ không nhét thêm vào: file này chỉ
 * phụ trách các trang mới (Tổng quan, Kịch bản, Báo cáo, Nguồn dữ liệu) cộng
 * mấy khối cắm vào trang cũ (chạy chiến dịch, Telegram, nhận cuộc gọi đến).
 *
 * Nạp SAU app.js, và bọc `switchPage` thay vì sửa nó — sửa trực tiếp thì mỗi
 * lần app.js đổi lại phải gỡ rối xem ai ghi đè ai.
 */

// ---------- tiện ích chung ----------

async function apiGet(url) {
  const res = await fetch(url);
  return res.json();
}

async function apiSend(url, body, method = 'POST') {
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return res.json();
}

function esc(t) {
  const d = document.createElement('div');
  d.textContent = t == null ? '' : String(t);
  return d.innerHTML;
}

function gio(ts) {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return d.toLocaleString('vi-VN', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

function phutGiay(giay) {
  if (!giay && giay !== 0) return '—';
  const s = Math.round(giay);
  return `${Math.floor(s / 60)}p${String(s % 60).padStart(2, '0')}s`;
}

function o(id) { return document.getElementById(id); }

/** Báo lỗi cho người dùng. Luôn tiếng Việt, luôn kèm cách xử lý nếu biết.
 *
 *  Đẩy qua thongBao() (khay trượt góc màn hình, định nghĩa trong app.js) thay
 *  cho alert(): alert() chặn cả luồng JS lại cho tới khi bấm OK, và trông như
 *  thông báo lỗi của trình duyệt chứ không phải phản hồi của app. Hàm này là
 *  đường báo lỗi dùng chung của mọi trang trong file, nên đổi ở đây là đổi hết.
 *  thongBao() tự rơi về alert() nếu khay chưa có trong DOM. */
function baoLoi(data, mac_dinh = 'Có lỗi xảy ra') {
  if (data && data.error) { thongBao(data.error, 'loi'); return true; }
  if (!data) { thongBao(mac_dinh, 'loi'); return true; }
  return false;
}

/** Dải thống kê, dùng đúng `.stat-cell/.k/.v` có sẵn trong style.css.
 *  Tự chế class Tailwind riêng thì mấy dải này lệch font và cỡ chữ so với các
 *  dải đã có ở trang Danh bạ. */
function statStrip(items) {
  return items.map(([nhan, gia_tri, mau]) => `
    <div class="stat-cell">
      <div class="k">${esc(nhan)}</div>
      <div class="v ${mau || 'text-white'}">${esc(gia_tri)}</div>
    </div>`).join('');
}

// ---------- bọc switchPage ----------

const _switchPageGoc = window.switchPage;
window.switchPage = function (name) {
  _switchPageGoc(name);
  if (name === 'overview') loadOverview();
  if (name === 'scenarios') loadScenarios();
  if (name === 'reports') initReports();
  if (name === 'datasources') loadDataSources();
  if (name === 'settings') { loadNotifyChannels(); loadRecordingStats(); }
  if (name === 'contacts') setTimeout(initCampaignRunner, 60);
  // Trang Nhắn tin xếp theo cột như trang Hội thoại, mà danh sách `flex` nằm
  // trong app.js. Bật ở đây thay vì sửa app.js - đúng lý do file này bọc
  // switchPage chứ không sửa nó.
  if (name === 'messaging') {
    document.getElementById('page-messaging').classList.add('flex');
    initMessaging();
  } else if (typeof msgDungTieng === 'function') {
    // Rời trang mà tiếng vẫn chạy thì không còn nút nào để tắt nó.
    msgDungTieng();
  }
};

// =====================================================================
// TỔNG QUAN
// =====================================================================

async function loadOverview() {
  try {
    const homNay = new Date(); homNay.setHours(0, 0, 0, 0);
    const [tt, dangChay, thietBi, ganNhat] = await Promise.all([
      apiGet(`/api/reports/summary?from_ts=${homNay.getTime() / 1000}`),
      apiGet('/api/phones/running'),
      apiGet('/api/devices'),
      apiGet('/api/reports/calls?limit=6'),
    ]);

    o('overviewStats').innerHTML = statStrip([
      ['Cuộc gọi hôm nay', tt.tong_cuoc ?? 0],
      ['Nghe máy', `${tt.ty_le_nghe_may ?? 0}%`, 'text-emerald-400'],
      ['Tổng thời lượng', phutGiay(tt.tong_thoi_luong || 0)],
      ['Có ghi âm', tt.co_ghi_am ?? 0],
      ['Chiến dịch đang chạy', (dangChay.campaigns || []).length,
        (dangChay.campaigns || []).length ? 'text-cyan-400' : 'text-gray-500'],
    ]);

    const cds = dangChay.campaigns || [];
    o('overviewCampaigns').innerHTML = cds.length ? cds.map(c => `
      <div class="flex items-center justify-between gap-3 py-2 border-b border-slate-750 last:border-0">
        <div>
          <div class="text-sm text-white">${esc(c.campaign_id)}</div>
          <div class="text-[10px] text-gray-500">${esc(c.ly_do || c.trang_thai)}</div>
        </div>
        <div class="text-xs text-gray-400">
          ${c.da_goi} cuộc · nghe máy ${c.da_nghe_may} (${c.ty_le_nghe_may}%)
          ${c.dang_goi?.length ? ` · <span class="text-cyan-400">${c.dang_goi.length} đang gọi</span>` : ''}
        </div>
      </div>`).join('')
      : '<div class="text-xs text-gray-600">Không có chiến dịch nào đang chạy.</div>';

    const dev = thietBi.devices || [];
    o('overviewDevices').innerHTML = dev.length ? dev.map(d => `
      <div class="flex items-center justify-between py-1.5 border-b border-slate-750 last:border-0">
        <span class="text-xs text-gray-300">${esc(d.name)}</span>
        <span class="pill st-${esc(d.status)}">${esc(d.status)}</span>
      </div>`).join('')
      : '<div class="text-xs text-gray-600">Chưa thêm thiết bị nào.</div>';

    const calls = ganNhat.calls || [];
    o('overviewRecent').innerHTML = calls.length ? calls.map(c => `
      <div class="flex items-center justify-between py-1.5 border-b border-slate-750 last:border-0">
        <span class="text-xs text-gray-300">${esc(c.customer_name || c.phone || '—')}</span>
        <span class="text-[10px] text-gray-500">${esc(c.quality_label || c.outcome || '')} · ${gio(c.created_at)}</span>
      </div>`).join('')
      : '<div class="text-xs text-gray-600">Chưa có cuộc gọi nào.</div>';
  } catch (e) {
    o('overviewCampaigns').innerHTML =
      `<div class="text-xs text-red-400">Không tải được: ${esc(e.message)}</div>`;
  }
}

// =====================================================================
// KỊCH BẢN (F3)
// =====================================================================

let scenarios = [];
let scenarioDangSua = null;

async function loadScenarios() {
  const data = await apiGet('/api/scenarios');
  scenarios = data.scenarios || [];
  o('scenarioList').innerHTML = scenarios.length ? scenarios.map(s => `
    <button onclick="editScenario('${s.scenario_id}')"
            class="w-full text-left px-3 py-2 rounded-lg hover:bg-slate-800/60 transition-colors
                   ${scenarioDangSua === s.scenario_id ? 'bg-slate-800/80' : ''}">
      <div class="flex items-center gap-2">
        <span class="text-sm text-white">${esc(s.name)}</span>
        ${s.is_default ? '<span class="tag tag-cyan">mặc định</span>' : ''}
      </div>
      <div class="text-[10px] text-gray-500 mt-0.5">
        ${esc(s.industry || 'chưa khai ngành')} · ${esc(s.direction)}
      </div>
    </button>`).join('')
    : '<div class="p-3 text-xs text-gray-600">Chưa có kịch bản nào.</div>';
}

function newScenario() {
  scenarioDangSua = '';
  veScenarioForm({
    name: '', industry: '', org_name: '', agent_name: '', opening_line: '',
    rules: '', examples: [], max_turns: 20, transfer_number: '', transfer_on: [],
    transfer_message: 'Dạ em xin phép nối máy cho chuyên viên ạ',
    direction: 'outbound', note: '',
  });
}

async function editScenario(id) {
  const data = await apiGet('/api/scenarios/' + id);
  if (baoLoi(data)) return;
  scenarioDangSua = id;
  veScenarioForm(data.scenario);
  loadScenarios();
}

function veScenarioForm(s) {
  o('scenarioEditTitle').textContent = scenarioDangSua ? `Sửa: ${s.name}` : 'Kịch bản mới';
  o('scenarioActions').innerHTML = scenarioDangSua ? `
    <a href="/api/scenarios/${scenarioDangSua}/export" class="text-[10px] text-gray-500 hover:text-white">Xuất file</a>
    <button onclick="setDefaultScenario()" class="text-[10px] text-cyan-400 hover:text-cyan-300">Đặt mặc định</button>
    <button onclick="deleteScenario()" class="text-[10px] text-gray-500 hover:text-red-400">Xoá</button>` : '';

  const vd = (s.examples || []).length ? s.examples : [{ khach: '', tu_van: '' }];
  o('scenarioForm').innerHTML = `
    <div class="grid grid-cols-4 gap-3">
      <div><label class="fld">Tên kịch bản</label><input id="scName" class="inp" value="${esc(s.name)}"></div>
      <div><label class="fld">Ngành</label><input id="scIndustry" class="inp" placeholder="ngân hàng / bảo hiểm…" value="${esc(s.industry)}"></div>
      <div><label class="fld">Tên tổ chức bot xưng</label><input id="scOrg" class="inp" value="${esc(s.org_name)}"></div>
      <div><label class="fld">Tên nhân viên</label><input id="scAgent" class="inp" value="${esc(s.agent_name)}"></div>
    </div>
    <div><label class="fld">Câu chào mở đầu</label>
      <input id="scOpening" class="inp" placeholder="Dạ em chào anh/chị…" value="${esc(s.opening_line)}"></div>

    <div><label class="fld">Luật riêng của ngành — mỗi dòng một luật</label>
      <textarea id="scRules" class="inp" rows="3">${esc(s.rules)}</textarea>
      <div class="text-[10px] text-gray-600 mt-1">
        Các luật chung (tối đa 2 câu, cấm bịa số, cấm liệt kê, đoán ý khi bản ghi
        sai chính tả) đã cố định trong hệ thống — không cần và không sửa được ở đây.
      </div>
    </div>

    <div>
      <label class="fld">Ví dụ hỏi–đáp (dạy mô hình ĐỘ DÀI câu trả lời)</label>
      <div id="scExamples" class="space-y-2">
        ${vd.map((e, i) => veViDu(e, i)).join('')}
      </div>
      <button onclick="addExample()" class="text-[10px] text-cyan-400 hover:text-cyan-300 mt-1.5">+ Thêm ví dụ</button>
      <div class="text-[10px] text-amber-500/80 mt-1">
        Đừng đặt con số thật vào ví dụ — mô hình sẽ chép nguyên con số đó ra trả lời khách.
      </div>
    </div>

    <div class="grid grid-cols-4 gap-3 pt-1 border-t border-slate-750">
      <div class="pt-3"><label class="fld">Số điện thoại chuyên viên</label>
        <input id="scTransferNumber" class="inp font-mono" value="${esc(s.transfer_number)}"></div>
      <div class="pt-3"><label class="fld">Số lượt tối đa</label>
        <input id="scMaxTurns" type="number" class="inp" min="1" value="${s.max_turns || 20}"></div>
      <div class="pt-3"><label class="fld">Hướng gọi</label>
        <select id="scDirection" class="inp">
          <option value="outbound" ${s.direction === 'outbound' ? 'selected' : ''}>Gọi ra</option>
          <option value="inbound" ${s.direction === 'inbound' ? 'selected' : ''}>Gọi vào</option>
          <option value="both" ${s.direction === 'both' ? 'selected' : ''}>Cả hai</option>
        </select></div>
      <div class="pt-3"><label class="fld">Câu nói trước khi nối máy</label>
        <input id="scTransferMessage" class="inp" value="${esc(s.transfer_message)}"></div>
    </div>

    <div><label class="fld">Chuyển tiếp sang người thật khi</label>
      <div class="flex flex-wrap items-center gap-3 pt-1">
        ${[['khach_yeu_cau', 'Khách đòi gặp người thật'],
           ['ngoai_pham_vi', 'Bot bí 2 lượt liên tiếp'],
           ['khong_tim_thay', 'Không có tài liệu 2 lượt liên tiếp'],
           ['het_luot', 'Vượt số lượt tối đa']].map(([k, nhan]) => `
          <label class="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer">
            <input type="checkbox" class="sc-transfer accent-cyan-500" value="${k}"
                   ${(s.transfer_on || []).includes(k) ? 'checked' : ''}> ${nhan}</label>`).join('')}
      </div>
    </div>

    <div class="flex items-center gap-2 pt-2 border-t border-slate-750">
      <button onclick="saveScenario()" class="btn btn-primary mt-3">Lưu kịch bản</button>
      ${scenarioDangSua ? '<button onclick="testScenario()" class="btn btn-soft mt-3">Chạy thử</button>' : ''}
    </div>
    <div id="scTestResult"></div>`;
}

function veViDu(e, i) {
  return `<div class="grid grid-cols-2 gap-2" data-example>
    <input class="inp sc-ex-khach" placeholder="Khách nói…" value="${esc(e.khach)}">
    <div class="flex gap-1">
      <input class="inp sc-ex-tuvan flex-1" placeholder="Bot trả lời…" value="${esc(e.tu_van)}">
      <button onclick="this.closest('[data-example]').remove()" class="btn btn-ghost px-2">×</button>
    </div></div>`;
}

function addExample() {
  o('scExamples').insertAdjacentHTML('beforeend', veViDu({ khach: '', tu_van: '' }, 0));
}

function thuThapScenario() {
  const examples = [...document.querySelectorAll('#scExamples [data-example]')]
    .map(d => ({
      khach: d.querySelector('.sc-ex-khach').value.trim(),
      tu_van: d.querySelector('.sc-ex-tuvan').value.trim(),
    }))
    .filter(e => e.khach && e.tu_van);

  return {
    name: o('scName').value.trim(),
    industry: o('scIndustry').value.trim(),
    org_name: o('scOrg').value.trim(),
    agent_name: o('scAgent').value.trim(),
    opening_line: o('scOpening').value.trim(),
    rules: o('scRules').value,
    examples,
    max_turns: parseInt(o('scMaxTurns').value) || 20,
    transfer_number: o('scTransferNumber').value.trim(),
    transfer_message: o('scTransferMessage').value.trim(),
    direction: o('scDirection').value,
    transfer_on: [...document.querySelectorAll('.sc-transfer:checked')].map(c => c.value),
  };
}

async function saveScenario() {
  const payload = thuThapScenario();
  if (!payload.name) { alert('Kịch bản phải có tên'); return; }
  const data = scenarioDangSua
    ? await apiSend('/api/scenarios/' + scenarioDangSua, payload, 'PATCH')
    : await apiSend('/api/scenarios', payload);
  if (baoLoi(data)) return;
  scenarioDangSua = data.scenario.scenario_id;
  await loadScenarios();
  veScenarioForm(data.scenario);
}

async function setDefaultScenario() {
  const data = await apiSend(`/api/scenarios/${scenarioDangSua}/default`);
  if (baoLoi(data)) return;
  loadScenarios();
}

async function deleteScenario() {
  if (!confirm('Xoá kịch bản này? Chiến dịch đang dùng nó sẽ quay về kịch bản mặc định.')) return;
  const data = await apiSend('/api/scenarios/' + scenarioDangSua, undefined, 'DELETE');
  if (baoLoi(data)) return;
  scenarioDangSua = null;
  o('scenarioForm').innerHTML = '<div class="text-xs text-gray-600">Đã xoá.</div>';
  o('scenarioActions').innerHTML = '';
  loadScenarios();
}

async function testScenario() {
  const cau = prompt('Khách nói gì?', 'Lãi suất bao nhiêu?');
  if (cau === null) return;
  o('scTestResult').innerHTML = '<div class="text-xs text-gray-500 mt-2">Đang chạy thử…</div>';
  const data = await apiSend(`/api/scenarios/${scenarioDangSua}/test`, { cau_khach: cau });
  if (data.error) {
    o('scTestResult').innerHTML = `<div class="text-xs text-red-400 mt-2">${esc(data.error)}</div>`;
    return;
  }
  o('scTestResult').innerHTML = `
    <div class="mt-3 p-3 bg-void rounded-lg border border-slate-750 space-y-2">
      <div><span class="text-[10px] text-gray-500 uppercase">Khách</span>
        <div class="text-sm text-gray-300">${esc(data.cau_khach)}</div></div>
      <div><span class="text-[10px] text-gray-500 uppercase">Bot trả lời (${data.so_tu} từ)</span>
        <div class="text-sm text-cyan-300">${esc(data.tra_loi) || '(rỗng)'}</div></div>
      <details><summary class="text-[10px] text-gray-500 cursor-pointer hover:text-white">Xem prompt đã dựng</summary>
        <pre class="text-[10px] text-gray-500 mt-2 whitespace-pre-wrap">${esc(data.system_prompt)}</pre></details>
    </div>`;
}

async function importScenario(input) {
  const file = input.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/scenarios/import', { method: 'POST', body: fd });
  const data = await res.json();
  input.value = '';
  if (baoLoi(data)) return;
  await loadScenarios();
  editScenario(data.scenario.scenario_id);
}

// =====================================================================
// BÁO CÁO (F12–F15)
// =====================================================================

let reportPage = 1;
let reportLabels = [];

async function initReports() {
  if (!o('rpOutcome').options.length || o('rpOutcome').options.length === 1) {
    const [meta, nhan, cds] = await Promise.all([
      apiGet('/api/reports/calls?limit=1'),
      apiGet('/api/reports/labels'),
      apiGet('/api/phones/campaigns'),
    ]);
    reportLabels = nhan.labels || [];

    o('rpOutcome').innerHTML = '<option value="">Tất cả</option>' +
      (meta.outcomes || []).map(x => `<option value="${x}">${x}</option>`).join('');
    o('rpQuality').innerHTML = '<option value="">Tất cả</option>' +
      (meta.qualities || []).map(x =>
        `<option value="${x}">${esc((meta.quality_labels || {})[x] || x)}</option>`).join('');
    o('rpLabel').innerHTML = '<option value="">Tất cả</option>' +
      reportLabels.map(l => `<option value="${l.label_id}">${esc(l.name)}</option>`).join('');
    o('rpCampaign').innerHTML = '<option value="">Tất cả</option>' +
      (cds.campaigns || []).map(c =>
        `<option value="${c.campaign_id}">${esc(c.name)}</option>`).join('');
  }
  loadReport();
}

function boLocBaoCao() {
  const p = new URLSearchParams();
  const tu = o('rpFrom').value, den = o('rpTo').value;
  if (tu) p.set('from_ts', new Date(tu + 'T00:00:00').getTime() / 1000);
  if (den) p.set('to_ts', new Date(den + 'T23:59:59').getTime() / 1000);
  for (const [id, key] of [['rpCampaign', 'campaign_id'], ['rpOutcome', 'outcome'],
                           ['rpQuality', 'quality'], ['rpLabel', 'label'],
                           ['rpGender', 'gender'], ['rpDirection', 'direction']]) {
    if (o(id).value) p.set(key, o(id).value);
  }
  if (o('rpMinDur').value) p.set('min_duration', o('rpMinDur').value);
  if (o('rpMaxDur').value) p.set('max_duration', o('rpMaxDur').value);
  if (o('rpQuery').value.trim()) p.set('q', o('rpQuery').value.trim());
  if (o('rpHasRec').checked) p.set('co_ghi_am', 'true');
  if (o('rpGomThu')?.checked) p.set('gom_phien_thu', 'true');
  return p;
}

function resetReportFilter() {
  ['rpFrom', 'rpTo', 'rpMinDur', 'rpMaxDur', 'rpQuery'].forEach(id => o(id).value = '');
  ['rpCampaign', 'rpOutcome', 'rpQuality', 'rpLabel', 'rpGender', 'rpDirection']
    .forEach(id => o(id).value = '');
  o('rpHasRec').checked = false;
  if (o('rpGomThu')) o('rpGomThu').checked = false;
  reportPage = 1;
  loadReport();
}

async function loadReport(page) {
  reportPage = page || 1;
  const p = boLocBaoCao();
  const [tt, ds] = await Promise.all([
    apiGet('/api/reports/summary?' + p.toString()),
    apiGet(`/api/reports/calls?${p.toString()}&page=${reportPage}&limit=50`),
  ]);

  o('reportStats').innerHTML = statStrip([
    ['Tổng cuộc', tt.tong_cuoc ?? 0],
    ['Nghe máy', `${tt.ty_le_nghe_may ?? 0}%`, 'text-emerald-400'],
    ['Thời lượng TB', phutGiay(tt.thoi_luong_tb || 0)],
    ['Tổng thời lượng', phutGiay(tt.tong_thoi_luong || 0)],
    ['Có ghi âm', tt.co_ghi_am ?? 0],
  ]);

  o('reportCount').textContent = `Cuộc gọi — ${ds.total} kết quả`;
  const calls = ds.calls || [];
  o('reportRows').innerHTML = calls.length ? calls.map(c => `
    <tr>
      <td><input type="checkbox" class="rp-row accent-cyan-500" value="${c.session_id}"></td>
      <td class="text-gray-400 whitespace-nowrap">${gio(c.created_at)}</td>
      <td>${esc(c.customer_name || '—')}</td>
      <td class="font-mono text-gray-400">${esc(c.phone || c.caller_number || '—')}</td>
      <td class="text-gray-500">${esc(c.campaign_name || '—')}</td>
      <td class="whitespace-nowrap">${phutGiay(c.duration_seconds)}</td>
      <td><span class="pill">${esc(c.outcome || '—')}</span></td>
      <td class="text-gray-400">${esc(c.quality_label || '—')}</td>
      <td>${veNhanChip(c)}</td>
      <td>${c.co_ghi_am
        ? `<audio controls preload="none" style="height:26px;width:150px"
             src="/api/reports/calls/${c.session_id}/recording"></audio>`
        : '<span class="text-gray-700">—</span>'}</td>
      <td class="text-gray-500 max-w-[280px] truncate" title="${esc(c.summary || '')}">${esc(c.summary || '—')}</td>
      <td class="row-actions"><button onclick="openCallDetail('${c.session_id}')"
            class="text-[10px] text-cyan-400 hover:text-cyan-300">Chi tiết</button></td>
    </tr>`).join('')
    : '<tr><td colspan="12" class="text-center text-gray-600 py-6">Không có cuộc gọi nào khớp bộ lọc.</td></tr>';

  o('reportBulk').innerHTML = `
    <select id="rpBulkLabel" class="inp" style="height:28px;padding:2px 8px;font-size:11px">
      <option value="">Gắn nhãn hàng loạt…</option>
      ${reportLabels.map(l => `<option value="${l.label_id}">${esc(l.name)}</option>`).join('')}
      <option value="__go__">— Gỡ nhãn —</option>
    </select>
    <button onclick="bulkLabel()" class="btn btn-ghost">Áp dụng</button>`;

  const soTrang = Math.ceil(ds.total / 50) || 1;
  o('reportPager').innerHTML = `
    <span class="text-[11px] text-gray-500">Trang ${reportPage}/${soTrang}</span>
    <div class="flex gap-1">
      <button onclick="loadReport(${reportPage - 1})" class="btn btn-ghost" ${reportPage <= 1 ? 'disabled' : ''}>← Trước</button>
      <button onclick="loadReport(${reportPage + 1})" class="btn btn-ghost" ${!ds.has_more ? 'disabled' : ''}>Sau →</button>
    </div>`;
}

function veNhanChip(c) {
  const l = reportLabels.find(x => x.label_id === c.label);
  if (l) return `<span class="tag" style="color:${esc(l.color)};border-color:${esc(l.color)}55">${esc(l.name)}</span>`;
  if (c.suggested_label) {
    const g = reportLabels.find(x => x.label_id === c.suggested_label);
    return `<span class="text-[10px] text-gray-600" title="AI đề xuất, bấm Chi tiết để xác nhận">
              ${esc(g ? g.name : c.suggested_label)}?</span>`;
  }
  return '<span class="text-gray-700">—</span>';
}

function toggleAllReportRows(cb) {
  document.querySelectorAll('.rp-row').forEach(x => x.checked = cb.checked);
}

async function bulkLabel() {
  const chon = [...document.querySelectorAll('.rp-row:checked')].map(x => x.value);
  if (!chon.length) { alert('Chưa chọn cuộc gọi nào'); return; }
  const nhan = o('rpBulkLabel').value;
  if (!nhan) { alert('Chọn nhãn muốn gắn'); return; }
  const data = await apiSend('/api/reports/label',
    { session_ids: chon, label: nhan === '__go__' ? '' : nhan });
  if (baoLoi(data)) return;
  loadReport(reportPage);
}

async function openCallDetail(id) {
  const data = await apiGet('/api/reports/calls/' + id);
  if (baoLoi(data)) return;
  const c = data.call;
  o('reportDetail').classList.remove('hidden');
  o('reportDetailTitle').textContent = `${c.customer_name || '—'} · ${c.phone || c.caller_number || ''}`;
  o('reportDetailBody').innerHTML = `
    <div class="grid grid-cols-2 gap-4">
      <div class="space-y-3">
        ${c.recording_path ? `<div>
          <div class="text-[10px] text-gray-500 uppercase mb-1">Ghi âm — trái: khách, phải: bot</div>
          <audio controls class="w-full" src="/api/reports/calls/${id}/recording"></audio></div>` : ''}
        <div>
          <div class="text-[10px] text-gray-500 uppercase mb-1">Tóm tắt</div>
          <div class="text-sm text-gray-300">${esc(c.summary) || '<span class="text-gray-600">Chưa có</span>'}</div>
          <button onclick="resummarize('${id}')" class="text-[10px] text-cyan-400 hover:text-cyan-300 mt-1">Tóm tắt lại</button>
        </div>
        <div>
          <div class="text-[10px] text-gray-500 uppercase mb-1">Gắn nhãn</div>
          <div class="flex flex-wrap gap-1.5">
            ${reportLabels.map(l => `<button onclick="setOneLabel('${id}','${l.label_id}')"
                class="tag ${c.label === l.label_id ? 'tag-cyan' : ''}"
                style="cursor:pointer">${esc(l.name)}</button>`).join('')}
            <button onclick="setOneLabel('${id}','')" class="tag" style="cursor:pointer">Gỡ nhãn</button>
          </div>
        </div>
        <div class="text-[11px] text-gray-500 space-y-0.5">
          <div>Kết quả: ${esc(c.outcome || '—')} · Chất lượng: ${esc(c.quality_label || '—')}</div>
          <div>Giới tính: ${esc(c.gender || 'không rõ')} · Hướng: ${esc(c.direction || '—')}</div>
          ${c.transferred_to ? `<div>Đã nối máy sang ${esc(c.transferred_to)} (${esc(c.transfer_reason)})</div>` : ''}
        </div>
      </div>
      <div>
        <div class="text-[10px] text-gray-500 uppercase mb-1">Toàn văn hội thoại</div>
        <div class="space-y-1.5 max-h-[360px] overflow-y-auto pr-2">
          ${(c.history || []).map(t => `
            <div class="text-xs ${t.role === 'user' ? 'text-gray-300' : 'text-cyan-300'}">
              <span class="text-[10px] text-gray-600">${t.role === 'user' ? 'Khách' : 'Bot'}:</span>
              ${esc(t.content)}</div>`).join('') || '<div class="text-xs text-gray-600">Không có lượt nào.</div>'}
        </div>
      </div>
    </div>`;
  o('reportDetail').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function closeCallDetail() { o('reportDetail').classList.add('hidden'); }

async function setOneLabel(id, nhan) {
  const data = await apiSend('/api/reports/label', { session_ids: [id], label: nhan });
  if (baoLoi(data)) return;
  openCallDetail(id);
  loadReport(reportPage);
}

async function resummarize(id) {
  const data = await apiSend(`/api/reports/calls/${id}/summarize`);
  if (baoLoi(data)) return;
  openCallDetail(id);
}

async function summarizePending() {
  const data = await apiSend('/api/reports/summarize-pending?limit=100');
  alert(`Đã xếp hàng tóm tắt ${data.da_xep_hang || 0} cuộc gọi. Chạy nền, xem lại sau ít phút.`);
}

function exportReport() {
  window.location = '/api/reports/export?' + boLocBaoCao().toString();
}

// =====================================================================
// NGUỒN DỮ LIỆU (F16)
// =====================================================================

let dataSources = [];
let dsDangSua = null;
let dsCheDoLoc = '';   // '' = tất cả | 'rag' | 'lookup' | 'loi'

async function loadDataSources() {
  o('dsRows').innerHTML = dsHangCho();
  ganVungKeoThaNguon();
  try {
    const data = await apiGet('/api/data-sources');
    dataSources = data.sources || [];
    veThongKeNguon();
    veChipNguon();
    veBangNguon();
  } catch (e) {
    o('dsRows').innerHTML = '<tr><td colspan="8" class="text-center text-red-400 py-8 text-xs">'
      + 'Không đọc được danh sách nguồn: ' + esc(e.message) + '</td></tr>';
  }
}

function veThongKeNguon() {
  const bat = dataSources.filter(s => s.enabled).length;
  const dong = dataSources.reduce((t, s) => t + (s.row_count || 0), 0);
  const loi = dataSources.filter(s => s.last_error).length;
  o('dsStats').innerHTML = statStrip([
    ['Nguồn dữ liệu', dataSources.length, 'text-white'],
    ['Đang bật', bat, 'text-emerald-400'],
    ['Tổng số dòng', dong.toLocaleString('vi-VN'), 'text-cyan-400'],
    ['Có lỗi', loi, loi ? 'text-red-400' : 'text-gray-600'],
  ]);
}

function veChipNguon() {
  const dem = ma => {
    if (!ma) return dataSources.length;
    if (ma === 'loi') return dataSources.filter(s => s.last_error).length;
    return dataSources.filter(s => s.mode === ma).length;
  };
  const cai = [['', 'Tất cả'], ['rag', 'Tri thức chung'], ['lookup', 'Tra theo khách'], ['loi', 'Có lỗi']];
  o('dsChips').innerHTML = cai.map(([ma, nhan]) =>
    `<button class="chip ${dsCheDoLoc === ma ? 'active' : ''}" onclick="locCheDoNguon('${ma}')">`
    + `${nhan}<span class="font-mono opacity-55">${dem(ma)}</span></button>`).join('');
}

function locCheDoNguon(ma) {
  dsCheDoLoc = ma;
  veChipNguon();
  veBangNguon();
}

function veBangNguon() {
  if (!dataSources.length) { o('dsRows').innerHTML = dsTrangRong(); return; }

  const tu = (o('dsTim')?.value || '').trim().toLowerCase();
  const ds = dataSources.filter(s => {
    const hop = !dsCheDoLoc
      || (dsCheDoLoc === 'loi' ? !!s.last_error : s.mode === dsCheDoLoc);
    return hop && (!tu || (s.name || '').toLowerCase().includes(tu));
  });

  if (!ds.length) {
    o('dsRows').innerHTML = '<tr><td colspan="8" class="text-center text-gray-600 py-10 text-xs">'
      + 'Không có nguồn nào khớp. Thử xoá bớt từ khoá hoặc chọn "Tất cả".</td></tr>';
    return;
  }

  o('dsRows').innerHTML = ds.map(s => `
    <tr>
      <td class="text-white font-medium">${esc(s.name)}</td>
      <td class="text-gray-500">${esc(s.kind)}</td>
      <td><span class="tag ${s.mode === 'rag' ? 'tag-cyan' : ''}">
        ${s.mode === 'rag' ? 'Tri thức chung' : 'Tra theo khách'}</span></td>
      <td class="font-mono text-[11px] text-gray-500 max-w-[280px] truncate"
          title="${esc(s.config.path || '')}">${esc(s.config.path || '—')}</td>
      <td class="font-mono text-[11px] text-gray-400">${(s.row_count || 0).toLocaleString('vi-VN')}</td>
      <td class="text-gray-500 text-[11px]">${s.sync_at ? gio(s.sync_at) : '—'}</td>
      <td>${s.last_error
        ? `<span class="pill st-error" title="${esc(s.last_error)}"><span class="dot"></span>lỗi</span>`
        : `<span class="pill ${s.enabled ? 'st-online' : 'st-offline'}"><span class="dot"></span>${s.enabled ? 'bật' : 'tắt'}</span>`}</td>
      <td class="text-right whitespace-nowrap">
        <button onclick="previewDataSource('${s.source_id}')" class="btn btn-ghost btn-xs">Xem trước</button>
        ${s.mode === 'rag'
          ? `<button onclick="syncDataSource('${s.source_id}')" class="btn btn-soft btn-xs">Nạp lại</button>`
          : `<button onclick="moTraThu('${s.source_id}')" class="btn btn-soft btn-xs">Tra thử</button>`}
        <button onclick="editDataSource('${s.source_id}')" class="btn btn-ghost btn-xs">Sửa</button>
        <button onclick="deleteDataSource('${s.source_id}')" class="btn btn-ghost btn-xs btn-xoa">Xoá</button>
      </td>
    </tr>`).join('');
}

function dsHangCho() {
  const c = w => `<td><div class="skel" style="width:${w}px"></div></td>`;
  return Array.from({ length: 3 }, () =>
    `<tr>${c(110)}${c(44)}${c(90)}${c(180)}${c(50)}${c(96)}${c(44)}<td></td></tr>`).join('');
}

function dsTrangRong() {
  return `<tr><td colspan="8" class="py-12">
    <div class="flex flex-col items-center gap-3 text-center">
      <svg class="w-8 h-8 text-slate-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.4"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.657 3.582 3 8 3s8-1.343 8-3V5M4 12c0 1.657 3.582 3 8 3s8-1.343 8-3"/></svg>
      <div>
        <div class="text-xs text-gray-300 font-medium">Chưa nối nguồn dữ liệu nào</div>
        <div class="text-[11px] text-gray-600 mt-1">Tải file Excel/CSV/SQLite lên rồi chọn bảng để bot tra cứu.</div>
      </div>
      <button onclick="newDataSource()" class="btn btn-soft btn-xs">+ Thêm nguồn đầu tiên</button>
    </div></td></tr>`;
}

function newDataSource() {
  dsDangSua = '';
  veDsForm({ name: '', kind: 'excel', mode: 'rag', config: {}, lookup_key: '', enabled: true });
}

function editDataSource(id) {
  dsDangSua = id;
  veDsForm(dataSources.find(s => s.source_id === id));
}

function closeDataSource() { o('dsEditor').classList.add('hidden'); dsDangSua = null; }

function veDsForm(s) {
  o('dsEditor').classList.remove('hidden');
  o('dsEditTitle').textContent = dsDangSua ? `Sửa: ${s.name}` : 'Thêm nguồn dữ liệu';
  const cfg = s.config || {};
  o('dsForm').innerHTML = `
    <div class="grid grid-cols-4 gap-3">
      <div><label class="fld">Tên</label><input id="dsName" class="inp" value="${esc(s.name)}"></div>
      <div><label class="fld">Kiểu file</label><select id="dsKind" class="inp">
        ${['excel', 'csv', 'sqlite'].map(k =>
          `<option value="${k}" ${s.kind === k ? 'selected' : ''}>${k}</option>`).join('')}
      </select></div>
      <div><label class="fld">Chế độ</label><select id="dsMode" class="inp" onchange="dsToggleMode()">
        <option value="rag" ${s.mode === 'rag' ? 'selected' : ''}>Tri thức chung (tìm gần đúng)</option>
        <option value="lookup" ${s.mode === 'lookup' ? 'selected' : ''}>Tra theo khách (khớp chính xác)</option>
      </select></div>
      <div id="dsLookupKeyWrap" class="${s.mode === 'lookup' ? '' : 'hidden'}">
        <label class="fld">Cột khoá</label>
        <input id="dsLookupKey" class="inp" placeholder="so_dien_thoai" value="${esc(s.lookup_key)}">
      </div>
    </div>
    <!-- Giải thích hai chế độ đặt ngay dưới chỗ CHỌN chế độ. Trước đây nó nằm
         thường trực trên đầu bảng — xa chỗ ra quyết định, và chiếm chỗ mãi dù
         chỉ cần đọc một lần. -->
    <div class="text-[11px] text-gray-500 leading-relaxed -mt-1">
      <span class="tag tag-cyan">Tri thức chung</span>
      Bảng giá, biểu phí, danh mục sản phẩm. Nạp vào kho tri thức, bot tìm gần đúng theo nghĩa.
      <br>
      <span class="tag">Tra theo khách</span>
      Dư nợ, đơn hàng. Khớp CHÍNH XÁC theo cột khoá (ví dụ số điện thoại), đọc thẳng từ file mỗi lần tra.
    </div>
    <div><label class="fld">Đường dẫn file trên máy này</label>
      <input id="dsPath" class="inp font-mono" placeholder="/Users/ban/bang_gia.xlsx" value="${esc(cfg.path || '')}">
      <div class="text-[10px] text-gray-600 mt-1">
        Chỉ nhận file cục bộ. Đường dẫn http/https bị từ chối — hệ thống chạy offline 100% theo hợp đồng.
      </div>
    </div>
    <div class="grid grid-cols-3 gap-3">
      <div><label class="fld">Sheet (Excel, để trống = sheet đầu)</label>
        <input id="dsSheet" class="inp" value="${esc(cfg.sheet || '')}"></div>
      <div><label class="fld">Bảng (SQLite)</label>
        <input id="dsTable" class="inp" value="${esc(cfg.table || '')}"></div>
      <div><label class="fld">Câu SELECT (SQLite, thay cho tên bảng)</label>
        <input id="dsQuery" class="inp font-mono" value="${esc(cfg.query || '')}"></div>
    </div>
    <div class="flex items-center gap-2">
      <button onclick="saveDataSource()" class="btn btn-primary">Lưu</button>
      <label class="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer ml-2">
        <input type="checkbox" id="dsEnabled" class="accent-cyan-500" ${s.enabled ? 'checked' : ''}> Đang bật</label>
    </div>
    <div id="dsTraThuKhung" class="${s.mode === 'lookup' ? '' : 'hidden'} rounded-lg border border-slate-750 bg-void p-3">
      <label class="fld" for="dsTraGiaTri">Tra thử</label>
      ${dsDangSua ? `
        <div class="flex gap-2">
          <input id="dsTraGiaTri" class="inp" placeholder="ví dụ: 0912345678"
                 onkeydown="if(event.key==='Enter')traThuNguon()">
          <button onclick="traThuNguon()" class="btn btn-soft">Tra</button>
        </div>
        <div class="text-[10px] text-gray-600 mt-1.5">
          Gõ đúng giá trị nằm ở cột khoá. Đây là thứ bot dùng để nhận ra khách khi gọi.
        </div>
        <div id="dsTraKetQua" class="mt-2"></div>`
        : '<div class="text-[11px] text-gray-600">Lưu nguồn này lại rồi mới tra thử được.</div>'}
    </div>
    <div id="dsPreview"></div>`;
}

function dsToggleMode() {
  const laTra = o('dsMode').value === 'lookup';
  o('dsLookupKeyWrap').classList.toggle('hidden', !laTra);
  o('dsTraThuKhung').classList.toggle('hidden', !laTra);
}

async function saveDataSource() {
  const payload = {
    source_id: dsDangSua || '',
    name: o('dsName').value.trim(),
    kind: o('dsKind').value,
    mode: o('dsMode').value,
    path: o('dsPath').value.trim(),
    sheet: o('dsSheet').value.trim(),
    table: o('dsTable').value.trim(),
    query: o('dsQuery').value.trim(),
    lookup_key: o('dsLookupKey') ? o('dsLookupKey').value.trim() : '',
    enabled: o('dsEnabled').checked,
  };
  if (!payload.name) {
    thongBao('Nguồn dữ liệu phải có tên.', 'loi');
    o('dsName').focus();
    return;
  }
  const data = await apiSend('/api/data-sources', payload);
  if (baoLoi(data)) return;
  dsDangSua = data.source.source_id;
  thongBao(`Đã lưu nguồn "${payload.name}".`, 'xong');
  await loadDataSources();
  // Vẽ lại form từ bản vừa lưu. Không vẽ lại thì tiêu đề panel vẫn là "Thêm
  // nguồn dữ liệu" và khung Tra thử vẫn báo "Lưu nguồn này lại rồi mới tra thử
  // được" — cả hai đều sai ngay sau khi vừa lưu xong.
  veDsForm(data.source);
  previewDataSource(dsDangSua);
}

async function previewDataSource(id) {
  if (dsDangSua !== id) editDataSource(id);
  const el = o('dsPreview');
  el.innerHTML = '<div class="text-xs text-gray-500 mt-2">Đang đọc file…</div>';
  const data = await apiSend(`/api/data-sources/${id}/preview`);
  if (data.error) {
    el.innerHTML = `<div class="text-xs text-red-400 mt-2">${esc(data.error)}</div>`;
    return;
  }
  const cot = data.cot || [];
  el.innerHTML = `
    <div class="mt-3 p-3 bg-void rounded-lg border border-slate-750">
      <div class="text-[11px] text-gray-400 mb-2">${data.so_dong} dòng · ${cot.length} cột</div>
      <div class="overflow-x-auto"><table class="data-table w-full">
        <thead><tr>${cot.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead>
        <tbody>${(data.xem_truoc || []).map(r =>
          `<tr>${cot.map(c => `<td class="text-gray-400">${esc(r[c] || '')}</td>`).join('')}</tr>`).join('')}
        </tbody></table></div>
      ${data.vi_du_van_ban ? `<div class="text-[10px] text-gray-600 mt-2">
        Một dòng bot sẽ đọc thành: <span class="text-gray-400">${esc(data.vi_du_van_ban)}</span></div>` : ''}
    </div>`;
}

async function syncDataSource(id) {
  const data = await apiSend(`/api/data-sources/${id}/sync`);
  if (baoLoi(data)) return;
  thongBao(`Đã nạp ${data.so_dong} dòng vào kho tri thức `
    + `(gỡ ${data.da_xoa_cu} mảnh cũ của nguồn này).`, 'xong');
  loadDataSources();
}

// Mở form của nguồn rồi đưa con trỏ vào ô tra thử. Trước đây việc này dùng
// prompt() rồi alert() — hai hộp của trình duyệt, không thấy được cột khoá đang
// đặt là gì, và kết quả biến mất ngay khi bấm OK nên không đối chiếu được.
function moTraThu(id) {
  editDataSource(id);
  const inp = o('dsTraGiaTri');
  if (inp) { inp.focus(); inp.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
}

async function traThuNguon() {
  const inp = o('dsTraGiaTri');
  const kq = o('dsTraKetQua');
  if (!inp || !kq) return;
  const gt = inp.value.trim();
  if (!gt) { thongBao('Nhập giá trị cần tra đã.', 'loi'); inp.focus(); return; }

  kq.innerHTML = '<div class="text-[11px] text-gray-500">Đang tra…</div>';
  const data = await apiSend(`/api/data-sources/${dsDangSua}/lookup`, { gia_tri: gt });
  if (data.error) {
    kq.innerHTML = `<div class="text-[11px] text-red-400">${esc(data.error)}</div>`;
    return;
  }
  if (!data.tim_thay) {
    kq.innerHTML = `<div class="text-[11px] text-amber-300">${esc(data.ghi_chu || 'Không tìm thấy dòng nào khớp.')}</div>`;
    return;
  }
  kq.innerHTML = '<div class="rounded-lg border border-emerald-500/25 bg-emerald-500/[0.04] p-3">'
    + '<div class="text-[10px] text-emerald-400 uppercase tracking-wider mb-2">Tìm thấy</div>'
    + '<div class="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1 text-[11px]">'
    + Object.entries(data.du_lieu).map(([k, v]) =>
        `<div class="text-gray-500 font-mono">${esc(k)}</div><div class="text-gray-200">${esc(v)}</div>`).join('')
    + '</div></div>';
}

async function deleteDataSource(id) {
  const s = dataSources.find(x => x.source_id === id);
  if (!confirm(`Xoá nguồn "${s ? s.name : id}"? Dữ liệu nó đã nạp vào kho tri thức cũng bị gỡ theo.`)) return;
  const data = await apiSend('/api/data-sources/' + id, undefined, 'DELETE');
  if (baoLoi(data)) return;
  closeDataSource();
  thongBao(`Đã xoá nguồn "${s ? s.name : id}".`, 'xong');
  loadDataSources();
}

// =====================================================================
// CHẠY CHIẾN DỊCH (F6 + F9 + F10)
// =====================================================================

let cpId = '';
let cpWS = null;
let cpTimer = null;

/** Chiến dịch đang chọn ở trang Danh bạ.
 *
 * app.js giữ lựa chọn trong biến toàn cục `selectedCampaign` (chọn bằng chip,
 * không phải thẻ select), nên đọc thẳng biến đó thay vì dò DOM. */
function campaignDangChon() {
  return (typeof selectedCampaign !== 'undefined' && selectedCampaign) || '';
}

async function initCampaignRunner() {
  const id = campaignDangChon();
  cpId = id;
  o('cpNoCampaign').classList.toggle('hidden', !!id);
  o('cpBody').classList.toggle('hidden', !id);
  if (!id) { dongCampaignWS(); return; }

  const [cd, scs, voices, devs] = await Promise.all([
    apiGet('/api/phones/campaigns/' + id),
    apiGet('/api/scenarios?direction=outbound'),
    apiGet('/api/voices'),
    apiGet('/api/devices'),
  ]);
  if (cd.error) return;
  const c = cd.campaign;

  o('cpScenario').innerHTML = '<option value="">Kịch bản mặc định</option>' +
    (scs.scenarios || []).map(s =>
      `<option value="${s.scenario_id}" ${c.scenario_id === s.scenario_id ? 'selected' : ''}>${esc(s.name)}</option>`).join('');
  o('cpVoice').innerHTML = (voices.voices || []).map(v =>
    `<option value="${v.name}" ${c.voice_name === v.name ? 'selected' : ''}>${esc(v.name)}</option>`).join('')
    || '<option value="default">Giọng mặc định</option>';

  let daChon = [];
  try { daChon = JSON.parse(c.device_ids || '[]'); } catch { daChon = []; }
  o('cpDevices').innerHTML = (devs.devices || []).map(d =>
    `<option value="${d.device_id}" ${daChon.includes(d.device_id) ? 'selected' : ''}>${esc(d.name)} (${d.status})</option>`).join('');
  o('cpDevices').size = Math.min(4, Math.max(1, (devs.devices || []).length));
  o('cpDevices').style.height = '';

  o('cpConcurrency').value = c.concurrency || 1;
  o('cpStartDate').value = c.start_date || '';
  o('cpEndDate').value = c.end_date || '';
  o('cpRetryNoAnswer').checked = !!c.retry_no_answer;
  o('cpRetryBusy').checked = !!c.retry_busy;
  o('cpRetryVoicemail').checked = !!c.retry_voicemail;
  o('cpRetryMax').value = c.retry_max ?? 3;
  o('cpRetryDelay').value = c.retry_delay_min ?? 30;
  o('cpOnVoicemail').value = c.on_voicemail || 'hangup';
  o('cpDetectGender').checked = c.detect_gender !== 0;
  o('cpRecord').checked = c.record_calls !== 0;

  let khung = [];
  try { khung = JSON.parse(c.call_windows || '[]'); } catch { khung = []; }
  if (!khung.length) {
    khung = [{ days: [1, 2, 3, 4, 5], from: '08:00', to: '11:30' },
             { days: [1, 2, 3, 4, 5], from: '13:30', to: '17:00' }];
  }
  o('cpWindows').innerHTML = khung.map(veKhungGio).join('');

  capNhatTienDo();
}

function veKhungGio(k) {
  const thu = [[1, 'T2'], [2, 'T3'], [3, 'T4'], [4, 'T5'], [5, 'T6'], [6, 'T7'], [7, 'CN']];
  return `<div class="flex items-center gap-1.5" data-window>
    <input type="time" class="inp cw-from" style="width:96px" value="${esc(k.from)}">
    <span class="text-gray-600 text-xs">→</span>
    <input type="time" class="inp cw-to" style="width:96px" value="${esc(k.to)}">
    <div class="flex gap-0.5 ml-1">
      ${thu.map(([n, ten]) => `
        <label class="cursor-pointer nut-thu">
          <input type="checkbox" class="cw-day" value="${n}" ${(k.days || []).includes(n) ? 'checked' : ''}>
          <span class="tag">${ten}</span>
        </label>`).join('')}
    </div>
    <button onclick="this.closest('[data-window]').remove()" class="btn btn-ghost px-2">×</button>
  </div>`;
}

function addCallWindow() {
  o('cpWindows').insertAdjacentHTML('beforeend',
    veKhungGio({ days: [1, 2, 3, 4, 5], from: '08:00', to: '17:00' }));
}

function toggleCampaignSettings() {
  const el = o('cpSettings');
  el.classList.toggle('hidden');
  o('cpSettingsToggle').textContent = el.classList.contains('hidden') ? 'Cài đặt khác' : 'Ẩn cài đặt';
}

async function saveCampaignSettings() {
  if (!cpId) return;
  const khung = [...document.querySelectorAll('#cpWindows [data-window]')].map(d => ({
    from: d.querySelector('.cw-from').value,
    to: d.querySelector('.cw-to').value,
    days: [...d.querySelectorAll('.cw-day:checked')].map(x => parseInt(x.value)),
  })).filter(k => k.from && k.to && k.days.length);

  const data = await apiSend('/api/phones/campaigns/' + cpId, {
    scenario_id: o('cpScenario').value,
    voice_name: o('cpVoice').value,
    device_ids: JSON.stringify([...o('cpDevices').selectedOptions].map(x => x.value)),
    concurrency: parseInt(o('cpConcurrency').value) || 1,
    start_date: o('cpStartDate').value,
    end_date: o('cpEndDate').value,
    call_windows: JSON.stringify(khung),
    retry_no_answer: o('cpRetryNoAnswer').checked ? 1 : 0,
    retry_busy: o('cpRetryBusy').checked ? 1 : 0,
    retry_voicemail: o('cpRetryVoicemail').checked ? 1 : 0,
    retry_max: parseInt(o('cpRetryMax').value) || 3,
    retry_delay_min: parseInt(o('cpRetryDelay').value) || 30,
    on_voicemail: o('cpOnVoicemail').value,
    detect_gender: o('cpDetectGender').checked ? 1 : 0,
    record_calls: o('cpRecord').checked ? 1 : 0,
  }, 'PATCH');
  if (baoLoi(data)) return;
  o('cpProgress').textContent = 'Đã lưu cài đặt.';
}

async function startCampaign() {
  if (!cpId) return;
  await saveCampaignSettings();          // chạy đúng thứ vừa chỉnh, không phải bản cũ
  const data = await apiSend(`/api/phones/campaigns/${cpId}/start`);
  if (baoLoi(data)) return;
  moCampaignWS();
  capNhatTienDo();
}

async function pauseCampaign() {
  const data = await apiSend(`/api/phones/campaigns/${cpId}/pause`);
  if (baoLoi(data)) return;
  capNhatTienDo();
}

async function resumeCampaign() {
  const data = await apiSend(`/api/phones/campaigns/${cpId}/resume`);
  if (baoLoi(data)) return;
  capNhatTienDo();
}

async function stopCampaign() {
  if (!confirm('Dừng chiến dịch? Các cuộc đang gọi sẽ được nói nốt.')) return;
  const data = await apiSend(`/api/phones/campaigns/${cpId}/stop`);
  if (baoLoi(data)) return;
  dongCampaignWS();
  capNhatTienDo();
}

async function capNhatTienDo() {
  if (!cpId) return;
  const data = await apiGet(`/api/phones/campaigns/${cpId}/progress`);
  veTienDo(data.tien_do || {}, data);
}

function veTienDo(p, tong) {
  const dangChay = p.trang_thai === 'dang_chay';
  const tamDung = p.trang_thai === 'tam_dung';
  o('cpBtnStart').classList.toggle('hidden', dangChay || tamDung);
  o('cpBtnPause').classList.toggle('hidden', !dangChay);
  o('cpBtnResume').classList.toggle('hidden', !tamDung);
  o('cpBtnStop').classList.toggle('hidden', !(dangChay || tamDung));

  const phan = [];
  if (p.trang_thai) {
    phan.push({
      dang_chay: 'Đang chạy', tam_dung: 'Tạm dừng',
      xong: 'Đã xong', loi: 'Lỗi', chua_chay: 'Chưa chạy',
    }[p.trang_thai] || p.trang_thai);
  }
  if (p.da_goi != null) phan.push(`đã gọi ${p.da_goi} · nghe máy ${p.da_nghe_may} (${p.ty_le_nghe_may}%)`);
  if (tong && tong.san_sang != null) phan.push(`còn ${tong.san_sang} số sẵn sàng`);
  if (tong && tong.cho_goi_lai) phan.push(`${tong.cho_goi_lai} số chờ gọi lại`);
  if (p.ly_do) phan.push(p.ly_do);
  o('cpProgress').textContent = phan.join(' · ') || 'Chưa chạy';

  const dang = p.dang_goi || [];
  o('cpActiveCalls').innerHTML = dang.map(c => `
    <div class="flex items-center gap-2 text-[11px] text-gray-400">
      <span class="w-1.5 h-1.5 rounded-full bg-cyan-400 status-dot connecting"></span>
      <span class="font-mono">${esc(c.phone)}</span>
      <span>${esc(c.name || '')}</span>
    </div>`).join('');

  if (dangChay && !cpWS) moCampaignWS();
  if (!dangChay && !tamDung) dongCampaignWS();
}

function moCampaignWS() {
  dongCampaignWS();
  try {
    cpWS = new WebSocket(`ws://${location.host}/ws/campaign/${cpId}`);
    cpWS.onmessage = ev => {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'tien_do') veTienDo(msg, null);
    };
    cpWS.onclose = () => { cpWS = null; };
  } catch { cpWS = null; }
  // Chốt chặn: WebSocket rớt giữa chừng thì tiến độ vẫn phải cập nhật, chỉ là
  // thưa hơn. Không có nó thì màn hình đứng im mà chiến dịch vẫn đang chạy.
  cpTimer = setInterval(capNhatTienDo, 15000);
}

function dongCampaignWS() {
  if (cpWS) { try { cpWS.close(); } catch {} cpWS = null; }
  if (cpTimer) { clearInterval(cpTimer); cpTimer = null; }
}

async function importFromCampaign() {
  if (!cpId) { alert('Chọn chiến dịch đích ở ô lọc trước'); return; }
  const ds = await apiGet('/api/phones/campaigns');
  const khac = (ds.campaigns || []).filter(c => c.campaign_id !== cpId);
  if (!khac.length) { alert('Không có chiến dịch nào khác để lấy số'); return; }

  const chon = prompt(
    'Lấy số từ chiến dịch nào? Nhập số thứ tự:\n\n' +
    khac.map((c, i) => `${i + 1}. ${c.name} (${c.total} số)`).join('\n'));
  if (!chon) return;
  const nguon = khac[parseInt(chon) - 1];
  if (!nguon) { alert('Số thứ tự không hợp lệ'); return; }

  const tt = prompt('Lấy các số có trạng thái nào? (cách nhau bởi dấu phẩy)',
    'busy,no_answer');
  if (!tt) return;

  const data = await apiSend(`/api/phones/campaigns/${cpId}/import-from`, {
    source_campaign_id: nguon.campaign_id,
    statuses: tt.split(',').map(s => s.trim()).filter(Boolean),
  });
  if (baoLoi(data)) return;
  alert(`Đã chuyển ${data.imported} số sang chiến dịch này.\n${data.ghi_chu || ''}`);
  if (window.loadContacts) loadContacts();
  capNhatTienDo();
}

// =====================================================================
// TELEGRAM (F11) + GHI ÂM (F12)
// =====================================================================

async function loadNotifyChannels() {
  const data = await apiGet('/api/notify/channels');
  const ds = data.channels || [];
  o('notifyChannels').innerHTML = ds.length ? ds.map(k => `
    <div class="flex items-center gap-2 flex-wrap p-2 bg-void rounded-lg border border-slate-750">
      <input class="inp nt-name" style="width:150px" value="${esc(k.name)}" data-id="${k.channel_id}">
      <input class="inp nt-token font-mono" style="width:200px" placeholder="Token bot"
             value="${esc((k.config || {}).token || '')}">
      <input class="inp nt-chat font-mono" style="width:130px" placeholder="chat_id"
             value="${esc((k.config || {}).chat_id || '')}">
      <div class="flex items-center gap-2">
        ${[['call_success', 'Mỗi cuộc'], ['daily_summary', 'Cuối ngày'], ['campaign_done', 'Xong chiến dịch']]
          .map(([ev, nhan]) => `
          <label class="flex items-center gap-1 text-[11px] text-gray-400 cursor-pointer">
            <input type="checkbox" class="nt-ev accent-cyan-500" value="${ev}"
                   ${(k.events || []).includes(ev) ? 'checked' : ''}> ${nhan}</label>`).join('')}
      </div>
      <div class="ml-auto flex items-center gap-1.5">
        ${k.last_error ? `<span class="pill st-error" title="${esc(k.last_error)}">lỗi</span>` : ''}
        <button onclick="saveNotifyChannel(this)" class="btn btn-ghost">Lưu</button>
        <button onclick="testNotify('${k.channel_id}')" class="btn btn-ghost">Gửi thử</button>
        <button onclick="deleteNotifyChannel('${k.channel_id}')" class="btn btn-ghost hover:text-red-400">Xoá</button>
      </div>
    </div>`).join('')
    : '<div class="text-xs text-gray-600">Chưa có bot Telegram nào.</div>';
}

function addNotifyChannel() {
  o('notifyChannels').insertAdjacentHTML('afterbegin', `
    <div class="flex items-center gap-2 flex-wrap p-2 bg-void rounded-lg border border-cyan-500/25">
      <input class="inp nt-name" style="width:150px" placeholder="Tên bot" data-id="">
      <input class="inp nt-token font-mono" style="width:200px" placeholder="Token bot">
      <input class="inp nt-chat font-mono" style="width:130px" placeholder="chat_id">
      <div class="flex items-center gap-2">
        ${[['call_success', 'Mỗi cuộc'], ['daily_summary', 'Cuối ngày'], ['campaign_done', 'Xong chiến dịch']]
          .map(([ev, nhan]) => `
          <label class="flex items-center gap-1 text-[11px] text-gray-400 cursor-pointer">
            <input type="checkbox" class="nt-ev accent-cyan-500" value="${ev}" checked> ${nhan}</label>`).join('')}
      </div>
      <button onclick="saveNotifyChannel(this)" class="btn btn-primary ml-auto">Lưu</button>
    </div>`);
}

async function saveNotifyChannel(btn) {
  const row = btn.closest('div.flex');
  const data = await apiSend('/api/notify/channels', {
    channel_id: row.querySelector('.nt-name').dataset.id || '',
    name: row.querySelector('.nt-name').value.trim() || 'Telegram',
    token: row.querySelector('.nt-token').value.trim(),
    chat_id: row.querySelector('.nt-chat').value.trim(),
    events: [...row.querySelectorAll('.nt-ev:checked')].map(x => x.value),
    enabled: true,
  });
  if (baoLoi(data)) return;
  loadNotifyChannels();
}

async function testNotify(id) {
  const data = await apiSend('/api/notify/test', { channel_id: id });
  if (baoLoi(data)) return;
  const r = (data.ket_qua || [])[0];
  alert(r && r.ok ? 'Đã gửi. Kiểm tra Telegram.' : `Gửi thất bại: ${r ? r.loi : 'không rõ'}`);
  loadNotifyChannels();
}

async function deleteNotifyChannel(id) {
  if (!confirm('Xoá kênh này?')) return;
  await apiSend('/api/notify/channels/' + id, undefined, 'DELETE');
  loadNotifyChannels();
}

async function loadRecordingStats() {
  const data = await apiGet('/api/reports/recordings/stats');
  o('recordingStats').textContent =
    `${data.so_file || 0} bản ghi · ${data.dung_luong_mb || 0} MB · ${data.so_ngay || 0} ngày`;
  if (data.giu_ngay) o('recCleanupDays').value = data.giu_ngay;
}

async function cleanupRecordings() {
  const ngay = parseInt(o('recCleanupDays').value) || 90;
  if (!confirm(`Xoá vĩnh viễn mọi bản ghi cũ hơn ${ngay} ngày?`)) return;
  const data = await apiSend(`/api/reports/recordings/cleanup?older_than_days=${ngay}`);
  if (baoLoi(data)) return;
  alert(`Đã xoá ${data.da_xoa} file, giải phóng ${data.giai_phong_mb} MB.`);
  loadRecordingStats();
}

// =====================================================================
// NHẬN CUỘC GỌI ĐẾN (F17)
// =====================================================================

async function loadInboundPanel() {
  o('inboundPanel').classList.remove('hidden');
  const [devs, tt, scs] = await Promise.all([
    apiGet('/api/devices'),
    apiGet('/api/devices/inbound/status'),
    apiGet('/api/scenarios?direction=inbound'),
  ]);
  const dangNghe = new Map((tt.devices || []).map(d => [d.device_id, d]));
  const adb = (devs.devices || []).filter(d => d.kind === 'adb');

  o('inboundRows').innerHTML = adb.length ? adb.map(d => {
    const s = dangNghe.get(d.device_id);
    const bat = s && s.dang_nghe;
    return `<div class="flex items-center gap-3 flex-wrap p-2 bg-void rounded-lg border border-slate-750">
      <span class="text-sm text-white" style="min-width:140px">${esc(d.name)}</span>
      <select class="inp ib-scenario" style="width:200px" data-id="${d.device_id}">
        <option value="">Kịch bản mặc định</option>
        ${(scs.scenarios || []).map(x =>
          `<option value="${x.scenario_id}" ${d.inbound_scenario_id === x.scenario_id ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}
      </select>
      <div style="width:130px">
        <input type="number" step="0.5" min="0" class="inp ib-delay"
               value="${d.inbound_delay_s ?? 2}" title="Đợi mấy giây rồi mới bắt máy">
      </div>
      <span class="text-[11px] text-gray-500">${bat ? `đã nhận ${s.da_nhan} cuộc` : ''}</span>
      ${s && s.loi ? `<span class="pill st-error" title="${esc(s.loi)}">lỗi</span>` : ''}
      <button onclick="toggleInbound('${d.device_id}', ${bat ? 'false' : 'true'}, this)"
              class="btn ${bat ? 'btn-ghost hover:text-red-400' : 'btn-soft'} ml-auto">
        ${bat ? 'Tắt' : 'Bật nhận cuộc gọi'}</button>
    </div>`;
  }).join('')
    : '<div class="text-xs text-gray-600">Chưa có máy ADB nào. Thêm máy ở bảng bên dưới.</div>';
}

async function toggleInbound(id, bat, btn) {
  const row = btn.closest('div.flex');
  let url = `/api/devices/${id}/inbound/${bat ? 'enable' : 'disable'}`;
  if (bat) {
    const sc = row.querySelector('.ib-scenario').value;
    const delay = row.querySelector('.ib-delay').value || 2;
    url += `?scenario_id=${encodeURIComponent(sc)}&delay_s=${delay}`;
  }
  const data = await apiSend(url);
  if (baoLoi(data)) return;
  loadInboundPanel();
}

// ---------- khởi động ----------

document.addEventListener('DOMContentLoaded', () => {
  // Trang chủ là Tổng quan. app.js không biết trang này nên phải gọi ở đây.
  loadOverview();
  // Bọc `selectCampaign` của app.js để khối "chạy chiến dịch" đổi theo chip
  // người dùng vừa bấm. Bọc thay vì sửa app.js: sửa trực tiếp thì lần sau đọc
  // code không ai biết ai đang ghi đè ai.
  if (typeof window.selectCampaign === 'function') {
    const goc = window.selectCampaign;
    window.selectCampaign = function (id) {
      goc(id);
      setTimeout(initCampaignRunner, 50);
    };
  }
});

// =====================================================================
// NHẮN TIN - kiểm thử tư vấn bằng chữ
// =====================================================================
//
// Đường đi: gõ chữ -> {type:'text_soi'} -> process_text_turn(soi=True). Chế độ
// soi đi trọn vòng nghiệp vụ (lượt thường gặp, tra hồ sơ, RAG, LLM, lưới chặn
// số) nhưng BỎ câu đệm và BỎ sinh tiếng, đổi lại `metrics` mang thêm dấu vết
// chẩn đoán: nguồn RAG kèm điểm khớp, cờ đường đi, lưới chặn đã bắt gì.
//
// WebSocket RIÊNG, KHÔNG dùng chung `ws` của app.js. Dùng chung là hai trang đổ
// vào cùng một CallSession: lịch sử lẫn nhau và AI coi lượt gõ với lượt nói là
// một cuộc trò chuyện. Trang Hội thoại cố ý bỏ ô gõ chữ để số đo ở đó là số
// thật của đường thoại - tách hẳn phiên là cách duy nhất giữ được điều đó.

let msgWs = null;
let msgSessionId = null;
let msgLuot = 0;
let msgDangCho = false;
let msgOTraLoi = null;        // <div> câu trả lời đang chảy về
let msgChuoiTraLoi = '';
let msgDaGanPhim = false;

function msgTrangThai(chu, mau = 'text-gray-600') {
  const el = document.getElementById('msgTrangThai');
  if (el) { el.textContent = chu; el.className = `text-[10px] font-mono ${mau}`; }
}

function initMessaging() {
  msgNoi();
  msgNapToc();
  if (!msgDaGanPhim) {
    const o = document.getElementById('msgInput');
    o.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); msgGui(); }
    });
    msgDaGanPhim = true;
  }
  setTimeout(() => document.getElementById('msgInput')?.focus(), 50);
}

function msgNoi() {
  if (msgWs && (msgWs.readyState === WebSocket.OPEN || msgWs.readyState === WebSocket.CONNECTING)) return;
  const giaoThuc = location.protocol === 'https:' ? 'wss:' : 'ws:';
  // Nối lại bằng ĐÚNG session cũ: mất mạng giữa chừng mà xin phiên mới thì AI
  // quên sạch mấy lượt vừa rồi, còn người soi thì không nhận ra vì khung chat
  // vẫn còn nguyên chữ trên màn hình.
  msgWs = new WebSocket(`${giaoThuc}//${location.host}/ws/call/${msgSessionId || 'new'}`);

  msgWs.onopen = () => { msgTrangThai('đã nối', 'text-emerald-400'); msgGuiCauHinh(); };
  msgWs.onmessage = (e) => msgNhan(JSON.parse(e.data));
  msgWs.onclose = () => {
    msgTrangThai('mất kết nối - đang nối lại', 'text-amber-400');
    msgHienCho(false);
    setTimeout(msgNoi, 3000);
  };
  msgWs.onerror = () => msgTrangThai('lỗi kết nối', 'text-red-400');
}

function msgGuiCauHinh() {
  if (!msgWs || msgWs.readyState !== WebSocket.OPEN) return;
  msgWs.send(JSON.stringify({
    type: 'set_session',
    customer_name: document.getElementById('msgCustomerName').value,
    product: document.getElementById('msgProduct').value,
  }));
}

function msgHienCho(bat) {
  msgDangCho = bat;
  document.getElementById('msgTyping').classList.toggle('hidden', !bat);
  document.getElementById('msgSend').disabled = bat;
}

function msgCuonXuong() {
  const l = document.getElementById('msgList');
  l.scrollTop = l.scrollHeight;
}

function msgGui() {
  const o = document.getElementById('msgInput');
  const chu = o.value.trim();
  if (!chu || msgDangCho) return;
  if (!msgWs || msgWs.readyState !== WebSocket.OPEN) {
    msgTrangThai('chưa nối - thử lại sau giây lát', 'text-amber-400');
    return;
  }

  document.getElementById('msgWelcome')?.remove();
  msgThemBongKhach(chu);
  msgLuot += 1;
  msgWs.send(JSON.stringify({ type: 'text_soi', text: chu, turn_id: msgLuot }));
  o.value = '';
  msgChuoiTraLoi = '';
  msgOTraLoi = null;
  msgHienCho(true);
}

function msgXoaHoiThoai() {
  msgDungTieng();
  document.getElementById('msgList').innerHTML =
    '<div class="text-xs text-gray-600 text-center py-4">Đã xóa. Lịch sử phía AI vẫn giữ - mở lại trang hoặc tải lại app để bắt đầu phiên mới.</div>';
  msgChuoiTraLoi = '';
  msgOTraLoi = null;
}

function msgThemBongKhach(chu) {
  const d = document.createElement('div');
  d.className = 'flex animate-fade-up';
  d.innerHTML = `<div class="ml-auto max-w-2xl bg-cyan-500/10 border border-cyan-500/20 rounded-lg px-3 py-2 text-sm text-gray-200 whitespace-pre-wrap break-words">${esc(chu)}</div>`;
  document.getElementById('msgList').appendChild(d);
  msgCuonXuong();
}

function msgBatDauTraLoi() {
  const boc = document.createElement('div');
  boc.className = 'animate-fade-up';
  boc.innerHTML =
    '<div class="max-w-2xl bg-deep border border-slate-750 rounded-lg px-3 py-2 text-sm text-gray-200 whitespace-pre-wrap break-words" data-vaitro="loi"></div>' +
    '<div class="max-w-2xl mt-1.5" data-vaitro="soi"></div>';
  document.getElementById('msgList').appendChild(boc);
  msgOTraLoi = boc;
  return boc;
}

function msgNhan(m) {
  switch (m.type) {
    case 'connected':
      msgSessionId = m.session_id;
      break;

    case 'response_chunk':
      // Dùng `response_chunk` chứ không dùng `token`: đây là chữ ĐÃ qua bộ lọc
      // xưng hô, tức đúng thứ khách sẽ nghe. Token thô còn "chúng tôi" chưa đổi.
      if (!msgOTraLoi) msgBatDauTraLoi();
      msgChuoiTraLoi += (msgChuoiTraLoi ? ' ' : '') + (m.text || '');
      msgOTraLoi.querySelector('[data-vaitro="loi"]').textContent = msgChuoiTraLoi;
      msgCuonXuong();
      break;

    case 'turn_complete': {
      msgHienCho(false);
      if (!msgOTraLoi && !m.full_response) break;
      const boc = msgOTraLoi || msgBatDauTraLoi();
      const cau = m.full_response || msgChuoiTraLoi;
      boc.querySelector('[data-vaitro="loi"]').textContent = cau;
      boc.querySelector('[data-vaitro="soi"]').innerHTML = msgPhieuSoi(m.metrics || {}, cau);
      msgOTraLoi = null;
      msgChuoiTraLoi = '';
      msgCuonXuong();
      break;
    }

    case 'error': {
      msgHienCho(false);
      const d = document.createElement('div');
      d.className = 'text-xs text-red-400 bg-red-500/10 border border-slate-750 rounded-lg px-3 py-2';
      d.textContent = m.message || 'Lỗi không rõ';
      document.getElementById('msgList').appendChild(d);
      msgCuonXuong();
      break;
    }
  }
}

// ---------- phiếu soi ----------

function msgChip(chu, mau = 'text-gray-400') {
  return `<span class="text-[10px] font-mono px-2 py-0.5 rounded bg-void border border-slate-750 ${mau}">${chu}</span>`;
}

function msgPhieuSoi(m, cau) {
  const chips = [];

  // --- đường đi: câu này do ĐÂU trả lời ---
  // Không có mấy cờ này thì rất dễ tưởng model vừa nghĩ ra câu trả lời, trong
  // khi thực ra nó lấy từ bảng cứng - sửa prompt cả buổi không đổi được gì.
  if (m.luot_thuong_gap) chips.push(msgChip(`bảng sẵn: ${esc(m.luot_thuong_gap)}`, 'text-amber-400'));
  if (m.tra_tu_ho_so) chips.push(msgChip(`hồ sơ: ${esc(m.tra_tu_ho_so)}`, 'text-amber-400'));
  if (m.cong_cu) chips.push(msgChip(`công cụ: ${esc(m.cong_cu)}`, 'text-violet-400'));
  if (m.llm_nghi_san) chips.push(msgChip('bản nghĩ sẵn', 'text-violet-400'));
  if (m.rag_doan_truoc) chips.push(msgChip('RAG đoán trước', 'text-violet-400'));
  if (!m.luot_thuong_gap && !m.tra_tu_ho_so) chips.push(msgChip('RAG → LLM'));

  // --- số đo ---
  if (m.rag_ms != null) chips.push(msgChip(`RAG ${m.rag_ms}ms`));
  if (m.llm_ttft_ms != null) chips.push(msgChip(`LLM đầu ${m.llm_ttft_ms}ms`));
  if (m.total_ms != null) chips.push(msgChip(`tổng ${m.total_ms}ms`));
  if (m.llm_tokens != null) chips.push(msgChip(`${m.llm_tokens} token`));

  // --- lưới chặn ---
  if (m.chan_so_sai) chips.push(msgChip(`chặn số: ${esc(m.chan_so_sai)}`, 'text-red-400'));
  if (m.chan_tien_sai) chips.push(msgChip(`chặn tiền: ${esc(m.chan_tien_sai)}`, 'text-red-400'));

  let html = `<div class="flex flex-wrap gap-1.5 items-center">${chips.join('')}` +
    `<button class="text-[10px] font-mono px-2 py-0.5 rounded bg-void border border-slate-750 text-cyan-400" ` +
    `onclick="msgNgheThu(this)" data-cau="${esc(cau)}">▶ nghe thử</button></div>`;

  // --- nguồn RAG ---
  const nguon = m.rag_nguon || [];
  if (nguon.length) {
    const dong = nguon.map(n => {
      const mau = n.bi_loc ? 'text-gray-600 opacity-50' : 'text-gray-400';
      const nhan = n.bi_loc ? msgChip('ĐÃ LỌC', 'text-amber-300') : '';
      const diem = n.diem == null ? '—' : n.diem;
      const trich = (n.doan || '').replace(/\s+/g, ' ').slice(0, 140);
      return `<div class="border-l border-slate-750 px-2 py-1 ${mau}">` +
        `<div class="flex flex-wrap gap-1.5 items-center mb-1">` +
        `<span class="text-[10px] font-mono text-violet-400">${esc(n.nguon || 'không rõ nguồn')}</span>` +
        `<span class="text-[10px] font-mono text-gray-600">khớp ${diem}</span>${nhan}</div>` +
        `<div class="text-[10px] font-mono">${esc(trich)}${(n.doan || '').length > 140 ? '…' : ''}</div></div>`;
    }).join('');
    html += `<div class="mt-1.5 space-y-1">` +
      `<div class="text-[10px] font-mono text-gray-600">truy vấn RAG: ${esc(m.rag_truy_van || '—')}</div>` +
      dong + `</div>`;
  }

  return html;
}

async function msgNgheThu(btn) {
  const cau = btn.getAttribute('data-cau') || '';
  if (!cau) return;
  const cu = btn.textContent;
  btn.textContent = '… đang đọc';
  btn.disabled = true;
  // Bấm nút này cũng phải cắt tiếng đang phát: bấm hai câu liền nhau mà không
  // cắt là hai câu chồng lên nhau.
  const luot = ++msgLuotPhat;
  msgDungTieng();
  try {
    const fd = new FormData();
    fd.append('text', cau);
    fd.append('voice_name', document.getElementById('msgVoiceSelect')?.value || 'default');
    // Cắt mảnh y như cuộc gọi: nghe thử mà đọc nguyên câu một phát thì nhịp
    // lệch ~10% so với thứ khách thật sự nghe, tức nghe xong vẫn không biết gì.
    fd.append('cat_manh', 'true');
    const d = await (await fetch('/api/voices/test-tts', { method: 'POST', body: fd })).json();
    if (d.error) { btn.textContent = '✗ ' + d.error.slice(0, 40); return; }
    await msgPhatTieng(d.audio, luot);
    btn.textContent = cu;
  } catch (e) {
    btn.textContent = '✗ lỗi phát';
  } finally {
    btn.disabled = false;
  }
}

// ---------- tốc đọc của giọng đang chọn ----------
//
// Tốc là thuộc tính của GIỌNG, không phải của phiên: backend ghi vào tệp
// `<giọng>.speed` nằm cạnh file wav. Nên kéo thanh này là đổi luôn cho CUỘC GỌI
// THẬT, không riêng trang Nhắn tin. Tiêu đề của khối đã ghi rõ điều đó.
//
// Còn một hệ số THỨ HAI nhân chồng lên khi gọi điện (`/api/voices/phone-speed`).
// Nút "nghe thử" ở trang này CÓ áp hệ số đó, nên nhịp nghe ở đây đúng bằng nhịp
// khách nghe - chỉ khác ở chỗ chưa hạ băng thông xuống 8kHz.
//
// Trước 13-08-2026 thì không: hệ số chỉ được nhân khi `qua_dien_thoai=true`, mà
// cờ đó đồng thời hạ băng thông. Kết quả là nghe ở 24kHz ra 283 âm tiết/phút
// còn cuộc gọi đọc 347, và chú thích cũ ở đây chỉ đi CẢNH BÁO điều đó thay vì
// sửa. Nay `qua_dien_thoai` chỉ còn nghĩa "hạ băng thông".

let msgTocGiong = {};   // tên giọng -> { toc, rieng }

// MỘT thẻ Audio dùng chung cho cả trang, và một số thứ tự lượt phát.
//
// Vì sao cần cả hai: bản đầu tạo `new Audio().play()` mới mỗi lần, không dừng
// cái đang chạy. Kéo thanh tốc vài nhịp là mấy bản tiếng chồng lên nhau, và
// người nghe tưởng "chỉnh tốc không ăn, vẫn ra tốc cũ" - thật ra tiếng tốc cũ
// vẫn đang phát đè lên tiếng tốc mới.
//
// Số lượt lo nốt trường hợp còn lại: yêu cầu cũ chạy chậm về SAU yêu cầu mới thì
// vẫn là tiếng tốc cũ, dừng thẻ Audio không cứu được vì lúc đó nó chưa phát.
let msgTieng = null;
let msgLuotPhat = 0;

function msgDungTieng() {
  if (msgTieng) {
    msgTieng.pause();
    msgTieng.currentTime = 0;
    msgTieng = null;
  }
}

/** Phát một bản WAV base64, cắt hẳn thứ đang phát. `luot` là số thứ tự lấy
 *  trước khi gọi mạng; khác `msgLuotPhat` nghĩa là đã có yêu cầu mới hơn -> bỏ. */
async function msgPhatTieng(b64, luot) {
  if (luot !== msgLuotPhat) return;
  msgDungTieng();
  msgTieng = new Audio('data:audio/wav;base64,' + b64);
  try {
    await msgTieng.play();
  } catch { /* trình duyệt chặn tự phát khi không có thao tác người dùng */ }
}

async function msgNapToc() {
  try {
    const d = await (await fetch('/api/voices')).json();
    msgTocGiong = {};
    (d.voices || []).forEach(v => {
      msgTocGiong[v.name] = { toc: +(v.speed ?? 1), rieng: !!v.speed_rieng };
    });
    msgVeToc();
  } catch { /* chưa nạp được thì giữ nguyên thanh trượt */ }
}

function msgVeToc() {
  const ten = document.getElementById('msgVoiceSelect')?.value;
  const t = msgTocGiong[ten];
  const thanh = document.getElementById('msgToc');
  const so = document.getElementById('msgTocSo');
  const nutBo = document.getElementById('msgTocBo');
  if (!thanh || !so || !nutBo) return;
  // Chưa biết tốc của giọng này thì KHOÁ thanh lại thay vì hiện 1.00 - hiện số
  // bịa rồi người dùng kéo từ đó là ghi đè tốc thật bằng một số vô căn cứ.
  if (!t) {
    thanh.disabled = true;
    so.textContent = '—';
    nutBo.classList.add('hidden');
    return;
  }
  thanh.disabled = false;
  thanh.value = t.toc;
  so.textContent = t.toc.toFixed(2);
  so.className = `text-[10px] font-mono w-8 ${t.rieng ? 'text-violet-400' : 'text-gray-500'}`;
  nutBo.classList.toggle('hidden', !t.rieng);
}

async function msgDatToc(toc) {
  const ten = document.getElementById('msgVoiceSelect').value;
  if (!msgTocGiong[ten]) return;
  // CẮT tiếng đang phát NGAY khi thả thanh trượt, trước cả khi gọi mạng: người
  // dùng vừa đổi tốc thì bản tốc cũ không còn nghĩa gì, để nó chạy tiếp là vừa
  // chồng tiếng vừa làm tưởng chỉnh tốc không ăn.
  msgDungTieng();
  try {
    const d = await (await fetch(`/api/voices/${encodeURIComponent(ten)}/speed`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ speed: parseFloat(toc) }),
    })).json();
    if (d.error) { alert(d.error); return; }
    await msgNapToc();
    msgNgheThuToc(ten);
  } catch (e) { alert('Lỗi đặt tốc: ' + e.message); }
}

async function msgBoToc() {
  const ten = document.getElementById('msgVoiceSelect').value;
  msgDungTieng();
  await fetch(`/api/voices/${encodeURIComponent(ten)}/speed`, { method: 'DELETE' });
  await msgNapToc();
}

/** Đọc lại NGAY sau khi đổi tốc. Chỉnh tốc mà không nghe lại thì phải mò, và
 *  tiếng cũ trong bộ nhớ đệm từng làm người dùng tưởng nút không ăn. Ưu tiên đọc
 *  chính câu AI vừa trả lời - đó mới là văn bản đang cần nghe cho vừa tai. */
async function msgNgheThuToc(ten) {
  const cuoi = [...document.querySelectorAll('button[data-cau]')].pop();
  const cau = cuoi?.getAttribute('data-cau')
    || 'Dạ em chào anh chị, lãi suất vay tín chấp hiện tại là 7.9% một năm ạ.';
  // Lấy số lượt TRƯỚC khi gọi mạng. Kéo thanh nhanh vài nhịp thì các yêu cầu về
  // không theo thứ tự gửi; bản nào không phải lượt mới nhất là tiếng TỐC CŨ,
  // `msgPhatTieng` sẽ bỏ nó thay vì phát đè.
  const luot = ++msgLuotPhat;
  try {
    const fd = new FormData();
    fd.append('text', cau);
    fd.append('voice_name', ten);
    fd.append('cat_manh', 'true');
    const d = await (await fetch('/api/voices/test-tts', { method: 'POST', body: fd })).json();
    if (d.audio) await msgPhatTieng(d.audio, luot);
  } catch { /* nghe thử hỏng thì thôi, tốc vẫn đã lưu */ }
}
