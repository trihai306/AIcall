"""Ghep manh co tao ra hang loat NGAT HOI NHO khong - thu ma nguong 300ms bo qua.

Nguoi dung van nghe "ngat hoi co van de" sau khi moi phep do deu bao sach. Vi moi
phep do tu truoc toi gio deu dat nguong 250-300ms - hop ly cho "quang dung bia",
nhung MU voi thu khac han: ghep manh sinh rieng lai voi nhau tao ra mot vet noi o
MOI ranh gioi. Cat 5 tu thi 12 vet moi luot. Moi vet chi 50-150ms thi tung cai
khong bi bao, nhung dan lai la nghe ngat quang.

Do: cung mot doan van, sinh MOT LAN va sinh THEO MANH roi ghep. Dem quang lang o
NHIEU nguong, tu 40ms tro len. Ban sinh mot lan la moc - no cung co quang lang
(nhip nghi that cua tieng noi), nen chi phan CHENH LECH moi la do ghep manh.

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\do_ngat_hoi_vi_mo.py
"""
import asyncio
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import soundfile as sf          # noqa: E402

from backend.pipeline.text_chunker import nhip_nghi_sau, tach_manh    # noqa: E402
from backend.services.audio_utils import chen_lang_dau_wav            # noqa: E402
from backend.services.tts_service import F5TTSService                 # noqa: E402

RA = Path("C:/tmp/ngathoi")
NGUONG_IM, KHUNG = 0.015, 0.02
MUC = [40, 60, 80, 100, 150, 200, 300]

VAN = ("Dạ vâng ạ, với tình hình thu nhập của anh chị thì em có thể tư vấn hạn "
       "mức lên đến năm trăm triệu đồng, thời hạn vay linh hoạt từ mười hai đến "
       "sáu mươi tháng, và lãi suất áp dụng từ bảy phẩy chín phần trăm một năm "
       "tính trên dư nợ giảm dần ạ. Anh chị chuẩn bị giúp em chứng minh nhân "
       "dân, sổ hộ khẩu và sao kê lương ba tháng gần nhất thì bên em xử lý rất "
       "nhanh ạ.")


def lang_cac_muc(x, sr):
    n = max(1, int(sr * KHUNG))
    k = len(x) // n
    if k == 0:
        return {m: 0 for m in MUC}, []
    im = np.abs(x[: k * n].reshape(k, n)).max(axis=1) < NGUONG_IM
    ra, i = [], 0
    while i < k:
        if im[i]:
            j = i
            while j < k and im[j]:
                j += 1
            if i > 0 and j < k:                 # bo hai dau
                ra.append((j - i) * KHUNG * 1000)
            i = j
        else:
            i += 1
    return {m: sum(1 for d in ra if d >= m) for m in MUC}, ra


def cat(van):
    ra, dem = [], ""
    for t in van.split():
        dem += " " + t
        m, dem = tach_manh(dem, first_chunk=(not ra))
        if m:
            ra.append(m)
    if dem.strip():
        ra.append(dem.strip())
    return ra


def main():
    svc = F5TTSService()
    svc.load()
    ten = svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    RA.mkdir(parents=True, exist_ok=True)

    def sinh_bytes(t):
        return asyncio.run(svc.synthesize(t, voice=ten))

    def doc(b):
        x, sr = sf.read(io.BytesIO(b), dtype="float32")
        return (x.mean(axis=1) if x.ndim > 1 else x), sr

    manh_text = cat(VAN)
    print(f"\n  giọng {ten}   {len(VAN.split())} từ -> {len(manh_text)} mảnh"
          f" -> {len(manh_text)-1} vết nối\n")

    # --- sinh mot lan ------------------------------------------------------
    x1, sr = doc(sinh_bytes(VAN))
    d1, _ = lang_cac_muc(x1, sr)
    sf.write(RA / "mot_lan.wav", x1 / max(1.0, float(np.abs(x1).max())), sr)

    # --- sinh theo manh roi GHEP Y HET pipeline ----------------------------
    manh_wav, nghi = [], 0.0
    for c in manh_text:
        b = sinh_bytes(c)
        if nghi > 0:
            b = chen_lang_dau_wav(b, nghi)
        nghi = nhip_nghi_sau(c)
        y, sr = doc(b)
        manh_wav.append(y)
    x2 = np.concatenate(manh_wav)
    d2, ds2 = lang_cac_muc(x2, sr)
    sf.write(RA / "ghep_manh.wav", x2 / max(1.0, float(np.abs(x2).max())), sr)

    print(f"  {'ngưỡng':>8} {'sinh MỘT LẦN':>14} {'ghép mảnh':>11} {'chênh':>7}")
    print("  " + "-" * 48)
    for m in MUC:
        print(f"  {m:>5}ms {d1[m]:>13} {d2[m]:>11} {d2[m]-d1[m]:>+7}")
    print("  " + "-" * 48)
    print(f"\n  dài: {len(x1)/sr:.2f}s (một lần)  vs  {len(x2)/sr:.2f}s (ghép)")
    print(f"  tổng im lặng giữa: {sum(_ for _ in [0]) or 0:.0f}", end="")
    print(f"  {sum(d for d in ds2):.0f}ms trên bản ghép")
    print(f"\n  Chênh ở ngưỡng THẤP (40-100ms) mới là vết nối do ghép mảnh.")
    print(f"  Ngưỡng 300ms - thứ mọi phép đo trước dùng - bỏ qua hết đám đó.")
    print(f"\n  wav ở {RA}")


if __name__ == "__main__":
    main()
