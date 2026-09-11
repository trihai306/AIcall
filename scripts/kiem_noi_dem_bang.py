"""Soi chỗ nối câu đệm -> câu đọc NGUYÊN VĂN của bảng hỏi-đáp, trên kho THẬT.

Chạy TRÊN MÁY WIN (cần bộ nhúng):
    .venv\\python.exe scripts\\kiem_noi_dem_bang.py

Câu nguyên văn phát bằng tiếng dựng sẵn nên không cắt chữ ở chỗ nối được, và câu
đệm được chọn TRƯỚC khi tra bảng. Chỗ duy nhất sửa được là câu mở đầu của tình
huống dẫn vào dòng đó. Script này phân loại CHÍNH câu hỏi của từng dòng bằng bộ
phân loại thật để biết khách sẽ nghe câu mở đầu nào trước câu nào, rồi báo:

  LẶP  câu mở đầu và 6 chữ đầu câu nguyên văn có chung chữ mang chủ đề
       ("Dạ về hồ sơ cần chuẩn bị thì," + "Mình chuẩn bị căn cước...")
  XEM  câu mở đầu hứa đi xem / tuỳ trường hợp, rồi câu nguyên văn khẳng định
       luôn ("Dạ hạn mức này còn tuỳ hồ sơ," + "Hạn mức này thuộc tốp cao...")

Chạy lại sau khi đổi ví dụ tình huống hoặc thêm dòng bảng hỏi-đáp, rồi cập nhật
`DO_PHAN_LOAI` trong `tests/test_mo_dau_truoc_cau_nguyen_van.py` theo cột "->".
Mâu thuẫn về NGHĨA ngoài hai loại trên thì máy không bắt được - đọc cột ghép.
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from backend.config import settings
from backend.services.filler_situation import NGUONG_CAU_DEM, chon_tinh_huong, chuan_hoa
from backend.services.rag_service import RAGService

_KHONG_CHU_DE = {
    "dạ", "vâng", "ạ", "em", "anh", "chị", "mình", "bên", "của", "về", "thì",
    "là", "này", "đó", "cho", "và", "đã", "rồi", "với", "xin", "phép",
}
_HUA_XEM = re.compile(r"\b(xem|kiểm tra|tuỳ|tùy)\b", re.I)


def _tu(s: str) -> set[str]:
    return {w for w in re.findall(r"\w+", s.lower()) if w not in _KHONG_CHU_DE}


def main() -> int:
    conn = sqlite3.connect(str(settings.db_file))
    th = {i: (json.loads(v), json.loads(m)) for i, v, m in conn.execute(
        "SELECT id, vi_du, mo_dau FROM tinh_huong WHERE bat=1")}
    rag = RAGService()
    rag.load()
    kho = {i: chuan_hoa(rag.embed(v)) for i, (v, _) in th.items() if v}

    loi = 0
    for ma, cau_hoi, tra_loi in conn.execute(
            "SELECT id, cau_hoi, tra_loi FROM hoi_dap WHERE bat=1"):
        dau = _tu(" ".join(tra_loi.split()[:6]))
        if ma in th:
            den = {ma: ["(dòng chê: đi theo tình huống cùng id)"]}
        else:
            den = {}
            for q in json.loads(cau_hoi):
                id_th, diem = chon_tinh_huong(chuan_hoa(rag.embed([q]))[0], kho,
                                              nguong=NGUONG_CAU_DEM)
                den.setdefault(id_th, []).append(f"{q} {diem:.2f}")
        print(f"\n== {ma}: {tra_loi[:60]!r}")
        for id_th, cac_q in den.items():
            print(f"   -> {id_th}  ({'; '.join(cac_q)})")
            if id_th is None:
                continue
            for m in th[id_th][1]:
                nhan = []
                if _tu(m) & dau:
                    nhan.append(f"LẶP {sorted(_tu(m) & dau)}")
                if _HUA_XEM.search(m):
                    nhan.append("XEM")
                loi += bool(nhan)
                print(f"      {'  '.join(nhan) or 'ok':12s} {m} {tra_loi[:40]}")
    print(f"\n{loi} chỗ nối có vấn đề")
    return 1 if loi else 0


if __name__ == "__main__":
    raise SystemExit(main())
