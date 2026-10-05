"""Chọn tình huống bằng cosine. Thuần numpy, không GPU."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

from backend.services.filler_situation import (
    NGUONG_DIEM, chon_tinh_huong, chon_tinh_huong_cau_day_du,
    chon_tinh_huong_tu_khoa_nhanh, chon_tinh_huong_vi_du_nhanh, chuan_hoa,
)


def v(*x) -> np.ndarray:
    return np.array(x, dtype=np.float32)


def test_chon_tinh_huong_diem_cao_nhat():
    kho = {
        "lai_suat": chuan_hoa(np.stack([v(1, 0, 0)])),
        "ho_so": chuan_hoa(np.stack([v(0, 1, 0)])),
    }
    id_th, diem = chon_tinh_huong(chuan_hoa(v(0.9, 0.1, 0))[0], kho)
    assert id_th == "lai_suat" and diem > NGUONG_DIEM


def test_lay_vi_du_khop_nhat_trong_cung_tinh_huong():
    """Một tình huống có nhiều ví dụ: lấy ví dụ KHỚP NHẤT, không lấy trung bình.
    Trung bình làm loãng - hai ví dụ trái nhau triệt tiêu nhau."""
    kho = {"a": chuan_hoa(np.stack([v(1, 0, 0), v(0, 0, 1)]))}
    id_th, diem = chon_tinh_huong(chuan_hoa(v(0, 0, 1))[0], kho)
    assert id_th == "a" and diem == pytest.approx(1.0, abs=1e-5)


def test_duoi_nguong_tra_none_kem_diem():
    """Trả cả điểm để nơi gọi ghi log được vì sao trượt."""
    kho = {"a": chuan_hoa(np.stack([v(1, 0, 0)]))}
    id_th, diem = chon_tinh_huong(chuan_hoa(v(0, 1, 0))[0], kho)
    assert id_th is None and diem < NGUONG_DIEM


def test_kho_rong():
    id_th, diem = chon_tinh_huong(chuan_hoa(v(1, 0, 0))[0], {})
    assert id_th is None and diem == 0.0


def test_tinh_huong_khong_co_vi_du_bi_bo_qua():
    """Ma trận rỗng không được làm hàm nổ."""
    kho = {"rong": np.zeros((0, 3), dtype=np.float32),
           "a": chuan_hoa(np.stack([v(1, 0, 0)]))}
    assert chon_tinh_huong(chuan_hoa(v(1, 0, 0))[0], kho)[0] == "a"


def test_chuan_hoa_vector_khong():
    """Vector 0 không được sinh NaN - chia cho 0 là bẫy im lặng."""
    r = chuan_hoa(v(0, 0, 0))
    assert not np.isnan(r).any()


def test_nguong_tuy_chinh():
    kho = {"a": chuan_hoa(np.stack([v(1, 0, 0)]))}
    q = chuan_hoa(v(0.8, 0.6, 0))[0]
    assert chon_tinh_huong(q, kho, nguong=0.9)[0] is None
    assert chon_tinh_huong(q, kho, nguong=0.5)[0] == "a"


def test_cau_day_du_co_tu_khoa_ro_cuu_ung_vien_vector_sap_nguong():
    kho = {"the_dien_tu": chuan_hoa(v(1, 0))}
    q = chuan_hoa(v(0.85, 0.527))[0]
    situations = [SimpleNamespace(id="the_dien_tu", bat=True,
                                  tu_khoa=("thẻ điện tử", "thẻ ảo"))]
    assert chon_tinh_huong_cau_day_du(
        "Đăng ký thẻ điện tử Shinhan và mã SMS ở đâu?", q, kho, situations
    )[0] == "the_dien_tu"
    assert chon_tinh_huong_cau_day_du(
        "Đăng ký tài khoản và mã SMS ở đâu?", q, kho, situations
    )[0] is None


def test_cau_day_du_khong_cuu_khi_tu_khoa_mo_ho_hoac_diem_yeu():
    kho = {"the_dien_tu": chuan_hoa(v(1, 0)), "phi": chuan_hoa(v(0, 1))}
    situations = [
        SimpleNamespace(id="the_dien_tu", bat=True, tu_khoa=("thẻ điện tử",)),
        SimpleNamespace(id="phi", bat=True, tu_khoa=("thẻ điện tử",)),
    ]
    q = chuan_hoa(v(0.85, 0.527))[0]
    assert chon_tinh_huong_cau_day_du(
        "Thẻ điện tử thế nào?", q, kho, situations
    )[0] is None
    assert chon_tinh_huong_cau_day_du(
        "Thẻ điện tử thế nào?", chuan_hoa(v(0.70, 0.714))[0], kho,
        situations[:1]
    )[0] is None


def test_tu_khoa_ro_chon_ngay_nhung_khong_cat_nham_cau_phu_dinh():
    situations = [
        SimpleNamespace(id="the_dien_tu", bat=True,
                        tu_khoa=("thẻ điện tử", "thẻ ảo")),
        SimpleNamespace(id="hoi_chi_nhanh", bat=True, tu_khoa=("ở đâu",)),
        SimpleNamespace(id="khach_dong_y", bat=True, tu_khoa=("đăng ký",)),
    ]
    assert chon_tinh_huong_tu_khoa_nhanh(
        "Đăng ký thẻ điện tử Shinhan và mã SMS dùng ở đâu?", situations
    ) == "the_dien_tu"
    assert chon_tinh_huong_tu_khoa_nhanh(
        "Tôi không hỏi thẻ điện tử, tôi hỏi lãi suất", situations
    ) is None
    situations.append(SimpleNamespace(
        id="doi_chieu_the", bat=True, tu_khoa=("thẻ điện tử",)))
    assert chon_tinh_huong_tu_khoa_nhanh(
        "Thẻ điện tử dùng ra sao?", situations
    ) is None


def test_vi_du_moi_duoc_chon_ngay_va_trung_nhan_phai_ve_vector():
    situations = [
        SimpleNamespace(id="chung", bat=True, vi_du=("A lô",)),
        SimpleNamespace(id="hoi_phi", bat=True,
                        vi_du=("Mất phí gì không?", "Có tốn phí không?")),
    ]
    assert chon_tinh_huong_vi_du_nhanh(
        "  MAT PHI GI KHONG  ", situations) == ("hoi_phi", True)
    situations.append(SimpleNamespace(id="che_phi_cao", bat=True,
                                      vi_du=("mất phí gì không",)))
    assert chon_tinh_huong_vi_du_nhanh(
        "Mất phí gì không?", situations) == (None, True)
    assert chon_tinh_huong_vi_du_nhanh("A lô", situations) == (None, False)
    assert chon_tinh_huong_vi_du_nhanh(
        "Mất phí gì không?", situations,
        bo_qua=frozenset({"hoi_phi"})) == ("che_phi_cao", True)
    situations[1].bat = False
    assert chon_tinh_huong_vi_du_nhanh(
        "Có tốn phí không?", situations) == (None, False)


# --- Ngưỡng siết lên 0,90 ngày 05-09-2026 -------------------------------------
#
# Đo lại trên 102 lượt tiếng khách THẬT (trích từ 47 bản ghi cuộc gọi,
# `scripts/do_nguong_tinh_huong.py`) cho kết quả KHÁC HẲN phép đo cũ vốn dựa
# trên tập nhỏ:
#
#     mốc 1000ms   0,75 -> chọn 29, đúng 15, SAI 14   (52%)
#                  0,90 -> chọn  4, đúng  4, SAI  0   (100%)
#     mốc 1200ms   0,75 -> chọn 33, đúng 20, SAI 13   (61%)
#                  0,90 -> chọn  5, đúng  5, SAI  0   (100%)
#
# Comment cũ ghi "0,75 -> phân loại 4 lần, đúng 4 (100%)" — đúng với tập đo lúc
# đó, nhưng trên tiếng thật thì 0,75 để lọt gần MỘT NỬA số lần chọn là sai.
#
# Nguyên tắc không đổi, chỉ có số đo tốt hơn: chọn sai mẩu mở đầu tệ hơn không
# có mẩu nào, vì rổ chung vốn trung tính còn chọn sai thì nghe như AI hiểu nhầm.

def test_nguong_cau_dem_thap_thi_phai_co_luoi_do_phu_bu_lai():
    """Ngưỡng dưới 0,90 thì vùng ĐỘ PHỦ THẤP phải có lưới khác gác.

    Bản cũ của test này chốt cứng `NGUONG_CAU_DEM >= 0.90`. Đó là một QUYẾT ĐỊNH
    (đổi "chọn nhiều" lấy "chọn đúng"), không phải quy luật - và ngày 06-09-2026
    người dùng chọn ngược lại sau khi thấy cái giá: 3/5 lượt không nhận ra tình
    huống, kéo theo 60% số lượt mất luôn câu đệm.

    Thứ KHÔNG đổi là quy luật đằng sau, đo được bằng cùng một bảng ở hai ngưỡng
    (`scripts/do_do_phu_tinh_huong.py [nguong]`), phần độ phủ dưới 0,5:
        chấm ở 0,90 -> 4 đúng / 0 SAI
        chấm ở 0,75 -> 4 đúng / 7 SAI
    Tức ngưỡng cao TỰ gác vùng đó; hạ ngưỡng thì phải có lưới khác thế chỗ.
    """
    from backend.services.filler_pick import DIEM_DOI_KHI_PHU_THAP
    from backend.services.filler_situation import NGUONG_CAU_DEM
    if NGUONG_CAU_DEM >= 0.90:
        return
    assert DIEM_DOI_KHI_PHU_THAP >= 0.90, (
        f"ngưỡng câu đệm đang {NGUONG_CAU_DEM} (< 0,90) mà vùng độ phủ thấp "
        "không đòi điểm cao -> mở cửa cho đúng 7 lần sai đã đo")


def test_nguong_cau_dem_KHONG_dung_chung_voi_nguong_chung():
    """Nâng `NGUONG_DIEM` chung là âm thầm siết luôn BẢNG HỎI-ĐÁP.

    `_tra_bang_hoi_dap` cũng gọi `chon_tinh_huong` với ngưỡng mặc định. Lần sửa
    đầu nâng thẳng `NGUONG_DIEM` lên 0,90 và bộ test đã bắt được qua
    `test_nguong_doc_thang_cao_hon_nguong_trung` (đọc thẳng 0,90 phải CAO HƠN
    ngưỡng trúng bảng). Hai đường chịu rủi ro khác nhau nên phải có hai ngưỡng.

    `>=` chứ không `>`: 06-09-2026 người dùng hạ ngưỡng câu đệm về đúng 0,75 nên
    hai số TRÙNG NHAU. Điều phải giữ là hai HẰNG SỐ RIÊNG - trùng giá trị lúc này
    là trùng tình cờ. Cấm chiều ngược lại: câu đệm lỏng hơn bảng hỏi-đáp thì vô
    lý, vì chọn sai câu đệm nghe tệ hơn trượt bảng hỏi-đáp nhiều.
    """
    from backend.services.filler_situation import NGUONG_CAU_DEM
    assert NGUONG_CAU_DEM >= NGUONG_DIEM
