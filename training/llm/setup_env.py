"""Dựng venv riêng cho fine-tune LLM (.venv-train) và kiểm chứng nó chạy được.

Vì sao venv riêng: Unsloth kéo theo bản transformers/torch riêng, xung đột với
F5-TTS trong venv chính. Trộn chung là hỏng cả hai.

Vì sao viết bằng Python chứ không phải .sh/.ps1: máy Windows không có bash, mà
duy trì hai bản script song song thì sớm muộn cũng lệch nhau. Gọi qua
sys.executable thì chạy được ở cả hai hệ.

    python training/llm/setup_env.py            # dựng (bỏ qua thứ đã có)
    python training/llm/setup_env.py --check    # chỉ kiểm tra, không cài
    python training/llm/setup_env.py --force    # cài lại từ đầu
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
VENV_DIR = PROJECT_DIR / ".venv-train"

# Khớp với venv chính (torch 2.11.0+cu128). RTX 5070 là Blackwell sm_120, bản
# cu12.1/cu12.4 KHÔNG có kernel cho kiến trúc này - phải cu128.
TORCH_INDEX = "https://download.pytorch.org/whl/cu128"


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(cmd: list[str], desc: str) -> int:
    """Chạy và cho output chảy thẳng ra stdout để JobRunner stream về UI."""
    print(f"\n>>> {desc}")
    print("    " + " ".join(str(c) for c in cmd), flush=True)
    proc = subprocess.run(cmd, cwd=str(PROJECT_DIR))
    if proc.returncode != 0:
        print(f"[ERROR] {desc} thất bại (exit {proc.returncode})", flush=True)
    return proc.returncode


def kiem_tra(py: Path) -> bool:
    """Import thật các thư viện cần, không chỉ kiểm tra file có tồn tại."""
    code = (
        "import json, sys\n"
        "out = {}\n"
        "try:\n"
        "    import torch\n"
        "    out['torch'] = torch.__version__\n"
        "    out['cuda_build'] = torch.version.cuda\n"
        "    out['cuda_available'] = torch.cuda.is_available()\n"
        "    if torch.cuda.is_available():\n"
        "        out['gpu'] = torch.cuda.get_device_name(0)\n"
        "        out['capability'] = list(torch.cuda.get_device_capability(0))\n"
        "        free, total = torch.cuda.mem_get_info()\n"
        "        out['vram_free_gb'] = round(free / 1024**3, 1)\n"
        "        out['vram_total_gb'] = round(total / 1024**3, 1)\n"
        "except Exception as e:\n"
        "    out['torch_error'] = f'{type(e).__name__}: {e}'\n"
        "for mod in ('unsloth', 'trl', 'datasets', 'transformers', 'peft'):\n"
        "    try:\n"
        "        m = __import__(mod)\n"
        "        out[mod] = getattr(m, '__version__', 'ok')\n"
        "    except Exception as e:\n"
        "        out[mod + '_error'] = f'{type(e).__name__}: {e}'\n"
        "print('KETQUA' + json.dumps(out))\n"
    )
    proc = subprocess.run([str(py), "-c", code], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=str(PROJECT_DIR))
    # Unsloth in rất nhiều banner khi import - chỉ lấy dòng kết quả.
    dong = [l for l in (proc.stdout or "").splitlines() if l.startswith("KETQUA")]
    if not dong:
        print("[ERROR] Không kiểm tra được môi trường.")
        if proc.stdout:
            print(proc.stdout[-2000:])
        if proc.stderr:
            print(proc.stderr[-2000:])
        return False

    import json
    info = json.loads(dong[0][len("KETQUA"):])
    print("\n=== Môi trường .venv-train ===")
    for k, v in info.items():
        print(f"  {k:16} {v}")

    loi = [k for k in info if k.endswith("_error")]
    if loi:
        print(f"\n[ERROR] Thiếu/hỏng: {', '.join(k[:-6] for k in loi)}")
        return False
    if not info.get("cuda_available"):
        print("\n[ERROR] Torch không thấy GPU. Fine-tune bắt buộc cần CUDA.")
        return False

    print("\n[OK] Môi trường training sẵn sàng.")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="Chỉ kiểm tra, không cài")
    ap.add_argument("--force", action="store_true", help="Xoá .venv-train rồi dựng lại")
    args = ap.parse_args()

    py = venv_python(VENV_DIR)

    if args.check:
        if not py.exists():
            print(f"[ERROR] Chưa có {VENV_DIR.name}. Chạy không kèm --check để dựng.")
            sys.exit(1)
        sys.exit(0 if kiem_tra(py) else 1)

    if args.force and VENV_DIR.exists():
        print(f">>> Xoá {VENV_DIR}")
        shutil.rmtree(VENV_DIR)

    if not py.exists():
        if run([sys.executable, "-m", "venv", str(VENV_DIR)], f"Tạo {VENV_DIR.name}"):
            sys.exit(1)
    else:
        print(f">>> Đã có {VENV_DIR.name}, dùng lại (thêm --force để dựng lại)")

    if run([str(py), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
           "Nâng cấp pip"):
        sys.exit(1)

    if run([str(py), "-m", "pip", "install", "torch", "--index-url", TORCH_INDEX],
           "Cài torch (cu128, cho Blackwell sm_120)"):
        sys.exit(1)

    # triton-windows: Unsloth cần triton, nhưng gói 'triton' trên PyPI chỉ có
    # bản Linux. Trên Windows phải dùng gói riêng, thiếu nó là Unsloth import lỗi.
    if os.name == "nt":
        if run([str(py), "-m", "pip", "install", "triton-windows"],
               "Cài triton-windows (Unsloth cần, bản 'triton' thường chỉ có cho Linux)"):
            sys.exit(1)

    if run([str(py), "-m", "pip", "install", "unsloth", "datasets", "trl", "transformers", "peft"],
           "Cài unsloth + trl + datasets"):
        sys.exit(1)

    print("\n" + "=" * 46)
    print(" Kiểm tra lại bằng cách import thật")
    print("=" * 46)
    sys.exit(0 if kiem_tra(py) else 1)


if __name__ == "__main__":
    main()
