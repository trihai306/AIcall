// Vỏ ngoài của app: thanh trên, bảng lệnh Ctrl+K, thu gọn thanh bên, gập nhóm
// điều hướng và hai bảng phụ của trang Tổng quan.
//
// Nạp SAU app.js và trang_moi.js. Không sửa hàm nào của hai file đó: chỉ đọc
// thanh điều hướng có sẵn và gọi `switchPage`. Mọi chuỗi từ server đều đi qua
// textContent, không qua innerHTML.

(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  function nho(khoa, giaTri) {           // localStorage có thể bị chặn (app đóng gói)
    try {
      if (giaTri === undefined) return localStorage.getItem(khoa);
      localStorage.setItem(khoa, giaTri);
    } catch (e) { /* không nhớ được thì thôi */ }
    return null;
  }
  function the(ten, lop, chu) {
    var e = document.createElement(ten);
    if (lop) e.className = lop;
    if (chu !== undefined && chu !== null) e.textContent = chu;
    return e;
  }
  function boDau(s) {
    return (s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd');
  }

  // ---------------------------------------------------------------- thanh trên
  // Tên nhóm + tên trang lấy từ chính thanh điều hướng, không chép bảng tên ra
  // chỗ thứ hai rồi lệch nhau về sau.
  window.capNhatCrumb = function () {
    var nut = document.querySelector('.nav-btn.active');
    if (!nut || !$('crumbPage')) return;
    var nhom = nut.closest('.nav-sec');
    var ten = nhom && nhom.querySelector('.nav-group span');
    $('crumbPage').textContent = nut.textContent.trim();
    $('crumbGroup').textContent = ten ? ten.textContent.trim() : '';
    document.title = nut.textContent.trim() + ' · VoiceBank AI';
  };

  function chip(ten, st, phu, lop) {
    var c = the('span', 'svc-chip' + (lop ? ' ' + lop : ''));
    if (st) { c.dataset.st = st; c.appendChild(the('i')); }
    c.appendChild(document.createTextNode(ten));
    if (phu) c.appendChild(the('small', '', phu));
    return c;
  }
  var sucKhoe = null;
  function veChip(d) {
    var o = $('svcChips');
    if (!o) return;
    o.textContent = '';
    if (!d) { o.appendChild(chip('Mất kết nối máy chủ', 'down')); return; }
    var sv = d.services || {};
    var tts = sv.tts === 'loaded' ? 'ok' : (sv.tts ? 'warn' : 'down');
    o.appendChild(chip('STT', sv.stt === 'ok' ? 'ok' : 'down'));
    o.appendChild(chip('LLM', sv.llm === 'ok' ? 'ok' : 'down'));
    o.appendChild(chip('TTS', tts, tts === 'warn' ? 'đang nạp' : ''));
    o.appendChild(chip('Tri thức', /^[1-9]/.test(sv.rag || '') ? 'ok' : 'warn'));
  }
  function hoiSucKhoe() {
    return fetch('/api/health').then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { sucKhoe = d && d.services ? d : null; })
      .catch(function () { sucKhoe = null; })
      .then(function () { veChip(sucKhoe); veHeThong(); });
  }
  function dongHo() {
    var o = $('appClock');
    if (!o) return;
    var n = new Date();
    o.textContent = n.toLocaleDateString('vi-VN', { weekday: 'short', day: '2-digit', month: '2-digit' }) +
      ' · ' + n.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
  }

  // ------------------------------------------------------------- thanh bên
  window.thuGonThanhBen = function () {
    var gon = document.body.classList.toggle('rail');
    nho('vb_rail', gon ? '1' : '0');
  };
  window.gapNhom = function (nut) {
    var sec = nut.closest('.nav-sec');
    var gap = sec.classList.toggle('gap');
    nut.setAttribute('aria-expanded', gap ? 'false' : 'true');
    var dang = [];
    document.querySelectorAll('.nav-sec.gap').forEach(function (s) { dang.push(s.dataset.sec); });
    nho('vb_gap', dang.join(','));
  };
  function khoiPhucThanhBen() {
    if (nho('vb_rail') === '1') document.body.classList.add('rail');
    (nho('vb_gap') || '').split(',').forEach(function (m) {
      var sec = m && document.querySelector('.nav-sec[data-sec="' + m + '"]');
      // Không gập nhóm đang chứa trang hiện tại: mở app ra mà không thấy mình ở đâu.
      if (sec && !sec.querySelector('.nav-btn.active')) {
        sec.classList.add('gap');
        sec.querySelector('.nav-group').setAttribute('aria-expanded', 'false');
      }
    });
    // Dải biểu tượng không còn chữ: tên trang hiện ra khi rê chuột.
    document.querySelectorAll('.nav-btn').forEach(function (b) { b.title = b.textContent.trim(); });
  }

  // ------------------------------------------------------------- bảng lệnh
  var bang = null, oNhap = null, oDs = null, muc = [], chon = 0;
  function dungBang() {
    bang = the('div', 'cmdk hidden');
    bang.addEventListener('mousedown', function (e) { if (e.target === bang) dongBangLenh(); });
    var hop = the('div', 'cmdk-box');
    oNhap = the('input');
    oNhap.type = 'text';
    oNhap.placeholder = 'Tìm trang… (gõ không dấu cũng được)';
    oNhap.setAttribute('aria-label', 'Tìm trang');
    oNhap.addEventListener('input', function () { chon = 0; loc(); });
    oNhap.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') { chon = Math.min(chon + 1, muc.length - 1); to(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { chon = Math.max(chon - 1, 0); to(); e.preventDefault(); }
      else if (e.key === 'Enter' && muc[chon]) { di(muc[chon].dataset.page); e.preventDefault(); }
    });
    oDs = the('div', 'cmdk-list');
    var chan = the('div', 'cmdk-foot', '↑↓ chọn · Enter mở · Esc đóng');
    hop.appendChild(oNhap); hop.appendChild(oDs); hop.appendChild(chan);
    bang.appendChild(hop);
    document.body.appendChild(bang);
  }
  function loc() {
    var q = boDau(oNhap.value.trim());
    oDs.textContent = '';
    muc = [];
    document.querySelectorAll('.nav-sec').forEach(function (sec) {
      var nhom = sec.querySelector('.nav-group span').textContent.trim();
      sec.querySelectorAll('.nav-btn').forEach(function (b) {
        var ten = b.textContent.trim();
        if (q && boDau(ten + ' ' + nhom).indexOf(q) < 0) return;
        var d = the('button', 'cmdk-item');
        d.type = 'button';
        d.dataset.page = b.dataset.page;
        var bt = b.querySelector('svg');
        if (bt) d.appendChild(bt.cloneNode(true));
        d.appendChild(the('span', '', ten));
        d.appendChild(the('small', '', nhom));
        d.addEventListener('click', function () { di(b.dataset.page); });
        d.addEventListener('mousemove', function () { chon = muc.indexOf(d); to(); });
        oDs.appendChild(d);
        muc.push(d);
      });
    });
    if (!muc.length) oDs.appendChild(the('div', 'cmdk-empty', 'Không có trang nào khớp.'));
    to();
  }
  function to() {
    muc.forEach(function (m, i) { m.classList.toggle('chon', i === chon); });
    if (muc[chon]) muc[chon].scrollIntoView({ block: 'nearest' });
  }
  function di(trang) { dongBangLenh(); window.switchPage(trang); }
  window.moBangLenh = function () {
    if (!bang) dungBang();
    bang.classList.remove('hidden');
    oNhap.value = ''; chon = 0; loc();
    oNhap.focus();
  };
  function dongBangLenh() { if (bang) bang.classList.add('hidden'); }
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      if (bang && !bang.classList.contains('hidden')) dongBangLenh(); else window.moBangLenh();
    } else if (e.key === 'Escape') { dongBangLenh(); }
  });

  // -------------------------------------------------- bảng phụ trang Tổng quan
  function dong(nhan, giaTri, st) {
    var d = the('div', 'kv');
    d.appendChild(the('span', '', nhan));
    var v = the('strong', '', giaTri);
    if (st) { var i = the('i'); i.dataset.st = st; v.insertBefore(i, v.firstChild); }
    d.appendChild(v);
    return d;
  }
  function veHeThong() {
    var o = $('overviewSystem');
    if (!o) return;
    o.textContent = '';
    if (!sucKhoe) { o.appendChild(dong('Máy chủ', 'Không kết nối được', 'down')); return; }
    var sv = sucKhoe.services || {}, he = sucKhoe.system || {};
    o.appendChild(dong('Nhận giọng nói (STT)', sv.stt === 'ok' ? (sv.stt_engine || 'Sẵn sàng') : 'Chưa sẵn sàng', sv.stt === 'ok' ? 'ok' : 'down'));
    o.appendChild(dong('Mô hình trả lời (LLM)', sv.llm === 'ok' ? 'Sẵn sàng' : 'Chưa sẵn sàng', sv.llm === 'ok' ? 'ok' : 'down'));
    o.appendChild(dong('Giọng đọc (TTS)', sv.tts === 'loaded' ? 'Đã nạp' : 'Đang nạp…', sv.tts === 'loaded' ? 'ok' : 'warn'));
    o.appendChild(dong('Kho tri thức', (sv.rag || '—').replace(' docs', ' mảnh'), /^[1-9]/.test(sv.rag || '') ? 'ok' : 'warn'));
    if (he.gpu_name) o.appendChild(dong('GPU', he.gpu_name.replace('NVIDIA GeForce ', '') + (he.gpu_vram_gb ? ' · ' + he.gpu_vram_gb + ' GB' : '')));
  }
  var TEN_VIEC = { running: 'Đang chuẩn bị', paused: 'Tạm nhường cuộc gọi', done: 'Đã xong', error: 'Có lỗi cần xem', idle: 'Đang nghỉ', cancelled: 'Đã dừng' };
  function veKho(d) {
    var o = $('overviewBank');
    if (!o) return;
    o.textContent = '';
    if (!d || !d.stats) { o.appendChild(the('div', 'text-xs text-gray-600', 'Chưa đọc được trạng thái kho.')); return; }
    var st = d.stats, job = d.job || {};
    var so = the('div', 'bank-num');
    so.appendChild(the('strong', '', (st.answers || 0).toLocaleString('vi-VN')));
    so.appendChild(the('span', '', 'câu trả lời soạn sẵn'));
    o.appendChild(so);
    var tong = st.voice_total || 0, xong = st.voice_ready || 0;
    var pt = tong ? Math.round(xong * 100 / tong) : 0;
    var thanh = the('div', 'bar'); var ruot = the('div'); ruot.style.width = pt + '%'; thanh.appendChild(ruot);
    o.appendChild(thanh);
    o.appendChild(the('div', 'bank-sub', 'Giọng đọc sẵn ' + xong.toLocaleString('vi-VN') + '/' + tong.toLocaleString('vi-VN') + ' (' + pt + '%)'));
    var hang = the('div', 'bank-row');
    var loi = job.status === 'error';
    var nhan = the('span', 'pill ' + (loi ? 'st-error' : job.status === 'running' ? 'st-calling' : 'st-online'), TEN_VIEC[job.status] || job.status || '—');
    hang.appendChild(nhan);
    hang.appendChild(the('small', '', d.enabled ? 'Tự bổ sung: bật' : 'Tự bổ sung: tắt'));
    o.appendChild(hang);
    if (loi && job.error) o.appendChild(the('div', 'bank-err', job.error.slice(0, 160)));
  }
  window.napBangPhu = function () {
    hoiSucKhoe();
    fetch('/api/knowledge/thu-vien-tu-dong').then(function (r) { return r.ok ? r.json() : null; })
      .then(veKho).catch(function () { veKho(null); });
  };

  // ---------------------------------------------------------------- khởi động
  khoiPhucThanhBen();
  window.capNhatCrumb();
  dongHo(); setInterval(dongHo, 30000);
  window.napBangPhu();
  setInterval(function () {
    var o = $('page-overview');
    if (o && !o.classList.contains('hidden')) window.napBangPhu(); else hoiSucKhoe();
  }, 15000);
})();
