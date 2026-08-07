"""Giọng mẫu nào sống sót qua vocoder AMR tốt nhất?

nfe không ảnh hưởng (đã đo). Nắm còn lại là chính giọng mẫu: vocoder dựng lại
tiếng theo mô hình thanh quản, nên giọng nào có phần tuần hoàn mạnh (HNR cao,
phổ ít phẳng) thì dựng lại đúng hơn; giọng nhiều hơi, nhiều nhiễu thì méo.
Đo cả tần số cơ bản: F0 quá cao hoặc quá thấp đều khó cho mô hình 8kHz.
"""
import asyncio, io, subprocess, sys, tempfile, wave
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
P = Path(r"C:\duan\chat-ai"); sys.path.insert(0, str(P))
import numpy as np
sys.path.insert(0, str(P/"scripts"))
from do_kim_loai import do_phang_pho, do_hnr, qua_gsm, ghi, doc

CAU = ("Dạ em chào anh chị ạ. Bên em đang có chương trình vay tín chấp "
       "lãi suất ưu đãi từ sáu phẩy năm phần trăm một năm.")

def do_f0(x, sr):
    """F0 trung vị bằng tự tương quan trên các khung có tiếng."""
    N, H = 1024, 512
    ra = []
    for k in range(0, len(x)-N, H):
        w = x[k:k+N]
        if np.sqrt((w**2).mean()) < 0.01: continue
        w = w - w.mean()
        ac = np.correlate(w, w, mode="full")[N-1:]
        if ac[0] <= 0: continue
        lo, hi = int(sr/400), int(sr/70)
        if hi >= len(ac): continue
        ra.append(sr / (lo + int(np.argmax(ac[lo:hi]))))
    return float(np.median(ra)) if ra else 0.0

async def main():
    from backend.config import settings
    from backend.services.audio_utils import resample_audio
    from backend.services.tts_service import F5TTSService
    tts = F5TTSService(); tts.load()
    await tts.synthesize("khởi động", use_cache=False)
    out = P/"logs"/"so_giong"; out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.wav"): f.unlink()

    giong = [v["name"] for v in tts.list_voices() if v.get("ref_text")]
    print(f"Có {len(giong)} giọng: {', '.join(giong)}\n")
    print(f"{'giọng':<14}{'F0':>7}{'phẳng gốc':>12}{'sau AMR':>10}"
          f"{'HNR gốc':>10}{'sau AMR':>10}{'sụt HNR':>10}")
    print("-" * 74)
    for g in giong:
        try:
            ten = await tts.ensure_voice(g)
            w = await tts.synthesize(CAU, use_cache=False, voice=ten)
        except Exception as e:
            print(f"{g:<14} lỗi: {e}")
            continue
        x, sr = doc(w)
        x8 = resample_audio(x, sr, 8000)
        y8 = qua_gsm(x8)
        (out/f"{g}_goc24k.wav").write_bytes(w)
        (out/f"{g}_qua_dien_thoai.wav").write_bytes(ghi(y8, 8000))
        hg, ha = do_hnr(x, sr), do_hnr(y8, 8000)
        print(f"{g:<14}{do_f0(x,sr):>6.0f}Hz{do_phang_pho(x,sr):>12.4f}"
              f"{do_phang_pho(y8,8000):>10.4f}{hg:>9.1f}dB{ha:>9.1f}dB{ha-hg:>+9.1f}dB")
    print("-" * 74)
    print(f"\n{out}")

asyncio.run(main())
