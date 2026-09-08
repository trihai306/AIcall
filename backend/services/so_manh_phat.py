"""Sổ ghi các mảnh tiếng AI đã xếp vào hàng đợi phát, kèm độ dài từng mảnh.

Vì sao cần: lúc khách cắt lời, `phone_call_service.drop_pending_audio()` bỏ
những khung còn nằm trong hàng đợi và biết nó bỏ BAO NHIÊU khung - nhưng không
biết bấy nhiêu khung đó ứng với những CHỮ nào. Không có ánh xạ đó thì không thể
đọc nốt phần khách chưa kịp nghe.

Chỉ ghi ở mức MẢNH, không tới mức từ: TTS trả tiếng theo mảnh, muốn chính xác
tới từng từ thì phải đổi cách nó trả tiếng - đắt hơn nhiều so với cái nhận được.
"""

FRAME_MS = 20

# Mảnh bị cắt mất ít hơn ngần này thì coi như khách đã nghe trọn ý. Đọc lại cả
# mảnh chỉ vì hụt vài chục mili giây cuối là bắt khách nghe lại thứ vừa nghe.
_NGUONG_COI_LA_CHUA_NGHE = 0.3


class SoManhPhat:
    def __init__(self):
        self._manh: list[tuple[str, int]] = []   # (chữ, số khung)

    def them(self, chu: str, so_khung: int):
        if chu and so_khung > 0:
            self._manh.append((chu, so_khung))

    def xoa(self):
        self._manh.clear()

    def _chua_nghe(self, so_khung_bo: int) -> list[tuple[str, int]]:
        """Duyệt NGƯỢC từ mảnh cuối: hàng đợi rút theo thứ tự, nên những khung
        còn đọng lại lúc bỏ luôn là phần ĐUÔI của những gì đã xếp vào.

        Trả về cả số khung chứ không chỉ chữ: hai mảnh có thể trùng chữ y hệt
        ("dạ vâng" hai lần trong một lượt), tra ngược theo chữ là đếm nhầm.
        """
        con: list[tuple[str, int]] = []
        lai = so_khung_bo
        for chu, n in reversed(self._manh):
            if lai <= 0:
                break
            if lai >= n * _NGUONG_COI_LA_CHUA_NGHE:
                con.append((chu, n))
            lai -= n
        con.reverse()
        return con

    def con_do(self, so_khung_bo: int) -> str:
        """Chữ khách CHƯA kịp nghe, ghép lại theo đúng thứ tự phát."""
        return " ".join(chu for chu, _ in self._chua_nghe(so_khung_bo))

    def giay_con_do(self, so_khung_bo: int) -> float:
        """Phần chưa nghe dài bao nhiêu giây - để so với trần của luật đọc-nốt."""
        khung = sum(n for _, n in self._chua_nghe(so_khung_bo))
        return round(khung * FRAME_MS / 1000, 3)

    def chu_da_xep(self) -> str:
        """Toàn bộ lời AI đã xếp vào hàng đợi trong lượt này.

        Lưới chặn vọng (`cat_loi_dieu_kien.la_vong_ai`) đối chiếu chữ nghe được
        từ kênh khách với chuỗi này.
        """
        return " ".join(chu for chu, _ in self._manh)
