"""`_send_filler` phải quyết định bỏ câu đệm bằng `du_doan_cho_ms`, không phải
`can_che_ms`.

Test hàm thuần logic không bắt được lỗi đã xảy ra: `du_doan_cho_ms` có thể đúng
hoàn hảo mà `_send_filler` vẫn đem `can_che` (đã bị sàn 1800ms kéo lên) ra so
với ngưỡng - đúng như bản cũ làm suốt một tháng. Chỗ hỏng nằm ở ĐƯỜNG NỐI, nên
test phải chạy qua chính đường đó.

Không dựng TTS/GPU: `_send_filler` chỉ đọc `session.latency_log` rồi thoát sớm
ở nhánh bỏ đệm, nên một session giả là đủ. Lượt KHÔNG bỏ thì dừng lại ở
`lay_kho()` - ta chỉ cần biết nó đã ĐI QUA nhánh bỏ đệm.
"""
import asyncio
import types

import pytest

from backend.pipeline.streaming_pipeline import StreamingPipeline
from backend.services.filler_pick import NGUONG_BO_DEM_MS
from backend.services.filler_store import LoiKho


def _session(ttfa_list, spec_answer=None):
    """Session tối thiểu cho nhánh bỏ đệm. Chỉ những thuộc tính nó thật sự đọc."""
    return types.SimpleNamespace(
        latency_log=[{"ttfa_ms": v, "la_thoai": True} for v in ttfa_list],
        spec_answer=spec_answer,
        tinh_huong=None,
        spec_task=None,
        spec_stt=None,
        voice_name=None,
        turn_id=1,
    )


def _chay(session, n_audio=3200):
    """Gọi `_send_filler` và trả metrics. ws=None vì nhánh bỏ đệm không gửi gì.

    Lượt KHÔNG bị bỏ đệm chạy tiếp tới `lay_kho()` rồi ném `LoiKho` (test này
    không mở DB). Nuốt đúng ngoại lệ đó - nó CHÍNH LÀ bằng chứng đã đi qua nhánh
    bỏ đệm mà không dừng lại. Nuốt mọi ngoại lệ thì test sẽ xanh cả khi
    `_send_filler` hỏng ngay dòng đầu.
    """
    pipe = StreamingPipeline.__new__(StreamingPipeline)   # không chạy __init__ (nạp model)
    metrics: dict = {}
    try:
        asyncio.run(pipe._send_filler(None, session, 0.0, metrics,
                                      la_thoai=True, n_audio=n_audio))
    except LoiKho:
        pass
    return metrics


def test_duong_nhanh_thi_BO_cau_dem():
    """Đây là ca mà bản cũ TRƯỢT: `can_che` = 1800 (sàn) nên không bao giờ bỏ.

    Nay `du_doan` = 350 * 1.25 = 437ms, dưới ngưỡng 1000 -> bỏ.
    """
    m = _chay(_session([300, 350]))
    assert "filler_bo_qua" in m, (
        "đường chạy 350ms mà vẫn phát câu đệm -> ngưỡng lại thành mã chết")
    assert m["du_doan_cho_ms"] == pytest.approx(350 * 1.25, abs=1)


def test_duong_cham_thi_VAN_phat():
    """TTFA p50 thật của máy này là 1774ms. Không được bỏ đệm ở mức đó."""
    m = _chay(_session([1774]))
    assert "filler_bo_qua" not in m


def test_luot_dau_khong_bao_gio_bo():
    """Chưa có số đo -> `du_doan` là None -> phải phát.

    Lượt đầu là lượt chậm nhất cuộc gọi (đo được TTFA 8026ms khi tra hồ sơ nguội).
    """
    m = _chay(_session([]))
    assert "filler_bo_qua" not in m


def test_nghi_san_KHONG_tu_no_quyet_dinh_bo():
    """`spec_answer` chỉ đổi chữ ghi vào metrics, không đổi quyết định.

    Giả định cũ "có bản nghĩ sẵn thì câu thật tới tức thì" đã bị số đo bác bỏ:
    đúng những lượt dùng bản nghĩ sẵn lại là lượt khách nghe im lâu nhất
    (947/1295/1739ms), vì chỉ chúng bị bỏ đệm.
    """
    m = _chay(_session([1774], spec_answer="Dạ lãi suất bên em là..."))
    assert "filler_bo_qua" not in m, "nghĩ sẵn không được tự nó bỏ câu đệm"

    m2 = _chay(_session([300], spec_answer="Dạ lãi suất bên em là..."))
    assert "nghĩ sẵn" in m2["filler_bo_qua"]


def test_moc_bo_dem_dung_bang_hang_so_chung():
    """Ngay dưới ngưỡng thì bỏ, ngay trên thì phát - không lệch hằng số."""
    duoi = (NGUONG_BO_DEM_MS - 50) / 1.25
    tren = (NGUONG_BO_DEM_MS + 50) / 1.25
    assert "filler_bo_qua" in _chay(_session([duoi]))
    assert "filler_bo_qua" not in _chay(_session([tren]))


# --- Chờ câu đệm LLM: chỉ chờ khi task ĐANG chạy -------------------------
#
# Đo 06-09-2026: câu đệm LLM sinh được và dựng tiếng xong, nhưng xong SAU lúc
# lượt mở nên `_send_filler` đọc phải chuỗi rỗng rồi bỏ đi. Nay có chờ - nhưng
# chờ có điều kiện, vì chờ vô điều kiện là trì hoãn câu trả lời ở ĐÚNG những
# lượt vốn đã chậm nhất.

def test_khong_co_task_thi_KHONG_cho():
    """Lượt không ai đang nghĩ câu đệm phải đi thẳng, không mất 300ms vô ích."""
    from backend.pipeline.streaming_pipeline import StreamingPipeline
    import time as _t

    s = _session([1774])
    s.spec_cau_dem = ""
    s._cau_dem_dang_nghi = False
    t0 = _t.perf_counter()
    m = _chay(s)
    troi = (_t.perf_counter() - t0) * 1000
    assert troi < StreamingPipeline._CHO_SINH_CAU_DEM_MS, (
        f"chờ {troi:.0f}ms trong khi không có task nào đang nghĩ")
    assert "cau_dem_llm_cho_ms" not in m


def test_tran_cho_khong_qua_300ms():
    """Trần phải nhỏ hơn hẳn quãng im nó đang vá (1,7-3,2 giây)."""
    from backend.pipeline.streaming_pipeline import StreamingPipeline
    assert StreamingPipeline._CHO_SINH_CAU_DEM_MS <= 300.0
