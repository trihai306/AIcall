import asyncio, io, sys
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
from pathlib import Path
from backend.pipeline import text_chunker as TC
from backend.services.audio_utils import chen_lang_dau_wav
from backend.services.tts_service import F5TTSService
VAN=("Dạ vâng ạ, với tình hình thu nhập của anh chị thì em có thể tư vấn hạn mức lên đến "
     "năm trăm triệu đồng, thời hạn vay linh hoạt từ mười hai đến sáu mươi tháng, và lãi "
     "suất áp dụng từ bảy phẩy chín phần trăm một năm tính trên dư nợ giảm dần ạ. Anh chị "
     "chuẩn bị giúp em chứng minh nhân dân, sổ hộ khẩu và sao kê lương ba tháng gần nhất, "
     "thì bên em xử lý rất nhanh ạ. Sau khi anh chị nộp đủ hồ sơ thì bên em thẩm định trong "
     "vòng một ngày làm việc, phê duyệt xong là giải ngân ngay trong hai mươi bốn giờ, tiền "
     "chuyển thẳng vào tài khoản anh chị đăng ký chứ không phải ra quầy nhận ạ. Anh chị cho "
     "em xin ít phút để em tư vấn kỹ hơn được không ạ.")
RA=Path(r"C:/tmp/thudai"); RA.mkdir(parents=True,exist_ok=True)
svc=F5TTSService(); svc.load()
ten=svc.default_voice_name(); asyncio.run(svc.ensure_voice(ten))
NG,KH=0.015,0.02
def lang(y,sr,tt=250):
    n=max(1,int(sr*KH)); k=len(y)//n
    im=np.abs(y[:k*n].reshape(k,n)).max(axis=1)<NG
    ra=[]; i=0
    while i<k:
        if im[i]:
            j=i
            while j<k and im[j]: j+=1
            if i>0 and j<k and (j-i)*20>=tt: ra.append((j-i)*20)
            i=j
        else: i+=1
    return ra
print(f"\n  {'cat':>7} {'manh':>5} {'moi noi':>8} {'lang bia':>9} {'tong dai':>9}")
print("  "+"-"*46)
for n_tu in (5, 10, 16):
    cu=TC.GIOI_HAN_TU_MANH; TC.GIOI_HAN_TU_MANH=n_tu
    ra,dem=[],""
    for t in VAN.split():
        dem+=" "+t
        m,dem=TC.tach_manh(dem, n_tu, first_chunk=(not ra))
        if m: ra.append(m)
    if dem.strip(): ra.append(dem.strip())
    TC.GIOI_HAN_TU_MANH=cu
    ws, nghi, bia = [], 0.0, 0
    for c in ra:
        b=asyncio.run(svc.synthesize(c, voice=ten))
        if nghi>0: b=chen_lang_dau_wav(b, nghi)
        nghi=TC.nhip_nghi_sau(c)
        y,sr=sf.read(io.BytesIO(b),dtype="float32")
        if y.ndim>1: y=y.mean(axis=1)
        bia+=len(lang(y,sr)); ws.append(y)
    z=np.concatenate(ws); d=float(np.abs(z).max())
    if d>1.0: z/=d
    p=RA/f"cat_{n_tu}_tu.wav"; sf.write(p,z,sr)
    print(f"  {n_tu:>5} tu {len(ra):>5} {len(ra)-1:>8} {bia:>9} {len(z)/sr:>8.2f}s")
print("  "+"-"*46)
