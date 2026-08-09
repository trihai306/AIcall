"""Dung thu cach "sinh 5 tu mot, vua phat vua sinh tiep" roi so voi cach hien tai.

Y cua nguoi dung: cat that nho thi manh dau ra rat nhanh, va trong luc dang doc
manh nay thi may van sinh kip manh sau, nen khong the dut.

Script khong tranh luan - no DUNG ca hai cach tren cung mot doan van, mo phong
dung lich phat that, roi xuat wav de nghe.

Mo hinh phat (giong client that): manh sau noi duoi manh truoc.
    phat = max(luc_sinh_xong, luc_manh_truoc_phat_xong)
Dut khi luc_sinh_xong > luc_manh_truoc_phat_xong: het tieng de phat, loa im.

Do ca hai tinh huong:
    GPU ranh          - chi co TTS chay
    Ollama dang sinh  - dung thuc te, TTS cham 2.4 lan

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\thu_manh_5_tu.py
    .venv\\python.exe scripts\\thu_manh_5_tu.py --tu 3 5 8
"""
import argparse
import asyncio
import json
import re
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import soundfile as sf          # noqa: E402
import torch                    # noqa: E402

from backend.config import settings                                  # noqa: E402
from backend.pipeline.text_chunker import should_flush                # noqa: E402
from backend.services.tts_service import F5TTSService, trim_silence   # noqa: E402

OLLAMA = "http://127.0.0.1:11434/api/generate"
RA = Path("C:/tmp/manh5tu")
SR = 24000

VAN = ("Dạ vâng ạ, với tình hình thu nhập của anh chị thì em có thể tư vấn hạn mức "
       "lên đến năm trăm triệu đồng, thời hạn vay linh hoạt từ mười hai đến sáu mươi "
       "tháng, và lãi suất áp dụng từ bảy phẩy chín phần trăm một năm tính trên dư nợ "
       "giảm dần ạ. Anh chị chuẩn bị giúp em chứng minh nhân dân, sổ hộ khẩu và sao kê "
       "lương ba tháng gần nhất thì bên em xử lý rất nhanh ạ.")


def cat_theo_tu(van: str, n: int):
    tu = van.split()
    return [" ".join(tu[i:i+n]) for i in range(0, len(tu), n)]


def cat_hien_tai(van: str):
    """Dung DUNG luat cat cua pipeline dang chay."""
    ra, dem = [], ""
    for i, t in enumerate(van.split()):
        dem = (dem + " " + t).strip()
        if should_flush(dem, first_chunk=(not ra)):
            ra.append(dem)
            dem = ""
    if dem.strip():
        ra.append(dem.strip())
    return ra


def nhieu_ollama(dung: threading.Event):
    while not dung.is_set():
        try:
            b = json.dumps({"model": settings.ollama_model,
                            "prompt": "Viết một đoạn tư vấn vay tín chấp thật dài.",
                            "stream": True, "options": {"num_predict": 400}}).encode()
            r = urllib.request.Request(OLLAMA, data=b,
                                       headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(r, timeout=120) as resp:
                for _ in resp:
                    if dung.is_set():
                        return
        except Exception:
            return


def chay(svc, rw, rs, rt, sp, nfe, manh_text):
    """Sinh tuan tu, ghi lai luc sinh xong tung manh."""
    from f5_tts.infer.utils_infer import infer_batch_process
    ra, t0 = [], time.perf_counter()
    for c in manh_text:
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            y, sr, _ = next(infer_batch_process(
                (rw, rs), rt, [c], svc._model, svc._vocoder,
                mel_spec_type="vocos", progress=None, nfe_step=nfe, speed=sp,
                device=svc._model.device))
        y = trim_silence(np.asarray(y), sr)
        ra.append({"text": c, "xong": time.perf_counter() - t0,
                   "wav": y / max(1.0, float(np.abs(y).max())), "dai": len(y) / sr})
    return ra


def len_lich(manh):
    het = None
    for m in manh:
        if het is None:
            m["phat"], m["dut"] = m["xong"], 0.0
        else:
            m["dut"] = max(0.0, m["xong"] - het)
            m["phat"] = max(m["xong"], het)
        het = m["phat"] + m["dai"]
    return manh


def dung_wav(manh, p: Path):
    tong = max(m["phat"] + m["dai"] for m in manh) + 0.3
    out = np.zeros(int(tong * SR), dtype=np.float32)
    for m in manh:
        i = int(m["phat"] * SR)
        j = min(i + len(m["wav"]), len(out))
        out[i:j] += m["wav"][: j - i]
    d = float(np.abs(out).max())
    if d > 1.0:
        out /= d
    sf.write(p, out, SR)
    return tong


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tu", type=int, nargs="+", default=[5],
                    help="cat may tu mot manh")
    a = ap.parse_args()

    svc = F5TTSService()
    svc.load()
    ten = svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    rw, rs, rt = svc._voices[ten]
    sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step
    RA.mkdir(parents=True, exist_ok=True)

    cach = [(f"{n} từ một mảnh", cat_theo_tu(VAN, n)) for n in a.tu]
    cach.append(("cách hiện tại (cắt ở dấu câu)", cat_hien_tai(VAN)))

    print(f"\n  giọng {ten}   đoạn mẫu {rw.shape[-1]/rs:.2f}s   speed {sp:.2f}   nfe {nfe}")
    print(f"  văn bản {len(VAN.split())} từ\n")

    for nhan_gpu, co_nhieu in (("GPU rảnh", False), ("Ollama đang sinh", True)):
        dung = threading.Event()
        if co_nhieu:
            th = threading.Thread(target=nhieu_ollama, args=(dung,), daemon=True)
            th.start()
            time.sleep(4)
        print(f"  ===== {nhan_gpu} =====")
        print(f"      {'cách':<30} {'mảnh':>5} {'tiếng đầu':>11} {'tổng sinh':>10}"
              f" {'chỗ đứt':>8} {'im tổng':>9}")
        print("      " + "-" * 78)
        for nhan, texts in cach:
            m = len_lich(chay(svc, rw, rs, rt, sp, nfe, texts))
            dut = [x["dut"] for x in m if x["dut"] > 0.05]
            tag = "nhieu" if co_nhieu else "ranh"
            ten_tep = re.sub(r"\W+", "_", nhan) + f"_{tag}.wav"
            dung_wav(m, RA / ten_tep)
            print(f"      {nhan:<30} {len(m):>5} {m[0]['xong']*1000:>9.0f}ms"
                  f" {m[-1]['xong']:>9.2f}s {len(dut):>8} {sum(dut)*1000:>7.0f}ms")
        dung.set()
        time.sleep(2)
        print()

    print(f"  wav ở {RA}")
    print("\n  'tiếng đầu' = khách chờ bao lâu mới nghe được tiếng.")
    print("  'tổng sinh' = tổng thời gian máy phải làm việc cho cả đoạn.")
    print("  'chỗ đứt'   = số lần loa hết tiếng để phát, phải chờ mảnh sau.")


if __name__ == "__main__":
    main()
