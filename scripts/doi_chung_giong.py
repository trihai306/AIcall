"""Kiểm xem thước đo độ giống có PHÂN BIỆT được người khác nhau không.

Vì sao cần: MFCC cosine giữa hai đoạn tiếng nói bất kỳ thường đã 0.95+, vì nó bị
chi phối bởi độ nghiêng phổ chung của tiếng nói người. Nếu hai NGƯỜI KHÁC NHAU
cũng cho 0.977 thì con số 0.977 của F5 chẳng nói lên gì.

Script dựng ma trận: mỗi đoạn mẫu so với mọi đoạn mẫu khác, và với tiếng F5 sinh
ra từ chính nó. Đọc ma trận:
  - Nếu ô "tự sinh" CAO hơn hẳn các ô "người khác"  => F5 clone thật, thước đo tốt
  - Nếu chúng bằng nhau                              => F5 KHÔNG clone, hoặc thước đo mù

Chạy TRÊN MÁY WIN:
    .venv\\python.exe scripts\\doi_chung_giong.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import torch                    # noqa: E402
import librosa                  # noqa: E402

from backend.services.tts_service import F5TTSService, trim_silence  # noqa: E402

CAU = "Lãi suất vay tín chấp của bên em là từ bảy phẩy chín phần trăm một năm"
GIONG = ["giong_heu", "giong_nam", "fosd_1", "nam_moi1"]


def mfcc(x, sr):
    x = np.asarray(x, dtype=np.float32)
    if sr != 24000:
        x = librosa.resample(x, orig_sr=sr, target_sr=24000)
    return librosa.feature.mfcc(y=x, sr=24000, n_mfcc=20)[1:].mean(axis=1)


def cos(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def main():
    svc = F5TTSService()
    svc.load()
    from f5_tts.infer.utils_infer import infer_batch_process

    mau, sinh = {}, {}
    for g in GIONG:
        try:
            asyncio.run(svc.ensure_voice(g))
        except Exception as e:
            print(f"  bỏ qua {g}: {e}")
            continue
        rw, rs, rt = svc._voices[g]
        ref = rw.detach().cpu().numpy().squeeze() if torch.is_tensor(rw) else np.asarray(rw).squeeze()
        mau[g] = mfcc(ref, rs)
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            x, sr, _ = next(infer_batch_process(
                (rw, rs), rt, [CAU], svc._model, svc._vocoder,
                mel_spec_type="vocos", progress=None, nfe_step=32, speed=1.0,
                device=svc._model.device))
        sinh[g] = mfcc(trim_silence(np.asarray(x), sr), sr)

    ten = list(mau)
    w = max(len(t) for t in ten) + 2

    print("\n  MA TRẬN: đoạn mẫu (hàng) so với đoạn mẫu người khác (cột)")
    print("  " + " " * w + "".join(f"{t:>11}" for t in ten))
    for a in ten:
        print(f"  {a:<{w}}" + "".join(
            f"{'  --   ':>11}" if a == b else f"{cos(mau[a], mau[b]):>11.3f}"
            for b in ten))

    print("\n  MA TRẬN: đoạn mẫu (hàng) so với TIẾNG F5 SINH RA từ mỗi giọng (cột)")
    print("  " + " " * w + "".join(f"{t:>11}" for t in ten))
    for a in ten:
        print(f"  {a:<{w}}" + "".join(f"{cos(mau[a], sinh[b]):>11.3f}" for b in ten))

    print("\n  KẾT LUẬN")
    for a in ten:
        tu = cos(mau[a], sinh[a])
        khac_mau = [cos(mau[a], mau[b]) for b in ten if b != a]
        khac_sinh = [cos(mau[a], sinh[b]) for b in ten if b != a]
        cao_nhat = max(range(len(ten)), key=lambda i: cos(mau[a], sinh[ten[i]]))
        dung = ten[cao_nhat] == a
        print(f"  {a:<{w}} tự sinh {tu:.3f} | người khác (mẫu) {max(khac_mau):.3f}"
              f" | người khác (F5 sinh) {max(khac_sinh):.3f}"
              f" | {'KHỚP' if dung else 'LẪN sang ' + ten[cao_nhat]}")

    dung_het = all(
        max(range(len(ten)), key=lambda i: cos(mau[a], sinh[ten[i]])) == ten.index(a)
        for a in ten)
    print("\n  => Thước đo PHÂN BIỆT được: F5 clone đúng người." if dung_het else
          "\n  => Thước đo KHÔNG phân biệt được, hoặc F5 không clone đúng người.")


if __name__ == "__main__":
    main()
