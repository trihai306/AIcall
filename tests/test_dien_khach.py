"""Khách đã nói mình làm tự do thì câu hỏi giấy tờ ở lượt sau phải tra kho theo diện đó.

Đo 09-10-2026 trên backend thật: "anh làm tự do" rồi "thế cần giấy tờ gì" nhận
câu hồ sơ chung có "hợp đồng lao động"; và mô hình tự viết ra "hợp đồng kinh
doanh" - cụm không có trong tài liệu nào.
"""
import pytest

from backend.pipeline.chan_tuan_thu import sua_thuat_ngu_lai
from backend.pipeline.dien_khach import cau_hoi_cho_kho, dien_khach
from backend.services.answer_bank_selector import _is_follow_up

TAI_LIEU = ("## Điều kiện vay\n- Có hợp đồng lao động hoặc giấy phép kinh doanh\n"
            "## Hồ sơ cần thiết\n- Hợp đồng lao động (nếu là người đi làm)\n")


@pytest.mark.parametrize("luot, dien", [
    (["anh muốn vay", "anh làm tự do"], "tu_do"),
    (["chị buôn bán ngoài chợ"], "tu_do"),
    (["tôi không có hợp đồng lao động"], "tu_do"),
    (["em đi làm công ty"], "di_lam"),
    (["anh có hợp đồng lao động rồi"], "di_lam"),
    # Lượt GẦN NHẤT nói về việc làm thắng lượt cũ.
    (["anh làm tự do", "à nhầm, anh là nhân viên công ty"], "di_lam"),
    (["trước anh làm công ty giờ ra buôn bán"], ""),   # nêu cả hai: không đoán
    (["anh muốn trả nợ tự do được không"], ""),         # "tự do" không phải việc làm
    ([], ""),
])
def test_dien_khach_theo_luot_gan_nhat(luot, dien):
    assert dien_khach(luot) == dien


@pytest.mark.parametrize("nguoi_khac", [
    "vợ anh là nhân viên công ty",
    "bạn anh làm ở công ty",
])
def test_nghe_cua_nguoi_khac_khong_ghi_de_dien_cua_khach(nguoi_khac):
    truoc = ["anh làm tự do", nguoi_khac]
    assert dien_khach(truoc) == "tu_do"
    assert cau_hoi_cho_kho("thế cần giấy tờ gì", truoc) == "làm tự do cần giấy tờ gì"


@pytest.mark.parametrize("luot", [
    "vợ anh là nhân viên công ty, còn anh làm tự do",
    "anh làm tự do, còn vợ anh là nhân viên công ty",
    "Anh làm tự do...    vợ anh là nhân viên công ty",
    "VỢ ANH là NHÂN VIÊN công ty!!! ;;; còn ANH làm TỰ DO",
])
def test_cung_luot_chi_lay_cum_viec_lam_cua_chinh_khach(luot):
    assert dien_khach([luot]) == "tu_do"


def test_khach_noi_ro_minh_la_nhan_vien_van_cap_nhat_di_lam():
    assert dien_khach(["anh làm tự do", "à không, anh là nhân viên công ty"]) == "di_lam"


def test_hoi_giay_to_sau_khi_noi_lam_tu_do_thi_ghep_dien_vao_cau_tra_kho():
    truoc = ["anh muốn vay", "anh làm tự do"]
    assert cau_hoi_cho_kho("thế cần giấy tờ gì", truoc) == "làm tự do cần giấy tờ gì"
    assert cau_hoi_cho_kho("hồ sơ gồm những gì em", truoc) == "làm tự do hồ sơ gồm những gì em"
    assert cau_hoi_cho_kho("vậy thì anh cần chuẩn bị gì", truoc).startswith("làm tự do anh cần")


@pytest.mark.parametrize("cau, truoc", [
    ("thế cần giấy tờ gì", ["anh muốn vay"]),                     # chưa nói diện
    ("thế cần giấy tờ gì", ["em đi làm công ty"]),                # đi làm công
    ("thế cần giấy tờ gì", ["anh làm tự do", "à anh là nhân viên công ty"]),
    ("anh buôn bán tự do, cần giấy tờ gì", ["anh làm tự do"]),    # lượt này tự nêu diện
    ("hồ sơ bao lâu thì duyệt", ["anh làm tự do"]),               # hỏi thời gian
    ("lãi suất bao nhiêu", ["anh làm tự do"]),                    # không hỏi giấy tờ
])
def test_cac_truong_hop_khong_duoc_ghep(cau, truoc):
    assert cau_hoi_cho_kho(cau, truoc) == cau


@pytest.mark.parametrize("cau, noi_tiep", [
    ("anh làm tự do", False),                 # "tự do" có chữ "do", không phải "đó"
    ("làm tự do cần giấy tờ gì", False),
    ("hôm nay lãi bao nhiêu", False),         # "nay" không phải "này"
    ("cái đó lãi bao nhiêu", True),
    ("gói này phí bao nhiêu", True),
    ("goi nay phi bao nhieu", True),          # gõ không dấu: giữ cách xét cũ
])
def test_chu_chi_tro_xet_tren_chu_co_dau(cau, noi_tiep):
    assert _is_follow_up(cau) is noi_tiep


def test_cum_lai_duoc_doi_ve_dung_cum_cua_tai_lieu():
    ra, sua = sua_thuat_ngu_lai(
        "Dạ anh có thu nhập ổn định và hợp đồng kinh doanh thì em kiểm tra giúp ạ.", TAI_LIEU)
    assert "giấy phép kinh doanh" in ra and "hợp đồng kinh doanh" not in ra and sua
    dau, _ = sua_thuat_ngu_lai("Hợp đồng kinh doanh là bắt buộc ạ.", TAI_LIEU)
    assert dau.startswith("Giấy phép kinh doanh")


def test_khong_doi_khi_tai_lieu_khong_lam_can_cu_duoc():
    cau = "Dạ anh cần hợp đồng kinh doanh ạ."
    # Tài liệu thật sự có cụm đó, hoặc không có cụm đúng để đổi sang: để nguyên.
    assert sua_thuat_ngu_lai(cau, TAI_LIEU + "- Hợp đồng kinh doanh với đối tác\n") == (cau, None)
    assert sua_thuat_ngu_lai(cau, "## Thẻ tín dụng\n- Phí thường niên") == (cau, None)
    assert sua_thuat_ngu_lai("Dạ anh cần hợp đồng lao động ạ.", TAI_LIEU)[1] is None
