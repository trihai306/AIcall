"""Kiem tra: manh ket bang TIEU TU cuoi cau (nha/nhe/a) co bi keo dai khong.

Gia thuyet: so_am_tiet dem "nha" bang mot am tiet DAY DU, nhung noi ra no rat
nhe. Dem thua thi fix_duration cap du gio, F5 phai keo dai chinh chu do.

Doi chung bat buoc: manh CUNG SO AM TIET nhung ket bang mot chu NANG. Neu chi
do manh co tieu tu thi khong biet 250ms la dai hay binh thuong.

Moi cau sinh 2 lan roi lay trung binh - F5 dao dong +-6% giua cac lan.
"""
import sys, statistics as st
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, torch, asyncio
from backend.config import settings
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services import tts_service as T
from f5_tts.infer.utils_infer import infer_batch_process

CAP = [  # (ket bang tieu tu, ket bang chu nang) - cung so am tiet
 ("Lãi suất vay tín chấp bên em chỉ từ bảy phẩy chín phần trăm nha",
  "Lãi suất vay tín chấp bên em chỉ từ bảy phẩy chín phần trăm thôi"),
 ("Hồ sơ của anh hoàn toàn đủ điều kiện để vay bên em nhé",
  "Hồ sơ của anh hoàn toàn đủ điều kiện để vay bên em rồi"),
 ("Anh chuẩn bị giúp em sao kê lương ba tháng gần nhất ạ",
  "Anh chuẩn bị giúp em sao kê lương ba tháng gần nhất nhá"),
 ("Thời gian giải ngân chỉ trong vòng hai mươi bốn giờ thôi nha",
  "Thời gian giải ngân chỉ trong vòng hai mươi bốn giờ làm việc"),
 ("Em sẽ gửi anh bảng tính lãi chi tiết qua tin nhắn nhé",
  "Em sẽ gửi anh bảng tính lãi chi tiết qua tin nhắn ngay"),
]
LAP = 2

svc = T.F5TTSService(); svc.load()
ten = svc.default_voice_name(); asyncio.run(svc.ensure_voice(ten))
rw, rs, rt = svc._voices[ten]; sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step
dai_ref = rw.shape[-1] / rs

def sinh(chu, fix):
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
        y, sr, _ = next(infer_batch_process((rw, rs), rt, [T.bo_dau_cau_cho_f5(chu)],
            svc._model, svc._vocoder, mel_spec_type="vocos", progress=None,
            nfe_step=nfe, speed=sp, fix_duration=fix, device=svc._model.device))
    return T.cat_lang_bia(T.trim_silence(np.asarray(y), sr), sr), sr

def am_cuoi(y, sr):
    """(dai am tiet cuoi, trung vi am tiet giua) tinh bang ms."""
    h = max(1, int(sr * 0.01)); k = len(y) // h
    e = np.array([float(np.sqrt((y[i*h:(i+1)*h] ** 2).mean())) for i in range(k)])
    if k < 25: return None
    e = np.convolve(e, np.ones(5) / 5, mode="same")
    dinh = [i for i in range(3, k-3)
            if e[i] == max(e[max(0,i-7):i+8]) and e[i] > e.max() * 0.20]
    if len(dinh) < 4: return None
    ranh = [0] + [int(np.argmin(e[a:b]) + a) for a, b in zip(dinh, dinh[1:])] + [k]
    d = np.diff(ranh) * 10.0
    return float(d[-1]), float(np.median(d[:-1]))

def do(chu):
    n = normalize_for_tts(chu)
    fix = T.thoi_luong_ep(n, dai_ref, sp)
    c, g = [], []
    for _ in range(LAP):
        y, sr = sinh(n, fix); r = am_cuoi(y, sr)
        if r: c.append(r[0]); g.append(r[1])
    return (st.mean(c), st.mean(g), T.so_am_tiet(n)) if c else (0, 0, 0)

print(f"\n  MANH KET BANG TIEU TU  vs  MANH KET BANG CHU NANG   ({LAP} lan/cau)\n")
print(f"  {'':<5} {'am':>3} {'cuoi':>7} {'giua':>7} {'ty le':>7}   chu cuoi")
print("  " + "-" * 62)
ty_t, ty_n = [], []
for a, b in CAP:
    for nhan, cau, kho in (("tiểu", a, ty_t), ("nặng", b, ty_n)):
        c, g, am = do(cau)
        if g:
            kho.append(c / g)
            print(f"  {nhan:<5} {am:>3} {c:>5.0f}ms {g:>5.0f}ms {c/g:>6.2f}x   ...{cau.split()[-1]}")
    print()
print("  " + "-" * 62)
print(f"\n  ket bang TIEU TU : am cuoi dai gap {st.mean(ty_t):.2f} lan am thuong")
print(f"  ket bang CHU NANG: am cuoi dai gap {st.mean(ty_n):.2f} lan am thuong")
print(f"  chenh: {st.mean(ty_t)/max(st.mean(ty_n),0.01):.2f} lan")
