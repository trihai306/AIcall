"""Hỏi lại khi KHÔNG NGHE RA CHỮ - thay cho cơ chế nhắc theo im lặng.

VÌ SAO ĐỔI HƯỚNG. Bản trước nhắc theo ĐỒNG HỒ: khách im quá N giây thì hỏi "còn
nghe em không". Nó sai về nguyên tắc - im lặng không có nghĩa là hỏng, người ta
im để nghĩ. Và trên cuộc gọi thật nó đẻ ra năm lỗi liên tiếp (xem bộ nhớ
`chat-ai-do-tre-luot-dau`), trong đó có hai lỗi làm khách khó chịu thật:
bám ngay sau mỗi câu trả lời, và lọt vào lịch sử làm mô hình mất mạch.

Người dùng chốt 06-09-2026: *"Bỏ cơ chế hỏi cho tôi đi, nếu AI không nghe thấy
chữ mới hỏi hoặc chữ có vấn đề"*. Tức chỉ hỏi khi có LÝ DO NGHE ĐƯỢC, không hỏi
theo đồng hồ.

Hai loại lý do, xử ở hai chỗ khác nhau:

  KHÔNG RA CHỮ   STT trả chuỗi rỗng dù có tiếng -> file này, phát câu hỏi lại.
                 Trước đây lượt đó IM HOÀN TOÀN: chỉ gửi sự kiện lỗi rồi
                 `turn_complete` rỗng, khách nói mà không được đáp gì.

  CHỮ CÓ VẤN ĐỀ  STT ra chữ nhưng vô nghĩa ("hắn mất mỏi nhược") -> để mô hình
                 tự hỏi lại theo quy tắc 11 của prompt. Đã đo là chạy đúng,
                 không cần chặn thêm bằng code.
"""

# Không chứa con số: câu đi thẳng xuống TTS, không qua RAG lẫn bộ chặn số.
CAU_HOI_LAI: tuple[str, ...] = (
    "Dạ em nghe chưa rõ, anh chị nói lại giúp em được không ạ?",
    "Dạ đường truyền hơi nhiễu, anh chị nhắc lại giúp em một lần nữa ạ.",
)

# Hỏi lại quá số này thì thôi. Kênh có thể đang ồn liên tục hoặc khách đã bỏ máy;
# hỏi mãi vào chỗ không ai nghe thì phiền hơn là im.
TOI_DA_LIEN_TIEP = 2


def nen_hoi_lai(so_lan_lien_tiep: int, toi_da: int = TOI_DA_LIEN_TIEP) -> bool:
    """Có nên hỏi lại không, khi đây là lần thứ `so_lan_lien_tiep` liền không ra chữ.

    Đếm LIÊN TIẾP, đặt lại về 0 ngay khi nghe được một lượt có chữ - nếu đếm dồn
    cả cuộc gọi thì một cuộc gọi dài bình thường cũng chạm trần rồi câm.
    """
    return 0 <= so_lan_lien_tiep < toi_da


def chon_cau_hoi_lai(so_lan_lien_tiep: int) -> str:
    """Câu cho lần hỏi thứ `so_lan_lien_tiep` (đếm từ 0). Quá số câu thì lấy câu cuối."""
    if so_lan_lien_tiep < 0:
        so_lan_lien_tiep = 0
    return CAU_HOI_LAI[min(so_lan_lien_tiep, len(CAU_HOI_LAI) - 1)]
