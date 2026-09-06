"""Lần đoán cuối câu phải chạy trên TOÀN BỘ câu, không phải trên đệm rỗng.

Lỗi đã xảy ra (tới 06-09-2026): `api/websocket.py` gọi `speculate(ngay=True)`
SAU `take_audio()`, tức đệm đã sạch. Chú thích trong code ghi đó là cố ý — để
giữ `tinh_huong` của task cũ. Cái giá không ai đo lúc đó: lần đoán giá trị nhất
của cả lượt không bao giờ chạy.

Với n = 0 thì `speculate` hỏng ở CẢ HAI nhánh:
  - task cũ đã xong  -> `n < _SPEC_MIN_MS` -> return ngay
  - task cũ đang chạy -> huỷ nó rồi phiên âm trên đệm rỗng -> `spec_stt = (0,"")`

Cả hai đều để `spec_answer` đứng nguyên ở bản soạn GIỮA CHỪNG theo câu cụt, nên
`_answer_hit` trượt và câu trả lời phải sinh lại từ đầu. Đo trên ba cuộc gọi thử:
`llm_nghi_san` FALSE ở 9/9 lượt.
"""
import pytest

from backend.pipeline.streaming_pipeline import StreamingPipeline


# --- _answer_hit: vì sao bản cụt luôn trượt ------------------------------

def test_ban_cut_bi_vut_dung_nhu_log_ghi():
    """Đúng cặp chữ log in ra ngày 06-09, giữ làm ca kiểm chứng.

    Phần khách nói thêm là 4 từ MANG NGHĨA -> phải trượt. Đây là hành vi ĐÚNG
    của `_answer_hit`; chỗ hỏng nằm ở việc `spec` bị cụt, không ở luật này.
    """
    assert StreamingPipeline._answer_hit(
        "thế vay tối đa", "thế vay tối đa được bao nhiêu tiền") is False


def test_cau_TRON_thi_trung():
    """Cùng câu đó, nhưng bản đoán nghe trọn -> dùng lại được.

    Đây là thứ bản sửa mở ra: đoán trên trọn câu thì phần nói thêm chỉ còn từ
    đệm cuối câu.
    """
    assert StreamingPipeline._answer_hit(
        "thế vay tối đa được bao nhiêu tiền",
        "thế vay tối đa được bao nhiêu tiền ạ") is True


def test_them_qua_ba_tu_van_truot():
    """Lưới an toàn phải còn nguyên: đây là ĐỌC THẲNG cho khách nghe."""
    assert StreamingPipeline._answer_hit(
        "lãi suất bao nhiêu", "lãi suất bao nhiêu ạ nhé vậy thế") is False


# --- websocket: thứ tự set_audio / speculate / take_audio ----------------

def test_websocket_dat_lai_tieng_TRUOC_khi_doan():
    """Canh thứ tự bằng cách đọc mã nguồn — đường này không test đơn vị được
    (cần WebSocket thật + STT + LLM), mà thứ tự chính là chỗ đã hỏng.

    Ràng buộc: `set_audio(audio_bytes)` phải đứng TRƯỚC `speculate(ngay=True)`,
    và `take_audio()` dọn đệm đứng SAU.
    """
    import inspect
    from backend.api import websocket as ws
    src = inspect.getsource(ws)

    i_set = src.find("session.set_audio(audio_bytes)")
    i_spec = src.find("speculate(session, ngay=True)")
    assert i_set != -1, "mất set_audio -> đoán cuối câu lại chạy trên đệm rỗng"
    assert i_spec != -1
    assert i_set < i_spec, (
        "set_audio phải đứng TRƯỚC speculate(ngay=True); đảo lại là tái hiện "
        "đúng lỗi làm nghi_san false ở 9/9 lượt")
    assert src.find("session.take_audio()", i_spec) != -1, (
        "thiếu take_audio() dọn đệm sau khi đoán -> tiếng lượt này lẫn sang lượt sau")
