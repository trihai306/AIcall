"""Manh DAU cua mot luot ton bao nhieu, va ha nfe cuu duoc bao nhieu.

use_cache=False bat buoc: bo nho dem lam moi phep do ra 0ms.
"""
import asyncio, statistics, sys, time
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import backend.services.tts_service as TS
# dung nhung manh dau THAT lay tu log cuoc goi
CAU=["Anh muốn vay 500 triệu đồng đúng không ạ?",
     "Dạ lãi suất vay tín chấp bên em từ 7,9% một năm ạ.",
     "Dạ hạn mức vay lên đến 500 triệu đồng ạ.",
     "Dạ vâng em hiểu ạ."]
async def main():
    tts=TS.F5TTSService(); tts.load()
    toc=tts.toc_do_cua("giong_heu")*tts.he_so_thoai()
    # ham nong: lan dau bao gio cung dat (nap do thi, cap phat)
    await tts.synthesize("Khởi động.", voice="giong_heu", speed=toc, use_cache=False)
    print(f"{'nfe':>5}{'ms mảnh đầu (trung vị)':>26}{'từng lần':>34}")
    print("-"*66)
    for nfe in (16,12,10,8):
        ms=[]
        for c in CAU:
            t0=time.perf_counter()
            await tts.synthesize(c, voice="giong_heu", speed=toc,
                                 nfe_step=nfe, use_cache=False)
            ms.append((time.perf_counter()-t0)*1000)
        print(f"{nfe:>5}{statistics.median(ms):>22.0f}ms    "
              + " ".join(f"{v:.0f}" for v in ms))
asyncio.run(main())
