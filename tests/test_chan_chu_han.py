"""Chặn chữ Hán/Nhật/Hàn lọt vào câu đọc cho khách.

Vì sao cần: qwen2.5 là model Trung Quốc. Đo 08-08 trên qwen2.5:3b, nó trả lời
"CMND hoặc CCCD bản chính và 复印件" - chữ Hán nghĩa là "bản photo". F5-TTS
không đọc được, khách nghe ra tiếng lạ giữa câu tư vấn ngân hàng.

Lưới này chạy bất kể dùng model nào: 7B cũng có thể lọt, chỉ là hiếm hơn.
"""
from backend.pipeline.text_normalizer import chan_chu_ngoai


def test_bo_chu_han_giua_cau():
    ra, dinh = chan_chu_ngoai("CMND bản chính và 复印件, Hộ khẩu")
    assert "复印件" not in ra
    assert dinh == "复印件"
    assert ra == "CMND bản chính và, Hộ khẩu"


def test_cau_sach_thi_giu_nguyen():
    ra, dinh = chan_chu_ngoai("Lãi suất 7.9% một năm ạ")
    assert ra == "Lãi suất 7.9% một năm ạ"
    assert dinh is None


def test_khong_dung_vao_tieng_viet_co_dau():
    cau = "Anh chị chuẩn bị hồ sơ giúp em nhé, gồm sổ hộ khẩu"
    assert chan_chu_ngoai(cau)[0] == cau


def test_bo_ca_cum_nhieu_chu():
    ra, dinh = chan_chu_ngoai("giấy tờ 身份证明 kèm theo")
    assert "身份证明" not in ra
    assert dinh == "身份证明"


def test_khong_de_lai_khoang_trang_doi():
    ra, _ = chan_chu_ngoai("giấy tờ 复印件 kèm theo")
    assert "  " not in ra
    assert ra == "giấy tờ kèm theo"
