"""Lưới thuộc tính phải chạy ĐÚNG CHỖ `chan_so_sai` chạy: trên từng mảnh, trước TTS.

Hai test này đọc MÃ NGUỒN chứ không gọi pipeline: dựng `StreamingPipeline` thật
đòi STT + LLM + TTS + RAG, tức cần GPU và vài giây nạp model, quá đắt cho một
test canh dây nối. Đánh đổi: chúng bắt được "quên nối" và "nối sai thứ tự",
không bắt được "nối đúng chỗ nhưng truyền sai tham số" - phần đó do
`tests/test_thuoc_tinh.py` và bước chấm lại ở Task 7 gác.
"""
import inspect

from backend.pipeline import streaming_pipeline


def test_luoi_thuoc_tinh_duoc_goi_trong_duong_sinh():
    ma = inspect.getsource(streaming_pipeline)
    assert "chan_thuoc_tinh_sai" in ma


def test_goi_SAU_chan_so_sai():
    """`chan_so_sai` sửa số đọc nhầm trước; lưới này phán trên bản đã sửa."""
    ma = inspect.getsource(streaming_pipeline)
    assert ma.index("chan_so_sai(doan") < ma.index("chan_thuoc_tinh_sai(")


def test_bat_duoc_thi_SUA_CAU_chu_khong_im_lang():
    """Đổi 09-09-2026. Trước đó lưới chỉ ghi nhật ký - khách vẫn nghe câu bịa.

    Người dùng hỏi thẳng: "chặn thì nó im lặng không trả lời à?". Không: thang
    xử lý ở `thuoc_tinh.sua_theo_tai_lieu` thay số bằng giá trị trong tài liệu,
    không thay được thì bỏ mệnh đề, bỏ hết mới dùng `CAU_KIEM_TRA_LAI`.

    Bật mặc định dù chưa có tỉ lệ đánh dấu nhầm trên cuộc gọi thật, vì hai chiều
    sai không cân nhau - xem `config.thuoc_tinh_sua_cau`.
    """
    ma = inspect.getsource(streaming_pipeline)
    assert "sua_theo_tai_lieu(" in ma, "bắt được mà không sửa gì"
    assert ma.index("chan_thuoc_tinh_sai(\n") < ma.index("sua_theo_tai_lieu(\n"), (
        "phải phán trước rồi mới sửa")


def test_van_TAT_duoc_bang_co():
    from backend.config import settings
    assert hasattr(settings, "thuoc_tinh_sua_cau")


def test_bo_HET_moi_dung_cau_mau():
    """Câu mẫu là nhánh HIẾM. Dùng nó cho mọi lượt là quay lại "trả lời 1 kiểu"."""
    ma = inspect.getsource(streaming_pipeline)
    assert "moi.strip() or CAU_KIEM_TRA_LAI" in ma
