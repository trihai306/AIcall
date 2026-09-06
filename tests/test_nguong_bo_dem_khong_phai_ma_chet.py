"""Ngưỡng bỏ câu đệm phải THẬT SỰ kích hoạt được.

Lỗi đã xảy ra (08-2026 → 06-09-2026): `_FILLER_BO_QUA_MS = 700` nằm trong
`streaming_pipeline` kèm một đoạn chú thích dài giải thích vì sao cần nó, nhưng
nó so với `can_che_ms` — hàm có SÀN 1800ms (thoại) / 2000ms (chat). Sàn đó làm
`can_che < 700` luôn False, nên nhánh bỏ câu đệm là MÃ CHẾT và câu đệm phát ở
mọi lượt suốt một tháng. Không có gì báo lỗi: log sạch, test xanh.

Bộ test này canh đúng cái bẫy đó — một hằng số ngưỡng phải nằm trong TẦM VỚI
của đại lượng nó so sánh.
"""
import pytest

from backend.services.filler_pick import (NGUONG_BO_DEM_MS, can_che_ms,
                                          du_doan_cho_ms)


def _luot(ttfa, la_thoai=True):
    return {"ttfa_ms": ttfa, "la_thoai": la_thoai}


def test_nguong_nam_trong_tam_voi_cua_du_doan():
    """Đường nhanh thật thì dự đoán phải TỤT XUỐNG DƯỚI ngưỡng.

    Đây là bài kiểm tra mà bản cũ trượt: cùng lịch sử này, `can_che_ms` trả
    1800 nên không đời nào dưới 700.
    """
    su = [_luot(300), _luot(350)]
    du_doan = du_doan_cho_ms(su, la_thoai=True)
    assert du_doan < NGUONG_BO_DEM_MS

    # Và đây là bằng chứng vì sao KHÔNG được dùng can_che_ms cho việc này:
    assert can_che_ms(su, la_thoai=True, mac_dinh=1800.0) > NGUONG_BO_DEM_MS


@pytest.mark.parametrize("mac_dinh", [1800.0, 2000.0])
def test_san_luon_cao_hon_nguong_bo_dem(mac_dinh):
    """Canh thẳng vào cơ chế gây lỗi, để ai hạ sàn cũng thấy ràng buộc này.

    Chừng nào sàn còn cao hơn ngưỡng, `can_che_ms` còn KHÔNG dùng được để quyết
    định bỏ câu đệm. Test này không đòi sửa sàn - nó đòi hai đại lượng đừng bị
    dùng lẫn.
    """
    assert can_che_ms([], la_thoai=True, mac_dinh=mac_dinh) > NGUONG_BO_DEM_MS


def test_duong_cham_thi_van_phat_dem():
    """TTFA thật của máy này: p50 1774ms (130 lượt, 06-09-2026).

    Ngưỡng phải nằm DƯỚI mức đó, nếu không nó bỏ đệm ở lượt trung bình và khách
    nghe im lặng gần 2 giây.
    """
    su = [_luot(1774)]
    assert du_doan_cho_ms(su, la_thoai=True) > NGUONG_BO_DEM_MS


def test_luot_dau_khong_bao_gio_bi_bo_dem():
    """Chưa có số đo -> None -> nơi gọi phải phát.

    Lượt đầu là lượt CHẬM NHẤT cuộc gọi (tra hồ sơ nguội, đo được TTFA 8026ms).
    Bỏ đệm ở đó là hỏng đúng chỗ đau nhất.
    """
    assert du_doan_cho_ms([], la_thoai=True) is None


def test_nguong_dung_moc_1_giay_nguoi_dung_chot():
    """Người dùng 06-09: "có 1s để im lặng rồi nói".

    Chốt bằng test để lần sau ai đổi số cũng phải đọc lại lý do.
    """
    assert NGUONG_BO_DEM_MS == 1000.0
