"""Test nhu CUOC GOI THAT: khach NOI, khong go chu.

Khac han bo test truoc. Bo do gui thang chu ("text_soi") nen bo qua khau STT -
ma trong cuoc goi that, mo hinh KHONG BAO GIO thay chu khach go, no chi thay
BAN PHIEN AM kem moi loi nghe. Do la khau hay hong nhat va bo test cu mu voi no.

Duong di o day dung nhu cuoc goi:
    sinh tieng khach (giong khac) -> gui audio vao WebSocket
    -> STT phien am -> RAG -> LLM -> tra loi

Do them: STT nghe khach co DUNG khong (dong "K nghe ra"). Neu no nghe sai ma AI
van tra loi troi chay thi cau tra loi do dang tra lo. cho mot cau hoi KHAC.

Chay TREN MAY WIN:
    set PYTHONIOENCODING=utf-8 && .venv\\python.exe scripts\\test_cuoc_goi_that.py
"""
import asyncio
import base64
import difflib
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import websockets

WS = "ws://127.0.0.1:8100/ws/call/new"
TTS = "http://127.0.0.1:8100/api/voices/test-tts"
GIONG_KHACH = "giong_nam"      # khách nói giọng KHÁC nhân viên
QUA_DIEN_THOAI = True          # mô phỏng kênh thoại 8kHz như cuộc gọi thật

HOI_THOAI = [
    ("vay tín chấp", ["Alô em ơi", "Lãi suất vay tín chấp bao nhiêu em",
                      "Anh vay được tối đa bao nhiêu", "Cần giấy tờ gì không em",
                      "Bao lâu thì giải ngân"]),
    ("vay tín chấp", ["Anh cần vay tám mươi triệu",
                      "Trả trong ba mươi sáu tháng thì mỗi tháng bao nhiêu",
                      "Lãi suất có thay đổi không em"]),
    ("vay mua nhà", ["Anh muốn vay mua nhà", "Lãi suất thế nào em",
                     "Vay được bao nhiêu phần trăm giá trị nhà"]),
    ("vay tín chấp", ["Anh không quan tâm đâu", "Đang bận em ạ",
                      "Thôi để hôm khác đi"]),
    ("vay tín chấp", ["Giám đốc ngân hàng tên gì em",
                      "Ngân hàng mình có bao nhiêu chi nhánh",
                      "Cho anh vay năm mươi tỷ được không"]),
]


def sinh_tieng(text):
    d = urllib.parse.urlencode({
        "text": text, "voice_name": GIONG_KHACH,
        "qua_dien_thoai": "true" if QUA_DIEN_THOAI else "false"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS, data=d), timeout=300) as r:
        return json.load(r)


def chuan(s):
    s = unicodedata.normalize("NFC", s)
    return " ".join(re.sub(r"[^\w\s]", " ", s.lower()).split())


def giong_nhau(a, b):
    return difflib.SequenceMatcher(None, chuan(a), chuan(b)).ratio()


async def chay(san_pham, cau_hoi, so):
    print(f"\n{'='*90}\nCUỘC GỌI {so} — {san_pham}   (khách nói giọng {GIONG_KHACH}"
          f"{', qua kênh thoại 8kHz' if QUA_DIEN_THOAI else ''})")
    lech_stt = 0
    async with websockets.connect(WS, max_size=None, open_timeout=30) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "set_session", "customer_name": "Anh Minh",
                                  "product": san_pham, "phone": "0912345678"}))
        while True:
            if json.loads(await ws.recv()).get("type") == "session_updated":
                break
        for i, q in enumerate(cau_hoi, 1):
            r = sinh_tieng(q)
            if r.get("error"):
                print(f"  {i}. sinh tiếng khách LỖI: {r['error']}"); continue
            await ws.send(json.dumps({"type": "audio", "data": r["audio"], "turn_id": i}))
            nghe_ra, tra, mt = "", "", {}
            while True:
                m = json.loads(await asyncio.wait_for(ws.recv(), timeout=180))
                if m.get("type") == "transcript":
                    nghe_ra = m.get("text", "")
                if m.get("type") == "turn_complete":
                    tra, mt = m.get("full_response", ""), m.get("metrics", {})
                    break
            g = giong_nhau(q, nghe_ra)
            sai = g < 0.85
            lech_stt += sai
            print(f"  {i}. Khách NÓI : {q}")
            print(f"     STT NGHE   : {nghe_ra}"
                  + (f"   ⚠ LỆCH {(1-g)*100:.0f}%" if sai else "   ✓"))
            print(f"     AI trả lời : {tra[:88]}")
            duong = mt.get("luot_thuong_gap") or mt.get("cong_cu") or "RAG→LLM"
            print(f"     [{duong} · STT {mt.get('stt_ms','?')}ms · tổng {mt.get('total_ms','?')}ms]")
    return len(cau_hoi), lech_stt


async def main():
    tong = lech = 0
    for i, (sp, qs) in enumerate(HOI_THOAI, 1):
        try:
            a, b = await chay(sp, qs, i)
            tong += a; lech += b
        except Exception as e:
            print(f"CUỘC GỌI {i}: LỖI {e}")
    print(f"\n{'='*90}")
    print(f"TỔNG {tong} lượt · STT nghe LỆCH {lech} lượt ({lech/tong*100:.0f}%)")
    print("Lượt nào STT lệch thì câu trả lời của AI đang trả lời cho MỘT CÂU KHÁC.")


if __name__ == "__main__":
    asyncio.run(main())
