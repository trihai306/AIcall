"""Câu mồi từ vựng phải ĐI TỚI model, không dừng ở cửa HTTP.

Kiểu hỏng đã xảy ra (bắt được 13-08-2026): `stt_service` gửi `prompt=moi_tu_vung()`
trong form từ lâu, nhưng `/inference` không KHAI trường đó. FastAPI bỏ qua trường
lạ mà không kêu một tiếng nào - không log, không lỗi, mã trả về vẫn 200. Tính năng
viết xong, có cả biến thể vùng miền, nằm chết suốt mà không ai biết.

Không test nào bắt được vì cả hai đầu đều "đúng" khi soi riêng. Chỗ đứt nằm ở
đoạn nối. Ba test dưới đây canh đúng đoạn nối đó, và không cần nạp model.
"""
import inspect

from backend.services.stt_service import moi_tu_vung
from whisper_server import pho_server


def test_endpoint_khai_truong_prompt():
    """Không khai thì FastAPI vứt lặng lẽ - đúng kiểu hỏng đã xảy ra."""
    assert "prompt" in inspect.signature(pho_server.inference).parameters


def test_prompt_chay_toi_ham_phien_am():
    assert "prompt" in inspect.signature(pho_server._transcribe_sync).parameters


def test_ten_truong_khop_voi_ben_gui():
    """Hai đầu phải gọi cùng một tên. Đổi tên một bên là đứt lại y như cũ."""
    nguon = inspect.getsource(
        __import__("backend.services.stt_service", fromlist=["x"])
    )
    assert '"prompt"' in nguon, "stt_service phải gửi trường tên đúng là 'prompt'"


def test_moi_tu_vung_co_noi_dung():
    """Mồi rỗng thì `initial_prompt=None` và cả tính năng thành vô nghĩa."""
    assert moi_tu_vung("").strip()
    assert moi_tu_vung("nam").strip() != moi_tu_vung("").strip()
