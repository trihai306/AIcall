import inspect, sys, re
sys.stdout.reconfigure(encoding="utf-8")
import f5_tts.infer.utils_infer as u
s = inspect.getsource(u.infer_batch_process)
i = s.find("generated, _ = model_obj.sample")
print("=== phan goi sample va sau do ===")
print(s[i-200:i+1400])
print("\n=== vong lap o cuoi ===")
print(s[-1200:])
