"""Chay NHIEU hoi thoai NHIEU LUOT qua dung duong WebSocket, roi soi tung luot.

Khac cac script truoc: chung do MOT cau roi le. Cai nay chay ca hoi thoai co ngu
canh, vi loi that hay nam o luot 3-4 khi lich su da day (mo hinh dong khuon,
RAG lac sang san pham khac, lap lai cau truoc).

Moi luot kiem BON thu:
  1. RAG co lay manh cua SAN PHAM KHAC ma khong bi loc?  (loi "RAG lac san pham")
  2. Luoi chan so/tien co phai ra tay?                    (model doc sai so)
  3. Cho STT nghe lai tieng -> co mat/thua chu?
  4. Do tre

Chay TREN MAY WIN:
    set PYTHONIOENCODING=utf-8 && .venv\\python.exe scripts\\test_nhieu_hoi_thoai.py
"""
import asyncio
import base64
import difflib
import io
import json
import re
import sys
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import websockets

from backend.pipeline.text_normalizer import normalize_for_tts

WS = "ws://127.0.0.1:8100/ws/call/new"
TTS = "http://127.0.0.1:8100/api/voices/test-tts"
STT = "http://127.0.0.1:8178/inference"
GIONG = "giong_heu"

HOI_THOAI = [
    ("vay tín chấp", [
        "xin chào em",
        "lãi suất vay tín chấp bao nhiêu",
        "vay được tối đa bao nhiêu",
        "cần giấy tờ gì không em",
        "bao lâu thì giải ngân",
    ]),
    ("vay tín chấp", [
        "anh cần vay 80 triệu",
        "trả trong 36 tháng thì mỗi tháng bao nhiêu",
        "lãi suất có thay đổi không",
        "anh đang nợ chỗ khác thì có vay được không",
    ]),
    ("vay mua nhà", [
        "em ơi anh muốn vay mua nhà",
        "lãi suất thế nào",
        "vay được bao nhiêu phần trăm giá trị nhà",
        "thời hạn tối đa mấy năm",
    ]),
    ("thẻ tín dụng", [
        "cho anh hỏi về thẻ tín dụng",
        "hạn mức bao nhiêu",
        "phí thường niên thế nào",
    ]),
    ("vay tín chấp", [
        "anh không quan tâm đâu",
        "đang bận",
        "thôi để hôm khác đi",
    ]),
]

SAN_PHAM_MA = {"vay tín chấp": "vay_tin_chap", "vay mua nhà": "vay_mua_nha",
               "thẻ tín dụng": "the_tin_dung", "tiết kiệm": "tiet_kiem"}


def _sinh_tieng(text):
    d = urllib.parse.urlencode({"text": text, "voice_name": GIONG}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS, data=d), timeout=300) as r:
        return json.load(r)


def _nghe(b64):
    ranh = uuid.uuid4().hex
    b = io.BytesIO()
    w = lambda s: b.write(s if isinstance(s, bytes) else s.encode("utf-8"))
    w(f"--{ranh}\r\n"); w('Content-Disposition: form-data; name="file"; filename="a.wav"\r\n')
    w("Content-Type: application/octet-stream\r\n\r\n"); w(base64.b64decode(b64)); w("\r\n")
    for k, v in (("language", "vi"), ("response_format", "json")):
        w(f"--{ranh}\r\n"); w(f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    w(f"--{ranh}--\r\n")
    req = urllib.request.Request(STT, data=b.getvalue(),
        headers={"Content-Type": f"multipart/form-data; boundary={ranh}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r).get("text", "").strip()


def _tu(s):
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return [t for t in s.split() if t]


def _lech(mong, nghe):
    a, b = _tu(mong), _tu(nghe)
    mat, them = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if op in ("delete", "replace"):
            mat += a[i1:i2]
        if op in ("insert", "replace"):
            them += b[j1:j2]
    return mat, them


async def chay_mot(san_pham, cau_hoi, so):
    ket = []
    async with websockets.connect(WS, max_size=None, open_timeout=30) as ws:
        await ws.recv()      # {"type":"connected"}
        await ws.send(json.dumps({"type": "set_session", "customer_name": "Anh Minh",
                                  "product": san_pham}))
        while True:
            m = json.loads(await ws.recv())
            if m.get("type") == "session_updated":
                break
        for i, q in enumerate(cau_hoi, 1):
            await ws.send(json.dumps({"type": "text_soi", "text": q, "turn_id": i}))
            tra, mt = "", {}
            while True:
                m = json.loads(await asyncio.wait_for(ws.recv(), timeout=180))
                if m.get("type") == "turn_complete":
                    tra, mt = m.get("full_response", ""), m.get("metrics", {})
                    break
            ket.append((q, tra, mt))
    return ket


def soi(san_pham, ket, so):
    ma = SAN_PHAM_MA.get(san_pham, "")
    print(f"\n{'='*88}\nHỘI THOẠI {so} — sản phẩm: {san_pham}")
    for i, (q, tra, mt) in enumerate(ket, 1):
        canh = []
        # 1. RAG lấy mảnh sản phẩm KHÁC mà không bị lọc
        for n in (mt.get("rag_nguon") or []):
            ng = (n.get("nguon") or "").replace(".md", "")
            if not n.get("bi_loc") and ng in SAN_PHAM_MA.values() and ng != ma:
                canh.append(f"RAG LẠC: {ng} (khớp {n.get('diem')})")
        # 2. Lưới chặn ra tay
        if mt.get("chan_so_sai"):
            canh.append(f"CHẶN SỐ: {mt['chan_so_sai']}")
        if mt.get("chan_tien_sai"):
            canh.append(f"CHẶN TIỀN: {mt['chan_tien_sai']}")
        # 3. STT nghe lại
        rac = ""
        if tra.strip():
            r = _sinh_tieng(tra)
            if not r.get("error"):
                mat, them = _lech(normalize_for_tts(tra), _nghe(r["audio"]))
                if mat or them:
                    rac = f"mất={mat} thừa={them}"
        duong = mt.get("luot_thuong_gap") or mt.get("cong_cu") or "RAG→LLM"
        print(f"  {i}. K: {q}")
        print(f"     A: {tra[:96]}")
        print(f"     [{duong} · {mt.get('total_ms','?')}ms]"
              + (f"  ⚠ {' | '.join(canh)}" if canh else "")
              + (f"  ♪ {rac}" if rac else ""))
    return ket


async def main():
    tong_luot = tong_canh = tong_rac = 0
    for i, (sp, qs) in enumerate(HOI_THOAI, 1):
        try:
            ket = await chay_mot(sp, qs, i)
        except Exception as e:
            print(f"HỘI THOẠI {i}: LỖI {e}")
            continue
        soi(sp, ket, i)
        tong_luot += len(ket)
    print(f"\n{'='*88}\nTỔNG: {tong_luot} lượt trên {len(HOI_THOAI)} hội thoại")


if __name__ == "__main__":
    asyncio.run(main())
