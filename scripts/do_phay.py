import asyncio, sys
from pathlib import Path
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, torch
from backend.config import settings
from backend.services.tts_service import F5TTSService, trim_silence

NGUONG, KH = 0.015, 0.02
def lang(x, sr, tt=200):
    n = max(1, int(sr*KH)); k = len(x)//n
    to = np.array([np.abs(x[i*n:(i+1)*n]).max() for i in range(k)])
    im = to < NGUONG; ra=[]; i=0
    while i < k:
        if im[i]:
            j=i
            while j<k and im[j]: j+=1
            if i>0 and j<k and (j-i)*20>=tt: ra.append((j-i)*20)
            i=j
        else: i+=1
    return ra

CAP = [
 ("0 phay", "Anh chị chuẩn bị giấy tờ tuỳ thân và sổ hộ khẩu rồi gửi lại cho bên em nhé ạ"),
 ("1 phay", "Anh chị chuẩn bị giấy tờ tuỳ thân, và sổ hộ khẩu rồi gửi lại cho bên em nhé ạ"),
 ("3 phay", "Anh chị chuẩn bị giấy tờ tuỳ thân, sổ hộ khẩu, sao kê lương, rồi gửi cho bên em ạ"),
]
svc = F5TTSService(); svc.load()
ten = svc.default_voice_name(); asyncio.run(svc.ensure_voice(ten))
rw, rs, rt = svc._voices[ten]
sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step
from f5_tts.infer.utils_infer import infer_batch_process
print(f"\n  speed {sp:.2f}  nfe {nfe}   8 luot moi ban\n")
print(f"  {'ban':<9} {'so nghi TB':>11} {'nghi dai nhat':>14} {'cac nghi do duoc'}")
print("  " + "-"*70)
for nhan, cau in CAP:
    sos, laus, tatca = [], [], []
    for _ in range(8):
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            y, sr, _ = next(infer_batch_process((rw, rs), rt, [cau], svc._model,
                svc._vocoder, mel_spec_type="vocos", progress=None,
                nfe_step=nfe, speed=sp, device=svc._model.device))
        lg = lang(trim_silence(np.asarray(y), sr), sr)
        sos.append(len(lg)); laus.append(max(lg) if lg else 0); tatca += lg
    print(f"  {nhan:<9} {np.mean(sos):>11.1f} {max(laus):>12.0f}ms   "
          f"{sorted(set(tatca), reverse=True)[:8]}")
print("  " + "-"*70)
