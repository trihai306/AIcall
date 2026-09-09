"""Trích cặp (thuộc tính, giá trị) - nền của lưới chặn số sai chủ thể.

Vì sao không dùng embedding: đo 08-09-2026 trên 20 câu đối chứng, cosine cho câu
ĐÚNG 0,02-0,46 và câu BỊA 0,03-0,33 - hai dải chồng lấn, không ngưỡng nào tách
được. Embedding đo CÙNG CHỦ ĐỀ chứ không đo ĐÚNG/SAI: với nó "lãi suất 5%" và
"lãi suất 7.9%" gần như đồng nghĩa.
"""
from backend.pipeline.thuoc_tinh import (THUOC_TINH_MAC_DINH, cap_trong,
                                         chan_thuoc_tinh_sai, chuan_so)


def test_chuan_so_khong_an_so_khong_cua_hang_tram():
    """`"500".rstrip("0")` cho `"5"` - đã mắc, làm tài liệu đọc ra 'hạn mức 5 triệu'."""
    assert chuan_so("500") == "500"
    assert chuan_so("7,9") == "7.9"
    assert chuan_so("7.90") == "7.9"


def test_trich_duoc_lai_suat():
    assert cap_trong("Lãi suất từ 7.9% một năm", THUOC_TINH_MAC_DINH) == [("lãi suất", "7.9", "%")]


def test_so_thap_phan_bi_tach_van_trich_dung():
    """Bản ghi lời AI có "từ 7. 9%" - không dán lại thì trích ra 9% và chặn oan."""
    assert cap_trong("Lãi suất từ 7. 9% một năm", THUOC_TINH_MAC_DINH) == [("lãi suất", "7.9", "%")]


def test_tu_khoa_nam_sau_so_van_nhan_ra():
    """"trên 70 tuổi" - từ khoá đứng SAU số."""
    assert cap_trong("Khách trên 70 tuổi vẫn vay được", THUOC_TINH_MAC_DINH) == [("tuổi", "70", "tuổi")]


def test_khong_co_tu_khoa_thi_khong_trich():
    assert cap_trong("Anh chờ em 5 phút nhé", THUOC_TINH_MAC_DINH) == []


def test_doc_gia_tri_tu_tai_lieu():
    """Giá trị đúng ĐỌC TỪ TÀI LIỆU, không viết cứng - sửa tài liệu là lưới đổi theo."""
    from backend.pipeline.thuoc_tinh import gia_tri_tai_lieu
    tl = "- Lãi suất: từ 7.9%/năm\n- Hạn mức: lên đến 500 triệu đồng\n"
    kho = gia_tri_tai_lieu(tl, THUOC_TINH_MAC_DINH)
    assert kho["lãi suất"] == {("7.9", "%")}
    assert kho["hạn mức"] == {("500", "triệu")}


def test_tai_lieu_rong_thi_kho_rong():
    from backend.pipeline.thuoc_tinh import gia_tri_tai_lieu
    assert gia_tri_tai_lieu("", THUOC_TINH_MAC_DINH) == {}


# --- Fix round 1: 3 lỗi đã xác nhận thực nghiệm ---

def test_bug1_han_muc_truoc_thu_nhap_khong_bi_vao_nham():
    """Bug 1: 'Hạn mức 500 triệu, thu nhập từ 5 triệu' — từ khoá gần nhất phải thắng.

    Nếu code lấy kết quả đầu tiên trong dict (lãi suất → hạn mức → thời hạn → ...)
    thì 5 triệu bị gán cho hạn mức thay vì thu nhập vì 'hạn mức' xuất hiện trong
    cửa sổ ±60 ký tự xung quanh số 5.
    """
    cau = "Hạn mức 500 triệu, thu nhập từ 5 triệu mỗi tháng"
    ket_qua = cap_trong(cau, THUOC_TINH_MAC_DINH)
    assert ("hạn mức", "500", "triệu") in ket_qua
    assert ("thu nhập", "5", "triệu") in ket_qua


def test_bug2_thu_nhap_truoc_han_muc_khong_bi_vao_nham():
    """Bug 2: 'Thu nhập 10 triệu thì hạn mức 300 triệu' — thứ tự đảo vẫn đúng.

    Như bug 1 nhưng từ khoá xuất hiện theo thứ tự ngược lại.
    """
    cau = "Thu nhập 10 triệu thì hạn mức 300 triệu ạ"
    ket_qua = cap_trong(cau, THUOC_TINH_MAC_DINH)
    assert ("thu nhập", "10", "triệu") in ket_qua
    assert ("hạn mức", "300", "triệu") in ket_qua


def test_bug3_dai_so_bat_ca_hai_dau():
    """Bug 3: '12 - 60 tháng' — regex chỉ bắt '60', bỏ sót '12'.

    Dải số dạng 'N - M <đơn-vị>' phải cho ra cả hai số với cùng đơn vị.
    """
    cau = "- Thời hạn: 12 - 60 tháng"
    ket_qua = cap_trong(cau, THUOC_TINH_MAC_DINH)
    assert ("thời hạn", "12", "tháng") in ket_qua
    assert ("thời hạn", "60", "tháng") in ket_qua


def test_gia_tri_khop_thi_cho_qua():
    from backend.pipeline.thuoc_tinh import chan_thuoc_tinh_sai
    tl = "- Lãi suất: từ 7.9%/năm\n"
    ra, sua = chan_thuoc_tinh_sai("Lãi suất từ 7.9% một năm ạ", tl, THUOC_TINH_MAC_DINH)
    assert sua is None and ra == "Lãi suất từ 7.9% một năm ạ"


def test_gia_tri_lech_thi_bao_lech():
    from backend.pipeline.thuoc_tinh import chan_thuoc_tinh_sai
    tl = "- Lãi suất: từ 7.9%/năm\n"
    _, sua = chan_thuoc_tinh_sai("Lãi suất chỉ 5% một năm ạ", tl, THUOC_TINH_MAC_DINH)
    assert sua is not None and "lãi suất" in sua and "5" in sua


def test_so_do_KHACH_neu_thi_khong_chan():
    """AI nhắc lại số của khách là ĐÚNG. Cùng ranh giới `so_can_cu` đã đặt."""
    from backend.pipeline.thuoc_tinh import cap_trong, chan_thuoc_tinh_sai
    tl = "- Hạn mức: lên đến 500 triệu đồng\n"
    # Câu thử PHẢI trích được cặp, không thì test xanh vì `cap_trong` trả rỗng
    # chứ không phải vì lưới nhận ra số đó của khách.
    assert cap_trong("Hạn mức anh cần là 400 triệu ạ", THUOC_TINH_MAC_DINH)
    _, sua = chan_thuoc_tinh_sai("Hạn mức anh cần là 400 triệu ạ", tl, THUOC_TINH_MAC_DINH,
                                 khach_noi="anh muốn vay tầm 400 triệu")
    assert sua is None


def test_ty_va_trieu_quy_doi_duoc():
    from backend.pipeline.thuoc_tinh import chan_thuoc_tinh_sai
    tl = "- Hạn mức: lên đến 10 tỷ đồng\n"
    _, sua = chan_thuoc_tinh_sai("Hạn mức lên đến 10000 triệu đồng ạ", tl, THUOC_TINH_MAC_DINH)
    assert sua is None


def test_thuoc_tinh_KHONG_CO_trong_tai_lieu_thi_khong_phan():
    """Tài liệu không nói gì về thuộc tính đó thì lưới này im - việc của lưới NLI."""
    from backend.pipeline.thuoc_tinh import chan_thuoc_tinh_sai
    _, sua = chan_thuoc_tinh_sai("Miễn lãi 45 ngày ạ", "- Lãi suất: từ 7.9%/năm\n",
                                 THUOC_TINH_MAC_DINH)
    assert sua is None


def test_van_ban_KHONG_bi_thay_ca_cau():
    """Ràng buộc lõi: lưới trả về mô tả để chỗ gọi xử lý, KHÔNG tự thay câu."""
    from backend.pipeline.thuoc_tinh import chan_thuoc_tinh_sai
    goc = "Lãi suất chỉ 5% một năm ạ"
    ra, _ = chan_thuoc_tinh_sai(goc, "- Lãi suất: từ 7.9%/năm\n", THUOC_TINH_MAC_DINH)
    assert ra == goc


def test_loi_khach_TRICH_DUOC_cap_thi_khong_no():
    """`cap_trong` trả BỘ BA (tên, số, đơn vị) - đọc thành bộ đôi là nổ giữa cuộc gọi.

    Test cũ dùng lời khách "anh muốn vay tầm 400 triệu", câu này KHÔNG có từ khoá
    nào nên `cap_trong` trả rỗng và vòng lặp không chạy - lỗi giải nén không lộ.
    Bộ chấm trên 250 lượt thật mới bắt được. Lời khách ở đây phải trích ĐƯỢC cặp.
    """
    from backend.pipeline.thuoc_tinh import cap_trong, chan_thuoc_tinh_sai
    khach = "hạn mức của anh là 400 triệu"
    assert cap_trong(khach, THUOC_TINH_MAC_DINH), "câu thử phải trích được cặp"
    ra, sua = chan_thuoc_tinh_sai("Hạn mức lên đến 400 triệu ạ",
                                  "- Hạn mức: lên đến 500 triệu đồng\n",
                                  THUOC_TINH_MAC_DINH, khach_noi=khach)
    assert sua is None, "số do khách nêu thì không được chặn"


# --- Ba lỗi đo được trên 60 câu hỏi thật, 09-09-2026 ------------------------
# Chấm tay 20 lượt lưới đánh dấu: chỉ 8 là bịa thật, 12 là CHẶN OAN. Bật chặn
# với tỉ lệ đó là chặn nhầm nhiều hơn chặn đúng. Ba nhóm dưới đây là toàn bộ
# nguyên nhân của 12 lượt oan ấy.

def test_so_NAM_TRONG_DAI_cua_tai_lieu_thi_khong_chan():
    """Tài liệu ghi "12 - 60 tháng" là một KHOẢNG, không phải hai giá trị rời.

    Câu thật bị chặn oan: "vay 300 triệu trong 36 tháng thì mỗi tháng trả
    khoảng 8.2 triệu". 36 nằm GIỮA 12 và 60, tức đúng tài liệu. Dính ở cả bốn
    cấu hình nạp ngữ cảnh đã thử, nên đây là nguồn oan lớn nhất.
    """
    doc = "- Thời hạn: 12 - 60 tháng"
    _, sua = chan_thuoc_tinh_sai("Dạ vay trong thời hạn 36 tháng ạ.", doc,
                                 THUOC_TINH_MAC_DINH)
    assert sua is None, f"36 nằm trong dải 12-60 mà vẫn bị chặn: {sua}"


def test_so_NGOAI_DAI_van_bi_chan():
    """Nới cho số trong dải KHÔNG được nới luôn cho số ngoài dải."""
    doc = "- Thời hạn: 12 - 60 tháng"
    _, sua = chan_thuoc_tinh_sai("Dạ vay trong thời hạn 72 tháng ạ.", doc,
                                 THUOC_TINH_MAC_DINH)
    assert sua is not None, "72 ngoài dải 12-60 mà lọt"


def test_dai_trong_cau_AI_thuoc_ve_MOT_thuoc_tinh():
    """Hai đầu của một dải luôn cùng một thuộc tính - đừng xét riêng từng đầu.

    Câu thật: đầu dải 30 gần "hạn mức" nên vào đúng, còn đầu kia 200 lại gần
    "thu nhập" hơn nên bị gán sang thu nhập rồi báo lệch.
    """
    cau = "Hạn mức thẻ Gold là từ 30 đến 200 triệu đồng, phù hợp với thu nhập của anh."
    ten = {t for t, _, _ in cap_trong(cau, THUOC_TINH_MAC_DINH)}
    assert ten == {"hạn mức"}, f"hai đầu dải phải cùng thuộc tính, đang ra {ten}"


def test_mot_tu_khoa_khong_vo_lay_hai_con_so():
    """Một lần xuất hiện của từ khoá chỉ nhận MỘT cụm số - cụm gần nhất.

    Câu thật, hoàn toàn đúng tài liệu, vẫn bị chặn: "Với thu nhập ổn định từ 5
    triệu đồng/tháng trở lên, anh/chị có thể xin vay đến 500 triệu đồng." Chữ
    "thu nhập" là từ khoá DUY NHẤT trong câu nên nó vơ cả 500 triệu - vốn là
    hạn mức - rồi báo "thu nhập 500 triệu, tài liệu ghi 5 triệu".
    """
    cau = ("Với thu nhập ổn định từ 5 triệu đồng/tháng trở lên, "
           "anh/chị có thể xin vay đến 500 triệu đồng.")
    cap = cap_trong(cau, THUOC_TINH_MAC_DINH)
    assert ("thu nhập", "5", "triệu") in cap, "vẫn phải bắt được thu nhập 5 triệu"
    assert not [x for x in cap if x[1] == "500"], (
        f"500 triệu không có từ khoá của mình thì phải bỏ qua, đang ra {cap}")


def test_ty_le_cho_vay_khong_phai_lai_suat():
    """"80% giá trị bất động sản" là tỷ lệ cho vay, không phải lãi suất."""
    cau = ("Dạ lãi suất vay mua nhà từ 6.5% trong 2 năm đầu ạ. Sau đó thả nổi "
           "từ 8-10% năm. Em có thể vay tối đa 80% giá trị bất động sản.")
    cap = cap_trong(cau, THUOC_TINH_MAC_DINH)
    assert ("lãi suất", "80", "%") not in cap, f"80% bị đọc thành lãi suất: {cap}"
    assert ("lãi suất", "6.5", "%") in cap, "vẫn phải bắt được lãi suất thật"


def test_hoan_tien_khong_phai_lai_suat():
    """"hoàn tiền 3%" là ưu đãi hoàn tiền, không phải lãi suất."""
    cau = "Dạ lãi suất 0% trả góp, và thẻ được hoàn tiền 3% cho mọi giao dịch ạ."
    cap = cap_trong(cau, THUOC_TINH_MAC_DINH)
    assert ("lãi suất", "3", "%") not in cap, f"3% hoàn tiền bị đọc thành lãi suất: {cap}"
