"""'Doc bi nhanh' = vai chu bi nen con 1/3 thoi luong. Ngan sach co chua duoc khong?

Do: nhip TUNG CHU (60/thoi luong chu). Dem so chu vuot 600 am tiet/phut - do la
muc nguoi dung nghe ra "luot qua".
"""
import asyncio, io, statistics, sys
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import backend.services.tts_service as TS
from backend.api.voices import _cat_manh_nhu_pipeline, _ghep_nhu_pipeline
from whisper_server.pho_server import _pick_device
from faster_whisper import WhisperModel
from backend.services.stt_service import moi_tu_vung
dev,ct=_pick_device()
stt=WhisperModel(r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-medium-ct2",device=dev,compute_type=ct)
MOI=moi_tu_vung("nam")
CAU=["Vâng anh yên tâm, sổ anh đang giữ, không có tranh chấp là được, bên em tiếp nhận, em sẽ kiểm tra thêm quy hoạch miễn phí cho anh trước để đảm bảo tài sản ạ.",
     "Dạ bên em cần hóa đơn nhập hàng và sổ sách bán hàng, còn nguồn thu từ cửa hàng thì anh cho em xin sao kê ba tháng gần nhất ạ.",
     "Dạ thu nhập khoảng 50 triệu thì thoải mái trả nợ rồi ạ. Chị nhà có lương thì cho sao kê là được anh ạ.",
     "Dạ hiện tại bên em đang có chương trình ưu đãi dành riêng cho khách hàng có thu nhập ổn định từ 15 triệu đồng trở lên ạ."]
async def main():
    tts=TS.F5TTSService(); tts.load()
    toc=tts.toc_do_cua("giong_heu")*tts.he_so_thoai()
    goc=TS.HE_SO_BU_LANG
    print(f"{'hệ số':>7}{'chữ >600':>10}{'chữ >800':>10}{'nhanh nhất':>12}{'nhịp TB':>10}{'giây':>8}")
    print("-"*60)
    for hs in (0.85,0.95,1.05):
        TS.HE_SO_BU_LANG=hs
        nhip=[]; giay=0.0
        for c in CAU:
            manh=_cat_manh_nhu_pipeline(c)
            wav=await _ghep_nhu_pipeline(tts,manh,"giong_heu",toc,False)
            segs,_=stt.transcribe(io.BytesIO(wav),language="vi",initial_prompt=MOI,
                                  vad_filter=False,beam_size=5,word_timestamps=True)
            tu=[w for s in segs for w in (s.words or []) if w.end>w.start]
            nhip += [60.0/(w.end-w.start) for w in tu]
            giay += len(wav)/2/24000
        n6=sum(1 for v in nhip if v>600); n8=sum(1 for v in nhip if v>800)
        print(f"{hs:>7.2f}{n6:>7}/{len(nhip)}{n8:>7}/{len(nhip)}{max(nhip):12.0f}"
              f"{statistics.median(nhip):10.0f}{giay:8.1f}")
    TS.HE_SO_BU_LANG=goc
asyncio.run(main())
