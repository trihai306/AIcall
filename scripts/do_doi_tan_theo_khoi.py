"""Đổi tần theo KHỐI có làm hỏng nhận dạng không?

Bắt được trong cuộc gọi thật: cùng một đoạn tiếng, cùng model, cùng mồi từ vựng,
mà hai đường cho hai kết quả:

    lúc gọi (đường luồng)  -> "trần vay năm mươi triệu"
    đọc lại từ bản ghi     -> "anh cần vay năm mươi triệu"   <- ĐÚNG

Khác biệt duy nhất: đường luồng nâng 8k->16k theo TỪNG KHỐI khi tiếng chảy về,
còn đọc lại thì nâng cả đoạn một lần. `resample_poly` gọi rời từng khối không
mang trạng thái bộ lọc qua ranh giới, nên mỗi mối nối là một điểm gãy.

Ghi chú cũ trong `audio_utils` có so FFT với đa pha và kết luận "STT đọc y hệt",
nhưng phép so đó là GIỮA HAI CÁCH CẮT KHỐI - chưa bao giờ so với việc không cắt.

Script cắt cùng một lượt theo nhiều cỡ khối rồi cho STT đọc, để thấy cỡ khối ảnh
hưởng tới đâu.

    python scripts/do_doi_tan_theo_khoi.py
    python scripts/do_doi_tan_theo_khoi.py --file <bản ghi> --luot 4
"""

import argparse
import asyncio
import sys
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def nang_theo_khoi(x8: np.ndarray, khoi_ms: int) -> np.ndarray:
    """Nâng 8k->16k theo từng khối rời, đúng như đường luồng đang làm."""
    from backend.services.audio_utils import resample_lien_tuc
    if khoi_ms <= 0:
        return resample_lien_tuc(x8, 8000, 16000)
    n = 8000 * khoi_ms // 1000
    manh = [resample_lien_tuc(x8[i:i + n], 8000, 16000)
            for i in range(0, len(x8), n)]
    return np.concatenate(manh) if manh else x8


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="")
    ap.add_argument("--luot", type=int, default=0, help="0 = chạy mọi lượt")
    ap.add_argument("--khoi", type=int, nargs="+", default=[0, 20, 100, 400])
    a = ap.parse_args()

    import soundfile as sf

    from backend.services import phone_call_service as PS
    from backend.services.stt_service import STTService
    from soi_tung_luot import cat_luot

    if a.file:
        f = Path(a.file)
    else:
        goc = PROJECT / "data" / "recordings"
        tep = sorted(goc.rglob("*.opus")) + sorted(goc.rglob("*.wav"))
        if not tep:
            print("  không thấy bản ghi nào")
            return 1
        f = max(tep, key=lambda p: p.stat().st_mtime)

    x, sr = sf.read(str(f), dtype="float32", always_2d=True)
    khach = x[:, 0]
    luot, _, _ = cat_luot(khach, sr, PS)
    if not luot:
        print("  bản ghi không có lượt nào của khách")
        return 1

    stt = STTService()
    print(f"\n  {f.name} | {len(luot)} lượt | cỡ khối 0 = nâng cả đoạn một lần\n")

    chon = [i for i in range(len(luot)) if not a.luot or i + 1 == a.luot]
    khac = 0
    for i in chon:
        bd, kt, talk, du_dai = luot[i]
        if not du_dai:
            continue
        seg = khach[bd:kt]
        print(f"  lượt {i+1} ({talk}ms):")
        ket = {}
        for k in a.khoi:
            y = nang_theo_khoi(seg, k)
            pcm = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
            nghe = (await stt.transcribe(pcm)).strip()
            ket[k] = nghe
            ten = "cả đoạn" if k == 0 else f"khối {k}ms"
            print(f"    {ten:<12} {nghe!r}")
        if len(set(ket.values())) > 1:
            khac += 1
            print("    ^^ CÁCH CẮT KHỐI LÀM ĐỔI KẾT QUẢ")
        print()

    print(f"  {khac}/{len(chon)} lượt cho kết quả KHÁC NHAU tuỳ cỡ khối.")
    if khac:
        print("  -> Đổi tần theo khối đang làm hỏng nhận dạng. Sửa bằng cách giữ")
        print("     trạng thái bộ lọc qua các khối, hoặc nâng tần một lần khi chốt lượt.")
    else:
        print("  -> Cỡ khối không ảnh hưởng. Nguyên nhân nằm ở chỗ khác.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
