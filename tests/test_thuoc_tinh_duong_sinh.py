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


def test_chi_ghi_nhat_ky_chua_thay_cau():
    """Giai đoạn này lưới CHƯA được thay câu - chỉ ghi metrics và log.

    Bật chặn thật là việc của kế hoạch sau, sau khi nhật ký trên cuộc gọi thật
    cho thấy chặn nhầm <= 5%. Nếu ai đó nối thẳng kết quả vào `ra` thì test này
    đỏ, và đó là chủ ý.
    """
    ma = inspect.getsource(streaming_pipeline)
    dong = [l for l in ma.splitlines() if "chan_thuoc_tinh_sai(" in l]
    assert dong, "không tìm thấy chỗ gọi lưới"
    dong_goi = dong[0]
    assert dong_goi.lstrip().startswith("_,"), (
        "kết quả văn bản của lưới phải bị bỏ đi (`_,`) ở giai đoạn ghi nhật ký, "
        f"nhưng dòng gọi là: {dong_goi.strip()!r}")
