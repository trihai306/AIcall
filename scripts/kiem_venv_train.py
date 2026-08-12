import sys
try:
    import torch
    print("  torch  ", torch.__version__, "| cuda", torch.cuda.is_available())
except Exception as e:
    print("  torch  KHONG CO:", e)
for m in ("unsloth", "peft", "trl", "transformers", "bitsandbytes", "datasets"):
    try:
        mod = __import__(m)
        print(f"  {m:<14} {getattr(mod, '__version__', 'OK')}")
    except Exception as e:
        print(f"  {m:<14} KHONG CO ({type(e).__name__})")
print("  python", sys.version.split()[0])
