"""Do TTS cham di bao nhieu khi Ollama DANG sinh token - va model nao lam te nhat.

Vi sao: TTS consumer chay SONG SONG voi LLM streaming (streaming_pipeline.py).
Manh 1 dang phat thi manh 2 duoc sinh, nhung luc do Ollama van dang nha token va
hai ben dung chung mot GPU. Manh 1 phat het ma manh 2 chua xong => DUT GIUA CAU.
Nam truoc ca khau phat nen CA web lan dien thoai deu dinh.

Script tra loi ba cau:
  1. TTS mat bao lau khi GPU RANH
  2. TTS mat bao lau khi Ollama DANG sinh
  3. Model nao lam chenh lech nhieu hon (7b vs ban 1.9GB)

Va quan trong nhat: so thoi gian sinh manh voi DO DAI TIENG cua manh truoc.
Sinh lau hon tieng dang phat = chac chan dut.

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\do_tranh_gpu.py
    .venv\\python.exe scripts\\do_tranh_gpu.py --model qwen2.5:7b tuvan-qwen-hoithoai:latest
"""
import argparse
import json
import statistics as st
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import torch                    # noqa: E402

from backend.config import settings                                  # noqa: E402
from backend.services.tts_service import F5TTSService, trim_silence  # noqa: E402

OLLAMA = "http://127.0.0.1:11434/api/generate"
# Cau dai vua phai - dung do dai manh that ma pipeline cat ra.
CAU = "Lãi suất bên em đang là từ bảy phẩy chín phần trăm một năm ạ."
NHAC = ("Hãy viết một đoạn tư vấn dài về vay tín chấp, càng chi tiết càng tốt, "
        "nêu đủ điều kiện hồ sơ thủ tục và các lưu ý.")


def sinh_lien_tuc(model: str, dung: threading.Event) -> None:
    """Bat Ollama nha token lien tuc cho toi khi duoc bao dung."""
    while not dung.is_set():
        try:
            b = json.dumps({"model": model, "prompt": NHAC, "stream": True,
                            "options": {"num_predict": 400}}).encode()
            r = urllib.request.Request(OLLAMA, data=b,
                                       headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(r, timeout=120) as resp:
                for _ in resp:            # doc tung dong de Ollama sinh that
                    if dung.is_set():
                        return
        except Exception:
            return


def do_tts(svc, rw, rs, rt, sp, nfe, lan):
    from f5_tts.infer.utils_infer import infer_batch_process
    ms, giay = [], []
    for _ in range(lan):
        t0 = time.perf_counter()
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            y, sr, _ = next(infer_batch_process(
                (rw, rs), rt, [CAU], svc._model, svc._vocoder,
                mel_spec_type="vocos", progress=None, nfe_step=nfe, speed=sp,
                device=svc._model.device))
        ms.append((time.perf_counter() - t0) * 1000)
        giay.append(len(trim_silence(np.asarray(y), sr)) / sr)
    return st.median(ms), st.median(giay)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", nargs="+",
                    default=["qwen2.5:7b", "tuvan-qwen-hoithoai:latest"])
    ap.add_argument("--lan", type=int, default=5)
    a = ap.parse_args()

    svc = F5TTSService()
    svc.load()
    ten = svc.default_voice_name()
    import asyncio
    asyncio.run(svc.ensure_voice(ten))
    rw, rs, rt = svc._voices[ten]
    sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step

    do_tts(svc, rw, rs, rt, sp, nfe, 2)          # ham nong torch.compile
    ranh_ms, dai_giay = do_tts(svc, rw, rs, rt, sp, nfe, a.lan)

    print(f"\n  giong {ten}   nfe {nfe}   speed {sp:.2f}")
    print(f"  cau thu dai {dai_giay:.2f}s tieng\n")
    print(f"  {'tinh huong':<34} {'TTS':>9} {'so voi ranh':>13} {'du/thieu':>11}")
    print("  " + "-" * 72)
    print(f"  {'GPU ranh (khong ai dung)':<34} {ranh_ms:>7.0f}ms {'1.00x':>13}"
          f" {dai_giay*1000 - ranh_ms:>+9.0f}ms")

    for m in a.model:
        dung = threading.Event()
        th = threading.Thread(target=sinh_lien_tuc, args=(m, dung), daemon=True)
        th.start()
        time.sleep(4)                             # doi Ollama nap model va chay deu
        ban_ms, _ = do_tts(svc, rw, rs, rt, sp, nfe, a.lan)
        dung.set()
        th.join(timeout=10)
        time.sleep(2)
        du = dai_giay * 1000 - ban_ms
        print(f"  {'Ollama ' + m + ' dang sinh':<34} {ban_ms:>7.0f}ms"
              f" {ban_ms/ranh_ms:>12.2f}x {du:>+9.0f}ms")

    print("  " + "-" * 72)
    print("\n  Cot 'du/thieu' = do dai tieng cua manh TRU thoi gian sinh manh ke tiep.")
    print("  Am  => manh sau chua kip xong luc manh truoc phat het => DUT GIUA CAU.")
    print("  Duong nho => vua du, chi can mang tre mot chut la dut.")


if __name__ == "__main__":
    main()
