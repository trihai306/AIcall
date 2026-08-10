"""Cho STT nghe lai TUNG MANH cua ban ghi roi so voi chu AI that su noi.

Day la phep thu re nhat va bat duoc thu ma do pho, do bien do, do quang dut deu
KHONG bat duoc - da thu ca bon va deu bao "sach" trong khi khach nghe ro. Chinh
nguoi dung nghi ra cach nay.

Khac `soi_ban_ghi.py`: script do soi TIENG (quang lang, bien do). Script nay soi
CHU - AI doc co dung khong, co lot chu la khong, co nuot chu khong.

So voi chu DA CHUAN HOA (`normalize_for_tts`) chu khong phai chu tho: F5 nhan ban
da bung viet tat va doc so thanh chu, nen so voi ban tho se bao sai hang loat.

Chay TREN MAY WIN, sau khi da chay ghi_hoi_thoai_that.py:
    .venv\\python.exe scripts\\nghe_lai_ban_ghi.py
"""
import argparse
import difflib
import io
import json
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import soundfile as sf          # noqa: E402

from backend.pipeline.text_normalizer import normalize_for_tts  # noqa: E402

STT = "http://127.0.0.1:8178/inference"


def nghe(x, sr) -> str:
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


def chuan(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", default="C:/tmp/hoithoai/hoi_thoai.wav")
    ap.add_argument("--bang", default="C:/tmp/hoithoai/bang_tra.txt")
    ap.add_argument("--nguong", type=float, default=80.0,
                    help="dưới % giống này thì coi là có vấn đề")
    a = ap.parse_args()

    x, sr = sf.read(a.wav, dtype="float32")
    if x.ndim > 1:
        x = x.mean(axis=1)

    hang = []
    for l in Path(a.bang).read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s+(\d):([\d.]+) - (\d):([\d.]+)\s+(\S+)\s+(.*?)\s*(<==.*)?$", l)
        if m:
            t0 = int(m.group(1)) * 60 + float(m.group(2))
            t1 = int(m.group(3)) * 60 + float(m.group(4))
            chu = m.group(6).strip()
            if chu and chu != "[cau dem]":
                hang.append((t0, t1, m.group(5), chu))

    print(f"\n  {len(hang)} mảnh có chữ (bỏ câu đệm)\n")
    print(f"  {'mốc':>7} {'giống':>7}  chữ AI nói  |  STT nghe lại")
    print("  " + "-" * 76)

    diem, xau = [], []
    for t0, t1, nhan, chu in hang:
        seg = x[int(t0 * sr):int(t1 * sr)]
        if len(seg) < sr * 0.15:
            continue
        can = normalize_for_tts(chu)
        t = nghe(seg, sr)
        g = difflib.SequenceMatcher(None, chuan(can).split(), chuan(t).split()).ratio() * 100
        diem.append(g)
        if g < a.nguong:
            xau.append((t0, g, can, t))
        print(f"  {int(t0)//60}:{t0 - 60*(int(t0)//60):05.2f} {g:>6.0f}%  {can[:32]:<32} | {t[:32]}")

    print("  " + "-" * 76)
    print(f"\n  giống trung bình : {np.mean(diem):.0f}%")
    print(f"  mảnh dưới {a.nguong:.0f}%    : {len(xau)}/{len(diem)}")
    if xau:
        print(f"\n  CÁC MẢNH ĐÁNG NGỜ")
        for t0, g, can, t in sorted(xau, key=lambda z: z[1])[:10]:
            print(f"    {int(t0)//60}:{t0 - 60*(int(t0)//60):05.2f}  {g:.0f}%")
            print(f"      nói : {can[:62]}")
            print(f"      nghe: {t[:62]}")


if __name__ == "__main__":
    main()
