import importlib, sys
mods = ["torch","torchaudio","torchcodec","sentence_transformers","f5_tts",
        "fastapi","uvicorn","faster_whisper","ctranslate2","chromadb",
        "librosa","soundfile","ollama"]
bad = 0
for m in mods:
    try:
        mod = importlib.import_module(m)
        print("  OK   %-22s %s" % (m, getattr(mod, "__version__", "")))
    except Exception as e:
        bad += 1
        print("  FAIL %-22s %s: %s" % (m, type(e).__name__, str(e)[:110]))
import torch
print("  CUDA available : %s" % torch.cuda.is_available())
if torch.cuda.is_available():
    print("  GPU            : %s" % torch.cuda.get_device_name(0))
    print("  VRAM total     : %.1f GB" % (torch.cuda.get_device_properties(0).total_memory/1024**3))
print("  --> %d/%d OK" % (len(mods)-bad, len(mods)))
