"""Bù đuôi: cho F5 một chỗ để "ngân dài" rồi cắt bỏ chỗ đó.

>>> ĐANG TẮT. ĐÃ THI CÔNG, ĐÃ ĐO, VÀ BÁC BỎ ngày 16-08-2026. <<<
>>> Giữ lại mã và số đo để khỏi ai thử lại từ đầu.            <<<

KẾT QUẢ: bù đuôi làm chữ cuối của khách DÀI RA, không ngắn đi. Đo bằng mốc từng
chữ, cùng một câu ("Anh chuẩn bị bảng lương ba tháng gần nhất nhé."):

    KHÔNG bù   chữ "nhé" = 340ms
    CÓ bù      chữ "nhé" = 500ms      <- TỆ HƠN

Đo end-to-end qua đường xuất, 8 câu: độ ngân 1.82x -> 2.08x, thời gian sinh
315ms -> 1060ms mỗi câu. Chỉ có CER là tốt lên (0.58% -> 0.30%), tức KHÂU CẮT
chạy đúng - cái sai là giả thuyết, không phải bản thi công.

VÌ SAO SAI: giả thuyết là "F5 cần một chỗ để đổ phần kéo dài, cho nó mẩu bù thì
nó tha chữ thật". Thực tế `thoi_luong_ep` cấp thời lượng THEO SỐ ÂM TIẾT, nên
thêm chữ là cấp thêm thời lượng - và chữ cuối của khách vẫn hút phần dôi ra.
Mẩu bù không hút hộ (đo được: "vâng" 240ms, "ạ" 140ms, đều NGẮN hơn "nhé" 500ms
dù chúng mới là chữ đứng cuối).

CÒN DÙNG ĐƯỢC: phần mốc từng chữ (`stt_service.moc_tung_chu` +
`word_timestamps` của máy chủ nhận dạng) là hạ tầng tốt, cắt chính xác tới từng
chữ - CER 0.30% chứng minh điều đó. Việc nào cần biết "chữ nào ở giây nào" thì
dùng lại được ngay.

VẤN ĐỀ. F5 sinh MỖI MẢNH như một phát ngôn trọn vẹn, nên nó kéo dài âm tiết cuối
mảnh - thứ người thật chỉ làm ở CUỐI CÂU. Đo trên 97 tệp xuất thật: âm tiết cuối
trung vị 277ms so với ~150ms của âm tiết thường, tức **1,55x**; 25/97 tệp có âm
cuối ≥2x, cá biệt 500ms (3,1x). Và số chữ bị ngân tăng thẳng theo số mảnh:

    1 mảnh 0.72   2 mảnh 1.39   3 mảnh 2.00   4 mảnh 3.10   (tương quan +0.50)

Người dùng nghe ra: *"lâu lâu có chữ nó đọc kiểu ạ nhưng chữ ngân dài"*.

CÁCH CHỮA. Nối thêm một mẩu chữ vào cuối rồi cắt bỏ phần tiếng của nó. F5 dồn
phần kéo dài vào mẩu bù, chữ thật của khách kết thúc đúng nhịp. Đo được: nội
dung thật kết thúc sớm hơn **330ms** (1,80s thay vì 2,13s trên cùng một câu).

VÌ SAO PHẢI DÙNG MỐC TỪNG CHỮ ĐỂ CẮT. Đã thử ba cách rẻ hơn và cả ba đều ăn vào
chữ thật:

    cắt ở khe lặng ≥100ms        ngân 1.03x nhưng CER 0.58% -> 7.07%
    cắt theo tỉ lệ âm tiết       ngân 1.25x nhưng CER        -> 6.65%
    khe lặng + bám đáy năng lượng ngân 1.34x nhưng CER       -> 1.99%

Gốc của cả ba: **không phải câu nào F5 cũng chừa khe lặng trước mẩu bù**. Quét 7
mẩu bù khác nhau trên 8 câu, tỉ lệ có khe ≥60ms:

    " Dạ." 1/8   " Vâng." 4/8   ", vâng." 4/8   ". Cảm ơn." 7/8   ". Tạm biệt." 7/8

Mẩu nhiều âm tiết mở đầu bằng phụ âm tắc tách bạch hơn hẳn, nhưng vẫn không bao
giờ đủ 8/8. Nên chỗ cắt phải lấy từ MỐC THỜI GIAN CỦA CHỮ, không đoán từ tín
hiệu.

GIÁ PHẢI TRẢ, và vì sao chỉ dùng cho ĐƯỜNG XUẤT: mỗi mảnh tốn thêm một lượt STT
(~300ms) cộng phần sinh dôi ra cho mẩu bù (~15%). Đường thoại có trần TTFA nên
KHÔNG dùng; đường xuất file không có ràng buộc đó.
"""
import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

# Mẩu bù. KHÔNG được có dấu chấm phía trước - đó là lỗi đã mắc và đo được.
#
# Thử `". Tạm biệt."` thì dấu chấm tạo ra một CÂU MỚI, nên câu gốc vẫn kết thúc
# và VẪN được kéo dài. Mốc chữ cho thấy rõ: "nhé" chạy 1.72->2.06 = 340ms rồi
# "tạm" mới bắt đầu. Đo end-to-end: ngân 1.82x -> 2.09x, tức TỆ HƠN không bù.
#
# Mẩu bù phải NỐI LIỀN cụm để chữ cuối của khách không còn ở vị trí kết câu.
# Không cần nó tách bạch về mặt tín hiệu: chỗ cắt lấy từ MỐC CHỮ chứ không dò
# khe lặng, nên mẩu ngắn dính liền vẫn cắt được chính xác.
MAU_BU = " vâng ạ."

# Chữ đầu tiên của mẩu bù, dùng để tìm chỗ cắt trong danh sách mốc chữ.
_CHU_DAU_MAU_BU = "vâng"

# Lùi thêm chừng này trước khi cắt. Mốc `start` của faster-whisper rơi vào lúc
# âm THANH của chữ bắt đầu, mà phụ âm tắc có quãng đóng câm trước đó thuộc về
# chính chữ ấy - không lùi thì còn sót một tiếng "tắc" rất khẽ ở đuôi.
LUI_MS = 40.0


def _bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def tim_moc_cat(doan: list[dict]) -> float | None:
    """Giây bắt đầu của mẩu bù, lấy từ mốc từng chữ. None nếu không tìm ra.

    So khớp KHÔNG DẤU: PhoWhisper hay trả "vang" thay vì "vâng", và một dấu sai
    không được phép làm hỏng chỗ cắt.

    Lấy lần xuất hiện CUỐI CÙNG: "vâng" là chữ RẤT hay gặp trong chính lời của
    bot ("dạ vâng em hiểu rồi ạ"), nên lần đầu gần như chắc chắn không phải mẩu
    bù. Đây là lý do phải quét hết rồi lấy cái sau cùng.
    """
    moc = None
    for d in doan or ():
        for w in d.get("words") or ():
            sach = _bo_dau(re.sub(r"[^\w\sÀ-ỹ]", "", w.get("word", "")))
            if sach == _bo_dau(_CHU_DAU_MAU_BU):
                moc = float(w.get("start", 0.0))
    return moc


def cat_theo_moc(pcm, sr: int, moc_giay: float):
    """Cắt tiếng tại `moc_giay`, lùi `LUI_MS`. Trả nguyên bản nếu mốc vô lý."""
    if moc_giay is None:
        return pcm
    n = int(max(0.0, moc_giay - LUI_MS / 1000.0) * sr)
    # Lưới an toàn: mốc quá sớm nghĩa là STT nghe nhầm chữ nào đó thành "vâng".
    # Cắt theo nó sẽ mất nửa câu của khách - thà giữ nguyên còn hơn.
    if n < int(0.35 * len(pcm)):
        logger.warning("bu_duoi: mốc cắt %.2fs quá sớm so với %.2fs tiếng — bỏ qua",
                       moc_giay, len(pcm) / sr)
        return pcm
    return pcm[:n]
