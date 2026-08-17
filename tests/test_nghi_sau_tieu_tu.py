"""Nghỉ sau vế kết bằng TIỂU TỪ phải ngắn hơn nghỉ sau câu thường.

Bên A nghe ra (17-08): *"chữ ạ nó cứ nặng kiểu gì á, ạ nặng cái rồi mới nói"*.

BA LẦN ĐO TRƯỚC ĐỀU SAI CHỖ. Máy nhận dạng báo chữ "ạ" dài 480ms nên tôi đi tìm
lỗi ngân dài và lỗi âm sắc suốt bốn thước đo. Đo lại bằng NĂNG LƯỢNG thì:

    "ạ" thật    120ms CÓ TIẾNG
    rồi         320ms IM LẶNG TUYỆT ĐỐI (quãng nghỉ code chèn)

Máy nhận dạng gộp quãng im vào chữ. Chữ "ạ" KHÔNG ngân - nó ngắn, và cái nghe
"nặng" là âm tắc thanh hầu của dấu nặng bị cắt cụt vào đúng khoảng im, rồi phải
đợi 320ms mới nói tiếp.

Nghỉ 320ms là nghỉ của DẤU CHẤM. Sau tiểu từ lễ phép ("...trong hẻm ạ. Ngõ
trước...") người thật đi tiếp nhanh hơn nhiều - tiểu từ không kết thúc ý, nó chỉ
đánh dấu thái độ.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path("/Users/hainc/duan/freelancer/chat-ai/.claude/worktrees/ai-voice-quality-issue-86cab4")))

from backend.pipeline.text_chunker import (NGHI_CHAM_MS, NGHI_PHAY_MS,
                                           NGHI_TIEU_TU_MS, nhip_nghi_sau)


def test_ve_ket_bang_TIEU_TU_thi_nghi_NGAN_hon():
    dai = nhip_nghi_sau("Vị trí nhà mình là mặt tiền đường lớn hay trong hẻm ạ.")
    thuong = nhip_nghi_sau("đất ở đô thị có nhà kiên cố như vậy thì thanh khoản rất tốt.")
    assert dai < thuong, f"tiểu từ {dai}ms không ngắn hơn câu thường {thuong}ms"
    assert dai == NGHI_TIEU_TU_MS


def test_van_con_nghi_chu_KHONG_bo_han():
    """Bỏ hẳn thì chữ sau dính vào đuôi 'ạ' - đúng lỗi bên A báo trước đó."""
    assert NGHI_TIEU_TU_MS >= 150.0


def test_cac_tieu_tu_khac_cung_duoc():
    for tu in ("nhé", "nha", "nhỉ"):
        assert nhip_nghi_sau(f"em gửi anh xem trước {tu}.") == NGHI_TIEU_TU_MS


def test_KHONG_dinh_vao_cau_thuong():
    assert nhip_nghi_sau("bên em sẽ báo lại ngay sau khi có kết quả.") == NGHI_CHAM_MS


def test_phay_khong_doi():
    assert nhip_nghi_sau("Dạ vâng,") == NGHI_PHAY_MS


def test_tieu_tu_kem_dau_PHAY_thi_van_la_phay():
    """"..., ạ," giữa câu thì đó là ngắt ý, không phải kết câu."""
    assert nhip_nghi_sau("dạ vâng ạ,") == NGHI_PHAY_MS
