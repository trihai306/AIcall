"""Behavioral assertions on the answer, not merely source-code strings."""
import pytest
from backend.pipeline.tra_loi_khoan_vay import tra_loi

DOC = """# Vay tín chấp
## Thông tin
- Hạn mức: 500 triệu đồng
- Lãi suất: từ 7.9%/năm
- Thời hạn: 12 - 60 tháng
## Hồ sơ
- CCCD
- Sao kê lương
"""


@pytest.mark.parametrize("new", [75, 135, 275, 350, 425, 499, 725])
def test_new_numbers_never_use_old_rejection(new):
    history = [{"role": "user", "content": "anh vay 850 triệu trong 24 tháng"}]
    unclear = f"anh muốn vay {new} trong vòng mười hai tháng thì mỗi tháng bao nhiêu"
    answer = tra_loi(unclear, DOC, history=history)
    assert answer and answer[0] == "xac_nhan_don_vi_vay"
    assert "850" not in answer[1]
    history += [{"role": "user", "content": unclear},
                {"role": "assistant", "content": answer[1]},
                {"role": "user", "content": "triệu"}]
    answer = tra_loi("mỗi tháng đóng bao nhiêu", DOC, history=history)
    assert answer and str(new) in answer[1] and "850" not in answer[1]
    assert answer[0] == ("tinh_tra_gop" if new <= 500 else "vuot_han_muc")


def test_bare_correction_and_calc_followup_stay_pending():
    history = [{"role": "user", "content": "anh vay 800 triệu trong 12 tháng"},
               {"role": "user", "content": "anh vay 275"}]
    answer = tra_loi("tính đi", DOC, history=history)
    assert answer[0] == "xac_nhan_don_vi_vay" and "800" not in answer[1]


def test_income_does_not_preempt_mixed_loan_question():
    answer = tra_loi("lương anh 18 triệu một tháng và anh vay 275 triệu trong 24 tháng mỗi tháng đóng bao nhiêu", DOC)
    assert answer[0] == "tinh_tra_gop"
    assert "275 triệu" in answer[1] and "24 tháng" in answer[1]


def test_latest_recall_does_not_revert_to_old_complete_pair():
    history = [{"role": "user", "content": "anh vay 450 triệu trong 12 tháng"},
               {"role": "user", "content": "anh vay 275 triệu"},
               {"role": "user", "content": "đổi sang 36 tháng"}]
    answer = tra_loi("nhắc lại số tiền và kỳ hạn hiện tại", DOC, history=history)
    assert answer[0] == "nhac_lai_nhu_cau"
    assert "275 triệu" in answer[1] and "36 tháng" in answer[1]


def test_ambiguous_multiple_amounts_do_not_make_a_financial_claim():
    answer = tra_loi("anh vay 250 triệu hay 350 triệu trong 24 tháng mỗi tháng bao nhiêu", DOC)
    assert answer[0] == "xac_nhan_so_tien_vay"


def test_no_salary_payment_method_invented():
    answer = tra_loi("lương anh 18 triệu một tháng", DOC)
    assert "18 triệu" in answer[1] and "chuyển khoản" not in answer[1]


def test_unit_answer_continues_pending_calculation():
    history = [{"role": "user", "content": "anh muốn vay 275 trong 24 tháng mỗi tháng đóng bao nhiêu"}]
    answer = tra_loi("triệu", DOC, history=history)
    assert answer[0] == "tinh_tra_gop"
    assert "275 triệu" in answer[1] and "24 tháng" in answer[1]


def test_fractional_principal_is_not_rounded_to_another_amount():
    answer = tra_loi("anh muốn vay 275,125 triệu", DOC)
    assert "275,125 triệu" in answer[1]


def test_calculation_followup_when_customer_supplied_both_units():
    history = [{"role": "user", "content": "anh vay 275 triệu trong 24 tháng"}]
    answer = tra_loi("ờ tính đi", DOC, history=history)
    assert answer[0] == "tinh_tra_gop"


def test_original_recall_is_distinct_from_current_request():
    history = [{"role": "user", "content": "anh vay 450 triệu trong 12 tháng"},
               {"role": "user", "content": "anh vay 275 triệu trong 36 tháng"}]
    original = tra_loi("nhắc lại số tiền và kỳ hạn anh nói lúc đầu", DOC, history=history)
    current = tra_loi("nhắc lại số tiền và kỳ hạn hiện tại", DOC, history=history)
    assert "450 triệu" in original[1] and "12 tháng" in original[1]
    assert "275 triệu" in current[1] and "36 tháng" in current[1]


@pytest.mark.parametrize("question", ["hợp đồng cũ mỗi tháng trả bao nhiêu", "dư nợ của anh còn bao nhiêu"])
def test_existing_contract_question_does_not_calculate_new_loan(question):
    history = [{"role": "user", "content": "anh vay 275 triệu trong 24 tháng"}]
    assert tra_loi(question, DOC, history=history) is None


def test_cancelled_request_cannot_fall_back_to_llm_calculation():
    history = [{"role": "user", "content": "anh vay 275 triệu trong 24 tháng"},
               {"role": "user", "content": "không vay nữa"}]
    answer = tra_loi("tính đi", DOC, history=history)
    assert answer[0] == "thieu_du_kien_tinh_lai"
    assert "275" not in answer[1]


def test_clarification_does_not_depend_on_product_document():
    history = [{"role": "user", "content": "anh vay 850 triệu"}]
    answer = tra_loi("anh vay 275", "", history=history)
    assert answer[0] == "xac_nhan_don_vi_vay" and "850" not in answer[1]


# --- Dữ kiện mơ hồ KHÔNG được dính sang lượt sau -----------------------------
#
# Cuộc gọi 7db3f780: sau một lần "ba sáu tháng" không đọc được, mọi lượt có chữ
# "vay" đều bị hỏi lại "muốn vay bao nhiêu tháng", kể cả "nợ tất toán trên một
# năm thì có vay được không" và "có vay hơn năm trăm triệu được không".
def test_ky_han_mo_ho_luot_truoc_khong_chan_cau_hoi_khac():
    history = [
        {"role": "user", "content": "vay trong hai ba tháng"},
        {"role": "assistant", "content": "Dạ anh chị muốn vay trong bao nhiêu tháng hoặc năm ạ?"},
    ]
    got = tra_loi("nợ tất toán trên một năm thì có vay được không", DOC, history=history)
    assert not got or got[0] != "xac_nhan_ky_han_vay"

    got = tra_loi("nhưng mà có vay hơn năm trăm triệu được không", DOC, history=history)
    assert got and got[0] == "vuot_han_muc"
    assert "hơn mức đó" in got[1] and "đang vượt" not in got[1]


def test_no_tat_toan_khong_chu_xau_van_la_hoi_no_cu_khong_phai_nhu_cau():
    doc = DOC + "\n## Khách hỏi về nợ xấu\n- Nợ đã tất toán trên 1 năm: có thể xem xét, cần kiểm tra hồ sơ cụ thể\n"
    history = [{"role": "user", "content": "vay một trăm triệu trong ba sáu tháng thì như nào"}]
    got = tra_loi("nợ tất toán trên một năm thì có vay được không", doc, history=history)
    assert got and got[0] == "no_xau_da_tat_toan"
    # Tài liệu không có mục nợ xấu: cũng KHÔNG được lôi 100 triệu cũ ra trả lời.
    got = tra_loi("nợ tất toán trên một năm thì có vay được không", DOC, history=history)
    assert not got or got[0] != "nhu_cau_vay"


def test_khong_hoi_lai_cung_mot_cau_hai_lan_lien():
    history = [
        {"role": "user", "content": "vay một trăm triệu trong hai ba tháng"},
        {"role": "assistant", "content": "Dạ anh chị muốn vay trong bao nhiêu tháng hoặc năm ạ?"},
    ]
    # Khách lại nói mơ hồ y hệt: lần hai không hỏi lại nữa, để mô hình xử lý.
    got = tra_loi("hai ba tháng", DOC, history=history)
    assert not got or got[0] != "xac_nhan_ky_han_vay"


def test_vay_tien_trong_ky_han_thi_nhu_nao_la_hoi_tinh():
    got = tra_loi("ví dụ số tiền vay một trăm triệu trong ba sáu tháng thì như nào", DOC)
    assert got and got[0] == "tinh_tra_gop"
    assert "100 triệu" in got[1] and "36 tháng" in got[1]


def test_bo_sung_ky_han_sau_khi_da_hoi_tinh_thi_tinh_luon():
    history = [
        {"role": "user", "content": "vay một trăm triệu thì mỗi tháng trả bao nhiêu"},
        {"role": "assistant", "content": "Dạ để tính khoản trả hàng tháng, anh chị cho em biết thời hạn vay ạ."},
    ]
    got = tra_loi("ba sáu tháng", DOC, history=history)
    assert got and got[0] == "tinh_tra_gop"
    assert "36 tháng" in got[1]


# --- Luật đọc tài liệu bắt đúng câu -------------------------------------------
DOC_CHE = DOC + """
## Xử lí tình huống khi khách chê
- Chê lãi cao: Lãi này bên em đã là ưu đãi thuộc tốp tốt nhất thị trường rồi ạ, do vay không tài sản thế chấp nên lãi sẽ hơi cao chút
- Chê hạn mức thấp: Hạn mức này bên em thuộc tốp cao trên thị trường rồi đó ạ, vay tín chấp nên không ngân hàng nào dám cho vay quá nhiều ạ
## Khách hỏi về nợ xấu
- Nợ xấu nhóm 3, 4, 5 tại CIC: hồ sơ rất khó được phê duyệt
- Nợ đã tất toán trên 1 năm: có thể xem xét, cần kiểm tra hồ sơ cụ thể
- Câu nên nói: "Dạ nếu mình còn nợ xấu nhóm ba trở lên tại CIC thì hồ sơ khó
  duyệt ạ. Còn nếu mình đã tất toán trên một năm rồi thì anh chị cho em xin
  thông tin để em kiểm tra giúp ạ."
"""


@pytest.mark.parametrize("cau", ["hạn mức thấp vậy", "ta chê sao hạn mức lại thấp vậy", "hạn mức ít thế"])
def test_che_han_muc_thap_doc_dung_dong_tai_lieu(cau):
    got = tra_loi(cau, DOC_CHE)
    assert got and got[0] == "phan_hoi_han_muc_thap"
    assert "tốp cao trên thị trường" in got[1]
    assert "500 triệu" not in got[1]


def test_che_lai_cao_doc_dung_dong_tai_lieu():
    got = tra_loi("mà lãi hơi cao nhỉ", DOC_CHE)
    assert got and got[0] == "phan_hoi_lai_cao"
    assert "tốp tốt nhất thị trường" in got[1]


def test_thoi_gian_vay_toi_da_khong_phai_han_muc():
    got = tra_loi("vậy còn thời gian vay tối đa được bao lâu", DOC)
    assert got and got[0] == "thoi_han_san_pham"
    assert "60 tháng" in got[1] and "500" not in got[1]


@pytest.mark.parametrize("cau", ["lãi suất như nào", "mà thì vay tín chấp thì lãi như nào", "lãi suất hiện tại là bao nhiêu", "lãi ra sao"])
def test_lai_nhu_nao_doc_lai_suat(cau):
    got = tra_loi(cau, DOC)
    assert got and got[0] == "lai_suat_san_pham"
    assert "7.9%" in got[1]


def test_so_lai_phai_tra_van_la_cau_hoi_tinh():
    # Đừng để luật lãi suất nới rộng nuốt mất câu hỏi TIỀN lãi.
    history = [{"role": "user", "content": "anh vay ba trăm triệu có được không"}]
    got = tra_loi("cho anh số lãi phải chi trả bao nhiêu", DOC, history=history)
    assert got and got[0] == "thieu_du_kien_tinh_lai"


@pytest.mark.parametrize("cau", ["thế nợ xấu có vay được không", "nợ xấu nhóm năm", "anh nợ loại ba được không"])
def test_no_xau_doc_cau_nen_noi_trong_tai_lieu(cau):
    got = tra_loi(cau, DOC_CHE)
    assert got and got[0] == "no_xau_cau_nen_noi"
    assert "nhóm ba trở lên" in got[1] and "tất toán trên một năm" in got[1]


def test_no_xau_khong_co_muc_thi_de_mo_hinh():
    assert tra_loi("thế nợ xấu có vay được không", DOC) is None
