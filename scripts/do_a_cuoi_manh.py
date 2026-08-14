"""Chu "a" o cuoi TUNG MANH co bi chap duoi am khong?

Moi manh la mot lan goi F5 rieng, nen "cuoi phat ngon" lap lai 3-5 lan moi luot
chu khong phai mot lan moi file.
"""
import asyncio, io, sys, unicodedata, wave
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import backend.services.tts_service as TS
from backend.api.voices import _cat_manh_nhu_pipeline
from whisper_server.pho_server import _pick_device
from faster_whisper import WhisperModel
from backend.services.stt_service import moi_tu_vung
dev,ct=_pick_device()
stt=WhisperModel(r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-medium-ct2",device=dev,compute_type=ct)
MOI=moi_tu_vung("nam")
VAN=["Vâng, ngõ ô tô vào được là điểm cộng lớn khi định giá tài sản ạ. Thông thường ngân hàng sẽ cho vay tối đa khoảng 70% đến 75% giá trị tài sản mà ngân hàng thẩm định.",
     "Dạ hạn mức vay lên đến 500 triệu đồng ạ. Thời gian vay tối đa sáu mươi tháng ạ. Anh chị cần thêm thông tin gì không ạ?",
     "Dạ em xin phép kiểm tra lại thông tin này rồi báo lại anh chị ngay ạ. Anh chị chờ em một chút nhé."]
def chu_cuoi(wav):
    segs,_=stt.transcribe(io.BytesIO(wav),language="vi",initial_prompt=MOI,
                          vad_filter=False,beam_size=5,word_timestamps=True)
    tu=[w for s in segs for w in (s.words or [])]
    return unicodedata.normalize("NFC",tu[-1].word.strip().lower().strip(".,?!")) if tu else "∅"
async def main():
    tts=TS.F5TTSService(); tts.load()
    toc=tts.toc_do_cua("giong_heu")*tts.he_so_thoai()
    tong=dung=0
    print(f"{'mảnh':<62}{'mong':>8}{'nghe':>10}")
    print("-"*82)
    for van in VAN:
        for m in _cat_manh_nhu_pipeline(van):
            wav=await tts.synthesize(m,voice="giong_heu",speed=toc,use_cache=False)
            mong=unicodedata.normalize("NFC",m.rstrip(".?!,").split()[-1].lower())
            nghe=chu_cuoi(wav)
            ok = mong==nghe; tong+=1; dung+=ok
            print(f"{m[:60]:<62}{mong:>8}{nghe:>10}" + ("" if ok else "   ✗"))
    print("-"*82)
    print(f"chữ cuối MẢNH đúng: {dung}/{tong}")
asyncio.run(main())
