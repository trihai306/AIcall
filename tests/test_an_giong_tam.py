"""Giọng lắp tạm không được lọt vào danh sách chọn.

Nghe thử một ứng viên đoạn mẫu thì phải lắp nó thành giọng thật vài phút rồi
dọn. Trong khoảng đó nó nằm trong sổ giọng - mà danh sách giọng CHÍNH LÀ chỗ
người dùng chọn giọng cho cuộc gọi. Chọn nhầm một cái sắp bị xoá là cuộc gọi
mất giọng giữa chừng.

Luật phải nằm MỘT CHỖ: `/api/voices` do `api/calls.py` phục vụ chứ không phải
`api/voices.py` (router `/api` trần đăng ký trước), nên hai bản chép sẽ lệch
nhau mà không có gì báo.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services.tts_service import TIEN_TO_TAM, an_giong_tam


def g(*ten):
    return [{"name": t} for t in ten]


def test_bo_giong_tam():
    ra = an_giong_tam(g("heu_a6_35", "thu_heu_goc_0", "giong_nam"))
    assert [v["name"] for v in ra] == ["heu_a6_35", "giong_nam"]


def test_giu_nguyen_khi_khong_co_giong_tam():
    ra = an_giong_tam(g("heu_a6_35", "giong_nam"))
    assert len(ra) == 2


def test_KHONG_bo_nham_giong_that_co_chu_thu_o_giua():
    """Chỉ TIỀN TỐ mới tính - "giong_thu_nghiem" là giọng thật."""
    ra = an_giong_tam(g("giong_thu_nghiem", "am_thu", "thu_x_1"))
    assert [v["name"] for v in ra] == ["giong_thu_nghiem", "am_thu"]


def test_rong_va_thieu_ten():
    assert an_giong_tam([]) == []
    assert an_giong_tam(None) == []
    assert len(an_giong_tam([{}, {"name": None}])) == 2


def test_tien_to_dung_nhu_da_chot():
    assert TIEN_TO_TAM == "thu_"
