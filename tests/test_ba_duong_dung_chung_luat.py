"""Test giọng, Nhắn tin và Cuộc gọi phải dùng CHUNG một bộ luật đọc.

Ba tính năng là ba đoạn mã khác nhau, và cái giá của việc chúng lệch nhau đúng là
thứ đã xảy ra nhiều lần trong dự án này:
  - chỉnh tốc trên trang Test giọng rồi ra cuộc gọi nghe khác (hệ số thoại chỉ áp
    cho một đường - xem `test_nghe_thu_dung_nhip_cuoc_goi.py`);
  - trang Test giọng cắt mảnh kiểu khác đường gọi (xem `test_chia_ca_luot.py`).

File này canh phần còn lại: luật chuẩn hoá chữ trước khi đưa vào F5.
"""
import inspect

from backend.pipeline.text_normalizer import dong_dau_cuoi, normalize_for_tts


def test_dong_dau_cuoi_chay_o_CA_HAI_duong_sinh():
    """`tts_service` sinh tiếng bằng hai đường - lô và đơn. Quên một đường thì
    nửa số mảnh mất dấu kết câu và F5 cắt phựt âm cuối ở đúng nửa đó.

    Đo được cái giá (200ms cuối, mỗi ô 5ms):
        không dấu cuối   ████████████████████████████████▓▓▓▓▓░░·
        có dấu chấm      ███████████████▓█▓▓▓▓▓▓▓▓░░░░░░░░░░·····
    """
    from backend.services import tts_service
    nguon = inspect.getsource(tts_service)
    # Mỗi chỗ gọi `normalize_for_tts` để đưa chữ xuống F5 phải bọc `dong_dau_cuoi`.
    goi_tran = [d for d in nguon.splitlines()
                if "normalize_for_tts(" in d
                and "dong_dau_cuoi" not in d
                and not d.lstrip().startswith(("#", "from", "import"))]
    assert not goi_tran, f"còn {len(goi_tran)} chỗ chưa bọc: {goi_tran}"


def test_them_dau_cham_khi_thieu():
    assert dong_dau_cuoi("câu thiếu dấu cuối") == "câu thiếu dấu cuối."


def test_khong_dung_toi_cau_da_co_dau():
    for t in ("có chấm rồi.", "hỏi thế nào?", "kêu lên!", "vế chưa xong,"):
        assert dong_dau_cuoi(t) == t


def test_khong_them_vao_chuoi_rong():
    assert dong_dau_cuoi("") == ""
    assert dong_dau_cuoi("   ") == "   "


def test_luat_chuan_hoa_khong_them_chu():
    """Cả ba đường đều đi qua `normalize_for_tts`, và nó chỉ được thêm DẤU.

    Người dùng báo "thừa chữ 'vâng'" khi bản vá cũ tự nối "Dạ" thành "Dạ vâng".
    """
    cau = "Dạ đối với mục đích kinh doanh thì bên em hỗ trợ ạ."
    ra = normalize_for_tts(cau)
    assert "vâng" not in ra
    assert len(ra.replace(",", " ").split()) == len(cau.replace(",", " ").split())
