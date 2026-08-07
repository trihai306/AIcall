"""Chọn giọng mẫu (reference audio) từ dataset đã train.

F5-TTS là mô hình sao chép giọng: lúc chạy nó nghe một đoạn mẫu ngắn rồi bắt
chước chất giọng VÀ ngữ điệu của đoạn đó. Nên đoạn mẫu quan trọng ngang model.

Hai tiêu chí đo được:
  - Độ dài 3-8s. F5-TTS cắt mẫu xuống 12s; mẫu 3.8s nhanh hơn mẫu 12s ~96ms.
  - Ưu tiên câu MỞ ĐẦU BẰNG "Dạ". Gần như mọi câu trả lời của tổng đài đều bắt
    đầu bằng chữ này, mà giọng mẫu hiện tại không chứa nó -> đo được đọc sai
    thành "giả" khoảng 70% số lần.

    python scripts/pick_ref.py --dataset <thu_muc_dataset> --name giong_thu
"""

import argparse
import shutil
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

REF_MIN_S, REF_MAX_S = 3.0, 8.0
PROJECT = Path(__file__).resolve().parent.parent


def main() -> int:
    import soundfile as sf

    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, help="Thư mục có NNN.wav + NNN.txt")
    ap.add_argument("--name", required=True, help="Tên giọng, dùng làm tên file mẫu")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    ds = Path(args.dataset)
    if not ds.exists():
        print(f"[!] Không thấy dataset: {ds}")
        return 1

    ung_vien = []
    for w in sorted(ds.glob("*.wav")):
        try:
            d = sf.info(str(w)).duration
        except Exception:
            continue
        if not (REF_MIN_S <= d <= REF_MAX_S):
            continue
        t = w.with_suffix(".txt")
        text = t.read_text(encoding="utf-8").strip() if t.exists() else ""
        ung_vien.append((w, d, text))

    if not ung_vien:
        print(f"[!] Không có đoạn nào dài {REF_MIN_S}-{REF_MAX_S}s để làm giọng mẫu.")
        print("    Tự chọn tay một file rồi copy vào models/tts/ref_voices/")
        return 1

    co_da = [c for c in ung_vien if c[2].lower().lstrip('"\u201c ').startswith("dạ")]
    chon, dur, text = (co_da or ung_vien)[0]

    out = Path(args.out) if args.out else PROJECT / "models" / "tts" / "ref_voices" / f"{args.name}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(str(chon), str(out))
    out.with_suffix(".txt").write_text(text + "\n", encoding="utf-8")

    print(f"  ứng viên 3-8s: {len(ung_vien)} | mở đầu bằng \"Dạ\": {len(co_da)}")
    print(f"  chọn {chon.name} ({dur:.1f}s): {text[:70]}")
    if not co_da:
        print("  [!] Không câu nào mở đầu bằng \"Dạ\" - chữ này nhiều khả năng")
        print("      vẫn bị đọc sai. Cần thu thêm câu có \"Dạ\" nếu muốn sửa hẳn.")
    print(f"  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
