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


# --- Lọt tiếng ANH: 7B mắc nhiều hơn 3B mắc tiếng Trung -------------------

def test_cat_duoi_tieng_anh():
    # Đo thật 08-08, qwen2.5:7b, 2/36 lượt (5.6%) - dày hơn ca chữ Trung của 3B.
    ra, dinh = chan_chu_ngoai(
        "Hạn mức vay tín chấp lên đến 500 triệu đồng. "
        "Dependent on your income and other factors, the actual amount may vary.")
    assert ra == "Hạn mức vay tín chấp lên đến 500 triệu đồng."
    assert dinh and dinh.startswith("Dependent")


def test_giu_ma_giay_to_va_ten_rieng():
    # CMND/CCCD/KT3/CIC/ABC la chu ASCII hop le trong cau tieng Viet.
    cau = "Anh chuẩn bị CMND hoặc CCCD, hộ khẩu hoặc KT3, và tra CIC nhé"
    assert chan_chu_ngoai(cau)[0] == cau


def test_giu_cau_tieng_viet_co_vai_tu_anh_le():
    cau = "Bên em có gói combo ưu đãi cho anh chị ạ"
    assert chan_chu_ngoai(cau)[0] == cau


def test_cat_ca_chu_han_lan_tieng_anh_trong_mot_cau():
    ra, _ = chan_chu_ngoai("Dạ vâng ạ. 复印件 and your income are needed for this")
    assert "复印件" not in ra and "income" not in ra
    assert ra.startswith("Dạ vâng ạ")


def test_bo_ca_dau_cau_toan_rong():
    # Thiếu dải U+3000-303F thì cắt chữ Hán xong còn sót "，。" giữa câu.
    ra, _ = chan_chu_ngoai("Dạ vâng ạ.关于汽车贷款，我们暂时没有提供。")
    assert "，" not in ra and "。" not in ra
    assert ra == "Dạ vâng ạ."
