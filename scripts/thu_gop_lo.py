"""Gop nhieu manh vao MOT lan goi F5 thi nhanh hon bao nhieu?

infer_batch_process chi lap qua tung cau - khong gop lo. Nhung CFM.sample ben
duoi NHAN LO that: cond (b, nw), text danh sach b phan tu, duration rieng tung
phan tu. Gop lo thi doan mau chi xu ly MOT lan cho ca lo thay vi b lan.

Do: cung 8 manh, sinh tuan tu vs gop lo co 2/4/8.
"""
import asyncio, sys, time, statistics as st
sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, torch, torchaudio
from backend.config import settings
from backend.services import tts_service as T
from backend.pipeline.text_normalizer import normalize_for_tts
from f5_tts.infer.utils_infer import (infer_batch_process, target_sample_rate,
                                      hop_length, target_rms)
from f5_tts.model.utils import convert_char_to_pinyin

MANH = ["dạ vâng ạ em nghe", "anh cần chuẩn bị chứng minh", "nhân dân và sổ hộ",
        "khẩu bản sao công chứng", "sao kê lương ba tháng", "gần nhất của anh ạ",
        "em sẽ hỗ trợ anh", "làm hồ sơ ngay nhé"]
LAP = 3

def chuan_bi(rw, rs, dev):
    a = rw
    if a.shape[0] > 1: a = torch.mean(a, dim=0, keepdim=True)
    rms = torch.sqrt(torch.mean(torch.square(a)))
    if rms < target_rms: a = a * target_rms / rms
    if rs != target_sample_rate:
        a = torchaudio.transforms.Resample(rs, target_sample_rate)(a)
    return a.to(dev), rms

def sinh_lo(svc, rw, rs, rt, chu, fix, nfe):
    """Mot lan goi cho CA LO."""
    dev = svc._model.device
    a, rms = chuan_bi(rw, rs, dev)
    b = len(chu)
    ref_len = a.shape[-1] // hop_length
    cond = a.repeat(b, 1)
    van = convert_char_to_pinyin([rt + c for c in chu])
    dur = torch.tensor([int(f * target_sample_rate / hop_length) for f in fix],
                       device=dev, dtype=torch.long)
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
        gen, _ = svc._model.sample(cond=cond, text=van, duration=dur, steps=nfe,
                                   cfg_strength=2.0, sway_sampling_coef=-1)
        gen = gen.to(torch.float32)[:, ref_len:, :].permute(0, 2, 1)
        song = svc._vocoder.decode(gen)
        if rms < target_rms: song = song * rms / target_rms
        song = song.cpu().numpy()
    ra = []
    for i, d in enumerate(dur.tolist()):
        n = (d - ref_len) * hop_length
        ra.append(song[i][:n] if song.ndim > 1 else song[:n])
    return ra

def sinh_tuan_tu(svc, rw, rs, rt, chu, fix, nfe, sp):
    ra = []
    for c, f in zip(chu, fix):
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            y, _, _ = next(infer_batch_process((rw, rs), rt, [c], svc._model,
                svc._vocoder, mel_spec_type="vocos", progress=None, nfe_step=nfe,
                speed=sp, fix_duration=f, device=svc._model.device))
        ra.append(np.asarray(y))
    return ra

async def main():
    svc = T.F5TTSService(); svc.load()
    ten = svc.default_voice_name(); await svc.ensure_voice(ten)
    rw, rs, rt = svc._voices[ten]; sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step
    dai_ref = rw.shape[-1] / rs
    chu = [T.bo_dau_cau_cho_f5(normalize_for_tts(m)) for m in MANH]
    fix = [T.thoi_luong_ep(c, dai_ref, sp) for c in chu]

    # ham nong ca hai duong
    sinh_tuan_tu(svc, rw, rs, rt, chu[:2], fix[:2], nfe, sp)
    sinh_lo(svc, rw, rs, rt, chu[:2], fix[:2], nfe)

    t = []
    for _ in range(LAP):
        t0 = time.perf_counter(); r0 = sinh_tuan_tu(svc, rw, rs, rt, chu, fix, nfe, sp)
        t.append((time.perf_counter()-t0)*1000)
    goc = st.median(t)
    print(f"\n  8 manh, {sum(len(x) for x in r0)/target_sample_rate:.2f}s tieng ra\n")
    print(f"  {'cách':<16} {'tổng':>9} {'mỗi mảnh':>10} {'so với tuần tự':>16}")
    print("  " + "-"*56)
    print(f"  {'tuần tự':<16} {goc:>8.0f}ms {goc/8:>9.0f}ms {'100%':>16}")
    for co in (2, 4, 8):
        t = []
        for _ in range(LAP):
            t0 = time.perf_counter()
            for i in range(0, 8, co):
                sinh_lo(svc, rw, rs, rt, chu[i:i+co], fix[i:i+co], nfe)
            t.append((time.perf_counter()-t0)*1000)
        s = st.median(t)
        print(f"  {'gộp lô ' + str(co):<16} {s:>8.0f}ms {s/8:>9.0f}ms {s/goc*100:>15.0f}%")
    print("  " + "-"*56)
asyncio.run(main())
