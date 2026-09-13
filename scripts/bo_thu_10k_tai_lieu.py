"""Bộ thử 10.000 câu hỏi khách về TÀI LIỆU, chạy qua đường trả lời thật và tự chấm.

VÌ SAO. Các script chấm cũ chỉ chạy 4-20 câu cứng rồi in ra màn hình, nên mỗi lần
sửa luật hay đổi câu đệm không ai biết đã làm hỏng câu hỏi nào khác. Bộ này sinh
câu hỏi từ CHÍNH giá trị trong `knowledge/*.md`, mỗi câu mang đáp án kỳ vọng, chạy
qua WebSocket như trang Nhắn tin rồi chấm tự động.

ĐƯỜNG CHẠY. Tin `text_soi` (backend/api/websocket.py): đi trọn luật trả lời sẵn,
bảng hỏi-đáp, danh mục, quy tắc khoản vay, RAG/tài liệu, LLM và mọi lưới chặn,
nhưng BỎ câu đệm và TTS. Vì câu đệm (prefill) từng làm đổi câu trả lời, một phần
câu (`--ty-le-co-dem`) chạy bằng tin `text` - có câu đệm thật và có TTS.

MỖI CÂU MỘT PHIÊN MỚI (mã `bt10k_<số>`): luật khoản vay đọc lịch sử, dùng chung
phiên thì câu sau bị câu trước kéo lệch và không chấm được độc lập. Phiên thử được
ghi vào DB như phiên thật; `--don-db` xoá đúng các phiên mang tiền tố đó.

CHẤM (mỗi câu có thể dính nhiều lỗi):
  rong            không có chữ nào, hoặc metrics báo llm_rong
  chu_ngoai       có chữ Hán/Kana/Hangul
  thieu_dap_an    câu hỏi có đáp án trong tài liệu mà câu trả lời không chứa nó
  hua_kiem_tra    tài liệu có đáp án mà AI hứa "kiểm tra lại / báo lại"
  lac_san_pham    có con số chỉ nằm trong tài liệu của sản phẩm KHÁC
  so_ngoai_tai_lieu  có con số không nằm trong tài liệu, FAQ hay câu khách
  bia_ngoai_pham_vi  câu hỏi ngoài tài liệu mà AI vẫn nêu con số
  sai_huong       câu "vay X được không" / "vượt trần" trả lời ngược
  qua_dai         quá 60 từ (cảnh báo, không tính là trượt)

Chạy trên máy Win (backend :8100), nền:
    .venv\\python.exe scripts\\bo_thu_10k_tai_lieu.py --so 10000
Chỉ sinh câu hỏi để xem:  --chi-sinh
Chạy dở thì chạy lại cùng lệnh: tự bỏ qua câu đã có trong tệp kết quả.
Dừng êm: tạo tệp logs/bo_thu_10k/DUNG
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import statistics
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GOC))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Tên KHÁCH nói trong câu hỏi.
TEN_SP = {"vay_tin_chap": "vay tín chấp", "vay_mua_nha": "vay mua nhà",
          "the_tin_dung": "thẻ tín dụng", "tiet_kiem": "gửi tiết kiệm"}
# Tên gắn cho PHIÊN - phải khớp tên tệp tài liệu qua `ngu_canh_tai_lieu._ma`
# ("gửi tiết kiệm" ra "gui_tiet_kiem", không có tệp nào, và cả chủ đề tiết kiệm
# rơi về RAG - điểm thấp oan). Đúng tên trang Hội thoại dùng.
PHIEN_SP = {"vay_tin_chap": "vay tín chấp", "vay_mua_nha": "vay mua nhà",
            "the_tin_dung": "thẻ tín dụng", "tiet_kiem": "tiết kiệm"}

# ---------------------------------------------------------------------------
# NGÂN HÀNG CÂU HỎI: (mã sản phẩm, chủ đề, loại, [mẫu câu], [regex đáp án])
#   loại: fact      tài liệu có đáp án -> phải chứa ít nhất một regex đáp án
#         che       khách chê -> phải chứa regex, không được thêm số mới
#         danh_muc  hỏi danh mục sản phẩm
#         ngoai     ngoài tài liệu -> không được nêu con số
#   {sp} trong mẫu là chỗ nhắc tên sản phẩm (có thể bỏ trống khi phiên đã gắn
#   sản phẩm). Đáp án lấy NGUYÊN VĂN giá trị trong knowledge/*.md.
# ---------------------------------------------------------------------------
NGAN_HANG: list[tuple[str, str, str, list[str], list[str]]] = [
    # --- vay tín chấp ---
    ("vay_tin_chap", "lai_suat", "fact",
     ["lãi suất {sp} bao nhiêu", "{sp} lãi như nào", "lãi một năm bao nhiêu phần trăm",
      "lãi suất hiện tại của {sp} là bao nhiêu", "{sp} lãi mấy phần trăm", "mức lãi {sp} thế nào"],
     [r"7[.,]9"]),
    ("vay_tin_chap", "han_muc", "fact",
     ["{sp} vay tối đa được bao nhiêu", "hạn mức {sp} bao nhiêu", "vay được nhiều nhất bao nhiêu",
      "hạn mức tối đa của {sp} là bao nhiêu"],
     [r"500 ?triệu", r"năm trăm triệu"]),
    ("vay_tin_chap", "thoi_han", "fact",
     ["{sp} vay được bao lâu", "thời hạn vay tối đa bao lâu", "{sp} trả trong mấy năm",
      "vay tối đa mấy tháng"],
     [r"60 ?tháng", r"12.{0,12}60", r"5 năm"]),
    ("vay_tin_chap", "giai_ngan", "fact",
     ["bao lâu thì giải ngân", "{sp} giải ngân mất mấy ngày", "khi nào thì có tiền"],
     [r"24 ?(giờ|tiếng|h)", r"48 ?(giờ|tiếng)"]),
    ("vay_tin_chap", "tuoi", "fact",
     ["bao nhiêu tuổi thì vay {sp} được", "độ tuổi vay {sp} là bao nhiêu", "mấy tuổi thì vay được"],
     [r"22", r"60 ?tuổi"]),
    ("vay_tin_chap", "thu_nhap", "fact",
     ["thu nhập bao nhiêu thì vay {sp} được", "lương tối thiểu bao nhiêu mới vay được"],
     [r"5 ?triệu", r"năm triệu"]),
    ("vay_tin_chap", "ho_so", "fact",
     ["{sp} cần giấy tờ gì", "hồ sơ vay gồm những gì", "thủ tục cần chuẩn bị gì"],
     [r"căn cước|CCCD|CMND"]),
    ("vay_tin_chap", "ho_khau", "fact",
     ["có cần hộ khẩu không", "có cần kt ba không", "không có hộ khẩu thì sao"],
     [r"hộ khẩu|KT ?3"]),
    ("vay_tin_chap", "hop_dong_ld", "fact",
     ["có cần hợp đồng lao động không", "làm tự do có vay {sp} được không",
      "không có hợp đồng lao động thì vay được không"],
     [r"hợp đồng lao động|giấy phép kinh doanh"]),
    ("vay_tin_chap", "sao_ke", "fact",
     ["sao kê lương mấy tháng", "cần sao kê bao nhiêu tháng"],
     [r"3 ?tháng|ba tháng"]),
    ("vay_tin_chap", "no_xau", "fact",
     ["nợ xấu có vay {sp} được không", "dính nợ xấu nhóm ba có vay được không", "bị CIC có vay được không"],
     [r"nhóm ?(3|ba)|CIC|khó (được )?(duyệt|phê duyệt)"]),
    ("vay_tin_chap", "tat_toan_no_xau", "fact",
     ["nợ xấu đã tất toán hơn một năm có vay được không", "nợ tất toán trên một năm thì có vay được không"],
     [r"xem xét|một năm|1 năm"]),
    ("vay_tin_chap", "uu_dai", "fact",
     ["{sp} có ưu đãi gì không", "đang có khuyến mãi gì không"],
     [r"0[.,]5 ?%|voucher|500[.,]?000|miễn phí (tư vấn|thẩm định)"]),
    ("vay_tin_chap", "tra_truoc_han", "fact",
     ["trả nợ trước hạn có mất phí không", "tất toán sớm {sp} có bị phạt không"],
     [r"miễn phí|không (mất|bị|tính) phí"]),
    ("vay_tin_chap", "che_lai", "che",
     ["lãi cao quá", "mà lãi hơi cao nhỉ", "sao lãi cao thế"],
     [r"thế chấp|tốp|ưu đãi"]),
    ("vay_tin_chap", "che_han_muc", "che",
     ["hạn mức thấp vậy", "sao hạn mức lại thấp thế"],
     [r"tốp cao|không ngân hàng nào|tín chấp"]),
    # --- vay mua nhà ---
    ("vay_mua_nha", "lai_suat", "fact",
     ["lãi suất {sp} bao nhiêu", "{sp} lãi mấy phần trăm", "lãi ưu đãi {sp} là bao nhiêu"],
     [r"6[.,]5"]),
    ("vay_mua_nha", "lai_tha_noi", "fact",
     ["hết ưu đãi thì lãi {sp} bao nhiêu", "sau hai năm lãi {sp} thế nào"],
     [r"8.{0,6}10 ?%|thả nổi"]),
    ("vay_mua_nha", "han_muc", "fact",
     ["{sp} vay tối đa được bao nhiêu", "hạn mức {sp} là bao nhiêu"],
     [r"80 ?%|10 ?tỷ|mười tỷ"]),
    ("vay_mua_nha", "thoi_han", "fact",
     ["{sp} vay được bao nhiêu năm", "thời hạn {sp} tối đa bao lâu"],
     [r"25 ?năm|hai mươi lăm năm"]),
    ("vay_mua_nha", "tuoi", "fact",
     ["độ tuổi vay {sp} là bao nhiêu", "bao nhiêu tuổi thì vay {sp} được"],
     [r"22", r"65"]),
    ("vay_mua_nha", "thu_nhap", "fact",
     ["thu nhập bao nhiêu thì vay {sp} được", "{sp} yêu cầu lương bao nhiêu"],
     [r"10 ?triệu|mười triệu"]),
    ("vay_mua_nha", "tai_san", "fact",
     ["{sp} có cần tài sản đảm bảo không", "vay mua nhà có phải thế chấp không"],
     [r"tài sản đảm bảo|bất động sản|thế chấp|sổ (đỏ|hồng)"]),
    ("vay_mua_nha", "sao_ke", "fact",
     ["vay mua nhà sao kê lương mấy tháng"],
     [r"6 ?tháng|sáu tháng"]),
    ("vay_mua_nha", "ho_so", "fact",
     ["{sp} cần giấy tờ gì", "hồ sơ vay mua nhà gồm những gì"],
     [r"sổ (đỏ|hồng)|hợp đồng mua bán|CCCD|CMND|căn cước|hộ khẩu|sao kê"]),
    ("vay_mua_nha", "tra_truoc_han", "fact",
     ["{sp} trả nợ trước hạn có mất phí không", "vay mua nhà tất toán sớm có bị phạt không"],
     [r"3 ?năm|ba năm|1.{0,4}2 ?%"]),
    ("vay_mua_nha", "uu_dai", "fact",
     ["{sp} có ưu đãi gì không"],
     [r"thẩm định|6[.,]5|3 ?năm|cố định"]),
    ("vay_mua_nha", "vi_du", "fact",
     ["vay mua nhà 1 tỷ trong 20 năm thì mỗi tháng trả bao nhiêu",
      "vay một tỷ mua nhà hai mươi năm mỗi tháng trả bao nhiêu"],
     # Tài liệu ghi "khoảng 9.5 triệu"; luật tính theo dư nợ giảm dần ra 9,6.
     [r"9[.,]\d"]),
    # --- thẻ tín dụng ---
    ("the_tin_dung", "han_muc", "fact",
     ["{sp} hạn mức bao nhiêu", "mở {sp} được hạn mức tối đa bao nhiêu"],
     [r"500 ?triệu", r"10.{0,15}500"]),
    ("the_tin_dung", "mien_lai", "fact",
     ["{sp} miễn lãi bao nhiêu ngày", "thẻ tín dụng được miễn lãi mấy ngày"],
     [r"55 ?ngày|năm mươi lăm ngày"]),
    ("the_tin_dung", "cashback", "fact",
     ["{sp} có hoàn tiền không", "thẻ tín dụng hoàn tiền bao nhiêu phần trăm"],
     [r"1.{0,4}3 ?%|3 ?%|hoàn tiền"]),
    ("the_tin_dung", "phi_thuong_nien", "fact",
     ["phí thường niên {sp} bao nhiêu", "{sp} mất phí hàng năm không"],
     [r"miễn phí|200[.,]?000|400[.,]?000|800[.,]?000"]),
    ("the_tin_dung", "the_gold", "fact",
     ["thẻ gold phí thường niên bao nhiêu", "thẻ gold hạn mức bao nhiêu"],
     [r"400[.,]?000|30.{0,12}200"]),
    ("the_tin_dung", "the_platinum", "fact",
     ["thẻ platinum phí bao nhiêu", "thẻ platinum hạn mức bao nhiêu"],
     [r"800[.,]?000|100.{0,12}500"]),
    ("the_tin_dung", "the_classic", "fact",
     ["thẻ classic phí thường niên bao nhiêu", "thẻ classic hạn mức bao nhiêu"],
     [r"200[.,]?000|10.{0,12}50"]),
    ("the_tin_dung", "tuoi", "fact",
     ["mấy tuổi thì mở {sp} được", "bao nhiêu tuổi làm thẻ tín dụng được"],
     [r"18"]),
    ("the_tin_dung", "thu_nhap", "fact",
     ["mở {sp} cần thu nhập bao nhiêu", "lương bao nhiêu thì làm thẻ tín dụng được"],
     [r"5 ?triệu|năm triệu"]),
    ("the_tin_dung", "khac_ghi_no", "fact",
     ["thẻ tín dụng khác thẻ ghi nợ thế nào", "thẻ tín dụng với thẻ ghi nợ khác gì nhau"],
     [r"chi tiêu trước|trả sau|trừ (tiền )?trực tiếp"]),
    ("the_tin_dung", "quen_tra", "fact",
     ["quên trả nợ thẻ tín dụng thì sao", "trả chậm thẻ tín dụng có sao không"],
     [r"phạt|CIC|lãi|điểm tín dụng"]),
    ("the_tin_dung", "tang_han_muc", "fact",
     ["làm sao để tăng hạn mức thẻ tín dụng", "muốn nâng hạn mức thẻ thì làm thế nào"],
     [r"6 ?tháng|đúng hạn|hotline|chi nhánh"]),
    ("the_tin_dung", "tra_gop", "fact",
     ["{sp} có trả góp không lãi không", "quẹt thẻ tín dụng trả góp được không"],
     [r"0 ?%|trả góp"]),
    # --- gửi tiết kiệm ---
    ("tiet_kiem", "toi_thieu", "fact",
     ["{sp} tối thiểu bao nhiêu", "gửi ít nhất bao nhiêu tiền"],
     [r"1 ?triệu|một triệu"]),
    ("tiet_kiem", "ky_12", "fact",
     ["{sp} 12 tháng lãi bao nhiêu", "gửi một năm lãi bao nhiêu phần trăm"],
     [r"5[.,]5"]),
    ("tiet_kiem", "ky_6", "fact",
     ["{sp} 6 tháng lãi bao nhiêu", "gửi sáu tháng lãi mấy phần trăm"],
     [r"4[.,]5"]),
    ("tiet_kiem", "ky_3", "fact",
     ["{sp} 3 tháng lãi bao nhiêu"], [r"3[.,]8"]),
    ("tiet_kiem", "ky_1", "fact",
     ["{sp} 1 tháng lãi bao nhiêu"], [r"3[.,]5"]),
    ("tiet_kiem", "ky_24", "fact",
     ["{sp} 24 tháng lãi bao nhiêu", "gửi hai năm lãi bao nhiêu"], [r"5[.,]8"]),
    ("tiet_kiem", "ky_36", "fact",
     ["{sp} 36 tháng lãi bao nhiêu", "gửi ba năm lãi bao nhiêu"], [r"\b6 ?%"]),
    ("tiet_kiem", "khong_ky_han", "fact",
     ["gửi không kỳ hạn lãi bao nhiêu"], [r"0[.,]5"]),
    ("tiet_kiem", "online", "fact",
     ["{sp} online có lãi cao hơn không", "gửi online được cộng thêm bao nhiêu"],
     [r"0[.,]2"]),
    ("tiet_kiem", "rut_truoc_han", "fact",
     ["{sp} rút trước hạn thì sao", "rút tiền tiết kiệm trước hạn có mất lãi không"],
     [r"0[.,]5|không kỳ hạn"]),
    ("tiet_kiem", "dieu_kien", "fact",
     ["{sp} cần điều kiện gì", "mấy tuổi thì gửi tiết kiệm được"],
     [r"18|CCCD|CMND|căn cước"]),
    ("tiet_kiem", "thu_nhap", "fact",
     ["{sp} có cần chứng minh thu nhập không"],
     [r"không (yêu cầu|cần)|chỉ cần (cmnd|cccd|căn cước)"]),
    ("tiet_kiem", "ky_han", "fact",
     ["{sp} có những kỳ hạn nào", "gửi tiết kiệm được mấy tháng"],
     # Mô hình hay đọc bằng chữ: "từ một đến ba mươi sáu tháng" là đúng.
     [r"1.{0,12}36|không kỳ hạn|36 ?tháng|ba mươi sáu tháng"]),
    ("tiet_kiem", "uu_dai", "fact",
     ["{sp} có ưu đãi gì không"], [r"miễn phí|bảo hiểm tai nạn|100 ?triệu"]),
    ("tiet_kiem", "che_lai", "che",
     ["lãi tiết kiệm thấp quá", "sao lãi gửi thấp thế"],
     [r"tốp cao|bảo hiểm tiền gửi|kỳ hạn"]),
    # --- danh mục ---
    ("", "danh_muc_chung", "danh_muc",
     ["bên em có những sản phẩm gì", "ngân hàng bên bạn có dịch vụ gì", "bên em có những gói nào"],
     [r"vay tín chấp", r"vay mua nhà", r"thẻ tín dụng", r"tiết kiệm"]),
    ("", "danh_muc_vay", "danh_muc",
     ["bên bạn cho vay những cái gì", "bên em cho vay những gì", "có mấy loại vay"],
     [r"tín chấp", r"mua nhà"]),
    ("", "khong_co_bao_hiem", "danh_muc",
     ["bên em có bảo hiểm không", "có bán bảo hiểm không em"],
     [r"chưa có|không có"]),
    # --- ngoài tài liệu ---
    ("", "ngoai_vay_mua_xe", "ngoai", ["vay mua xe lãi bao nhiêu", "vay mua ô tô được bao nhiêu"], []),
    ("", "ngoai_chuyen_khoan", "ngoai", ["phí chuyển khoản liên ngân hàng bao nhiêu"], []),
    ("", "ngoai_thau_chi", "ngoai", ["lãi suất thấu chi bao nhiêu"], []),
    ("", "ngoai_ty_gia", "ngoai", ["tỷ giá đô hôm nay bao nhiêu"], []),
    ("", "ngoai_vay_kinh_doanh", "ngoai", ["có cho vay kinh doanh không", "vay vốn kinh doanh lãi bao nhiêu"], []),
    ("", "ngoai_bao_hiem_nhan_tho", "ngoai", ["bảo hiểm nhân thọ một tháng đóng bao nhiêu"], []),
]

# Câu hỏi có số tiền/kỳ hạn: sinh theo lưới giá trị, đáp án tính từ tài liệu.
MUC_VAY = [30, 50, 80, 100, 150, 200, 250, 300, 350, 400, 450, 500, 600, 800]
KY_HAN = [12, 18, 24, 36, 48, 60]
LAI_TC = 7.9
TRAN_TC = 500

MO_DAU = ["", "cho anh hỏi ", "em ơi ", "ờ ", "chị hỏi chút ", "thế ", "cho chị hỏi là ", "à em "]
DUOI = ["", " em", " nhỉ", " vậy", " ạ", " thế", " em nhé"]
# Lỗi nghe nhầm đã gặp thật trên kênh 8kHz (kịch bản sc_nganhang ghi sẵn).
NGHE_NHAM = [("lãi suất", "lãnh xuất"), ("hạn mức", "hạng mức"), ("tín chấp", "tính chấp"),
             ("căn cước", "cẩn cước")]

SO_CHU = {"một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5, "sáu": 6, "bảy": 7, "tám": 8, "chín": 9}


def _bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _dien(mau: str, sp: str, nhac_sp: bool) -> str:
    ten = TEN_SP.get(sp, "")
    if "{sp}" in mau:
        return re.sub(r"\s+", " ", mau.replace("{sp}", ten if nhac_sp else "")).strip()
    return mau


def sinh_cau_hoi(so: int, seed: int) -> list[dict]:
    """Sinh đúng `so` câu, rải đều theo chủ đề, cố định theo `seed`."""
    rng = random.Random(seed)
    chu_de: list[list[dict]] = []
    for sp, cd, loai, maus, dap in NGAN_HANG:
        bien = []
        for mau in maus:
            for md in MO_DAU:
                for du in DUOI:
                    for nhac in (True, False):
                        if not sp and not nhac:
                            continue
                        # Phiên chưa gắn sản phẩm thì câu PHẢI nhắc sản phẩm,
                        # không thì chính người cũng không trả lời được.
                        if sp and "{sp}" in mau and not nhac:
                            phien_sp = PHIEN_SP[sp]
                        elif sp and "{sp}" not in mau:
                            phien_sp = PHIEN_SP[sp]
                        else:
                            phien_sp = "" if rng.random() < 0.4 else PHIEN_SP.get(sp, "")
                        cau = (md + _dien(mau, sp, nhac) + du).strip()
                        bien.append({"sp": sp, "chu_de": cd, "loai": loai, "cau": cau,
                                     "phien_sp": phien_sp, "dap": dap})
        chu_de.append(bien)
    # Chủ đề tính toán: mỗi (mức, kỳ hạn, cách hỏi) là một biến thể.
    tinh = []
    for x in MUC_VAY:
        for t in KY_HAN:
            for mau in ("vay {x} triệu trong {t} tháng thì mỗi tháng trả bao nhiêu",
                        "anh vay {x} triệu {t} tháng mỗi tháng đóng bao nhiêu",
                        "ví dụ vay {x} triệu trong {t} tháng thì như nào"):
                tinh.append({"sp": "vay_tin_chap", "chu_de": "tinh_tra_gop", "loai": "tinh",
                             "cau": mau.format(x=x, t=t), "phien_sp": "vay tín chấp",
                             "x": x, "t": t, "dap": []})
    chu_de.append(tinh)
    nhu_cau = []
    for x in MUC_VAY + [700, 1000]:
        for mau in ("anh vay {x} triệu có được không", "muốn vay tầm {x} triệu được không em",
                    "vay {x} triệu được không"):
            nhu_cau.append({"sp": "vay_tin_chap", "chu_de": "nhu_cau_vay", "loai": "nhu_cau",
                            "cau": mau.format(x=x), "phien_sp": "vay tín chấp", "x": x, "dap": []})
    chu_de.append(nhu_cau)

    moi_cd = max(1, so // len(chu_de))
    ra: list[dict] = []
    for bien in chu_de:
        rng.shuffle(bien)
        lay = [bien[i % len(bien)] for i in range(moi_cd)]
        ra.extend(dict(b) for b in lay)
    while len(ra) < so:
        ra.append(dict(rng.choice(rng.choice(chu_de))))
    ra = ra[:so]
    rng.shuffle(ra)
    for i, q in enumerate(ra):
        q["i"] = i
        # 12% câu mang lỗi nghe nhầm thật của kênh thoại.
        if rng.random() < 0.12:
            for dung, sai in NGHE_NHAM:
                if dung in q["cau"]:
                    q["cau"] = q["cau"].replace(dung, sai, 1)
                    q["nghe_nham"] = sai
                    break
    return ra


# ---------------------------------------------------------------------------
# CHẤM
# ---------------------------------------------------------------------------
CHU_NGOAI = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
HUA = re.compile(r"kiểm tra lại|xem lại|tra lại|báo lại|liên hệ lại|chuyên viên (sẽ )?(liên hệ|gọi)|"
                 r"chưa có thông tin|chưa có quy định", re.I)
SO_RE = re.compile(r"\d+(?:[.,]\d+)*")


def _chuan_so(s: str) -> str:
    """"7,9" -> "7.9"; "500.000" -> "500000"; "3,4" -> "3.4"."""
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", s):
        return re.sub(r"[.,]", "", s)
    return s.replace(",", ".")


def cac_so(text: str) -> set[str]:
    return {_chuan_so(m.group()) for m in SO_RE.finditer(text or "")}


def nap_tai_lieu() -> dict[str, str]:
    kho = {}
    for ma in TEN_SP:
        p = GOC / "knowledge" / "products" / f"{ma}.md"
        kho[ma] = p.read_text(encoding="utf-8") if p.exists() else ""
    faq = GOC / "knowledge" / "faq" / "faq_banking.md"
    kho["faq"] = faq.read_text(encoding="utf-8") if faq.exists() else ""
    return kho


def cham(q: dict, tra_loi: str, metrics: dict, kho: dict[str, str]) -> list[str]:
    loi: list[str] = []
    t = (tra_loi or "").strip()
    if not t or metrics.get("llm_rong"):
        loi.append("rong")
    if CHU_NGOAI.search(t):
        loi.append("chu_ngoai")

    so_tl = cac_so(t)
    so_cau = cac_so(q["cau"])
    sp = q.get("sp") or ""
    so_minh = cac_so(kho.get(sp, "")) | cac_so(kho["faq"]) if sp else set()
    so_tat_ca = set().union(*(cac_so(v) for v in kho.values()))
    tinh_ra = metrics.get("tra_tu_quy_tac_tai_chinh") in ("tinh_tra_gop",)

    loai = q["loai"]
    if loai in ("fact", "che", "danh_muc"):
        dap = q.get("dap") or []
        if dap:
            can_tat_ca = loai == "danh_muc" and q["chu_de"].startswith("danh_muc")
            khop = [bool(re.search(r, t, re.I)) for r in dap]
            if (can_tat_ca and not all(khop)) or (not can_tat_ca and not any(khop)):
                loi.append("thieu_dap_an")
        if loai == "fact" and HUA.search(t):
            loi.append("hua_kiem_tra")
    if loai == "che":
        moi = so_tl - so_minh - so_cau
        if moi:
            loi.append("so_ngoai_tai_lieu")
    if loai == "ngoai":
        if so_tl - so_cau:
            loi.append("bia_ngoai_pham_vi")
    if sp and loai in ("fact", "che", "nhu_cau") and not tinh_ra:
        ngoai = so_tl - so_minh - so_cau - {"1", "2", "0"}
        # Số chỉ có trong tài liệu sản phẩm khác = lạc sản phẩm; số không nằm
        # trong tài liệu nào = bịa.
        lac = {s for s in ngoai if s in so_tat_ca}
        if lac:
            loi.append("lac_san_pham")
        if ngoai - lac:
            loi.append("so_ngoai_tai_lieu")
    if loai == "tinh":
        x, th = q["x"], q["t"]
        if x > TRAN_TC:
            if not re.search(r"500 ?triệu", t) or not re.search(r"vượt|tối đa|chưa", t, re.I):
                loi.append("sai_huong")
        else:
            ky_vong = x / th + x * LAI_TC / 100 / 12
            gan = [float(s) for s in so_tl if re.fullmatch(r"\d+(\.\d+)?", s)]
            if not any(abs(g - ky_vong) <= max(0.15, ky_vong * 0.1) for g in gan):
                loi.append("thieu_dap_an")
            if HUA.search(t):
                loi.append("hua_kiem_tra")
    if loai == "nhu_cau":
        x = q["x"]
        if x > TRAN_TC and not re.search(r"vượt|tối đa|chưa (phù hợp|được)|hơn mức", t, re.I):
            loi.append("sai_huong")
        if x <= TRAN_TC and re.search(r"vượt|không (được|thể) vay", t, re.I):
            loi.append("sai_huong")
    if len(t.split()) > 60:
        loi.append("qua_dai")
    return loi


LOI_TRUOT = {"rong", "chu_ngoai", "thieu_dap_an", "hua_kiem_tra", "lac_san_pham",
             "so_ngoai_tai_lieu", "bia_ngoai_pham_vi", "sai_huong"}


def nguon_tra_loi(m: dict) -> str:
    for k in ("tra_tu_danh_muc", "tra_tu_quy_tac_tai_chinh", "tra_tu_ho_so", "luot_thuong_gap"):
        if m.get(k):
            return f"{k}:{m[k]}"
    if m.get("bang_doc_thang"):
        return f"bang_doc_thang:{m.get('bang_hoi_dap')}"
    if m.get("llm_rong"):
        return "llm_rong"
    return "llm"


# ---------------------------------------------------------------------------
# CHẠY
# ---------------------------------------------------------------------------
async def mot_cau(host: str, q: dict, dung_dem: bool, tien_to: str) -> dict:
    import websockets
    sid = f"{tien_to}{q['i']:05d}"
    t0 = time.perf_counter()
    kieu = "text" if dung_dem else "text_soi"
    full, metrics, loi_ws = "", {}, ""
    try:
        async with websockets.connect(f"ws://{host}/ws/call/{sid}", max_size=None,
                                      open_timeout=20) as ws:
            await ws.send(json.dumps({"type": "set_session", "customer_name": "Anh/Chị",
                                      "product": q["phien_sp"]}))
            while True:
                m = json.loads(await asyncio.wait_for(ws.recv(), 20))
                if m.get("type") == "session_updated":
                    break
            await ws.send(json.dumps({"type": kieu, "text": q["cau"], "turn_id": 1}))
            while True:
                raw = await asyncio.wait_for(ws.recv(), 90)
                if isinstance(raw, bytes):
                    continue
                m = json.loads(raw)
                if m.get("type") == "turn_complete":
                    full = m.get("full_response", "") or ""
                    metrics = m.get("metrics", {}) or {}
                    break
                if m.get("type") == "error":
                    loi_ws = str(m.get("message", ""))[:200]
    except Exception as e:  # một câu hỏng không được làm chết cả buổi 3 giờ
        loi_ws = f"{type(e).__name__}: {e}"[:200]
    return {"full": full, "metrics": metrics, "loi_ws": loi_ws, "kieu": kieu,
            "ms": round((time.perf_counter() - t0) * 1000)}


GIU_METRICS = ("ttfa_ms", "total_ms", "llm_ttft_ms", "tra_tu_quy_tac_tai_chinh", "tra_tu_danh_muc",
               "tra_tu_ho_so", "luot_thuong_gap", "bang_hoi_dap", "bang_doc_thang", "llm_rong",
               "neo_san_pham", "cong_cu", "chan_so_sai", "chan_tien_sai", "chan_lai_suat_bia",
               "chan_thuoc_tinh", "thuoc_tinh_da_sua", "chan_tu_cam", "filler_text")


async def chay(args) -> Path:
    thu = GOC / "logs" / "bo_thu_10k"
    thu.mkdir(parents=True, exist_ok=True)
    ra = thu / f"ket_qua_seed{args.seed}_{args.so}.jsonl"
    cau = sinh_cau_hoi(args.so, args.seed)
    rng = random.Random(args.seed + 1)
    dung_dem = {q["i"] for q in cau if rng.random() < args.ty_le_co_dem}
    xong = set()
    if ra.exists():
        for dong in ra.read_text(encoding="utf-8").splitlines():
            try:
                xong.add(json.loads(dong)["i"])
            except Exception:
                pass
    con = [q for q in cau if q["i"] not in xong]
    print(f"Bộ thử: {len(cau)} câu, đã có {len(xong)}, còn {len(con)} -> {ra}", flush=True)
    kho = nap_tai_lieu()
    hang = asyncio.Queue()
    for q in con:
        hang.put_nowait(q)
    khoa = asyncio.Lock()
    dem = Counter()
    t_bat_dau = time.time()

    async def tho():
        while True:
            if (thu / "DUNG").exists():
                return
            try:
                q = hang.get_nowait()
            except asyncio.QueueEmpty:
                return
            kq = await mot_cau(args.host, q, q["i"] in dung_dem, args.tien_to)
            loi = cham(q, kq["full"], kq["metrics"], kho)
            if kq["loi_ws"] and not kq["full"]:
                loi = ["loi_ket_noi"] + loi
            dong = {"i": q["i"], "cau": q["cau"], "sp": q["sp"], "phien_sp": q["phien_sp"],
                    "chu_de": q["chu_de"], "loai": q["loai"], "nghe_nham": q.get("nghe_nham", ""),
                    "kieu": kq["kieu"], "tra_loi": kq["full"], "nguon": nguon_tra_loi(kq["metrics"]),
                    "loi": loi, "ms": kq["ms"], "loi_ws": kq["loi_ws"],
                    "metrics": {k: kq["metrics"][k] for k in GIU_METRICS if k in kq["metrics"]}}
            async with khoa:
                with ra.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(dong, ensure_ascii=False) + "\n")
                dem["xong"] += 1
                if any(e in LOI_TRUOT or e == "loi_ket_noi" for e in loi):
                    dem["truot"] += 1
                if dem["xong"] % 100 == 0:
                    toc = dem["xong"] / max(1, time.time() - t_bat_dau)
                    print(f"  {len(xong) + dem['xong']}/{len(cau)}  trượt {dem['truot']}  "
                          f"{toc:.2f} câu/s  còn ~{(len(con) - dem['xong']) / max(toc, 1e-6) / 60:.0f} phút",
                          flush=True)

    await asyncio.gather(*(tho() for _ in range(args.workers)))
    return ra


def tong_ket(ra: Path) -> dict:
    dong = [json.loads(x) for x in ra.read_text(encoding="utf-8").splitlines() if x.strip()]
    n = len(dong)
    truot = [d for d in dong if any(e in LOI_TRUOT or e == "loi_ket_noi" for e in d["loi"])]
    loi_dem = Counter(e for d in dong for e in d["loi"])
    theo_cd = defaultdict(lambda: [0, 0])
    theo_nguon = defaultdict(lambda: [0, 0])
    theo_kieu = defaultdict(lambda: [0, 0])
    theo_nham = defaultdict(lambda: [0, 0])
    for d in dong:
        hong = any(e in LOI_TRUOT or e == "loi_ket_noi" for e in d["loi"])
        for bang, khoa in ((theo_cd, f"{d['sp'] or '-'}/{d['chu_de']}"),
                           (theo_nguon, d["nguon"].split(":")[0]), (theo_kieu, d["kieu"]),
                           (theo_nham, "nghe_nham" if d["nghe_nham"] else "sach")):
            bang[khoa][0] += 1
            bang[khoa][1] += hong
    vi_du = defaultdict(list)
    for d in truot:
        for e in d["loi"]:
            if len(vi_du[e]) < 8:
                vi_du[e].append({"cau": d["cau"], "phien_sp": d["phien_sp"], "tra_loi": d["tra_loi"][:220],
                                 "nguon": d["nguon"], "loi": d["loi"]})

    def ty(b):
        return {k: {"so": v[0], "truot": v[1], "ty_le_dat": round(1 - v[1] / v[0], 4)}
                for k, v in sorted(b.items(), key=lambda kv: kv[1][1] / kv[1][0], reverse=True)}

    ms = [d["ms"] for d in dong if d["ms"]]
    tk = {
        "tong": n, "dat": n - len(truot), "truot": len(truot),
        "ty_le_dat": round(1 - len(truot) / n, 4) if n else 0,
        "loi": dict(loi_dem.most_common()),
        "theo_chu_de": ty(theo_cd), "theo_nguon": ty(theo_nguon), "theo_kieu": ty(theo_kieu),
        "nghe_nham": ty(theo_nham),
        "ms": {"p50": statistics.median(ms) if ms else None,
               "p95": sorted(ms)[int(len(ms) * 0.95)] if ms else None},
        "vi_du": vi_du,
    }
    (ra.parent / (ra.stem + "_tong_ket.json")).write_text(
        json.dumps(tk, ensure_ascii=False, indent=1), encoding="utf-8")
    return tk


def cham_lai(ra: Path, so: int, seed: int) -> None:
    """Chấm lại kết quả đã có bằng bộ chấm hiện tại, không gọi lại backend.
    Dòng kết quả không lưu đáp án mẫu nên phải sinh lại bộ câu theo seed."""
    theo_i = {q["i"]: q for q in sinh_cau_hoi(so, seed)}
    kho = nap_tai_lieu()
    dong = [json.loads(x) for x in ra.read_text(encoding="utf-8").splitlines() if x.strip()]
    doi = 0
    for d in dong:
        if "loi_ket_noi" in d["loi"]:
            continue
        moi = cham(theo_i[d["i"]], d["tra_loi"], d.get("metrics") or {}, kho)
        doi += moi != d["loi"]
        d["loi"] = moi
    ra.write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in dong), encoding="utf-8")
    print(f"chấm lại {len(dong)} dòng, đổi kết luận {doi} dòng")


def don_db(tien_to: str) -> None:
    import sqlite3
    db = sqlite3.connect(GOC / "data" / "app.db")
    mau = tien_to.replace("_", r"\_") + "%"
    for bang in ("conversation_turns", "latency_metrics", "call_sessions"):
        n = db.execute(f"DELETE FROM {bang} WHERE session_id LIKE ? ESCAPE '\\'", (mau,)).rowcount
        print(f"xoá {n} dòng {bang}")
    db.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--so", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--host", default="127.0.0.1:8100")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--ty-le-co-dem", type=float, default=0.1)
    ap.add_argument("--tien-to", default="bt10k_")
    ap.add_argument("--chi-sinh", action="store_true")
    ap.add_argument("--chi-tong-ket", action="store_true")
    ap.add_argument("--don-db", action="store_true")
    ap.add_argument("--cham-lai", action="store_true")
    ap.add_argument("--tep", default="")
    args = ap.parse_args()

    if args.chi_sinh:
        cau = sinh_cau_hoi(args.so, args.seed)
        print(json.dumps(Counter(q["chu_de"] for q in cau).most_common(), ensure_ascii=False))
        for q in cau[:25]:
            print(q["i"], q["phien_sp"] or "-", "|", q["cau"])
        print("so cau khac nhau:", len({(q["cau"], q["phien_sp"]) for q in cau}))
        return
    if args.don_db:
        don_db(args.tien_to)
        return
    ra = GOC / "logs" / "bo_thu_10k" / f"ket_qua_seed{args.seed}_{args.so}.jsonl"
    if args.tep:
        ra = Path(args.tep)
    if args.cham_lai:
        cham_lai(ra, args.so, args.seed)
    elif not args.chi_tong_ket:
        ra = asyncio.run(chay(args))
    tk = tong_ket(ra)
    print(json.dumps({k: tk[k] for k in ("tong", "dat", "truot", "ty_le_dat", "loi", "ms")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
