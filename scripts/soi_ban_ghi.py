"""Soi mot ban ghi hoi thoai va bao MOI khuyet tat da biet cach do.

Toi khong nghe duoc, nen phai do. Gom tat ca cac phep do da tung bat duoc loi
that trong du an nay, chay mot luot tren mot tep wav:

  1. QUANG LANG DAI    - tren 300ms giua cac doan co tieng. Cho dut hoac F5 bia.
  2. AM RAC / LAP CHU  - cho STT nghe lai tung doan, so voi ban chep chung.
  3. VUOT TRAN         - mau bi xen dinh (bien do cham 1.0).
  4. LECH MUC          - doan nay to hon doan kia bao nhieu.
  5. NHIP TUNG DOAN    - am tiet/phut cua tung doan; lech nhau nhieu = troi.
  6. IM HOAN TOAN      - doan chi co nhieu nen, khong co tieng.

Chay TREN MAY WIN (can may chu STT):
    .venv\\python.exe scripts\\soi_ban_ghi.py C:\\tmp\\hoithoai\\hoi_thoai.wav
"""
import argparse
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import soundfile as sf          # noqa: E402

STT = "http://127.0.0.1:8178/inference"
NGUONG_IM, KHUNG = 0.015, 0.02
LANG_DAI_MS = 300


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
    try:
        return json.loads(urllib.request.urlopen(r, timeout=300).read()).get("text", "").strip()
    except Exception as e:
        raise RuntimeError(f"STT khong goi duoc: {e}") from e


def am_tiet(s):
    return len([t for t in re.split(r"\s+", s.strip()) if re.search(r"\w", t)])


def phan_doan(x, sr):
    """Tach thanh cac doan CO TIENG, cach nhau boi quang lang >= 300ms."""
    n = max(1, int(sr * KHUNG))
    k = len(x) // n
    to = np.array([np.abs(x[i*n:(i+1)*n]).max() for i in range(k)])
    co = to >= NGUONG_IM
    doan, lang, i = [], [], 0
    while i < k and not co[i]:
        i += 1
    while i < k:
        b = i
        while i < k and co[i]:
            i += 1
        doan.append((b * KHUNG, i * KHUNG))
        j = i
        while i < k and not co[i]:
            i += 1
        if i < k and (i - j) * KHUNG * 1000 >= LANG_DAI_MS:
            lang.append((j * KHUNG, (i - j) * KHUNG * 1000))
    return doan, lang


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tep")
    a = ap.parse_args()

    p = Path(a.tep)
    x, sr = sf.read(str(p), dtype="float32")
    if x.ndim > 1:
        x = x.mean(axis=1)

    print(f"\n  tep : {p.name}")
    print(f"  dai : {len(x)/sr:.1f}s   {sr} Hz")

    nghe_lai(np.zeros(int(sr*0.5), dtype=np.float32), sr)   # kiem STT song

    doan, lang = phan_doan(x, sr)
    print(f"\n  [1] QUANG LANG > {LANG_DAI_MS}ms giua cac doan co tieng")
    if not lang:
        print("      khong co - DAT")
    for t, d in lang:
        print(f"      {t:6.2f}s  im {d:5.0f}ms")

    print(f"\n  [2..6] SOI TUNG DOAN CO TIENG ({len(doan)} doan)")
    print(f"      {'moc':>7} {'dai':>6} {'dinh':>6} {'RMS dB':>8} {'am/phut':>8}  ban chep")
    print("      " + "-" * 78)
    nhips, dinhs, tran, im = [], [], 0, 0
    for b, e in doan:
        seg = x[int(b*sr):int(e*sr)]
        if len(seg) < sr * 0.15:
            continue
        dinh = float(np.abs(seg).max())
        rms = 20*np.log10(max(float(np.sqrt((seg**2).mean())), 1e-9))
        t = nghe_lai(seg, sr)
        n = am_tiet(t)
        nhip = n / (len(seg)/sr) * 60 if n else 0
        if n:
            nhips.append(nhip)
        dinhs.append(dinh)
        tran += dinh > 0.999
        if not n:
            im += 1
        co = ""
        if dinh > 0.999:
            co += " XEN DINH"
        if not n:
            co += " KHONG RA CHU"
        print(f"      {b:6.2f}s {e-b:5.2f}s {dinh:6.2f} {rms:8.1f} {nhip:8.0f}"
              f"  {t[:42]}{co}")

    print("      " + "-" * 78)
    print(f"\n  TONG KET")
    print(f"    quang lang > {LANG_DAI_MS}ms : {len(lang)}")
    print(f"    doan bi xen dinh     : {tran}/{len(doan)}")
    print(f"    doan khong ra chu    : {im}/{len(doan)}")
    if nhips:
        print(f"    nhip cac doan        : {min(nhips):.0f} - {max(nhips):.0f} am tiet/phut"
              f"   (trung vi {np.median(nhips):.0f})")
        lech = (max(nhips) - min(nhips)) / np.median(nhips) * 100
        print(f"    chenh lech nhip      : {lech:.0f}%"
              f"{'  <== TROI, cac doan doc khong deu' if lech > 60 else ''}")
    if dinhs:
        print(f"    dinh cao nhat        : {max(dinhs):.2f}"
              f"   thap nhat {min(dinhs):.2f}")


if __name__ == "__main__":
    main()
