"""Dựng đoạn mẫu 3s tốt nhất, rồi đo tốc độ khi cộng cả compile.

Chọn đoạn theo HAI tiêu chí, không chỉ một:
  1. biên sạch  - hai đầu đủ im để không cắt cụt chữ
  2. STT tự tin - `avg_logprob` cao, nghĩa là lời phiên âm đáng tin
Tiêu chí 2 quan trọng ngang tiêu chí 1: F5 học từ CẶP (tiếng, lời), lời sai chỗ
nào thì mô hình lệch chỗ đó ở mọi câu nó đọc sau này.
"""
import asyncio
import io
import sys
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, "C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")

F = Path(r"C:\Users\Admin\Desktop\giọng Hêu.wav")
RA = Path("C:/duan/chat-ai/models/tts/ref_voices")
LOG = Path("C:/duan/chat-ai/logs/giong_moi")
DAI = 3.2


async def main():
    import httpx
    from backend.config import settings
    from backend.services.audio_utils import pcm_to_wav, resample_audio
    from backend.services.stt_service import STTService, _don_token
    from backend.services.tts_service import F5TTSService

    with wave.open(str(F), "rb") as w:
        sr, nch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        khoi = []
        for p in range(0, n, sr * 30):
            w.setpos(p)
            b = w.readframes(min(sr * 30, n - p))
            a = np.frombuffer(b, dtype=np.int16).astype(np.float32)
            if nch > 1:
                a = a.reshape(-1, nch).mean(axis=1)
            khoi.append(a / 32768.0)
    x = resample_audio(np.concatenate(khoi), sr, 24000)
    SR = 24000
    print(f"  đọc xong {len(x)/SR/60:.1f} phút")

    N = int(0.02 * SR)
    rms = np.array([np.sqrt((x[i:i + N] ** 2).mean()) for i in range(0, len(x) - N, N)])
    san = float(np.percentile(rms, 25))
    kh = int(DAI / 0.02)
    bien = int(0.25 / 0.02)

    # lấy 12 ứng viên tốt nhất theo biên sạch, rồi mới chấm bằng STT
    ung = []
    for i in range(0, len(rms) - kh, 40):
        w_ = rms[i:i + kh]
        dau, cuoi, giua = w_[:bien], w_[-bien:], w_[bien:-bien]
        if giua.mean() < san * 3:
            continue
        d = giua.mean() / (dau.mean() + cuoi.mean() + 1e-9) - 2.0 * giua.std() / (giua.mean() + 1e-9)
        ung.append((d, i))
    ung.sort(reverse=True)
    print(f"  {len(ung)} ứng viên, chấm 12 cái đầu bằng STT\n")

    tot = None
    async with httpx.AsyncClient(timeout=30.0) as c:
        for d, i in ung[:12]:
            t0 = i * 0.02
            seg = x[int(t0 * SR):int((t0 + DAI) * SR)]
            a16 = resample_audio(seg, SR, 16000)
            pcm = (np.clip(a16, -1, 1) * 32767).astype("<i2").tobytes()
            r = await c.post(f"{settings.whisper_server_url}/inference",
                             files={"file": ("a.wav", pcm_to_wav(pcm, 16000), "audio/wav")},
                             data={"response_format": "verbose_json", "language": "vi",
                                   "temperature": "0"})
            j = r.json()
            loi = _don_token((j.get("text") or "").strip())
            segs = j.get("segments") or []
            lp = min((s.get("avg_logprob", -9) for s in segs), default=-9)
            print(f"    giây {t0:>6.0f}  logprob {lp:>7.3f}  {loi[:58]!r}")
            if len(loi) >= 20 and (tot is None or lp > tot[0]):
                tot = (lp, t0, seg, loi)

    if tot is None:
        print("  [!] không tìm được đoạn nào đủ tốt")
        return
    lp, t0, seg, loi = tot
    print(f"\n  CHỌN: giây {t0:.0f}, logprob {lp:.3f}")
    print(f"  lời : {loi!r}")

    p = RA / "giong_heu.wav"
    with wave.open(str(p), "wb") as o:
        o.setnchannels(1); o.setsampwidth(2); o.setframerate(SR)
        o.writeframes((np.clip(seg, -1, 1) * 32767).astype("<i2").tobytes())
    (RA / "giong_heu.txt").write_text(loi, encoding="utf-8")
    print(f"  lưu : {p}  ({len(seg)/SR:.1f}s)")

    # --- đo tốc độ: 4 tổ hợp ------------------------------------------
    CAU = ("Dạ em chào anh chị ạ. Bên em đang có chương trình vay tín chấp "
           "lãi suất ưu đãi từ sáu phẩy năm phần trăm một năm.")
    LOG.mkdir(parents=True, exist_ok=True)
    print(f"\n  {'cấu hình':<38}{'sinh tiếng':>12}")
    print("  " + "-" * 50)
    for ten, ref, txt, comp in (
        ("giọng cũ 3.8s, không compile", "./models/tts/ref_voices/giong_ngan.wav",
         "Xin chào anh chị, em là nhân viên tư vấn ngân hàng.", False),
        ("giọng cũ 3.8s, CÓ compile", "./models/tts/ref_voices/giong_ngan.wav",
         "Xin chào anh chị, em là nhân viên tư vấn ngân hàng.", True),
        ("giọng mới 3.2s, không compile", "./models/tts/ref_voices/giong_heu.wav", loi, False),
        ("giọng mới 3.2s, CÓ compile", "./models/tts/ref_voices/giong_heu.wav", loi, True),
    ):
        settings.f5tts_ref_audio, settings.f5tts_ref_text = ref, txt
        settings.f5tts_compile = comp
        tts = F5TTSService(); tts.load()
        await tts.synthesize("khởi động một hai ba", use_cache=False)
        ms = []
        for k in range(3):
            t = time.perf_counter()
            w = await tts.synthesize(CAU, use_cache=False)
            ms.append((time.perf_counter() - t) * 1000)
            if k == 0:
                (LOG / f"cuoi_{ten.replace(' ','_').replace(',','')}.wav").write_bytes(w)
        print(f"  {ten:<38}{np.mean(ms):>9.0f} ms")


asyncio.run(main())
