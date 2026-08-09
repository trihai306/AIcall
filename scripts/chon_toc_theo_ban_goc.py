"""Tim speed cho F5 khop NHIP THAT cua nguoi thu - va xem no co chua luon
quang dung bia giua cau khong.

Do duoc tren toan bo ban thu goc (20.2 phut, scripts/do_nhip_ban_goc.py):
    nhip THO  220 am tiet/phut   (tinh ca luc nghi)
    nhip RONG 287 am tiet/phut   (chi luc co tieng)

Phai so voi nhip RONG, khong phai nhip tho: F5 chi sinh phan CO TIENG, con
quang nghi giua cau da duoc chen bang code (`nhip_nghi_sau` trong pipeline).
Lay nham nhip tho thi AI se noi cham hon nguoi that roi lai bi chen them nghi.

Gia thuyet dang kiem: speed 0.90 dang bat F5 KEO GIAN tieng so voi nhip that
(206 so voi 287). Keo gian = cap DU thoi luong, ma cap du chinh la co che de ra
quang dung bia giua cau. Neu dung thi tang speed se chua luon ca hai.

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\chon_toc_theo_ban_goc.py
    .venv\\python.exe scripts\\chon_toc_theo_ban_goc.py --speed 1.0 1.2 1.4
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
RA = Path("C:/tmp/toctheogoc")
NGUONG_IM, KHUNG = 0.015, 0.02
MUC_TIEU_RONG = 287        # do duoc tren ban thu goc

# Cau DAI khong dau o giua - de bat quang dung bia. 34 am tiet la muc hong
# nang nhat do duoc (4/4 luot) o speed 0.90.
CAU_DAI = ("Bên em đang triển khai gói vay tín chấp dành cho khách hàng có thu nhập "
           "ổn định với hạn mức linh hoạt và thủ tục rất đơn giản nhanh gọn nên anh chị")
# Cau binh thuong co dau, de nghe thu
CAU_THU = [
    "Dạ em chào anh chị, em gọi từ ngân hàng để tư vấn về khoản vay tín chấp ạ.",
    "Lãi suất bên em đang là từ bảy phẩy chín phần trăm một năm, tính trên dư nợ giảm dần.",
    "Anh chị cho em xin ít phút để em tư vấn kỹ hơn được không ạ?",
]


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
    return json.loads(urllib.request.urlopen(r, timeout=180).read()).get("text", "").strip()


def am_tiet(s):
    return len([t for t in re.split(r"\s+", s.strip()) if re.search(r"\w", t)])


def giay_co_tieng(x, sr):
    n = max(1, int(sr * KHUNG))
    k = len(x) // n
    if k == 0:
        return len(x) / sr
    to = np.array([np.abs(x[i*n:(i+1)*n]).max() for i in range(k)])
    return float((to >= NGUONG_IM).sum() * KHUNG)


def lang_giua(x, sr, toi_thieu_ms=250):
    n = max(1, int(sr * KHUNG))
    k = len(x) // n
    to = np.array([np.abs(x[i*n:(i+1)*n]).max() for i in range(k)])
    im = to < NGUONG_IM
    ra, i = [], 0
    while i < k:
        if im[i]:
            j = i
            while j < k and im[j]:
                j += 1
            if i > 0 and j < k and (j - i) * 20 >= toi_thieu_ms:
                ra.append((j - i) * 20)
            i = j
        else:
            i += 1
    return ra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=float, nargs="+",
                    default=[0.90, 1.00, 1.10, 1.20, 1.30])
    ap.add_argument("--lan", type=int, default=4)
    a = ap.parse_args()

    svc = F5TTSService()
    svc.load()
    ten = svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    rw, rs, rt = svc._voices[ten]
    nfe = settings.f5tts_nfe_step
    from f5_tts.infer.utils_infer import infer_batch_process
    RA.mkdir(parents=True, exist_ok=True)

    print(f"\n  giong {ten}   nfe {nfe}   moc can dat: nhip RONG {MUC_TIEU_RONG} am tiet/phut")
    print(f"  cau do quang dung: {am_tiet(CAU_DAI)} am tiet, KHONG dau o giua\n")
    print(f"  {'speed':>6} {'nhip RONG':>10} {'lech moc':>9} {'nhip THO':>9}"
           f" {'luot co dung bia':>17} {'dung lau nhat':>14}")
    print("  " + "-" * 74)

    for sp in a.speed:
        rongs, thos, ban, laus = [], [], 0, []
        for k in range(a.lan):
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
                y, sr, _ = next(infer_batch_process(
                    (rw, rs), rt, [CAU_DAI], svc._model, svc._vocoder,
                    mel_spec_type="vocos", progress=None, nfe_step=nfe, speed=sp,
                    device=svc._model.device))
            y = trim_silence(np.asarray(y), sr)
            at = am_tiet(nghe_lai(y, sr))
            ct = giay_co_tieng(y, sr)
            if at >= 5 and ct > 0.5:
                rongs.append(at / ct * 60)
                thos.append(at / (len(y) / sr) * 60)
            lg = lang_giua(y, sr)
            ban += bool(lg)
            laus.append(max(lg) if lg else 0)
        if not rongs:
            print(f"  {sp:>6.2f}   (STT khong doc duoc)")
            continue
        r, t = float(np.median(rongs)), float(np.median(thos))
        co = "  <== KHOP" if abs(r - MUC_TIEU_RONG) <= 15 and ban == 0 else ""
        print(f"  {sp:>6.2f} {r:>10.0f} {r-MUC_TIEU_RONG:>+9.0f} {t:>9.0f}"
              f" {ban:>14}/{a.lan} {max(laus):>12.0f}ms{co}")

        # xuat mot ban de nghe
        manh = []
        for c in CAU_THU:
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
                y, sr, _ = next(infer_batch_process(
                    (rw, rs), rt, [c], svc._model, svc._vocoder,
                    mel_spec_type="vocos", progress=None, nfe_step=nfe, speed=sp,
                    device=svc._model.device))
            y = trim_silence(np.asarray(y), sr)
            manh.append(y / max(1.0, float(np.abs(y).max())))
            manh.append(np.zeros(int(sr * 0.4), dtype=np.float32))
        sf.write(RA / f"speed_{sp:.2f}.wav", np.concatenate(manh), sr)

    print("  " + "-" * 74)
    print(f"\n  Moc {MUC_TIEU_RONG} am tiet/phut la nhip RONG do tren 20.2 phut ban thu goc.")
    print("  'dung bia' = quang lang > 250ms giua cau, ma cau nay KHONG co dau nao o giua.")
    print(f"\n  wav o {RA}")


if __name__ == "__main__":
    main()
