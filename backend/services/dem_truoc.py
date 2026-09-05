"""Vòng đệm giữ tiếng TRƯỚC lúc VAD nhận ra khách bắt đầu nói.

Cả hai đường thu (trình duyệt và điện thoại) đều mở lượt theo cùng một luật:
"N khung liên tiếp vượt ngưỡng". Cả hai cũng mắc cùng một lỗi - vứt sạch phần
tiếng TRƯỚC thời điểm nhận ra. Mà phụ âm đầu tiếng Việt (h, th, l, c, x) năng
lượng thấp nên chính chúng nằm dưới ngưỡng.

Hậu quả đo được 05-09-2026 (`scripts/do_cut_dau_cau.py`, PhoWhisper-medium):

    cắt   0ms -> CER 0,000
    cắt 200ms -> CER 0,334    "hạn mức được bao nhiêu" -> "mức được bao nhiêu"
    cắt 400ms -> CER 0,466    "lãi suất bao nhiêu"     -> "nhiều"

Khớp đúng chữ rác thấy trên cuộc gọi thật (phiên 4cd44fb7): `sẵn mức được bao
nhiêu`, `mừng được mời nhiều`, `lãi suất rất nhiều`.

## Vì sao 300ms chứ không phải "càng dài càng chắc"

Phần đệm chứa tiếng AI vọng ngược vào micro. Whisper chép luôn lời AI thành lời
khách. Đo (`scripts/do_dem_truoc.py`, thêm đệm vào đầu câu rồi chấm CER):

| loại đệm | +300ms | +500ms | +800ms |
|---|---|---|---|
| im lặng / nền phòng | 0,000 | 0,000 | 0,000 |
| vọng AI 15% | 0,000 | 0,073 | 0,483 |
| vọng AI 30% | 0,033 | 0,481 | 0,896 |

Kiểu hỏng: `năm trăm triệu đồng lãi suất bao nhiêu`. Nên đây là núm CÓ TRẦN,
không phải càng to càng tốt. Nới quá 400ms thì phải đo lại bằng chính script đó.
"""
from __future__ import annotations

import math
from collections import deque

# Mốc mặc định cho cả hai đường. Xem bảng ở trên trước khi đổi.
DEM_TRUOC_MS = 300


class DemTruoc:
    """Giữ `ms` mili-giây tiếng gần nhất, BẤT KỂ có vượt ngưỡng hay không.

    Khác biệt cốt lõi với mã cũ: không biết gì về ngưỡng, nên chỗ trũng giữa hai
    âm tiết không làm mất phần đã giữ.
    """

    def __init__(self, ms: float = DEM_TRUOC_MS, khung_ms: float = 20.0):
        # Làm tròn LÊN: thiếu một khung là thiếu đúng phần phụ âm đầu.
        self.so_khung = max(1, math.ceil(ms / khung_ms))
        self.khung_ms = khung_ms
        self._d: deque[bytes] = deque(maxlen=self.so_khung)

    def them(self, khung: bytes) -> None:
        self._d.append(bytes(khung))

    def lay(self) -> bytes:
        """Nối lại theo đúng thứ tự thời gian. KHÔNG làm rỗng đệm."""
        return b"".join(self._d)

    def xoa(self) -> None:
        self._d.clear()

    def __len__(self) -> int:
        return len(self._d)
