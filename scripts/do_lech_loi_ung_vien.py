"""Ngưỡng lệch lời nên đặt ở đâu? Đo phân bố thật thay vì đoán.

Bằng chứng hiện có chỉ có hai mốc: đoạn mẫu lệch 0% chạy tốt, lệch 12,5% cho
WER đầu ra 160%. Khoảng giữa CHƯA AI ĐO. Ngưỡng 5% đang dùng là số đoán, mà nó
đang loại 21/24 ứng viên trên bản ghi heu_goc - đủ nhiều để đáng đo cho ra nhẽ.

Script cắt đúng các ứng viên mà đường thật sẽ kiểm, cho STT nghe lại từng cái,
rồi in phân bố lệch lời. Nếu có khe rõ giữa nhóm sạch và nhóm hỏng thì đặt
ngưỡng vào khe đó; không có khe thì phải thừa nhận là ngưỡng tuỳ chọn.

    .venv\\python.exe scripts\\do_lech_loi_ung_vien.py heu_goc
"""
import argparse
import io
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np          # noqa: E402
import soundfile as sf      # noqa: E402

from backend.services.chon_doan_mau import (cer, cham_diem,  # noqa: E402
                                            dep_de_len, nan_moc, tach_don_vi,
                                            xep_hang)

GOC = Path(__file__).resolve().parents[1]
NGUON = GOC / "models" / "tts" / "nguon"
KHO = NGUON / ".phan_tich"
STT = "http://127.0.0.1:8178/inference"


def nghe_lai(x, sr) -> str:
    b = io.BytesIO()
    sf.write(b, x, sr, format="WAV", subtype="PCM_16")
    bd = b"----x"
    body = (b"--" + bd + b"\r\nContent-Disposition: form-data; name=\"file\"; "
            b"filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
            + b.getvalue() + b"\r\n--" + bd + b"--\r\n")
    r = urllib.request.Request(STT, data=body,
                               headers={"Content-Type": "multipart/form-data; boundary=----x"})
    try:
        return json.loads(urllib.request.urlopen(r, timeout=180).read()).get("text", "").strip()
    except Exception as e:
        return f"[[lỗi: {e}]]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ten")
    ap.add_argument("--so", type=int, default=24)
    a = ap.parse_args()

    doan = json.loads((KHO / f"{a.ten}.stt.json").read_text(encoding="utf-8"))
    x, sr = sf.read(str(NGUON / f"{a.ten}.wav"), dtype="float32")
    if x.ndim > 1:
        x = x.mean(axis=1)

    uv = tach_don_vi(doan)
    for d in uv:
        d["m_a"] = nan_moc(x, sr, int(d["a"] * sr))
        d["m_b"] = nan_moc(x, sr, int(d["b"] * sr))
        d.update(cham_diem(x[d["m_a"]:d["m_b"]], sr, d["loi"], d["loi"]))
    tot = dep_de_len(xep_hang(uv))[:a.so]
    print(f"  {len(uv)} ứng viên, kiểm lời {len(tot)} cái đứng đầu\n")

    ket = []
    for d in tot:
        nghe = nghe_lai(x[d["m_a"]:d["m_b"]], sr)
        ket.append((cer(d["loi"], nghe), d, nghe))

    ket.sort(key=lambda k: k[0])
    print(f"  {'lệch':>6} {'dài':>5} {'tiểu từ':>7}  lời")
    print("  " + "-" * 96)
    for c, d, nghe in ket:
        print(f"  {c*100:5.1f}% {d['dai']:5.2f} {'CÓ' if d['co_tieu_tu'] else '-':>7}  {d['loi'][:70]}")
        if c > 0.05:
            print(f"         nghe lại: {nghe[:70]}")

    v = [c for c, _, _ in ket]
    print("\n  phân bố:")
    for lo, hi in [(0, .02), (.02, .05), (.05, .08), (.08, .12), (.12, .25), (.25, 9)]:
        n = sum(1 for c in v if lo <= c < hi)
        print(f"    {lo*100:5.1f}-{hi*100:5.1f}%  {'#' * n} {n}")
    # Khe rộng nhất giữa hai giá trị liền nhau - chỗ đó mới là ngưỡng tự nhiên.
    if len(v) > 1:
        khe = max(zip(v, v[1:]), key=lambda p: p[1] - p[0])
        print(f"\n  khe rộng nhất: {khe[0]*100:.1f}% -> {khe[1]*100:.1f}% "
              f"(rộng {(khe[1]-khe[0])*100:.1f} điểm)")


if __name__ == "__main__":
    main()
