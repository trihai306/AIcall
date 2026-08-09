"""Dựng bản giữ ĐÚNG NHỊP của A nhưng dùng clip mẫu sạch, và soi lại demo A.

Bối cảnh: anh nghe A/B xong bảo "A ổn". Nhưng A (giong_heu clip 2.21s, speed
0.64) đo được 3/3 lượt có âm rác ở đầu và 2/3 vượt trần biên độ.

Nhịp A phát ra là ~180 âm tiết/phút. Clip heu_c (5.4s, sạch 0/3) ở speed 0.90
cho 206. Muốn về 180 thì cần speed ~0.79. Khi đó heu_c chạy ở 85% nhịp thật của
người đó, vẫn hơn hẳn A (61%) — vì trong clip đó chính người ấy đã nói chậm sẵn.

Script: (1) cho STT nghe lại từng câu trong demo A để đếm rác thật,
        (2) dựng bản C cùng câu, nhịp ~180, bằng clip heu_c.

Chạy TRÊN MÁY WIN:
    .venv\\python.exe scripts\\giu_nhip_a.py
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

from backend.services.tts_service import F5TTSService, trim_silence  # noqa: E402

CAU = [
    "Dạ em chào anh chị, em gọi từ ngân hàng để tư vấn về khoản vay tín chấp ạ.",
    "Lãi suất bên em đang là từ bảy phẩy chín phần trăm một năm, tính trên dư nợ giảm dần.",
    "Hạn mức tối đa là năm trăm triệu, thời hạn vay lên tới sáu mươi tháng.",
    "Anh chị cho em xin ít phút để em tư vấn kỹ hơn được không ạ?",
]
DAU = ["dạ em chào", "lãi suất", "hạn mức", "anh chị cho em"]
STT = "http://127.0.0.1:8178/inference"
RA = Path("C:/tmp/nghethu")
NGHI = 0.35
SPEED_C = 0.79


def am_tiet(s):
    return len([t for t in re.split(r"\s+", s.strip()) if re.search(r"\w", t)])


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
    try:
        return json.loads(urllib.request.urlopen(r, timeout=180).read()).get("text", "").strip()
    except Exception as e:
        return f"[STT lỗi: {e}]"


def main():
    svc = F5TTSService()
    svc.load()
    from f5_tts.infer.utils_infer import infer_batch_process

    RA.mkdir(parents=True, exist_ok=True)

    # --- (1) soi lai demo A: clip CU nam o ban sao lưu -----------------------
    bak = Path("models/tts/ref_voices/giong_heu.wav.bak-20260809")
    print("\n  [1] SOI LẠI BẢN A (clip 2.21s, speed 0.64) — cho STT nghe lại từng câu\n")
    if bak.exists():
        import torchaudio
        w, s = torchaudio.load(str(bak))
        rt_bak = Path("models/tts/ref_voices/giong_heu.txt.bak-20260809").read_text(encoding="utf-8").strip()
        w = w.to(svc._model.device)
        rac = tran = 0
        for c, d in zip(CAU, DAU):
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
                y, sr, _ = next(infer_batch_process(
                    (w, s), rt_bak, [c], svc._model, svc._vocoder,
                    mel_spec_type="vocos", progress=None, nfe_step=32, speed=0.64,
                    device=svc._model.device))
            y = np.asarray(y)
            dinh = float(np.abs(y).max())
            t = nghe_lai(trim_silence(y, sr), sr).lower()
            co = not t.startswith(d)
            rac += co
            tran += dinh > 1.0
            print(f"      {'CÓ RÁC' if co else 'sạch  '} | đỉnh {dinh:.2f} | {t[:60]}")
        print(f"\n      âm rác {rac}/{len(CAU)}   vượt trần {tran}/{len(CAU)}")
    else:
        print("      không thấy bản sao lưu, bỏ qua")

    # --- (2) dung ban C: nhip cua A, clip sach ------------------------------
    print(f"\n  [2] DỰNG BẢN C — clip heu_c 5.4s, speed {SPEED_C} (nhắm ~180 âm tiết/phút)\n")
    asyncio.run(svc.ensure_voice("heu_c"))
    rw, rs, rt = svc._voices["heu_c"]
    manh, tong_at, tong_giay, rac, tran = [], 0, 0.0, 0, 0
    for c, d in zip(CAU, DAU):
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            y, sr, _ = next(infer_batch_process(
                (rw, rs), rt, [c], svc._model, svc._vocoder,
                mel_spec_type="vocos", progress=None, nfe_step=32, speed=SPEED_C,
                device=svc._model.device))
        y = np.asarray(y)
        tran += float(np.abs(y).max()) > 1.0
        y = trim_silence(y, sr)
        t = nghe_lai(y, sr).lower()
        co = not t.startswith(d)
        rac += co
        tong_at += am_tiet(c)
        tong_giay += len(y) / sr
        print(f"      {'CÓ RÁC' if co else 'sạch  '} | {t[:60]}")
        manh.append(y / max(1.0, float(np.abs(y).max())))
        manh.append(np.zeros(int(sr * NGHI), dtype=np.float32))

    x = np.concatenate(manh)
    p = RA / f"C_nhip_cua_A_heu_c_sp{SPEED_C:.2f}.wav"
    sf.write(p, x, sr)
    nhip = tong_at / tong_giay * 60
    print(f"\n      âm rác {rac}/{len(CAU)}   vượt trần {tran}/{len(CAU)}")
    print(f"      nhịp ra {nhip:.0f} âm tiết/phút   (A là ~180)")
    print(f"      -> {p}")


if __name__ == "__main__":
    main()
