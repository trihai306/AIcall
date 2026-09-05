"""Chay lai 7 luot bang giong that VA THU LAI TIENG AI tra loi.

Backend gui tieng qua WS dang {"type":"audio","data":<base64 wav>}. Thu tat ca
manh cua moi luot, noi PCM lai thanh 1 file wav / luot.
"""
import asyncio, time, base64, io, json, time, wave
from pathlib import Path
import websockets

# Moi lan chay phai la PHIEN MOI, khong thi lich su luot cu con do va
# ket qua khong so sanh duoc voi lan truoc.
PHIEN = f"{int(time.time())}"

DU_AN = Path(__file__).resolve().parents[1]

URL = f"ws://127.0.0.1:8100/ws/call/thu_tieng_ai_{PHIEN}"
VAO = Path(DU_AN / "data" / "luot_that")
RA  = Path(DU_AN / "data" / "tieng_ai")
RA.mkdir(parents=True, exist_ok=True)

def noi_pcm(manh: list[bytes]) -> tuple[bytes, int]:
    """Moi manh la 1 file WAV doc lap -> boc PCM ra roi noi."""
    pcm, sr = b"", 24000
    for w in manh:
        try:
            with wave.open(io.BytesIO(w)) as f:
                sr = f.getframerate()
                pcm += f.readframes(f.getnframes())
        except Exception:
            pass          # manh hong thi bo, khong lam chet ca luot
    return pcm, sr

async def mot_luot(ws, pcm_khach: bytes):
    await ws.send(json.dumps({"type": "audio",
                              "data": base64.b64encode(pcm_khach).decode()}))
    phien_am, tra_loi, manh = "", "", []
    while True:
        try:
            tin = json.loads(await asyncio.wait_for(ws.recv(), timeout=90))
        except asyncio.TimeoutError:
            return phien_am, "(qua han)", manh
        t = tin.get("type", "")
        if t == "transcript":
            phien_am = tin.get("text", "")
        elif t == "audio":
            manh.append(base64.b64decode(tin.get("data", "")))
        elif t == "turn_complete":
            return phien_am, tin.get("full_response", ""), manh

async def main():
    dong = []
    async with websockets.connect(URL, max_size=None) as ws:
        await ws.recv()
        for i in range(1, 8):
            pa, tl, manh = await mot_luot(ws, (VAO / f"luot_{i}.raw").read_bytes())
            pcm, sr = noi_pcm(manh)
            f = RA / f"ai_luot_{i}.wav"
            with wave.open(str(f), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
                w.writeframes(pcm)
            giay = len(pcm) / 2 / sr if sr else 0
            dong.append(f"luot {i}: {len(manh)} manh, {giay:.2f}s @ {sr}Hz\n"
                        f"   nghe : {pa!r}\n   dap  : {tl.strip()!r}")
            print(f"luot {i}: {len(manh)} manh {giay:.1f}s")
    (Path(DU_AN / "data") / "ket_tieng_ai.txt").write_text(
        "\n".join(dong), encoding="utf-8")
    print("xong")

asyncio.run(main())
