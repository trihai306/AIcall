"""Nhắc khách khi cả hai bên cùng im sau lúc AI trả lời xong.

VÌ SAO. Cuộc gọi thật `99ee5360` (05-09-2026): AI đọc xong dư nợ rồi im tuyệt
đối, đo trên bản ghi là 6 giây liền kênh AI bằng 0 và kênh khách chỉ còn nền.
Khách cúp máy (`dumpsys telecom`: REMOTE/NORMAL) - nghe như cuộc gọi đã đứt.

Người thật không im như vậy: trả lời xong thì mời tiếp một câu. Ở đây không có ai
làm việc đó, vì pipeline chỉ chạy khi VAD cắt được một lượt của khách - khách
không nói thì không có lượt nào, và không có lượt thì không có gì phát ra.

Luật tách khỏi vòng chạy để test được: vòng thật là một task nền trong
`PhoneCallBridge`, không dựng lại được trong test đơn vị.

KHÔNG import gì nặng ở đây - module này bị `phone_call_service` kéo vào, mà file
đó đã nặng sẵn.
"""

# Câu nhắc đi THẲNG xuống TTS, không qua RAG và không qua bộ chặn số - nên không
# được chứa con số nào (có test canh điều này).
#
# Lần 1 hỏi lại cho khách một lối vào. Lần 2 KHÔNG hỏi y hệt nữa mà mở đường kết
# thúc: khách im hai lần liền thì gần như chắc là đang bận hoặc đã bỏ máy, hỏi
# thêm chỉ làm phiền.
CAU_NHAC: tuple[str, ...] = (
    "Dạ anh chị còn nghe em nói không ạ?",
    "Dạ nếu anh chị đang bận thì em xin phép gọi lại sau ạ.",
)


def chon_cau_nhac(so_lan_da_nhac: int) -> str:
    """Câu cho lần nhắc thứ `so_lan_da_nhac` (đếm từ 0). Quá số câu thì lấy câu cuối."""
    if so_lan_da_nhac < 0:
        so_lan_da_nhac = 0
    return CAU_NHAC[min(so_lan_da_nhac, len(CAU_NHAC) - 1)]


# Ngưỡng im lặng cho TỪNG lần nhắc, tính từ lần nói gần nhất.
#
# Đo trên cuộc gọi thật `f2f61c42` (06-09-2026) với ngưỡng phẳng 4 giây: bắn 6
# câu nhắc trong 47 giây, có chỗ vừa hỏi "còn nghe em không" xong 4 giây đã nói
# "xin phép gọi lại sau". Khách đang NGHĨ thì đã bị giục.
#
# Người thật để khoảng 6 giây rồi mới hỏi lại, và phải im lâu hơn nhiều mới ngỏ
# lời gác máy. Nên ngưỡng lần hai dài gấp hơn hai lần, KHÔNG dùng chung một số.
HE_SO_LAN_SAU = 2.5


def nguong_cho_lan(so_lan_da_nhac: int, nguong_co_ban: float) -> float:
    """Ngưỡng im lặng cho lần nhắc thứ `so_lan_da_nhac` (đếm từ 0)."""
    if so_lan_da_nhac <= 0:
        return nguong_co_ban
    return nguong_co_ban * HE_SO_LAN_SAU


def co_nen_nhac(*, im_giay: float, so_lan_da_nhac: int, ai_dang_noi: bool,
                con_tieng_cho_phat: bool, nguong_giay: float, toi_da: int) -> bool:
    """Có nên phát câu nhắc ngay bây giờ không.

    Ba cửa chặn, theo thứ tự rẻ dần:

    1. `ai_dang_noi` - lượt đang sinh. Chen vào là tự cắt lời mình.
    2. `con_tieng_cho_phat` - lượt sinh xong nhưng tiếng còn trong hàng đợi, khách
       VẪN ĐANG NGHE. Đây là cửa dễ quên nhất: `_luot_dang_chay` đã tắt ở
       `turn_complete` trong khi tiếng còn phát thêm vài giây nữa.
    3. `toi_da` - im hai lần liền thì thôi, đừng gọi mãi vào chỗ không ai nghe.
    """
    if ai_dang_noi or con_tieng_cho_phat:
        return False
    if so_lan_da_nhac >= toi_da:
        return False
    # Ngưỡng NỚI DẦN: lần nhắc sau phải chờ lâu hơn hẳn lần trước.
    return im_giay >= nguong_cho_lan(so_lan_da_nhac, nguong_giay)

def moc_dem_im(moc_cu: float | None, con_tieng_cho_phat: bool,
               bay_gio: float) -> float | None:
    """Mốc để bắt đầu đếm im lặng, cập nhật mỗi vòng.

    VÌ SAO CẦN. Bản đầu đặt mốc tại `turn_complete` - tức lúc MÔ HÌNH sinh xong
    chữ. Nhưng tiếng còn nằm trong hàng đợi và phát tiếp 5-8 giây nữa (TTS sinh
    nhanh hơn thời gian thực nhiều lần). Đồng hồ im lặng vì thế chạy gần hết
    TRƯỚC KHI khách kịp nghe xong, nên chỉ cần im thêm một hai giây là đã bị
    nhắc. Đo trên cuộc gọi thật `55069e44` (06-09-2026): 3 câu trả lời thì cả 3
    đều bị một câu nhắc bám ngay sau, khách phàn nàn "AI cứ gọi liên tục".

    Cách sửa: chừng nào CÒN tiếng chờ phát thì mốc bị dời lên hiện tại. Khi hàng
    đợi vừa cạn, mốc chính là lúc phát xong - đó mới là lúc khách bắt đầu im.
    """
    if moc_cu is None:
        return None
    if con_tieng_cho_phat:
        return bay_gio
    return moc_cu


def dang_xu_ly_luot(*, khach_dang_noi: bool, luot_dang_chay: bool,
                    luot_task_con_chay: bool) -> bool:
    """Lượt của khách còn đang đi trên đường: nói -> STT -> LLM -> TTS?

    Ba vế, thiếu vế nào cũng để lọt một quãng mà câu nhắc chen được vào:

      khach_dang_noi      khách đang mở miệng (VAD thấy tiếng)
      luot_task_con_chay  đã nói xong, STT/LLM đang chạy - quãng 1-2 giây mà
                          `luot_dang_chay` VẪN TẮT vì chưa có mảnh tiếng nào
      luot_dang_chay      mảnh tiếng đầu đã về, AI đang nói
    """
    return bool(khach_dang_noi or luot_task_con_chay or luot_dang_chay)
