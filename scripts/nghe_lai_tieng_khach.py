"""Nghe lại CHÍNH tiếng mình đã nói trong cuộc gọi, đủ to để đối chiếu với bản
phiên âm.

Vì sao cần: trong file hội thoại ghép, tiếng khách là bản ghi thật qua GSM nên
nhỏ hơn tiếng F5 khoảng 9dB và bị cắt còn dải 300-3400Hz, nghe cạnh nhau thì
gần như chìm - không cách nào tự kiểm được "máy nghe đúng chưa".

Script cắt từng lượt theo đúng logic VAD, chuẩn mức từng lượt cho ngang tiếng
AI, rồi ghi ra:
  0_ca_bang_ghi.wav   - cả bản ghi, đã chuẩn mức
  luot_1..N.wav       - từng lượt riêng, để nghe đi nghe lại một câu
  ban_chu.txt         - máy nghe ra gì ở từng lượt

Không hạ nhiễu mạnh: mục đích là NGƯỜI nghe để đối chiếu, hạ mạnh sẽ nuốt mất
chính những chữ đang cần kiểm.

    python scripts/nghe_lai_tieng_khach.py
    python scripts/nghe_lai_tieng_khach.py --file logs/tieng_khach/khach.wav
"""

import argparse
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

RA = PROJECT / "logs" / "nghe_lai"
MUC_DICH = 10 ** (-15.0 / 20)      # -15 dBFS RMS, ngang tiếng F5


def chuan_muc(x: np.ndarray, nguong_im: float = 0.02) -> np.ndarray:
    """Kéo phần CÓ TIẾNG lên -15 dBFS. Đo RMS trên phần có tiếng thôi, không thì
    quãng lặng dài kéo tụt số đo và câu ngắn bị đẩy vỡ."""
    manh = np.abs(x) > nguong_im * np.abs(x).max()
    rms = float(np.sqrt((x[manh] ** 2).mean())) if manh.any() else 0.0
    if rms < 1e-6:
        return x
    y = x * (MUC_DICH / rms)
    dinh = float(np.abs(y).max())
    return y / dinh * 0.97 if dinh > 0.97 else y      # chặn vỡ, không nén


def ghi(p: Path, x: np.ndarray, sr: int):
    p.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(PROJECT / "logs/tieng_khach/khach_nói.wav"))
    ap.add_argument("--le", type=float, default=0.25,
                    help="lấy dư mỗi đầu bao nhiêu giây, kẻo cụt chữ đầu/cuối")
    a = ap.parse_args()

    from soi_tung_luot import cat_luot

    from backend.services import phone_call_service as PS

    f = Path(a.file)
    with wave.open(str(f)) as w:
        sr = w.getframerate()
        x = (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
             .astype(np.float32) / 32768.0)

    luot, nen, nguong = cat_luot(x, sr, PS)
    print(f"\n  {f.name}: {len(x)/sr:.1f}s @ {sr}Hz | {len(luot)} lượt "
          f"| nền {nen:.0f}, ngưỡng {nguong:.0f}")
    truoc = 20 * np.log10(float(np.sqrt((x[np.abs(x) > 0.02 * np.abs(x).max()] ** 2).mean())) + 1e-9)
    print(f"  mức gốc {truoc:.1f} dBFS -> chuẩn về -15.0 dBFS "
          f"(tiếng F5 để so: -14.9)\n")

    RA.mkdir(parents=True, exist_ok=True)
    for p in RA.glob("*"):
        p.unlink()
    ghi(RA / "0_ca_bang_ghi.wav", chuan_muc(x), sr)

    le = int(a.le * sr)
    dong = []
    for i, (bd, kt, talk, du_dai) in enumerate(luot, 1):
        seg = x[max(0, bd - le):min(len(x), kt + le)]
        ghi(RA / f"luot_{i}.wav", chuan_muc(seg), sr)
        print(f"  lượt {i}: {bd/sr:5.1f}-{kt/sr:5.1f}s  ({talk}ms tiếng)"
              f"{'' if du_dai else '   [ngắn hơn MIN_TURN_MS]'}")
        dong.append(f"lượt {i}: {bd/sr:.1f}-{kt/sr:.1f}s, {talk}ms tiếng")

    (RA / "ban_chu.txt").write_text(
        f"{f.name}\nmức gốc {truoc:.1f} dBFS, đã kéo lên -15 dBFS\n\n"
        + "\n".join(dong)
        + "\n\nNghe từng lượt rồi ghi lại anh THỰC SỰ nói gì, để đối chiếu với\n"
          "bản máy nghe ra trong logs/tieng_that/ban_chu.txt\n", encoding="utf-8")

    print(f"\n  {RA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
