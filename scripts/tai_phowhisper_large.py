"""Tải PhoWhisper-large rồi chuyển sang CTranslate2 để faster-whisper dùng được.

Hiện chạy PhoWhisper-MEDIUM. Căn cứ để thử large: cùng bộ tiếng qua kênh 8kHz,
small 64,1% -> medium 84,2% (xem [[chat-ai-tai-may-nghe-kem]]) - hai mươi điểm
chênh đó nói cỡ model còn dư địa. KỲ VỌNG KHÔNG PHẢI KẾT QUẢ: đo bằng
`scripts/so_medium_large.py` rồi mới đổi.

    .venv\\python.exe scripts\\tai_phowhisper_large.py

Xong thì có models/phowhisper/PhoWhisper-large-ct2. ĐỪNG đổi $CT2DIR trong
start_services.ps1 cho tới khi đo xong cả tốc độ lẫn CER.
"""
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

NGUON = "vinai/PhoWhisper-large"
RA = PROJECT / "models" / "phowhisper" / "PhoWhisper-large-ct2"


def main() -> int:
    if (RA / "model.bin").exists():
        print(f"  đã có sẵn: {RA}")
        return 0
    RA.parent.mkdir(parents=True, exist_ok=True)
    # int8_float16: CÙNG cách lượng tử với bản small/medium đang có, để phép so
    # chỉ khác CỠ MODEL chứ không khác cả cách lượng tử.
    lenh = [
        str(PROJECT / ".venv" / "Scripts" / "ct2-transformers-converter.exe"),
        "--model", NGUON,
        "--output_dir", str(RA),
        "--copy_files", "preprocessor_config.json", "tokenizer.json",
        "--quantization", "int8_float16",
    ]
    print(f"  tải + chuyển {NGUON} -> {RA}")
    r = subprocess.run(lenh)
    if r.returncode != 0:
        print("  HỎNG - xem log ở trên")
        return r.returncode
    mb = sum(f.stat().st_size for f in RA.rglob("*")) / 2**20
    print(f"  xong: {RA} ({mb:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
