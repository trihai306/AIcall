"""Câu đệm đứng NGAY TRƯỚC một câu đọc nguyên văn phải hợp với câu đó.

VÌ SAO CÓ FILE NÀY. Diễn lại cuộc gọi `08c0d3e0` (11-09-2026), ba lượt đọc
nguyên văn bảng hỏi-đáp mà khách nghe lặp hoặc nghe ngược nghĩa:

    "Dạ về mức lãi này em xin nói rõ thêm," + "Lãi này bên em đã là ưu đãi..."
    "Dạ hạn mức này còn tuỳ hồ sơ của mình," + "Hạn mức này bên em thuộc tốp cao..."
    "Dạ về hồ sơ cần chuẩn bị thì,"          + "Mình chuẩn bị căn cước công dân..."

Câu nguyên văn là TIẾNG DỰNG SẴN nên không cắt chữ ở chỗ nối được như câu mô
hình viết (`BotLichSu`). Và câu đệm được chọn TRƯỚC khi tra bảng
(`_send_filler` chạy trước `_tra_bang_hoi_dap`). Chỗ duy nhất sửa được là chính
câu mở đầu của tình huống dẫn vào câu nguyên văn đó.

Tình huống nào dẫn vào dòng nào:
  - dòng CHÊ: id dòng TRÙNG id tình huống, dòng đi theo tình huống chứ không
    theo cosine (`bang_hoi_dap.dong_theo_tinh_huong`) - chắc chắn.
  - dòng khác: theo bộ phân loại, đo trên Win 11-09-2026 bằng câu hỏi của chính
    dòng đó. Đổi ví dụ tình huống thì đo lại, xem `scripts/kiem_noi_dem_bang.py`.
"""
import json
import re
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]

# Đo 11-09-2026: "cần những gì", "chuẩn bị gì", "cần giấy tờ gì", "thủ tục gồm
# những gì" -> hoi_ho_so; "chi nhánh ở đâu", "đến đâu để làm" -> hoi_chi_nhanh;
# "vay như nào", "quy trình vay ra sao" -> hoi_cach_vay (trước khi có tình huống
# này: hoi_lai_suat 0,83 - khách nghe "Dạ về lãi suất thì, Bên em cho vay tín
# chấp, tức là không cần tài sản thế chấp").
DO_PHAN_LOAI = {"can_nhung_gi": "hoi_ho_so", "ben_em_o_dau": "hoi_chi_nhanh",
                "co_che_vay_chung": "hoi_cach_vay"}

# Chữ không mang chủ đề: trùng mấy chữ này không phải lặp ý.
_KHONG_CHU_DE = {
    "dạ", "vâng", "ạ", "em", "anh", "chị", "mình", "bên", "của", "về", "thì",
    "là", "này", "đó", "cho", "và", "đã", "rồi", "với", "xin", "phép", "ạ",
}
# Hứa đi xem / tuỳ trường hợp, rồi câu nguyên văn khẳng định luôn - hai câu
# ngược nhau trong một hơi.
_HUA_XEM = re.compile(r"\b(xem|kiểm tra|tuỳ|tùy|còn tuỳ|còn tùy)\b", re.I)


def _tu(s: str) -> list[str]:
    return [w for w in re.findall(r"\w+", s.lower()) if w not in _KHONG_CHU_DE]


def _doc():
    th = {t["id"]: t for t in json.loads(
        (GOC / "data/tinh_huong_seed.json").read_text(encoding="utf-8"))["tinh_huong"]}
    hd = json.loads((GOC / "data/hoi_dap_seed.json").read_text(encoding="utf-8"))
    hd = hd["hoi_dap"] if isinstance(hd, dict) else hd
    return th, {d["id"]: d for d in hd}


def _cap_noi():
    """Mọi cặp (dòng, tình huống, câu mở đầu) khách sẽ nghe liền nhau."""
    th, hd = _doc()
    ma_th = {i: i for i in hd if i in th}
    ma_th.update(DO_PHAN_LOAI)
    for ma_dong, ma in ma_th.items():
        for m in th[ma]["mo_dau"]:
            yield ma_dong, hd[ma_dong]["tra_loi"], m


def test_bang_do_phan_loai_con_tro_toi_dong_va_tinh_huong_that():
    th, hd = _doc()
    for dong, ma in DO_PHAN_LOAI.items():
        assert dong in hd and ma in th, (dong, ma)


def test_cau_mo_dau_khong_nhac_lai_chu_cua_cau_nguyen_van():
    loi = []
    for dong, tra_loi, m in _cap_noi():
        trung = set(_tu(m)) & set(_tu(" ".join(tra_loi.split()[:6])))
        if trung:
            loi.append(f"{dong}: {m!r} + {tra_loi[:40]!r} lặp {sorted(trung)}")
    assert not loi, "\n".join(loi)


def test_cau_mo_dau_khong_hua_xem_truoc_cau_khang_dinh():
    loi = [f"{dong}: {m!r}" for dong, _, m in _cap_noi() if _HUA_XEM.search(m)]
    assert not loi, "\n".join(loi)


# --- Khách hỏi "bên em có X không" -----------------------------------------

def test_hoi_co_san_pham_co_tinh_huong_rieng():
    """Không có tình huống này thì câu đó rơi vào hoi_dieu_kien (0,750) và khách
    nghe "Dạ về điều kiện vay thì," - trớt chủ đề (bản diễn lại 11-09)."""
    th, _ = _doc()
    assert "bên bạn có cho vay tín chấp không" in th["hoi_co_san_pham"]["vi_du"]


def test_cau_mo_dau_hoi_co_san_pham_khong_tra_loi_co_truoc():
    """Câu đệm phát khi CHƯA biết bên em có sản phẩm đó không. "Dạ vâng ạ," /
    "Dạ có ạ," trước câu hỏi có-không là đã trả lời CÓ - bịa khi sản phẩm không
    có (khách hỏi "có vay mua nhà không" mà bên em chỉ cho vay tín chấp)."""
    th, _ = _doc()
    for m in th["hoi_co_san_pham"]["mo_dau"]:
        assert not re.search(r"\b(vâng|có|được)\b", m.lower()), m
