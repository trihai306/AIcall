"""Đổi câu khi lưới chặn số bắn HAI LƯỢT LIỀN.

VÌ SAO CÓ FILE NÀY. Cuộc gọi thật `ccb61c05` (06-09-2026):

    khách: anh vay một lăm          -> CHẶN TIỀN SAI: 150 triệu -> thay cả câu
    khách: anh vay trong một năm    -> CHẶN TIỀN SAI: 150 triệu -> thay cả câu

Hai lượt liền mở đầu bằng đúng một câu. Chặn thì ĐÚNG - khách nói mờ ("một
lăm"), mô hình đoán thành 150 triệu, con số đó không có căn cứ nào. Nhưng khách
nghe ra là AI chỉ biết mỗi một câu, và đó là lời than *"trả lời 1 kiểu"*.

Câu mẫu cũ còn tự nuôi vòng lặp: "em kiểm tra lại rồi báo sau" không gỡ được gì,
nên lượt sau mô hình vẫn nói lại đúng con số đó và lại bị chặn. Từ lần thứ hai
phải HỎI LẠI con số - gốc là khách nói mờ thì chỉ khách gỡ được.

Không lấy `random`: cùng một cuộc gọi phải ra cùng một chuỗi câu để soi lại bản
ghi còn đối chiếu được với log.
"""
from backend.pipeline.text_normalizer import CAU_KIEM_TRA_LAI

# Thứ tự có ý: câu 1 giữ nguyên hành vi cũ (lượt bị chặn đơn lẻ là ca thường
# gặp nhất), từ câu 2 chuyển sang HỎI vì lúc đó đã thành vòng lặp.
#
# KHÔNG câu nào được chứa chữ số - chính chúng lại đi qua lưới chặn số.
CAU_CHAN: tuple[str, ...] = (
    CAU_KIEM_TRA_LAI,
    "Dạ để em khỏi nói sai, anh chị nhắc lại giúp em con số mình đang cần ạ?",
    "Dạ em chưa dám chốt số khi chưa tra kỹ, anh chị cho em xin lại thông tin mình muốn ạ.",
)


def cau_chan(so_lan_lien_tiep: int) -> str:
    """Câu cho lần chặn thứ `so_lan_lien_tiep` (đếm từ 1). Quá thì lấy câu cuối."""
    if so_lan_lien_tiep < 1:
        so_lan_lien_tiep = 1
    return CAU_CHAN[min(so_lan_lien_tiep, len(CAU_CHAN)) - 1]


def dem_chan_lien_tiep(luot: int, moc_cu: int | None,
                       so_lan_cu: int) -> tuple[int, int]:
    """Số lần chặn LIÊN TIẾP và mốc lượt mới, sau khi lượt `luot` bị chặn.

    Đếm theo LƯỢT chứ không theo lần gọi: `_chan_so` chạy trên từng mảnh của
    một lượt, đếm theo mảnh thì một lượt hai mảnh đã nhảy sang câu thứ hai dù
    khách mới nghe chặn một lần.

    Giữa hai lần chặn mà có một lượt trả lời bình thường thì khách không nghe
    thấy lặp - đếm lại từ đầu.
    """
    if moc_cu is None or luot - moc_cu > 1:
        return 1, luot
    if luot == moc_cu:                 # vẫn trong chính lượt đó
        return max(so_lan_cu, 1), moc_cu
    return so_lan_cu + 1, luot
