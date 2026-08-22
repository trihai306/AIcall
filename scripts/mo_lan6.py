"""Mo tieng that cua Lan 6: quang lang o dau, chu nao mat, duoi cau co gi."""
import io, re, sys, unicodedata, wave
from pathlib import Path
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.api.voices import _cat_manh_nhu_pipeline
from backend.pipeline.text_chunker import nhip_nghi_sau
from backend.pipeline.text_normalizer import normalize_for_tts
from whisper_server.pho_server import _pick_device
from faster_whisper import WhisperModel
D=Path(r"C:\Users\Admin\Desktop\Check giọng\Lan 6")
VAN={
 "4/5":( "5/1 Thiếu chữ 'ngõ'.wav",
   "Dạ, đất ở đô thị có nhà kiên cố như vậy thì thanh khoản rất tốt. Vị trí nhà mình là mặt tiền đường lớn hay trong hẻm ạ. Ngõ trước nhà rộng khoảng bao nhiêu mét, xe hơi có vào tận nơi được không anh"),
 "6":( "6/1 Sau chữ 'vâng' không ngắt nghỉ dấu phẩy, sau dấu chấm chỗ 'thẩm định' gần như ko ngắt nghỉ.wav",
   "Vâng, ngõ ô tô vào được là điểm cộng lớn khi định giá tài sản ạ. Thông thường ngân hàng sẽ cho vay tối đa khoảng 70% đến 75% giá trị tài sản mà ngân hàng thẩm định. Với căn nhà 80 mét vuông kèm nhà 3 tầng ở khu vực đó, nếu định giá sơ bộ tầm"),
 "7":( "7/1 Cuối câu cảm giác gãy chữ, nghe tiếng 'hợp'.wav",
   "Bước tiếp theo là phần nguồn thu để trả nợ. Hiện tại thu nhập chính của hai vợ chồng đến từ những nguồn nào vậy anh"),
 "3":( "3/1 'nhé' và 'ạ' cuối câu nghe bị 'hợp'.wav",
   "Để em tư vấn chính xác về hạn mức 1,5 tỷ này, em xin phép hỏi một chút về thông tin tài sản anh dự định thế chấp nhé. Sổ đỏ này hiện tại đứng tên một mình anh hay cả hai vợ chồng ạ"),
}
def rms(x): return float(np.sqrt(np.mean(x**2))) if len(x) else 0.0
def lang(x,sr,toi_thieu=60):
    o=int(sr*0.020); n=len(x)//o
    e=np.array([rms(x[i*o:(i+1)*o]) for i in range(n)])
    ng=0.20*float(np.percentile(e,95)); im=e<ng; ra=[];i=0
    while i<n:
        if im[i]:
            j=i
            while j<n and im[j]: j+=1
            if (j-i)*20>=toi_thieu: ra.append((i*20/1000,(j-i)*20))
            i=j
        else: i+=1
    return ra
dev,ct=_pick_device(); stt=WhisperModel(r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-medium-ct2",
                                        device=dev,compute_type=ct)
for ten,(f,van) in VAN.items():
    p=D/f
    if not p.exists(): print(f"\n### {ten}: KHÔNG thấy {f}"); continue
    with wave.open(str(p)) as w:
        sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
    manh=_cat_manh_nhu_pipeline(van)
    print(f"\n{'='*76}\n### THƯ MỤC {ten}   {len(x)/sr:.2f}s")
    print("   mảnh + nhịp nghỉ code CHÈN sau mỗi mảnh:")
    for m in manh: print(f"      {len(m.split()):>2} từ · nghỉ {nhip_nghi_sau(m):>3.0f}ms | {m[:64]}")
    q=lang(x,sr)
    print(f"   quãng lặng ĐO ĐƯỢC: {', '.join(f'{a:.2f}s({b:.0f}ms)' for a,b in q) or 'KHÔNG CÓ'}")
    segs,_=stt.transcribe(str(p),language="vi",word_timestamps=True,vad_filter=False,beam_size=5)
    tu=[w for s in segs for w in (s.words or []) if w.end>w.start]
    nghe=" ".join(w.word.strip() for w in tu)
    print(f"   máy nghe: {nghe[:150]}")
    mong=set(normalize_for_tts(van).replace(","," ").replace("."," ").lower().split())
    co=set(unicodedata.normalize("NFC",nghe).lower().replace(","," ").replace("."," ").split())
    mat=[w for w in ("ngõ","nhé","ạ","vâng","dạ") if w in mong and w not in co]
    if mat: print(f"   CHỮ MẤT: {mat}")
    if tu:
        c=tu[-1]; a=int(c.start*sr)
        print(f"   chữ cuối máy nghe: {c.word.strip()!r} ({c.start:.2f}-{c.end:.2f}s)  "
              f"RMS {rms(x[a:int(c.end*sr)]):.4f}")
        o=int(sr*0.005)
        d=[rms(x[len(x)-(i+1)*o:len(x)-i*o]) for i in range(50)][::-1]
        mx=max(d) or 1
        print("   250ms cuối: " + "".join("█" if v>.5*mx else "▓" if v>.25*mx else "░" if v>.08*mx else "·" for v in d))
