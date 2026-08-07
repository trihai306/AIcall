"""Bộ lọc bịa chữ có phân biệt được nhiễu với giọng thật không?

Whisper sinh ra câu tiếng Việt trôi chảy từ tạp âm. Trên đường thoại EDGE điều
này xảy ra liên tục - một cuộc gọi thật cho ra "điều này đã khiến nhiều người mơ
ước được hiểu rõ" lặp y hệt qua bốn lượt, AI trả lời rỗng.

Phép thử: đưa vào NHIỄU (đáng lẽ bị bỏ) và GIỌNG THẬT (đáng lẽ giữ), xem bộ lọc
có tách đúng không. Giọng thật lấy từ chính giọng mẫu TTS đã lưu.

    python scripts/kiem_loc_stt.py
"""

import asyncio
import io
import sys
import wave
from pathlib import Path

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))


def wav_16k(x: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


async def main() -> int:
    from backend.services import phone_call_service as pcs
    from backend.services.audio_utils import resample_audio
    from backend.services.stt_service import STTService

    stt = STTService()
    if not await stt.health_check():
        print("Máy chủ STT chưa chạy")
        return 1

    r = np.random.default_rng(7)
    mau: list[tuple[str, bytes, bool]] = []

    # Nhiễu ở vài mức, mô phỏng nền kênh thoại. Cả bốn đáng lẽ bị bỏ.
    for db in (-45, -35, -28, -22):
        n = r.standard_normal(int(2.5 * 16000)).astype(np.float32)
        n = n / (np.abs(n).max() or 1.0) * (10 ** (db / 20))
        mau.append((f"nhiễu {db} dBFS", wav_16k(n), False))

    # Giọng thật - đáng lẽ GIỮ.
    kho = PROJECT / "data" / "mau_so_sanh.wav"
    if kho.exists():
        x, sr = pcs._wav_to_pcm(kho.read_bytes())
        mau.append(("giọng TTS sạch", wav_16k(resample_audio(x, sr, 16000)), True))
        # Giọng thật + nhiễu, giống điều kiện đường thoại thật.
        y = resample_audio(x, sr, 16000)
        n = r.standard_normal(y.size).astype(np.float32)
        n = n / (np.abs(n).max() or 1.0) * (10 ** (-30 / 20))
        mau.append(("giọng + nhiễu -30dB", wav_16k(y + n), True))
    else:
        print("(chưa có data/mau_so_sanh.wav nên bỏ phần giọng thật)")

    # In SỐ THẬT trước, rồi mới chấm. Ngưỡng đặt bằng cách đoán thì bộ lọc
    # không bắt được gì - lần đầu cả 4 mẫu nhiễu đều lọt qua.
    import httpx
    print(f"\n    {'đầu vào':<24}{'no_speech':>10}{'logprob':>10}"
          f"{'mong đợi':>10}{'kết quả':>9}   văn bản")
    dung = 0
    async with httpx.AsyncClient(timeout=60) as cli:
        for ten, wav, nen_giu in mau:
            r = await cli.post(f"{stt.base_url}/inference",
                               files={"file": ("a.wav", wav, "audio/wav")},
                               data={"language": "vi",
                                     "response_format": "verbose_json",
                                     "temperature": "0"})
            j = r.json()
            doan = j.get("segments") or []
            ns = max((d.get("no_speech_prob", 0.0) for d in doan), default=float("nan"))
            lp = min((d.get("avg_logprob", 0.0) for d in doan), default=float("nan"))
            text = await stt.transcribe(wav, sample_rate=16000)
            giu = bool(text)
            ok = giu == nen_giu
            dung += ok
            print(f"    {ten:<24}{ns:>10.3f}{lp:>10.3f}"
                  f"{'GIỮ' if nen_giu else 'BỎ':>10}{'giữ' if giu else 'bỏ':>9}"
                  f"   {'đúng' if ok else 'SAI'} {(j.get('text') or '')[:34]}")

    print(f"\n    {dung}/{len(mau)} đúng")
    await stt.close()
    return 0 if dung == len(mau) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
