"""Am tiet CUOI MANH hong 37% - ngan sach thoi luong co cuu duoc khong?

Lan truoc do HE_SO_BU_LANG bang "tu sai ca file" nen 0.85 thang. Lan nay do
DUNG cho hong: chu cuoi cua tung manh.
"""
import asyncio, io, sys, unicodedata
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
     "Dạ em xin phép kiểm tra lại thông tin này rồi báo lại anh chị ngay ạ. Anh chị chờ em một chút nhé.",
     "Dạ, đất ở đô thị có nhà kiên cố thì thanh khoản rất tốt ạ. Vị trí nhà mình là mặt tiền hay trong hẻm ạ.",
     "Dạ lãi suất vay tín chấp bên em từ 7,9% một năm ạ. Hạn mức lên đến 500 triệu đồng ạ."]
def chu_cuoi(wav):
    segs,_=stt.transcribe(io.BytesIO(wav),language="vi",initial_prompt=MOI,
                          vad_filter=False,beam_size=5,word_timestamps=True)
    tu=[w for s in segs for w in (s.words or [])]
    return unicodedata.normalize("NFC",tu[-1].word.strip().lower().strip(".,?!")) if tu else "∅"
async def main():
    tts=TS.F5TTSService(); tts.load()
    toc=tts.toc_do_cua("giong_heu")*tts.he_so_thoai()
    manh=[m for v in VAN for m in _cat_manh_nhu_pipeline(v)]
    print(f"tổng {len(manh)} mảnh\n")
    goc=TS.HE_SO_BU_LANG
    print(f"{'hệ số':>7}{'chữ cuối mảnh đúng':>22}   mảnh hỏng")
    print("-"*76)
    for hs in (0.85,0.95,1.05,1.15):
        TS.HE_SO_BU_LANG=hs
        dung=0; hong=[]
        for m in manh:
            wav=await tts.synthesize(m,voice="giong_heu",speed=toc,use_cache=False)
            mong=unicodedata.normalize("NFC",m.rstrip(".?!,").split()[-1].lower())
            ra=chu_cuoi(wav)
            if mong==ra: dung+=1
            else: hong.append(f"{mong}→{ra}")
        print(f"{hs:>7.2f}{dung:>16}/{len(manh)}   {', '.join(hong)[:48]}")
    TS.HE_SO_BU_LANG=goc
asyncio.run(main())
