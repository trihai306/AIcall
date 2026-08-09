"""Thu cach chua thang: CAT BO quang lang bia ra, thay vi tim cach ngan F5 bia.

Da duoi nguyen nhan qua nam gia thuyet va sai ca nam (nfe, checkpoint, dau gach,
do dai van ban, kich thuoc manh). Cat manh 5 tu ha duoc 19 -> 9 quang nhung
khong het. Cach nay khong can biet vi sao F5 bia: no soi tieng SAU KHI sinh roi
bop ngan quang lang qua dai.

Vi sao co the phan biet duoc quang that voi quang bia:
    F5 nghi o dau phay : do duoc toi da 220ms  (scripts/do_nghi_dau_phay.py)
    quang bia          : 300 - 1600ms          (do tren ban ghi hoi thoai that)
Hai vung KHONG chong nhau. Nen mot nguong o giua tach duoc sach.

Khong xoa han quang lang - bop ve `giu_ms`. Xoa han thi hai tu dinh sat nhau
nghe hut hoi, nhat la o cho von co dau phay.

Script do trung thuc: cho STT nghe lai CA HAI ban roi so ban chep. Bop nham vao
tieng noi thi ban chep se rung chu.

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\thu_cat_lang_giua.py
    .venv\\python.exe scripts\\thu_cat_lang_giua.py --nguong 260 --giu 190
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
RA = Path("C:/tmp/catlang")
NGUONG_IM, KHUNG = 0.015, 0.02

# Cau DAI, nhieu ve, nhieu dau phay - dung dang lam F5 bia nhat.
CAU = [
    "Được ạ, với vay tín chấp thì anh cần là công dân Việt Nam từ hai mươi hai đến "
    "sáu mươi tuổi, có thu nhập ổn định từ năm triệu đồng một tháng trở lên, có hợp "
    "đồng lao động còn hiệu lực và không có nợ xấu tại các tổ chức tín dụng ạ.",
    "Anh chị chuẩn bị giúp em chứng minh nhân dân hoặc căn cước công dân, sổ hộ khẩu "
    "hoặc giấy tạm trú, sao kê lương ba tháng gần nhất và hợp đồng lao động, để hồ sơ "
    "đầy đủ thì bên em xử lý nhanh hơn nhiều ạ.",
    "Sau khi anh chị nộp đủ hồ sơ thì bên em thẩm định trong vòng một ngày làm việc, "
    "phê duyệt xong là giải ngân ngay trong hai mươi bốn giờ, tiền chuyển thẳng vào "
    "tài khoản anh chị đăng ký ạ.",
    "Dạ vâng ạ, với tình hình thu nhập của anh chị thì em có thể tư vấn hạn mức lên "
    "đến năm trăm triệu đồng, thời hạn vay linh hoạt từ mười hai đến sáu mươi tháng ạ.",
]


def chuan(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


def nghe_lai(x, sr):
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


def _khung_im(x, sr):
    n = max(1, int(sr * KHUNG))
    k = len(x) // n
    to = np.array([np.abs(x[i*n:(i+1)*n]).max() for i in range(k)])
    return to < NGUONG_IM, n, k


def do_lang(x, sr, toi_thieu_ms=250):
    im, n, k = _khung_im(x, sr)
    ra, i = [], 0
    while i < k:
        if im[i]:
            j = i
            while j < k and im[j]:
                j += 1
            if i > 0 and j < k and (j - i) * KHUNG * 1000 >= toi_thieu_ms:
                ra.append((j - i) * KHUNG * 1000)
            i = j
        else:
            i += 1
    return ra


def cat_lang_giua(x, sr, nguong_ms=260.0, giu_ms=190.0):
    """Bóp mọi quãng lặng GIỮA tiếng dài quá `nguong_ms` xuống còn `giu_ms`.

    Chỉ đụng vào quãng nằm giữa, không đụng hai đầu - hai đầu là việc của
    `trim_silence`, và nhịp nghỉ nối mảnh do `chen_lang_dau_wav` lo.
    """
    im, n, k = _khung_im(x, sr)
    if k == 0:
        return x
    giu_khung = max(1, int(giu_ms / (KHUNG * 1000)))
    doan, i = [], 0
    while i < k:
        if im[i]:
            j = i
            while j < k and im[j]:
                j += 1
            dai_ms = (j - i) * KHUNG * 1000
            if i > 0 and j < k and dai_ms > nguong_ms:
                doan.append(x[i*n:(i + giu_khung)*n])     # bóp ngắn lại
            else:
                doan.append(x[i*n:j*n])                   # giữ nguyên
            i = j
        else:
            j = i
            while j < k and not im[j]:
                j += 1
            doan.append(x[i*n:j*n])
            i = j
    doan.append(x[k*n:])          # phần lẻ cuối
    return np.concatenate(doan) if doan else x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nguong", type=float, default=260.0)
    ap.add_argument("--giu", type=float, default=190.0)
    ap.add_argument("--lan", type=int, default=4)
    a = ap.parse_args()

    svc = F5TTSService()
    svc.load()
    ten = svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    rw, rs, rt = svc._voices[ten]
    sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step
    from f5_tts.infer.utils_infer import infer_batch_process
    RA.mkdir(parents=True, exist_ok=True)

    print(f"\n  giọng {ten}   speed {sp:.2f}   nfe {nfe}")
    print(f"  bóp quãng > {a.nguong:.0f}ms xuống {a.giu:.0f}ms\n")
    print(f"  {'câu':>4} {'trước':>16} {'sau':>10} {'giây':>14}  chữ có rụng không")
    print("  " + "-" * 74)

    t_lang, s_lang, rung, tong = 0, 0, 0, 0
    for i, c in enumerate(CAU * a.lan, 1):
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            y, sr, _ = next(infer_batch_process(
                (rw, rs), rt, [c], svc._model, svc._vocoder,
                mel_spec_type="vocos", progress=None, nfe_step=nfe, speed=sp,
                device=svc._model.device))
        y = trim_silence(np.asarray(y), sr)
        z = cat_lang_giua(y, sr, a.nguong, a.giu)
        lt, ls = do_lang(y, sr), do_lang(z, sr)
        t_lang += len(lt); s_lang += len(ls); tong += 1

        a_truoc, a_sau = chuan(nghe_lai(y, sr)), chuan(nghe_lai(z, sr))
        khac = a_truoc != a_sau
        rung += khac
        print(f"  {i:>4} {len(lt):>3} quãng {sum(lt):>6.0f}ms {len(ls):>3} quãng"
              f" {len(y)/sr:>6.2f}->{len(z)/sr:<5.2f}s  {'KHÁC' if khac else 'giống hệt'}")
        if khac:
            print(f"        trước: {a_truoc[:60]}")
            print(f"        sau  : {a_sau[:60]}")
        if i <= 2:
            sf.write(RA / f"cau{i}_truoc.wav", y / max(1.0, float(np.abs(y).max())), sr)
            sf.write(RA / f"cau{i}_sau.wav", z / max(1.0, float(np.abs(z).max())), sr)

    print("  " + "-" * 74)
    print(f"\n  quãng lặng > 250ms : {t_lang} -> {s_lang}")
    print(f"  bản chép đổi        : {rung}/{tong}"
          f"{'   <== BÓP NHẦM VÀO TIẾNG NÓI' if rung else '   (không rụng chữ nào)'}")
    print(f"\n  wav ở {RA}")


if __name__ == "__main__":
    main()
