"""Vi sao manh CANG TO thi doc cang gian, cang lap tu, cang tu ngat quang?

Chi DO, khong sua gi. Do dung ba trieu chung nguoi dung bao:
  1. doc bi cach ra du KHONG co dau cham/phay  -> dem quang lang GIUA manh
  2. doan sau doc gian hon doan truoc          -> nhip am tiet/phut theo co manh
  3. lap tu / doc sai tu                       -> cho STT nghe lai roi doi chieu

Nghi van dang kiem: `thoi_luong_ep` cap thoi luong = am_tiet * nhip * 1.11.
He so 1.11 la NHAN, nen thoi gian thua tang tuyen tinh theo do dai manh. Ma
chinh docstring cua `cat_lang_bia` da do: cap cang nhieu thoi luong thi F5 chen
cang nhieu nghi (0% o he so 0.85, 2% o 1.11, 5% o 1.25). Neu dung, manh 20 tu
phai thua gap 4 lan manh 5 tu ve TUYET DOI.

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\chan_doan_manh_dai.py
    .venv\\python.exe scripts\\chan_doan_manh_dai.py --tu 5 10 20 --lan 2
"""
import argparse
import asyncio
import difflib
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

from backend.config import settings                        # noqa: E402
from backend.pipeline.text_normalizer import normalize_for_tts   # noqa: E402
from backend.services.tts_service import (                 # noqa: E402
    F5TTSService, bo_dau_cau_cho_f5, cat_lang_bia, so_am_tiet,
    thoi_luong_ep, trim_silence)

STT = "http://127.0.0.1:8178/inference"
KHUNG_MS = 20.0

# Van ban that, CO dau cau - de xem cho ngat cau co duoc nghi khong.
VAN = ("Dạ vâng ạ, bên em đang có chương trình vay tín chấp, anh không cần thế "
       "chấp gì hết. Lãi suất hiện tại từ bảy phẩy chín phần trăm một năm, cố "
       "định suốt kỳ vay chứ không thả nổi. Hạn mức cao nhất là năm trăm triệu, "
       "thời hạn thì anh chọn từ mười hai đến sáu mươi tháng. Điều kiện đơn "
       "giản thôi ạ, anh có thu nhập ổn định từ năm triệu một tháng trở lên là "
       "được rồi.")


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


def _rms_khung(x, sr):
    n = max(1, int(sr * KHUNG_MS / 1000))
    k = len(x) // n
    if k < 1:
        return np.zeros(0)
    kh = x[: k * n].reshape(k, n).astype(np.float64)
    return np.sqrt((kh * kh).mean(axis=1))


def quang_lang_giua(x, sr, nguong_ms):
    """(so quang, tong ms) cac quang lang GIUA manh dai qua nguong_ms.

    Dung dung dinh nghia cua `cat_lang_bia`: RMS < 20% dinh, va phai co khung
    cham day 7% - de khong dem nham cho trung giua hai am tiet.
    """
    rms = _rms_khung(x, sr)
    if len(rms) < 3:
        return 0, 0.0
    dinh = float(rms.max())
    im = rms < dinh * 0.20
    day = dinh * 0.07
    so, tong, i, k = 0, 0.0, 0, len(rms)
    while i < k:
        j = i
        while j < k and im[j] == im[i]:
            j += 1
        dai = (j - i) * KHUNG_MS
        if im[i] and i > 0 and j < k and dai > nguong_ms and float(rms[i:j].min()) < day:
            so += 1
            tong += dai
        i = j
    return so, tong


def giay_co_tieng(x, sr):
    rms = _rms_khung(x, sr)
    if len(rms) == 0:
        return len(x) / sr
    return float((rms >= max(float(rms.max()) * 0.07, 0.005)).sum() * KHUNG_MS / 1000)


def _tu(s):
    return [t for t in re.split(r"\W+", s.lower()) if t]


def doi_chieu(goc: str, nghe: str):
    """(so tu lap, so tu sai) khi so ban nghe lai voi ban goc."""
    a, b = _tu(goc), _tu(nghe)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    lap = sai = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        them = b[j1:j2]
        bo = a[i1:i2]
        # "lap tu" = chu thua ma chinh no vua xuat hien ngay truoc do
        for t in them:
            truoc = b[max(0, j1 - 2):j1]
            if t in truoc or t in bo:
                lap += 1
            else:
                sai += 1
        sai += max(0, len(bo) - len(them))
    return lap, sai


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tu", type=int, nargs="+", default=[5, 10, 20])
    ap.add_argument("--lan", type=int, default=1)
    ap.add_argument("--he-so", type=float, nargs="+", default=None,
                    help="Quét HE_SO_BU_LANG thay vì quét cỡ mảnh")
    ap.add_argument("--giu-dau", action="store_true",
                    help="KHÔNG bỏ dấu câu trước khi đưa vào F5")
    ap.add_argument("--nguong-lang", type=float, default=None,
                    help="Ép NGUONG_LANG_BIA_MS khác (mặc định 360)")
    ap.add_argument("--giu-lang", type=float, default=None,
                    help="Ép GIU_LANG_MS khác (mặc định 200)")
    a = ap.parse_args()

    svc = F5TTSService()
    svc.load()
    ten = svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    rw, rs, _ = svc._voices[ten]
    dai_ref = rw.shape[-1] / rs
    sp = svc.toc_do_cua(ten)

    tu = VAN.split()
    print(f"\n  giọng {ten}   speed {sp:.2f}   nfe {settings.f5tts_nfe_step}"
          f"   ref {dai_ref:.2f}s   văn bản {len(tu)} từ\n")
    nhan = "hệ số" if a.he_so else "cắt"
    print(f"  {nhan:>7} {'mảnh':>5} {'thừa':>6} {'THÔ ≥360':>9} {'THÔ ≥200':>9}"
          f" {'SAU ≥150':>9} {'dài':>7} {'nhịp':>5} {'thô':>5} {'lắp':>4} {'sai':>4}")
    print("  " + "-" * 84)

    import backend.services.tts_service as mod
    goc_he_so = mod.HE_SO_BU_LANG
    if a.giu_dau:
        mod.bo_dau_cau_cho_f5 = lambda t: t
        print("  [giữ nguyên dấu câu khi đưa vào F5]\n")
    vong = a.he_so if a.he_so else a.tu

    for v in vong:
        if a.he_so:
            mod.HE_SO_BU_LANG = v
            n = a.tu[-1]
        else:
            mod.HE_SO_BU_LANG = goc_he_so
            n = v
        manh = [" ".join(tu[i:i + n]) for i in range(0, len(tu), n)]
        c_cap = c_noi = 0.0
        s360 = s200 = 0
        m360 = m200 = 0.0
        sau200, msau200 = 0, 0.0
        dai_sau = 0.0
        nhips, lap_t, sai_t = [], 0, 0
        for _ in range(a.lan):
            for c in manh:
                chu = mod.bo_dau_cau_cho_f5(normalize_for_tts(c))
                cap = thoi_luong_ep(chu, dai_ref, sp)
                y, sr = svc._synthesize_sync(c, ten)   # RAW, chua cat gi
                # phan SINH RA = tong - doan mau
                cap_gen = (cap - dai_ref) if cap else float("nan")
                noi = giay_co_tieng(y, sr)
                q3, t3 = quang_lang_giua(y, sr, 360.0)
                q2, t2 = quang_lang_giua(y, sr, 200.0)
                c_cap += cap_gen if cap else 0.0
                c_noi += noi
                s360 += q3
                m360 += t3
                s200 += q2
                m200 += t2
                z = cat_lang_bia(
                    trim_silence(y, sr), sr,
                    nguong_ms=(a.nguong_lang if a.nguong_lang
                               else mod.NGUONG_LANG_BIA_MS),
                    giu_ms=(a.giu_lang if a.giu_lang else mod.GIU_LANG_MS))
                # 150ms chứ không 200: `cat_lang_bia` bóp quãng bịa xuống ĐÚNG
                # 200ms, đo ở ngưỡng 200 thì chính cái nó vừa để lại không được
                # đếm - mà lỗ 200ms nằm giữa cụm từ thì tai vẫn nghe ra.
                q2s, t2s = quang_lang_giua(z, sr, 150.0)
                sau200 += q2s
                msau200 += t2s
                dai_sau += len(z) / sr
                nghe = nghe_lai(z, sr)
                at = len(_tu(nghe))
                ct = giay_co_tieng(z, sr)
                if at >= 2 and ct > 0.2:
                    nhips.append(at / ct * 60)
                l, s = doi_chieu(chu, nghe)
                lap_t += l
                sai_t += s
        thua = (c_cap - c_noi) / c_noi * 100 if c_noi else 0
        tv = float(np.median(nhips)) if nhips else 0
        # Nhịp THÔ = tính trên CẢ chiều dài phát ra (kể cả quãng nghỉ) - đây mới
        # là tốc độ tai nghe được. `nhịp` chỉ là tốc độ phát âm.
        tho = (so_am_tiet(" ".join(manh)) * a.lan / dai_sau * 60) if dai_sau else 0
        nhan_hang = f"{v:>6.2f}" if a.he_so else f"{n:>4} từ"
        print(f"  {nhan_hang:>7} {len(manh):>5} {thua:>5.0f}%"
              f" {s360:>3}/{m360:>4.0f}ms {s200:>3}/{m200:>4.0f}ms"
              f" {sau200:>3}/{msau200:>4.0f}ms {dai_sau:>6.2f}s"
              f" {tv:>5.0f} {tho:>5.0f} {lap_t:>4} {sai_t:>4}")

    mod.HE_SO_BU_LANG = goc_he_so
    print("  " + "-" * 84)
    print("  thừa = fix_duration cấp dư bao nhiêu % so với phần thực sự có tiếng.")
    print("  THÔ  = quãng lặng GIỮA mảnh trên bản chưa xử lý (F5 tự bịa ra).")
    print("  SAU  = quãng lặng còn sót lại SAU trim_silence + cat_lang_bia.")
    print("  dài  = tổng giây phát ra thật sự (cái khách phải ngồi nghe).")
    print("  nhịp = âm tiết/phút tính trên phần CÓ TIẾNG (tốc độ phát âm).")
    print("  thô  = âm tiết/phút tính trên CẢ chiều dài (tốc độ tai nghe được).")
    print("  Mốc so sánh: đoạn mẫu của chính giọng đó = 247 âm tiết/phút.\n")


if __name__ == "__main__":
    main()
