"""Cap cang nhieu gio thi F5 cang chen nghi? Phep thu lieu-luong.

Neu im lang tang theo thoi luong duoc cap -> F5 chen nghi de TIEU thoi gian
thua, va chi can sua he so la xong, khong phai dong dao vao am thanh.
Neu im lang khong doi -> do la ban tinh cua F5, phai cat o dau ra.

Moi muc sinh 3 lan vi F5 dao dong +-6%.
"""
import sys, statistics as st
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, torch, asyncio
from backend.config import settings
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services import tts_service as T
from f5_tts.infer.utils_infer import infer_batch_process

CAU = [
 "Anh chị cần đáp ứng các điều kiện như công dân Việt Nam từ 22 đến 60 tuổi",
 "Anh muốn vay tín chấp thì lãi suất sẽ là từ 7.9%/năm nha anh",
 "Hộ khẩu hoặc KT3, sao kê lương 3 tháng gần nhất và hợp đồng lao động",
]
LAP = 3
svc = T.F5TTSService(); svc.load()
ten = svc.default_voice_name(); asyncio.run(svc.ensure_voice(ten))
rw, rs, rt = svc._voices[ten]; sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step
dai_ref = rw.shape[-1] / rs

def sinh(chu, fix):
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
        y, sr, _ = next(infer_batch_process((rw, rs), rt, [T.bo_dau_cau_cho_f5(chu)],
            svc._model, svc._vocoder, mel_spec_type="vocos", progress=None,
            nfe_step=nfe, speed=sp, fix_duration=fix, device=svc._model.device))
    return T.trim_silence(np.asarray(y), sr), sr

def im_giua(y, sr, toi_thieu_ms=120):
    """Tong im lang GIUA tieng, do bang RMS tuong doi - dung phep tai nghe thay."""
    h = max(1, int(sr * 0.01)); k = len(y) // h
    e = np.convolve(np.array([float(np.sqrt((y[i*h:(i+1)*h]**2).mean()))
                              for i in range(k)]), np.ones(3)/3, mode="same")
    ng = max(e.max() * 0.06, 3e-4)
    co = np.nonzero(e > ng)[0]
    if len(co) < 5: return 0.0, 0
    d0, d1 = int(co[0]), int(co[-1]); tong = 0; dem = 0; i = d0
    while i < d1:
        if e[i] <= ng:
            j = i
            while j < d1 and e[j] <= ng: j += 1
            if (j-i)*10 >= toi_thieu_ms: tong += (j-i)*10; dem += 1
            i = j
        else: i += 1
    return tong, dem

print(f"\n  {LAP} lan/muc, {len(CAU)} cau\n")
print(f"  {'he so':>8} {'cap':>7} {'ra':>7} {'im giua':>8} {'so quang':>9} {'% im':>6}")
print("  " + "-" * 52)
for he in (0.85, 0.95, 1.064, 1.11, 1.25, None):
    ra, im, sq, cp = [], [], [], []
    for chu in CAU:
        n = normalize_for_tts(chu)
        cu = T.HE_SO_BU_LANG
        if he is not None: T.HE_SO_BU_LANG = he
        fix = T.thoi_luong_ep(n, dai_ref, sp) if he is not None else None
        T.HE_SO_BU_LANG = cu
        for _ in range(LAP):
            y, sr = sinh(n, fix); t, d = im_giua(y, sr)
            ra.append(len(y)/sr); im.append(t/1000); sq.append(d)
            cp.append((fix - dai_ref) if fix else float("nan"))
    nhan = f"{he:.3f}" if he is not None else "khong ep"
    c = "  -  " if he is None else f"{st.mean(cp):>5.2f}s"
    print(f"  {nhan:>8} {c:>7} {st.mean(ra):>6.2f}s {st.mean(im):>7.2f}s "
          f"{st.mean(sq):>8.1f} {st.mean(im)/st.mean(ra)*100:>5.0f}%")
print("  " + "-" * 52)
