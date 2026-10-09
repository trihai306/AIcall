"""Trọng tài bằng luật của chế độ hai vai Qwen đối thoại."""
from backend.services import answer_bank_selfask as sa

NGUON = ("# Vay tín chấp\n- Lãi suất: từ 7.9%/năm\n- Hạn mức: lên đến 500 triệu đồng\n"
         "- Giải ngân: trong vòng 24 giờ sau khi phê duyệt\n")


def test_dap_an_co_can_cu_nguyen_van_thi_dat():
    item, why = sa._cham_luot(
        "Lãi suất vay tín chấp là bao nhiêu em?",
        "Dạ lãi suất vay tín chấp từ 7.9% một năm ạ. ||| Lãi suất: từ 7.9%/năm", NGUON)
    assert why == "" and item["cau_hoi"] == ["Lãi suất vay tín chấp là bao nhiêu em?"]
    assert item["evidence"] == "Lãi suất: từ 7.9%/năm"


def test_tu_van_bao_khong_co_thi_khong_luu():
    assert sa._cham_luot("Làm nghề tự do có vay tín chấp được không?", "KHONG_CO", NGUON) == (
        None, "tài liệu không có")


def test_can_cu_bia_hoac_so_ngoai_tai_lieu_bi_loai():
    _, why = sa._cham_luot("Phí trả nợ trước hạn vay tín chấp bao nhiêu?",
                           "Dạ phí trả trước hạn là 2% ạ. ||| Phí trả trước hạn: 2%", NGUON)
    assert why == "căn cứ không có nguyên văn trong tài liệu"
    _, why = sa._cham_luot("Lãi suất vay tín chấp là bao nhiêu em?",
                           "Dạ lãi suất chỉ 6.5% một năm ạ. ||| Lãi suất: từ 7.9%/năm", NGUON)
    assert "số không nằm trong nguồn" in why


def test_cau_hoi_noi_tiep_hoac_tra_loi_ne_tranh_bi_loai():
    _, why = sa._cham_luot("Thế còn hạn mức thì sao?",
                           "Dạ hạn mức lên đến 500 triệu đồng ạ. ||| Hạn mức: lên đến 500 triệu đồng", NGUON)
    assert why == "câu hỏi không tự đủ nghĩa"
    _, why = sa._cham_luot("Hạn mức vay tín chấp tối đa bao nhiêu?",
                           "Dạ anh chị xem chi tiết trong tài liệu sản phẩm ạ. ||| Hạn mức: lên đến 500 triệu đồng",
                           NGUON)
    assert why == "trả lời né tránh"
    _, why = sa._cham_luot("Hạn mức vay tín chấp tối đa bao nhiêu?", "Dạ 500 triệu ạ.", NGUON)
    assert why == "sai mẫu trả lời"


def test_luat_hai_vai_noi_ro_dieu_cam():
    assert "KHONG_CO" in sa.LUAT_TU_VAN and "CHÉP NGUYÊN VĂN" in sa.LUAT_TU_VAN
    assert "TỰ ĐỦ NGHĨA" in sa.LUAT_KHACH and len(sa.VAI_KHACH) >= 5


def test_doi_thuong_dat_khi_lich_su_khong_du_kien():
    item, why = sa._cham_doi_thuong(
        "Dạo này anh làm ăn khó quá em ạ",
        "Dạ em hiểu ạ, giai đoạn này nhiều anh chị cũng vất vả. Anh chị cứ tham khảo thông tin thôi ạ.")
    assert why == "" and item["evidence"] == ""


def test_doi_thuong_cam_con_so_du_kien_va_loi_hua():
    for cau in ("Dạ lãi suất bên em chỉ từ 7.9% thôi ạ.",
                "Dạ anh chị yên tâm, hồ sơ chắc chắn được duyệt ạ.",
                "Dạ em sẽ gửi tin nhắn cho anh chị ngay ạ.",
                "Dạ bên em đang có ưu đãi lớn ạ."):
        item, why = sa._cham_doi_thuong("Nghe cũng được đấy em nhỉ", cau)
        assert item is None and why.startswith("nêu dữ kiện hoặc lời hứa"), cau
    assert sa._cham_doi_thuong("Nghe cũng được đấy em nhỉ", "Vâng anh.")[1] == "không mở đầu bằng Dạ"
    assert sa._cham_doi_thuong("ừ", "Dạ vâng ạ.")[1] == "lời khách quá ngắn hoặc có số"


def test_doi_thuong_loai_lac_vai_va_cho_phep_xin_loi():
    ok, why = sa._cham_doi_thuong("Sao gọi hoài vậy, phiền quá",
                                  "Dạ em xin lỗi đã làm phiền anh chị ạ. Em xin ghi nhận ạ.")
    assert why == "" and ok is not None
    for khach in ("Chào em, dạo này khỏe không", "Anh muốn biết gói vay em vừa nhắc đến",
                  "Xong việc là cháu gọi lại ngay cho em"):
        assert sa._cham_doi_thuong(khach, "Dạ vâng ạ.")[1] == "lời khách lạc vai hoặc hỏi sản phẩm"
    for tra_loi in ("Dạ anh chị cảm ơn ạ, em rất vui ạ.", "Dạ em sẽ liên hệ lại khi khách hàng rảnh ạ.",
                    "Dạ chúc bác sớm khỏe mạnh ạ."):
        assert sa._cham_doi_thuong("Bữa nay mệt quá em ơi", tra_loi)[0] is None
