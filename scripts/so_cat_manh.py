"""Ba duong sinh tieng co cat manh GIONG NHAU khong?

  1. Cuoc goi that + Hoi thoai (chat)  -> streaming_pipeline: tach_manh + co_manh
  2. Trang Test giong / nut nghe thu    -> voices.py: _cat_manh_nhu_pipeline

Chay TREN MAY WIN (day moi la code that dang chay):
    set PYTHONIOENCODING=utf-8 && .venv\\python.exe scripts\\so_cat_manh.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from backend.pipeline.text_chunker import co_manh, tach_manh

CAU = [
    "Dạ chào anh Minh ạ, em là Lan, nhân viên tư vấn của Ngân hàng Quân đội. "
    "Anh có cần hỗ trợ gì không?",
    "Dạ lãi suất vay tín chấp của bên em là từ bảy phẩy chín phần trăm một năm, "
    "hạn mức lên đến năm trăm triệu đồng ạ.",
    "Được ạ, anh cần vay bao nhiêu và trong thời hạn bao lâu để em tư vấn cụ thể hơn?",
    "Dạ vâng em hiểu ạ.",
    "Anh cứ yên tâm nhé, hồ sơ chỉ cần chứng minh nhân dân và sao kê lương ba tháng "
    "gần nhất, giải ngân trong hai tư giờ ạ.",
]


def cat_nhu_pipeline(text: str) -> list[str]:
    """Y HET vong lap trong streaming_pipeline.tts_consumer."""
    ra, buf, i = [], text, 0
    while buf.strip() and i < 40:
        manh, buf = tach_manh(buf, n=co_manh(i), first_chunk=(i == 0))
        if not manh:
            break
        ra.append(manh)
        i += 1
    if buf.strip():          # xa phan du cuoi luot
        ra.append(buf.strip())
    return ra


def cat_nhu_test_giong(text: str) -> list[str]:
    """Ham that ma /api/voices/test-tts dung."""
    from backend.api.voices import _cat_manh_nhu_pipeline
    return _cat_manh_nhu_pipeline(text)


def main():
    khop = 0
    for i, c in enumerate(CAU, 1):
        a = cat_nhu_pipeline(c)
        b = cat_nhu_test_giong(c)
        giong = (a == b)
        khop += giong
        print(f"--- Cau {i} --- {'KHOP' if giong else 'LECH !!!'}")
        if giong:
            for m in a:
                print(f"      | {m}")
        else:
            print(f"   pipeline ({len(a)} manh):")
            for m in a:
                print(f"      | {m}")
            print(f"   test giong ({len(b)} manh):")
            for m in b:
                print(f"      | {m}")
        print()
    print(f"===> {khop}/{len(CAU)} cau cat GIONG NHAU")


if __name__ == "__main__":
    main()
