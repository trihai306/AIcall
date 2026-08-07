"""Quét giọng mẫu và số bước khuếch tán, chấm bằng HNR sau khi qua AMR-NB.

Trả lời câu hỏi: làm sao cho HNR của F5 gần với người thật?

Đo được cho tới lúc này:

    giọng mẫu (người thật)   7.03 dB
    đầu ra F5                6.17 dB
    AMR-NB lấy đi             0.05 dB

Nghĩa là toàn bộ khoảng cách sinh ra ở khâu tổng hợp, không phải ở mạng. Nên chỗ
cần thử là tham số tổng hợp, và giờ thử được ngoại tuyến - không phải gọi lần nào.

Mỗi cấu hình đọc cùng một câu, cho qua AMR-NB rồi chấm. Trần lý thuyết là HNR của
chính giọng mẫu: F5 không thể sạch hơn thứ nó bắt chước.

    python scripts/quet_giong.py
    python scripts/quet_giong.py --nfe 12 24 --lan 2
"""

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mo_phong_amr import RA, doc_wav, hnr, qua_amr  # noqa: E402

CAU = ("Dạ em chào anh chị ạ. Em là nhân viên tư vấn của ngân hàng. "
       "Anh chị có cần em hỗ trợ thông tin gì không ạ?")


def cham_file(p: Path, ten: str) -> tuple[float, float]:
    """Trả (HNR trước AMR, HNR sau AMR), cả hai đo ở 8kHz cho so được với nhau."""
    g8 = RA / f"{ten}_8k.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(p),
                    "-ar", "8000", "-ac", "1", str(g8)],
                   capture_output=True, timeout=180)
    x, _ = doc_wav(g8)
    y, _ = doc_wav(qua_amr(g8, RA / f"{ten}_amr.wav"))
    return hnr(x, 8000), hnr(y, 8000)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nfe", type=int, nargs="+", default=[12, 16, 24, 32])
    ap.add_argument("--lan", type=int, default=1, help="mỗi cấu hình đọc mấy lần")
    a = ap.parse_args()

    from backend.config import settings
    from backend.services.tts_service import F5TTSService

    kho = PROJECT / "models" / "tts" / "ref_voices"
    giong = sorted(p for p in kho.glob("*.wav"))
    if not giong:
        print("Không có giọng mẫu nào trong", kho)
        return 1

    RA.mkdir(parents=True, exist_ok=True)
    print("[1] Trần lý thuyết - HNR của chính các giọng mẫu:")
    tran = {}
    for g in giong:
        t, s = cham_file(g, f"ref_{g.stem}")
        tran[g.stem] = s
        print(f"    {g.stem:<16}{t:>8.2f} ->{s:>8.2f} sau AMR")

    print("\n[2] Nạp F5 ...")
    tts = F5TTSService()
    tts.load()
    for g in giong:
        txt = g.with_suffix(".txt")
        if txt.exists():
            try:
                tts._register_voice_sync(g.stem, str(g),
                                         txt.read_text(encoding="utf-8").strip())
            except Exception as e:
                print(f"    không đăng ký được {g.stem}: {e}")

    print(f"\n[3] Quét {len(giong)} giọng x {len(a.nfe)} mức nfe"
          f"{f' x {a.lan} lần' if a.lan > 1 else ''}")
    print(f"\n    {'giọng mẫu':<16}{'nfe':>5}{'HNR ra':>9}{'sau AMR':>9}"
          f"{'trần':>8}{'còn thiếu':>11}")
    ket = []
    for g in giong:
        for nfe in a.nfe:
            settings.f5tts_nfe_step = nfe
            diem = []
            for lan in range(a.lan):
                ten = f"{g.stem}_nfe{nfe}_{lan}"
                f = RA / f"{ten}.wav"
                try:
                    f.write_bytes(await tts.synthesize(CAU, voice=g.stem,
                                                       use_cache=False))
                except Exception as e:
                    print(f"    {g.stem:<16}{nfe:>5}  lỗi: {str(e)[:50]}")
                    break
                diem.append(cham_file(f, ten))
            if not diem:
                continue
            t = float(np.mean([d[0] for d in diem]))
            s = float(np.mean([d[1] for d in diem]))
            thieu = tran[g.stem] - s
            print(f"    {g.stem:<16}{nfe:>5}{t:>9.2f}{s:>9.2f}"
                  f"{tran[g.stem]:>8.2f}{thieu:>11.2f}")
            ket.append((g.stem, nfe, s, thieu))

    if ket:
        tot = max(ket, key=lambda k: k[2])
        print("\n" + "=" * 62)
        print(f"CAO NHẤT: giọng '{tot[0]}' với nfe {tot[1]} — {tot[2]:.2f} dB "
              f"(còn thiếu {tot[3]:.2f} dB so với chính giọng mẫu)")
        theo_nfe = {}
        for _, n, s, _ in ket:
            theo_nfe.setdefault(n, []).append(s)
        rai = max(np.mean(v) for v in theo_nfe.values()) - \
            min(np.mean(v) for v in theo_nfe.values())
        print(f"nfe làm HNR đổi tối đa {rai:.2f} dB — "
              f"{'đáng kể' if rai > 0.3 else 'gần như không đổi, đừng chỉnh nfe vì HNR'}")
        print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
