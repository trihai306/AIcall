"""Nhom manh 700-1141ms la do BIEN DICH LAI khi gap do dai moi?

torch.compile luu do thi theo HINH DANG tensor. fix_duration cho ra do dai khac
nhau tung manh, gap hinh dang moi la phai bien dich lai - dung mot lan, cham gap
3-4 lan, roi cac lan sau nhanh tro lai. Dung dang lo trong log.

Phep thu: sinh MOT cau lap lai nhieu lan (mot hinh dang) roi sinh nhieu cau DAI
KHAC NHAU (nhieu hinh dang). Neu gia thuyet dung thi cot hai co nhieu dinh nhon.
"""
import asyncio, json, sys, time, threading, urllib.request, statistics as st
sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.config import settings
from backend.services.tts_service import F5TTSService

print(f"  F5TTS_COMPILE = {getattr(settings, 'f5tts_compile', '(khong co truong nay)')}")

# doan Ollama co that su chay khong
def thu_ollama():
    try:
        d = json.dumps({"model": settings.ollama_model, "prompt": "đếm từ 1 đến 5",
                        "stream": False}).encode()
        r = urllib.request.Request(f"{settings.ollama_host}/api/generate", data=d,
                                   headers={"Content-Type": "application/json"})
        t0 = time.perf_counter()
        g = json.loads(urllib.request.urlopen(r, timeout=120).read())
        return (time.perf_counter()-t0)*1000, len(g.get("response", ""))
    except Exception as e:
        return None, str(e)[:60]

ms, n = thu_ollama()
print(f"  Ollama thu goi : {f'{ms:.0f}ms, {n} ky tu' if ms else f'LOI - {n}'}")

async def main():
    svc = F5TTSService(); svc.load()
    ten = svc.default_voice_name(); await svc.ensure_voice(ten)
    await svc.synthesize("hâm nóng máy cho nóng", voice=ten, use_cache=False)

    MOT = "anh cần chuẩn bị chứng minh nhân dân"          # cùng độ dài mọi lần
    NHIEU = ["dạ vâng ạ", "anh cần chuẩn bị chứng minh", "em xin phép",
             "anh chị vui lòng cung cấp thêm thông tin chi tiết", "vâng",
             "thời gian giải ngân trong vòng hai mươi bốn giờ làm việc kể từ",
             "được ạ", "hạn mức tối đa là năm trăm triệu", "em cảm ơn anh nhiều"]
    async def do(ds):
        t = []
        for c in ds:
            t0 = time.perf_counter()
            await svc.synthesize(c, voice=ten, use_cache=False)
            t.append((time.perf_counter()-t0)*1000)
        return t
    a = await do([MOT]*9)
    b = await do(NHIEU)
    print(f"\n  {'lần':>4} {'cùng độ dài':>13} {'độ dài khác nhau':>18}")
    print("  " + "-"*40)
    for i, (x, y) in enumerate(zip(a, b), 1):
        print(f"  {i:>4} {x:>12.0f}ms {y:>17.0f}ms")
    print("  " + "-"*40)
    print(f"  {'trung vi':>4} {st.median(a):>12.0f}ms {st.median(b):>17.0f}ms")
    print(f"  {'to nhất':>4} {max(a):>12.0f}ms {max(b):>17.0f}ms")
    print(f"\n  chênh to/trung vị: cùng độ dài {max(a)/st.median(a):.1f}x"
          f" | khác nhau {max(b)/st.median(b):.1f}x")
asyncio.run(main())
