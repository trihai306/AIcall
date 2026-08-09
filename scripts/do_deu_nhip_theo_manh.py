"""Cat manh ngan co lam nhip doc KHONG DEU giua cac manh khong?

Nguoi dung: "no doc kieu khong dong bo toc do, luc nhanh luc cham".

Nghi van: cong thuc thoi luong cua F5
    duration = ref_len + int(ref_len / ref_text_bytes * gen_text_bytes / speed)
chia theo BYTE va co int() lam tron. Manh cang NGAN thi sai so lam tron cang
chiem ti le lon -> moi manh ra mot nhip khac nhau. Cat 5 tu la ngan nhat tu
truoc toi nay, nen neu gia thuyet dung thi day la loi do chinh viec cat nho gay
ra, khong phai loi san co.

Do: cung mot doan van, cat theo N tu, sinh tung manh, do nhip RONG (am tiet tren
giay CO TIENG) cua tung manh, roi xem cac manh lech nhau bao nhieu.

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\do_deu_nhip_theo_manh.py
    .venv\\python.exe scripts\\do_deu_nhip_theo_manh.py --tu 5 8 12 20
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
NGUONG_IM, KHUNG = 0.015, 0.02

VAN = ("Dạ vâng ạ với tình hình thu nhập của anh chị thì em có thể tư vấn hạn mức "
       "lên đến năm trăm triệu đồng thời hạn vay linh hoạt từ mười hai đến sáu mươi "
       "tháng và lãi suất áp dụng từ bảy phẩy chín phần trăm một năm tính trên dư nợ "
       "giảm dần ạ anh chị chuẩn bị giúp em chứng minh nhân dân sổ hộ khẩu và sao kê "
       "lương ba tháng gần nhất thì bên em xử lý rất nhanh ạ")


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
    to = np.abs(x[: k * n].reshape(k, n)).max(axis=1)
    return float((to >= NGUONG_IM).sum() * KHUNG)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tu", type=int, nargs="+", default=[5, 8, 12, 20])
    a = ap.parse_args()

    svc = F5TTSService()
    svc.load()
    ten = svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    rw, rs, rt = svc._voices[ten]
    sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step
    from f5_tts.infer.utils_infer import infer_batch_process

    tu = VAN.split()
    print(f"\n  giọng {ten}   speed {sp:.2f}   nfe {nfe}   văn bản {len(tu)} từ\n")
    print(f"  {'cắt':>6} {'mảnh':>5} {'nhịp chậm nhất':>15} {'nhanh nhất':>12}"
          f" {'trung vị':>10} {'lệch':>7}")
    print("  " + "-" * 62)

    for n in a.tu:
        manh = [" ".join(tu[i:i+n]) for i in range(0, len(tu), n)]
        nhips = []
        for c in manh:
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
                y, sr, _ = next(infer_batch_process(
                    (rw, rs), rt, [c], svc._model, svc._vocoder,
                    mel_spec_type="vocos", progress=None, nfe_step=nfe, speed=sp,
                    device=svc._model.device))
            y = trim_silence(np.asarray(y), sr)
            at = am_tiet(nghe_lai(y, sr))
            ct = giay_co_tieng(y, sr)
            if at >= 2 and ct > 0.2:
                nhips.append(at / ct * 60)
        if not nhips:
            print(f"  {n:>6} — STT không đọc được")
            continue
        tv = float(np.median(nhips))
        lech = (max(nhips) - min(nhips)) / tv * 100
        print(f"  {n:>4} từ {len(manh):>5} {min(nhips):>14.0f} {max(nhips):>11.0f}"
              f" {tv:>9.0f} {lech:>6.0f}%")

    print("  " + "-" * 62)
    print("\n  'lệch' = (nhanh nhất - chậm nhất) / trung vị. Càng cao càng nghe")
    print("  ra 'lúc nhanh lúc chậm'. Dưới ~30% thì tai gần như không nhận ra.")


if __name__ == "__main__":
    main()
