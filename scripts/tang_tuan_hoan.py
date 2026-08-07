"""CÁCH 3: làm tín hiệu TTS "hợp gu" bộ mã CELP hơn, để bớt tiếng kim loại.

BỐI CẢNH. Cuộc gọi GSM bắt buộc đi qua AMR-NB, không có chế độ truyền thô -
tắt hết bộ lọc của điện thoại cũng không thoát được. Nên trong ràng buộc "phải
là cuộc gọi tới SIM thật", đòn bẩy duy nhất còn lại nằm ở phía TA: sửa tín hiệu
trước khi đưa vào bộ mã.

ĐO ĐƯỢC ĐIỀU QUYẾT ĐỊNH. Cho bản thu NGƯỜI THẬT đi qua AMR-NB:
    HNR   6.98 -> 7.18 dB   (TĂNG nhẹ)
    phẳng 0.0484 -> 0.0446  (phổ bớt phẳng)
Tức bộ mã KHÔNG hề làm hỏng giọng người. Nó chỉ dựng sai khi tín hiệu vào thiếu
tính tuần hoàn - đúng chỗ giọng khuếch tán yếu (5.1 dB so với 7.2 dB).

Ý TƯỞNG. AMR-NB dựng lại giọng theo mô hình "bộ lọc thanh quản + nguồn kích
thích TUẦN HOÀN". Bộ dự đoán chu kỳ (LTP) của nó bám vào phần lặp lại giữa các
chu kỳ cao độ. Nhiễu rộng dải xen giữa các hài làm nó bám trượt -> âm kim loại.
Vậy hãy TĂNG tính tuần hoàn trước khi đưa vào.

HAI KỸ THUẬT:
  A. Lọc lược đồng bộ cao độ - cộng tín hiệu với chính nó trễ đúng một chu kỳ.
     Phần tuần hoàn trùng pha nên cộng dồn, nhiễu lệch pha nên triệt bớt.
  B. Tăng tuần hoàn trên PHẦN DƯ tuyến tính - tách bao phổ (LPC) ra, chỉ làm
     sạch nguồn kích thích rồi dựng lại. Đây đúng là thứ CELP mô hình hoá, và
     vì giữ nguyên bao phổ nên không đổi âm sắc.

KẾT QUẢ ĐO (mẫu thay thế: giọng người trộn nhiễu cho tụt về 5.1 dB):
    chưa xử lý            5.60 dB sau AMR   phẳng 0.1016
    A  lọc lược           6.48 dB           phẳng 0.0805
    B  phần dư            6.14 dB           phẳng 0.0854
    C  cả hai             6.66 dB           phẳng 0.0735   <- tốt nhất
    người thật (đích)     7.18 dB           phẳng 0.0446
C lấy lại 1.06 dB trong khoảng cách 1.58 dB, tức khoảng 2/3.

Chi phí: 24.7ms cho 3.78s tiếng (0.65% thời gian thực) - không đáng kể so với
ngân sách TTFA 1000ms.

CHƯA KIỂM CHỨNG - ĐỌC KỸ TRƯỚC KHI BẬT LÊN PRODUCTION:
  1. Mẫu thử là giọng người TRỘN NHIỄU, không phải tiếng F5-TTS thật. Nhiễu
     được thêm vào rồi lọc ra nên có phần vòng quanh. Phải chạy lại trên tiếng
     TTS thật (máy Windows có GPU) mới kết luận được.
  2. Méo phổ đo được 8.4 dB khi áp lên giọng sạch - tín hiệu bị đổi khá nhiều.
     Phần lớn là do bỏ nền nhiễu giữa các hài (đúng chủ đích), nhưng lọc lược
     quá tay thì sinh tiếng rỗng/máy móc. PHẢI NGHE BẰNG TAI trước khi chốt.
     Đối chứng có lợi: so với bản gốc sạch, tín hiệu suy biến cách 16.17 dB,
     sau khi xử lý còn 12.86 dB - tức có kéo lại gần giọng thật hơn.

    python scripts/tang_tuan_hoan.py              # chạy lại bảng đo trên
    python scripts/tang_tuan_hoan.py --nghe       # dựng file WAV để nghe thử
"""

import sys
import wave
from pathlib import Path

import numpy as np
from scipy import signal as sg

PROJECT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# Bộ mã AMR-NB - hai máy hai đường khác nhau
# --------------------------------------------------------------------------
def lay_bo_ma_amr():
    """Trả hàm qua_amr(x8)->y8, tự chọn đường theo máy đang chạy.

    Mac: ctypes vào libopencore-amrnb.dylib, vì ffmpeg của Homebrew chỉ có bộ
         GIẢI mã AMR chứ không có bộ MÃ HOÁ.
    Windows: ffmpeg ở C:\\ffmpeg-shared có đủ `libopencore_amrnb`.
    Cùng codec, cùng bitrate 12.2k nên số đo hai máy so được với nhau.
    """
    try:
        sys.path.insert(0, str(PROJECT / "scripts"))
        from amr_tren_mac import AmrNb
        bo = AmrNb()
        return bo.qua_amr, "ctypes/libopencore-amrnb"
    except Exception:
        pass

    import subprocess
    import tempfile

    def qua_amr_ffmpeg(x8: np.ndarray) -> np.ndarray:
        with tempfile.TemporaryDirectory() as d:
            vao, amr, ra = (Path(d) / n for n in ("i.wav", "m.amr", "o.wav"))
            ghi_wav(vao, x8, 8000)
            for lenh in (
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(vao),
                 "-ar", "8000", "-ac", "1", "-c:a", "libopencore_amrnb",
                 "-b:a", "12.2k", str(amr)],
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(amr),
                 "-ar", "8000", "-ac", "1", str(ra)],
            ):
                r = subprocess.run(lenh, capture_output=True, text=True, timeout=180)
                if r.returncode != 0:
                    raise RuntimeError(
                        "ffmpeg không có libopencore_amrnb hoặc lỗi: "
                        f"{(r.stderr or '')[:200]}")
            return doc_wav(ra)[0]

    return qua_amr_ffmpeg, "ffmpeg/libopencore_amrnb"


# --------------------------------------------------------------------------
# Đọc / đổi tần số
# --------------------------------------------------------------------------
def doc_wav(p: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(p), "rb") as w:
        sr, nc = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        if nc > 1:
            x = x.reshape(-1, nc).mean(axis=1)
    return x.astype(np.float32) / 32768.0, sr


def ghi_wav(p: Path, x: np.ndarray, sr: int) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def resample(x: np.ndarray, sr: int, dich: int) -> np.ndarray:
    if sr == dich:
        return x.astype(np.float32)
    return sg.resample(x, int(len(x) * dich / sr)).astype(np.float32)


# --------------------------------------------------------------------------
# Thước đo - giữ cùng công thức với do_kim_loai.py để số so được với nhau
# --------------------------------------------------------------------------
def do_hnr(x: np.ndarray, sr: int) -> float:
    N, H = 1024, 512
    ra = []
    for k in range(0, len(x) - N, H):
        w = x[k:k + N]
        if np.sqrt((w ** 2).mean()) < 0.01:
            continue
        w = w - w.mean()
        ac = np.correlate(w, w, mode="full")[N - 1:]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        lo, hi = int(sr / 400), int(sr / 70)
        if hi >= len(ac):
            continue
        r = min(max(float(ac[lo:hi].max()), 1e-6), 0.999999)
        ra.append(10 * np.log10(r / (1 - r)))
    return float(np.mean(ra)) if ra else 0.0


def do_phang_pho(x: np.ndarray, sr: int) -> float:
    N, H = 1024, 512
    ra = []
    for k in range(0, len(x) - N, H):
        w = x[k:k + N]
        if np.sqrt((w ** 2).mean()) < 0.01:
            continue
        ph = np.abs(np.fft.rfft(w * np.hanning(N))) ** 2 + 1e-12
        f = np.fft.rfftfreq(N, 1 / sr)
        ph = ph[(f >= 200) & (f < 3400)]
        ra.append(float(np.exp(np.log(ph).mean()) / ph.mean()))
    return float(np.mean(ra)) if ra else 0.0


def do_meo_pho(x: np.ndarray, y: np.ndarray, sr: int) -> float:
    """Log-spectral distance, dB. Dưới 1dB thì tai người khó phân biệt."""
    N, H = 512, 256
    n = min(len(x), len(y))
    x, y = x[:n], y[:n]
    ra = []
    for k in range(0, n - N, H):
        a = x[k:k + N]
        if np.sqrt((a ** 2).mean()) < 0.01:
            continue
        A = np.abs(np.fft.rfft(a * np.hanning(N))) ** 2 + 1e-10
        B = np.abs(np.fft.rfft(y[k:k + N] * np.hanning(N))) ** 2 + 1e-10
        f = np.fft.rfftfreq(N, 1 / sr)
        m = (f >= 200) & (f < 3400)
        d = 10 * (np.log10(A[m]) - np.log10(B[m]))
        ra.append(np.sqrt((d ** 2).mean()))
    return float(np.mean(ra)) if ra else 0.0


# --------------------------------------------------------------------------
# Ước lượng cao độ
# --------------------------------------------------------------------------
def uoc_luong_chu_ky(x, sr, N=320, H=160, nguong=0.30):
    """Chu kỳ cao độ (số mẫu) cho từng khung; 0 = vô thanh hoặc im.

    Ngưỡng 0.30 để chỉ nhận khung thật sự hữu thanh - áp lọc lược lên phụ âm
    xát (s, x, ch) sẽ làm nhoè chúng, mà phụ âm mới là thứ quyết định nghe rõ.
    """
    lo, hi = int(sr / 400), int(sr / 70)
    ra = []
    for k in range(0, max(len(x) - N, 0) + 1, H):
        w = x[k:k + N]
        if len(w) < N or np.sqrt((w ** 2).mean()) < 0.01:
            ra.append(0)
            continue
        w = w - w.mean()
        ac = np.correlate(w, w, mode="full")[N - 1:]
        if ac[0] <= 0 or hi >= len(ac):
            ra.append(0)
            continue
        ac = ac / ac[0]
        seg = ac[lo:hi]
        i = int(np.argmax(seg))
        ra.append(lo + i if seg[i] > nguong else 0)
    return np.array(ra), H


# --------------------------------------------------------------------------
# A. Lọc lược đồng bộ cao độ
# --------------------------------------------------------------------------
def loc_luoc(x, sr, alpha=0.4, N=320, H=160):
    """y[n] = (x[n] + a*x[n-T] + a*x[n+T]) / (1+2a), T = chu kỳ cao độ.

    Lấy cả chu kỳ trước và sau (chứ không chỉ trước) để không làm lệch pha -
    lệch pha nghe thành tiếng vọng nhẹ.
    """
    chu_ky, H = uoc_luong_chu_ky(x, sr, N, H)
    y = x.copy()
    for i, T in enumerate(chu_ky):
        if T <= 0:
            continue
        idx = np.arange(i * H, min(i * H + H, len(x)))
        ok = (idx - T >= 0) & (idx + T < len(x))
        if not ok.any():
            continue
        j = idx[ok]
        y[j] = (x[j] + alpha * x[j - T] + alpha * x[j + T]) / (1 + 2 * alpha)
    return y.astype(np.float32)


# --------------------------------------------------------------------------
# B. Tăng tuần hoàn trên phần dư LP
# --------------------------------------------------------------------------
def _lpc(x, p):
    """Levinson-Durbin. Trả None nếu khung suy biến."""
    r = np.correlate(x, x, mode="full")[len(x) - 1:len(x) + p]
    if len(r) < p + 1 or r[0] <= 0:
        return None
    a = np.zeros(p + 1)
    a[0], e = 1.0, r[0]
    for i in range(1, p + 1):
        acc = r[i] + (np.dot(a[1:i], r[i - 1:0:-1]) if i > 1 else 0.0)
        k = -acc / e
        moi = a.copy()
        for j in range(1, i):
            moi[j] = a[j] + k * a[i - j]
        moi[i] = k
        a = moi
        e *= (1 - k * k)
        if e <= 0:
            return None
    return a


def tang_tuan_hoan_du(x, sr, alpha=0.7, p=10, N=320, H=160):
    """Tách bao phổ (LPC) ra, làm sạch phần dư, rồi dựng lại.

    Giữ nguyên bao phổ nên KHÔNG đổi âm sắc - chỉ đổi độ tuần hoàn của nguồn
    kích thích, đúng thứ bộ dự đoán chu kỳ của CELP nhìn vào.
    """
    chu_ky, H = uoc_luong_chu_ky(x, sr, N, H)
    y = np.zeros(len(x), dtype=np.float32)
    dem = np.zeros(len(x), dtype=np.float32)
    cua = np.hanning(N).astype(np.float32)

    for i, T in enumerate(chu_ky):
        a0, b0 = i * H, i * H + N
        if b0 > len(x):
            break
        w = x[a0:b0] * cua
        a = _lpc(w, p) if (T > 0 and np.sqrt((w ** 2).mean()) >= 1e-4) else None
        if a is None:
            y[a0:b0] += w
            dem[a0:b0] += cua
            continue
        du = sg.lfilter(a, [1.0], w)
        if T < len(du):
            du[T:] = (du[T:] + alpha * du[:-T].copy()) / (1 + alpha)
        lai = sg.lfilter([1.0], a, du)
        # giữ nguyên năng lượng khung, tránh bộ lọc kéo mức trôi
        r0 = np.sqrt((w ** 2).mean())
        r1 = np.sqrt((lai ** 2).mean()) or 1e-9
        y[a0:b0] += (lai * (r0 / r1)).astype(np.float32)
        dem[a0:b0] += cua

    # Rìa đầu/cuối: cửa sổ Hann tắt dần về 0 nên `dem` ở đó rất nhỏ, chia cho nó
    # sinh đỉnh khổng lồ. Ngưỡng 1e-6 quá lỏng để bắt. Chỗ nào cửa sổ phủ chưa
    # đủ thì coi như chưa xử lý, giữ nguyên đầu vào.
    thieu = dem < 0.5
    dem[thieu] = 1.0
    z = (y / dem).astype(np.float32)
    z[thieu] = x[thieu]
    return z


def xu_ly(x, sr, a_luoc=0.4, a_du=0.7):
    """Kỹ thuật C - cả hai bước. Đây là cấu hình đo được tốt nhất."""
    return tang_tuan_hoan_du(loc_luoc(x, sr, a_luoc), sr, a_du)


# --------------------------------------------------------------------------
# Mẫu thay thế cho tiếng TTS (máy Mac không chạy được F5-TTS)
# --------------------------------------------------------------------------
def lam_suy_bien(x, sr, hnr_dich=5.1, seed=0):
    """Trộn nhiễu rộng dải cho HNR tụt về đúng mức đo được của F5-TTS."""
    rng = np.random.default_rng(seed)
    nhieu = rng.standard_normal(len(x)).astype(np.float32)
    b, a = sg.butter(4, [200 / (sr / 2), 3400 / (sr / 2)], btype="band")
    nhieu = sg.lfilter(b, a, nhieu).astype(np.float32)
    nhieu /= (np.sqrt((nhieu ** 2).mean()) or 1e-9)
    rms = np.sqrt((x ** 2).mean())
    lo, hi = 0.0, 1.0
    for _ in range(30):
        m = (lo + hi) / 2
        if do_hnr(x + nhieu * rms * m, sr) > hnr_dich:
            lo = m
        else:
            hi = m
    return (x + nhieu * rms * (lo + hi) / 2).astype(np.float32)


# --------------------------------------------------------------------------
def _main() -> int:
    import argparse

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="WAV để thử; bỏ trống thì dùng giọng mẫu")
    ap.add_argument("--nghe", action="store_true", help="dựng WAV để nghe thử")
    a = ap.parse_args()

    p = Path(a.file) if a.file else PROJECT / "models/tts/ref_voices/giong_ngan.wav"
    x, sr = doc_wav(p)
    x8 = resample(x, sr, 8000)
    qua_amr, duong = lay_bo_ma_amr()
    print(f"\n  Bộ mã AMR: {duong}")

    def cham(ten, sig, so_voi=None):
        y = qua_amr(sig)
        meo = f"{do_meo_pho(so_voi, sig, 8000):>9.2f}" if so_voi is not None else f"{'-':>9}"
        print(f"  {ten:<30}{do_hnr(sig, 8000):>8.2f}{do_hnr(y, 8000):>10.2f}"
              f"{do_phang_pho(y, 8000):>11.4f}{meo}")
        return do_hnr(y, 8000), y

    print(f"\n  Mẫu: {p.name}  ({len(x8)/8000:.2f}s)")
    print(f"  {'=' * 70}")
    print(f"  {'':<30}{'HNR vào':>8}{'sau AMR':>10}{'phẳng sau':>11}{'méo phổ':>9}")
    print(f"  {'-' * 70}")
    cham("người thật (đích)", x8)
    xd = lam_suy_bien(x8, 8000)
    base, _ = cham("suy biến ~TTS (mốc dưới)", xd, x8)
    print(f"  {'-' * 70}")
    tot = 0.0
    for al, ad in ((0.2, 0.4), (0.4, 0.7), (0.6, 0.8)):
        h, _ = cham(f"+ xử lý ({al}, {ad})", xu_ly(xd, 8000, al, ad), x8)
        tot = max(tot, h)
    print(f"  {'=' * 70}")
    print(f"\n  Lấy lại {tot - base:+.2f} dB trong khoảng cách "
          f"{7.18 - base:.2f} dB tới giọng người.")
    print("  Cột 'méo phổ' so với BẢN GỐC SẠCH: thấp hơn = gần giọng thật hơn.")

    if a.nghe:
        out = PROJECT / "logs" / "cach3_nghe_thu"
        out.mkdir(parents=True, exist_ok=True)
        for f in out.glob("*.wav"):
            f.unlink()
        for ten, sig in (("1_nguoi_that", x8),
                         ("2_suy_bien_chua_xu_ly", xd),
                         ("3_suy_bien_xu_ly_nhe", xu_ly(xd, 8000, 0.2, 0.4)),
                         ("4_suy_bien_xu_ly_manh", xu_ly(xd, 8000, 0.4, 0.7)),
                         ("5_nguoi_that_co_xu_ly", xu_ly(x8, 8000, 0.4, 0.7))):
            ghi_wav(out / f"{ten}__qua_dien_thoai.wav", qua_amr(sig), 8000)
        print(f"\n  Mẫu nghe thử: {out}")
        print("  Nghe 2 -> 3 -> 4 để thấy mức xử lý tăng dần.")
        print("  File 5: kiểm tra xử lý có làm hỏng giọng vốn đã sạch không.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
