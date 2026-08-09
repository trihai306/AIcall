"""Vi sao moi manh doc mot nhip khac nhau - va cach ep cho deu.

Nguoi dung: "no doc kieu khong dong bo toc do, luc nhanh luc cham".
Do duoc: cac cau ra tu 194 den 500 am tiet/phut, chenh hon 2.5 lan.

Da loai: kich thuoc manh (lech 31-42% o MOI muc, 5 tu con deu nhat) va cau dem
dung san (khop -11%).

Gia thuyet con lai, o ngay trong cong thuc cua F5:

    duration = ref_len + int(ref_len / ref_text_BYTES * gen_text_BYTES / speed)

F5 cap thoi luong theo so BYTE cua chu. Nhung tai nguoi nghe nhip theo AM TIET.
Tieng Viet co dau la 3 byte moi chu ("ạ" = 3 byte) trong khi chu khong dau chi 1
("anh" = 3 byte cho 3 chu cai). Nen hai cau CUNG SO AM TIET nhung khac mat do
dau se duoc cap thoi luong khac han - va nghe ra nhanh cham khac nhau.

Phan [1] kiem gia thuyet: doi chieu byte-tren-am-tiet voi nhip do duoc.
Phan [2] thu cach chua: tu tinh thoi luong theo AM TIET roi ep bang fix_duration.

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\do_nhip_theo_byte.py
"""
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
NHIP_MUC_TIEU = 287.0        # nhip RONG do tren ban thu goc, am tiet/phut

CAU = [
    # nhieu dau - byte/am tiet CAO
    "Dạ vâng ạ, để em kiểm tra lại giúp anh chị nhé",
    "Vâng ạ, đợi em một lát rồi em báo lại ngay ạ",
    "Dạ, khoản vay tín chấp của bên em rất tiện lợi ạ",
    # it dau - byte/am tiet THAP
    "Anh cho em xin so tai khoan ngan hang nhe",
    "Em xin phep hoi anh mot cau ngan thoi nhe",
    "Anh vui long cho em xin thong tin ca nhan",
    # hon hop
    "Lãi suất bên em là bảy phẩy chín phần trăm một năm",
    "Hạn mức tối đa năm trăm triệu, thời hạn sáu mươi tháng",
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
    to = np.abs(x[: k * n].reshape(k, n)).max(axis=1)
    return float((to >= NGUONG_IM).sum() * KHUNG)


def main():
    svc = F5TTSService()
    svc.load()
    ten = svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    rw, rs, rt = svc._voices[ten]
    sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step
    dai_ref = rw.shape[-1] / rs
    from f5_tts.infer.utils_infer import infer_batch_process

    def sinh(c, fix=None):
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            y, sr, _ = next(infer_batch_process(
                (rw, rs), rt, [c], svc._model, svc._vocoder,
                mel_spec_type="vocos", progress=None, nfe_step=nfe, speed=sp,
                fix_duration=fix, device=svc._model.device))
        y = trim_silence(np.asarray(y), sr)
        at = am_tiet(nghe_lai(y, sr))
        g = giay_co_tieng(y, sr)
        return (at / g * 60 if at >= 2 and g > 0.2 else 0), len(y) / sr

    print(f"\n  giọng {ten}   speed {sp:.2f}   nfe {nfe}   đoạn mẫu {dai_ref:.2f}s")
    print(f"  mốc nhịp muốn có: {NHIP_MUC_TIEU:.0f} âm tiết/phút\n")

    # ---- [1] byte tren am tiet co giai thich duoc nhip khong -------------
    print("  [1] BYTE TRÊN ÂM TIẾT ĐỐI CHIẾU VỚI NHỊP ĐỌC RA")
    print(f"      {'byte/âm tiết':>13} {'nhịp ra':>9}  câu")
    print("      " + "-" * 62)
    bs, ns = [], []
    for c in CAU:
        n_at = am_tiet(c)
        bpa = len(c.encode("utf-8")) / max(n_at, 1)
        nhip, _ = sinh(c)
        if nhip:
            bs.append(bpa); ns.append(nhip)
            print(f"      {bpa:>13.2f} {nhip:>8.0f}  {c[:44]}")
    if len(bs) >= 3:
        r = float(np.corrcoef(bs, ns)[0, 1])
        print(f"\n      Tương quan byte/âm tiết với nhịp: {r:+.2f}")
        print("      Âm mạnh (dưới -0.6) = đúng: chữ càng nhiều byte thì đọc càng CHẬM.")

    # ---- [2] ep thoi luong theo AM TIET ---------------------------------
    print(f"\n  [2] ÉP THỜI LƯỢNG THEO ÂM TIẾT (fix_duration)")
    print(f"      {'nhịp thường':>12} {'nhịp ép':>9}  câu")
    print("      " + "-" * 62)
    th, ep = [], []
    for c in CAU:
        n_at = am_tiet(c)
        # thoi luong CAN cho phan sinh, tinh theo am tiet
        can = n_at / (NHIP_MUC_TIEU / 60.0)
        nhip_th, _ = sinh(c)
        nhip_ep, _ = sinh(c, fix=dai_ref + can)
        if nhip_th and nhip_ep:
            th.append(nhip_th); ep.append(nhip_ep)
            print(f"      {nhip_th:>12.0f} {nhip_ep:>8.0f}  {c[:44]}")
    if th and ep:
        lt = (max(th) - min(th)) / np.median(th) * 100
        le = (max(ep) - min(ep)) / np.median(ep) * 100
        print(f"\n      lệch nhịp giữa các câu : {lt:.0f}%  ->  {le:.0f}%")
        print(f"      trung vị               : {np.median(th):.0f}  ->  {np.median(ep):.0f}"
              f"   (mốc {NHIP_MUC_TIEU:.0f})")


if __name__ == "__main__":
    main()
