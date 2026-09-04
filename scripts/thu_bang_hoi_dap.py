"""Bảng hỏi-đáp có bắt được những câu mà tri thức cũ trượt không.

Chạy:
    .venv/bin/python scripts/thu_bang_hoi_dap.py

Các câu dưới đây là câu ĐÃ ĐO TRƯỢT ngày 2026-09-02 trên kho tình huống:
"cơ chế thế nào" 0.622 (dưới ngưỡng, khách nghe im lặng đầu lượt),
"vay như nào" rơi nhầm vào hoi_lai_suat 0.832.
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from backend.config import settings
from backend.services.bang_hoi_dap import bo_qua_khac_san_pham, doc_dong
from backend.services.filler_situation import chon_tinh_huong, chuan_hoa

# (câu khách nói, sản phẩm phiên, id mong đợi hoặc None = không được trúng bừa)
BO_THU = [
    ("cơ chế thế nào",            "vay tín chấp", "co_che_vay_chung"),
    ("vay như nào",               "vay tín chấp", "co_che_vay_chung"),
    ("thế vay ra sao",            "vay tín chấp", "co_che_vay_chung"),
    ("quy trình vay thế nào",     "vay tín chấp", "co_che_vay_chung"),
    ("cần chuẩn bị những gì",     "vay tín chấp", "can_nhung_gi"),
    ("phải có giấy tờ gì",        "vay tín chấp", "can_nhung_gi"),
    ("bên em có lợi gì không",    "vay tín chấp", "co_loi_gi_khong"),
    ("chi nhánh ở đâu",           "vay tín chấp", "ben_em_o_dau"),
    ("bên em ở đâu",              "",             "ben_em_o_dau"),
    # Không thuộc bảng: phải trượt chứ không được vơ bừa một dòng.
    ("lãi suất bao nhiêu phần trăm", "vay tín chấp", None),
    ("anh đang bận lắm",          "vay tín chấp", None),
]


def main() -> int:
    from backend.services.rag_service import RAGService
    conn = sqlite3.connect(str(settings.db_file))
    dong = {d["id"]: d for d in doc_dong(conn)}
    if not dong:
        print("Bang rong - chay scripts/nap_hoi_dap.py truoc")
        return 1
    rag = RAGService(); rag.load()
    kho = {ma: chuan_hoa(rag.embed(list(d["cau_hoi"]))) for ma, d in dong.items()}
    dieu_kien = {ma: d["san_pham"] for ma, d in dong.items()}
    print(f"Bang: {len(kho)} dong\n")

    dung = vo_bua = 0
    for cau, sp, mong in BO_THU:
        q = chuan_hoa(rag.embed([cau]))[0]
        ma, diem = chon_tinh_huong(q, kho, bo_qua=bo_qua_khac_san_pham(dieu_kien, sp))
        ok = (ma == mong)
        dung += ok
        if mong is None and ma is not None:
            vo_bua += 1
        print(f"{'OK ' if ok else 'SAI'} {cau!r:34} -> {str(ma):20} {diem:.3f}"
              f"{'' if ok else f'   (mong: {mong})'}")

    print(f"\nDung {dung}/{len(BO_THU)}   |   vo bua (khong thuoc bang ma van tra ve): {vo_bua}")
    dat = dung >= len(BO_THU) - 1 and vo_bua == 0
    print("=> DAT" if dat else "=> KHONG DAT")
    return 0 if dat else 1


if __name__ == "__main__":
    raise SystemExit(main())
