"""Stage the already-benchmarked FP32 files; optionally select the engine.

Run on Windows. Only the three STT settings are changed, with an exact backup
of the old .env. This does not restart services, dial, or alter call records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REVISION = "65b6b319ecd0fe5875b5afa701eeae84f6f608fa"


def idle() -> None:
    import httpx
    with httpx.Client(timeout=10, trust_env=False) as client:
        response = client.get("http://127.0.0.1:8100/api/devices/voice/status")
        response.raise_for_status()
        if response.json().get("calls"):
            raise RuntimeError("A call is present; do not change ASR now")


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    idle()
    evidence = ROOT / "logs/asr_eval_20260912/results/gip1.5_fp32_modified_beam_search.json"
    result = json.loads(evidence.read_text(encoding="utf-8"))
    assert result["completed"] and result["model"]["precision"] == "fp32"
    assert result["model"]["revision"] == REVISION
    target = ROOT / "models/stt/gipformer1.5-fp32"
    target.mkdir(parents=True, exist_ok=True)
    for entry in result["model"]["files"].values():
        source = Path(entry["path"])
        if digest(source) != entry["sha256"]:
            raise RuntimeError(f"Benchmarked file changed: {source.name}")
        destination = target / source.name
        if destination.exists():
            if digest(destination) != entry["sha256"]:
                raise RuntimeError(f"Refusing to overwrite a different model: {destination}")
        else:
            shutil.copy2(source, destination)
        assert digest(destination) == entry["sha256"]
        print("VERIFIED_MODEL", destination.name, entry["sha256"])
    from backend.services.gipformer_stt import GipformerSTT
    engine = GipformerSTT(target)
    engine.load()
    print("READY", json.dumps(engine.info()))
    if not args.activate:
        return
    idle()
    env = ROOT / ".env"
    original = env.read_bytes()
    text = original.decode("utf-8-sig")
    updates = {"STT_ENGINE": "gipformer",
               "GIPFORMER_MODEL_PATH": "./models/stt/gipformer1.5-fp32",
               "GIPFORMER_NUM_THREADS": "4"}
    newline = "\r\n" if "\r\n" in text else "\n"
    for key, value in updates.items():
        pattern = rf"(?m)^[ \t]*{key}[ \t]*=[^\r\n]*"
        if re.search(pattern, text):
            text = re.sub(pattern, f"{key}={value}", text)
        else:
            text += ("" if text.endswith("\n") else newline) + f"{key}={value}" + newline
    if text.encode("utf-8") == original:
        print("CONFIG_ALREADY_SELECTED")
        return
    backup = ROOT / "logs/_run" / f"env_before_gipformer_{time.time_ns()}.bak"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(env, backup)
    with tempfile.NamedTemporaryFile(dir=ROOT, prefix=".env-gipformer-", delete=False) as temp:
        temp.write(text.encode("utf-8"))
        staged = Path(temp.name)
    os.replace(staged, env)
    print("CONFIG_SELECTED", json.dumps(updates))
    print("BACKUP", backup)
    print("Restart required. No service was restarted by this script.")


if __name__ == "__main__":
    main()
