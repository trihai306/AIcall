"""Khách nói đè lên AI: AI phải im ngay, và câu nói dở phải được ghép với câu sau.

Kịch bản y như gọi điện thật:
  1. Khách nói "Cho em hỏi"          -> ngắn, AI hiểu sai là đã hỏi xong
  2. AI bắt đầu trả lời
  3. Khách nói đè lên "lãi suất vay tín chấp bao nhiêu"
  4. AI phải: dừng tiếng ngay, bỏ câu trả lời dở, ghép hai vế thành
     "Cho em hỏi lãi suất vay tín chấp bao nhiêu" rồi trả lời một lần cho đúng.

So sánh được: không có bước ghép thì AI chỉ nghe "lãi suất vay tín chấp bao nhiêu"
- lần này vẫn ra đúng, nhưng vế "Cho em hỏi" mất thì những câu như
"Cho em hỏi" + "cái vừa nói ấy" sẽ trật hoàn toàn.

    python scripts/cat_loi_ghep_cau.py
"""

import asyncio
import base64
import io
import json
import sys
import time
import wave
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

def wav_16k(b: bytes) -> bytes:
    """WAV 24kHz của TTS -> PCM thô 16kHz mono, đúng thứ micro gửi lên."""
    import numpy as np

    with wave.open(io.BytesIO(b)) as w:
        sr = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    n = int(len(pcm) / sr * 16000)
    return np.interp(np.linspace(0, len(pcm) - 1, n),
                     np.arange(len(pcm)), pcm).astype(np.int16).tobytes()

async def day_tieng(ws, pcm, turn_id=None, thoi_gian_that=True):
    MAU = 2048 * 2      # ~128ms ở 16kHz, bằng đúng cỡ khung của ScriptProcessor
    for k in range(0, len(pcm), MAU):
        await ws.send(json.dumps({"type": "audio_chunk",
                                  "data": base64.b64encode(pcm[k:k + MAU]).decode()}))
        if thoi_gian_that:
            await asyncio.sleep(MAU / 32000)
    if turn_id is not None:
        await ws.send(json.dumps({"type": "audio_end", "turn_id": turn_id}))

async def main() -> int:
    import websockets

    from backend.services.tts_service import F5TTSService

    tts = F5TTSService()
    tts.load()

    VE1 = "Cho em hỏi"
    VE2 = "lãi suất vay tín chấp bao nhiêu"
    print(f"Sinh giọng khách: {VE1!r} / {VE2!r}")
    a1 = wav_16k(await tts.synthesize(VE1, use_cache=False))
    a2 = wav_16k(await tts.synthesize(VE2, use_cache=False))

    # 127.0.0.1 chứ KHÔNG phải "localhost": trên Windows tên đó phân giải
    # ra IPv6 ::1 trước, mà uvicorn nghe 0.0.0.0 (chỉ IPv4) -> ConnectionRefused.
    async with websockets.connect("ws://127.0.0.1:8100/ws/call/catloi01",
                                  max_size=64 * 1024 * 1024) as ws:
        await ws.recv()
        t0 = time.perf_counter()
        su_kien = []

        async def nghe():
            while True:
                m = json.loads(await ws.recv())
                su_kien.append((round((time.perf_counter() - t0) * 1000), m))

        task = asyncio.create_task(nghe())

        print(f"\n[1] Khách nói: {VE1!r}")
        await day_tieng(ws, a1, turn_id=1)

        print("[2] Chờ AI bắt đầu nói ...")
        for _ in range(60):
            if any(m.get("type") == "audio" for _, m in su_kien):
                break
            await asyncio.sleep(0.1)
        t_ai_noi = next((t for t, m in su_kien if m.get("type") == "audio"), None)
        print(f"    AI phát mảnh đầu ở {t_ai_noi} ms")

        await asyncio.sleep(0.3)
        print("[3] Khách NÓI ĐÈ LÊN -> gửi barge_in")
        t_cat = round((time.perf_counter() - t0) * 1000)
        await ws.send(json.dumps({"type": "barge_in"}))

        print(f"[4] Khách nói tiếp: {VE2!r}")
        await day_tieng(ws, a2, turn_id=2, thoi_gian_that=False)

        await asyncio.sleep(12)
        task.cancel()

    # --- chấm điểm ---------------------------------------------------------
    manh_sau_cat = [t for t, m in su_kien
                    if m.get("type") == "audio" and t > t_cat and m.get("turn_id") == 1]
    phien_am = [m.get("text") for _, m in su_kien if m.get("type") == "transcript"]
    xong = [m for _, m in su_kien if m.get("type") == "turn_complete"]
    bi_cat = [m for m in xong if m.get("metrics", {}).get("bi_cat_loi")]
    that = [m for m in xong if not m.get("metrics", {}).get("bi_cat_loi")]

    print("\n" + "=" * 66)
    dat = True

    def kiem(mo_ta, dieu_kien, them=""):
        nonlocal dat
        dat &= bool(dieu_kien)
        print(("  ĐẠT  " if dieu_kien else "  TRẬT ") + mo_ta + (f"  {them}" if them else ""))

    kiem("AI im ngay khi bị cắt", not manh_sau_cat,
         f"({len(manh_sau_cat)} mảnh lọt sau khi cắt)")
    kiem("server báo lượt bị cắt lời", bi_cat)
    # So chữ thường và bỏ dấu câu: PhoWhisper luôn trả về chữ thường và tự thêm
    # dấu chấm cuối câu, so nguyên văn thì trật dù nội dung ghép đúng.
    def gon(s: str) -> str:
        return " ".join("".join(c for c in s.lower() if c.isalnum() or c.isspace()).split())

    mong = f"{VE1} {VE2}"
    thay = phien_am[-1] if phien_am else ""
    kiem("ghép hai vế thành một ý", gon(thay) == gon(mong),
         f"\n         mong đợi: {mong!r}\n         nhận được: {thay!r}")
    kiem("chỉ trả lời MỘT lần cho ý đã ghép", len(that) == 1,
         f"({len(that)} câu trả lời thật)")
    if that:
        print(f"\n  AI trả lời: {that[-1].get('full_response', '')}")
        mt = that[-1].get("metrics", {})
        if mt.get("ghep_cau_bi_cat"):
            print(f"  (đã ghép từ vế bị cắt: {mt['ghep_cau_bi_cat']!r})")

    print("=" * 66)
    print("=> " + ("TẤT CẢ ĐẠT" if dat else "CÓ MỤC TRẬT"))
    return 0 if dat else 1

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
