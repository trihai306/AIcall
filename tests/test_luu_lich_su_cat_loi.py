"""Hồi quy lưu lịch sử khi khách cắt lời AI giữa cuộc gọi."""

import asyncio

import pytest

from backend.models import db
from backend.pipeline.session_manager import CallSession


@pytest.fixture()
def db_that(tmp_path):
    asyncio.run(db.init_db(tmp_path / "lich_su.db"))
    yield
    asyncio.run(db.close_db())


def _luu(session: CallSession):
    asyncio.run(db.save_session(session))


def _doc(session: CallSession) -> list[dict]:
    return asyncio.run(db.get_session(session.session_id))["history"]


def test_luot_bi_cat_duoc_thay_bang_cau_da_ghep(db_that):
    """Index cũ phải được cập nhật, không được giữ câu/đáp án dở."""
    session = CallSession()
    session.add_turn("assistant", "Em chào anh.")
    session.add_turn("user", "Anh muốn hỏi")
    session.add_turn("assistant", "Dạ anh cứ hỏi ạ.")
    _luu(session)

    session.danh_dau_bi_cat()
    session.add_turn("user", session.ghep_cau_bi_cat("lãi suất bao nhiêu"))
    session.add_turn("assistant", "Lãi suất được tính theo hồ sơ của anh ạ.")
    _luu(session)

    assert _doc(session) == session.history
    assert _doc(session)[1]["content"] == "Anh muốn hỏi lãi suất bao nhiêu"


def test_cat_loi_roi_ket_thuc_phai_xoa_duoi_da_luu(db_that):
    """Kết thúc ngay sau khi cắt vẫn phải xóa các hàng thừa trong SQLite."""
    session = CallSession()
    session.add_turn("assistant", "Em chào anh.")
    session.add_turn("user", "Anh đang nói dở")
    session.add_turn("assistant", "Câu trả lời chưa phát xong.")
    _luu(session)

    session.danh_dau_bi_cat()
    _luu(session)

    assert session.history == [{"role": "assistant", "content": "Em chào anh."}]
    assert _doc(session) == session.history


def test_lich_su_rong_sau_cat_loi_cung_duoc_dong_bo(db_that):
    """Phiên chat không có lời chào vẫn có thể bị cắt về lịch sử rỗng."""
    session = CallSession()
    session.add_turn("user", "Cho tôi hỏi")
    session.add_turn("assistant", "Dạ vâng.")
    _luu(session)

    session.danh_dau_bi_cat()
    _luu(session)

    assert session.history == []
    assert _doc(session) == []
