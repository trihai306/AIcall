"""Ha nfe manh dau co lam doc sai chu khong? Cho may nghe lai."""
import asyncio, difflib, io, re, sys, unicodedata, wave
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import backend.services.tts_service as TS
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services.stt_service import moi_tu_vung
from whisper_server.pho_server import _pick_device
from faster_whisper import WhisperModel
CAU=["Anh muốn vay 500 triệu đồng đúng không ạ?",
     "Dạ lãi suất vay tín chấp bên em từ 7,9% một năm ạ.",
     "Dạ hạn mức vay lên đến 500 triệu đồng ạ.",
     "Dạ vâng em hiểu ạ.",
     "Dạ thời gian vay tối đa là sáu mươi tháng ạ.",
     "Dạ anh chị chuẩn bị căn cước công dân và sao kê lương ạ."]
dev,ct=_pick_device(); stt=WhisperModel(r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-medium-ct2",
                                        device=dev,compute_type=ct)
MOI=moi_tu_vung("nam")
VT={"vê bê banh":"vpbank","tê pê banh":"tpbank","em bê banh":"mbbank"}
def chuan(s):
    s=" ".join(re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split())
    for a,b in VT.items(): s=s.replace(a,b)
    return s
def sai(a,b):
    A,B=chuan(a).split(),chuan(b).split()
    sm=difflib.SequenceMatcher(None,A,B,autojunk=False); m=t=0
    for op,i1,i2,j1,j2 in sm.get_opcodes():
        if op in ("delete","replace"): m+=i2-i1
        if op in ("insert","replace"): t+=j2-j1
    return (m+t)/(2*max(1,len(A)))
async def main():
    tts=TS.F5TTSService(); tts.load()
    toc=tts.toc_do_cua("giong_heu")*tts.he_so_thoai()
    print(f"{'nfe':>5}{'câu đạt':>10}{'từ sai TB':>12}   chữ lệch")
    print("-"*64)
    for nfe in (16,12,10):
        e=[];lech=[]
        for c in CAU:
            wav=await tts.synthesize(c,voice="giong_heu",speed=toc,
                                     nfe_step=nfe,use_cache=False)
            segs,_=stt.transcribe(io.BytesIO(wav),language="vi",
                                  initial_prompt=MOI,vad_filter=False,beam_size=5)
            ra=" ".join(s.text for s in segs).strip()
            x=sai(normalize_for_tts(c),ra); e.append(x)
            if x>0.05: lech.append(ra[:30])
        print(f"{nfe:>5}{sum(v<=0.05 for v in e):>7}/{len(e)}{sum(e)/len(e)*100:11.1f}%   "
              + (", ".join(lech)[:38] or "—"))
asyncio.run(main())
