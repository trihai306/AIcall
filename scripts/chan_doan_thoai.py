"""Vì sao giọng nghe ổn ở bản gốc nhưng sang điện thoại thì hỏng?

CER nói đường thoại chỉ mất 2% năng lượng, nhưng tai nghe ra khác. Kiểm ba
nghi phạm đo được:
  1. Mức âm lượng - AMR lượng tử hoá theo mức tín hiệu, tiếng nhỏ thì nhiễu nổi
  2. Đỉnh tín hiệu - vượt ngưỡng thì codec méo
  3. Độ nghiêng phổ - mất dải trên làm giọng đục, cần biết đục bao nhiêu
  4. Ranh giới giữa các mảnh - resample TỪNG MẢNH riêng thì mỗi mối nối có gợn
"""
import asyncio, io, subprocess, sys, tempfile, wave
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
P = Path(r"C:\duan\chat-ai"); sys.path.insert(0, str(P))
import numpy as np
from backend.services.audio_utils import resample_audio

CAU = ["Dạ anh chị chuẩn bị chứng minh nhân dân ạ",
       "Lãi suất vay tín chấp từ sáu phẩy năm phần trăm một năm",
       "Hạn mức cho vay lên đến năm trăm triệu đồng"]

def doc(b):
    with wave.open(io.BytesIO(b)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype("float32")/32768, w.getframerate()

def nghieng_pho(x, sr):
    """Tỉ số năng lượng dải cao (1-3.4kHz) trên dải thấp (100-1000Hz).
    Càng nhỏ càng đục."""
    ph = np.abs(np.fft.rfft(x * np.hanning(len(x))))**2
    f = np.fft.rfftfreq(len(x), 1/sr)
    thap = ph[(f>=100)&(f<1000)].sum() or 1e-12
    cao = ph[(f>=1000)&(f<3400)].sum()
    return float(cao/thap)

async def main():
    from backend.services.tts_service import F5TTSService
    tts = F5TTSService(); tts.load()
    await tts.synthesize("khởi động", use_cache=False)

    print("1) MỨC ÂM LƯỢNG của tiếng TTS (AMR cần tín hiệu đủ to mới ít nhiễu)")
    print(f"   {'câu':<5}{'RMS':>10}{'đỉnh':>9}{'dBFS':>9}{'độ dự trữ':>12}")
    rms_all = []
    manh = []
    for i, c in enumerate(CAU, 1):
        w = await tts.synthesize(c, use_cache=False)
        x, sr = doc(w); manh.append((x, sr))
        r = float(np.sqrt((x**2).mean())); d = float(np.abs(x).max())
        rms_all.append(r)
        print(f"   {i:<5}{r:>10.4f}{d:>9.3f}{20*np.log10(r+1e-12):>9.1f}"
              f"{20*np.log10(1/(d+1e-12)):>11.1f}dB")
    print(f"   -> RMS trung bình {np.mean(rms_all):.4f} "
          f"({20*np.log10(np.mean(rms_all)):.1f} dBFS). "
          f"Chuẩn thoại thường nhắm -18 tới -20 dBFS.")

    print("\n2) ĐỘ NGHIÊNG PHỔ (năng lượng 1-3.4kHz / 100Hz-1kHz; nhỏ = đục)")
    for i, (x, sr) in enumerate(manh, 1):
        x8 = resample_audio(x, sr, 8000)
        print(f"   câu {i}: gốc 24kHz {nghieng_pho(x,sr):.3f}"
              f"   ->  hạ 8kHz {nghieng_pho(x8,8000):.3f}")

    print("\n3) RANH GIỚI MẢNH - resample từng mảnh riêng có gây gợn không?")
    x, sr = manh[0]
    n = len(x)//3
    # cách hiện tại: mỗi mảnh hạ tần riêng rồi nối
    rieng = np.concatenate([resample_audio(x[k*n:(k+1)*n], sr, 8000) for k in range(3)])
    # cách đối chứng: hạ tần cả câu một lần
    ca_cau = resample_audio(x[:3*n], sr, 8000)
    m = min(len(rieng), len(ca_cau))
    sai_khac = float(np.abs(rieng[:m] - ca_cau[:m]).max())
    # bậc nhảy tại đúng hai mối nối
    b = len(ca_cau)//3
    buoc = [abs(float(rieng[k*b] - rieng[k*b-1])) for k in (1, 2)]
    trong_long = float(np.abs(np.diff(ca_cau)).max())
    print(f"   sai khác lớn nhất so với hạ cả câu: {sai_khac:.4f}")
    print(f"   bậc nhảy tại 2 mối nối: {buoc[0]:.4f}, {buoc[1]:.4f}")
    print(f"   bậc lớn nhất trong lòng tín hiệu:   {trong_long:.4f}")
    print("   -> mối nối lớn hơn bậc bình thường là có gợn nghe được"
          if max(buoc) > trong_long else "   -> mối nối không vượt bậc bình thường")

asyncio.run(main())
