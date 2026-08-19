"""Chặn chữ nước ngoài lọt ra từ LLM.

Bắt được ngày 18-08-2026 bằng chính bộ đọc thử 100 mẫu:

    Dạ em chào chị, em là Lan bên Ngân hàng Quân đội ạ. Em có thể giúp gì cho
    chị今天天气不错，你打算出去玩吗？

Đo trên 34 mẫu đầu: 1/136 lượt (0,7%). Nghe thì nhỏ, nhưng với 100 cuộc gọi
mỗi ngày là gần một cuộc dính - và F5 sẽ CỐ ĐỌC chỗ chữ Hán đó ra tiếng, khách
nghe được một tràng vô nghĩa giữa cuộc tư vấn.

CẮT chứ không sinh lại: đường thoại thật có trần TTFA, sinh lại cả lượt là cộng
thêm vài giây khách phải chờ. Cắt đi thì câu còn lại vẫn trọn nghĩa - đúng ca
trên, cắt xong ra "Em có thể giúp gì cho chị?".

Bộ chấm điểm cũ của dự án MÙ với lỗi này: nó chưa bao giờ kiểm chữ nước ngoài.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.pipeline.text_normalizer import bo_chu_la, co_chu_la


def test_ca_that_da_gap():
    vao = "Dạ em chào chị, em là Lan bên Ngân hàng Quân đội ạ. Em có thể giúp gì cho chị今天天气不错，你打算出去玩吗？"
    ra = bo_chu_la(vao)
    assert not co_chu_la(ra)
    assert ra.startswith("Dạ em chào chị")
    assert "giúp gì cho chị" in ra


def test_GIU_NGUYEN_tieng_viet_du_dau():
    """Tiếng Việt nằm dưới U+1EFF nên không được đụng tới cái nào."""
    for c in ["Dạ vâng ạ, em nghe anh chị.",
              "Lãi suất từ 7,9% một năm ạ.",
              "Nguyễn Thị Hường ở phường Đội Cấn, quận Ba Đình.",
              "Chị cứ yên tâm nhé, bên em hỗ trợ tận nơi ạ."]:
        assert bo_chu_la(c) == c, f"đụng vào tiếng Việt: {c}"
        assert not co_chu_la(c)


def test_bo_ca_NHAT_va_HAN():
    assert not co_chu_la(bo_chu_la("xin chào こんにちは em nghe"))
    assert not co_chu_la(bo_chu_la("xin chào 안녕하세요 em nghe"))


def test_bo_dau_cau_TOAN_RONG():
    """Dấu ，。？！ toàn rộng đi kèm chữ Hán - bỏ sót thì F5 vẫn đọc lạ."""
    assert not co_chu_la(bo_chu_la("em nghe anh ạ，好的。"))


def test_KHONG_de_lai_hai_khoang_trang():
    ra = bo_chu_la("em có thể 今天天气 giúp gì ạ")
    assert "  " not in ra, f"còn khoảng trắng đôi: {ra!r}"


def test_KHONG_de_lai_khoang_trang_thua_o_hai_dau():
    assert bo_chu_la("今天 em nghe ạ") == "em nghe ạ"
    assert bo_chu_la("em nghe ạ 今天") == "em nghe ạ"


def test_chuoi_sach_thi_tra_ve_CHINH_NO():
    c = "Dạ em chào anh chị ạ."
    assert bo_chu_la(c) is c or bo_chu_la(c) == c


def test_rong_va_None():
    assert bo_chu_la("") == ""
    assert bo_chu_la(None) == ""
    assert not co_chu_la("")
    assert not co_chu_la(None)


def test_co_chu_la_bat_dung():
    assert co_chu_la("今天")
    assert not co_chu_la("Dạ vâng ạ")
    assert not co_chu_la("7,9% một năm")


def test_toan_chu_la_thi_ra_RONG():
    """Cả lượt là chữ lạ thì phải ra rỗng, để chỗ gọi biết mà bỏ lượt."""
    assert bo_chu_la("今天天气不错，你打算出去玩吗？") == ""
