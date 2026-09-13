"""Offline A/B on real, completed phone recordings; never dial or edit sessions.

Windows example:
  .venv/python.exe scripts/do_asr_call_that.py prepare --count 3
  .venv/python.exe scripts/do_asr_call_that.py run --engine pho
  .venv/python.exe scripts/do_asr_call_that.py run --engine gip --precision int8

Raw LEFT customer channel only. Evaluation excerpts use an explicitly approximate
energy segmenter, NOT a replay of production VAD, echo cancellation or speculation.
No WER/CER is claimed without separately human-verified references.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import re
import sys
import time
import unicodedata

import httpx
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
DEFAULT_OUT = PROJECT / "logs" / "asr_eval_20260912"


def save_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def get_json(client: httpx.Client, url: str) -> dict:
    response = client.get(url)
    response.raise_for_status()
    return response.json()


def assert_idle(client: httpx.Client, base: str) -> None:
    status = get_json(client, base + "/api/devices/voice/status")
    if "calls" not in status or status["calls"]:
        raise RuntimeError("Active/unknown call state: abort benchmark, leave services intact")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def customer_channel(audio: np.ndarray) -> np.ndarray:
    if audio.ndim != 2 or audio.shape[1] != 2:
        raise ValueError("Expected stereo customer-left/bot-right recording; do not guess channels")
    return np.ascontiguousarray(audio[:, 0], dtype=np.float32)


def excerpts(audio: np.ndarray, sr: int) -> tuple[list[tuple[int, int]], dict]:
    """Low-threshold offline excerpts, with 240 ms preroll and 360 ms tail.

    Closing after 650 ms quiet deliberately preserves short intra-sentence pauses.
    This is not production VAD; the exact same files feed every recognizer.
    """
    n = max(1, sr // 50)
    rms = np.array([np.sqrt(np.mean(audio[i:i+n] ** 2)) * 32768
                    for i in range(0, len(audio), n)])
    if not len(rms):
        return [], {"noise_rms": 0.0}
    noise = float(np.percentile(rms, 20))
    on, off = max(250.0, noise * 4), max(150.0, noise * 2)
    result = []
    start = None
    streak = 0
    last_voice = 0
    for i, value in enumerate(rms):
        if start is None:
            streak = streak + 1 if value >= on else 0
            if streak >= 3:
                start = max(0, i - 2 - 12)
                last_voice = i
            continue
        if value >= off:
            last_voice = i
        if i - last_voice >= 33 or i - start >= 750:
            end = min(len(audio), (last_voice + 19) * n)
            if last_voice - start >= 18:
                result.append((start * n, end))
            start, streak = None, 0
    if start is not None and last_voice - start >= 18:
        result.append((start * n, min(len(audio), (last_voice + 19) * n)))
    # Merge overlapping preroll/tail windows so frames are never counted twice.
    merged = []
    for a, b in result:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged, {"noise_rms": noise, "on_rms": on, "off_rms": off,
                    "frame_ms": 20, "close_ms": 660, "preroll_ms": 240,
                    "tail_ms": 360, "production_vad_replay": False}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text.lower())
    return " ".join(re.findall(r"\w+", text, flags=re.UNICODE))


def edit_distance(a: list | str, b: list | str) -> int:
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        row = [i]
        for j, y in enumerate(b, 1):
            row.append(min(previous[j] + 1, row[-1] + 1,
                           previous[j-1] + (x != y)))
        previous = row
    return previous[-1]


def reference_scores(hypotheses: dict[str, str], references: list[dict]) -> dict:
    verified = [r for r in references if r.get("human_verified") is True
                and r.get("sample_id") in hypotheses and r.get("text", "").strip()]
    if not verified:
        return {"verified_samples": 0, "wer": None, "cer": None,
                "reason": "No human-verified reference; model outputs are not ground truth"}
    words = chars = word_errors = char_errors = 0
    for row in verified:
        ref, hyp = normalize(row["text"]), normalize(hypotheses[row["sample_id"]])
        words += len(ref.split())
        chars += len(ref)
        word_errors += edit_distance(ref.split(), hyp.split())
        char_errors += edit_distance(ref, hyp)
    return {"verified_samples": len(verified), "reference_words": words,
            "word_errors": word_errors, "wer": word_errors / words if words else None,
            "cer": char_errors / chars if chars else None,
            "normalization": "NFC, lowercase, punctuation removed; Vietnamese accents retained"}


def prepare(args) -> None:
    out = args.out
    if (out / "manifest.json").exists():
        raise RuntimeError("Manifest already exists: reuse it or select a new --out; do not overwrite evidence")
    with httpx.Client(timeout=30, trust_env=False) as client:
        assert_idle(client, args.base)
        health = get_json(client, args.base + "/api/health")
        stt = get_json(client, args.stt + "/health")
        selected = []
        target_phone = args.phone
        for page in range(1, 6):
            listing = get_json(client, args.base + f"/api/history?page={page}&limit=100")
            for row in listing.get("sessions", []):
                if not row.get("recording_path") or not row.get("phone"):
                    continue
                if row.get("status") != "ended" or row.get("duration_seconds", 0) < 10:
                    continue
                if not target_phone:
                    target_phone = row["phone"]
                if row["phone"] == target_phone:
                    selected.append(row)
                if len(selected) >= args.count:
                    break
            if len(selected) >= args.count or not listing.get("has_more"):
                break
        if not selected:
            raise RuntimeError("No completed recorded phone calls found")
        sessions, samples = [], []
        for row in selected:
            sid = row["session_id"]
            session = get_json(client, args.base + f"/api/sessions/{sid}")["session"]
            save_json(out / "sessions" / f"{sid}.json", session)
            recording = Path(session["recording_path"])
            audio, sr = sf.read(recording, dtype="float32", always_2d=True)
            customer = customer_channel(audio)
            spans, method = excerpts(customer, sr)
            entry = {"session_id": sid, "created_at": row["created_at"],
                     "session_duration_s": row["duration_seconds"],
                     "recording_duration_s": len(audio) / sr, "sample_rate": sr,
                     "recording_path": str(recording), "recording_sha256": sha256(recording),
                     "history_items": len(session.get("history", [])),
                     "turn_count": row["turn_count"], "segmentation": method}
            sessions.append(entry)
            # Preserve a convenient mono copy without touching the source recording.
            dest = out / "customer" / f"{sid}.wav"
            dest.parent.mkdir(parents=True, exist_ok=True)
            sf.write(dest, customer, sr, subtype="PCM_16")
            print("SESSION", json.dumps(entry, ensure_ascii=False), flush=True)
            for index, (a, b) in enumerate(spans, 1):
                sample_id = f"{sid}_{index:02d}"
                dest = out / "samples" / f"{sample_id}.wav"
                dest.parent.mkdir(parents=True, exist_ok=True)
                sf.write(dest, customer[a:b], sr, subtype="PCM_16")
                sample = {"sample_id": sample_id, "session_id": sid,
                          "path": str(dest.relative_to(out)), "start_s": a / sr,
                          "end_s": b / sr, "duration_s": (b-a) / sr,
                          "sha256": sha256(dest)}
                samples.append(sample)
                print("SAMPLE", json.dumps(sample), flush=True)
        logs = get_json(client, args.base + "/api/logs?ten=backend&so_dong=2000")
        save_json(out / "backend_log_snapshot.json", logs)
        from backend.config import settings
        from backend.services.stt_service import moi_tu_vung
        manifest = {"created_at": time.time(), "platform": platform.platform(),
                    "python": sys.version, "health": health, "stt_health": stt,
                    "prompt": moi_tu_vung(settings.stt_vung_mien),
                    "scope": "last completed recorded calls to same phone, newest first",
                    "recording_channel": "left/raw customer; no bot mixing; no denoise",
                    "reference_status": "UNVERIFIED - no human transcript available",
                    "sessions": sessions, "samples": samples}
        save_json(out / "manifest.json", manifest)
        save_json(out / "references.json", [{"sample_id": s["sample_id"],
                  "text": "", "human_verified": False} for s in samples])
        print("PREPARED", len(sessions), "calls", len(samples), "excerpts", flush=True)


def wav_bytes(audio: np.ndarray, sr: int) -> bytes:
    f = io.BytesIO()
    sf.write(f, audio, sr, format="WAV", subtype="PCM_16")
    return f.getvalue()


def run(args) -> None:
    manifest = load_json(args.out / "manifest.json")
    samples = manifest["samples"]
    if args.limit:
        samples = samples[:args.limit]
    with httpx.Client(timeout=60, trust_env=False) as client:
        assert_idle(client, args.base)
        if args.engine == "pho":
            from backend.services.stt_service import STTService, _don_token, _sua_nghe_nham
            service = STTService()
            model_meta = get_json(client, args.stt + "/health")
            name = "pho_" + args.prompt_mode

            def infer(audio, sr):
                response = client.post(args.stt + "/inference",
                    files={"file": ("sample.wav", wav_bytes(audio, sr), "audio/wav")},
                    data={"language": "vi", "temperature": "0", "response_format": "verbose_json",
                          "prompt": manifest["prompt"] if args.prompt_mode == "production" else ""})
                response.raise_for_status()
                data = response.json()
                raw = (data.get("text") or "").strip()
                text = _sua_nghe_nham(_don_token(raw))
                seg = data.get("segments") or []
                lp = min((s.get("avg_logprob", 0) for s in seg), default=0)
                ns = max((s.get("no_speech_prob", 0) for s in seg), default=0)
                reason = service._dang_ngo(text, ns, lp, len(audio) / sr)
                return {"text": text, "raw_text": raw, "logprob": lp,
                        "filter_rejection": reason, "no_speech_prob": ns,
                        "production_retry_replayed": False}
        else:
            os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
            os.environ["HF_HUB_DISABLE_XET"] = "1"
            sys.path.insert(0, str(args.out / "deps"))
            import sherpa_onnx
            from huggingface_hub import HfApi, hf_hub_download
            repo = ("g-group-ai-lab/gipformer1.5-65M-rnnt" if args.version == "1.5"
                    else "g-group-ai-lab/gipformer-65M-rnnt")
            revision = HfApi(token=False).model_info(repo).sha
            suffix = ".int8.onnx" if args.precision == "int8" else ".onnx"
            paths = {}
            for key in ("encoder", "decoder", "joiner", "tokens"):
                filename = "tokens.txt" if key == "tokens" else key + suffix
                paths[key] = hf_hub_download(repo, filename, revision=revision, token=False,
                    local_dir=args.out / "models" / repo.split("/")[-1])
                print("MODEL_FILE", filename, Path(paths[key]).stat().st_size, flush=True)
            model_meta = {"repo": repo, "revision": revision, "precision": args.precision,
                          "provider": "cpu", "threads": args.threads,
                          "decoding": args.decoding,
                          "files": {k: {"path": p, "sha256": sha256(Path(p))} for k, p in paths.items()}}
            recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(**paths,
                num_threads=args.threads, sample_rate=16000, feature_dim=80,
                decoding_method=args.decoding, provider="cpu")
            name = f"gip{args.version}_{args.precision}_{args.decoding}"

            def infer(audio, sr):
                if sr != 16000:
                    g = math.gcd(sr, 16000)
                    audio = resample_poly(audio, 16000 // g, sr // g).astype(np.float32)
                stream = recognizer.create_stream()
                stream.accept_waveform(16000, audio)
                recognizer.decode_streams([stream])
                return {"text": stream.result.text.strip()}

        output = args.out / "results" / f"{name}.json"
        if output.exists():
            raise RuntimeError(f"Results already exist: {output}; do not overwrite evidence")
        # Warm up with one actual excerpt, excluding model loading/download and warmup.
        audio, sr = sf.read(args.out / samples[0]["path"], dtype="float32")
        infer(audio, sr)
        results = []
        for index, sample in enumerate(samples):
            assert_idle(client, args.base)
            path = args.out / sample["path"]
            if sha256(path) != sample["sha256"]:
                raise RuntimeError(f"Sample changed since manifest: {path}")
            audio, sr = sf.read(path, dtype="float32")
            repeats = []
            for _ in range(args.repeats):
                start = time.perf_counter()
                answer = infer(audio, sr)
                repeats.append({**answer, "elapsed_ms": (time.perf_counter() - start) * 1000})
            row = {**sample, "runs": repeats, "text": repeats[0]["text"],
                   "median_ms": float(np.median([r["elapsed_ms"] for r in repeats]))}
            results.append(row)
            save_json(output, {"name": name, "model": model_meta, "completed": False,
                              "samples": results})
            print("RESULT", name, sample["sample_id"], f'{row["median_ms"]:.0f}ms',
                  json.dumps(row["text"], ensure_ascii=False), flush=True)
        latencies = [r["median_ms"] for r in results]
        duration = sum(r["duration_s"] for r in results)
        summary = {"samples": len(results), "audio_s": duration, "repeats": args.repeats,
                   "mean_ms": float(np.mean(latencies)), "p50_ms": float(np.median(latencies)),
                   "p95_ms": float(np.percentile(latencies, 95)),
                   "rtf": sum(latencies) / 1000 / duration,
                   "empty": sum(not r["text"] for r in results),
                   "repeat_disagreements": sum(len({normalize(x["text"]) for x in r["runs"]}) > 1
                                                for r in results),
                   "reference_scores": reference_scores({r["sample_id"]: r["text"] for r in results},
                                                        load_json(args.out / "references.json")),
                   "latency_scope": "offline full-excerpt decode; warmup/download excluded; not phone response time"}
        save_json(output, {"name": name, "model": model_meta, "completed": True,
                           "summary": summary, "samples": results})
        print("SUMMARY", name, json.dumps(summary, ensure_ascii=False), flush=True)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "run"])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--base", default="http://127.0.0.1:8100")
    parser.add_argument("--stt", default="http://127.0.0.1:8178")
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--phone", default="")
    parser.add_argument("--engine", choices=["pho", "gip"], default="pho")
    parser.add_argument("--prompt-mode", choices=["production", "none"], default="production")
    parser.add_argument("--version", choices=["1", "1.5"], default="1.5")
    parser.add_argument("--precision", choices=["int8", "fp32"], default="int8")
    parser.add_argument("--decoding", choices=["greedy_search", "modified_beam_search"], default="modified_beam_search")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    if args.repeats < 1 or args.count < 1 or args.threads < 1:
        parser.error("repeats/count/threads must be positive")
    if args.action == "prepare":
        prepare(args)
    else:
        run(args)


if __name__ == "__main__":
    main()
