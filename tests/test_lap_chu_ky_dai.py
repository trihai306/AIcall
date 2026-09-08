"""Whisper kẹt vòng lặp với CHU KỲ DÀI (10-20 từ) - bộ bắt lặp cũ không thấy.

Cuộc gọi thật 64b6f2ac (06-09-2026), STT trả về (logprob −0,16, tức "tự tin"):
    'anh muốn thuê máy với em giá bao nhiêu ạ anh chẳng biết rồi ông chẳng nói
     với bà cháu từ lúc nãy là dâu có tiền chắc anh chẳng biết rồi ông chẳng nói
     với bà cháu từ lúc nãy là dâu có tiền chắc anh chẳng nói với bà cháu từ
     lúc nãy là dâu có tiền chắc'
Cụm 14 từ lặp 3 lần. `_lap_khong_the_that` chỉ xét cụm 2 từ chiếm ≥50% số cụm
và số từ khác nhau ≤ 1/4 - cả hai đều không chạm với chu kỳ dài, và câu rác
này đi thẳng vào lịch sử làm AI trả lời "em không rõ nhu cầu".
"""
from backend.services.stt_service import STTService

lap = STTService._lap_khong_the_that

RAC_THAT = ("anh muốn thuê máy với em giá bao nhiêu ạ anh chẳng biết rồi ông chẳng nói "
            "với bà cháu từ lúc nãy là dâu có tiền chắc anh chẳng biết rồi ông chẳng nói "
            "với bà cháu từ lúc nãy là dâu có tiền chắc anh chẳng nói với bà cháu từ "
            "lúc nãy là dâu có tiền chắc")


def test_bat_duoc_chu_ky_dai_lap_ba_lan():
    assert lap(RAC_THAT), "cụm 14 từ lặp 3 lần phải bị coi là vòng lặp máy"


def test_cau_dai_binh_thuong_khong_bi_oan():
    cau = ("anh muốn vay ba trăm triệu trong sáu mươi tháng thì mỗi tháng trả bao nhiêu "
           "và lãi suất có cố định không hay thả nổi theo thị trường em nhé")
    assert lap(cau) == ""


def test_lap_hai_lan_cum_ngan_van_la_noi_binh_thuong():
    # Khách nhắc lại câu hỏi hai lần là chuyện thường - chỉ chu kỳ dài lặp ≥3
    # hoặc chiếm gần hết câu mới là máy.
    assert lap("lãi suất bao nhiêu lãi suất bao nhiêu em") == ""
