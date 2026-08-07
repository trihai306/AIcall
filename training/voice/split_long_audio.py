"""Cắt một file thu âm dài thành từng câu để đưa vào prepare_dataset.py.

prepare_dataset.py yêu cầu "mỗi file 1 câu", nên bản thu liền mạch 30-60 phút
không dùng thẳng được. Script này cắt tại chỗ ngắt giọng, xuất 001.wav, 002.wav...
rồi bạn chạy prepare_dataset.py trên thư mục kết quả như bình thường.

Dùng Silero VAD (đã có sẵn trong dự án) thay vì dò theo mức năng lượng: VAD phân
biệt được tiếng nói với tiếng ồn nền, còn ngưỡng năng lượng thì cắt nhầm ở chỗ
hít thở hoặc tiếng quạt.

    python training/voice/split_long_audio.py --input thu_am_30p.wav
    python training/voice/split_long_audio.py --input thu_am_30p.wav --pick-ref

--pick-ref còn chọn giúp một đoạn ngắn làm giọng mẫu lúc chạy. Ưu tiên đoạn có
chữ "Dạ" ở đầu, vì F5-TTS bắt chước ngữ điệu từ đoạn mẫu và gần như mọi câu trả
lời đều mở đầu bằng "Dạ".
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

# Console Windows mặc định cp1252, in tiếng Việt là ném UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TARGET_SR = 24000

# F5-TTS cắt giọng mẫu xuống 12s nên đoạn dài hơn là phí. ZipVoice cũng khuyến
# nghị 1-30s cho dữ liệu train. Khoảng 3-15s là vùng an toàn cho cả hai.
MIN_SEG_S = 1.5
MAX_SEG_S = 15.0
TARGET_SEG_S = 8.0
# Giọng mẫu lúc chạy: đo được mẫu 3.8s nhanh hơn mẫu bị cắt về 12s tới 96ms.
REF_MIN_S, REF_MAX_S = 3.0, 8.0


def load_mono_24k(path: Path) -> np.ndarray:
    wav, sr = sf.read(str(path), dtype="float32", always_2d=True)
    wav = wav.mean(axis=1)
    if sr != TARGET_SR:
        n = int(round(len(wav) / sr * TARGET_SR))
        wav = np.interp(
            np.linspace(0, len(wav) - 1, n), np.arange(len(wav)), wav
        ).astype("float32")
    return wav


def speech_regions(wav: np.ndarray) -> list[tuple[int, int]]:
    """Trả về các đoạn có tiếng nói, đơn vị mẫu ở TARGET_SR."""
    import torch

    model, utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad", model="silero_vad",
        force_reload=False, trust_repo=True,
    )
    get_ts = utils[0]
    # Silero chạy ở 16kHz
    n16 = int(len(wav) / TARGET_SR * 16000)
    w16 = np.interp(np.linspace(0, len(wav) - 1, n16), np.arange(len(wav)), wav)
    ts = get_ts(torch.from_numpy(w16.astype("float32")), model,
                sampling_rate=16000, min_silence_duration_ms=300,
                min_speech_duration_ms=250)
    k = TARGET_SR / 16000
    return [(int(t["start"] * k), int(t["end"] * k)) for t in ts]


def gom_doan(regions, total_len) -> list[tuple[int, int]]:
    """Gộp các vùng tiếng liền nhau cho tới khi đạt độ dài mong muốn."""
    segs, cur_s, cur_e = [], None, None
    for s, e in regions:
        if cur_s is None:
            cur_s, cur_e = s, e
            continue
        # gộp nếu vẫn dưới mốc mong muốn, và không vượt trần
        if (e - cur_s) / TARGET_SR <= TARGET_SEG_S:
            cur_e = e
        else:
            if (cur_e - cur_s) / TARGET_SR >= MIN_SEG_S:
                segs.append((cur_s, cur_e))
            cur_s, cur_e = s, e
    if cur_s is not None and (cur_e - cur_s) / TARGET_SR >= MIN_SEG_S:
        segs.append((cur_s, cur_e))

    # chẻ đôi đoạn nào lỡ vượt trần
    out = []
    for s, e in segs:
        while (e - s) / TARGET_SR > MAX_SEG_S:
            mid = s + int(MAX_SEG_S * TARGET_SR)
            out.append((s, mid))
            s = mid
        if (e - s) / TARGET_SR >= MIN_SEG_S:
            out.append((s, e))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="File thu âm dài (.wav/.mp3/...)")
    ap.add_argument("--out", default=None, help="Thư mục xuất (mặc định <tên file>_cat)")
    ap.add_argument("--pad-ms", type=int, default=120,
                    help="Chừa thêm hai đầu mỗi đoạn, tránh cắt cụt phụ âm")
    ap.add_argument("--pick-ref", action="store_true",
                    help="Chọn luôn một đoạn ngắn làm giọng mẫu lúc chạy")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        sys.exit(f"Không thấy file: {src}")
    out_dir = Path(args.out) if args.out else src.parent / f"{src.stem}_cat"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Đọc {src} ...")
    wav = load_mono_24k(src)
    print(f"  {len(wav)/TARGET_SR/60:.1f} phút, {TARGET_SR} Hz mono")

    print("Dò tiếng nói bằng Silero VAD ...")
    regions = speech_regions(wav)
    print(f"  {len(regions)} vùng có tiếng")

    segs = gom_doan(regions, len(wav))
    if not segs:
        sys.exit("Không cắt được đoạn nào. File có tiếng nói không?")

    pad = int(args.pad_ms / 1000 * TARGET_SR)
    dur_all = []
    for i, (s, e) in enumerate(segs, 1):
        s2, e2 = max(0, s - pad), min(len(wav), e + pad)
        seg = wav[s2:e2]
        peak = float(np.max(np.abs(seg))) or 1.0
        seg = (seg / peak * 0.95).astype("float32")   # chuẩn đỉnh
        sf.write(str(out_dir / f"{i:03d}.wav"), seg, TARGET_SR, subtype="PCM_16")
        dur_all.append(len(seg) / TARGET_SR)

    tong = sum(dur_all)
    print(f"\nĐã cắt {len(segs)} đoạn -> {out_dir}")
    print(f"  tổng {tong/60:.1f} phút | ngắn nhất {min(dur_all):.1f}s | "
          f"dài nhất {max(dur_all):.1f}s | trung bình {tong/len(dur_all):.1f}s")

    if args.pick_ref:
        ung_vien = [(i + 1, d) for i, d in enumerate(dur_all)
                    if REF_MIN_S <= d <= REF_MAX_S]
        if not ung_vien:
            print("\n[!] Không có đoạn nào dài 3-8s để làm giọng mẫu.")
        else:
            print(f"\nỨng viên làm giọng mẫu ({len(ung_vien)} đoạn dài 3-8s):")
            for idx, d in ung_vien[:10]:
                print(f"  {idx:03d}.wav  {d:.1f}s")
            print("\n  Chọn đoạn có transcript BẮT ĐẦU BẰNG \"Dạ\" nếu có -")
            print("  F5-TTS bắt chước ngữ điệu từ đoạn mẫu, mà đo được chữ \"Dạ\"")
            print("  đang bị đọc sai ~70% số lần với giọng mẫu hiện tại.")

    print("\nBước tiếp theo:")
    print(f"  python training/voice/prepare_dataset.py --input {out_dir}")


if __name__ == "__main__":
    main()
