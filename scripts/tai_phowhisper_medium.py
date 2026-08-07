"""Tải PhoWhisper-medium rồi chuyển sang CTranslate2 để faster-whisper dùng được.

Hiện hệ thống chạy PhoWhisper-SMALL. Bản medium lớn gấp ~3 lần, kỳ vọng nghe khá
hơn trên kênh thoại 8kHz đã mất dải phụ âm - nhưng KỲ VỌNG KHÔNG PHẢI KẾT QUẢ,
phải đo bằng `scripts/so_stt_small_medium.py` rồi mới đổi.

Chạy nền, mất vài phút (tải ~3GB rồi lượng tử hoá):

    python scripts/tai_phowhisper_medium.py

Xong thì thư mục models/phowhisper/PhoWhisper-medium-ct2 sẵn sàng. ĐỪNG đổi
whisper_server sang dùng nó cho tới khi đo xong.
"""

import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

NGUON = "vinai/PhoWhisper-medium"
RA = PROJECT / "models" / "phowhisper" / "PhoWhisper-medium-ct2"


def main() -> int:
    if (RA / "model.bin").exists():
        print(f"  đã có sẵn: {RA}")
        return 0
    RA.parent.mkdir(parents=True, exist_ok=True)

    # int8_float16: cùng lượng tử hoá với bản small đang chạy, để so sánh CHỈ
    # khác kích thước model chứ không khác cả cách lượng tử.
    lenh = [
        str(PROJECT / ".venv" / "Scripts" / "ct2-transformers-converter.exe"),
        "--model", NGUON,
        "--output_dir", str(RA),
        "--copy_files", "preprocessor_config.json", "tokenizer.json",
        "--quantization", "int8_float16",
    ]
    print(f"  tải + chuyển {NGUON} -> {RA}")
    print(f"  {' '.join(lenh)}\n")
    r = subprocess.run(lenh, text=True, capture_output=True)
    print((r.stdout or "")[-2000:])
    if r.returncode != 0:
        print("  LỖI:")
        print((r.stderr or "")[-2000:])
        return 1
    tong = sum(f.stat().st_size for f in RA.rglob("*") if f.is_file())
    print(f"  xong: {tong / 1024**2:.0f} MB tại {RA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
