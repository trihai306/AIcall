"""Gọi thử đường THOẠI y như khách gọi điện: đẩy PCM 16kHz theo thời gian thực.

Không gọi HTTP mà đi đúng WebSocket + audio_chunk/audio_end mà micro dùng, để
đo được cả phần đoán trước (speculate) - thứ chỉ chạy khi audio tới dần.

Giọng "khách" sinh bằng chính TTS của hệ thống rồi hạ về 16kHz. Không phải giọng
người thật nên STT dễ nghe hơn đôi chút, nhưng đường đi thì giống hệt.
"""
import asyncio, base64, json, sys, time, wave, io
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
P = Path(r"C:\duan\chat-ai"); sys.path.insert(0, str(P))

import numpy as np
import websockets

CAU_KHACH = [
    "Anh còn nợ bao nhiêu tiền vậy em",
    "Khoản vay của anh bao giờ đến hạn",
    "Lãi suất vay tín chấp bao nhiêu một năm",
]

def wav_16k(wav_bytes: bytes) -> bytes:
    """WAV 24kHz của TTS -> PCM thô 16kHz mono, đúng thứ micro gửi lên."""
    with wave.open(io.BytesIO(wav_bytes)) as w:
        sr = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    n = int(len(pcm) / sr * 16000)
    return np.interp(np.linspace(0, len(pcm) - 1, n),
                     np.arange(len(pcm)), pcm).astype(np.int16).tobytes()

async def main():
    from backend.services.tts_service import F5TTSService
    tts = F5TTSService(); tts.load()

    print("Sinh giọng khách ...")
    tieng = []
    for c in CAU_KHACH:
        tieng.append(wav_16k(await tts.synthesize(c, use_cache=False)))
        print(f"  {len(tieng[-1])/32000:.1f}s  {c}")

    # 127.0.0.1 chứ KHÔNG phải "localhost": trên Windows tên đó phân giải
    # ra IPv6 ::1 trước, mà uvicorn nghe 0.0.0.0 (chỉ IPv4) -> ConnectionRefused.
    uri = "ws://127.0.0.1:8100/ws/call/goithu01"
    async with websockets.connect(uri, max_size=64 * 1024 * 1024) as ws:
        print(f"\n{json.loads(await ws.recv())['type']}\n")
        await ws.send(json.dumps({"type": "set_session", "customer_name": "Anh Hải",
                                  "product": "vay tín chấp", "phone": "0833816298"}))
        await asyncio.sleep(0.3)

        for i, (cau, pcm) in enumerate(zip(CAU_KHACH, tieng), 1):
            print(f"--- Lượt {i}: khách nói \"{cau}\" ---")
            # Đẩy 128ms một mẩu, ngủ đúng 128ms -> giống hệt micro thật.
            MAU = 2048 * 2
            t_bat_dau = time.perf_counter()
            for k in range(0, len(pcm), MAU):
                await ws.send(json.dumps({"type": "audio_chunk",
                                          "data": base64.b64encode(pcm[k:k+MAU]).decode()}))
                await asyncio.sleep(MAU / 32000)
            t_dut_loi = time.perf_counter()
            await ws.send(json.dumps({"type": "audio_end", "turn_id": i}))

            n_manh, t_tieng_dau, tra_loi, phien_am = 0, None, "", ""
            while True:
                m = json.loads(await ws.recv())
                t = m.get("type")
                if t == "audio":
                    n_manh += 1
                    if t_tieng_dau is None:
                        t_tieng_dau = (time.perf_counter() - t_dut_loi) * 1000
                    if m.get("turn_id") != i:
                        print(f"  [!] mảnh của lượt {m.get('turn_id')} lọt vào lượt {i}")
                elif t == "transcript":
                    phien_am = m.get("text", "")
                elif t == "turn_complete":
                    tra_loi = m.get("full_response", "")
                    mt = m.get("metrics", {})
                    break
            print(f"  nghe thành : {phien_am}")
            print(f"  trả lời    : {tra_loi}")
            print(f"  tiếng đầu  : {t_tieng_dau:.0f} ms sau khi khách dứt lời"
                  f"  | {n_manh} mảnh audio")
            print(f"  bóc tách   : STT {mt.get('stt_ms','-')}ms · RAG {mt.get('rag_ms','-')}ms"
                  f" · TTFA {mt.get('ttfa_ms','-')}ms · tổng {mt.get('total_ms','-')}ms"
                  f"{'  (RAG đoán trước)' if mt.get('rag_doan_truoc') else ''}")
            print(f"  nghĩ sẵn   : {'CÓ DÙNG' if mt.get('llm_nghi_san') else 'không'}"
                  f"  | công cụ: {mt.get('cong_cu','-')}"
                  f" ({mt.get('cong_cu_ms','-')}ms"
                  f"{', lưới từ khoá' if mt.get('cong_cu_nhanh') else ''})\n")
            await asyncio.sleep(0.5)

asyncio.run(main())
