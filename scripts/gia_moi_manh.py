"""Sinh mot manh ton bao nhieu thoi gian CO DINH, va bao nhieu theo do dai.

Neu phan co dinh lon thi cat cang nho cang ton tong thoi gian GPU - va do la
thu quyet dinh "tao lau" chu khong phai toc doc.

Do 3 lan moi muc, GPU ranh (Ollama khong chay).
"""
import asyncio, io, sys, time, statistics as st
sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import soundfile as sf
from backend.pipeline.text_chunker import tach_manh
from backend.pipeline import text_chunker as TC
from backend.services.tts_service import F5TTSService

DOAN = ("Dạ anh muốn vay tín chấp thì lãi suất sẽ là từ bảy phẩy chín phần trăm "
        "một năm nha anh. Hạn mức tối đa là năm trăm triệu đồng, còn giấy tờ thì "
        "anh chuẩn bị chứng minh nhân dân, sổ hộ khẩu và sao kê lương ba tháng "
        "gần nhất. Thời gian giải ngân trong vòng hai mươi bốn giờ sau khi hồ sơ "
        "được phê duyệt, anh yên tâm nhé.")
LAP = 3

def cat(van, n):
    ra, dem = [], ""
    for tu in van.split():
        dem = f"{dem} {tu}" if dem else tu
        while True:
            m, dem = tach_manh(dem, n=n)
            if m is None: break
            ra.append(m)
    if dem.strip(): ra.append(dem.strip())
    return ra

async def main():
    svc = F5TTSService(); svc.load()
    ten = svc.default_voice_name(); await svc.ensure_voice(ten)
    await svc.synthesize("hâm nóng máy", voice=ten, use_cache=False)   # bỏ lượt nguội
    print(f"\n  {'cỡ mảnh':>8} {'số mảnh':>8} {'tổng sinh':>10} {'tiếng ra':>9} "
          f"{'nhanh gấp':>10} {'mỗi mảnh':>9}")
    print("  " + "-"*62)
    for n in (5, 8, 12, 16, 24):
        manh = cat(DOAN, n)
        tong, tieng = [], 0.0
        for _ in range(LAP):
            t0 = time.perf_counter(); tieng = 0.0
            for m in manh:
                b = await svc.synthesize(m, voice=ten, use_cache=False)
                x, sr = sf.read(io.BytesIO(b), dtype="float32"); tieng += len(x)/sr
            tong.append(time.perf_counter() - t0)
        s = st.median(tong)
        print(f"  {n:>8} {len(manh):>8} {s*1000:>9.0f}ms {tieng:>8.2f}s "
              f"{tieng/s:>9.1f}x {s/len(manh)*1000:>8.0f}ms")
    print("  " + "-"*62)
asyncio.run(main())
