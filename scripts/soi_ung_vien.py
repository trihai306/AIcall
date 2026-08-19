"""Soi bộ tách/chấm đoạn mẫu trên BẢN NGHE ĐÃ CẤT - không nghe lại.

Nghe hết bản ghi 20 phút mất ~4 phút, mà khâu hay phải chỉnh là tách/chấm.
Script này nạp `<ten>.stt.json` rồi chạy lại tách + chấm trong vài giây, nên
sửa ngưỡng xong là biết ngay ăn hay không.

    .venv\\python.exe scripts\\soi_ung_vien.py heu_goc --tim "tự ti"
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from backend.services.chon_doan_mau import (DAI_MAX, DAI_MIN, TIEU_TU,  # noqa
                                            co_tieu_tu, diem, gon,
                                            tach_don_vi)

KHO = Path(__file__).resolve().parents[1] / "models" / "tts" / "nguon" / ".phan_tich"


def dump_quanh(doan, moc, truoc=8, sau=14):
    """In mốc từng chữ quanh một vị trí - để thấy khe im thật, đừng đoán."""
    tu = [w for d in doan for w in (d.get("words") or [])]
    tu.sort(key=lambda w: w.get("start", 0.0))
    try:                                   # `moc` là MỐC GIÂY
        giay = float(moc)
        i = max(0, min(range(len(tu)), key=lambda k: abs(tu[k].get("start", 0) - giay)))
        moc_tu = tu[i].get("word", "")
    except ValueError:
        moc_tu = None
    for i, w in enumerate(tu):
        if moc_tu is not None and w is not tu[i]:
            pass
        if (moc_tu is None and gon(w.get("word", "")) == gon(moc)) or \
           (moc_tu is not None and abs(w.get("start", 0) - float(moc)) < 0.6):
            for x, y in zip(tu[max(0, i - truoc):i + sau], tu[max(0, i - truoc) + 1:i + sau + 1]):
                khe = y.get("start", 0) - x.get("end", 0)
                co = "  <-- khe" if khe > 0.15 else ""
                print(f"    {x.get('start',0):8.2f}-{x.get('end',0):.2f} "
                      f"{x.get('word',''):<14} khe sau {khe*1000:5.0f}ms{co}")
            return
    print(f"    không thấy chữ \"{moc}\"")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ten")
    ap.add_argument("--tim", default="", help="chuỗi cần tìm trong lời")
    ap.add_argument("--so", type=int, default=25)
    ap.add_argument("--moc", default="", help="in mốc từng chữ quanh chữ này")
    a = ap.parse_args()

    doan = json.loads((KHO / f"{a.ten}.stt.json").read_text(encoding="utf-8"))
    tu = [w for d in doan for w in (d.get("words") or [])]
    print(f"  {len(doan)} đoạn STT, {len(tu)} từ")

    # Chuỗi cần tìm có nằm trong BẢN NGHE không? Nếu không thì lỗi ở khâu nghe,
    # không phải khâu tách - đừng chỉnh bộ tách cho phí công.
    if a.tim:
        het = gon(" ".join(w.get("word", "") for w in tu))
        print(f"  \"{a.tim}\" trong bản nghe: "
              f"{'CÓ' if gon(a.tim) in het else 'KHÔNG'}")

    if a.moc:
        print(f"\n  mốc từng chữ quanh \"{a.moc}\":")
        dump_quanh(doan, a.moc)
        print()

    dv = tach_don_vi(doan)
    print(f"  tách được {len(dv)} đơn vị dài {DAI_MIN}-{DAI_MAX}s\n")

    ket = [d for d in dv if co_tieu_tu(d["loi"])]
    print(f"  kết bằng tiểu từ thật {sorted(TIEU_TU)}: {len(ket)} đoạn")
    for d in ket[:a.so]:
        print(f"    {d['a']:7.2f}s {d['dai']:.2f}s  {d['loi'][:78]}")

    if a.tim:
        print(f"\n  đơn vị có chứa \"{a.tim}\":")
        thay = [d for d in dv if gon(a.tim) in gon(d["loi"])]
        if not thay:
            print("    KHÔNG CÓ - bộ tách không đẻ ra đơn vị nào chứa chuỗi này.")
            # Chuỗi nằm ở đâu trong bản ghi? Cho biết để soi tay.
            for i, w in enumerate(tu):
                if gon(a.tim).split()[0] == gon(w.get("word", "")):
                    quanh = " ".join(x.get("word", "") for x in tu[max(0, i - 6):i + 12])
                    print(f"    quanh {w.get('start', 0):.2f}s: {quanh}")
                    break
        for d in thay:
            print(f"    {d['a']:7.2f}s {d['dai']:.2f}s  điểm {diem({**d, 'co_tieu_tu': co_tieu_tu(d['loi']), 'le_phep': True, 'h1h2': 6.0, 'nen': -60.0}):.2f}")
            print(f"      {d['loi']}")


if __name__ == "__main__":
    main()