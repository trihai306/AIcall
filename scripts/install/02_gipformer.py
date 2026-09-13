"""Install the exact Gipformer build benchmarked for live calls.

The model revision and file hashes are pinned to the production A/B evidence in
``logs/asr_eval_20260912``.  A changed upstream file is rejected instead of
silently replacing the recognizer that was measured.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "models" / "stt" / "gipformer1.5-fp32"
REPO = "g-group-ai-lab/gipformer1.5-65M-rnnt"
REVISION = "65b6b319ecd0fe5875b5afa701eeae84f6f608fa"
EXPECTED_SHA256 = {
    "encoder.onnx": "96b3c83c9c39afc4421f8fd2914d26b53ae837e56788a7bd5aece61580937c36",
    "decoder.onnx": "ea584ee86d6f74191f934f8b950013adcb2c33483785aa8b1b44fff3a7b30069",
    "joiner.onnx": "d146a1cff4a0060d7031e5eb91295773661bc52c356c952dd1e2759e60ffa94d",
    "tokens.txt": "f536d03c2e95ebd2930cf0abec88e823bd17d3c1933da7ae6a82db3b80605e15",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_dependencies() -> None:
    try:
        import huggingface_hub  # noqa: F401
        import sherpa_onnx  # noqa: F401
        return
    except ImportError:
        pass

    requirements = ROOT / "whisper_server" / "requirements-gipformer.txt"
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-input", "-r", str(requirements)],
        cwd=ROOT,
        check=True,
    )


def _stage(downloaded: Path, destination: Path, expected: str) -> None:
    actual = _sha256(downloaded)
    if actual != expected:
        raise RuntimeError(
            f"Checksum mismatch for {destination.name}: expected {expected}, got {actual}"
        )

    if destination.exists() and _sha256(destination) == expected:
        print(f"[SKIP] {destination.name} already verified")
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=destination.name + ".", suffix=".tmp", dir=destination.parent, delete=False
    ) as tmp:
        staged = Path(tmp.name)
    try:
        shutil.copy2(downloaded, staged)
        if _sha256(staged) != expected:
            raise RuntimeError(f"Staged checksum changed for {destination.name}")
        os.replace(staged, destination)
    finally:
        if staged.exists():
            staged.unlink()
    print(f"[OK] {destination.name} {expected}")


def main() -> None:
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    sys.path.insert(0, str(ROOT))
    _ensure_dependencies()

    from huggingface_hub import hf_hub_download

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for filename, expected in EXPECTED_SHA256.items():
        destination = MODEL_DIR / filename
        if destination.exists() and _sha256(destination) == expected:
            print(f"[SKIP] {filename} already verified")
            continue
        downloaded = Path(
            hf_hub_download(
                repo_id=REPO,
                filename=filename,
                revision=REVISION,
                token=False,
            )
        )
        _stage(downloaded, destination, expected)

    from backend.services.gipformer_stt import GipformerSTT

    engine = GipformerSTT(MODEL_DIR)
    engine.load()
    print("[OK] Gipformer ready:", engine.info())


if __name__ == "__main__":
    main()
