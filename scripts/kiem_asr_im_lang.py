"""Known no-speech controls, separate from the real-call accuracy evaluation.

Use downloaded benchmark models only; no service restart or outbound call.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from do_asr_call_that import DEFAULT_OUT, assert_idle, load_json, save_json, wav_bytes


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(DEFAULT_OUT / "deps"))
    import sherpa_onnx
    from backend.services.stt_service import STTService, _don_token, _sua_nghe_nham

    sr = 16000
    rng = np.random.default_rng(20260912)
    controls = {
        "digital_silence_1s": np.zeros(sr, dtype=np.float32),
        "digital_silence_4s": np.zeros(4 * sr, dtype=np.float32),
        "white_noise_rms8_3s": (rng.normal(size=sr * 3) * 8 / 32768).astype(np.float32),
        "tone450hz_rms1000_2s": (np.sin(np.arange(sr * 2) * 2 * np.pi * 450 / sr)
                                  * np.sqrt(2) * 1000 / 32768).astype(np.float32),
    }
    out = DEFAULT_OUT / "results" / "no_speech_controls.json"
    if out.exists():
        raise RuntimeError("Control results already exist; do not overwrite evidence")
    manifest = load_json(DEFAULT_OUT / "manifest.json")
    all_results = []
    with httpx.Client(timeout=60, trust_env=False) as client:
        assert_idle(client, "http://127.0.0.1:8100")
        service = STTService()
        for name, audio in controls.items():
            response = client.post("http://127.0.0.1:8178/inference",
                files={"file": ("control.wav", wav_bytes(audio, sr), "audio/wav")},
                data={"language": "vi", "response_format": "verbose_json",
                      "temperature": "0", "prompt": manifest["prompt"]})
            response.raise_for_status()
            data = response.json()
            text = _sua_nghe_nham(_don_token(data.get("text") or ""))
            segments = data.get("segments") or []
            lp = min((s.get("avg_logprob", 0) for s in segments), default=0)
            ns = max((s.get("no_speech_prob", 0) for s in segments), default=0)
            row = {"engine": "pho_production", "sample": name, "text": text,
                   "filter_rejection": service._dang_ngo(text, ns, lp, len(audio)/sr),
                   "known_no_speech": True}
            all_results.append(row)
            print(row, flush=True)
        for precision in ("int8", "fp32"):
            previous = load_json(DEFAULT_OUT / "results" / f"gip1.5_{precision}_modified_beam_search.json")
            paths = {k: v["path"] for k, v in previous["model"]["files"].items()}
            rec = sherpa_onnx.OfflineRecognizer.from_transducer(**paths,
                num_threads=4, sample_rate=16000, feature_dim=80,
                decoding_method="modified_beam_search", provider="cpu")
            for name, audio in controls.items():
                assert_idle(client, "http://127.0.0.1:8100")
                stream = rec.create_stream()
                stream.accept_waveform(sr, audio)
                rec.decode_streams([stream])
                row = {"engine": f"gip1.5_{precision}", "sample": name,
                       "text": stream.result.text.strip(), "known_no_speech": True}
                all_results.append(row)
                print(row, flush=True)
            del rec
        save_json(out, {"created_at": time.time(), "results": all_results,
                       "scope": "synthetic known-no-speech only; bypasses production VAD",
                       "real_call_accuracy": None})
        assert_idle(client, "http://127.0.0.1:8100")


if __name__ == "__main__":
    main()
