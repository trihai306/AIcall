"""Kiểm tra bộ lọc STT không vứt nhầm câu ngắn khách nói thật.

Bối cảnh: `_RAC` trong stt_service.py liệt kê những câu Whisper hay bịa ra trên
nền im lặng ("cảm ơn các bạn đã xem", "hãy subscribe"...). Nhưng danh sách đó
có cả "xin chào" và "cảm ơn" - là câu KHÁCH NÓI THẬT, liên tục, trong mọi cuộc
gọi. Lọc theo câu chữ đơn thuần thì không phân biệt nổi hai trường hợp.

Cách phân biệt đúng: dựa vào `avg_logprob`. Đo được (scripts/kiem_loc_stt.py):
    giọng thật sạch  -0.015      nhiễu -22 dBFS  -0.925
    giọng + nhiễu    -0.007      nhiễu -28 dBFS  -0.643
                                 nhiễu -45 dBFS  -0.242
Giọng thật cách nhiễu một quãng rất rộng, nên câu "hay bị bịa" chỉ cần đòi độ
tin cao hơn bình thường là tách được.

    python scripts/kiem_loc_cau_ngan.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from backend.services.stt_service import STTService

# (câu, avg_logprob, có nên giữ không)
# Độ tin lấy theo hai vùng đã đo: giọng thật quanh -0.02, nhiễu từ -0.24 trở xuống.
TRUONG_HOP = [
    # Khách nói thật, độ tin cao -> PHẢI giữ
    ("xin chào",              -0.02, True),
    ("Xin chào",              -0.05, True),
    ("cảm ơn",                -0.02, True),
    ("cảm ơn các bạn",        -0.03, True),
    ("hết rồi",               -0.04, True),
    ("cảm ơn nhé",            -0.02, True),
    ("alo",                   -0.03, True),
    ("vâng",                  -0.02, True),
    ("vay tín chấp",          -0.08, True),

    # Whisper bịa trên nhiễu, độ tin thấp -> PHẢI vứt
    ("cảm ơn các bạn đã xem", -0.64, False),
    ("hãy subscribe",         -0.93, False),
    ("xin chào",              -0.82, False),
    ("ghiền mì gõ",           -0.71, False),
    ("cảm ơn",                -0.45, False),

    # Câu dài bình thường, độ tin vừa -> PHẢI giữ
    ("tôi muốn vay hai trăm triệu", -0.25, True),
    ("lãi suất bao nhiêu vậy em",   -0.28, True),
]


def main():
    stt = STTService()
    hong = []
    print(f"{'câu':32} {'logprob':>8} {'mong đợi':>9} {'thực tế':>9}")
    print("-" * 64)
    for cau, tu_tin, nen_giu in TRUONG_HOP:
        ly_do = stt._dang_ngo(cau, khong_tieng=0.0, tu_tin=tu_tin)
        thuc_te_giu = not ly_do
        dat = thuc_te_giu == nen_giu
        if not dat:
            hong.append((cau, tu_tin, nen_giu, ly_do))
        print(f"{cau:32} {tu_tin:>8.2f} {'giữ' if nen_giu else 'vứt':>9} "
              f"{'giữ' if thuc_te_giu else 'vứt':>9}  {'' if dat else '<-- SAI'}")
        if not dat and ly_do:
            print(f"{'':32} lý do bị vứt: {ly_do}")

    print()
    if hong:
        print(f"[HỎNG] {len(hong)}/{len(TRUONG_HOP)} trường hợp sai:")
        for cau, tu_tin, nen_giu, ly_do in hong:
            mong = "giữ" if nen_giu else "vứt"
            print(f"   '{cau}' (logprob {tu_tin}) — mong đợi {mong}, "
                  f"nhưng {'bị vứt vì ' + ly_do if ly_do else 'được giữ'}")
        sys.exit(1)

    print(f"[ĐẠT] {len(TRUONG_HOP)}/{len(TRUONG_HOP)} trường hợp đúng")


if __name__ == "__main__":
    main()
