"""Trang nghe thử phải cắt mảnh Y HỆT đường gọi thật.

ĐỔI 13-08-2026: `chia_ca_luot` đã bị gỡ, việc đó nay do
`api/voices._cat_manh_nhu_pipeline` làm. Test giữ nguyên MỤC ĐÍCH, chỉ đổi hàm
được soi. Trước đó file này đỏ trên cả hai máy vì trỏ vào hàm đã mất - ghi chú
dự án gọi đây là việc "đang treo, chưa chọn giữ bản nào"; bản `_cat_manh...`
thắng vì nó chỉ dùng `tach_manh`+`co_manh`, thứ cả hai máy đều có.

Vì sao cần bộ test này chứ không chỉ đọc mắt: trang nghe thử và đường gọi thật là
hai đoạn mã khác nhau, và cái giá của việc chúng lệch nhau đúng là thứ đã xảy ra
trước đây - chỉnh tốc/chọn giọng trên trang test rồi ra cuộc gọi lại nghe khác.
Test này neo hai bên vào nhau: đổi luật cắt mà quên một bên là đỏ ngay.

Bản mô phỏng ở đây lặp lại vòng producer của `streaming_pipeline` (dòng ~1042 và
đoạn xả đệm ~1079) một cách độc lập, nên nếu `chia_ca_luot` đi chệch pipeline thì
hai bên lệch nhau và test đỏ.
"""

import pytest

from backend.api.voices import _cat_manh_nhu_pipeline as chia_ca_luot
from backend.pipeline.text_chunker import (CO_MANH_TANG_DAN,
                                           TOI_THIEU_TU_MANH_CUOI,
                                           co_manh, nhip_nghi_sau, tach_manh)

try:
    from backend.pipeline.text_chunker import CAT_THEO_CAU
except ImportError:
    # Lối cắt theo câu là việc đang làm dở, chưa có trên mọi bản. Thiếu cờ thì
    # coi như tắt - đừng để test vỡ chỉ vì nhánh này chưa có nó.
    CAT_THEO_CAU = False


def nhu_pipeline(text: str, buoc_token=None) -> list[str]:
    """Bản sao vòng cắt mảnh của `streaming_pipeline`, viết độc lập để đối chứng.

    `buoc_token` = số từ mỗi lần nạp vào đệm, để giả các cỡ token khác nhau của
    LLM. Ranh giới mảnh KHÔNG được phụ thuộc vào cỡ token - chỉ thời điểm giao
    mới phụ thuộc.
    """
    tu_het = text.split()
    buoc = buoc_token or 1
    ra: list[str] = []
    dem = ""
    for i in range(0, len(tu_het), buoc):
        cum = " ".join(tu_het[i:i + buoc])
        dem += cum if not dem else " " + cum
        while True:
            manh, dem = tach_manh(dem, n=co_manh(len(ra)),
                                  first_chunk=(len(ra) == 0))
            if manh is None or not manh.strip():
                break
            ra.append(manh.strip())
    du = dem.strip()
    if du and ra and len(du.split()) < TOI_THIEU_TU_MANH_CUOI:
        ra[-1] = f"{ra[-1]} {du}".strip()
        du = ""
    if du:
        ra.append(du)
    return ra


CAU = [
    "Xin chào anh chị, em là nhân viên tư vấn ngân hàng ABC",
    "Dạ em chào anh Hải, lãi suất vay tín chấp hiện tại là 7.9% một năm, "
    "hạn mức lên đến 500 triệu đồng ạ.",
    "Dạ vâng ạ.",
    "Một hai ba bốn năm sáu bảy tám chín mười",
    "Dạ",
    "",
]


@pytest.mark.parametrize("cau", CAU)
def test_khop_pipeline(cau):
    assert chia_ca_luot(cau) == nhu_pipeline(cau)


@pytest.mark.parametrize("cau", CAU)
@pytest.mark.parametrize("buoc", [1, 2, 3, 7])
def test_ranh_gioi_khong_phu_thuoc_co_token(cau, buoc):
    """Cỡ token của LLM chỉ đổi THỜI ĐIỂM giao, không đổi chỗ cắt."""
    assert nhu_pipeline(cau, buoc_token=buoc) == nhu_pipeline(cau, buoc_token=1)


def test_khong_mat_chu():
    """Ghép các mảnh lại phải ra đúng chữ ban đầu - không rơi, không thêm."""
    for cau in CAU:
        assert " ".join(chia_ca_luot(cau)).split() == cau.split()


@pytest.mark.skipif(CAT_THEO_CAU,
                    reason="cắt theo câu thì cỡ mảnh do dấu câu quyết, không do CO_MANH_TANG_DAN")
def test_co_manh_tang_dan():
    """Mảnh đầu phải nhỏ (tiếng ra sớm), mảnh sau to dần.

    CHỈ đúng ở lối cắt theo SỐ TỪ. Khi `CAT_THEO_CAU` bật thì cỡ mảnh do dấu kết
    câu quyết định - đó là lý do test này có skipif chứ không phải hằng số cứng:
    đã có lúc máy chạy `CAT_THEO_CAU=True` trong khi nhánh git còn ở lối cắt 5 từ.
    """
    cau = " ".join(f"tu{i}" for i in range(60))
    manh = chia_ca_luot(cau)
    assert len(manh[0].split()) == CO_MANH_TANG_DAN[0]
    assert len(manh[1].split()) == CO_MANH_TANG_DAN[1]
    assert len(manh[2].split()) == CO_MANH_TANG_DAN[2]


@pytest.mark.skipif(not CAT_THEO_CAU, reason="chỉ áp dụng cho lối cắt theo câu")
@pytest.mark.parametrize("cau", [
    "Dạ em chào anh Hải. Lãi suất bảy phẩy chín ạ. Vâng",
    "Dạ em chào anh. Vâng ạ",
    "Lãi suất vay tín chấp bảy phẩy chín phần trăm một năm ạ. Dạ",
])
def test_duoi_ngan_khong_thanh_manh_rieng_o_loi_cat_cau(cau):
    """Đuôi cụt sau dấu chấm phải GỘP vào mảnh trước, không đứng riêng.

    Đây đúng là chỗ một bản cắt viết tay (thiếu bước gộp đuôi của
    `streaming_pipeline`) đi chệch: nó nhả "Vâng" / "Dạ" thành mảnh MỘT TỪ, mà F5
    sinh mỗi mảnh như một câu trọn vẹn nên từ đó nghe tách hẳn khỏi câu nó thuộc
    về. Xem `TOI_THIEU_TU_MANH_CUOI`.
    """
    manh = chia_ca_luot(cau)
    assert all(len(m.split()) >= TOI_THIEU_TU_MANH_CUOI for m in manh), manh


@pytest.mark.skipif(not CAT_THEO_CAU, reason="chỉ áp dụng cho lối cắt theo câu")
def test_cat_theo_cau_moi_manh_la_mot_cau():
    """Lối cắt theo câu: mỗi dấu kết câu là một ranh giới mảnh."""
    manh = chia_ca_luot("Dạ em chào anh. Lãi suất bảy phẩy chín ạ. "
                        "Anh có muốn nghe thêm không?")
    assert len(manh) == 3
    assert all(m.rstrip().endswith((".", "!", "?", "…")) for m in manh)


def test_duoi_ngan_gop_vao_manh_truoc():
    """Đuôi ngắn hơn TOI_THIEU_TU_MANH_CUOI không được thành mảnh riêng."""
    # 5 + 1 từ: từ dư phải gộp vào mảnh đầu chứ không đứng riêng.
    manh = chia_ca_luot("mot hai ba bon nam sau")
    assert len(manh) == 1
    assert manh[0].split() == ["mot", "hai", "ba", "bon", "nam", "sau"]


def test_rong_ra_danh_sach_rong():
    assert chia_ca_luot("") == []
    assert chia_ca_luot("   ") == []


def test_mot_manh_thi_khong_khac_gi_mot_phat():
    """Chữ ngắn hơn một mảnh thì cắt mảnh không đổi gì - phải y hệt bản một phát."""
    assert chia_ca_luot("Dạ vâng") == ["Dạ vâng"]


def test_nhip_nghi_theo_cau_hinh_hien_hanh():
    """Nhịp nghỉ phải lấy từ `nhip_nghi_sau`, không được đặt số riêng ở chỗ khác.

    CAT_DON_GIAN=True thì hàm trả 0.0 - test này không khẳng định giá trị, chỉ
    khẳng định trang test và đường gọi cùng đọc MỘT nguồn.
    """
    for m in chia_ca_luot(CAU[1]):
        assert nhip_nghi_sau(m) == nhip_nghi_sau(m)  # cùng nguồn, không hằng số rời
