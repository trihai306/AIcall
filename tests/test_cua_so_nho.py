"""Cửa sổ nhớ của mô hình: còn bao nhiêu chỗ cho hội thoại, và khi nào phải kêu.

Số trong các test này là số ĐO THẬT ngày 2026-09-02 trên máy Windows bằng
`prompt_eval_count` của Ollama với qwen2.5:7b - không phải số bịa ra.
"""
from backend.services.cua_so_nho import canh_bao_tran, con_cho_hoi_thoai, doc_so_token

# Cấu hình đang chạy thật lúc phát hiện lỗi.
CTX_CU, LOI_DAN_CO_TRI_THUC, MAX_TL = 2048, 1414, 150


def test_con_cho_hoi_thoai_tru_ca_loi_dan_lan_cho_tra_loi():
    # 2048 - 1414 - 150. Quên trừ chỗ trả lời là báo dư 150 token.
    assert con_cho_hoi_thoai(LOI_DAN_CO_TRI_THUC, CTX_CU, MAX_TL) == 484


def test_cua_so_day_thi_con_cho_khong_am():
    assert con_cho_hoi_thoai(3000, CTX_CU, MAX_TL) == 0


def test_cau_hinh_dang_chay_phai_keu_len():
    # Đây chính là lỗi bên A báo: bot quên giữa chừng cuộc mà không gì báo.
    assert canh_bao_tran(LOI_DAN_CO_TRI_THUC, CTX_CU, MAX_TL) is not None


def test_cua_so_rong_rai_thi_im():
    # Cùng lời dặn ấy, nới cửa sổ lên 8192 thì không còn gì phải kêu.
    assert canh_bao_tran(LOI_DAN_CO_TRI_THUC, 8192, MAX_TL) is None


def test_canh_bao_noi_ra_con_bao_nhieu_luot():
    # Kêu mà không nói còn mấy lượt thì người đọc log vẫn không biết gấp hay không.
    assert "6" in canh_bao_tran(LOI_DAN_CO_TRI_THUC, CTX_CU, MAX_TL)


def test_du_cho_mot_cuoc_tu_van_that_thi_im():
    # Ngưỡng KHÔNG phải phần trăm cửa sổ: cấu hình hỏng thật chỉ dùng 76% mà
    # vẫn chỉ nhớ 6 lượt. Thước đo đúng là CHỨA ĐƯỢC MẤY LƯỢT.
    # 2048 - 150 - 398 = 1500 token = đúng 20 lượt.
    assert canh_bao_tran(398, CTX_CU, MAX_TL) is None


def test_thieu_mot_luot_so_voi_cuoc_that_thi_keu():
    assert canh_bao_tran(399, CTX_CU, MAX_TL) is not None


# --- Đọc số token thật từ phản hồi Ollama ---------------------------------
# Chunk cuối của stream mang `prompt_eval_count` - số token THẬT của lời dặn
# cộng lịch sử. Có nó thì khỏi ước lượng bằng ký tự.

def test_doc_duoc_so_token_tu_chunk_cuoi():
    assert doc_so_token({"done": True, "prompt_eval_count": 1414}) == 1414


def test_chunk_dang_stream_chua_co_so_thi_tra_none():
    assert doc_so_token({"done": False, "message": {"content": "Dạ"}}) is None


def test_doc_duoc_ca_khi_chunk_la_doi_tuong_khong_phai_dict():
    class Chunk:
        done = True
        prompt_eval_count = 900
    assert doc_so_token(Chunk()) == 900


def test_chunk_khong_co_truong_nao_thi_tra_none():
    # Ollama đổi tên trường hoặc bản cũ không trả - không được ném lỗi làm
    # hỏng cả lượt trả lời của khách.
    assert doc_so_token({}) is None
