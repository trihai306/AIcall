"""Luật cắt mảnh: cứ 5 từ một, trừ hai chỗ không được cắt.

Đổi từ "cắt ở dấu câu" ngày 2026-08-09 vì mảnh dài làm F5 tự bịa quãng dừng giữa
câu — 19 quãng 300-1600ms trong bản ghi hội thoại thật 111 giây. Đo đối chứng
cùng đoạn văn, cùng lúc Ollama đang sinh token:

    dấu câu (cũ)  6 mảnh   1 quãng lặng > 250ms
    5 từ         18 mảnh   0
    3 từ         29 mảnh   3, kèm 21 lần sinh không kịp phát

Test này khoá cả ba thứ: đúng 5 từ, không bẻ cụm số, không xé số phân cách nghìn.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from backend.pipeline import text_chunker
from backend.pipeline.text_chunker import (
    GIOI_HAN_TU_MANH, TRAN_CHO_CUM_SO_SAU, nhip_nghi_sau, tach_manh,
)


@pytest.fixture(autouse=True)
def cat_thong_minh(monkeypatch):
    """Tệp này khoá lối cắt THÔNG MINH, không phải lối máy móc đang bật.

    Đường chạy thật từ 2026-08-10 dùng `CAT_DON_GIAN = True` (xem
    `tests/test_cat_don_gian.py`). Giữ nguyên các test này vì lối thông minh vẫn
    còn nguyên trong mã và bật lại chỉ bằng một dòng - mỗi ràng buộc ở đây đều
    từ một lỗi thật, mất chúng là mất luôn lý do chúng tồn tại.
    """

    # `CAT_THEO_CAU` (2026-08-11) đè lên cả hai lối cũ - tắt để khoá lối thông minh.
    monkeypatch.setattr(text_chunker, "CAT_THEO_CAU", False)
    monkeypatch.setattr(text_chunker, "CAT_DON_GIAN", False)


def cat(van: str, first: bool = True) -> list[str]:
    """Cắt y hệt vòng stream của pipeline.

    Token của Ollama mang dấu cách ở ĐẦU (" ngay"), nên phải nối kiểu " " + tu
    chứ không strip - đó chính là cách đệm hình thành trên đường chạy thật.
    """
    ra, dem = [], ""
    for t in van.split():
        dem += " " + t
        manh, dem = tach_manh(dem, first_chunk=(first and not ra))
        if manh:
            ra.append(manh)
    if dem.strip():
        ra.append(dem.strip())
    return ra


def du(dem: str) -> bool:
    """Đã tách được mảnh chưa. Thêm dấu cách cuối = token sau đã bắt đầu."""
    return tach_manh(dem + " ")[0] is not None


# --- cắt đúng 5 từ -------------------------------------------------------

def test_cat_dung_moc_n_tu():
    """Cắt đúng ở mốc, không sớm không muộn. Dùng từ THƯỜNG, không dùng từ số -
    từ số bị `_dang_giua_cum_so` giữ lại nên mảnh dài ra."""
    tu = ["anh", "chị", "vui", "lòng", "chờ", "em", "chút", "xíu", "nhé", "thôi",
          "để", "bên", "kia", "xem", "giúp", "mình", "một", "tẹo", "rồi", "báo"]
    van = " ".join(tu[:GIOI_HAN_TU_MANH + 3])
    m = cat(van)
    assert len(m[0].split()) == GIOI_HAN_TU_MANH


def test_chua_du_moc_thi_chua_cat():
    tu = ["anh", "chị", "vui", "lòng", "chờ", "em", "chút", "xíu", "nhé", "thôi",
          "để", "bên", "kia", "xem", "giúp", "mình", "một", "tẹo", "rồi", "báo"]
    assert du(" ".join(tu[:GIOI_HAN_TU_MANH - 1])) is False
    assert du(" ".join(tu[:GIOI_HAN_TU_MANH])) is True


def test_manh_dau_khong_con_luat_rieng():
    """Trước đây mảnh đầu cắt ở 12 từ. Nay mọi mảnh đều 5 từ."""
    van = "anh chị vui lòng chờ em một chút để em tra cứu"
    assert cat(van, first=True) == cat(van, first=False)


def test_du_thi_gom_vao_manh_cuoi():
    tu = ["anh", "chị", "vui", "lòng", "chờ", "em", "chút", "xíu", "nhé", "thôi",
          "để", "bên", "kia", "xem", "giúp", "mình", "một", "tẹo"]
    van = " ".join(tu[:GIOI_HAN_TU_MANH + 2])
    m = cat(van)
    assert " ".join(m) == van, "không được mất chữ nào"


# --- không bẻ đôi cụm số -------------------------------------------------

@pytest.mark.parametrize("dem", [
    "hạn mức tối đa năm",          # "năm" mở đầu "năm trăm triệu"
    "lãi suất chỉ có bảy",         # "bảy" mở đầu "bảy phẩy chín"
    "vay được tối đa khoảng",      # "khoảng" đứng trước số
    "thời hạn vay lên tới",        # "tới" đứng trước số
    "lãi suất là sáu phần",        # "phần" mở đầu "phần trăm"
])
def test_khong_cat_giua_cum_so(dem):
    assert du(dem) is False, f"đã cắt sau {dem.split()[-1]!r}"


def test_cum_so_dong_thi_cat_duoc():
    """Có dấu câu ở cuối nghĩa là cụm đã đóng."""
    assert du("bảy phẩy chín phần trăm,") is True


def test_cum_so_khong_giu_buffer_mai():
    """Chuỗi toàn từ số phải được giao khi quá trần, không kẹt vô hạn."""
    van = " ".join(["một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám"] * 6)
    m = cat(van)
    assert len(m) >= 2
    assert all(len(x.split()) <= TRAN_CHO_CUM_SO_SAU + 2 for x in m)


# --- không xé số phân cách nghìn ----------------------------------------

def test_khong_xe_so_phan_cach_nghin():
    """"142." là dấu phân cách nghìn, không phải hết câu.

    Lỗi thật bắt được 2026-08-06: khách nghe "một trăm bốn mươi hai" rồi mới tới
    "năm trăm nghìn". Ca nguy hiểm là khi mốc 5 từ rơi ĐÚNG ngay sau "142.".
    """
    assert du("anh ơi dư nợ 142.") is False


def test_moc_khong_cham_vao_so_thi_cat_binh_thuong():
    """Số nằm SAU mốc thì mốc không đụng tới nó - cứ cắt."""
    tu = ["anh", "chị", "vui", "lòng", "chờ", "em", "chút", "xíu", "nhé", "thôi",
          "để", "bên", "kia", "xem", "giúp", "mình"]
    assert du(" ".join(tu[:GIOI_HAN_TU_MANH]) + " 142.") is True


def test_so_da_tron_thi_cat_duoc():
    tu = ["anh", "chị", "vui", "lòng", "chờ", "em", "chút", "xíu", "nhé", "thôi",
          "để", "bên", "kia", "xem", "giúp"]
    assert du(" ".join(tu[:GIOI_HAN_TU_MANH - 1]) + " 142.500.000") is True


# --- nhịp nghỉ vẫn hoạt động --------------------------------------------

def test_nhip_nghi_theo_dau_cuoi_manh():
    """Dấu chấm nghỉ lâu nhất, rồi tới dấu phẩy, rồi tới cắt giữa chừng.

    Cắt giữa chừng KHÔNG còn là 0: F5 sinh cả câu cũng tự nghỉ ở giữa cụm từ,
    mà trim_silence đã cắt mất chỗ đó ở mọi mép mảnh.
    """
    from backend.pipeline.text_chunker import NGHI_GIUA_CUM_MS
    assert (nhip_nghi_sau("em xin phép hỏi ạ.")
            > nhip_nghi_sau("em xin phép hỏi ạ,")
            > nhip_nghi_sau("cắt giữa chừng không dấu")
            == NGHI_GIUA_CUM_MS > 0)


def test_dem_rong_khong_cat():
    assert tach_manh("")[0] is None
    assert tach_manh("   ")[0] is None


# --- cắt ở dấu câu để code chèn được nhịp nghỉ ---------------------------
#
# Từ 2026-08-09 dấu câu bị bỏ khỏi chữ đưa vào F5 (`bo_dau_cau_cho_f5`), nên dấu
# nằm GIỮA mảnh sẽ mất luôn quãng nghỉ: F5 không nghỉ nữa mà code cũng không chèn
# vì chỗ đó không phải ranh giới mảnh. Cắt ở dấu thì dấu luôn rơi vào ranh giới.

from backend.pipeline.text_chunker import (  # noqa: E402
    NGHI_CHAM_MS, NGHI_PHAY_MS, TOI_THIEU_TU_KHI_CAT_O_DAU,
)


def test_cat_ngay_o_dau_phay_du_chua_du_5_tu():
    m = cat("dạ vâng ạ, anh chị chờ em chút")
    assert m[0] == "dạ vâng ạ,"


def test_cat_o_dau_cham():
    m = cat("em hiểu rồi ạ. anh chị cho em hỏi thêm")
    assert m[0] == "em hiểu rồi ạ."


def test_khong_cat_o_dau_khi_chua_du_toi_thieu():
    """"Dạ," một mình là mảnh 1 từ - tốn trọn một lượt F5 cho 0,3 giây tiếng."""
    assert TOI_THIEU_TU_KHI_CAT_O_DAU == 3
    m = cat("dạ, anh chị cho em xin ít phút")
    assert len(m[0].split()) >= TOI_THIEU_TU_KHI_CAT_O_DAU


def test_van_cat_o_moc_khi_khong_co_dau():
    tu = ["anh", "chị", "vui", "lòng", "chờ", "em", "chút", "xíu", "nhé", "thôi",
          "để", "bên", "kia", "xem", "giúp", "mình", "một", "tẹo"]
    m = cat(" ".join(tu[:GIOI_HAN_TU_MANH + 2]))
    assert len(m[0].split()) == GIOI_HAN_TU_MANH


def test_khong_cat_o_dau_phan_cach_nghin():
    """"142." đứng ở từ thứ 3 vẫn không được coi là hết câu."""
    m = cat("dư nợ 142.500.000 đồng ạ nhé anh")
    assert not m[0].endswith("142.")


def test_nhip_nghi_dat_cung_theo_yeu_cau():
    """NỚI 100/200 -> 180/320 ngày 14-08-2026, theo tai người dùng.

    Họ báo ở Lần 6 hai chỗ "không ngắt nghỉ" (sau chữ "vâng" có phẩy, và sau dấu
    chấm chỗ "thẩm định"). Đo trên chính câu họ gửi thì quãng nghỉ CÓ tồn tại,
    300ms - nhưng tai họ vẫn thấy chưa đủ, và ở chỗ này tai người là thước đo.

    Dựng ba mức rồi đo quãng nghỉ THẬT trong file (`scripts/dung_lai_lan6.py`):
        phẩy 100 / chấm 200 (cũ)   nghỉ đo được 300ms
        phẩy 180 / chấm 320        nghỉ đo được 420ms   <- chọn
        phẩy 250 / chấm 450        nghỉ đo được 560ms
    Chọn mức giữa vì mức cao làm câu bốn mảnh dài thêm gần một giây, mà cuộc gọi
    tính tiền theo phút.

    Ai hạ lại thì phải đo bằng chính script trên và hỏi người dùng - đây là con
    số do tai họ chốt, không phải hằng số kỹ thuật.
    """
    assert NGHI_CHAM_MS == 320.0
    assert NGHI_PHAY_MS == 180.0
    assert nhip_nghi_sau("em hiểu rồi ạ.") == NGHI_CHAM_MS
    assert nhip_nghi_sau("em hiểu rồi ạ,") == NGHI_PHAY_MS
    assert 0 < NGHI_PHAY_MS < NGHI_CHAM_MS


def test_nghi_o_ranh_gioi_khong_co_dau():
    """Cắt giữa chừng vẫn phải nghỉ chút - F5 sinh cả câu cũng nghỉ ở đó.

    Trước để 0ms và đó là chỗ hở: F5 tự nghỉ 12 chỗ khi sinh cả câu, ta chỉ nghỉ
    ở 4-6 chỗ có dấu, còn trim_silence cắt sạch lặng ở mọi mép mảnh.
    """
    from backend.pipeline.text_chunker import NGHI_GIUA_CUM_MS
    assert nhip_nghi_sau("anh chị vui lòng chờ") == NGHI_GIUA_CUM_MS
    assert 0 < NGHI_GIUA_CUM_MS < NGHI_PHAY_MS
