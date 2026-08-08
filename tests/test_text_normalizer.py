"""Chuẩn hoá chữ trước khi giao cho F5.

Hai nhóm ở đây đều xuất phát từ 5 bản ghi khách gửi về 2026-08-08 ("Check giọng
/ Heu 1"): khách than đọc giãn cách, lắp từ, đọc sai từ - và cả 5 lần lỗi đều rơi
đúng một chỗ trong kịch bản.
"""

from backend.pipeline.text_normalizer import normalize_for_tts


# --- chuỗi dấu chấm ----------------------------------------------------------
# F5 cấp thời lượng audio theo SỐ BYTE UTF-8 của chữ (utils_infer.py:470), nên
# mỗi dấu chấm thừa là một khoảng thời gian được cấp mà không có chữ nào để đọc.
# Model lấp chỗ trống bằng cách kéo giãn âm tiết rồi bịa một âm ở đuôi.
# Đo trên giọng khách đang dùng: có "......" thì 6/6 lần đẻ âm rác ("bên em i",
# "bên em nhìm"), thay bằng một dấu chấm thì 0/6.

def test_gop_chuoi_dau_cham_ve_mot():
    assert normalize_for_tts("bên em...... không biết") == "bên em. không biết"


def test_gop_ca_khi_chi_co_hai_dau_cham():
    assert normalize_for_tts("dạ.. vâng") == "dạ. vâng"


def test_gop_dau_ba_cham_unicode():
    # "…" là MỘT ký tự nhưng 3 byte - đắt ngang ba dấu chấm rời.
    assert normalize_for_tts("bên em… không biết") == "bên em. không biết"


def test_gop_ca_dau_hoi_va_dau_than_lap():
    # Cùng một cơ chế: byte thừa nào cũng là thời lượng được cấp mà không có chữ.
    assert normalize_for_tts("thế nào ạ?? em nghe") == "thế nào ạ? em nghe"
    assert normalize_for_tts("hay quá!! anh chị") == "hay quá! anh chị"


def test_khong_dung_toi_dau_phan_cach_nghin():
    # Guard THỨ TỰ: tiền tiếng Việt viết "142.500.000". Gộp dấu chấm phải chạy
    # SAU khi đọc số thành chữ, không thì "142.500.000" vỡ thành hai con số rời.
    assert (normalize_for_tts("dư nợ 142.500.000 đồng")
            == "dư nợ một trăm bốn mươi hai triệu năm trăm nghìn đồng")


# --- tên thương hiệu viết hoa-thường lẫn lộn ---------------------------------
# _ACRONYM_RE chỉ bắt cụm TOÀN HOA nên "VPBank" lọt lưới: F5 nhận nguyên chuỗi
# "vpbank" và đoán bừa - đo 15/15 lần sai, mỗi lần một kiểu ("pháp banh",
# "vấp banh", "việt bang", "vạc banh"). Tách "VP" ra đánh vần rồi để "bank"
# nguyên thì đọc đúng và ổn định.

def test_danh_van_phan_viet_tat_cua_ten_thuong_hieu():
    assert normalize_for_tts("ngân hàng VPBank.") == "ngân hàng vê pê bank."


def test_ap_dung_cho_ngan_hang_khac():
    assert normalize_for_tts("ngân hàng TPBank.") == "ngân hàng tê pê bank."


def test_khong_dung_toi_tu_chi_hoa_mot_chu_dau():
    # "Macbook" chỉ có MỘT chữ hoa đầu - không phải viết tắt dính đuôi.
    assert normalize_for_tts("máy Macbook") == "máy macbook"
