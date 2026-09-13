"""Kho tình huống trong `data/tinh_huong_seed.json`.

VÌ SAO SOI BẰNG TEST. Đây là dữ liệu gõ tay, mà mỗi lỗi trong đó đều hỏng CÂM:
mẩu thiếu dấu phẩy thì F5 hạ giọng kết câu ngay giữa lượt; tình huống một ví dụ
thì cosine dựa vào đúng một cách nói; hai tình huống trùng ví dụ thì điểm sát
nhau và chọn ra cái sai. Không cái nào báo lỗi lúc chạy.

Số mẩu mỗi tình huống là thứ quyết định khách có nghe lặp hay không: một mẩu thì
hỏi cùng chủ đề hai lần là nghe y hệt.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

GOC = Path(__file__).resolve().parents[1]
KHO = json.loads((GOC / "data" / "tinh_huong_seed.json").read_text(encoding="utf-8"))
TH = KHO["tinh_huong"]

SO_MAU_TOI_THIEU = 4


def test_moi_tinh_huong_du_mau_mo_dau():
    thieu = [t["id"] for t in TH if len(t.get("mo_dau", [])) < SO_MAU_TOI_THIEU]
    assert thieu == [], f"thiếu mẩu mở đầu: {thieu}"


def test_moi_mau_ket_bang_dau_phay():
    sai = [(t["id"], m) for t in TH for m in t.get("mo_dau", [])
           if not m.rstrip().endswith(",")]
    assert sai == []


def test_mau_khong_lap_trong_cung_tinh_huong():
    """Bốn mẩu giống nhau thì cũng như một mẩu."""
    lap = [t["id"] for t in TH if len(set(t.get("mo_dau", []))) != len(t.get("mo_dau", []))]
    assert lap == []


def test_mau_khong_chua_con_so():
    """Mẩu phát TRƯỚC khi LLM trả lời, nên nó chưa biết số nào cả. Đọc ra một
    con số ở đây là bịa, và lưới chặn số không soi câu đệm."""
    co_so = [(t["id"], m) for t in TH for m in t.get("mo_dau", [])
             if any(c.isdigit() for c in m)]
    assert co_so == []


def test_moi_tinh_huong_it_nhat_hai_vi_du():
    thieu = [t["id"] for t in TH if len(t.get("vi_du", [])) < 2]
    assert thieu == []


def test_khong_trung_ma_tinh_huong():
    ma = [t["id"] for t in TH]
    assert len(ma) == len(set(ma))


def test_khong_hai_tinh_huong_dung_chung_mot_vi_du():
    """Trùng ví dụ thì điểm cosine sát nhau và cái được chọn là ngẫu nhiên."""
    thay: dict[str, str] = {}
    trung = []
    for t in TH:
        for v in t.get("vi_du", []):
            k = v.strip().lower()
            if k in thay:
                trung.append((thay[k], t["id"], v))
            thay[k] = t["id"]
    assert trung == []


def test_ma_tinh_huong_dung_dinh_dang():
    import re
    sai = [t["id"] for t in TH if not re.match(r"^[a-z0-9_]{2,40}$", t["id"])]
    assert sai == []


def test_du_nhom_phu_cac_cau_khach_hay_hoi():
    """20 nhóm cũ phủ vay/thẻ/từ chối. Thiếu mấy nhóm này thì khách hỏi xong
    nghe "Dạ" trung tính - đúng thứ tính năng câu đệm sinh ra để tránh."""
    ma = {t["id"] for t in TH}
    for can in ("hoi_phi", "hoi_chi_nhanh", "hoi_tat_toan", "khach_dong_y",
                "xin_gui_tai_lieu"):
        assert can in ma, f"thiếu nhóm {can}"


def test_nhom_thai_do_khong_mang_ten_san_pham_trong_vi_du():
    """Đo trên máy thật: ví dụ "được rồi tôi muốn vay" của `khach_dong_y` kéo
    phiên âm cụt "vay tín chấp" lên 0.757 — VƯỢT ngưỡng 0.75, nên khách vừa hỏi
    về sản phẩm lại nghe "Dạ vâng em cảm ơn anh chị,".

    Ghi chú trong `filler_situation` cho thấy chính câu đó trước đây chỉ đạt
    0.614 và rơi an toàn về rổ đuôi. Nhóm mới thêm vào đã làm nó vượt ngưỡng.

    Nhóm nói về THÁI ĐỘ (đồng ý, từ chối, hẹn lại) phải dùng câu thái độ thuần;
    tên sản phẩm trong ví dụ kéo nó về phía các nhóm hỏi sản phẩm.
    """
    THAI_DO = {"khach_dong_y", "tu_choi_dang_ban", "tu_choi_khong_can", "hen_goi_lai"}
    TEN_SP = ("vay", "thẻ", "tín chấp", "mua nhà", "tiết kiệm", "lãi suất")
    dinh = [(t["id"], v) for t in TH if t["id"] in THAI_DO
            for v in t["vi_du"] if any(x in v.lower() for x in TEN_SP)]
    assert dinh == [], f"ví dụ mang tên sản phẩm: {dinh}"


def test_khong_mau_nao_ket_bang_chu_thi():
    """13-09-2026: "thì" cuối câu đệm treo lơ lửng trước quãng chờ câu trả lời."""
    from backend.pipeline.bo_thi_cuoi import bo_thi_cuoi
    sai = [(t["id"], m) for t in TH for m in t.get("mo_dau", []) if bo_thi_cuoi(m) != m]
    assert sai == []


def test_cau_dem_bang_hoi_dap_khong_ket_bang_thi():
    from backend.pipeline.bo_thi_cuoi import bo_thi_cuoi
    bang = json.loads((GOC / "data" / "hoi_dap_seed.json").read_text(encoding="utf-8"))
    dong = bang if isinstance(bang, list) else next(iter(bang.values()))
    sai = [d["id"] for d in dong if bo_thi_cuoi(d.get("cau_dem") or "") != (d.get("cau_dem") or "")]
    assert sai == []


def test_nhom_chung_co_cau_du_dai_de_che_luot_cham():
    """Cuộc gọi 7db3f780 (13-09-2026): nhóm chung chỉ còn "Dạ,"… dài 0,27-0,57s
    trong khi lượt qua LLM chờ 1-1,5s, khách nghe "Dạ," rồi im 0,8-1,04s (đo trên
    bản ghi). Nhóm chung phải có câu dài cỡ 1-1,3s. Độ dài tiếng không suy được
    từ chữ, nên canh bằng số từ; độ dài thật đo lại sau khi dựng clip.

    Cố ý KHÔNG dài tới 1,35s: `_FILLER_CHUNG_HUT_TOI_DA_MS` (450) + câu chung
    dài nhất >= sàn che 1800ms thì hệ thống thôi chờ phân loại chủ đề ở MỌI lượt,
    và câu đệm theo chủ đề ít được dùng. Đo khi dựng thật giọng heu_a6_35: "Dạ em
    trả lời anh chị luôn ạ," 1,51s và "Dạ vâng, em thông tin luôn ạ," 1,35s đều
    chạm mốc nên đã bỏ; ba câu còn lại 1,15-1,19s.
    """
    chung = next(t for t in TH if t["id"] == "chung")
    dai = [m for m in chung["mo_dau"] if len(m.rstrip(",").split()) >= 5]
    assert len(dai) >= 3, dai
    assert all(len(m.rstrip(",").split()) <= 8 for m in chung["mo_dau"])
