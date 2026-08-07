"""Cho tiếng đi qua AMR-NB ngay trên máy tính, khỏi phải gọi thử.

Vì sao cần: mỗi lần muốn biết một giọng nghe thế nào qua cuộc gọi, phải gọi thật
rồi hỏi tai người - chậm, và phụ thuộc người kia có rảnh không. Mà thứ làm hỏng
giọng nằm gọn trong bộ mã AMR-NB, thứ chạy được ngay trên PC:

    ffmpeg -c:a libopencore_amrnb   (mã hoá 12.2 kbps, 8kHz)
    ffmpeg                          (giải mã trở lại)

Nhờ vậy so được hàng chục giọng mẫu trong vài phút thay vì vài chục cuộc gọi.

Điểm chấm là HNR - tỉ số hài trên nhiễu. Đây là thứ quyết định vocoder dựng lại
giọng đúng hay sai: nó khớp mô hình thanh quản người vào tín hiệu, nên tín hiệu
càng giống thanh quản thật (hài rõ, ít nhiễu) thì dựng lại càng đúng. Đo trước
đây: người thật 7.2 dB, giọng F5-TTS 5.1 dB qua cùng đường này.

    python scripts/mo_phong_amr.py                      # dựng câu mẫu rồi chấm
    python scripts/mo_phong_amr.py --file duong/dan.wav # chấm một file có sẵn
"""

import argparse
import asyncio
import subprocess
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
RA = PROJECT / "data" / "qua_amr"
CAU = ("Dạ em chào anh chị ạ. Em là nhân viên tư vấn của ngân hàng. "
       "Anh chị có cần em hỗ trợ thông tin gì không ạ?")


def doc_wav(p: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(p), "rb") as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        if w.getnchannels() > 1:
            x = x.reshape(-1, w.getnchannels()).mean(axis=1)
    return x.astype(np.float32) / 32768.0, sr


def ghi_wav(p: Path, x: np.ndarray, sr: int) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return p


def qua_amr(vao: Path, ra_wav: Path, bitrate: str = "12.2k") -> Path:
    """Mã hoá sang AMR-NB rồi giải mã trở lại - đúng thứ mạng GSM làm."""
    amr = ra_wav.with_suffix(".amr")
    for lenh in (
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(vao),
         "-ar", "8000", "-ac", "1", "-c:a", "libopencore_amrnb",
         "-b:a", bitrate, str(amr)],
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(amr),
         "-ar", "8000", "-ac", "1", str(ra_wav)],
    ):
        r = subprocess.run(lenh, capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg lỗi: {(r.stderr or '')[:200]}")
    return ra_wav


def hnr(x: np.ndarray, sr: int) -> float:
    """Tỉ số hài trên nhiễu, dB. Chỉ tính trên khung CÓ TIẾNG.

    Cách làm: mỗi khung tìm đỉnh tự tương quan trong khoảng cao độ giọng người
    (70-350Hz). Đỉnh cao nghĩa là tín hiệu tuần hoàn -> nhiều hài; đỉnh thấp
    nghĩa là phần lớn là nhiễu.
    """
    n = int(0.04 * sr)                       # khung 40ms
    if x.size < n * 3:
        return 0.0
    khung = x[:x.size // n * n].reshape(-1, n)
    muc = np.sqrt((khung ** 2).mean(axis=1))
    co_tieng = khung[muc > muc.max() * 0.2]
    if co_tieng.shape[0] == 0:
        return 0.0

    lo, hi = int(sr / 350), int(sr / 70)
    ra = []
    for k in co_tieng:
        k = k - k.mean()
        r = np.correlate(k, k, mode="full")[n - 1:]
        if r[0] <= 0:
            continue
        r = r / r[0]
        if hi >= r.size:
            continue
        p = float(r[lo:hi].max())
        p = min(max(p, 1e-6), 0.999999)
        ra.append(10 * np.log10(p / (1 - p)))
    return float(np.mean(ra)) if ra else 0.0


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="WAV có sẵn; bỏ trống thì dựng câu mẫu bằng TTS")
    ap.add_argument("--bitrate", default="12.2k")
    a = ap.parse_args()

    RA.mkdir(parents=True, exist_ok=True)
    if a.file:
        goc = Path(a.file)
        ten = goc.stem
    else:
        from backend.services.tts_service import F5TTSService
        kho = PROJECT / "data" / "mau_so_sanh.wav"
        if not kho.exists():
            print("Dựng câu mẫu bằng TTS ...")
            tts = F5TTSService(); tts.load()
            kho.write_bytes(await tts.synthesize(CAU, use_cache=False))
        goc, ten = kho, "tts"

    x, sr = doc_wav(goc)
    sau = qua_amr(goc, RA / f"{ten}_qua_amr.wav", a.bitrate)
    y, sr2 = doc_wav(sau)

    # So HNR ở CÙNG tần số lấy mẫu. Bản gốc 24kHz mà bản qua AMR 8kHz thì khoảng
    # tìm cao độ lệch nhau, chấm ra số không so được với nhau.
    goc8 = RA / f"{ten}_goc_8k.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(goc),
                    "-ar", "8000", "-ac", "1", str(goc8)],
                   capture_output=True, timeout=120)
    x8, _ = doc_wav(goc8)

    h_goc, h_sau = hnr(x8, 8000), hnr(y, 8000)
    print(f"\n    {'':<22}{'HNR (dB)':>10}{'RMS':>10}")
    print(f"    {'gốc (hạ về 8kHz)':<22}{h_goc:>10.2f}{np.sqrt((x8**2).mean())*32768:>10.0f}")
    print(f"    {'sau khi qua AMR-NB':<22}{h_sau:>10.2f}{np.sqrt((y**2).mean())*32768:>10.0f}")
    print(f"    {'mất đi':<22}{h_goc - h_sau:>10.2f}")
    print(f"\n    nghe thử: {sau}")
    print("\n    Mốc so sánh đã đo trước đây qua cùng đường này:")
    print("      người thật 7.2 dB  ·  giọng F5-TTS 5.1 dB")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
