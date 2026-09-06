"""Sổ căn cứ của MỘT cuộc gọi - thứ lưới chặn số được phép tin.

VÌ SAO CÓ FILE NÀY. Ba lưới `chan_lai_suat_bia` / `chan_so_sai` / `chan_tien_sai`
đối chiếu con số AI nói với `ngu_canh` của ĐÚNG lượt đang chạy. Mà RAG mỗi lượt
lôi về mảnh khác nhau, nên một con số có căn cứ ở lượt này thành "bịa" ở lượt
sau. Cuộc gọi thật `009d9fb3` (06-09-2026) dính đúng hai lần:

    09:17:35  AI  : "Lãi suất hiện tại là 7.9%/năm"        <- KHÔNG bị chặn
    09:17:51  CHẶN LÃI SUẤT BỊA: bịa 7.9% (tài liệu chỉ có 8.5%)

    09:17:32  khách: "anh muốn vay tầm bốn trăm triệu"
    09:18:10  CHẶN TIỀN SAI: 400 triệu (không có căn cứ trong tài liệu)

Khách nghe hai lượt liền mở đầu y hệt nhau bằng `CAU_KIEM_TRA_LAI`, và than
"hỏi lãi cao vậy sao nó trả lời 1 kiểu". Mô hình trả lời khác nhau - chính lưới
làm chúng giống nhau.

CHỈ GHI HAI THỨ, và đây là ranh giới quan trọng nhất của file:

    TÀI LIỆU   ngữ cảnh đã dựng cho mỗi lượt (RAG đã lọc sản phẩm + dữ liệu tra
               được). Đây là văn bản người soạn, không phải chữ mô hình sinh.
    LỜI KHÁCH  số khách tự nêu thì AI nhắc lại là đúng.

KHÔNG ghi lời AI. Ghi vào là để mô hình tự bảo chứng cho số nó bịa: nói sai một
lần rồi lần sau nói lại thì lưới hết chặn được. Có test canh đúng ranh giới này
(`test_so_khong_ghi_loi_ai`).

XOÁ SỔ KHI ĐỔI NEO SẢN PHẨM. `_mat_na_loc` đã bỏ mảnh lạc sản phẩm trước khi
dựng ngữ cảnh, nên thứ vào sổ luôn thuộc sản phẩm đang tư vấn. Nhưng khách
chuyển từ vay mua nhà sang vay tín chấp thì "10 tỷ" của sản phẩm cũ vẫn nằm
trong sổ và sẽ bảo chứng cho đúng con số mà `test_chua_ro_san_pham` sinh ra để
chặn. Đổi neo là xoá.
"""


class SoCanCu:
    """Gom căn cứ đã xuất hiện trong cuộc gọi. Chỉ đọc bằng `can_cu`."""

    # Trần ký tự. Cuộc dài vài chục lượt mà nối hết ngữ cảnh lại thì mỗi lượt
    # phải quét vài trăm nghìn ký tự bằng regex, ngay trên đường găng độ trễ.
    # 20k đủ chứa khoảng 90 mảnh gần nhất - xa hơn thế thì con số cũng đã cũ.
    TRAN_KY_TU = 20000

    # Giữ trong bộ nhớ nhiều hơn trần một ít rồi mới dọn, khỏi cắt list mỗi lượt.
    _TRAN_MEM = TRAN_KY_TU * 4

    def __init__(self) -> None:
        self._manh: list[str] = []
        self._da_co: set[str] = set()
        self._neo: str = ""

    # --- ghi vào ---------------------------------------------------------

    def ghi_tai_lieu(self, ngu_canh: str) -> None:
        """Ghi ngữ cảnh đã dựng cho một lượt."""
        self._them(ngu_canh)

    def ghi_khach(self, cau: str) -> None:
        """Ghi câu khách vừa nói."""
        self._them(cau)

    def doi_neo(self, san_pham: str) -> None:
        """Báo sản phẩm đang neo. Đổi sang sản phẩm KHÁC thì xoá sạch sổ.

        Neo rỗng KHÔNG xoá: lượt không nhận ra sản phẩm là chuyện thường
        (khách hỏi giờ làm việc, hỏi hồ sơ), nó không có nghĩa là đã đổi đề tài.
        """
        if not san_pham or san_pham == self._neo:
            return
        if self._neo:
            self._manh.clear()
            self._da_co.clear()
        self._neo = san_pham

    def _them(self, s: str) -> None:
        s = (s or "").strip()
        # Bỏ trùng: cùng một mảnh RAG hay quay lại nhiều lượt liền, ghi hết thì
        # trần ký tự đầy bằng bản sao và đẩy mất căn cứ thật.
        if not s or s in self._da_co:
            return
        self._manh.append(s)
        self._da_co.add(s)
        while len(self._manh) > 1 and sum(map(len, self._manh)) > self._TRAN_MEM:
            self._da_co.discard(self._manh.pop(0))

    # --- đọc ra ----------------------------------------------------------

    @property
    def can_cu(self) -> str:
        """Chuỗi để lưới đối chiếu. Cắt phần CŨ khi vượt trần."""
        s = "\n".join(self._manh)
        if len(s) <= self.TRAN_KY_TU:
            return s
        s = s[-self.TRAN_KY_TU:]
        i = s.find("\n")
        return s[i + 1:] if i >= 0 else s
