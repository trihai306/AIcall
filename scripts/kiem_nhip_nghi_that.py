"""Kiểm nhịp nghỉ có THẬT SỰ được chèn trên đường chạy thật hay không.

Nối vào WebSocket của dịch vụ, gửi một câu hỏi, hứng từng mảnh audio rồi đo
khoảng lặng ở ĐẦU mỗi mảnh. Mảnh sau một mảnh kết thúc bằng dấu phẩy phải có
~305ms lặng dẫn vào, sau dấu chấm ~360ms; mảnh đầu tiên phải KHÔNG có gì.

    python scripts/kiem_nhip_nghi_that.py
"""
import asyncio, base64, io, json, sys, uuid, wave
import numpy as np
import websockets

WS = "ws://localhost:8100/ws/call/"
CAU = "Lãi suất vay tín chấp bên mình bao nhiêu, và cần giấy tờ gì vậy em?"


def lang_dau_ms(wav_bytes: bytes) -> float:
    with wave.open(io.BytesIO(wav_bytes)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    nz = np.nonzero(np.abs(x) > 0.005)[0]
    return (float(nz[0]) / sr * 1000) if len(nz) else len(x) / sr * 1000


async def main():
    sid = str(uuid.uuid4())
    manh = []
    async with websockets.connect(WS + sid, max_size=None) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "text", "text": CAU}))
        while True:
            m = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
            k = m.get("type", "")
            if k == "audio":
                # Bỏ filler: nó được gửi trước lượt thật để lấp im lặng, không
                # nằm trong chuỗi mảnh nên tính vào là lệch hết chỉ số.
                if m.get("is_filler"):
                    continue
                d = m.get("data") or m.get("audio") or ""
                if d:
                    manh.append(base64.b64decode(d))
            elif k == "response_chunk":
                manh.append(("text", m.get("text", "")))
            elif k == "turn_complete":
                break

    chu = [x[1] for x in manh if isinstance(x, tuple)]
    am = [x for x in manh if isinstance(x, bytes)]
    print(f"nhận {len(am)} mảnh audio, {len(chu)} mảnh chữ\n")
    if not am:
        print("KHÔNG có mảnh audio nào - kiểm lại tên trường base64 trong bản tin")
        return

    from backend.pipeline.text_chunker import nhip_nghi_sau
    for i, b in enumerate(am):
        thuc = lang_dau_ms(b)
        mong = nhip_nghi_sau(chu[i - 1]) if 0 < i < len(chu) + 1 and i - 1 < len(chu) else 0.0
        dat = abs(thuc - mong) < 60 or (mong == 0 and thuc < 60)
        print(f"  mảnh {i}: lặng đầu {thuc:6.0f} ms | mong đợi {mong:5.0f} ms "
              f"{'OK' if dat else '<-- LỆCH'}   {chu[i][:40] if i < len(chu) else ''}")


if __name__ == "__main__":
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    asyncio.run(main())
