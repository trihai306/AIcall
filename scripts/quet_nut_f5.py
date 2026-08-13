"""Quet CAC NUT CUA CHINH F5 xem cai nao cuu duoc am tiet cuoi.

Bon nut chua ai cham: doan mau (ref clip), nfe_step, cfg_strength,
sway_sampling_coef. Thuoc do la thu DUY NHAT quan trong: may co nghe DUNG chu
cuoi khong, va chu cuoi to bang bao nhieu so voi cac chu khac.
"""
import io, statistics, sys, unicodedata, wave
import numpy as np
import torch as _t
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import backend.services.tts_service as TS
from backend.services.tts_service import DEVICE, bo_dau_cau_cho_f5, thoi_luong_ep
from f5_tts.infer.utils_infer import hop_length, target_rms, target_sample_rate
from whisper_server.pho_server import _pick_device
from faster_whisper import WhisperModel
import torchaudio
from f5_tts.model.utils import convert_char_to_pinyin
M=r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-medium-ct2"
CAU=["Thời gian vay tối đa hai mươi lăm năm.",
     "Anh chị chuẩn bị hồ sơ vay vốn.",
     "Hạn mức lên đến năm trăm triệu đồng.",
     "Thời hạn vay là ba mươi sáu tháng.",
     "Bên em hỗ trợ vay mua nhà và vay kinh doanh.",
     "Thủ tục rất đơn giản và nhanh gọn."]
def rms_(x): return float(np.sqrt(np.mean(x**2))) if len(x) else 0.0
dev,ct=_pick_device(); stt=WhisperModel(M,device=dev,compute_type=ct)
def dong(x,sr):
    b=io.BytesIO()
    with wave.open(b,"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x,-1,1)*32767).astype(np.int16).tobytes())
    return b.getvalue()
def cham(wav, mong):
    sr_,x=None,None
    with wave.open(io.BytesIO(wav)) as w:
        sr_=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
    segs,_=stt.transcribe(io.BytesIO(wav),language="vi",word_timestamps=True,
                          vad_filter=False,beam_size=5)
    tu=[w for s in segs for w in (s.words or []) if w.end>w.start]
    v=[(unicodedata.normalize("NFC",w.word.strip().lower().strip(".,?!")),
        rms_(x[int(w.start*sr_):int(w.end*sr_)])) for w in tu]
    v=[t for t in v if t[1]>0]
    if len(v)<3: return False,0.0
    ty=v[-1][1]/max(1e-9,statistics.median(t[1] for t in v[:-1]))
    return v[-1][0]==mong, ty
def sinh(tts, cau, voice, nfe, cfg, sway):
    ref_wave, ref_sr, ref_text = tts._voices[voice]
    toc = tts.toc_do_cua("giong_heu")*tts.he_so_thoai()
    c = bo_dau_cau_cho_f5(TS.normalize_for_tts(cau))
    c = TS.dong_dau_cuoi(c)
    a = ref_wave
    if a.shape[0] > 1: a = _t.mean(a, dim=0, keepdim=True)
    r = _t.sqrt(_t.mean(_t.square(a)))
    if r < target_rms: a = a*target_rms/r
    if ref_sr != target_sample_rate:
        a = torchaudio.transforms.Resample(ref_sr, target_sample_rate)(a)
    a = a.to(DEVICE)
    rt = ref_text+" " if len(ref_text[-1].encode("utf-8"))==1 else ref_text
    ref_len = a.shape[-1]//hop_length
    ep = thoi_luong_ep(c, ref_wave.shape[-1]/ref_sr, toc)
    k = int(ep*target_sample_rate/hop_length)
    TS._dat_seed(_t, c, voice, toc)
    with _t.inference_mode(), tts._autocast_ctx():
        gen,_x = tts._model.sample(cond=a, text=convert_char_to_pinyin([rt+c]),
            duration=_t.tensor([k],device=DEVICE,dtype=_t.long),
            steps=nfe, cfg_strength=cfg, sway_sampling_coef=sway)
        gen = gen.to(_t.float32)[:, ref_len:, :].permute(0,2,1)
        s = tts._vocoder.decode(gen)
        if r < target_rms: s = s*r/target_rms
        s = s.cpu().numpy()[0][:(k-ref_len)*hop_length]
    return dong(s, target_sample_rate)
def chay(tts, nhan, voice, nfe, cfg, sway):
    d=0; ty=[]
    for cau in CAU:
        mong=unicodedata.normalize("NFC",cau.rstrip(".").split()[-1].lower())
        ok,t=cham(sinh(tts,cau,voice,nfe,cfg,sway), mong)
        d+=ok; ty.append(t)
    print(f"{nhan:<28}{d}/{len(CAU)}   chữ cuối/TV {sum(ty)/len(ty):.2f}")
def main():
    tts=TS.F5TTSService(); tts.load()
    import asyncio
    for v in ("giong_heu","heu_a","heu_b","heu_c","heu_d","heu_e"):
        try: asyncio.get_event_loop().run_until_complete(tts.ensure_voice(v))
        except Exception: pass
    print("nghe ĐÚNG chữ cuối / 6 câu\n" + "-"*50)
    print("— đổi ĐOẠN MẪU (nfe 16, cfg 2.0, sway -1):")
    for v in ("giong_heu","heu_a","heu_b","heu_c","heu_d","heu_e"):
        if v in tts._voices: chay(tts, f"   {v}", v, 16, 2.0, -1.0)
    print("— đổi nfe_step (giong_heu):")
    for n in (16,24,32,48): chay(tts, f"   nfe {n}", "giong_heu", n, 2.0, -1.0)
    print("— đổi cfg_strength:")
    for g in (1.0,1.5,2.0,3.0): chay(tts, f"   cfg {g}", "giong_heu", 16, g, -1.0)
    print("— đổi sway_sampling_coef:")
    for s in (-1.0,-0.5,0.0,1.0): chay(tts, f"   sway {s}", "giong_heu", 16, 2.0, s)
main()
