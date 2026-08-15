"""Tên tổ chức/nhân viên phải ra từ KỊCH BẢN, `.env` chỉ là lưới cuối.

Vì sao có test này: trước đây ba đường tự đọc lấy - đường LLM đọc kịch bản còn
bảng lượt thường gặp và câu mở đầu cuộc gọi đọc thẳng `.env`. Đổi tên trong kịch
bản xong thì trong CÙNG một cuộc gọi, câu chào sẵn xưng một tên còn câu mô hình
sinh xưng tên khác - và không có gì báo.
"""
from backend.config import settings
from backend.models import scenarios_db


def test_lay_tu_kich_ban():
    sc = {"org_name": "Ngân hàng Quân đội", "agent_name": "Hạnh"}
    assert scenarios_db.ten_to_chuc(sc) == "Ngân hàng Quân đội"
    assert scenarios_db.ten_nhan_vien(sc) == "Hạnh"


def test_kich_ban_de_len_env():
    """Kịch bản THẮNG `.env`, không phải ngược lại."""
    sc = {"org_name": "Tên trong kịch bản"}
    assert scenarios_db.ten_to_chuc(sc) != settings.bank_name
    assert scenarios_db.ten_to_chuc(sc) == "Tên trong kịch bản"


def test_khong_co_kich_ban_thi_ve_env():
    for rong in ({}, None):
        assert scenarios_db.ten_to_chuc(rong) == settings.bank_name
        assert scenarios_db.ten_nhan_vien(rong) == settings.agent_name


def test_truong_rong_cung_ve_env():
    """Chuỗi rỗng phải rơi về `.env`, không được trả về chuỗi rỗng.

    Kịch bản tạo qua API có thể để trống trường này; trả '' là bot xưng
    'em là  bên ' - mất tên mà không báo lỗi.
    """
    sc = {"org_name": "", "agent_name": "   "}
    assert scenarios_db.ten_to_chuc(sc) == settings.bank_name
    # Khoảng trắng KHÔNG bị coi là rỗng - đây là hành vi hiện tại, ghi lại để
    # nếu ai đổi sang .strip() thì thấy test này và biết mình đang đổi cái gì.
    assert scenarios_db.ten_nhan_vien(sc) == "   "


def test_ba_duong_dung_chung_mot_luat():
    """llm_service, lượt thường gặp và câu mở đầu phải ra CÙNG một tên."""
    import inspect

    from backend.services import llm_service, phone_call_service
    from backend.pipeline import streaming_pipeline

    for mod in (llm_service, phone_call_service, streaming_pipeline):
        src = inspect.getsource(mod)
        assert "settings.bank_name" not in src, (
            f"{mod.__name__} đọc thẳng settings.bank_name - phải đi qua "
            "scenarios_db.ten_to_chuc"
        )
        assert "settings.agent_name" not in src, (
            f"{mod.__name__} đọc thẳng settings.agent_name - phải đi qua "
            "scenarios_db.ten_nhan_vien"
        )
