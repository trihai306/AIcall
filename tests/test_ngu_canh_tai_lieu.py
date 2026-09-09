"""Nạp TRỌN tài liệu sản phẩm thay cho hai mảnh RAG.

Đo 09-09-2026 trên 60 câu hỏi thật của khách, qua chính `build_system_prompt` +
`stream_response`, qwen2.5:7b:

    cách nạp ngữ cảnh              ký tự   TTFT tv   tổng tv
    mảnh RAG top_k=2 (cũ)           1005     100ms     523ms
    trọn tài liệu sản phẩm          1773      27ms     459ms
    trọn tài liệu + FAQ (chọn)      2920      28ms     506ms
    trọn tài liệu + mảnh RAG        2803     104ms     483ms

Nhiều ký tự hơn mà NHANH HƠN, vì cache tiền tố. Chứng minh riêng bằng
`prompt_eval_duration`, chạy xen kẽ ba vòng: mảnh RAG đổi mỗi lượt tốn 92ms tính
prompt cho 1562 token, còn tài liệu đứng yên tốn 17ms cho 2896 token. `rag_context`
nằm gần cuối system prompt nên mảnh đổi mỗi lượt là phá cache từ chỗ đó trở đi.

Chọn "tài liệu + FAQ" chứ không phải "tài liệu trơn": `faq_banking.md` có nội
dung không nằm trong tài liệu sản phẩm nào (nợ xấu, cách tăng hạn mức thẻ, thẻ
tín dụng khác thẻ ghi nợ). Giá phải trả là ~47ms ở tổng thời gian.

Cách "tài liệu + mảnh RAG" ĐÃ THỬ VÀ BỎ: mảnh vẫn đổi mỗi lượt nên cache vẫn vỡ,
TTFT 104ms - không hơn gì bản cũ.
"""
import io
import os

from backend.pipeline.ngu_canh_tai_lieu import quen_nho, toan_van

GOC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_lay_duoc_tron_tai_lieu_san_pham():
    ra = toan_van("vay tín chấp")
    assert "7.9" in ra, "thiếu lãi suất - không phải trọn tài liệu"
    assert "12 - 60 tháng" in ra, "thiếu dòng thời hạn"


def test_co_kem_FAQ():
    """FAQ có nội dung không tài liệu sản phẩm nào có - mất nó là mất câu trả lời."""
    ra = toan_van("vay tín chấp")
    assert "nợ xấu" in ra.lower()


def test_san_pham_rong_thi_tra_rong():
    """Không rõ sản phẩm thì trả rỗng để đường sinh RƠI VỀ RAG như cũ."""
    assert toan_van("") == ""
    assert toan_van(None) == ""


def test_san_pham_khong_co_tai_lieu_thi_tra_rong():
    assert toan_van("bảo hiểm nhân thọ") == ""


def test_dau_cach_va_HOA_thuong_khong_anh_huong():
    assert toan_van("  Vay Tín Chấp  ") == toan_van("vay tín chấp")


def test_sua_tep_thi_lay_ban_moi(tmp_path):
    """Sửa tài liệu trên trang Tri thức xong phải ăn ngay, không cần khởi động lại.

    Trang đó ghi file xuống đĩa rồi mới nạp lại RAG (`_nap_lai_mot_tep`), nên
    nhớ theo mtime là đủ. Không canh mtime thì bot đọc bản cũ cho khách - đúng
    loại lỗi đã xảy ra một lần với kho vector.
    """
    thu = tmp_path / "knowledge" / "products"
    thu.mkdir(parents=True)
    tep = thu / "vay_tin_chap.md"
    tep.write_text("- Lãi suất: 1.1%/năm\n", encoding="utf-8")
    quen_nho()
    assert "1.1" in toan_van("vay tín chấp", goc=str(tmp_path))

    # mtime của một số hệ tệp chỉ chính xác tới giây -> ghi kèm kích thước khác
    tep.write_text("- Lãi suất: 2.2%/năm  (bản đã sửa)\n", encoding="utf-8")
    assert "2.2" in toan_van("vay tín chấp", goc=str(tmp_path)), (
        "vẫn trả bản cũ sau khi tệp đổi")


def test_thieu_thu_muc_thi_khong_no(tmp_path):
    quen_nho()
    assert toan_van("vay tín chấp", goc=str(tmp_path)) == ""


# --- canh dây nối trong đường sinh -----------------------------------------
# Soi MÃ NGUỒN chứ không dựng `StreamingPipeline`: dựng nó đòi STT + LLM + TTS +
# RAG, tức cần GPU và vài giây nạp model. Cùng đánh đổi với
# `tests/test_thuoc_tinh_duong_sinh.py`.

def test_duong_sinh_co_goi_toan_van():
    import inspect
    from backend.pipeline import streaming_pipeline
    assert "_toan_van_tai_lieu(session.product)" in inspect.getsource(streaming_pipeline)


def test_dat_SAU_nhanh_dap_san():
    """Lượt trả lời sẵn cố ý KHÔNG cần ngữ cảnh - đừng nạp tài liệu cho nó."""
    import inspect
    ma = inspect.getsource(__import__(
        "backend.pipeline.streaming_pipeline", fromlist=["x"]))
    assert ma.index("if dap_san:") < ma.index("elif tron_tai_lieu:")


def test_co_co_de_TAT_duoc():
    """Đổi hành vi đường thoại thì phải tắt được mà không cần sửa mã."""
    from backend.config import settings
    assert hasattr(settings, "ngu_canh_tron_tai_lieu")


def test_luoi_thuoc_tinh_doi_chieu_voi_CHINH_thu_mo_hinh_nhin_thay():
    """`ngu_canh` vừa là thứ đưa cho mô hình vừa là căn cứ của lưới.

    Nối trọn tài liệu vào `rag_context` nên lưới cũng được nâng theo: trước đây
    nó đối chiếu với hai mảnh RAG, giờ là trọn tài liệu. Đo 09-09-2026 trên 9
    câu bịa dựng tay: đối chiếu với mảnh bắt 0/9, đối chiếu với trọn tài liệu
    bắt 6/9, chặn oan 0/2 ở cả hai.
    """
    import inspect
    from backend.pipeline import streaming_pipeline
    ma = inspect.getsource(streaming_pipeline)
    assert ma.index("elif tron_tai_lieu:") < ma.index("chan_thuoc_tinh_sai(")
