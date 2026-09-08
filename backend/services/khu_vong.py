"""Khử tiếng AI vọng ngược vào kênh khách, dùng chính tiếng AI đã ghi xuống máy
làm tham chiếu.

VÌ SAO CÓ FILE NÀY. Đo trên bản ghi thật 06-09-2026 (`scripts/do_vong_ai.py`):
với số 0833816298, kênh khách trong lúc AI nói chỉ thấp hơn tiếng AI **6dB**,
tương quan −0,37 ở độ trễ ~340ms - tiếng AI phát ra loa của khách rồi lọt lại
micro. STT của cuộc đó ra toàn chữ rác ("mọi người rút lui", "rồi không đình mà
sợ đấy"). Người dùng nghe lại bản ghi và xác nhận: có tiếng Lan.

KHÁC MỌI PHÉP LỌC NHIỄU ĐÃ BỊ BÁC BỎ trong dự án (xem bộ nhớ
`chat-ai-loc-tap-am-vo-ich`): ở đây có TÍN HIỆU THAM CHIẾU - ta biết chính xác
thứ đã vọng - nên chỉ trừ phần tương quan với nó và không đụng phần còn lại.

Thuật toán: NLMS theo khối (block NLMS) trên cửa sổ 512 tap đặt quanh một mốc
trễ ước lượng bằng tương quan chéo. Trễ phải ước lượng vì nó gồm đệm của máy,
đường GSM đi và về, và khoảng cách loa-micro của khách - vài trăm mili giây và
khác nhau từng máy. Không cập nhật bộ lọc khi khách đang nói đè (Geigel), không
thì lời khách bị "học" thành vọng và bị trừ đi.

Cái giá: vọng đi qua bộ mã GSM nên PHI TUYẾN, bộ lọc tuyến tính chỉ trừ được
phần tuyến tính - kỳ vọng 10-15dB, không triệt hẳn.

Tham chiếu phải lấy ở `_write_loop` (lúc khung THẬT SỰ đi xuống máy), không phải
lúc xếp hàng: hàng đợi có thể chứa vài giây tiếng và phần bị vứt khi cắt lời
không bao giờ phát ra.

KHÔNG import torch/soundfile: module bị `phone_call_service` kéo vào và phải chạy
được trên máy không GPU để test.
"""
import numpy as np

# Tham chiếu im lâu hơn ngần này (cộng trễ tối đa) thì vọng không thể còn tới,
# bộ khử tự ngủ và khung đi qua nguyên vẹn - lúc rảnh tốn 0.
IM_SAU_MS = 1000.0
# Mức tham chiếu (float32, 1.0 = đầy thang) coi là AI đang phát.
MUC_HOAT_DONG = 1e-3
# Geigel: micro to hơn ngần này so với tham chiếu (đã căn trễ) thì có khách nói
# đè - đóng băng bộ lọc. 0,9 (−1dB): vọng đo được là −6dB, còn dư một quãng.
TI_LE_NOI_DE = 0.9
# Tin cậy tối thiểu của mốc trễ (tương quan chuẩn hoá) mới đem dùng.
TIN_TRE_TOI_THIEU = 0.05
# ERLE tốt nhất từng đạt từ mức này coi như bộ lọc đã hội tụ: 10 = 10dB.
ERLE_HOI_TU = 10.0
# Sau khi phát hiện nói đè, giữ đóng băng thêm ngần này khung (10 = 200ms).
HANGOVER_KHUNG = 10
# Tham chiếu giải thích được từ ngần này năng lượng khung micro (0,5 = 3dB) thì
# khung là vọng thuần, không phải lời khách.
PHAN_VONG_THUAN = 0.5
# Năng lượng bộ lọc (Σw²) tối đa còn hợp lý: đường vọng không khuếch đại quá 12dB.
NANG_LUONG_W_TOI_DA = 16.0


class KhuVong:
    def __init__(self, sr: int = 8000, khung: int = 160, so_tap: int = 64,
                 tre_toi_da_ms: float = 800.0, mu: float = 0.5,
                 cua_so_tre_s: float = 1.5):
        self.sr, self.khung, self.so_tap, self.mu = sr, khung, so_tap, mu
        self.tre_toi_da = int(sr * tre_toi_da_ms / 1000)
        self.cua_so = int(sr * cua_so_tre_s)
        # Hai vòng đệm cùng độ dài, mẫu mới nhất ở cuối. Đủ để căn trễ tối đa
        # cộng bề rộng bộ lọc cộng cửa sổ ước lượng.
        self.N = self.tre_toi_da + self.so_tap + self.khung + self.cua_so
        self.ref = np.zeros(self.N, dtype=np.float32)
        self.mic = np.zeros(self.N, dtype=np.float32)
        self.w = np.zeros(self.so_tap, dtype=np.float32)
        self.tre: int | None = None          # mẫu
        self.tin_tre = 0.0
        self.khung_ke_tu_ai = 10 ** 9
        self.dem_khung = 0
        self.dem_cap_nhat = 0
        # Thống kê để ghi log cuối cuộc gọi.
        self.khung_da_khu = 0
        self.khung_dong_bang = 0
        # Tỉ số năng lượng micro / sai số, làm mượt - thước đo bộ lọc đã học tới đâu.
        self.erle = 0.0
        self.erle_max = 0.0             # tốt nhất từng đạt, giảm rất chậm
        self.con_dong_bang = 0          # hangover còn lại sau lần phát hiện nói đè
        self.dong_bang_vi: dict[str, int] = {}   # đếm theo lý do, để chẩn đoán
        # Khung vừa xử lý có phải VỌNG THUẦN không (phần lớn năng lượng được
        # tham chiếu giải thích). VAD đọc cờ này để không tính khung đó là
        # "khách còn nói", và không mở lượt/cân nhắc cắt lời vì nó.
        self.la_vong = False
        self.khung_la_vong = 0
        self.so_lan_dat_lai = 0          # bộ lọc nổ / học nhầm phải đặt lại

    # --- vào ---------------------------------------------------------------
    def them_tham_chieu(self, x: np.ndarray):
        """Khung tiếng AI vừa ghi xuống máy (float32, tần số `sr`)."""
        x = np.asarray(x, dtype=np.float32)
        n = len(x)
        self.ref[:-n] = self.ref[n:]
        self.ref[-n:] = x
        if float(np.sqrt(np.mean(x * x))) >= MUC_HOAT_DONG:
            self.khung_ke_tu_ai = 0
        else:
            self.khung_ke_tu_ai += 1

    @property
    def dang_thuc(self) -> bool:
        """Còn có thể có vọng tới không?"""
        ngu_sau = (IM_SAU_MS + self.tre_toi_da * 1000.0 / self.sr) / (self.khung * 1000.0 / self.sr)
        return self.khung_ke_tu_ai <= ngu_sau

    def xu_ly(self, m: np.ndarray) -> np.ndarray:
        """Khung micro (float32) -> khung đã trừ vọng. AI im thì trả nguyên."""
        m = np.asarray(m, dtype=np.float32)
        n = len(m)
        self.mic[:-n] = self.mic[n:]
        self.mic[-n:] = m
        self.dem_khung += 1
        self.la_vong = False
        if not self.dang_thuc:
            return m
        # Ước lượng lại mốc trễ mỗi 500ms, NHƯNG chỉ khi bộ lọc chưa làm việc
        # tốt. Đang hội tụ mà vẫn ước lượng lại thì lúc khách chen vào, đỉnh
        # tương quan lệch đi, mốc mới thay mốc cũ và bộ lọc bị đặt lại về 0 -
        # rồi học lại đúng lúc đang có lời khách.
        if self.dem_khung % 25 == 0 and self.erle_max < ERLE_HOI_TU:
            self._uoc_luong_tre()
        if self.tre is None:
            return m

        # Cửa sổ tap đặt QUANH mốc trễ (nửa trước, nửa sau), không phải chỉ
        # phía sau: trễ trên đường GSM rung vài mili giây, đặt lệch một phía là
        # rung về phía kia rơi ra ngoài bộ lọc. Giới hạn LS trên bản ghi thật
        # (`scripts/gioi_han_vong_thuan.py`): 64 tap được 10,9dB và 8,7dB trên
        # khung vọng thuần giữ lại - không kém 512 tap, mà hội tụ nhanh gấp 8.
        # Tap k (0..so_tap-1) ứng với trễ `tre - nua + k`: nửa đầu bộ lọc nằm
        # TRƯỚC mốc, nửa sau nằm SAU mốc.
        nua = self.so_tap // 2
        tre0 = self.tre - nua
        bd = self.N - n - tre0 - (self.so_tap - 1)
        kt = self.N - tre0
        if bd < 0 or kt > self.N:
            return m
        x = self.ref[bd:kt]                           # dài n + so_tap - 1

        # --- phát hiện khách nói đè, rồi mới quyết có cập nhật hay không ----
        # Ba dấu hiệu, dấu nào cũng đủ. Kiểm chứng trên tín hiệu tổng hợp: chỉ
        # có Geigel thì khách nói ngang mức tham chiếu lọt qua, bộ lọc "học"
        # lời khách và ERLE sập từ 217 xuống 8 trong 1,5 giây - đầu ra tiến về
        # đúng mức lời khách, tức đang trừ mất lời khách.
        rms_m = float(np.sqrt(np.mean(m * m)))
        rms_x = float(np.sqrt(np.mean(x[-n:] ** 2)))
        # Tham chiếu đoạn này gần im (giữa hai từ của AI): không có vọng để học,
        # mà mẫu số chuẩn hoá `so_tap × ref²` nhỏ hơn cả ε nên mỗi bước cập
        # nhật lớn cỡ 1,6 - bộ lọc nổ. Đo trên bản ghi thật 06-09-2026: đầu ra
        # TO HƠN đầu vào 11-32dB, đúng vì đây. Chỉ trừ, không học.
        y0 = np.convolve(x, self.w, "valid")
        if rms_x < MUC_HOAT_DONG:
            e0 = m - y0
            self.la_vong = False
            self.khung_da_khu += 1
            return e0.astype(np.float32)
        e0 = m - y0
        e_m, e_y, e_e = float(np.dot(m, m)), float(np.dot(y0, y0)), float(np.dot(e0, e0))
        ly_do = ""
        # (1) Geigel - chỉ khi tham chiếu đoạn này thật sự có tiếng. Bản ghi
        # thật có những khung tham chiếu rỗng lẻ (lỗ 1 khung), lúc đó rms_x ~ 0
        # và Geigel bắn oan; kèm hangover 200ms là đóng băng gần như trọn cuộc
        # (đo: 1231/1300 khung, bộ lọc không học được gì).
        noi_de = rms_x >= MUC_HOAT_DONG and rms_m > TI_LE_NOI_DE * rms_x
        if noi_de:
            ly_do = "geigel"
        # Mốc so sánh là ERLE TỐT NHẤT từng đạt (`erle_max`), không phải ERLE
        # hiện tại: khách nói đè làm ERLE hiện tại sụt, mà lấy chính nó làm mốc
        # thì cổng tự mở lại và bộ lọc lại học lời khách. `erle_max` chỉ tăng
        # (giảm rất chậm), nên cổng chỉ mở khi sai số trở về gần mức quen thuộc
        # - tức khách đã ngừng.
        if self.erle_max >= ERLE_HOI_TU:
            if e_m > 2.0 * e_y + 1e-9:                        # (2) mạnh hơn vọng dự đoán
                noi_de, ly_do = True, ly_do or "manh_hon_du_doan"
            if e_e > 0 and e_m / e_e < self.erle_max / 4.0:   # (3) sai số cao bất thường
                noi_de, ly_do = True, ly_do or "sai_so_cao"
        # Hangover: lời nói có quãng lặng giữa các âm tiết, phát hiện được ở âm
        # tiết này thì giữ đóng băng qua quãng lặng tới âm tiết sau. CHỈ cho hai
        # luật dựa trên dự đoán - Geigel bắn lẻ tẻ trên nhiễu, cho nó hangover
        # là phủ kín thời gian.
        if noi_de and ly_do != "geigel":
            self.con_dong_bang = HANGOVER_KHUNG
        elif not noi_de and self.con_dong_bang > 0:
            self.con_dong_bang -= 1
            noi_de, ly_do = True, "hangover"

        # Khung là VỌNG THUẦN khi mô hình giải thích được quá nửa năng lượng
        # (>= 3dB). Khách nói đè thì phần giải thích được tụt hẳn (lời khách
        # không tương quan với tham chiếu) nên cờ tự tắt.
        self.la_vong = e_m > 0 and (1.0 - e_e / e_m) >= PHAN_VONG_THUAN
        if self.la_vong:
            self.khung_la_vong += 1

        if noi_de:
            self.khung_dong_bang += 1
            self.dong_bang_vi[ly_do] = self.dong_bang_vi.get(ly_do, 0) + 1
            self.khung_da_khu += 1
            return e0.astype(np.float32)

        # NLMS TỪNG MẪU, không theo khối. Đo trên tín hiệu tổng hợp (vọng −6dB,
        # trễ 340ms): theo khối mu=8 được 16,5dB và mu=32 phân kỳ; từng mẫu
        # mu=0,5 được 24dB, tốn 45ms CPU cho mỗi giây tiếng - chỉ chạy lúc AI
        # đang nói và khách im nên chấp nhận được.
        e = np.empty(n, dtype=np.float32)
        w = self.w
        # Sàn cho mẫu số: năng lượng của một vector tham chiếu ở đúng mức hoạt
        # động tối thiểu. Dưới sàn là mẫu quá nhỏ để tin, bước đi bị kìm lại.
        san = self.so_tap * MUC_HOAT_DONG * MUC_HOAT_DONG
        for i in range(n):
            xi = x[i:i + self.so_tap][::-1]           # xi[k] = tham chiếu trễ k mẫu
            e[i] = m[i] - float(np.dot(w, xi))
            w += (self.mu * e[i] / max(float(np.dot(xi, xi)), san)) * xi
        self.dem_cap_nhat += 1
        # Đường vọng qua loa-micro của khách không thể khuếch đại quá 12dB
        # (năng lượng bộ lọc > 16): tới đó là đã học nhầm, đặt lại.
        if not np.all(np.isfinite(w)) or float(np.dot(w, w)) > NANG_LUONG_W_TOI_DA:
            w[:] = 0.0
            self.dem_cap_nhat = 0
            self.erle = self.erle_max = 0.0
            self.so_lan_dat_lai += 1
        # ERLE đo bằng sai số TRƯỚC khi thích nghi trong khung này (a priori).
        # Bản đầu đo bằng sai số sau thích nghi: lạc quan giả, chỉ 10 khung đã
        # báo 6,5 rồi bật cổng nói-đè lên một bộ lọc chưa học xong -> đóng băng
        # vĩnh viễn ngay từ giây thứ nhất.
        if e_m > 0 and e_e > 0:
            self.erle = 0.9 * self.erle + 0.1 * (e_m / e_e)
            self.erle_max = max(self.erle_max * 0.999, self.erle)
        self.khung_da_khu += 1
        return e

    # --- ước lượng trễ -----------------------------------------------------
    def _uoc_luong_tre(self):
        L = self.cua_so
        mic_w = self.mic[-L:]
        ref_big = self.ref[self.N - L - self.tre_toi_da:]      # dài L + tre_toi_da
        if float(np.sqrt(np.mean(ref_big * ref_big))) < MUC_HOAT_DONG:
            return
        if float(np.sqrt(np.mean(mic_w * mic_w))) < MUC_HOAT_DONG:
            return
        n_fft = 1 << int(np.ceil(np.log2(len(ref_big) + L)))
        A = np.fft.rfft(ref_big, n_fft)
        B = np.fft.rfft(mic_w, n_fft)
        # corr[k] = sum_i ref_big[i + k] * mic_w[i]; mic muộn hơn ref -> trễ = tre_toi_da - k
        corr = np.fft.irfft(A * np.conj(B), n_fft)[: self.tre_toi_da + 1]
        # chuẩn hoá theo năng lượng từng đoạn ref trượt
        cs = np.concatenate(([0.0], np.cumsum(ref_big.astype(np.float64) ** 2)))
        nang_ref = cs[L:L + self.tre_toi_da + 1] - cs[: self.tre_toi_da + 1]
        nang_mic = float(np.dot(mic_w, mic_w))
        chuan = np.abs(corr) / (np.sqrt(nang_ref * nang_mic) + 1e-9)
        k = int(np.argmax(chuan))
        tin = float(chuan[k])
        tre_moi = self.tre_toi_da - k
        # Mốc cũ mất dần tin cậy để mốc mới có cửa thay thế khi điều kiện đổi.
        self.tin_tre *= 0.9
        if tin < max(TIN_TRE_TOI_THIEU, self.tin_tre):
            return
        if self.tre is None or abs(tre_moi - self.tre) > 2 * self.khung:
            self.w[:] = 0.0
            self.dem_cap_nhat = 0
            self.erle = self.erle_max = 0.0
            self.tre = tre_moi
        self.tin_tre = tin
