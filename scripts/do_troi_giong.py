"""Do F5 TROI GIONG khi van ban dai: dung giua cau, bat lai dot ngot, doc cham dan.

Nguoi dung nghe ra ngay, con bo do cu thi mu: no cho STT nghe lai roi so CHU, ma
troi giong khong lam sai chu - chi lam sai NHIP. Ban chep van dung tung tieng
trong khi tai nghe ro la cau bi khuc khuyu.

Do dung ba thu nguoi dung ta:
  1. DUNG GIUA CAU  - quang lang > 250ms nam GIUA cau (khong tinh dau/cuoi).
                      Cau tuyen bo binh thuong khong nghi lau the o giua.
  2. DOC CHAM DAN   - cat doi ban ghi, cho STT nghe tung nua, so am tiet/giay.
                      Nua sau cham hon nua dau nhieu = troi.
  3. NGAT LEN       - bien do nhay vot ngay sau mot quang lang.

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\do_troi_giong.py
    .venv\\python.exe scripts\\do_troi_giong.py --toi 40   (thu toi 40 am tiet)
"""
import argparse
import asyncio
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import soundfile as sf          # noqa: E402
import torch                    # noqa: E402

from backend.config import settings                                  # noqa: E402
from backend.services.tts_service import F5TTSService, trim_silence  # noqa: E402

STT = "http://127.0.0.1:8178/inference"
RA = Path("C:/tmp/troigiong")

# KHONG CO DAU NAO O GIUA. Day la diem mau chot cua phep do.
#
# Ban dau dung cau co dau phay, roi dem quang lang > 250ms va goi do la "troi
# giong". SAI: F5 nghi o dau phay la DUNG (do duoc 140-310ms moi cho). Dem lai
# thi so quang nghi bam sat so dau phay - 22 am tiet co 1 phay ra 1.2 nghi,
# 32 am tiet co 2 phay ra 2.2 nghi. Tuc la dang do DAU CAU chu khong do loi.
#
# Cau khong dau thi moi quang lang > 250ms o giua deu la F5 tu bia ra.
NEN = ("Bên em đang triển khai gói vay tín chấp dành cho khách hàng có thu nhập "
       "ổn định với hạn mức linh hoạt và thủ tục rất đơn giản nhanh gọn nên anh "
       "chị hoàn toàn có thể yên tâm đăng ký ngay hôm nay để nhận được mức lãi "
       "suất tốt nhất mà bên em đang áp dụng cho khách hàng mới trong tháng này")
MOC = [8, 14, 20, 28, 36, 46, 56]      # so am tiet cua tung ban cat


def nghe_lai(x, sr) -> str:
    b = io.BytesIO()
    sf.write(b, x, sr, format="WAV", subtype="PCM_16")
    bd = b"----x"
    body = (b"--" + bd + b"\r\nContent-Disposition: form-data; name=\"file\"; "
            b"filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
            + b.getvalue() + b"\r\n--" + bd + b"--\r\n")
    r = urllib.request.Request(
        STT, data=body,
        headers={"Content-Type": "multipart/form-data; boundary=----x"})
    try:
        return json.loads(urllib.request.urlopen(r, timeout=180).read()).get("text", "").strip()
    except Exception:
        return ""


def am_tiet(s: str) -> int:
    return len([t for t in re.split(r"\s+", s.strip()) if re.search(r"\w", t)])


def lang_giua(x: np.ndarray, sr: int, nguong=0.02, toi_thieu_ms=250):
    """Cac quang lang NAM GIUA cau, tra list (bat_dau_giay, dai_ms)."""
    khung = max(1, int(sr * 0.02))                    # cua so 20ms
    n = len(x) // khung
    to = np.array([np.abs(x[i*khung:(i+1)*khung]).max() for i in range(n)])
    im = to < nguong
    ra, i = [], 0
    while i < n:
        if im[i]:
            j = i
            while j < n and im[j]:
                j += 1
            # bo quang lang o hai DAU
            if i > 0 and j < n:
                dai = (j - i) * 20
                if dai >= toi_thieu_ms:
                    ra.append((i * 0.02, dai))
            i = j
        else:
            i += 1
    return ra


def nhip_hai_nua(x, sr):
    """Am tiet/giay cua nua DAU va nua SAU. Nua sau cham hon nhieu = troi."""
    g = len(x) // 2
    a, b = x[:g], x[g:]
    na, nb = am_tiet(nghe_lai(a, sr)), am_tiet(nghe_lai(b, sr))
    return na / (len(a)/sr), nb / (len(b)/sr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--giong", default=None)
    # F5 lay mau NGAU NHIEN: mot lan do moi do dai la chua ket luan duoc.
    ap.add_argument("--lan", type=int, default=1, help="lap may lan moi do dai")
    ap.add_argument("--moc", type=int, nargs="+", default=None)
    a = ap.parse_args()

    svc = F5TTSService()
    svc.load()
    ten = a.giong or svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    rw, rs, rt = svc._voices[ten]
    sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step
    from f5_tts.infer.utils_infer import infer_batch_process
    RA.mkdir(parents=True, exist_ok=True)

    tu = NEN.split()
    print(f"\n  giong {ten}   doan mau {rw.shape[-1]/rs:.2f}s   speed {sp:.2f}   nfe {nfe}\n")
    print(f"  {'âm tiết':>8} {'giây ra':>8} {'nghỉ TB':>10} {'nghỉ dài nhất':>14}"
          f" {'lượt hỏng':>9} {'trôi nhịp':>14}")
    print("  " + "-" * 82)

    for m in (a.moc or MOC):
        cau = " ".join(tu[:m])
        sos, laus, giays, trois, ban = [], [], [], [], 0
        for k in range(a.lan):
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
                y, sr, _ = next(infer_batch_process(
                    (rw, rs), rt, [cau], svc._model, svc._vocoder,
                    mel_spec_type="vocos", progress=None, nfe_step=nfe, speed=sp,
                    device=svc._model.device))
            y = trim_silence(np.asarray(y), sr)
            if k == 0:
                sf.write(RA / f"{m:02d}_am_tiet.wav",
                         y / max(1.0, float(np.abs(y).max())), sr)
            lg = lang_giua(y, sr)
            lau = max((d for _, d in lg), default=0)
            na, nb = nhip_hai_nua(y, sr)
            sos.append(len(lg)); laus.append(lau); giays.append(len(y)/sr)
            trois.append((nb - na) / na * 100 if na else 0)
            ban += bool(lg)
        so = float(np.mean(sos)); lau = max(laus)
        troi = float(np.mean(trois))
        co = f"  <== {ban}/{a.lan} lượt CÓ nghỉ giữa" if ban else ""
        print(f"  {m:>8} {np.mean(giays):>7.2f}s {so:>10.1f} {lau:>12.0f}ms"
              f" {ban:>7}/{a.lan} {troi:>+13.0f}%{co}")

    print("  " + "-" * 82)
    print("\n  'nghỉ giữa' = số quãng lặng > 250ms NẰM GIỮA câu. Câu bình thường nên là 0-1.")
    print("  'trôi' = nhịp nửa sau so với nửa đầu. Âm nhiều = đọc chậm dần về cuối.")
    print(f"\n  wav ở {RA} - nghe từ ngắn tới dài sẽ thấy chỗ nào bắt đầu hỏng.")


if __name__ == "__main__":
    main()
