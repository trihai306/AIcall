"""Do TUNG CHANG cua mot luot, khong doan cho nao cham.

Duong ong da tu ghi 8 moc: stt_ms, rag_ms, cong_cu_ms, llm_ttft_ms,
llm_chunk1_ms, tts_first_ms, ttfa_ms, total_ms. Script nay chi don ve mot bang.

TTFA la thu khach cam nhan: tu luc ho dut loi den luc nghe thay tieng dau tien.
"""
import asyncio, base64, io, json, sys, time
from pathlib import Path
sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf, websockets
from backend.services.tts_service import F5TTSService

WS = "ws://127.0.0.1:8100/ws/call/do-moc"
LUOT = [
 "Alo em chào anh, anh đang cần vay tín chấp thì lãi suất bao nhiêu vậy em?",
 "Vậy hạn mức tối đa là bao nhiêu, và anh cần chuẩn bị giấy tờ gì?",
 "Anh làm công ty được ba năm rồi, lương chuyển khoản mười lăm triệu một tháng.",
 "Thế thời gian giải ngân mất mấy ngày em nhỉ?",
 "Nếu anh muốn trả trước hạn thì có bị phạt gì không em?",
]
COT = ["stt_ms", "rag_ms", "cong_cu_ms", "llm_ttft_ms", "llm_chunk1_ms",
       "tts_first_ms", "ttfa_ms", "total_ms"]

def wav_bytes(x, sr):
    b = io.BytesIO(); sf.write(b, np.clip(x, -1, 1), sr, format="WAV", subtype="PCM_16")
    return b.getvalue()

async def main():
    svc = F5TTSService(); svc.load()
    await svc.ensure_voice("giong_nam")
    tieng = []
    for c in LUOT:
        b = await svc.synthesize(c, voice="giong_nam")
        x, sr = sf.read(io.BytesIO(b), dtype="float32")
        tieng.append((x.mean(axis=1) if x.ndim > 1 else x, sr))
    ra = []
    async with websockets.connect(WS, max_size=64*1024*1024) as ws:
        await ws.send(json.dumps({"type": "set_session", "customer_name": "anh Hải",
                                  "product": "vay tín chấp", "phone": "0912345678"}))
        try: await asyncio.wait_for(ws.recv(), timeout=20)
        except asyncio.TimeoutError: pass
        for i, (x, sr) in enumerate(tieng, 1):
            await ws.send(json.dumps({"type": "audio", "turn_id": i,
                                      "data": base64.b64encode(wav_bytes(x, sr)).decode()}))
            while True:
                g = json.loads(await asyncio.wait_for(ws.recv(), timeout=180))
                if g.get("type") == "turn_complete":
                    ra.append(g.get("metrics", {})); break
            await asyncio.sleep(1.0)
    print(f"\n  {'luot':>4} " + " ".join(f"{c.replace('_ms',''):>9}" for c in COT))
    print("  " + "-"*88)
    for i, m in enumerate(ra, 1):
        print(f"  {i:>4} " + " ".join(f"{m.get(c, '-'):>9}" for c in COT))
    print("  " + "-"*88)
    for c in COT:
        v = [m[c] for m in ra if isinstance(m.get(c), (int, float))]
        if v: print(f"  {c:<16} trung vi {sorted(v)[len(v)//2]:>6.0f}ms   to nhat {max(v):>6.0f}ms")
    print(f"\n  cac khoa khac o luot 1:")
    for k, v in ra[0].items():
        if k not in COT:
            print(f"    {k}: {str(v)[:70]}")
asyncio.run(main())
