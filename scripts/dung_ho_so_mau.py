"""Dựng file hồ sơ khách MẪU với bộ cột đầy đủ hơn (tài chính + lịch sử gọi).

Vì sao mỗi khách một DÒNG chứ không phải một FILE/DB riêng: `data_source_service`
tra theo khoá `so_dien_thoai` nên đã là O(1) - một dòng lấy ra ngay, không quét.
Tách thành nhiều file chỉ thêm việc mở/đóng chứ không nhanh hơn.

Chỗ thật sự phải dè chừng là ĐỘ DÀY của khối đưa vào prompt: chú thích trong
`data_source_service.dung_ngu_canh` ghi lại rằng mô hình 3B KHÔNG nhặt được số ra
khỏi dòng dày đặc. Bộ cột dưới đây gấp ba bộ cũ, nên phần dùng nó phải lọc theo
câu hỏi chứ đừng đổ hết vào prompt.

    python scripts/dung_ho_so_mau.py
    python scripts/dung_ho_so_mau.py --ghi-de
"""

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DICH = PROJECT / "data" / "nguon" / "ho_so_khach.db"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Ba nhóm, cố ý tách rõ vì chúng được dùng khác nhau:
#   định danh  -> quyết định xưng hô, dùng ngay từ lời chào
#   tài chính  -> câu hỏi về SỐ, phải trả lời chính xác tuyệt đối
#   tương tác  -> để AI không hỏi lại thứ khách đã nói lần trước
COT = [
    # --- định danh ---
    ("so_dien_thoai", "TEXT PRIMARY KEY"),
    ("ho_ten", "TEXT"),
    ("gioi_tinh", "TEXT"),          # nam / nu  -> khỏi phải đoán bằng cao độ giọng
    ("san_pham", "TEXT"),
    ("ma_hop_dong", "TEXT"),
    # --- tài chính ---
    ("du_no", "TEXT"),
    ("ky_han_con", "TEXT"),
    ("ngay_den_han", "TEXT"),
    ("tra_hang_thang", "TEXT"),
    ("lai_suat_dang_ap_dung", "TEXT"),
    ("han_muc_da_duyet", "TEXT"),
    ("nhom_no", "TEXT"),
    # --- lịch sử tương tác ---
    ("so_lan_da_goi", "TEXT"),
    ("ket_qua_lan_truoc", "TEXT"),
    ("ly_do_tu_choi", "TEXT"),
    ("khung_gio_nen_goi", "TEXT"),
    ("ghi_chu", "TEXT"),
]

MAU = [
    # Số 0396130621 khớp lại với danh bạ: trước đây hồ sơ ghi "Chị Lan / thẻ tín
    # dụng" trong khi danh bạ ghi "Khách thử / vay tín chấp", nên AI gọi sai tên
    # và tư vấn sai sản phẩm ngay trong các cuộc gọi thử.
    {
        "so_dien_thoai": "0396130621", "ho_ten": "Anh Hải", "gioi_tinh": "nam",
        "san_pham": "vay tín chấp", "ma_hop_dong": "TC-2024-88123",
        "du_no": "142.500.000 đồng", "ky_han_con": "21 tháng",
        "ngay_den_han": "15/09/2026", "tra_hang_thang": "7.850.000 đồng",
        "lai_suat_dang_ap_dung": "8.5%/năm", "han_muc_da_duyet": "300.000.000 đồng",
        "nhom_no": "Nhóm 1 - đủ tiêu chuẩn",
        "so_lan_da_goi": "3", "ket_qua_lan_truoc": "quan tâm, hẹn gọi lại",
        "ly_do_tu_choi": "", "khung_gio_nen_goi": "9h-11h các ngày trong tuần",
        "ghi_chu": "Đang cân nhắc vay thêm để sửa nhà",
    },
    {
        "so_dien_thoai": "0833816298", "ho_ten": "Chị Lan", "gioi_tinh": "nu",
        "san_pham": "thẻ tín dụng", "ma_hop_dong": "TD-2025-40917",
        "du_no": "8.300.000 đồng", "ky_han_con": "—",
        "ngay_den_han": "02/09/2026", "tra_hang_thang": "tối thiểu 415.000 đồng",
        "lai_suat_dang_ap_dung": "2.15%/tháng", "han_muc_da_duyet": "60.000.000 đồng",
        "nhom_no": "Nhóm 1 - đủ tiêu chuẩn",
        "so_lan_da_goi": "1", "ket_qua_lan_truoc": "không nghe máy",
        "ly_do_tu_choi": "", "khung_gio_nen_goi": "sau 17h",
        "ghi_chu": "Đã mở thẻ 03/2025, chưa dùng hết hạn mức",
    },
    {
        "so_dien_thoai": "0912345678", "ho_ten": "Anh Tuấn", "gioi_tinh": "nam",
        "san_pham": "vay mua nhà", "ma_hop_dong": "MN-2023-11204",
        "du_no": "1.850.000.000 đồng", "ky_han_con": "168 tháng",
        "ngay_den_han": "20/08/2026", "tra_hang_thang": "18.200.000 đồng",
        "lai_suat_dang_ap_dung": "9.2%/năm", "han_muc_da_duyet": "2.000.000.000 đồng",
        "nhom_no": "Nhóm 2 - cần chú ý",
        "so_lan_da_goi": "5", "ket_qua_lan_truoc": "từ chối",
        "ly_do_tu_choi": "đang khó khăn tài chính",
        "khung_gio_nen_goi": "12h-13h", "ghi_chu": "Trễ hạn 1 kỳ tháng 6",
    },
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ghi-de", action="store_true",
                    help="xoá bảng cũ rồi dựng lại (mất dữ liệu đang có)")
    a = ap.parse_args()

    DICH.parent.mkdir(parents=True, exist_ok=True)
    d = sqlite3.connect(DICH)
    cu = d.cursor()

    co = {r[1] for r in cu.execute("PRAGMA table_info(ho_so)")} \
        if cu.execute("select name from sqlite_master where type='table' and name='ho_so'"
                      ).fetchone() else set()

    if co and a.ghi_de:
        cu.execute("DROP TABLE ho_so")
        co = set()

    if not co:
        cu.execute("CREATE TABLE ho_so (" +
                   ", ".join(f"{t} {k}" for t, k in COT) + ")")
        print(f"đã tạo bảng ho_so với {len(COT)} cột")
    else:
        # Thêm dần cột mới, GIỮ dữ liệu đang có. Người dùng có thể đã nhập hồ sơ
        # thật vào đây rồi - dựng lại từ đầu là xoá mất.
        for ten, kieu in COT:
            if ten not in co:
                cu.execute(f"ALTER TABLE ho_so ADD COLUMN {ten} {kieu.replace(' PRIMARY KEY','')}")
                print(f"  thêm cột {ten}")

    # XOÁ THEO SỐ rồi mới chèn, đừng tin `INSERT OR REPLACE`: bảng có sẵn trên
    # máy thật được tạo KHÔNG có khoá chính, nên `OR REPLACE` không thay thế gì
    # cả và mỗi lần chạy lại đẻ thêm một dòng trùng số. Đã mắc: chạy một lần ra
    # 5 dòng cho 3 hồ sơ, và tra cứu bốc phải dòng cũ - tức AI đọc sai hồ sơ
    # khách mà không có dấu hiệu gì.
    ten_cot = [t for t, _ in COT]
    for r in MAU:
        cu.execute("DELETE FROM ho_so WHERE so_dien_thoai = ?",
                   (r["so_dien_thoai"],))
        cu.execute(
            f"INSERT INTO ho_so ({','.join(ten_cot)}) "
            f"VALUES ({','.join('?' * len(ten_cot))})",
            [r.get(t, "") for t in ten_cot])

    # Chỉ mục DUY NHẤT: vừa tăng tốc đường nóng (tra theo số ở mỗi cuộc gọi),
    # vừa chặn hẳn việc số bị trùng lần sau. Dựng SAU khi đã dọn trùng.
    trung = cu.execute("select so_dien_thoai, count(*) c from ho_so "
                       "group by so_dien_thoai having c > 1").fetchall()
    if trung:
        print("  [CẢNH BÁO] còn số trùng, không tạo được chỉ mục duy nhất: "
              + ", ".join(f"{s} ({c} dòng)" for s, c in trung))
        cu.execute("CREATE INDEX IF NOT EXISTS idx_ho_so_sdt ON ho_so(so_dien_thoai)")
    else:
        cu.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ho_so_sdt ON ho_so(so_dien_thoai)")
    d.commit()

    n = cu.execute("select count(*) from ho_so").fetchone()[0]
    print(f"\n{DICH}")
    print(f"  {n} hồ sơ, {len(COT)} cột")
    for r in cu.execute("select so_dien_thoai, ho_ten, san_pham, du_no from ho_so"):
        print(f"   {r[0]}  {r[1]:<10} {r[2]:<14} {r[3]}")
    return 0


raise SystemExit(main())
