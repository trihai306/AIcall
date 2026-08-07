"""Câu hỏi quyết định: qua điện thoại thì NGƯỜI THẬT có bị méo như TTS không?

Nếu bản thu người thật cũng nghe kim loại và như người khác thì lỗi ở đường
thoại, không phải ở TTS - và không có cách sửa nào bằng phần mềm. Nếu người thật
sống sót tốt hơn hẳn thì TTS mới là chỗ cần chữa.

Dùng chính file giọng mẫu (bản thu người thật) và tiếng TTS bắt chước nó, đẩy
qua cùng một chuỗi AMR-NB, đo cùng một thước.
"""
import asyncio, sys, wave
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
P = Path(r"C:\duan\chat-ai"); sys.path.insert(0, str(P)); sys.path.insert(0, str(P/"scripts"))
import numpy as np
from do_kim_loai import do_phang_pho, do_hnr, qua_gsm, ghi, doc

def doc_file(p):
    with wave.open(str(p)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return x.astype("float32")/32768, sr

async def main():
    from backend.config import settings
    from backend.services.audio_utils import resample_audio
    from backend.services.tts_service import F5TTSService
    tts = F5TTSService(); tts.load()
    await tts.synthesize("khởi động", use_cache=False)
    out = P/"logs"/"nguoi_vs_tts"; out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.wav"): f.unlink()

    ref = P / settings.f5tts_ref_audio.lstrip("./").replace("/", "\\")
    txt = ref.with_suffix(".txt")
    cau = txt.read_text(encoding="utf-8").strip() if txt.exists() else ""
    print(f"Bản thu người thật: {ref.name}")
    print(f"Nội dung: {cau[:70]}\n")

    mau = {}
    # 1) người thật
    xn, srn = doc_file(ref)
    mau["nguoi_that"] = (xn, srn)
    # 2) TTS đọc ĐÚNG câu đó, để so cùng nội dung
    if cau:
        w = await tts.synthesize(cau, use_cache=False)
        mau["tts_cung_cau"] = doc(w)

    print(f"{'nguồn':<18}{'phẳng gốc':>12}{'sau AMR':>10}{'HNR gốc':>10}{'sau AMR':>10}")
    print("-" * 62)
    for ten, (x, sr) in mau.items():
        x8 = resample_audio(x, sr, 8000)
        y8 = qua_gsm(x8)
        (out/f"{ten}_goc.wav").write_bytes(ghi(x, sr))
        (out/f"{ten}_qua_dien_thoai.wav").write_bytes(ghi(y8, 8000))
        print(f"{ten:<18}{do_phang_pho(x,sr):>12.4f}{do_phang_pho(y8,8000):>10.4f}"
              f"{do_hnr(x,sr):>9.1f}dB{do_hnr(y8,8000):>9.1f}dB")
    print("-" * 62)
    print(f"\n{out}")

asyncio.run(main())
