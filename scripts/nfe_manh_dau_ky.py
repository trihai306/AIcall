"""Ha nfe manh dau co lam hong chu "Da" khong - do dung cho chu thich neu.

Chu thich trong config.py: "O nfe thap chu 'Da' bi doc thanh 'Gia'/'Sac' - hong
dung tu khach nghe dau tien". Do 16 cau mo dau THAT, do rieng CHU DAU.
"""
import asyncio, difflib, io, re, statistics, sys, time, unicodedata
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import backend.services.tts_service as TS
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services.stt_service import moi_tu_vung
from whisper_server.pho_server import _pick_device
from faster_whisper import WhisperModel
CAU=["Dạ em chào anh chị ạ.",
     "Dạ lãi suất vay tín chấp bên em từ 7,9% một năm ạ.",
     "Dạ hạn mức vay lên đến 500 triệu đồng ạ.",
     "Dạ vâng em hiểu ạ.",
     "Dạ thời gian vay tối đa là sáu mươi tháng ạ.",
     "Dạ anh chị chuẩn bị căn cước công dân và sao kê lương ạ.",
     "Dạ bên em hỗ trợ vay mua nhà ạ.",
     "Dạ em xin phép kiểm tra lại ạ.",
     "Dạ phí trả nợ trước hạn là 2% ạ.",
     "Dạ hồ sơ duyệt trong hai ngày làm việc ạ.",
     "Dạ anh cho em xin thông tin liên hệ ạ.",
     "Dạ em sẽ gửi tin nhắn xác nhận ngay ạ.",
     "Anh muốn vay 500 triệu đồng đúng không ạ?",
     "Vâng, em ghi nhận thông tin của anh ạ.",
     "Dạ chương trình này áp dụng tới cuối tháng ạ.",
     "Dạ em cảm ơn anh chị nhiều ạ."]
dev,ct=_pick_device(); stt=WhisperModel(r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-medium-ct2",
                                        device=dev,compute_type=ct)
MOI=moi_tu_vung("nam")
def tu(s): return [t for t in re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split() if t]
def sai(a,b):
    A,B=tu(a),tu(b); sm=difflib.SequenceMatcher(None,A,B,autojunk=False); m=t=0
    for op,i1,i2,j1,j2 in sm.get_opcodes():
        if op in ("delete","replace"): m+=i2-i1
        if op in ("insert","replace"): t+=j2-j1
    return (m+t)/(2*max(1,len(A)))
async def main():
    tts=TS.F5TTSService(); tts.load()
    toc=tts.toc_do_cua("giong_heu")*tts.he_so_thoai()
    await tts.synthesize("Khởi động.",voice="giong_heu",speed=toc,use_cache=False)
    print(f"{'nfe':>5}{'chữ ĐẦU đúng':>15}{'từ sai TB':>12}{'ms trung vị':>13}   chữ đầu nghe sai")
    print("-"*84)
    for nfe in (16,12):
        dung=0;e=[];ms=[];sai_dau=[]
        for c in CAU:
            t0=time.perf_counter()
            wav=await tts.synthesize(c,voice="giong_heu",speed=toc,nfe_step=nfe,use_cache=False)
            ms.append((time.perf_counter()-t0)*1000)
            segs,_=stt.transcribe(io.BytesIO(wav),language="vi",
                                  initial_prompt=MOI,vad_filter=False,beam_size=5)
            ra=" ".join(s.text for s in segs).strip()
            mong=tu(normalize_for_tts(c)); nghe=tu(ra)
            ok = bool(mong) and bool(nghe) and mong[0]==nghe[0]
            dung+=ok
            if not ok and nghe: sai_dau.append(f"{mong[0]}→{nghe[0]}")
            e.append(sai(normalize_for_tts(c),ra))
        print(f"{nfe:>5}{dung:>12}/{len(CAU)}{sum(e)/len(e)*100:11.1f}%"
              f"{statistics.median(ms):12.0f}ms   {', '.join(sai_dau)[:40]}")
asyncio.run(main())
