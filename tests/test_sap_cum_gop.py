"""Xếp cụm mảnh để gộp, và trả lại hàng đợi phần không lấy.

Đây là chỗ dễ mất tiếng nhất của cả đường thoại: vòng tiêu thụ VÉT SẠCH hàng
đợi rồi phải đẩy lại phần dư. `asyncio.Queue` chỉ đẩy vào CUỐI, nên chỉ cần sai
thứ tự một nhịp là khách nghe đảo câu, hoặc mất trắng đuôi lượt.

Tách ra hàm thuần để thử được mà không phải dựng WebSocket, phiên và TTS.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.pipeline.text_chunker import TRAN_AM_TIET_GOP, sap_cum_gop


def cum(*t):
    return [(x, 0.0) for x in t]


# --- gộp --------------------------------------------------------------

def test_gop_het_khi_du_ngan():
    """Chuỗi toàn ranh giới PHẨY thì gộp hết (còn dấu chấm thì không - xem
    `test_KHONG_gop_qua_dau_CHAM`)."""
    dan, tra = sap_cum_gop(("Dạ vâng,", 0.0), cum("nhu cầu của anh,", "bên em hỗ trợ tốt."), False)
    assert [d[0] for d in dan] == ["Dạ vâng,", "nhu cầu của anh,", "bên em hỗ trợ tốt."]
    assert tra == []


def test_hang_doi_RONG_thi_khong_gop():
    dan, tra = sap_cum_gop(("Dạ em hiểu ạ.", 0.0), [], False)
    assert [d[0] for d in dan] == ["Dạ em hiểu ạ."]
    assert tra == []


# --- trả lại phần dư ---------------------------------------------------

def test_phan_du_tra_lai_DUNG_THU_TU():
    dai = "một hai ba bốn năm sáu bảy tám chín mười " * 3      # 30 âm tiết
    dan, tra = sap_cum_gop((dai, 0.0), cum(dai, "A.", "B."), False)
    assert len(dan) == 1, "quá trần mà vẫn gộp"
    assert [t for t, _ in tra] == [dai, "A.", "B."], "trả lại sai thứ tự -> khách nghe đảo câu"


def test_KHONG_MAT_MANH_NAO():
    """Bất biến quan trọng nhất: mọi mảnh vào đều phải ra, không thiếu cái nào."""
    dai = "một " * 25
    vao = cum(dai, dai, dai, dai)
    dan, tra = sap_cum_gop((dai, 0.0), vao, False)
    ra = [t for t, _ in dan] + [t for t, _ in tra if t is not None]
    assert len(ra) == 5, f"vào 5 mảnh, ra {len(ra)}"


# --- tín hiệu hết lượt -------------------------------------------------

def test_tin_hieu_HET_LUOT_luon_o_CUOI():
    """Trả `None` trước phần dư thì vòng tiêu thụ dừng sớm và mất đuôi lượt."""
    dai = "một " * 30
    dan, tra = sap_cum_gop((dai, 0.0), cum(dai, "Còn câu này."), True)
    assert tra[-1] is None, "tín hiệu hết lượt không nằm cuối"
    assert None not in [g for g in tra[:-1]], "có None lọt vào giữa"
    assert [t for t, _ in tra[:-1]] == [dai, "Còn câu này."]


def test_het_luot_ma_gop_het_thi_chi_tra_tin_hieu():
    dan, tra = sap_cum_gop(("Dạ vâng,", 0.0), cum("em nghe anh."), True)
    assert len(dan) == 2
    assert tra == [None]


# --- mảnh rỗng ---------------------------------------------------------

def test_manh_RONG_bi_bo_nhung_GIU_nhip_nghi():
    """Mảnh chỉ có dấu chấm thì không sinh tiếng, nhưng nhịp nghỉ của nó phải
    chuyển sang mảnh đầu - bỏ luôn là mảnh sau mất chỗ ngắt."""
    dan, tra = sap_cum_gop(("Dạ vâng,", 0.0), [(".", 320.0), ("em nghe anh.", 0.0)], False)
    assert [d[0] for d in dan] == ["Dạ vâng,", "em nghe anh."]
    assert dan[0][1] == 320.0, "nhịp nghỉ của mảnh rỗng bị mất"


def test_tran_dung_dung_hang_so_da_chot():
    assert TRAN_AM_TIET_GOP > 0


# --- chỉ gộp qua dấu PHẨY -------------------------------------------------
#
# Bên A nghe ra (17-08, tệp 4 bộ Lần 9): *"chữ 'ạ' — cái đã đọc từ luôn rồi mà
# 'ạ' còn chưa ngắt xong"*. Đo khe nghỉ thật sau "ạ":
#
#     bộ cũ bên A gửi   410ms
#     gộp HẾT           190ms   <- dính chữ, đúng chỗ bên A chỉ
#     không gộp         360ms
#     gộp PHẨY          360ms
#
# Gộp xoá quãng nghỉ do code chèn, mà F5 chỉ tự cho ~190ms ở dấu chấm - không đủ
# sau tiểu từ. Nên CHỈ gộp qua dấu phẩy: chỗ đó vốn không đáng nghỉ dài, còn ranh
# giới CÂU thì giữ nguyên mảnh để còn quãng nghỉ.

def test_KHONG_gop_qua_dau_CHAM():
    """Ranh giới câu phải giữ - nếu không "ạ." dính luôn chữ sau."""
    dan, _ = sap_cum_gop(("Vị trí nhà mình là mặt tiền đường lớn hay trong hẻm ạ.", 0.0),
                         cum("Ngõ trước nhà rộng khoảng bao nhiêu mét,"), False)
    assert len(dan) == 1, "đã gộp qua dấu chấm"


def test_CO_gop_qua_dau_PHAY():
    dan, _ = sap_cum_gop(("Dạ vâng,", 0.0), cum("nhu cầu bổ sung vốn thì bên em hỗ trợ tốt."), False)
    assert len(dan) == 2, "không gộp dù ranh giới là dấu phẩy"


def test_DUNG_LAI_o_dau_cham_dau_tien():
    """Gộp tới đâu thì dừng ở đó - không nhảy qua dấu chấm để gộp tiếp."""
    dan, tra = sap_cum_gop(("Dạ vâng,", 0.0),
                           cum("bên em hỗ trợ tốt.", "Cho em hỏi thêm,", "anh vay bao lâu ạ."), False)
    assert [d[0] for d in dan] == ["Dạ vâng,", "bên em hỗ trợ tốt."]
    assert [t for t, _ in tra] == ["Cho em hỏi thêm,", "anh vay bao lâu ạ."]


def test_khong_dau_cau_thi_KHONG_gop():
    """Mảnh cắt giữa câu (trần từ) không có dấu - đừng đoán, cứ để riêng."""
    dan, _ = sap_cum_gop(("bên em đang hỗ trợ rất tốt cho khách hàng", 0.0),
                         cum("có nhu cầu bổ sung vốn kinh doanh"), False)
    assert len(dan) == 1
