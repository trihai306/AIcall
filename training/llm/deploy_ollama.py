"""Đưa model vừa fine-tune vào Ollama và (tuỳ chọn) trỏ .env sang nó.

Chạy sau training/llm/train_lora.py. Tách khỏi train_lora.py để bước này hiện
thành một bước riêng trong log job: train hỏng và nạp hỏng là hai chuyện khác
nhau, gộp chung thì nhìn log không biết chết ở đâu.

    python training/llm/deploy_ollama.py
    python training/llm/deploy_ollama.py --set-env      # sửa luôn OLLAMA_MODEL
    python training/llm/deploy_ollama.py --name tuvan-qwen --modelfile Modelfile.tuvan-qwen
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
LLM_DIR = PROJECT_DIR / "models" / "llm"
ENV_FILE = PROJECT_DIR / ".env"

# Unsloth KHÔNG ghi .gguf vào thư mục được truyền vào: nó tự thêm hậu tố
# "_gguf". Truyền models/llm/tuvan-gguf thì file thật ra ở
# models/llm/tuvan-gguf_gguf/, còn thư mục kia chỉ chứa safetensors 16-bit
# trung gian (~5.8GB). Tìm cả hai chỗ để khỏi phụ thuộc vào hành vi đó.
GGUF_SRC_DIRS = [LLM_DIR / "tuvan-gguf_gguf", LLM_DIR / "tuvan-gguf", LLM_DIR]


def tim_gguf(thu_muc: list[Path] | Path, uu_tien: str = "q4_k_m") -> Path | None:
    """Tìm file .gguf vừa xuất. Ưu tiên bản lượng tử hoá mong muốn."""
    dirs = [thu_muc] if isinstance(thu_muc, Path) else thu_muc
    files: list[Path] = []
    for d in dirs:
        if d.exists():
            # rglob ở LLM_DIR sẽ quét cả thư mục con, nên có thể trùng - lọc sau.
            files.extend(d.rglob("*.gguf") if d.name.endswith("gguf") else d.glob("*.gguf"))
    files = sorted(set(files))
    if not files:
        return None
    for f in files:
        if uu_tien in f.name.lower():
            return f
    # Không thấy đúng bản thì lấy file lớn nhất - bản chưa lượng tử hoá vẫn
    # chạy được, chỉ nặng hơn.
    return max(files, key=lambda p: p.stat().st_size)


def sua_env(ten_model: str) -> bool:
    """Đổi OLLAMA_MODEL trong .env, giữ nguyên mọi dòng khác.

    Đọc bằng utf-8-sig: .env trên máy Windows có BOM, đọc bằng utf-8 thường
    thì ký tự BOM dính vào tên khoá đầu tiên và khoá đó thành vô hiệu.
    """
    if not ENV_FILE.exists():
        print(f"[WARN] Không thấy {ENV_FILE}, bỏ qua bước sửa .env")
        return False

    noi_dung = ENV_FILE.read_text(encoding="utf-8-sig")
    dong_moi, thay = [], False
    for dong in noi_dung.splitlines():
        if re.match(r"^\s*OLLAMA_MODEL\s*=", dong):
            dong_moi.append(f"OLLAMA_MODEL={ten_model}")
            thay = True
        else:
            dong_moi.append(dong)
    if not thay:
        dong_moi.append(f"OLLAMA_MODEL={ten_model}")

    ENV_FILE.write_text("\n".join(dong_moi) + "\n", encoding="utf-8-sig")
    print(f"[OK] .env -> OLLAMA_MODEL={ten_model}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="tuvan-qwen", help="Tên model trong Ollama")
    ap.add_argument("--modelfile", default="Modelfile.tuvan-qwen")
    ap.add_argument("--gguf-name", default="tuvan-qwen-q4.gguf",
                    help="Tên file gguf đích, phải khớp dòng FROM trong Modelfile")
    ap.add_argument("--set-env", action="store_true",
                    help="Sửa luôn OLLAMA_MODEL trong .env sang model mới")
    args = ap.parse_args()

    src = tim_gguf(GGUF_SRC_DIRS)
    if not src:
        cho_da_tim = "\n".join(f"          - {d}" for d in GGUF_SRC_DIRS)
        raise SystemExit(
            f"[ERROR] Không thấy file .gguf nào. Đã tìm ở:\n{cho_da_tim}\n"
            "        Train chưa xuất GGUF (có dùng --skip-gguf không?)."
        )
    print(f"Thấy GGUF: {src.name} ({round(src.stat().st_size / 1024**3, 2)} GB)")

    dest = LLM_DIR / args.gguf_name
    if dest.resolve() != src.resolve():
        print(f"Copy -> {dest.name}")
        shutil.copy2(src, dest)

    modelfile = LLM_DIR / args.modelfile
    if not modelfile.exists():
        raise SystemExit(f"[ERROR] Không thấy {modelfile}")

    # cwd phải là models/llm: Modelfile ghi FROM ./tuvan-qwen-q4.gguf, đường
    # dẫn tương đối đó tính theo thư mục đang đứng chứ không theo vị trí file.
    print(f"ollama create {args.name} -f {args.modelfile}")
    proc = subprocess.run(["ollama", "create", args.name, "-f", args.modelfile],
                          cwd=str(LLM_DIR))
    if proc.returncode != 0:
        raise SystemExit(f"[ERROR] ollama create thất bại (exit {proc.returncode})")

    print(f"[OK] Đã nạp model '{args.name}' vào Ollama")

    if args.set_env:
        sua_env(args.name)

    print("\n[OK] Xong. Khởi động lại dịch vụ để dùng model mới.")


if __name__ == "__main__":
    main()
