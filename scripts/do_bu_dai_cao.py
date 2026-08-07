"""Tiếng khách mất dải phụ âm - bù lại thì STT có khá hơn không?

ĐỪNG nhầm với lọc tạp âm. Đo trên cuộc gọi thật (`scripts/do_tap_am_that.py`):
SNR 48-51 dB, tức kênh CỰC SẠCH - lọc nhiễu ở đây không có gì để lọc, chỉ tổ
làm hỏng thêm. Chỗ hỏng thật nằm ở PHÂN BỐ PHỔ:

    dải        cuộc gọi ĐỌC ĐÚNG   cuộc gọi ĐỌC SAI
    200-500Hz        41.9%              58.4%
    500-1k           42.0%              27.3%
    2k-3k             5.2%               0.3%   <- dải phụ âm, mất sạch
    3k-3.4k           0.7%               0.0%

Mất 2-3kHz là mất s, x, t, ch, th - Whisper chỉ còn nguyên âm nên đoán bừa
("khuynh số tài khoản"). Đây là bài toán BÙ NGHIÊNG PHỔ, không phải khử nhiễu.

Cách đo: lấy câu có lời gốc biết trước, cho qua kênh thoại thật (8kHz + AMR-NB)
RỒI áp thêm đúng độ nghiêng đo được ở cuộc gọi hỏng, sau đó thử từng cách bù và
chấm CER. Có lời gốc nên chấm được, mà độ méo thì đúng thứ gặp thật.

    python scripts/do_bu_dai_cao.py
"""

import argparse
import asyncio
import io
import sys
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

CAU = [
    "Cho anh hỏi lãi suất vay tín chấp bao nhiêu",
    "Anh muốn vay hai trăm triệu trong ba mươi sáu tháng",
    "Cần những giấy tờ gì để làm hồ sơ",
    "Anh có căn cước công dân và sao kê lương rồi",
    "Hạn mức tối đa của bên em là bao nhiêu",
]
TU_KHOA = ["lãi suất", "tín chấp", "căn cước", "sao kê", "hạn mức", "hồ sơ"]


def cer(dung: str, doan: str) -> float:
    a = " ".join(dung.lower().split())
    b = " ".join(doan.lower().split())
    if not a:
        return 0.0
    truoc = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        nay = [i]
        for j, cb in enumerate(b, 1):
            nay.append(min(truoc[j] + 1, nay[j - 1] + 1,
                           truoc[j - 1] + (ca != cb)))
        truoc = nay
    return truoc[-1] / len(a)


def dai_nang_luong(x: np.ndarray, sr: int) -> dict[str, float]:
    F = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / sr)
    tong = F.sum() or 1.0
    return {ten: 100.0 * F[(f >= a) & (f < b)].sum() / tong
            for ten, a, b in [("200-500", 200, 500), ("500-1k", 500, 1000),
                              ("1k-2k", 1000, 2000), ("2k-3k", 2000, 3000)]}


# --- các cách bù, tất cả chạy ở 8kHz ---------------------------------------

def khong_bu(x, sr):
    return x


def tien_nhan_manh(x, sr, a=0.97):
    """Pre-emphasis y[n] = x[n] - a*x[n-1]: nâng đều 6dB/quãng tám.

    Đây là bước tiền xử lý kinh điển của nhận dạng tiếng nói, có sẵn trong hầu
    hết bộ trích đặc trưng - nhưng Whisper KHÔNG làm, nó ăn thẳng mel spectrogram.
    """
    y = np.append(x[0], x[1:] - a * x[:-1])
    return y.astype(np.float32)


def _ke_cao(x, sr, f0: float, db: float):
    """Kệ cao (high-shelf): nâng `db` dB cho mọi tần trên `f0`, dưới đó giữ nguyên.

    Đúng hình dạng cần cho chỗ này: chỗ hỏng là dải trên bị TỤT so với dải dưới,
    nên phải nâng một mảng chứ không phải nhấn một điểm.
    """
    from scipy import signal as _sg
    A = 10 ** (db / 40)
    w0 = 2 * np.pi * f0 / sr
    alpha = np.sin(w0) / (2 * 0.707)
    c, s = np.cos(w0), 2 * np.sqrt(A) * alpha
    b = [A * ((A + 1) + (A - 1) * c + s), -2 * A * ((A - 1) + (A + 1) * c),
         A * ((A + 1) + (A - 1) * c - s)]
    a = [(A + 1) - (A - 1) * c + s, 2 * ((A - 1) - (A + 1) * c),
         (A + 1) - (A - 1) * c - s]
    y = _sg.lfilter(np.array(b) / a[0], np.array(a) / a[0], x)
    return np.clip(y, -1, 1).astype(np.float32)


def ke_cao_10(x, sr):
    return _ke_cao(x, sr, 1200.0, 10.0)


def ke_cao_16(x, sr):
    return _ke_cao(x, sr, 1200.0, 16.0)


def loc_nhieu_hien_co(x, sr):
    """Bộ lọc tạp âm đã viết sẵn trong dự án nhưng CHƯA TỪNG được gọi."""
    from backend.services.phone_call_service import lam_sach_tieng_khach
    return lam_sach_tieng_khach(x, sr)


def ke_cao_va_loc(x, sr):
    return ke_cao_10(loc_nhieu_hien_co(x, sr), sr)


CACH = [("không bù", khong_bu), ("lọc nhiễu có sẵn", loc_nhieu_hien_co),
        ("pre-emphasis .97", tien_nhan_manh), ("kệ cao 1.2k +10dB", ke_cao_10),
        ("kệ cao 1.2k +16dB", ke_cao_16), ("lọc nhiễu + kệ cao", ke_cao_va_loc)]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cat-hz", type=float, default=1250.0,
                    help="tần số cắt mô phỏng độ nghiêng của cuộc gọi hỏng")
    a = ap.parse_args()

    import httpx
    from scipy import signal as _sg

    from backend.config import settings
    from backend.services.audio_utils import pcm_to_wav, resample_audio, resample_lien_tuc
    from backend.services.tts_service import F5TTSService
    from tang_tuan_hoan import lay_bo_ma_amr

    tts = F5TTSService(); tts.load()
    qua_amr, _ = lay_bo_ma_amr()

    # Mô phỏng kênh hỏng: qua AMR rồi áp lọc thông thấp bậc 1 để ép phổ về đúng
    # dạng đo được (2k-3k tụt còn ~0.3%).
    sos = _sg.butter(1, a.cat_hz / 4000.0, btype="low", output="sos")

    mau = []
    for cau in CAU:
        wav = await tts.synthesize(cau, use_cache=False)
        with wave.open(io.BytesIO(wav)) as w:
            sr24 = w.getframerate()
            x = (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
                 .astype(np.float32) / 32768.0)
        x8 = qua_amr(resample_audio(x, sr24, 8000))
        mau.append((_sg.sosfilt(sos, x8).astype(np.float32), cau))

    d = dai_nang_luong(np.concatenate([m for m, _ in mau]), 8000)
    print(f"\n  Kênh mô phỏng (cắt {a.cat_hz:.0f}Hz) so với cuộc gọi hỏng thật:")
    print(f"    {'dải':>8} {'mô phỏng':>10} {'thật':>8}")
    for ten, that in (("200-500", 58.4), ("500-1k", 27.3), ("1k-2k", 8.7),
                      ("2k-3k", 0.3)):
        print(f"    {ten:>8} {d[ten]:>9.1f}% {that:>7.1f}%")

    print(f"\n  {'cách bù':<22}{'CER':>8}{'từ khoá':>10}  ví dụ nghe ra")
    print("  " + "-" * 88)
    async with httpx.AsyncClient(timeout=90.0) as c:
        for ten, ham in CACH:
            tong_cer, giu, tong_khoa, vi_du = 0.0, 0, 0, ""
            for x8, goc in mau:
                y = resample_lien_tuc(ham(x8, 8000), 8000, 16000)
                pcm = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
                r = await c.post(
                    f"{settings.whisper_server_url}/inference",
                    files={"file": ("a.wav", pcm_to_wav(pcm, 16000), "audio/wav")},
                    data={"response_format": "json", "language": "vi",
                          "temperature": "0", "prompt": ""})
                tho = (r.json().get("text") or "").strip()
                tong_cer += cer(goc, tho)
                khoa = [k for k in TU_KHOA if k in goc.lower()]
                giu += sum(1 for k in khoa if k in tho.lower())
                tong_khoa += len(khoa)
                vi_du = vi_du or tho
            print(f"  {ten:<22}{tong_cer/len(mau):>8.3f}"
                  f"{f'{giu}/{tong_khoa}':>10}  {vi_du[:44]!r}")

    print("\n  CER thấp hơn + giữ được nhiều từ khoá hơn = tốt hơn. Nếu 'không bù'")
    print("  đã tốt nhất thì đừng thêm gì cả - mọi bộ lọc đều có giá của nó.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
