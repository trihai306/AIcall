"""Chỗ nối CÂU ĐỆM -> nội dung phải có nhịp nghỉ như mọi ranh giới phẩy khác.

Người dùng 07-09-2026, nghe cuộc 08c0d3e0: *"sau khi đọc hết câu đệm, cảm giác từ
liền kề tiếp theo bị ngắt quãng (đè lên từ phía trước, đồng thời tiếng to hơn nghe
rất giả)"*.

Đo trên chính bản ghi đó: **7/9 chỗ nối có đúng 0ms lặng**, và mức 300ms hai bên
ranh giới nhảy +3,0 đến +5,0 dB (đỉnh 988 -> 2235 ở lượt "lãi cao thế"). Hai mảnh
tiếng dựng RỜI NHAU - clip câu đệm dựng sẵn lúc khởi động, nội dung sinh lúc chạy,
cả hai đều bị `trim_silence` cắt sạch hai đầu - nên đuôi câu đệm đang tắt dần thì
nội dung vào ngay ở mức đầy. Đó là "đè lên" và "to hơn".

Vì sao chỗ này sót: dự án đã đo ra F5 LỜ dấu phẩy nên nhịp nghỉ phải chèn bằng
code (`nhip_nghi_sau`), nhưng vòng phát khởi tạo `nghi_ms = 0.0` và cố ý không
chèn vào mảnh ĐẦU để giữ TTFA. Câu đệm luôn kết bằng dấu phẩy, và nó đứng ngay
trước mảnh đầu - nên đúng một ranh giới phẩy trong cả hệ thống không được chèn.

ĐIỀU KIỆN BẮT BUỘC: chỉ chèn khi câu đệm CÒN ĐANG PHÁT. Cùng bản ghi có 2/9 lượt
`ĐÓI KHUNG` (216ms và 287ms) - ở đó câu đệm đã hết trước khi nội dung tới, tức
khách đang nghe khoảng lặng thật. Chèn thêm vào đó là làm dài thêm đúng chỗ đang
hỏng.
"""
import time

from backend.pipeline.streaming_pipeline import StreamingPipeline
from backend.pipeline.text_chunker import nhip_nghi_sau

DEM = "Dạ lãi suất bên em thì,"          # nguyên văn câu đệm cuộc 08c0d3e0


def test_cau_dem_con_dang_phat_thi_chen_nhip_phay():
    metrics = {"filler_text": DEM, "filler_xong_luc": time.perf_counter() + 0.5}
    assert StreamingPipeline._nghi_noi_cau_dem(metrics) == nhip_nghi_sau(DEM)


def test_dung_chung_luat_voi_moi_ranh_gioi_phay_khac():
    """Không đẻ hằng số mới: câu đệm kết bằng phẩy thì nghỉ đúng bằng nghỉ phẩy."""
    metrics = {"filler_text": DEM, "filler_xong_luc": time.perf_counter() + 0.5}
    assert StreamingPipeline._nghi_noi_cau_dem(metrics) > 0


def test_cau_dem_da_het_thi_khong_chen_gi():
    # Lượt 'mở sấu' và 'lãi cao thế': ĐÓI KHUNG 216ms/287ms, khách đang nghe im.
    metrics = {"filler_text": DEM, "filler_xong_luc": time.perf_counter() - 0.3}
    assert StreamingPipeline._nghi_noi_cau_dem(metrics) == 0.0


def test_khong_co_cau_dem_thi_khong_chen_gi():
    # Lượt bị bỏ câu đệm (nhanh sẵn / không rõ tình huống / vừa đọc nốt câu dở).
    assert StreamingPipeline._nghi_noi_cau_dem({}) == 0.0


def test_co_moc_thoi_gian_nhung_khong_co_chu_thi_khong_chen():
    """Chữ rỗng nghĩa là không biết câu đệm kết bằng dấu gì - đừng đoán bừa."""
    metrics = {"filler_text": "", "filler_xong_luc": time.perf_counter() + 0.5}
    assert StreamingPipeline._nghi_noi_cau_dem(metrics) == 0.0


def test_khoang_lang_da_co_duoc_tru_khoi_nhip_noi(monkeypatch):
    monkeypatch.setattr("backend.pipeline.streaming_pipeline.time.perf_counter", lambda: 10.05)
    metrics = {"filler_text": DEM, "filler_xong_luc": 10.0}
    import pytest
    assert StreamingPipeline._nghi_noi_cau_dem(metrics) == pytest.approx(nhip_nghi_sau(DEM) - 50)
