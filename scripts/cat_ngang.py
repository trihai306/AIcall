"""Khách nói tiếp khi AI còn đang trả lời - kiểm tra tiếng lượt cũ có lọt sang không.

Đây là lỗi đã báo: "khách nhắn tin tiếp thì vẫn đọc hội thoại trước".
Đo trước khi sửa: 3 mảnh (~8 giây tiếng) của lượt cũ vẫn tới nơi sau khi khách
đã sang lượt mới.
"""
import asyncio, base64, io, json, sys, time, wave
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
P = Path(r"C:\duan\chat-ai"); sys.path.insert(0, str(P))

import numpy as np
import websockets

def wav_16k(b: bytes) -> bytes:
    with wave.open(io.BytesIO(b)) as w:
        sr = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    n = int(len(pcm) / sr * 16000)
    return np.interp(np.linspace(0, len(pcm)-1, n), np.arange(len(pcm)), pcm).astype(np.int16).tobytes()

async def day_tieng(ws, pcm, turn_id, thoi_gian_that=True):
    """thoi_gian_that=False: đẩy hết ngay. Dùng cho lượt cắt ngang - mô phỏng
    khách đã nói đè lên AI nên tiếng của họ đã nằm sẵn ở server."""
    MAU = 2048 * 2
    for k in range(0, len(pcm), MAU):
        await ws.send(json.dumps({"type": "audio_chunk",
                                  "data": base64.b64encode(pcm[k:k+MAU]).decode()}))
        if thoi_gian_that:
            await asyncio.sleep(MAU / 32000)
    await ws.send(json.dumps({"type": "audio_end", "turn_id": turn_id}))

async def main():
    from backend.services.tts_service import F5TTSService
    tts = F5TTSService(); tts.load()
    c1 = wav_16k(await tts.synthesize("Vay tín chấp cần giấy tờ gì ạ", use_cache=False))
    c2 = wav_16k(await tts.synthesize("Thôi lãi suất", use_cache=False))   # ngắn, để audio_end kịp rơi vào lúc lượt 1 còn đang sinh tiếng

    # 127.0.0.1 chứ KHÔNG phải "localhost": trên Windows tên đó phân giải
    # ra IPv6 ::1 trước, mà uvicorn nghe 0.0.0.0 (chỉ IPv4) -> ConnectionRefused.
    async with websockets.connect("ws://127.0.0.1:8100/ws/call/catngang1",
                                  max_size=64*1024*1024) as ws:
        await ws.recv()
        t0 = time.perf_counter()
        ghi = []

        async def nghe():
            while True:
                m = json.loads(await ws.recv())
                if m.get("type") == "audio":
                    ghi.append((round((time.perf_counter()-t0)*1000),
                                m.get("turn_id"), len(m.get("data",""))))
                elif m.get("type") == "turn_complete":
                    ghi.append((round((time.perf_counter()-t0)*1000), "xong", 0))

        task = asyncio.create_task(nghe())
        print("Lượt 1: khách hỏi giấy tờ")
        await day_tieng(ws, c1, 1)
        print("  ... để AI trả lời 0.3 giây rồi CẮT NGANG")
        await asyncio.sleep(0.3)
        print("Lượt 2: khách đổi ý, hỏi lãi suất")
        await day_tieng(ws, c2, 2, thoi_gian_that=False)
        await asyncio.sleep(9)
        task.cancel()

    print(f"\n{'thời điểm':>10}  {'lượt':>6}  {'cỡ mảnh':>8}")
    lot = 0
    for t, tid, n in ghi:
        if tid == "xong":
            print(f"{t:>8}ms  {'--- turn_complete ---':>28}")
            continue
        canh = ""
        if tid == 1 and any(x[1] == 2 for x in ghi[:ghi.index((t,tid,n))+1]):
            canh = "  <-- LỌT: mảnh lượt 1 sau khi đã sang lượt 2"; lot += 1
        print(f"{t:>8}ms  {tid:>6}  {n:>8}{canh}")
    print(f"\n=> {lot} mảnh của lượt cũ lọt sang lượt mới")

asyncio.run(main())
