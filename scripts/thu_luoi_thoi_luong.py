"""Lam tron fix_duration ve luoi thi gom duoc bao nhieu hinh dang, va tra gia gi?

Gia thuyet: gom hinh dang -> it lan bien dich lai -> nhanh hon. Gia phai tra la
thoi luong lech toi da nua o luoi.
"""
import asyncio, io, json, sys, time, urllib.request, statistics as st
sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import soundfile as sf
from backend.config import settings
from backend.services import tts_service as T

# doan Ollama co that su tra loi khong (kiem lai cho chac)
try:
    d = json.dumps({"model": settings.ollama_model, "prompt": "đếm từ 1 đến 5",
                    "stream": False}).encode()
    r = urllib.request.Request(f"{settings.ollama_host}/api/generate", data=d,
                               headers={"Content-Type": "application/json"})
    t0 = time.perf_counter(); g = json.loads(urllib.request.urlopen(r, timeout=120).read())
    print(f"  Ollama: OK, {(time.perf_counter()-t0)*1000:.0f}ms, "
          f"{len(g.get('response',''))} ky tu -> phep do tranh GPU la HOP LE")
except Exception as e:
    print(f"  Ollama: LOI {str(e)[:70]} -> phep do tranh GPU KHONG hop le")

CAU = ["dạ vâng ạ", "anh cần chuẩn bị chứng minh", "em xin phép báo lại",
       "anh chị vui lòng cung cấp thêm thông tin", "vâng thưa anh",
       "thời gian giải ngân trong vòng hai mươi bốn giờ", "được ạ em ghi nhận",
       "hạn mức tối đa là năm trăm triệu đồng", "em cảm ơn anh nhiều",
       "hồ sơ của anh đã đủ điều kiện", "anh yên tâm nhé", "sao kê lương ba tháng"]

async def main():
    svc = T.F5TTSService(); svc.load()
    ten = svc.default_voice_name(); await svc.ensure_voice(ten)
    rw, rs, _ = svc._voices[ten]; dai_ref = rw.shape[-1]/rs
    sp = svc.toc_do_cua(ten)
    from backend.pipeline.text_normalizer import normalize_for_tts
    goc = [T.thoi_luong_ep(normalize_for_tts(c), dai_ref, sp) for c in CAU]
    print(f"\n  {len(CAU)} cau -> {len(set(round(g,4) for g in goc))} hinh dang khac nhau (khong luoi)")
    for buoc in (0.05, 0.10, 0.20):
        n = len(set(round(g/buoc) for g in goc))
        print(f"    luoi {buoc*1000:>3.0f}ms -> {n} hinh dang, lech toi da {buoc/2*1000:.0f}ms")

    await svc.synthesize("hâm nóng máy", voice=ten, use_cache=False)
    async def do(luoi):
        cu = T.LUOI_THOI_LUONG if hasattr(T, "LUOI_THOI_LUONG") else None
        t, dai = [], 0.0
        for c in CAU:
            if luoi:
                T._LUOI = luoi
            t0 = time.perf_counter()
            b = await svc.synthesize(c, voice=ten, use_cache=False)
            t.append((time.perf_counter()-t0)*1000)
            x, sr = sf.read(io.BytesIO(b), dtype="float32"); dai += len(x)/sr
        return t, dai
    t1, d1 = await do(None)
    t2, d2 = await do(None)          # lan hai: hinh dang da co san het
    print(f"\n  {'':<28} {'trung vi':>10} {'tong':>9} {'so manh > 450ms':>17}")
    print("  " + "-"*68)
    print(f"  {'lan 1 (hinh dang moi)':<28} {st.median(t1):>9.0f}ms {sum(t1):>8.0f}ms"
          f" {sum(1 for x in t1 if x > 450):>16}")
    print(f"  {'lan 2 (da co hinh dang)':<28} {st.median(t2):>9.0f}ms {sum(t2):>8.0f}ms"
          f" {sum(1 for x in t2 if x > 450):>16}")
    print("  " + "-"*68)
    print(f"\n  -> tiet kiem duoc {sum(t1)-sum(t2):.0f}ms tren {len(CAU)} manh"
          f" ({(1-sum(t2)/sum(t1))*100:.0f}%) neu khong phai bien dich lai")
asyncio.run(main())
