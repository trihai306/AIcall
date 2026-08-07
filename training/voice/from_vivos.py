"""Dựng bộ dữ liệu train giọng từ corpus VIVOS (một người nói).

Dùng để THỬ quy trình fine-tune khi chưa có bản thu riêng. VIVOS là corpus đọc
của ĐHQG TP.HCM, giấy phép CC-BY-NC-SA-4.0 nên chỉ hợp lệ cho nghiên cứu / thử
nghiệm phi thương mại - đúng phạm vi đang dùng, KHÔNG được đem lên sản phẩm.

VIVOS đã chia sẵn theo người nói và có transcript, nên không cần cắt như bản thu
liền mạch (xem split_long_audio.py cho trường hợp đó).

    python training/voice/from_vivos.py --root data/vivos/vivos --minutes 30
"""

import argparse
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import soundfile as sf

# Console Windows mặc định cp1252, in tiếng Việt là ném UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Giọng mẫu lúc chạy: đo được mẫu 3.8s nhanh hơn mẫu bị F5-TTS cắt về 12s tới 96ms.
REF_MIN_S, REF_MAX_S = 3.0, 8.0


def doc_prompts(p: Path) -> dict[str, str]:
    """prompts.txt: mỗi dòng '<utt_id> <transcript>'."""
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        utt, _, text = line.partition(" ")
        if text:
            out[utt] = text.strip()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="Thư mục vivos (chứa train/ test/)")
    ap.add_argument("--minutes", type=float, default=30.0,
                    help="Nhắm bao nhiêu phút cho người nói được chọn")
    ap.add_argument("--speaker", default=None, help="Ép chọn một người nói cụ thể")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    root = Path(args.root)
    train = root / "train"
    prompts_f = train / "prompts.txt"
    if not prompts_f.exists():
        sys.exit(f"Không thấy {prompts_f}")
    prompts = doc_prompts(prompts_f)
    print(f"prompts: {len(prompts)} câu")

    # gom theo người nói
    theo_nguoi = defaultdict(list)
    for spk_dir in sorted((train / "waves").iterdir()):
        if not spk_dir.is_dir():
            continue
        for w in sorted(spk_dir.glob("*.wav")):
            if w.stem in prompts:
                theo_nguoi[spk_dir.name].append(w)

    tong = {}
    for spk, files in theo_nguoi.items():
        s = 0.0
        for f in files:
            try:
                s += sf.info(str(f)).duration
            except Exception:
                pass
        tong[spk] = s

    xep = sorted(tong.items(), key=lambda kv: -kv[1])
    print(f"\n{len(xep)} người nói. Nhiều tiếng nhất:")
    for spk, s in xep[:8]:
        print(f"  {spk}  {s/60:5.1f} phút  ({len(theo_nguoi[spk])} câu)")

    if args.speaker:
        chon = args.speaker
    else:
        # gần mốc mong muốn nhất, nhưng không dưới 60% mốc
        du = [(spk, s) for spk, s in xep if s >= args.minutes * 60 * 0.6]
        chon = min(du, key=lambda kv: abs(kv[1] - args.minutes * 60))[0] if du else xep[0][0]

    files = theo_nguoi[chon]
    print(f"\n=> Chọn {chon}: {tong[chon]/60:.1f} phút, {len(files)} câu")

    sr0 = sf.info(str(files[0])).samplerate
    if sr0 < 24000:
        print(f"[!] VIVOS ở {sr0} Hz, F5-TTS dùng 24000 Hz. prepare_dataset.py sẽ")
        print("    nâng tần số, nhưng KHÔNG tạo lại được dải cao đã mất - giọng sẽ")
        print("    hơi đục so với bản thu 24kHz thật. Chấp nhận được để THỬ quy trình.")

    out_dir = Path(args.out) if args.out else Path(f"data/train_voice_{chon}")
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob("*"):
        f.unlink()

    ung_vien = []
    for i, w in enumerate(files, 1):
        shutil.copy(str(w), str(out_dir / f"{i:03d}.wav"))
        text = prompts[w.stem]
        (out_dir / f"{i:03d}.txt").write_text(text, encoding="utf-8")
        d = sf.info(str(w)).duration
        if REF_MIN_S <= d <= REF_MAX_S:
            ung_vien.append((i, d, text))

    print(f"\nĐã xuất {len(files)} câu -> {out_dir}")

    # Giọng mẫu: ưu tiên câu MỞ ĐẦU BẰNG "DẠ". Đo được chữ "Dạ" đang bị đọc sai
    # ~70% số lần vì giọng mẫu hiện tại không hề chứa âm này.
    co_da = [c for c in ung_vien if c[2].strip().lower().startswith("dạ")]
    print(f"\nỨng viên giọng mẫu (3-8s): {len(ung_vien)} câu, "
          f"trong đó {len(co_da)} câu mở đầu bằng \"Dạ\"")
    for i, d, t in (co_da or ung_vien)[:8]:
        dau = "  <-- có 'Dạ'" if t.strip().lower().startswith("dạ") else ""
        print(f"  {i:03d}.wav  {d:.1f}s  {t[:56]}{dau}")

    print(f"\nBước tiếp theo:")
    print(f"  python training/voice/prepare_dataset.py --input {out_dir} --no-asr")
    print(f"  (--no-asr vì VIVOS đã có transcript chuẩn do người soát, "
          f"không cần PhoWhisper đoán)")


if __name__ == "__main__":
    main()
