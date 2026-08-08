"""Ép cách AI GỌI KHÁCH, không chỉ cách nó tự xưng.

Vì sao có file này: đo 08-08 khi đổi sang qwen2.5:3b, mô hình gọi khách là
"bạn" ở 4/9 lượt ("Bạn có thể vay tối đa..."). Với tổng đài ngân hàng gọi cho
khách thì "bạn" sai vai. `sua_xung_ho` bản cũ chỉ sửa "tôi"->"em", tức chỉ lo
cách AI tự xưng, nên "bạn" lọt lưới.
"""
from backend.pipeline.text_normalizer import sua_xung_ho


def test_ban_thanh_anh_chi_mac_dinh():
    assert sua_xung_ho("Bạn có thể vay tối đa 500 triệu") \
        == "Anh chị có thể vay tối đa 500 triệu"


def test_giu_nguyen_chu_hoa_thuong():
    assert sua_xung_ho("khoản vay của bạn") == "khoản vay của anh chị"


def test_dung_dai_tu_theo_gioi_tinh():
    assert sua_xung_ho("Bạn cần giấy tờ gì", goi_khach="anh") \
        == "Anh cần giấy tờ gì"
    assert sua_xung_ho("của bạn", goi_khach="chị") == "của chị"


def test_khong_dung_vao_ban_be_ban_hang():
    assert sua_xung_ho("giới thiệu bạn bè") == "giới thiệu bạn bè"
    assert sua_xung_ho("bạn hàng lâu năm") == "bạn hàng lâu năm"


def test_van_giu_hanh_vi_cu():
    assert sua_xung_ho("Tôi sẽ kiểm tra") == "Em sẽ kiểm tra"
    assert sua_xung_ho("chúng tôi có ưu đãi") == "bên em có ưu đãi"
