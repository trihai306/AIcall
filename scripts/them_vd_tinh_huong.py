"""Them vi du LAY TU LOI KHACH THAT vao cac tinh huong hay suyt trượt.

Chi them nhung cau ma tinh huong khop la DUNG. Nhung cau khop NHAM (vd 'xin chao
em' khop `khach_hoi_so_dien_thoai`) thi KHONG them - them vao la dau doc bo phan
loai.

Chay: .venv\\python.exe scripts\\them_vd_tinh_huong.py [--that]
Khong co --that thi chi in ra xem truoc, khong ghi.
"""
import json, sqlite3, sys, time
from pathlib import Path
DU_AN = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")

# Nguon: `scripts/dao_suyt_tmp.py` chay tren 2074 cau khach that, vung 0.60-0.75.
THEM = {
    "hen_goi_lai": [
        "thôi để hôm khác",
        "để hôm khác đi",
        "thôi vậy còn lại cho mình sau nhé",
    ],
    "khach_hoi_lai_ten": [
        "alo ai đây",
        "alo ai đấy",
        "ai đấy ạ",
    ],
    # KHONG them cho `hoi_tinh_toan`. Da thu va DO THAY no dau doc bo phan loai:
    # cau "anh muon vay bon tram trieu trong vong muoi hai thang" la cau NEU Y
    # DINH chu khong phai cau hoi tinh toan, nen them vao thi keo theo moi cau
    # "anh muon vay X":
    #     'anh muon vay mua nha'  None -> hoi_tinh_toan   SAI
    #     'anh muon vay 2 ty'     hoi_dieu_kien -> hoi_tinh_toan   SAI
    # Muon bat duoc nhom nay thi phai co tinh huong RIENG cho "neu y dinh vay
    # kem so tien", khong phai nhet vao `hoi_tinh_toan`.
    "hoi_dieu_kien": [
        "em nói lại giúp anh toàn bộ điều kiện và thủ tục một lượt được không",
    ],
}

that = "--that" in sys.argv
cn = sqlite3.connect(str(DU_AN / "data" / "app.db"))
for id_th, moi in THEM.items():
    r = cn.execute("SELECT vi_du FROM tinh_huong WHERE id=?", (id_th,)).fetchone()
    if not r:
        print(f"  !! khong co tinh huong {id_th}"); continue
    cu = json.loads(r[0]) if r[0] else []
    them = [c for c in moi if c not in cu]
    print(f"{id_th:<24} {len(cu)} -> {len(cu)+len(them)} vi du   (+{len(them)})")
    for c in them:
        print(f"      + {c!r}")
    if that and them:
        cn.execute("UPDATE tinh_huong SET vi_du=?, updated_at=? WHERE id=?",
                   (json.dumps(cu + them, ensure_ascii=False), time.time(), id_th))
if that:
    cn.commit()
    print("\nDA GHI. Nho khoi dong lai backend de nhung lai vi du.")
else:
    print("\n(xem truoc - them --that de ghi that)")
