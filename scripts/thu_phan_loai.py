"""Phân loại 7 câu kiểm tra để xác nhận kho tình huống đúng.

Chay:
    .venv\\python.exe scripts\\thu_phan_loai.py

Bắt buộc sau khi đổi vi_du trong data/tinh_huong_seed.json và
nạp lại bằng nap_tinh_huong.py. Câu 2 phải KHÔNG ra khach_noi_khong_ro,
câu 6 phải ra khach_noi_khong_ro.
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from backend.config import settings
from backend.services.filler_situation import NGUONG_DIEM, chon_tinh_huong, chuan_hoa
from backend.services.rag_service import RAGService

CAU_KIEM_TRA = [
    "lai suat vay tin chap ben em bao nhieu mot nam",
    "u em noi di",
    "the vay toi da duoc bao nhieu tien",
    "vay tin chap thi can nhung gi",
    "duoc roi mai anh goi lai cho em nhe",
    "a lo nghe khong ro",
    "anh dang ban lam",
]

# Câu gốc tiếng Việt để hiển thị (truyền bằng file để tránh lỗi encoding CLI)
CAU_VIET = [
    "lãi suất vay tín chấp bên em bao nhiêu một năm",
    "ừ em nói đi",
    "thế vay tối đa được bao nhiêu tiền",
    "vay tín chấp thì cần những gì",
    "được rồi mai anh gọi lại cho em nhé",
    "a lô nghe không rõ",
    "anh đang bận lắm",
]


def main() -> int:
    print(f"Nguong diem: {NGUONG_DIEM}")

    # Nap kho vector tu DB
    conn = sqlite3.connect(str(settings.db_file))
    rows = conn.execute(
        "SELECT id, vi_du FROM tinh_huong WHERE bat=1"
    ).fetchall()
    conn.close()

    rag = RAGService()
    rag.load()

    kho_vec: dict = {}
    for id_th, vi_du_json in rows:
        vi_du = json.loads(vi_du_json)
        if not vi_du:
            continue
        vecs = chuan_hoa(rag.embed(vi_du))
        kho_vec[id_th] = vecs

    print(f"Nap {len(kho_vec)} tinh huong tu DB")
    print()

    co_loi = False
    for i, (cau_ascii, cau_viet) in enumerate(zip(CAU_KIEM_TRA, CAU_VIET), 1):
        # Dung ban ASCII de embed tranh loi codec; embed bang van ban goc tot hon
        # nhung day la ban du phong an toan tren moi terminal
        q = chuan_hoa(rag.embed([cau_ascii]))[0]
        id_th, diem = chon_tinh_huong(q, kho_vec)
        ket = id_th or "(none)"

        # Kiem tra cac rang buoc bat buoc
        if i == 2 and id_th == "khach_noi_khong_ro":
            nhan = "LOI!"
            co_loi = True
        elif i == 6 and id_th != "khach_noi_khong_ro":
            nhan = "LOI!"
            co_loi = True
        else:
            nhan = "ok"

        print(f"  [{i}] {nhan:4s} {cau_viet[:50]:50s} -> {ket:30s} {diem:.3f}")

    print()
    if co_loi:
        print("=> CO LOI: kiem tra lai vi_du trong data/tinh_huong_seed.json")
        return 1
    print("=> Tat ca rang buoc dat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
