"""Nghiem thu giong AI tren may Win. Xuat bao cao ASCII ra tep.

Vi sao ASCII: chuoi tieng Viet di qua PowerShell roi SSH bi hong dau o nhieu tang,
loc bang Select-String hay grep deu truot. Bao cao khong dau thi doc duoc o moi noi.

Gom hai phan:

  [1] Quet nfe -- sinh cau moi o tung muc nfe roi cho STT nghe lai.
      Do 08-09 phat hien: khong chi doan mau ngan moi sinh am rac, nfe thap
      cung sinh. Cung clip heu_c 5.45s: nfe32 sach 0/3 nhung nfe16 rac 5/5.

  [2] Soi 42 tep WAV cau dem DA DUNG tren dia -- day moi la thu khach nghe.
      Chung duoc dung theo nfe trong .env, nen neu nfe do ban thi rac da bi
      nuong san vao tep, chay lai bao nhieu lan cung the.

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\nghiem_thu_giong.py
    .venv\\python.exe scripts\\nghiem_thu_giong.py --nfe 16 24 32 --lan 5
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
from backend.services.filler_store import lay_kho                    # noqa: E402
from backend.services.tts_service import F5TTSService, trim_silence  # noqa: E402

STT = "http://127.0.0.1:8178/inference"
CAU = "Lãi suất vay tín chấp của bên em là từ bảy phẩy chín phần trăm một năm"
DAU = "lãi suất"
BAO_CAO = Path("C:/tmp/nghiem_thu.txt")

_ra = []


def in_ra(s: str = "") -> None:
    """In va ghi lai, bo dau de bao cao doc duoc qua moi tang encoding."""
    print(s)
    _ra.append(unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode())


class SttChet(RuntimeError):
    """May chu STT khong goi duoc.

    PHAI la ngoai le chu khong duoc tra ve chuoi loi: ban dau ham nay tra
    "[STT loi: ...]", chuoi do khong bat dau bang chu dau cua cau that nen bi
    dem thanh "co rac". Ket qua la bao cao 5/5 rac va 42/42 tep ban trong khi
    that ra chi la cong 8178 dang tat. Dung cu do hong ma van in ra so lieu la
    kieu sai nguy hiem nhat - thu gi khong do duoc thi phai dung han.
    """


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
    except Exception as e:
        raise SttChet(f"{STT} khong goi duoc: {e}") from e


def kiem_stt() -> None:
    """Goi thu STT bang 0.5s im lang truoc khi do bat cu thu gi."""
    try:
        nghe_lai(np.zeros(12000, dtype=np.float32), 24000)
    except SttChet as e:
        print(f"\n  DUNG: {e}")
        print("  Bat lai bang:")
        print("    powershell -File scripts\\start_services.ps1 -Detached")
        print("  roi doi den khi cong 8178 tra loi, rui chay lai script nay.\n")
        sys.exit(2)


def chuan(s: str) -> str:
    """Bo dau, bo dau cau, gom khoang trang - de so hai chuoi tieng Viet."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def co_rac_dau(goc: str, nghe: str) -> bool:
    """F5 co bia them chu o DAU khong.

    Khong so bang startswith: STT nghe chech tren cau ngan la chuyen thuong, va
    voi cau 3 am tiet nhu "da em ro" thi mot chu chech la truot ca chuoi. Do
    ngay lan dau bang startswith thi 4/42 tep bi bao "co rac" trong khi ca 4 chi
    la STT nghe lech: "da em ro" -> "em da", "tra giup" -> "trai giup". Bao
    nham 4 lan nhu the la du de nguoi ta thoi tin bo do.

    Cach dung: dem may chu O DAU ban chep lai KHONG he xuat hien trong cau that.
    F5 bia thi no bia han chu moi ("ca hieu ca nhan lai suat..."), con STT nghe
    chech thi chu van quanh quan trong cau.

    Nguong la 1 chu, da doi chieu voi cac ca THAT ghi duoc ngay 08-09:
        bia 4 chu : "ca hieu ca nhan | lai suat vay..."      -> la=4  bat
        bia 1 chu : "can | anh chi cho em xin it phut..."    -> la=1  bat
        STT chech : "da em ro" nghe thanh "em da"            -> la=0  bo qua
        STT chech : "tra giup" nghe thanh "trai giup"        -> la=0  bo qua
    Doi >=2 thi lot han ca "can"; con ca 4 ca STT nghe chech deu la=0 nen ha
    xuong 1 khong lam tang bao nham. Cai gay bao nham truoc do la startswith,
    khong phai nguong.
    """
    cg, ct = chuan(goc), chuan(nghe)
    if not ct:
        return False
    tu_goc = set(cg.split())
    la = 0
    for tu in ct.split():
        if tu in tu_goc:
            break
        la += 1
    return la >= 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nfe", type=int, nargs="+", default=[16, 20, 24, 32])
    ap.add_argument("--lan", type=int, default=5)
    ap.add_argument("--giong", default=None)
    a = ap.parse_args()

    kiem_stt()   # truoc khi nap model - hong dung cu do thi dung ngay, dung do
    svc = F5TTSService()
    svc.load()
    ten = a.giong or svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    rw, rs, rt = svc._voices[ten]
    from f5_tts.infer.utils_infer import infer_batch_process

    in_ra("=" * 68)
    in_ra("NGHIEM THU GIONG AI")
    in_ra("=" * 68)
    in_ra(f"giong        : {ten}")
    in_ra(f"doan mau     : {rw.shape[-1]/rs:.2f}s")
    in_ra(f"toc do       : {svc.toc_do_cua(ten):.2f}")
    in_ra(f"nfe trong env: {settings.f5tts_nfe_step}")
    in_ra()

    # ---- [1] quet nfe ----------------------------------------------------
    in_ra("[1] QUET NFE - sinh cau moi roi cho STT nghe lai")
    in_ra()
    in_ra(f"    {'nfe':>4} {'am rac':>9} {'vuot tran':>11}   ket qua")
    in_ra("    " + "-" * 50)
    bang = []
    for n in a.nfe:
        rac = tran = 0
        for _ in range(a.lan):
            with torch.inference_mode():
                x, sr, _ = next(infer_batch_process(
                    (rw, rs), rt, [CAU], svc._model, svc._vocoder,
                    mel_spec_type="vocos", progress=None, nfe_step=n,
                    speed=svc.toc_do_cua(ten), device=svc._model.device))
            x = np.asarray(x)
            tran += float(np.abs(x).max()) > 1.0
            rac += not nghe_lai(trim_silence(x, sr), sr).lower().startswith(DAU)
        bang.append((n, rac, tran))
        ok = "SACH" if rac == 0 and tran == 0 else "BAN"
        in_ra(f"    {n:>4} {rac:>6}/{a.lan} {tran:>8}/{a.lan}   {ok}")
    in_ra()
    sach = [n for n, r, t in bang if r == 0 and t == 0]
    if sach:
        in_ra(f"    -> nfe thap nhat con SACH: {min(sach)}")
    else:
        in_ra("    -> KHONG muc nfe nao sach. Van de nam o doan mau, khong o nfe.")
    in_ra()

    # ---- [2] soi cac tep cau dem da dung --------------------------------
    in_ra("[2] SOI 42 TEP CAU DEM DA DUNG TREN DIA - day la thu khach nghe")
    in_ra()
    thu_muc = Path("data/fillers_wav") / ten
    teps = sorted(thu_muc.glob("*.wav"))
    if not teps:
        in_ra(f"    KHONG thay tep nao trong {thu_muc}")
    else:
        theo_id = {c.id: c.text for c in lay_kho().duoi}
        ban, tong = [], 0
        for p in teps:
            cau_id = p.name.split("__")[0]
            goc = theo_id.get(cau_id)
            if goc is None:
                continue
            tong += 1
            x, sr = sf.read(p)
            if x.ndim > 1:
                x = x.mean(axis=1)
            t = nghe_lai(np.asarray(x, dtype=np.float32), sr)
            if co_rac_dau(goc, t):
                ban.append((cau_id, goc, t))
        in_ra(f"    tong cong    : {tong} tep")
        in_ra(f"    nghi co rac  : {len(ban)} tep")
        in_ra()
        for cau_id, goc, t in ban[:12]:
            in_ra(f"      {cau_id}")
            in_ra(f"        goc : {chuan(goc)[:58]}")
            in_ra(f"        nghe: {chuan(t)[:58]}")
        if len(ban) > 12:
            in_ra(f"      ... con {len(ban)-12} tep nua")
        in_ra()
        in_ra("    -> DAT" if not ban else
              f"    -> CHUA DAT: {len(ban)}/{tong} tep cau dem co chu la o dau")

    in_ra()
    in_ra("=" * 68)
    BAO_CAO.parent.mkdir(parents=True, exist_ok=True)
    BAO_CAO.write_text("\n".join(_ra), encoding="ascii", errors="ignore")
    print(f"\n  bao cao: {BAO_CAO}")


if __name__ == "__main__":
    main()
