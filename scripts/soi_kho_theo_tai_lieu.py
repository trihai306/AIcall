"""Soi kho trả lời theo tài liệu sản phẩm, và diễn tập một lần đổi con số.

    python scripts/soi_kho_theo_tai_lieu.py                      # chỉ báo cáo
    python scripts/soi_kho_theo_tai_lieu.py --thu vay_tin_chap "7.9%" "8.5%"
    python scripts/soi_kho_theo_tai_lieu.py --ghi                # lập mẫu vào DB thật

Không có `--ghi` thì mọi thứ chạy trên BẢN SAO của `data/app.db` và của thư mục
`knowledge/products` trong thư mục tạm; kho thật và tài liệu thật không bị đụng.
`--ghi` chỉ thêm hai bảng phụ (`hoi_dap_mau`, `tai_lieu_cau_truc`), không sửa
một câu trả lời nào.
"""
import argparse
import os
import shutil
import sqlite3
import sys
import tempfile

GOC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, GOC)

from backend.pipeline import bang_du_kien as bdk          # noqa: E402
from backend.services import kho_theo_tai_lieu as kho     # noqa: E402


def main() -> int:
    # Bảng điều khiển Windows mặc định cp1252, in tiếng Việt là vỡ.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--thu", nargs=3, metavar=("SAN_PHAM", "CU", "MOI"),
                    help="diễn tập: thay chuỗi CU bằng MOI trong tài liệu của SAN_PHAM")
    ap.add_argument("--ghi", action="store_true", help="lập mẫu vào data/app.db thật")
    a = ap.parse_args()
    that = os.path.join(GOC, "data", "app.db")

    if a.ghi:
        conn = sqlite3.connect(that)
        kq = kho.lap_mau(conn, GOC)
        conn.close()
        print("ĐÃ GHI mẫu vào", that)
    else:
        tam = tempfile.mkdtemp(prefix="soi_kho_")
        shutil.copy(that, os.path.join(tam, "app.db"))
        shutil.copytree(os.path.join(GOC, "knowledge", "products"),
                        os.path.join(tam, "knowledge", "products"))
        conn = sqlite3.connect(os.path.join(tam, "app.db"))
        kq = kho.lap_mau(conn, tam)
    for ten in ("khong_co_so", "co_mau", "chep_cung_con_dung",
                "so_khong_co_trong_tai_lieu", "khong_gan_san_pham"):
        print(f"{kq[ten]:6d}  {ten}")
    for ma, cau in kq["lech"][:12]:
        print(f"   lệch tài liệu: {ma[:44]} | {cau[:110]}")
    if not a.thu or a.ghi:
        return 0

    sp, cu, moi = a.thu
    tep = os.path.join(tam, "knowledge", "products", f"{bdk._ma(sp)}.md")
    noi_dung = open(tep, encoding="utf-8").read()
    if cu not in noi_dung:
        print(f"Tài liệu {sp} không có chuỗi {cu!r}")
        return 1
    sau = noi_dung.replace(cu, moi)
    rel = f"products/{bdk._ma(sp)}.md"
    print(f"\nDiễn tập: {rel}  {cu!r} -> {moi!r}")
    if not kho.chi_doi_so(conn, rel, sau):
        print("  Không phải thay đổi chỉ-con-số: sẽ đi đường soạn lại bằng Qwen như cũ.")
        return 0
    truoc = dict(conn.execute("SELECT id, tra_loi FROM hoi_dap WHERE bat=1"))
    open(tep, "w", encoding="utf-8").write(sau)
    conn.execute("CREATE TABLE IF NOT EXISTS answer_bank_entries (hoi_dap_id TEXT PRIMARY KEY,"
                 " source_path TEXT, source_hash TEXT, voice_ready INTEGER DEFAULT 0)")
    with conn:
        r = kho.ap_dung_doi_so(conn, rel, "dien_tap", tam)
    print(f"  viết lại {r['viet_lai']}, giữ nguyên {r['giu_nguyen']}, tắt {r['tat']}")
    sau_db = dict(conn.execute("SELECT id, tra_loi FROM hoi_dap WHERE bat=1"))
    cua_sp = {m for m, x in conn.execute("SELECT id, san_pham FROM hoi_dap")
              if bdk._ma(x or "") == bdk._ma(sp)}
    doi = [(truoc[m], sau_db[m]) for m in sau_db if truoc.get(m) != sau_db[m]]
    for x, y in doi[:5]:
        print(f"   - {x[:100]}\n     -> {y[:100]}")
    for m in r["da_tat"][:5]:
        print(f"   tắt: {truoc[m][:110]}")
    con_cu = [c for m, c in sau_db.items() if m in cua_sp and bdk.so_lech(c, sp, tam)]
    print(f"  câu còn bật mà nói con số ngoài tài liệu của {sp}: {len(con_cu)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
