"""
Chuẩn hoá dữ liệu thu âm cho fine-tune F5-TTS.

Input:  thư mục chứa các file ghi âm (.wav/.mp3/.m4a/.flac), mỗi file 1 câu.
Output: tools/F5-TTS-Vietnamese/data/your_dataset/  (format repo yêu cầu:
        NNN.wav 24kHz mono + NNN.txt transcript cùng tên)

Transcript:
  1. Nếu có training/voice/record_script.txt và tên file là số thứ tự (001.wav...)
     -> lấy text từ kịch bản (chính xác nhất).
  2. Nếu không -> gọi PhoWhisper server (http://localhost:8178) để tự nhận dạng,
     sau đó BẠN PHẢI soát lại các file .txt trước khi train.

Usage:
    python training/voice/prepare_dataset.py --input ~/recordings
    python training/voice/prepare_dataset.py --input ~/recordings --no-asr
"""
import argparse
import re
import sys
from pathlib import Path

import numpy as np

# Console Windows mặc định cp1252, in tiếng Việt là ném UnicodeEncodeError.
# split_long_audio.py và from_vivos.py đã có dòng này, riêng file này thiếu nên
# nó chết ngay dòng in đầu tiên, trước khi xử lý được file nào.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = PROJECT_DIR / "tools" / "F5-TTS-Vietnamese" / "data" / "your_dataset"
SCRIPT_PATH = Path(__file__).resolve().parent / "record_script.txt"
TARGET_SR = 24000


def load_script() -> dict[str, str]:
    """Parse record_script.txt -> {"001": "Dạ em chào anh ạ...", ...}"""
    mapping = {}
    if not SCRIPT_PATH.exists():
        return mapping
    for line in SCRIPT_PATH.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(\d{3})\.\s+(.+)$", line.strip())
        if m:
            mapping[m.group(1)] = m.group(2).strip()
    return mapping


def normalize_audio(path: Path) -> tuple[np.ndarray, int]:
    """Load -> mono -> resample 24kHz -> trim silence -> peak normalize."""
    import librosa

    audio, _sr = librosa.load(str(path), sr=TARGET_SR, mono=True)
    audio, _ = librosa.effects.trim(audio, top_db=35)
    peak = np.abs(audio).max()
    if peak > 0:
        audio = audio / peak * 0.95
    return audio, TARGET_SR


def _do_trung(a: str, b: str) -> float:
    """Tỉ lệ từ chung giữa hai câu. Dùng để phát hiện transcript dán nhầm."""
    ta, tb = set(a.lower().split()), set(b.lower().split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def _asr_kiem(wav_path, server_url: str) -> str | None:
    """Phiên âm một file đã ghi ra đĩa. Trả None nếu không gọi được server."""
    try:
        return transcribe(Path(wav_path).read_bytes(), server_url)
    except Exception as e:
        print(f"  [WARN] không đối chiếu được bằng ASR ({e})")
        return None


def transcribe(wav_bytes: bytes, server_url: str) -> str:
    import httpx

    resp = httpx.post(
        f"{server_url}/inference",
        files={"file": ("audio.wav", wav_bytes, "audio/wav")},
        data={"language": "vi", "response_format": "json", "temperature": "0"},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json().get("text", "").strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Thư mục chứa file ghi âm")
    parser.add_argument("--stt-server", default="http://localhost:8178")
    parser.add_argument("--no-script", action="store_true",
                        help="Bỏ qua record_script.txt, luôn dùng ASR. Dùng khi "
                             "file được cắt ra từ bản thu dài (split_long_audio.py) "
                             "chứ không phải đọc theo kịch bản.")
    parser.add_argument("--no-asr", action="store_true",
                        help="Không gọi STT, chỉ dùng kịch bản (file phải đặt tên 001.wav...)")
    args = parser.parse_args()

    import soundfile as sf

    input_dir = Path(args.input).expanduser()
    if not input_dir.exists():
        sys.exit(f"[ERROR] Không tìm thấy thư mục: {input_dir}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    script = load_script()

    exts = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
    files = sorted(p for p in input_dir.iterdir() if p.suffix.lower() in exts)
    if not files:
        sys.exit(f"[ERROR] Không có file audio nào trong {input_dir}")

    print(f"Xử lý {len(files)} file -> {OUTPUT_DIR}")
    ok, need_review, skipped = 0, 0, 0

    for f in files:
        try:
            audio, sr = normalize_audio(f)
        except Exception as e:
            print(f"  [SKIP] {f.name}: lỗi đọc audio ({e})")
            skipped += 1
            continue

        duration = len(audio) / sr
        if duration < 1.0 or duration > 30.0:
            print(f"  [SKIP] {f.name}: {duration:.1f}s (cần 1-30s)")
            skipped += 1
            continue

        stem = f.stem
        out_wav = OUTPUT_DIR / f"{stem}.wav"
        sf.write(str(out_wav), audio, sr)

        # Transcript, theo thứ tự tin cậy giảm dần:
        #   1. file <stem>.txt nằm cạnh audio - do người dùng cung cấp, chuẩn nhất
        #      (corpus mở như VIVOS đã kèm sẵn transcript đã được soát)
        #   2. record_script.txt nếu tên file là số thứ tự theo kịch bản
        #   3. ASR đoán - phải soát lại tay, transcript sai thì giọng train ra đọc sai
        sibling = f.with_suffix(".txt")
        text = ""
        asr_thay = False      # kịch bản có bị ASR thay không - dùng cho nhãn cuối
        if sibling.exists():
            text = sibling.read_text(encoding="utf-8").strip()
        if not text and not args.no_script:
            text = script.get(stem, "")
            if text:
                # BẪY: split_long_audio.py cũng đánh số 001, 002... nhưng từ một
                # bản thu BẤT KỲ, không đọc theo record_script.txt. Gán theo số
                # thứ tự là dán nhầm lời của kịch bản vào giọng người khác - đã
                # xảy ra thật, 60/228 file lệch tới 0-11% từ. Không có gì báo,
                # chỉ tới lúc nghe giọng train ra mới biết.
                # Nên đối chiếu với ASR trước khi tin vào số thứ tự.
                if not args.no_asr:
                    doan = _asr_kiem(out_wav, args.stt_server)
                    if doan is not None and _do_trung(text, doan) < 0.5:
                        print(f"  [CANH BAO] {f.name}: kịch bản ghi '{text[:40]}...' "
                              f"nhưng nghe ra '{doan[:40]}...' -> dùng bản ASR")
                        text = doan
                        # Nhớ lại việc đã THAY. Không có cờ này thì nhãn cuối
                        # vẫn in [script] vì nó chỉ xét "số này có trong kịch bản
                        # không", trong khi lời thật lấy từ ASR. Đọc log thấy
                        # [script] rồi tưởng transcript chuẩn theo kịch bản và bỏ
                        # qua khâu soát - trong khi đây đúng là loại transcript
                        # BẮT BUỘC phải soát.
                        asr_thay = True
                        need_review += 1
        if not text and not args.no_asr:
            try:
                import io

                buf = io.BytesIO()
                sf.write(buf, audio, sr, format="WAV")
                text = transcribe(buf.getvalue(), args.stt_server)
                need_review += 1
            except Exception as e:
                print(f"  [WARN] {f.name}: STT lỗi ({e}) - tự viết transcript vào {stem}.txt")

        (OUTPUT_DIR / f"{stem}.txt").write_text(text + "\n", encoding="utf-8")
        ok += 1
        tag = "txt" if sibling.exists() and sibling.read_text(encoding="utf-8").strip() \
              else ("asr-thay-kich-ban" if asr_thay
                    else ("script" if stem in script else ("asr" if text else "EMPTY")))
        print(f"  [OK] {stem}.wav ({duration:.1f}s) [{tag}]")

    total_dur = sum(
        len(sf.read(str(p))[0]) / TARGET_SR for p in OUTPUT_DIR.glob("*.wav")
    )
    print(f"\nXong: {ok} file, bỏ qua {skipped}. Tổng thời lượng: {total_dur/60:.1f} phút")
    if need_review:
        print(f"[QUAN TRỌNG] {need_review} transcript sinh bằng ASR - hãy mở {OUTPUT_DIR}")
        print("             và soát lại từng file .txt trước khi train!")
    if total_dur / 60 < 10:
        print("[WARN] Dưới 10 phút dữ liệu - giọng sau train có thể chưa ổn định.")
        print("       Khuyến nghị 15-20 phút trở lên (đợt 1), 45-60 phút nếu muốn giống nhất.")
    print("\nBước tiếp theo: bash training/voice/train.sh <ten_giong>")


if __name__ == "__main__":
    main()
