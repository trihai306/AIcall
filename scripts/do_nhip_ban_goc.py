"""Do NHIP NOI THAT cua nguoi thu, tren TOAN BO ban thu goc - roi chinh F5 theo.

Vi sao khong lay tu doan mau 5 giay: mot doan 5 giay chi la mot lat cat, co the
roi vao cho nguoi ta noi nhanh hoac cham bat thuong. Chinh vi the ma giong cu
(clip 2.21s) do ra 297 am tiet/phut trong khi cac clip khac cat tu CUNG BAN THU
lai cho 211-289. Lay tren ca ban thu moi ra con so that.

Do hai kieu, va hai con so nay khac nhau nhieu:
  - nhip THO  : am tiet / tong thoi gian  (co tinh ca luc nghi giua cau)
  - nhip RONG : am tiet / thoi gian CO TIENG  (bo het khoang lang)

F5 sinh ra tieng gan nhu lien tuc, it nghi, nen phai so voi nhip RONG. Lay nham
nhip tho thi se chinh cho AI noi cham hon nguoi that.

Chay TREN MAY WIN (can may chu STT):
    .venv\\python.exe scripts\\do_nhip_ban_goc.py
    .venv\\python.exe scripts\\do_nhip_ban_goc.py --tep "C:/path/file.wav" --mau 20
"""
import argparse
import io
import json
import re
import statistics as st
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import soundfile as sf          # noqa: E402

STT = "http://127.0.0.1:8178/inference"
DAI_MAU = 20.0        # moi lat cat 20 giay
NGUONG_IM = 0.015     # duoi muc nay coi la im
KHUNG = 0.02          # cua so 20ms


def tim_ban_goc() -> Path | None:
    """Tim tep wav lon nhat tren Desktop. Ten co dau nen KHONG truyen qua SSH."""
    d = Path.home() / "Desktop"
    if not d.exists():
        return None
    ung = [p for p in d.glob("*.wav") if p.stat().st_size > 50 * 1024 * 1024]
    if not ung:
        return None
    # uu tien tep co chu "h" (giong Heu) chu khong phai "Giong Nam"
    heu = [p for p in ung if "nam" not in p.stem.lower()]
    return max(heu or ung, key=lambda p: p.stat().st_size)


def nghe_lai(x, sr) -> str:
    b = io.BytesIO()
    sf.write(b, x, sr, format="WAV", subtype="PCM_16")
    bd = b"----x"
    body = (b"--" + bd + b"\r\nContent-Disposition: form-data; name=\"file\"; "
            b"filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
            + b.getvalue() + b"\r\n--" + bd + b"--\r\n")
    r = urllib.request.Request(
        STT, data=body,
        headers={"Content-Type": "multipart/form-data; boundary=----x"})
    return json.loads(urllib.request.urlopen(r, timeout=300).read()).get("text", "").strip()


def am_tiet(s: str) -> int:
    return len([t for t in re.split(r"\s+", s.strip()) if re.search(r"\w", t)])


def giay_co_tieng(x: np.ndarray, sr: int) -> float:
    n_khung = max(1, int(sr * KHUNG))
    n = len(x) // n_khung
    if n == 0:
        return len(x) / sr
    to = np.array([np.abs(x[i*n_khung:(i+1)*n_khung]).max() for i in range(n)])
    return float((to >= NGUONG_IM).sum() * KHUNG)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tep", default=None)
    ap.add_argument("--mau", type=int, default=14, help="lay bao nhieu lat cat")
    a = ap.parse_args()

    p = Path(a.tep) if a.tep else tim_ban_goc()
    if p is None or not p.exists():
        print("  khong tim thay ban thu goc tren Desktop")
        return 1

    info = sf.info(str(p))
    tong = info.frames / info.samplerate
    print(f"\n  tep      : {p.name}")
    print(f"  dai      : {tong/60:.1f} phut   {info.samplerate} Hz   {info.channels} kenh\n")

    # Rai deu cac lat cat, bo 5% dau va cuoi (thuong la im lang hoac gioi thieu)
    dau, cuoi = tong * 0.05, tong * 0.95
    moc = np.linspace(dau, cuoi - DAI_MAU, a.mau)

    print(f"  {'moc':>8} {'am tiet':>8} {'co tieng':>9} {'nhip THO':>10} {'nhip RONG':>11}")
    print("  " + "-" * 54)
    tho, rong = [], []
    for m in moc:
        i = int(m * info.samplerate)
        n = int(DAI_MAU * info.samplerate)
        x, sr = sf.read(str(p), start=i, frames=n, dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
        t = nghe_lai(x, sr)
        at = am_tiet(t)
        ct = giay_co_tieng(x, sr)
        if at < 5 or ct < 3:            # lat cat gan nhu im, bo qua
            print(f"  {m/60:>7.1f}p {at:>8} {ct:>8.1f}s   (bo qua - qua it tieng)")
            continue
        a_tho, a_rong = at / DAI_MAU * 60, at / ct * 60
        tho.append(a_tho); rong.append(a_rong)
        print(f"  {m/60:>7.1f}p {at:>8} {ct:>8.1f}s {a_tho:>9.0f} {a_rong:>10.0f}")

    if not rong:
        print("\n  khong lat cat nao dung duoc")
        return 1

    print("  " + "-" * 54)
    print(f"\n  NHIP THO  trung vi {st.median(tho):.0f} am tiet/phut"
          f"   (khoang {min(tho):.0f}-{max(tho):.0f})")
    print(f"  NHIP RONG trung vi {st.median(rong):.0f} am tiet/phut"
          f"   (khoang {min(rong):.0f}-{max(rong):.0f})")
    print(f"\n  => Chinh F5 theo NHIP RONG: {st.median(rong):.0f} am tiet/phut")
    print("     (F5 sinh tieng gan nhu lien tuc nen phai so voi nhip khong tinh")
    print("      khoang lang; lay nhip tho se lam AI noi cham hon nguoi that.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
