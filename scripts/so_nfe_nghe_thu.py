"""Giảm nfe thì nhanh thêm bao nhiêu, và giọng tệ đi tới đâu?

nfe = số bước khuếch tán. Mỗi bước gọi transformer 2 lần (classifier-free
guidance), nên bớt 2 bước là bớt 4 lượt tính - đây là cần gạt tốc độ mạnh nhất
còn lại sau khi đã bật torch.compile.

Cái giá là CHẤT LƯỢNG GIỌNG, mà chất lượng thì phải NGHE mới quyết được. Script
đo thời gian, xuất file để nghe, và kèm một con số khách quan để đối chiếu -
nhưng con số chỉ để tham khảo, tai người mới là trọng tài.

Xuất HAI bản mỗi mức:
  goc_24kHz    - nghe rõ mọi chi tiết, thấy được nfe thấp làm hỏng chỗ nào
  qua_dien_thoai - 8kHz + AMR-NB, ĐÚNG thứ khách nghe. Đây mới là bản để quyết,
                   vì kênh thoại có thể xoá sạch khác biệt giữa các mức nfe.

    python scripts/so_nfe_nghe_thu.py
    python scripts/so_nfe_nghe_thu.py --nfe 8 10 12 16
"""

import argparse
import asyncio
import io
import statistics
import sys
import time
import wave
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RA = PROJECT / "logs" / "so_nfe"
CAU = [
    "Dạ em chào anh chị ạ. Em là nhân viên tư vấn của ngân hàng ABC.",
    "Dạ hiện bên em lãi suất từ bảy phẩy chín phần trăm một năm ạ.",
    "Dạ chỉ cần căn cước và sao kê lương ba tháng gần nhất ạ.",
]


def doc(b: bytes):
    with wave.open(io.BytesIO(b)) as w:
        return (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
                .astype(np.float32) / 32768), w.getframerate()


def ghi(p: Path, x: np.ndarray, sr: int):
    p.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def hnr(x: np.ndarray, sr: int) -> float:
    """Tỉ lệ hài trên nhiễu (dB) - cao hơn là giọng sạch, ít rè.

    Chỉ để ĐỐI CHIẾU giữa các mức nfe trên cùng câu. Đừng so con số này với
    ngưỡng tuyệt đối nào: dự án đã đo được HNR nói dối ở bitrate thấp.
    """
    from scipy import signal as _sg
    if x.size < sr // 4:
        return 0.0
    f, t, Z = _sg.stft(x, fs=sr, nperseg=512, noverlap=384)
    P = np.abs(Z) ** 2
    manh = P.max(axis=0)
    co = manh > np.percentile(manh, 60)          # chỉ xét khung có tiếng
    if not co.any():
        return 0.0
    Pv = P[:, co]
    hai = np.sort(Pv, axis=0)[-8:].sum(axis=0)   # 8 vạch mạnh nhất ~ hài
    tong = Pv.sum(axis=0)
    ti = np.clip(hai / np.maximum(tong, 1e-12), 1e-6, 1 - 1e-6)
    return float(np.median(10 * np.log10(ti / (1 - ti))))


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nfe", type=int, nargs="+", default=[8, 10, 12, 16])
    ap.add_argument("--lap", type=int, default=3, help="đo mỗi câu mấy lần")
    a = ap.parse_args()

    from backend.config import settings
    from backend.services import phone_call_service as PS
    from backend.services.audio_utils import resample_audio
    from backend.services.tts_service import F5TTSService
    from tang_tuan_hoan import lay_bo_ma_amr

    tts = F5TTSService(); tts.load()
    giong = await tts.ensure_voice(Path(settings.f5tts_ref_audio).stem)
    qua_amr, _ = lay_bo_ma_amr()

    RA.mkdir(parents=True, exist_ok=True)
    for f in RA.glob("*"):
        f.unlink()

    print(f"\n  giọng {giong} | compile={settings.f5tts_compile}"
          f" | nfe đang dùng: {settings.f5tts_nfe_step}\n")
    print(f"  {'nfe':>5}{'ms/câu':>10}{'nhanh hơn nfe cao nhất':>26}"
          f"{'HNR gốc':>10}{'HNR qua thoại':>15}")
    print("  " + "-" * 72)

    moc_cao = None
    for nfe in sorted(a.nfe, reverse=True):
        ms, sach, thoai = [], [], []
        for i, cau in enumerate(CAU):
            for lan in range(a.lap):
                t0 = time.perf_counter()
                wav = await tts.synthesize(cau, voice=giong, use_cache=False,
                                           nfe_step=nfe)
                ms.append((time.perf_counter() - t0) * 1000)
            x, sr = doc(wav)
            y8 = resample_audio(PS.chuan_muc_thoai(x), sr, 8000)
            if settings.phone_tang_tuan_hoan:
                y8 = PS.tang_tuan_hoan(y8, 8000)
            y8 = qua_amr(y8)
            sach.append(hnr(x, sr))
            thoai.append(hnr(y8, 8000))
            ghi(RA / f"nfe{nfe:02d}_cau{i+1}_goc_24kHz.wav", x, sr)
            ghi(RA / f"nfe{nfe:02d}_cau{i+1}_qua_dien_thoai.wav", y8, 8000)

        tv = statistics.median(ms)
        moc_cao = moc_cao or tv
        print(f"  {nfe:>5}{tv:>9.0f}ms{moc_cao/tv:>24.2f}x"
              f"{statistics.median(sach):>9.1f}dB{statistics.median(thoai):>13.1f}dB")

    print(f"\n  {RA}")
    print("  NGHE BẢN 'qua_dien_thoai' để quyết, không phải bản gốc: kênh thoại")
    print("  có thể xoá sạch khác biệt mà tai nghe rõ ở 24kHz.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
