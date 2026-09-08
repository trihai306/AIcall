"""Ngân sách chờ phân loại tình huống phải khớp với các mốc im lặng.

Ba hằng số nằm ở HAI module khác nhau nhưng cùng quyết định một việc: câu đệm
có kịp biết tình huống hay không.

    phone_call_service.SPEC_CUOI_MS    - đoán cuối câu nổ ở mốc im lặng này
    phone_call_service.SILENCE_END_MS  - lượt kết thúc ở mốc im lặng này
    StreamingPipeline._CHO_TINH_HUONG_MS - `_send_filler` chờ thêm bấy nhiêu

Hiệu hai mốc đầu là quãng bản đoán được CHẠY TRƯỚC khi lượt bắt đầu. Cộng thêm
ngân sách chờ mới ra tổng thời gian STT được phép tốn. Ngắn hơn STT thật thì
`spec_stt` chưa về lúc chọn câu đệm, và mọi lượt như vậy rơi về rổ chung.

Không có test này thì sửa một hằng ở module này âm thầm phá hằng ở module kia,
và triệu chứng duy nhất nhìn thấy được là dòng log "chưa có spec_stt".
"""
from backend.pipeline.streaming_pipeline import StreamingPipeline
from backend.services.phone_call_service import SILENCE_END_MS, SPEC_CUOI_MS

# STT chậm nhất đo được trên cuộc gọi thật 06-09-2026 (logs/backend.log, chín
# lần phiên âm đoán trước): 178 / 230 / 306 / 375 / 426 / 449 / 520 / 621 / 829.
STT_CHAM_NHAT_MS = 829


def test_ngan_sach_cho_phu_het_stt_da_do():
    chay_truoc = SILENCE_END_MS - SPEC_CUOI_MS
    tong = chay_truoc + StreamingPipeline._CHO_TINH_HUONG_MS
    assert tong >= STT_CHAM_NHAT_MS, (
        f"chỉ cho STT {tong}ms (chạy trước {chay_truoc}ms + chờ "
        f"{StreamingPipeline._CHO_TINH_HUONG_MS}ms) nhưng đo được tới "
        f"{STT_CHAM_NHAT_MS}ms -> những lượt chậm mất hẳn tình huống")


# Dư bao nhiêu so với STT chậm nhất thì còn chấp nhận được.
#
# Cần lưới này vì chiều DƯ không có triệu chứng nào nhìn ra được: log vẫn sạch,
# test vẫn xanh, câu đệm vẫn đúng tình huống - chỉ có khách ngồi nghe im lâu hơn.
#
# Đã xảy ra thật: 650 chốt ngày 06-09 khi `PHONE_SILENCE_END_MS=500`, tức đà chạy
# trước chỉ 200ms. Cùng ngày hôm đó `PHONE_SILENCE_END_MS` nâng lên 1000, đà chạy
# trước thành 700ms, và 650 hoá thành DƯ 521ms mà không ai thấy. Cái giá đo trên
# cuộc gọi 08c0d3e0: `_send_filler` là await ĐẦU TIÊN của lượt nên nó chặn cả câu
# trả lời thật - 3/10 lượt câu đệm ra muộn 555/796/867ms, cộng cửa sổ im 1000ms
# thành 1,5-1,9 giây khách không nghe thấy gì.
DU_TOI_DA_MS = 300


def test_ngan_sach_cho_khong_du_thua():
    """Chờ là khách nghe im. Dư ngân sách = trả tiền cho thứ không dùng tới."""
    chay_truoc = SILENCE_END_MS - SPEC_CUOI_MS
    tong = chay_truoc + StreamingPipeline._CHO_TINH_HUONG_MS
    assert tong - STT_CHAM_NHAT_MS <= DU_TOI_DA_MS, (
        f"cho STT tận {tong}ms (chạy trước {chay_truoc}ms + chờ "
        f"{StreamingPipeline._CHO_TINH_HUONG_MS}ms) trong khi chậm nhất đo được "
        f"chỉ {STT_CHAM_NHAT_MS}ms -> dư {tong - STT_CHAM_NHAT_MS}ms, mà quãng dư "
        f"này nằm trên đường găng của CÂU TRẢ LỜI THẬT chứ không riêng câu đệm")


def test_ngan_sach_cho_khong_dai_hon_muc_chiu_duoc_quang_im():
    """Chờ = khách nghe im. Đừng chờ lâu hơn mức hệ thống tự coi là chịu được.

    `_FILLER_BO_QUA_MS` là mức mà dưới nó hệ thống thấy im lặng còn tự nhiên hơn
    một câu đệm. Chờ lâu hơn chính mức đó là tự tạo ra quãng im mình đang tránh.
    """
    assert (StreamingPipeline._CHO_TINH_HUONG_MS
            <= StreamingPipeline._FILLER_BO_QUA_MS)
