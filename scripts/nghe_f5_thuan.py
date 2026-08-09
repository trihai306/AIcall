"""Sinh tieng THANG tu F5, khong qua LLM, de nghe va do rieng chat luong giong.

Dung khi nghi van nam o F5 chu khong o cau chu do LLM sinh ra: bo han LLM di thi
con lai dung mot bien.

Do luon "LAP DUOI CAU" - kieu hong dac trung cua F5 khi duoc cap DU thoi luong:
model phai lap day khung nen no lap lai am cuoi. Cong thuc cua F5:

    duration = ref_len + int(ref_len / ref_text_bytes * gen_text_bytes / speed)

speed THAP => duration DAI => du khung => de lap duoi.
Ti le ref_len/ref_text_bytes cua doan mau cung anh huong y het.

Cach do: cho STT nghe lai, roi so duoi ban chep voi duoi cau that. Lap thi ban
chep se co chu cuoi (hoac cum cuoi) xuat hien hai lan lien nhau.

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\nghe_f5_thuan.py
    .venv\\python.exe scripts\\nghe_f5_thuan.py --speed 0.90 1.00
"""
import argparse
import asyncio
import io
import json
import re
import sys
import unicodedata
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
RA = Path("C:/tmp/f5thuan")
NGHI = 0.5

# Cau DAI dan - manh that trong hoi thoai len toi 11.4s, khong phai 2-3s.
# F5 troi giong khi van ban dai, nen phai thu dung co that moi tai hien duoc.
CAU_DAI = [
    "Dạ vâng ạ, với tình hình thu nhập của anh chị thì em có thể tư vấn hạn mức "
    "lên đến năm trăm triệu đồng, thời hạn vay linh hoạt từ mười hai đến sáu mươi "
    "tháng, và lãi suất áp dụng từ bảy phẩy chín phần trăm một năm tính trên dư nợ "
    "giảm dần ạ.",
    "Anh chị chuẩn bị giúp em chứng minh nhân dân hoặc căn cước công dân, sổ hộ "
    "khẩu hoặc giấy tạm trú, sao kê lương ba tháng gần nhất và hợp đồng lao động "
    "còn hiệu lực, để hồ sơ đầy đủ thì bên em xử lý nhanh hơn nhiều ạ.",
    "Sau khi anh chị nộp đủ hồ sơ thì bên em thẩm định trong vòng một ngày làm "
    "việc, phê duyệt xong là giải ngân ngay trong hai mươi bốn giờ, tiền chuyển "
    "thẳng vào tài khoản anh chị đăng ký chứ không phải ra quầy nhận ạ.",
]

CAU = [
    "Dạ em chào anh chị, em gọi từ ngân hàng để tư vấn về khoản vay tín chấp ạ.",
    "Lãi suất bên em đang là từ bảy phẩy chín phần trăm một năm.",
    "Hạn mức tối đa là năm trăm triệu đồng, thời hạn vay lên tới sáu mươi tháng.",
    "Anh chị chỉ cần chứng minh nhân dân, sổ hộ khẩu và sao kê lương ba tháng.",
    "Sau khi phê duyệt thì bên em giải ngân trong vòng hai mươi bốn giờ ạ.",
    "Anh chị cho em xin ít phút để em tư vấn kỹ hơn được không ạ?",
    "Dạ vâng, em hiểu rồi ạ.",
    "Vâng ạ, anh chị giữ máy giúp em một lát nhé.",
]


def chuan(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


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


def lap_duoi(goc: str, nghe: str) -> str:
    """Ban chep co lap chu/cum o CUOI khong. Tra chuoi mo ta, rong = khong lap."""
    t = chuan(nghe).split()
    if len(t) < 4:
        return ""
    # cum 1-3 chu cuoi co bi nhac hai lan lien nhau khong
    for n in (3, 2, 1):
        if len(t) >= 2 * n and t[-n:] == t[-2 * n:-n]:
            return " ".join(t[-n:]) + f"  (lap cum {n} chu)"
    # ban chep dai hon han cau that o phan duoi
    g = chuan(goc).split()
    if len(t) > len(g) + 2 and t[len(g):]:
        return " ".join(t[len(g):]) + "  (thua duoi)"
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=float, nargs="+", default=None,
                    help="cac muc speed muon thu; mac dinh lay tu cau hinh")
    ap.add_argument("--giong", default=None)
    a = ap.parse_args()

    svc = F5TTSService()
    svc.load()
    ten = a.giong or svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    rw, rs, rt = svc._voices[ten]
    nfe = settings.f5tts_nfe_step
    mucs = a.speed or [svc.toc_do_cua(ten)]

    from f5_tts.infer.utils_infer import infer_batch_process
    RA.mkdir(parents=True, exist_ok=True)

    print(f"\n  giong {ten}   doan mau {rw.shape[-1]/rs:.2f}s   nfe {nfe}")
    print(f"  cau mau: {rt[:70]}\n")

    for sp in mucs:
        print(f"  ===== speed {sp:.2f} =====")
        manh, lap = [], 0
        bo = CAU + CAU_DAI
        for c in bo:
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
                y, sr, _ = next(infer_batch_process(
                    (rw, rs), rt, [c], svc._model, svc._vocoder,
                    mel_spec_type="vocos", progress=None, nfe_step=nfe, speed=sp,
                    device=svc._model.device))
            y = trim_silence(np.asarray(y), sr)
            t = nghe_lai(y, sr)
            l = lap_duoi(c, t)
            lap += bool(l)
            print(f"    {'LAP   ' if l else 'sach  '} {len(y)/sr:5.2f}s | {t[:56]}")
            if l:
                print(f"             ^ duoi lap: {l}")
            manh.append(y / max(1.0, float(np.abs(y).max())))
            manh.append(np.zeros(int(sr * NGHI), dtype=np.float32))
        p = RA / f"f5_thuan_sp{sp:.2f}.wav"
        sf.write(p, np.concatenate(manh), sr)
        print(f"    -> lap duoi {lap}/{len(bo)}   {p.name}\n")

    print(f"  wav o {RA}")


if __name__ == "__main__":
    main()
