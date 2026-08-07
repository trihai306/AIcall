"""Đo TTFA THẬT qua WebSocket của dịch vụ, sau khi đổi ngưỡng cắt mảnh đầu.

Không suy ra từ đường cong: nối thẳng vào `/ws/call/{id}`, gửi câu khách bằng
đường text rồi bấm giờ tới lúc mảnh audio ĐẦU TIÊN về. Đó đúng là thứ khách chờ.

Bỏ lượt đầu (GPU chưa lên xung, và lần đầu còn nạp cache) rồi mới tính.

    python scripts/do_ttfa_that.py [số_lượt]
"""
import asyncio, json, statistics, sys, time, uuid

import websockets

WS = "ws://localhost:8100/ws/call/"

CAU_KHACH = [
    "Lãi suất vay tín chấp bên mình bao nhiêu vậy em?",
    "Anh muốn vay năm trăm triệu thì trả góp mấy tháng?",
    "Cần giấy tờ gì để làm hồ sơ vậy em?",
    "Khoản vay này có cần thế chấp không?",
    "Bao lâu thì tiền về tài khoản của anh?",
]


async def mot_luot(cau: str) -> dict:
    sid = str(uuid.uuid4())
    async with websockets.connect(WS + sid, max_size=None) as ws:
        await ws.recv()                                  # bản tin "connected"
        t0 = time.perf_counter()
        await ws.send(json.dumps({"type": "text", "text": cau}))

        ttfa = None
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=60)
            m = json.loads(raw) if isinstance(raw, str) else None
            if m is None:
                continue
            k = m.get("type", "")
            if k == "audio" and ttfa is None:
                ttfa = (time.perf_counter() - t0) * 1000
            if k == "turn_complete":
                return {
                    "ttfa_do_duoc": ttfa,
                    "metrics": m.get("metrics", {}),
                }


async def main():
    luot = int(sys.argv[1]) if len(sys.argv) > 1 else 3

    print("lượt khởi động (bỏ đi) ...")
    await mot_luot(CAU_KHACH[0])

    ttfa, tts1, chu1 = [], [], []
    for i in range(luot):
        for cau in CAU_KHACH:
            r = await mot_luot(cau)
            m = r["metrics"]
            t = m.get("ttfa_ms") or r["ttfa_do_duoc"]
            if t:
                ttfa.append(t)
                if m.get("tts_first_ms"):
                    tts1.append(m["tts_first_ms"])
                if m.get("tts_first_chars"):
                    chu1.append(m["tts_first_chars"])
        print(f"  xong lượt {i + 1}/{luot}")

    if not ttfa:
        print("không lấy được TTFA nào"); return
    ttfa.sort()
    print(f"\nTTFA trên {len(ttfa)} lượt:")
    print(f"  trung vị {statistics.median(ttfa):.0f} ms")
    print(f"  nhỏ nhất {min(ttfa):.0f} ms | lớn nhất {max(ttfa):.0f} ms")
    print(f"  vượt trần 1000ms: {sum(1 for t in ttfa if t > 1000)}/{len(ttfa)} lượt")
    if tts1:
        print(f"\n  TTS mảnh đầu: trung vị {statistics.median(tts1):.0f} ms")
    if chu1:
        print(f"  mảnh đầu dài : trung vị {statistics.median(chu1):.0f} ký tự"
              f" | lớn nhất {max(chu1)}")


if __name__ == "__main__":
    asyncio.run(main())
