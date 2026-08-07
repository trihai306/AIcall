"""Đo nhịp nghỉ mà F5-TTS TỰ SINH ở dấu phẩy và dấu chấm.

Vì sao phải đo: pipeline cắt câu thành mảnh, mỗi mảnh bị trim_silence cắt sạch
lặng hai đầu, nên khoảng nghỉ ở ranh giới mệnh đề biến mất - đo được bản cắt mảnh
ngắn hơn bản sinh một lần 1,63s trên 43 từ. Muốn chèn lại thì phải biết chèn BAO
NHIÊU. Con số đó lấy từ chính model chứ không bịa: sinh cả câu một lần rồi đo
khoảng lặng bên trong.

Cách tách bạch: câu chỉ có MỘT dấu phẩy -> khoảng lặng trong dài nhất chính là
nghỉ ở dấu phẩy. Đoạn hai câu ngắn -> khoảng lặng trong chính là nghỉ ở dấu chấm.

    python scripts/do_nhip_nghi.py
"""
import asyncio, io, pathlib, statistics, sys
import numpy as np
import soundfile as sf

GOC = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

CAU_PHAY = [
    "Dạ lãi suất hiện tại là sáu phẩy năm phần trăm, anh nhé.",
    "Em đã kiểm tra hồ sơ của mình rồi, tất cả đều hợp lệ ạ.",
    "Nếu anh vay năm trăm triệu, thời gian trả góp tối đa là ba mươi sáu tháng.",
    "Anh chuẩn bị giúp em căn cước công dân, cùng sao kê lương ba tháng gần nhất.",
    "Dạ khoản vay này không cần tài sản đảm bảo, anh yên tâm ạ.",
]

CAU_CHAM = [
    "Dạ em chào anh. Em gọi từ ngân hàng ạ.",
    "Hồ sơ của mình đã duyệt. Anh nhận tiền trong hôm nay nhé.",
    "Em hiểu rồi ạ. Để em kiểm tra lại giúp anh.",
    "Lãi suất cố định trong năm đầu. Sau đó thả nổi theo thị trường.",
    "Cảm ơn anh đã dành thời gian. Chúc anh một ngày tốt lành.",
]


def khoang_lang(x: np.ndarray, sr: int, nguong=0.005, toi_thieu_ms=60):
    """Các quãng lặng BÊN TRONG tín hiệu, trả về độ dài tính bằng ms.

    Dùng đúng ngưỡng 0.005 của trim_silence để đo cùng thước với thứ đang cắt.
    """
    im = np.abs(x) <= nguong
    ra, dau = [], None
    for i, v in enumerate(im):
        if v and dau is None:
            dau = i
        elif not v and dau is not None:
            ra.append((dau, i))
            dau = None
    # bỏ quãng chạm hai biên: đó là lặng đầu/cuối, không phải nhịp nghỉ trong câu
    ra = [(a, b) for a, b in ra if a > 0 and b < len(x)]
    return [ (b - a) * 1000 / sr for a, b in ra if (b - a) * 1000 / sr >= toi_thieu_ms ]


async def main():
    from backend.services.tts_service import F5TTSService
    tts = F5TTSService(); tts.load()

    async def sinh(t):
        w = await tts.synthesize(t, use_cache=False)
        x, sr = sf.read(io.BytesIO(w), dtype="float32")
        return (x.mean(axis=1) if x.ndim > 1 else x), sr

    for ten, bo in [("DẤU PHẨY", CAU_PHAY), ("DẤU CHẤM", CAU_CHAM)]:
        print(f"\n=== {ten} ===")
        dai_nhat = []
        for c in bo:
            x, sr = await sinh(c)
            q = khoang_lang(x, sr)
            n = max(q) if q else 0.0
            dai_nhat.append(n)
            print(f"  {n:6.0f} ms   (tổng {len(q)} quãng ≥60ms)   {c[:52]}")
        co = [v for v in dai_nhat if v > 0]
        if co:
            print(f"  --> trung vị {statistics.median(co):.0f} ms"
                  f" | nhỏ nhất {min(co):.0f} | lớn nhất {max(co):.0f}"
                  f" | {len(co)}/{len(bo)} câu có nghỉ")
        else:
            print("  --> không câu nào có quãng lặng trong ≥60ms")


if __name__ == "__main__":
    asyncio.run(main())
