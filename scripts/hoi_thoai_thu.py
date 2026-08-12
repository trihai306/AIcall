"""Diễn một cuộc gọi tư vấn hoàn chỉnh rồi ghi lại thành file nghe được.

Khác `goi_thu.py`: bên kia chỉ đo độ trễ 3 lượt rời. Ở đây là MỘT cuộc hội thoại
liên tục có ngữ cảnh - khách hỏi sản phẩm, hỏi hồ sơ riêng, nêu số của mình, rồi
từ chối - để xem AI giữ mạch và dùng đúng nguồn số hay không.

Đi đúng WebSocket + audio_chunk mà micro dùng, đẩy PCM theo thời gian thực, nên
chạm được cả phần đoán trước (`speculate`) - thứ chỉ chạy khi tiếng tới dần và
KHÔNG chạm tới được nếu gõ chữ.

Ghi ra WAV hai kênh:
    trái  = khách      phải = AI
Tách kênh để nghe lại còn biết ai nói gì, và để đo chồng tiếng nếu cần.
"""
import asyncio
import base64
import io
import json
import sys
import time
import wave
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
P = Path(r"C:\duan\chat-ai")
sys.path.insert(0, str(P))

import numpy as np
import websockets

# HAI tần số, đừng gộp:
#   SR_GUI  - bắt buộc 16kHz, đó là thứ micro trình duyệt gửi lên
#   SR_GHI  - 24kHz, đúng tần số TTS sinh ra, để file nghe lại không bị cắt ngọn
# Bản đầu ghi luôn 16kHz cho tiện -> vứt mất nguyên quãng tám trên của giọng,
# nghe ra "nhiễu" trong khi TTS không hề nhiễu.
SR_GUI = 16000
SR_GHI = 24000
SO_KHACH = "0833816298"         # có hồ sơ trong data/nguon/ho_so_khach.db

# Khách giọng NAM, AI giữ giọng nữ mặc định. Bản đầu để cả hai cùng một giọng
# nên nghe như một người tự nói chuyện, không phân biệt được ai đang nói.
# nam_moi1: nhịp gốc 2.48 âm tiết/giây, gần giọng nữ nhất nên chỉ phải
# bù speed 1.08 - kéo giãn càng ít càng đỡ ra tiếng lạ.
GIONG_KHACH = "nam_moi1"

# Kịch bản khách. Trộn đủ bốn loại để soi được từng đường:
#   (a) lượt xã giao  -> phải rơi vào bảng câu sẵn, KHÔNG tốn LLM
#   (b) hỏi sản phẩm  -> tra tài liệu
#   (c) hỏi hồ sơ     -> tra CSDL khách
#   (d) khách nêu số  -> AI không được "sửa" số của khách
CAU_KHACH = [
    "A lô, ai đấy ạ",
    "Ừ em nói đi",
    "Lãi suất vay tín chấp bên em bao nhiêu một năm",
    "Thế vay tối đa được bao nhiêu tiền",
    "Anh còn nợ bao nhiêu tiền vậy em",
    "Khoản vay của anh bao giờ thì đến hạn",
    "Vay tín chấp thì cần những giấy tờ gì",
    "Bao lâu thì được giải ngân",
    "Được rồi, mai anh gọi lại cho em nhé",
]


def _doc_wav(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(wav_bytes)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16), w.getframerate()


def _doi_tan(pcm: np.ndarray, tu: int, den: int) -> np.ndarray:
    """Hạ/nâng tần số CÓ LỌC.

    `np.interp` không lọc thông thấp nên hạ mẫu bị gập phổ: đo được năng lượng
    vùng >6.5kHz tăng từ 1.53% lên 2.06%, nghe ra như rè. `resample_poly` lọc
    sẵn trong lúc đổi tần.
    """
    if tu == den:
        return pcm
    from math import gcd
    g = gcd(tu, den)
    from scipy.signal import resample_poly
    return resample_poly(pcm.astype(np.float64), den // g, tu // g).astype(np.int16)


async def main():
    from backend.services.tts_service import F5TTSService
    tts = F5TTSService()
    tts.load()

    print("Dựng giọng khách…")
    tieng_khach = []
    tong_giay = 0.0
    for c in CAU_KHACH:
        pcm24, sr = _doc_wav(await tts.synthesize(c, use_cache=False,
                                                  voice=GIONG_KHACH))
        pcm24 = _doi_tan(pcm24, sr, SR_GHI)
        tieng_khach.append(pcm24)
        tong_giay += len(pcm24) / SR_GHI
        print(f"  {len(pcm24)/SR_GHI:4.1f}s  {c}")
    print(f"  --> khách nói tổng {tong_giay:.1f}s\n")

    # Hai kênh ghi độc lập rồi ghép cuối: ghi thẳng vào một mảng chung sẽ phải
    # biết trước độ dài, mà độ dài phụ thuộc AI trả lời dài bao nhiêu.
    kenh_khach: list[np.ndarray] = []
    kenh_ai: list[np.ndarray] = []

    def dem(mang: list[np.ndarray]) -> int:
        return sum(len(x) for x in mang)

    def can_bang():
        """Chèn im lặng cho hai kênh dài bằng nhau -> giữ đúng mốc thời gian."""
        a, b = dem(kenh_khach), dem(kenh_ai)
        if a < b:
            kenh_khach.append(np.zeros(b - a, dtype=np.int16))
        elif b < a:
            kenh_ai.append(np.zeros(a - b, dtype=np.int16))

    uri = "ws://127.0.0.1:8100/ws/call/hoithoai01"
    ket_qua = []
    async with websockets.connect(uri, max_size=64 * 1024 * 1024) as ws:
        await ws.recv()
        await ws.send(json.dumps({
            "type": "set_session", "customer_name": "Anh Hải",
            "product": "vay tín chấp", "phone": SO_KHACH}))
        await asyncio.sleep(0.3)

        for i, (cau, pcm) in enumerate(zip(CAU_KHACH, tieng_khach), 1):
            can_bang()
            kenh_khach.append(pcm)
            kenh_ai.append(np.zeros(len(pcm), dtype=np.int16))

            # Đẩy 128ms một mẩu, ngủ đúng 128ms - giống hệt micro thật, và đó là
            # điều kiện để `speculate` có cơ hội chạy.
            pcm16 = _doi_tan(pcm, SR_GHI, SR_GUI)
            MAU = 2048 * 2
            raw = pcm16.tobytes()
            for k in range(0, len(raw), MAU):
                await ws.send(json.dumps({
                    "type": "audio_chunk",
                    "data": base64.b64encode(raw[k:k + MAU]).decode()}))
                await asyncio.sleep(MAU / (SR_GUI * 2))
            t_dut = time.perf_counter()
            await ws.send(json.dumps({"type": "audio_end", "turn_id": i}))

            t_dau, phien_am, tra_loi, mt = None, "", "", {}
            dem_filler = []
            tieng_ai: list[np.ndarray] = []
            while True:
                m = json.loads(await ws.recv())
                t = m.get("type")
                if t == "audio":
                    if t_dau is None:
                        t_dau = (time.perf_counter() - t_dut) * 1000
                    _a, _sr = _doc_wav(base64.b64decode(m["data"]))
                    tieng_ai.append(_doi_tan(_a, _sr, SR_GHI))
                elif t == "filler":
                    dem_filler.append(m.get("text") or m.get("phrase") or "?")
                elif t == "transcript":
                    phien_am = m.get("text", "")
                elif t == "turn_complete":
                    tra_loi = m.get("full_response", "")
                    mt = m.get("metrics", {})
                    break

            can_bang()
            if tieng_ai:
                noi = np.concatenate(tieng_ai)
                kenh_ai.append(noi)
                kenh_khach.append(np.zeros(len(noi), dtype=np.int16))

            ket_qua.append({
                "hoi": cau, "nghe": phien_am, "dap": tra_loi,
                "tieng_dau_ms": round(t_dau) if t_dau else None,
                "ttfa": mt.get("ttfa_ms"), "stt": mt.get("stt_ms"),
                "tong": mt.get("total_ms"),
                "cong_cu": mt.get("cong_cu"), "cong_cu_ms": mt.get("cong_cu_ms"),
                "nghi_san": bool(mt.get("llm_nghi_san")),
                "san_co": mt.get("luot_thuong_gap"),
                "tinh_huong_id": mt.get("tinh_huong_id"),
                "tinh_huong_cho_ms": mt.get("tinh_huong_cho_ms"),
                "tinh_huong_diem": mt.get("tinh_huong_diem"),
            })
            print(f"--- Lượt {i} ---")
            print(f"  khách nói  : {cau}")
            print(f"  nghe thành : {phien_am}")
            print(f"  câu đệm    : {mt.get('filler_text') or (dem_filler[0] if dem_filler else '(không có)')}")
            print(f"  AI đáp     : {tra_loi}")
            t_dau_str = f"{t_dau:.0f}ms" if t_dau is not None else "N/A"
            th_str = ""
            if mt.get("tinh_huong_id"):
                th_str = f" · TH={mt.get('tinh_huong_id')}({mt.get('tinh_huong_diem',0):.2f})"
                if mt.get("tinh_huong_cho_ms") is not None:
                    th_str += f" cho={mt.get('tinh_huong_cho_ms')}ms"
            print(f"  tiếng đầu {t_dau_str} · TTFA {mt.get('ttfa_ms')}ms · "
                  f"STT {mt.get('stt_ms')}ms · công cụ {mt.get('cong_cu') or '-'} "
                  f"({mt.get('cong_cu_ms', '-')}ms)"
                  f"{' · NGHĨ SẴN' if mt.get('llm_nghi_san') else ''}"
                  f"{' · câu sẵn' if mt.get('luot_thuong_gap') else ''}"
                  f"{th_str}\n")
            # Khoảng lặng giữa hai lượt cho giống người thật ngắt nhịp.
            await asyncio.sleep(0.6)
            im = np.zeros(int(0.6 * SR_GHI), dtype=np.int16)
            kenh_khach.append(im)
            kenh_ai.append(im.copy())

    can_bang()
    trai = np.concatenate(kenh_khach)
    phai = np.concatenate(kenh_ai)
    stereo = np.empty(len(trai) * 2, dtype=np.int16)
    stereo[0::2] = trai
    stereo[1::2] = phai
    ra = P / "logs" / "hoi_thoai_thu.wav"
    with wave.open(str(ra), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR_GHI)
        w.writeframes(stereo.tobytes())

    print(f"=== Đã ghi: {ra}  ({len(trai)/SR_GHI:.1f}s, trái=khách, phải=AI) ===")
    print(json.dumps(ket_qua, ensure_ascii=False))


asyncio.run(main())
